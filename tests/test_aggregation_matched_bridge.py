"""Store-to-Gate-2 bridge for frozen matched task-family evidence (#246)."""

from __future__ import annotations

import dataclasses
import sqlite3
from typing import Any

import pytest

from skill_harness.aggregation import aggregate_matched_gate2
from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict
from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec, gate2_decide
from skill_harness.task_frontier import (
    Arm,
    Observation,
    TaskFamilyManifest,
    admit,
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

    assert result.effect.decision is result.decision
    assert result.task_family_id == "synthetic-e1-family"
    assert result.task_family_version == "1"
    assert result.observation_ids.both_pass == (("obs-00-full", "obs-00-null"),)
    assert result.observation_ids.full_only == (("obs-01-full", "obs-01-null"),)
    assert result.observation_ids.null_only == (("obs-02-full", "obs-02-null"),)
    assert result.observation_ids.both_fail == (("obs-03-full", "obs-03-null"),)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.task_family_id = "changed"  # type: ignore[misc]
