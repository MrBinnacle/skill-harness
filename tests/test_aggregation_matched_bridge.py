"""Store-to-Gate-2 bridge for frozen matched task-family evidence (#246)."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from skill_harness.aggregation import aggregate_matched_gate2
from skill_harness.oc import Gate2Design, MMESpec, gate2_decide
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
