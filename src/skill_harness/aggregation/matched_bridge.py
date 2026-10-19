"""Read-only bridge from matched task-family evidence to Gate-2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from skill_harness.aggregation.profile import EffectEstimate, effect_from_matched_gate2
from skill_harness.aggregation.verdict import (
    ValueClass,
    VerdictResult,
    matched_gate2_verdict,
)
from skill_harness.oc import Gate2Decision, Gate2Design
from skill_harness.task_frontier import (
    Arm,
    Phase,
    StoredObservation,
    TaskFamilyManifest,
    audit_observation,
    matched_evidence,
)

_PairKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class MatchedCellObservationIds:
    """Full/null observation-id pairs assigned to each paired-outcome cell."""

    both_pass: tuple[tuple[str, str], ...]
    full_only: tuple[tuple[str, str], ...]
    null_only: tuple[tuple[str, str], ...]
    both_fail: tuple[tuple[str, str], ...]


class MatchedRefusalReason(StrEnum):
    """Named reasons that prevent matched evidence from producing a decision."""

    NO_EVIDENCE = "no-evidence"
    """The store holds no matched row for this family version at all.

    Reserved for an empty read. It must not be returned when rows were stored
    and then rejected: `no-evidence` says the collection never happened, which
    implies collecting again would resolve the family. `INADMISSIBLE` is the
    reason for rows that exist and cannot be used.
    """
    INADMISSIBLE = "inadmissible"
    """Matched rows exist for this family version and every one is inadmissible.

    The distinction from `NO_EVIDENCE` is the one `UnmeasuredSubReason.NO_DATA`
    and `UnmeasuredSubReason.INADMISSIBLE` draw at the clause layer, and it is
    drawn for the same reason: the family has data and no admissible data, so
    re-running the family is not the fix. The term is the ratified one
    (`docs/concepts/why-unmeasured.md`), spelled as that vocabulary spells it.
    """
    DUPLICATE_ARM = "duplicate-arm"
    MISSING_ARM = "missing-arm"
    COUNT_MISMATCH = "count-mismatch"


class ExcludedObservationReason(StrEnum):
    """Named reasons that prevent one stored observation from entering a pair."""

    INADMISSIBLE = "inadmissible"


class RefusedPairReason(StrEnum):
    """Named reasons that prevent one pairing key from entering a decision."""

    DUPLICATE_ARM = "duplicate-arm"
    MISSING_ARM = "missing-arm"


@dataclass(frozen=True)
class ExcludedObservation:
    """One observation excluded before pair construction."""

    observation_id: str
    reason: ExcludedObservationReason
    stored_reason: str | None


@dataclass(frozen=True)
class RefusedPair:
    """One malformed pairing key and every observation filed under it."""

    pairing_key: _PairKey
    observation_ids: tuple[str, ...]
    reason: RefusedPairReason


@dataclass(frozen=True)
class ExclusionLedger:
    """Every stored observation or pair omitted from a Gate-2 decision."""

    excluded_observations: tuple[ExcludedObservation, ...]
    refused_pairs: tuple[RefusedPair, ...]


@dataclass(frozen=True)
class MatchedRefusal:
    """A typed explanation for a bridge result with no decision."""

    reason: MatchedRefusalReason


@dataclass(frozen=True)
class MatchedGate2Decision:
    """Gate-2 decision bound to the frozen family evidence that produced it."""

    effect: EffectEstimate
    decision: Gate2Decision
    verdict: VerdictResult
    task_family_id: str
    task_family_version: str
    observation_ids: MatchedCellObservationIds
    ledger: ExclusionLedger
    refusal: Literal[None] = None


@dataclass(frozen=True)
class MatchedGate2Refusal:
    """Typed refusal bound to the frozen family evidence that prevented a decision."""

    effect: Literal[None]
    decision: Literal[None]
    verdict: Literal[None]
    task_family_id: str
    task_family_version: str
    observation_ids: MatchedCellObservationIds
    ledger: ExclusionLedger
    refusal: MatchedRefusal


type MatchedGate2Result = MatchedGate2Decision | MatchedGate2Refusal


def _all_matched_evidence(
    conn: sqlite3.Connection, manifest: TaskFamilyManifest
) -> tuple[StoredObservation, ...]:
    """Every stored matched row for this family version, admissible or not.

    The admissible rows come from ``matched_evidence()`` and only from there: it
    is the registered estimator feed, so nothing that can reach a Gate-2
    decision is read around it. The supplementary query is scoped to the
    inadmissible tail, which the ledger has to name and which no seam exposes
    today — widening it to every row would make the estimator feed a dead call
    and put the decision path on a raw read.
    ``test_admissible_rows_reach_a_decision_only_through_the_registered_feed``
    stubs the feed empty and requires the eight admissible rows in the store to
    stay out of the result; before it existed, that widening was green.

    ``ORDER BY observation_id`` matches the feed's own rule (a unique key, never
    a timestamp), and the returned tuple is sorted again over the merged keys —
    concatenating two sorted feeds does not produce a sorted sequence. The two
    overlap today: delete either one and the exclusion ledger still comes back in
    id order, delete both and two stores holding the same rows in opposite
    physical order return different ledgers.
    ``test_shuffled_insertion_order_produces_identical_result_objects`` fails on
    the pair, not on either alone — and, since it asserts the ledger's id order
    rather than only the two stores' agreement, it also fails on an ordering that
    is deterministic but not by observation_id.

    ``audit_observation`` reads by id across ALL THREE partitions and returns the
    first hit, so its answer is only the row this query named while no other
    partition holds the same id. `admit` refuses that write; a store written
    around `admit` can hold it, and then the by-id read answers with the
    calibration row and the effect estimate acquires rung-selection data — the
    leak INVARIANTS #7 walls off. The phase stamp settles it: each partition
    CHECKs its own phase column (migration 0700), so a record stamped `matched`
    came out of the matched table, and that table's PRIMARY KEY makes it the row
    the query named. A record stamped anything else is a store that contradicts
    itself about one id, which is not an evidence judgment and does not get a
    typed refusal — `admit` raises on the same condition, and
    ``get_task_frontier_observation_by_id`` already says an ambiguous audit read
    is worse than a refused write.
    """
    records = {record.observation_id: record for record in matched_evidence(conn, manifest)}
    rows = conn.execute(
        """
        SELECT observation_id
        FROM task_frontier_matched_obs
        WHERE task_family_id = ?
          AND task_family_version = ?
          AND admissibility_state != 'admissible'
        ORDER BY observation_id
        """,
        (manifest.task_family_id, manifest.task_family_version),
    ).fetchall()
    for (observation_id,) in rows:
        stored = audit_observation(conn, str(observation_id))
        if stored is None:
            continue
        if stored.phase is not Phase.MATCHED:
            raise ValueError(
                f"observation_id {stored.observation_id!r} names a matched row in this "
                f"family version and comes back from the by-id audit read stamped "
                f"{stored.phase.value!r} — the same id is stored in two partitions, so the "
                "matched row cannot be resolved and a walled-off row would enter the "
                "effect path in its place"
            )
        records[stored.observation_id] = stored
    return tuple(records[observation_id] for observation_id in sorted(records))


def _pair_evidence(
    records: tuple[StoredObservation, ...],
) -> tuple[MatchedCellObservationIds, ExclusionLedger]:
    pairs: dict[_PairKey, list[StoredObservation]] = {}
    excluded: list[ExcludedObservation] = []
    for record in records:
        if record.admissibility_state != "admissible":
            excluded.append(
                ExcludedObservation(
                    observation_id=record.observation_id,
                    reason=ExcludedObservationReason.INADMISSIBLE,
                    stored_reason=record.inadmissibility_reason,
                )
            )
            continue
        key = (
            record.task_family_id,
            record.task_family_version,
            record.semantic_lineage_id,
            record.instance_id,
        )
        pairs.setdefault(key, []).append(record)

    cells: list[list[tuple[str, str]]] = [[], [], [], []]
    refused: list[RefusedPair] = []
    for key in sorted(pairs):
        records_for_key = sorted(pairs[key], key=lambda record: record.observation_id)
        by_arm: dict[Arm, list[StoredObservation]] = {Arm.FULL: [], Arm.NULL: []}
        for record in records_for_key:
            by_arm[record.arm].append(record)
        ids = tuple(record.observation_id for record in records_for_key)
        if any(len(arm_records) > 1 for arm_records in by_arm.values()):
            refused.append(RefusedPair(key, ids, RefusedPairReason.DUPLICATE_ARM))
            continue
        if any(not arm_records for arm_records in by_arm.values()):
            refused.append(RefusedPair(key, ids, RefusedPairReason.MISSING_ARM))
            continue
        full = by_arm[Arm.FULL][0]
        null = by_arm[Arm.NULL][0]
        cell_index = {
            (True, True): 0,
            (True, False): 1,
            (False, True): 2,
            (False, False): 3,
        }[(full.passed, null.passed)]
        cells[cell_index].append((full.observation_id, null.observation_id))

    return (
        MatchedCellObservationIds(
            both_pass=tuple(cells[0]),
            full_only=tuple(cells[1]),
            null_only=tuple(cells[2]),
            both_fail=tuple(cells[3]),
        ),
        ExclusionLedger(excluded_observations=tuple(excluded), refused_pairs=tuple(refused)),
    )


def aggregate_matched_gate2(
    conn: sqlite3.Connection,
    manifest: TaskFamilyManifest,
    design: Gate2Design,
    *,
    value_class: ValueClass | None,
) -> MatchedGate2Result:
    """Read and aggregate one frozen task family's stored matched evidence.

    `value_class` is required and has no default. The verdict layer withholds
    `CUT(subsumed)` and `CUT(no_lift)` for every class except
    `TRANSFORMATIVE_LIFT`, and it treats an unset class the same way, so a
    default would let a caller skip the decision while looking correct. This
    manifest carries a task family, not a skill name, so Path C cannot look the
    class up for itself: whoever knows the subject supplies it, and a caller
    that genuinely does not know one passes `None` in writing.

    Malformed evidence no longer raises. An inadmissible observation or a pair
    that cannot be completed is filed in the returned ``ledger`` and named
    there; a family that cannot produce a decision at all comes back as a
    ``MatchedGate2Refusal`` carrying the reason. Nothing is dropped silently.

    Reason precedence when no decision is possible: a duplicate arm first (the
    store contradicts itself about one instance, so no count from it is
    trustworthy), then — with no pair surviving — a pair that lost an arm, then
    rows that were all inadmissible, then an empty read. The last two are
    separated deliberately: `NO_EVIDENCE` means nothing was collected and
    `INADMISSIBLE` means what was collected cannot be used, and the ratified
    sub-reason vocabulary refuses to spend one word on both conditions.
    """
    observation_ids, ledger = _pair_evidence(_all_matched_evidence(conn, manifest))
    both_pass = observation_ids.both_pass
    full_only = observation_ids.full_only
    null_only = observation_ids.null_only
    both_fail = observation_ids.both_fail
    complete_pair_count = sum(map(len, (both_pass, full_only, null_only, both_fail)))
    refusal_reason: MatchedRefusalReason | None = None
    pair_reasons = {pair.reason for pair in ledger.refused_pairs}
    if RefusedPairReason.DUPLICATE_ARM in pair_reasons:
        refusal_reason = MatchedRefusalReason.DUPLICATE_ARM
    elif complete_pair_count == 0:
        if RefusedPairReason.MISSING_ARM in pair_reasons:
            refusal_reason = MatchedRefusalReason.MISSING_ARM
        elif ledger.excluded_observations:
            refusal_reason = MatchedRefusalReason.INADMISSIBLE
        else:
            refusal_reason = MatchedRefusalReason.NO_EVIDENCE
    elif complete_pair_count != design.n_pairs:
        refusal_reason = MatchedRefusalReason.COUNT_MISMATCH
    if refusal_reason is not None:
        return MatchedGate2Refusal(
            effect=None,
            decision=None,
            verdict=None,
            task_family_id=manifest.task_family_id,
            task_family_version=manifest.task_family_version,
            observation_ids=observation_ids,
            ledger=ledger,
            refusal=MatchedRefusal(refusal_reason),
        )
    effect = effect_from_matched_gate2(
        design,
        both_pass=len(both_pass),
        full_only=len(full_only),
        null_only=len(null_only),
        both_fail=len(both_fail),
    )
    if effect.decision is None:
        raise ValueError("matched Gate-2 effect must carry a decision")
    return MatchedGate2Decision(
        effect=effect,
        decision=effect.decision,
        verdict=matched_gate2_verdict(effect, value_class=value_class),
        task_family_id=manifest.task_family_id,
        task_family_version=manifest.task_family_version,
        observation_ids=observation_ids,
        ledger=ledger,
        refusal=None,
    )
