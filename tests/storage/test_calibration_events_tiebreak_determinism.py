"""Determinism regression for calibration_events ORDER BY tie-break.

calibration_events is an APPEND-ONLY immutable-history table. The audit query
list_calibration_events_for_judge_axis orders by `validated_at DESC` with NO
secondary sort key. When two events share the same validated_at timestamp, the
tie is broken by SQLite's hidden rowid (insertion order), which is not a stable
audit property: a restored DB or a different physical row ordering can return
same-timestamp events in a different order, breaking audit reproducibility.

The fix adds a deterministic secondary key: `validated_at DESC, calibration_event_id DESC`.

RED-TEST DESIGN NOTE (sqlite-tie-break-red-test-trap):
Rows are inserted in DESCENDING calibration_event_id order so that
insertion-rowid-order == calibration_event_id ASCENDING. At HEAD (no secondary
key) SQLite's reverse-index scan over `validated_at DESC` returns tied rows in
rowid order == id ASCENDING, i.e. the OPPOSITE of the asserted id-DESC order.
That makes the RED fire (actual = smallest id, expected = largest id). Inserting
in ascending order would collude with the scan direction and produce a placebo
that passes at HEAD.
"""

from __future__ import annotations

import sqlite3

from skill_harness.storage.repositories.evidence import (
    calibration_events as calib_repo,
)
from skill_harness.storage.repositories.evidence import (
    judges as judges_repo,
)
from skill_harness.storage.models import CalibrationEventWrite, JudgeWrite

_TS = "2026-06-04T12:00:00.000Z"
_SHA = "a" * 64

# Same validated_at for all three events -> forces the tie-break to decide order.
_SAME_VALIDATED_AT = "2026-06-04T12:00:00.000Z"

# UUIDv7-shaped ascending ids: ...000 < ...001 < ...002 (lexicographic == numeric here).
_IDS = [
    "0190d0a0-0000-7000-8000-000000000000",
    "0190d0a0-0000-7000-8000-000000000001",
    "0190d0a0-0000-7000-8000-000000000002",
]


def _make_judge(judge_id: str = "judge-tb") -> JudgeWrite:
    return JudgeWrite(
        judge_id=judge_id,
        model_id="claude-sonnet-4-6",
        system_prompt_sha256=_SHA,
        created_at=_TS,
    )


def _make_event(event_id: str, judge_id: str, axis: str) -> CalibrationEventWrite:
    return CalibrationEventWrite(
        calibration_event_id=event_id,
        judge_id=judge_id,
        axis=axis,
        pairwise_agreement=0.85,
        position_consistency=0.90,
        length_controlled_agreement=0.80,
        cohen_kappa=0.70,
        pair_set_size=50,
        pair_set_sha256=_SHA,
        state="calibrated",
        expires_at=None,
        validated_at=_SAME_VALIDATED_AT,
        n_a=40,
        n_b=7,
        n_tie=3,
        judge_n_a=41,
        judge_n_b=6,
        judge_n_tie=3,
        length_regression_coefficient=None,
        chance_baseline=0.35,
        total_usd_spent=0.0,
        cost_ledger_run_id=None,
    )


def test_list_for_judge_axis_tiebreaks_on_id_desc_for_same_validated_at(
    evidence_db: sqlite3.Connection,
) -> None:
    """Same-validated_at events must be returned in a deterministic order
    (calibration_event_id DESC), independent of physical insertion order."""
    judge_id = "judge-tb"
    axis = "citation_support"
    judges_repo.insert_judge(evidence_db, _make_judge(judge_id))

    # Insert in DESCENDING id order (see RED-TEST DESIGN NOTE): insertion-rowid
    # order therefore == id ASCENDING. This is the crux that makes the RED fire.
    for event_id in reversed(_IDS):
        calib_repo.insert_calibration_event(
            evidence_db, _make_event(event_id, judge_id, axis)
        )

    rows = calib_repo.list_calibration_events_for_judge_axis(
        evidence_db, judge_id, axis
    )

    assert len(rows) == 3
    # With a deterministic `, calibration_event_id DESC` tie-break, the largest id
    # comes first. At HEAD (no secondary key) the reverse-rowid scan returns the
    # smallest id first -> this assertion fails (RED).
    assert [r["calibration_event_id"] for r in rows] == list(reversed(_IDS)), (
        "same-validated_at events must be ordered by calibration_event_id DESC "
        "(deterministic audit order); got insertion-rowid order instead"
    )
    assert rows[0]["calibration_event_id"] == _IDS[2], (
        "id DESC tie-break — highest calibration_event_id first"
    )
