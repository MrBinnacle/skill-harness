"""Store-to-Gate-2 bridge for frozen matched task-family evidence (#246)."""

from __future__ import annotations

import dataclasses
import inspect
import sqlite3
from typing import Any

import pytest

from skill_harness.aggregation import (
    ExcludedObservationReason,
    MatchedRefusalReason,
    RefusedPairReason,
    aggregate_matched_gate2,
)
from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict
from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec, gate2_decide
from skill_harness.task_frontier import (
    Arm,
    Observation,
    TaskFamilyManifest,
    admit,
    audit_observation,
    load_manifest,
)


def _manifest_data(n_pairs: int) -> dict[str, Any]:
    return {
        "task_family_id": "synthetic-e1-family",
        "task_family_version": "1",
        "frozen_hashes": {
            "generator": "gen-sha-e1",
            "fixture": "fix-sha-e1",
            "oracle": "ora-sha-e1",
            "harness": "har-sha-e1",
            "code": "cod-sha-e1",
        },
        "phase_partition": {
            "calibration": [],
            "confirmation": [],
            "matched": [f"lineage-{index}" for index in range(n_pairs)],
        },
        "confirmation_attempt_budget": 0,
    }


def _store_table(
    conn: sqlite3.Connection,
    *,
    both_pass: int,
    full_only: int,
    null_only: int,
    both_fail: int,
) -> TaskFamilyManifest:
    outcomes = (
        [(True, True)] * both_pass
        + [(True, False)] * full_only
        + [(False, True)] * null_only
        + [(False, False)] * both_fail
    )
    manifest = load_manifest(_manifest_data(len(outcomes)))
    for index, (full_passed, null_passed) in enumerate(outcomes):
        lineage = f"lineage-{index}"
        instance = f"instance-{index}"
        for arm, passed in ((Arm.FULL, full_passed), (Arm.NULL, null_passed)):
            admission = admit(
                conn,
                manifest,
                Observation(
                    observation_id=f"obs-{index:02d}-{arm.value}",
                    semantic_lineage_id=lineage,
                    instance_id=instance,
                    arm=arm,
                    passed=passed,
                    generator_fingerprint="gen-sha-e1",
                    oracle_fingerprint="ora-sha-e1",
                    observed_at="2026-08-16T12:00:00+00:00",
                ),
            )
            assert admission.admissible is True
    return manifest


def _design(n_pairs: int) -> Gate2Design:
    return Gate2Design(
        n_pairs=n_pairs,
        gamma=0.90,
        mme=MMESpec(delta_min=0.20, q_min=0.70),
    )


def _insert_matched_row(
    conn: sqlite3.Connection,
    manifest: TaskFamilyManifest,
    *,
    observation_id: str,
    lineage: str,
    instance: str,
    arm: Arm,
    passed: bool,
    admissibility_state: str = "admissible",
    inadmissibility_reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO task_frontier_matched_obs (
            observation_id, task_family_id, task_family_version,
            semantic_lineage_id, phase, instance_id, arm, passed,
            generator_fingerprint, oracle_fingerprint, admissibility_state,
            inadmissibility_reason, observed_at, ingested_at
        ) VALUES (?, ?, ?, ?, 'matched', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            manifest.task_family_id,
            manifest.task_family_version,
            lineage,
            instance,
            arm.value,
            int(passed),
            "gen-sha-e1",
            "ora-sha-e1",
            admissibility_state,
            inadmissibility_reason,
            "2026-08-16T12:00:00+00:00",
            "2026-08-16T12:00:01Z",
        ),
    )


