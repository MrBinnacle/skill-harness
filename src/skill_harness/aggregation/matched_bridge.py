"""Read-only bridge from matched task-family evidence to Gate-2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from skill_harness.aggregation.profile import EffectEstimate, effect_from_matched_gate2
from skill_harness.aggregation.verdict import VerdictResult, matched_gate2_verdict
from skill_harness.oc import Gate2Decision, Gate2Design
from skill_harness.task_frontier import (
    Arm,
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

    ``ORDER BY observation_id`` matches the feed's own rule (a unique key, never
    a timestamp), and the returned tuple is sorted again over the merged keys —
    concatenating two sorted feeds does not produce a sorted sequence. The two
    overlap today: delete either one and the exclusion ledger still comes back in
    id order, delete both and two stores holding the same rows in opposite
    physical order return different ledgers.
    ``test_shuffled_insertion_order_produces_identical_result_objects`` fails on
    the pair, not on either alone.
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
        if stored is not None:
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
) -> MatchedGate2Result:
    """Read and aggregate one frozen task family's stored matched evidence.

    Malformed evidence no longer raises. An inadmissible observation or a pair
    that cannot be completed is filed in the returned ``ledger`` and named
    there; a family that cannot produce a decision at all comes back as a
    ``MatchedGate2Refusal`` carrying the reason. Nothing is dropped silently.
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
        verdict=matched_gate2_verdict(effect),
        task_family_id=manifest.task_family_id,
        task_family_version=manifest.task_family_version,
        observation_ids=observation_ids,
        ledger=ledger,
        refusal=None,
    )
