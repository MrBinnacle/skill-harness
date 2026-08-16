"""Read-only bridge from matched task-family evidence to Gate-2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from skill_harness.aggregation.profile import EffectEstimate, effect_from_matched_gate2
from skill_harness.aggregation.verdict import VerdictResult, matched_gate2_verdict
from skill_harness.oc import Gate2Decision, Gate2Design
from skill_harness.task_frontier import Arm, StoredObservation, TaskFamilyManifest, matched_evidence

_PairKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class MatchedCellObservationIds:
    """Full/null observation-id pairs assigned to each paired-outcome cell."""

    both_pass: tuple[tuple[str, str], ...]
    full_only: tuple[tuple[str, str], ...]
    null_only: tuple[tuple[str, str], ...]
    both_fail: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MatchedGate2Result:
    """Gate-2 result bound to the frozen family evidence that produced it."""

    effect: EffectEstimate
    decision: Gate2Decision
    verdict: VerdictResult
    task_family_id: str
    task_family_version: str
    observation_ids: MatchedCellObservationIds


def _pair_evidence(
    records: tuple[StoredObservation, ...],
) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
]:
    pairs: dict[_PairKey, dict[Arm, StoredObservation]] = {}
    for record in records:
        key = (
            record.task_family_id,
            record.task_family_version,
            record.semantic_lineage_id,
            record.instance_id,
        )
        by_arm = pairs.setdefault(key, {})
        if record.arm in by_arm:
            raise ValueError(f"matched pair {key!r} contains duplicate {record.arm.value!r} arms")
        by_arm[record.arm] = record

    cells: list[list[tuple[str, str]]] = [[], [], [], []]
    for key in sorted(pairs):
        by_arm = pairs[key]
        if set(by_arm) != {Arm.FULL, Arm.NULL}:
            raise ValueError(f"matched pair {key!r} must contain one full arm and one null arm")
        full = by_arm[Arm.FULL]
        null = by_arm[Arm.NULL]
        cell_index = {
            (True, True): 0,
            (True, False): 1,
            (False, True): 2,
            (False, False): 3,
        }[(full.passed, null.passed)]
        cells[cell_index].append((full.observation_id, null.observation_id))

    return tuple(cells[0]), tuple(cells[1]), tuple(cells[2]), tuple(cells[3])


def aggregate_matched_gate2(
    conn: sqlite3.Connection,
    manifest: TaskFamilyManifest,
    design: Gate2Design,
) -> MatchedGate2Result:
    """Read and aggregate one frozen task family's well-formed matched evidence."""
    both_pass, full_only, null_only, both_fail = _pair_evidence(matched_evidence(conn, manifest))
    effect = effect_from_matched_gate2(
        design,
        both_pass=len(both_pass),
        full_only=len(full_only),
        null_only=len(null_only),
        both_fail=len(both_fail),
    )
    if effect.decision is None:
        raise ValueError("matched Gate-2 effect must carry a decision")
    return MatchedGate2Result(
        effect=effect,
        decision=effect.decision,
        verdict=matched_gate2_verdict(effect),
        task_family_id=manifest.task_family_id,
        task_family_version=manifest.task_family_version,
        observation_ids=MatchedCellObservationIds(
            both_pass=both_pass,
            full_only=full_only,
            null_only=null_only,
            both_fail=both_fail,
        ),
    )