def test_empty_store_returns_typed_no_evidence_refusal(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(_manifest_data(1))

    result = aggregate_matched_gate2(evidence_db, manifest, _design(1))

    assert result.decision is None
    assert result.refusal is not None
    assert result.refusal.reason is MatchedRefusalReason.NO_EVIDENCE
    assert result.ledger.excluded_observations == ()
    assert result.ledger.refused_pairs == ()


def test_duplicate_arm_returns_typed_refusal_with_complete_pair_ledger(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(_manifest_data(1))
    for observation_id, arm in (
        ("obs-full-a", Arm.FULL),
        ("obs-full-b", Arm.FULL),
        ("obs-null", Arm.NULL),
    ):
        _insert_matched_row(
            evidence_db,
            manifest,
            observation_id=observation_id,
            lineage="lineage-0",
            instance="instance-0",
            arm=arm,
            passed=True,
        )

    result = aggregate_matched_gate2(evidence_db, manifest, _design(1))

    assert result.decision is None
    assert result.refusal is not None
    assert result.refusal.reason is MatchedRefusalReason.DUPLICATE_ARM
    assert result.ledger.excluded_observations == ()
    assert len(result.ledger.refused_pairs) == 1
    refused = result.ledger.refused_pairs[0]
    assert refused.reason is RefusedPairReason.DUPLICATE_ARM
    assert refused.observation_ids == ("obs-full-a", "obs-full-b", "obs-null")


def test_missing_arm_returns_typed_refusal_with_pair_ledger(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(_manifest_data(1))
    _insert_matched_row(
        evidence_db,
        manifest,
        observation_id="obs-full",
        lineage="lineage-0",
        instance="instance-0",
        arm=Arm.FULL,
        passed=True,
    )

    result = aggregate_matched_gate2(evidence_db, manifest, _design(1))

    assert result.decision is None
    assert result.refusal is not None
    assert result.refusal.reason is MatchedRefusalReason.MISSING_ARM
    assert result.ledger.excluded_observations == ()
    assert len(result.ledger.refused_pairs) == 1
    refused = result.ledger.refused_pairs[0]
    assert refused.reason is RefusedPairReason.MISSING_ARM
    assert refused.observation_ids == ("obs-full",)


def test_inadmissible_only_returns_typed_no_evidence_refusal_with_observation_ledger(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(_manifest_data(1))
    _insert_matched_row(
        evidence_db,
        manifest,
        observation_id="obs-inadmissible",
        lineage="lineage-0",
        instance="instance-0",
        arm=Arm.FULL,
        passed=True,
        admissibility_state="inadmissible",
        inadmissibility_reason="synthetic-fingerprint-drift",
    )

    result = aggregate_matched_gate2(evidence_db, manifest, _design(1))

    assert result.decision is None
    assert result.refusal is not None
    assert result.refusal.reason is MatchedRefusalReason.NO_EVIDENCE
    assert result.ledger.refused_pairs == ()
    assert len(result.ledger.excluded_observations) == 1
    excluded = result.ledger.excluded_observations[0]
    assert excluded.observation_id == "obs-inadmissible"
    assert excluded.reason is ExcludedObservationReason.INADMISSIBLE
    assert excluded.stored_reason == "synthetic-fingerprint-drift"


def test_surviving_pair_count_mismatch_returns_typed_refusal_without_exception(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = _store_table(
        evidence_db,
        both_pass=0,
        full_only=1,
        null_only=0,
        both_fail=0,
    )

    result = aggregate_matched_gate2(evidence_db, manifest, _design(2))

    assert result.decision is None
    assert result.refusal is not None
    assert result.refusal.reason is MatchedRefusalReason.COUNT_MISMATCH
    assert result.observation_ids.full_only == (("obs-00-full", "obs-00-null"),)
    assert result.ledger.excluded_observations == ()
    assert result.ledger.refused_pairs == ()


def test_decided_result_ledgers_inadmissible_observation_and_incomplete_pair(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = load_manifest(_manifest_data(3))
    for observation_id, lineage, instance, arm, state, stored_reason in (
        ("obs-valid-full", "lineage-0", "instance-0", Arm.FULL, "admissible", None),
        ("obs-valid-null", "lineage-0", "instance-0", Arm.NULL, "admissible", None),
        (
            "obs-inadmissible",
            "lineage-1",
            "instance-1",
            Arm.FULL,
            "inadmissible",
            "synthetic-oracle-drift",
        ),
        ("obs-incomplete", "lineage-2", "instance-2", Arm.NULL, "admissible", None),
    ):
        _insert_matched_row(
            evidence_db,
            manifest,
            observation_id=observation_id,
            lineage=lineage,
            instance=instance,
            arm=arm,
            passed=True,
            admissibility_state=state,
            inadmissibility_reason=stored_reason,
        )

    result = aggregate_matched_gate2(evidence_db, manifest, _design(1))

    assert result.decision is Gate2Decision.UNRESOLVED
    assert result.refusal is None
    assert result.observation_ids.both_pass == (("obs-valid-full", "obs-valid-null"),)
    assert tuple(item.observation_id for item in result.ledger.excluded_observations) == (
        "obs-inadmissible",
    )
    assert tuple(item.stored_reason for item in result.ledger.excluded_observations) == (
        "synthetic-oracle-drift",
    )
    assert len(result.ledger.refused_pairs) == 1
    assert result.ledger.refused_pairs[0].reason is RefusedPairReason.MISSING_ARM
    assert result.ledger.refused_pairs[0].observation_ids == ("obs-incomplete",)


@pytest.mark.parametrize(
    ("both_pass", "full_only", "null_only", "both_fail"),
    [
        (0, 8, 0, 0),
        (0, 3, 0, 5),
        (0, 0, 0, 8),
    ],
)
@pytest.mark.parametrize(
    "gamma,delta_min,q_min",
    [
        (0.90, 0.20, 0.70),
        (0.95, 0.10, 0.80),
    ],
)
def test_bridge_decision_reproduces_direct_gate2_for_registered_e1_shapes(
    evidence_db: sqlite3.Connection,
    both_pass: int,
    full_only: int,
    null_only: int,
    both_fail: int,
    gamma: float,
    delta_min: float,
    q_min: float,
) -> None:
    manifest = _store_table(
        evidence_db,
        both_pass=both_pass,
        full_only=full_only,
        null_only=null_only,
        both_fail=both_fail,
    )
    design = Gate2Design(
        n_pairs=8,
        gamma=gamma,
        mme=MMESpec(delta_min=delta_min, q_min=q_min),
    )

    result = aggregate_matched_gate2(evidence_db, manifest, design)

    assert result.decision is gate2_decide(design, full_only, null_only)


@pytest.mark.parametrize(
    (
        "both_pass",
        "full_only",
        "null_only",
        "both_fail",
        "expected",
        "expected_verdict",
        "expected_cut_reason",
    ),
    [
        (4, 8, 0, 4, Gate2Decision.BENEFIT, KeepCutVerdict.KEEP, None),
        (4, 0, 8, 4, Gate2Decision.HARM, KeepCutVerdict.CUT, CutSubReason.HARMFUL),
        (6, 2, 2, 6, Gate2Decision.EQUIVALENT, KeepCutVerdict.CANT_TELL_YET, None),
        (5, 5, 1, 5, Gate2Decision.UNRESOLVED, KeepCutVerdict.CANT_TELL_YET, None),
    ],
)
def test_every_terminal_decision_is_reached_through_the_store_bridge_path(
    evidence_db: sqlite3.Connection,
    both_pass: int,
    full_only: int,
    null_only: int,
    both_fail: int,
    expected: Gate2Decision,
    expected_verdict: KeepCutVerdict,
    expected_cut_reason: CutSubReason | None,
) -> None:
    manifest = _store_table(
        evidence_db,
        both_pass=both_pass,
        full_only=full_only,
        null_only=null_only,
        both_fail=both_fail,
    )
    design = Gate2Design(
        n_pairs=16,
        gamma=0.90,
        mme=MMESpec(delta_min=0.20, q_min=0.70),
    )

    result = aggregate_matched_gate2(evidence_db, manifest, design)

    assert result.decision is expected
    assert result.verdict.verdict is expected_verdict
    assert result.verdict.cut_sub_reason is expected_cut_reason


def test_result_is_immutable_and_binds_effect_identity_and_ids_to_each_cell(
    evidence_db: sqlite3.Connection,
) -> None:
    manifest = _store_table(
        evidence_db,
        both_pass=1,
        full_only=1,
        null_only=1,
        both_fail=1,
    )
    design = Gate2Design(
        n_pairs=4,
        gamma=0.90,
        mme=MMESpec(delta_min=0.20, q_min=0.70),
    )

    result = aggregate_matched_gate2(evidence_db, manifest, design)

    assert result.effect is not None
    assert result.effect.decision is result.decision
    assert result.task_family_id == "synthetic-e1-family"
    assert result.task_family_version == "1"
    assert result.observation_ids.both_pass == (("obs-00-full", "obs-00-null"),)
    assert result.observation_ids.full_only == (("obs-01-full", "obs-01-null"),)
    assert result.observation_ids.null_only == (("obs-02-full", "obs-02-null"),)
    assert result.observation_ids.both_fail == (("obs-03-full", "obs-03-null"),)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.task_family_id = "changed"  # type: ignore[misc]


def test_result_ids_alone_reproduce_the_four_cell_table_and_decision(
    evidence_db: sqlite3.Connection,
) -> None:
    """Rebuild the table from the ids themselves, not from how many there are.

    Counting each cell's tuples only re-reads a length the same call produced: a
    bridge that files a concordant pair in the wrong concordant cell keeps every
    count intact and survives it (swap the both_pass and both_fail cell indices
    and this test stayed green). So each id is read back out of the store through
    the by-id audit seam and the cell is re-derived from the two stored ``passed``
    booleans.
    """
    manifest = _store_table(
        evidence_db,
        both_pass=5,
        full_only=5,
        null_only=1,
        both_fail=5,
    )
    design = Gate2Design(
        n_pairs=16,
        gamma=0.90,
        mme=MMESpec(delta_min=0.20, q_min=0.70),
    )

    result = aggregate_matched_gate2(evidence_db, manifest, design)
    ids = result.observation_ids
    cell_of_outcome = {(True, True): 0, (True, False): 1, (False, True): 2, (False, False): 3}
    rebuilt_table = [0, 0, 0, 0]
    for filed_cell, cell in enumerate((ids.both_pass, ids.full_only, ids.null_only, ids.both_fail)):
        for full_id, null_id in cell:
            full = audit_observation(evidence_db, full_id)
            null = audit_observation(evidence_db, null_id)
            assert full is not None and null is not None
            assert (full.arm, null.arm) == (Arm.FULL, Arm.NULL)
            stored_cell = cell_of_outcome[(full.passed, null.passed)]
            assert stored_cell == filed_cell, (
                f"{full_id}/{null_id} passed=({full.passed}, {null.passed}) belongs in cell "
                f"{stored_cell}, filed in {filed_cell}"
            )
            rebuilt_table[stored_cell] += 1

    assert tuple(rebuilt_table) == (5, 5, 1, 5)
    assert sum(rebuilt_table) == design.n_pairs
    assert gate2_decide(design, rebuilt_table[1], rebuilt_table[2]) is result.decision


def test_bridge_has_one_public_entry_point_with_only_registered_inputs() -> None:
    """Pin the entry point the bridge DEFINES, not how it spells its imports.

    The set is scoped by ``__module__`` on purpose. A namespace query alone
    (``vars(bridge)`` filtered on the leading underscore) also matches every
    function the module imported — ``matched_evidence``, ``effect_from_matched_gate2``,
    ``matched_gate2_verdict``, ``dataclass`` — none of which is an entry point the
    bridge exposes; Python has no module-private import. Under that query the
    criterion is satisfiable by renaming the imports to ``_matched_evidence`` and
    friends, which changes no interface and was how this assertion was first made
    to pass. Scoping to functions defined here cannot be satisfied that way: it
    goes red when the module grows a second public function and stays green
    however the imports are spelled.
    """
    import skill_harness.aggregation.matched_bridge as bridge

    assert list(inspect.signature(aggregate_matched_gate2).parameters) == [
        "conn",
        "manifest",
        "design",
    ]
    defined_public_callables = {
        name
        for name, value in vars(bridge).items()
        if not name.startswith("_")
        and inspect.isfunction(value)
        and value.__module__ == bridge.__name__
    }
    assert defined_public_callables == {"aggregate_matched_gate2"}
    # The seam callers reach through the package is the seam these tests drive.
    assert bridge.aggregate_matched_gate2 is aggregate_matched_gate2
