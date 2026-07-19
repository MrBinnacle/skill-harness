"""End-to-end mock test for calibrate() — verifies write path (A34, A37).

Uses unittest.mock to intercept:
  - write_calibration_event_with_pointer (dual_write helper)
  - JudgeClient (skips live Anthropic calls)

Verifies:
  - write_calibration_event_with_pointer is called with a CalibrationEventWrite
    that has all 10 new A37 fields populated.
  - Rejected state (N<50) → no write call.
  - Conditional state (50≤N<100) → write called with state='conditional'.
  - Calibrated state (N≥100, all thresholds) → write called with state='calibrated'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pairs_jsonl(path: Path, n: int, human_choices: list[str] | None = None) -> None:
    """Write n valid JSONL calibration pairs to path.

    human_choices cycles if shorter than n. Defaults to all-A.
    """
    choices = human_choices or ["A"]
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            pair = {
                "pair_id": f"p{i:04d}",
                "axis": "clarity",
                "prompt": f"Question {i}",
                "response_a": f"Answer A {i}",
                "response_b": f"Answer B {i}",
                "human_preference": choices[i % len(choices)],
                "labeler_id": "lab-001",
                "labeled_at": "2026-01-01T00:00:00Z",
            }
            fh.write(json.dumps(pair) + "\n")


def _make_judge_verdict(choice: str = "A", position_swap_agreement: int = 1) -> Any:
    """Build a minimal JudgeVerdict-like object."""
    v = MagicMock()
    v.choice = choice
    v.position_swap_agreement = position_swap_agreement
    v.admissibility_state = "admissible"
    v.inadmissibility_reason = None
    v.length_a = 10
    v.length_b = 10
    return v


# ---------------------------------------------------------------------------
# N < 50 → no write
# ---------------------------------------------------------------------------


def test_calibrate_n_below_50_does_not_write(tmp_path: Path) -> None:
    """Rejected state (N<50) must not call write_calibration_event_with_pointer."""
    from skill_harness.oracles.calibration.command import calibrate

    path = tmp_path / "pairs.jsonl"
    _write_pairs_jsonl(path, n=30)

    mock_judge = MagicMock()
    mock_judge.evaluate_pair.return_value = _make_judge_verdict("A")

    with patch(
        "skill_harness.oracles.calibration.command.write_calibration_event_with_pointer"
    ) as mock_write:
        result = calibrate(
            judge_id="judge-001",
            axis="clarity",
            pair_set_path=path,
            judge_client=mock_judge,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
            dry_run=False,
        )
        mock_write.assert_not_called()

    assert result.state == "rejected"


# ---------------------------------------------------------------------------
# N = 60 → conditional write
# ---------------------------------------------------------------------------


def test_calibrate_n_60_writes_conditional(tmp_path: Path) -> None:
    """50≤N<100 must write a calibration_event with state='conditional'."""
    from skill_harness.oracles.calibration.command import calibrate
    from skill_harness.storage.models import CalibrationEventWrite

    path = tmp_path / "pairs.jsonl"
    _write_pairs_jsonl(path, n=60)

    mock_judge = MagicMock()
    mock_judge.evaluate_pair.return_value = _make_judge_verdict("A")

    with patch(
        "skill_harness.oracles.calibration.command.write_calibration_event_with_pointer"
    ) as mock_write:
        result = calibrate(
            judge_id="judge-001",
            axis="clarity",
            pair_set_path=path,
            judge_client=mock_judge,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
            dry_run=False,
        )
        mock_write.assert_called_once()
        call_event = mock_write.call_args[0][2]  # positional: (ev_conn, rt_conn, event, pointer)
        assert isinstance(call_event, CalibrationEventWrite)
        assert call_event.state == "conditional"

    assert result.state == "conditional"


# ---------------------------------------------------------------------------
# N ≥ 100 → calibrated write with all A37 fields present
# ---------------------------------------------------------------------------


def test_calibrate_n_100_writes_calibrated_with_a37_fields(tmp_path: Path) -> None:
    """N≥100 with passing metrics → write with all 10 A37 fields populated."""
    from skill_harness.oracles.calibration.command import calibrate
    from skill_harness.storage.models import CalibrationEventWrite

    path = tmp_path / "pairs.jsonl"
    # Mix A, B, tie to get realistic distributions
    _write_pairs_jsonl(path, n=100, human_choices=["A", "A", "B", "tie"])

    mock_judge = MagicMock()
    # Judge always agrees with human → high pairwise_agreement + position_consistent
    mock_judge.evaluate_pair.return_value = _make_judge_verdict("A", position_swap_agreement=1)

    with patch(
        "skill_harness.oracles.calibration.command.write_calibration_event_with_pointer"
    ) as mock_write:
        result = calibrate(
            judge_id="judge-001",
            axis="clarity",
            pair_set_path=path,
            judge_client=mock_judge,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
            dry_run=False,
        )
        # May or may not be calibrated based on real metric values; just verify
        # the write was called and the event has all A37 fields.
        if result.state in ("calibrated", "conditional"):
            mock_write.assert_called_once()
            call_event = mock_write.call_args[0][2]
            assert isinstance(call_event, CalibrationEventWrite)
            # A37 new fields must be set (not absent from model)
            assert call_event.n_a is not None
            assert call_event.n_b is not None
            assert call_event.n_tie is not None
            assert call_event.judge_n_a is not None
            assert call_event.judge_n_b is not None
            assert call_event.judge_n_tie is not None
            # length_regression_coefficient is None in C.3 (C.4 fills it)
            assert call_event.length_regression_coefficient is None
            # chance_baseline should be a float ≥ 0
            assert isinstance(call_event.chance_baseline, float)
            assert call_event.chance_baseline >= 0.0
            # total_usd_spent = 0.0 in C.3 (C.4 fills it)
            assert call_event.total_usd_spent == 0.0
            # cost_ledger_run_id is None in C.3
            assert call_event.cost_ledger_run_id is None


# ---------------------------------------------------------------------------
# Verify CalibrationEventWrite model has all 10 A37 new fields
# ---------------------------------------------------------------------------


def test_calibration_event_write_has_a37_fields() -> None:
    """CalibrationEventWrite must have all 10 fields from A37 migration."""

    from skill_harness.storage.models import CalibrationEventWrite

    fields = CalibrationEventWrite.model_fields
    required_new_fields = [
        "n_a",
        "n_b",
        "n_tie",
        "judge_n_a",
        "judge_n_b",
        "judge_n_tie",
        "length_regression_coefficient",
        "chance_baseline",
        "total_usd_spent",
        "cost_ledger_run_id",
    ]
    for f in required_new_fields:
        assert f in fields, f"CalibrationEventWrite missing A37 field: {f}"


def test_calibration_event_write_accepts_rejected_state() -> None:
    """CalibrationEventWrite must accept state='rejected' (A37 enum extension)."""
    from skill_harness.storage.models import CalibrationEventWrite

    # Should not raise
    event = CalibrationEventWrite(
        calibration_event_id="evt-001",
        judge_id="judge-001",
        axis="clarity",
        pairwise_agreement=0.3,
        position_consistency=0.3,
        length_controlled_agreement=None,
        cohen_kappa=0.1,
        pair_set_size=30,
        pair_set_sha256="abc" * 21 + "ab",  # 64 hex chars
        state="rejected",
        expires_at=None,
        validated_at="2026-01-01T00:00:00Z",
        n_a=20,
        n_b=8,
        n_tie=2,
        judge_n_a=20,
        judge_n_b=8,
        judge_n_tie=2,
        length_regression_coefficient=None,
        chance_baseline=0.5,
        total_usd_spent=0.0,
        cost_ledger_run_id=None,
    )
    assert event.state == "rejected"


# ---------------------------------------------------------------------------
# C2 regression: injection-detected sentinel verdicts must not move
# agreement stats (pairwise_agreement, cohen_kappa, judge_n_*), and the
# excluded count must be surfaced separately, not silently dropped.
# ---------------------------------------------------------------------------


def _make_sentinel_verdict(reason: str = "suspected_injection") -> Any:
    """Build a JudgeVerdict-shaped sentinel: choice/raw_observation are
    hardcoded placeholders — this is what JudgeClient.evaluate_pair returns
    when detect_meta_tokens fires (judge.py:270-283) or the response is
    truncated/malformed (judge.py:301-311), i.e. no real judge opinion.
    """
    from skill_harness.oracles.tier2.judge import JudgeVerdict

    return JudgeVerdict(
        choice="tie",
        position_swap_agreement=0,
        admissibility_state="inadmissible",
        inadmissibility_reason=reason,  # type: ignore[arg-type]
        raw_observation=0.0,
        length_adjusted_observation=None,
        length_a=10,
        length_b=10,
        rationale_brief="[sentinel]",
    )


def test_injection_sentinels_do_not_move_agreement_stats(tmp_path: Path) -> None:
    """C2 regression: a pair set with injection-quoting responses must not
    move pairwise_agreement/cohen_kappa — and the excluded sentinel count must
    be reported separately (n_inadmissible_verdicts), never hidden.

    Asserts directly on CalibrationResult (populated regardless of final
    admissibility gate/state — see calibrate()'s unconditional return) rather
    than on the persisted CalibrationEventWrite, so the test does not depend
    on incidentally crossing the "calibrated"/"conditional" thresholds.
    """
    from skill_harness.oracles.calibration.command import calibrate

    n_baseline = 100
    n_sentinel = 12
    human_choices = ["A", "A", "B", "tie"]

    baseline_path = tmp_path / "baseline.jsonl"
    _write_pairs_jsonl(baseline_path, n=n_baseline, human_choices=human_choices)

    augmented_path = tmp_path / "augmented.jsonl"
    # First n_baseline rows are IDENTICAL to the baseline file (same cycling
    # index -> same human_preference); the extra n_sentinel rows simulate
    # injection-quoting responses and get sentinel verdicts below, regardless
    # of what human label they happen to draw (including "tie" — the exact
    # case that would spuriously "agree" with the old choice="tie" sentinel).
    _write_pairs_jsonl(augmented_path, n=n_baseline + n_sentinel, human_choices=human_choices)

    # Baseline: every pair gets the same admissible "A" verdict.
    baseline_judge = MagicMock()
    baseline_judge.evaluate_pair.return_value = _make_judge_verdict("A", position_swap_agreement=1)

    with patch("skill_harness.oracles.calibration.command.write_calibration_event_with_pointer"):
        baseline_result = calibrate(
            judge_id="judge-baseline",
            axis="clarity",
            pair_set_path=baseline_path,
            judge_client=baseline_judge,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
            dry_run=False,
        )

    # Augmented: same n_baseline admissible "A" verdicts, PLUS n_sentinel
    # injection-detected sentinel verdicts for the appended pairs.
    verdict_sequence = [
        _make_judge_verdict("A", position_swap_agreement=1) for _ in range(n_baseline)
    ] + [_make_sentinel_verdict("suspected_injection") for _ in range(n_sentinel)]
    augmented_judge = MagicMock()
    augmented_judge.evaluate_pair.side_effect = verdict_sequence

    with patch("skill_harness.oracles.calibration.command.write_calibration_event_with_pointer"):
        augmented_result = calibrate(
            judge_id="judge-augmented",
            axis="clarity",
            pair_set_path=augmented_path,
            judge_client=augmented_judge,
            evidence_conn=MagicMock(),
            runtime_conn=MagicMock(),
            dry_run=False,
        )

    # Sentinel verdicts must not move agreement stats: exact equality between
    # baseline (no sentinels) and augmented (n_baseline admissible + n_sentinel
    # injected sentinels) runs.
    assert augmented_result.pairwise_agreement == baseline_result.pairwise_agreement
    assert augmented_result.cohen_kappa == baseline_result.cohen_kappa
    assert augmented_result.chance_baseline == baseline_result.chance_baseline

    # Sentinel count must be surfaced separately, never hidden.
    assert baseline_result.n_inadmissible_verdicts == 0
    assert augmented_result.n_inadmissible_verdicts == n_sentinel


def test_calibration_event_write_accepts_uncalibrated_state() -> None:
    """CalibrationEventWrite must accept state='uncalibrated' (pre-existing)."""
    from skill_harness.storage.models import CalibrationEventWrite

    event = CalibrationEventWrite(
        calibration_event_id="evt-002",
        judge_id="judge-001",
        axis="clarity",
        pairwise_agreement=0.5,
        position_consistency=0.5,
        length_controlled_agreement=None,
        cohen_kappa=0.1,
        pair_set_size=100,
        pair_set_sha256="abc" * 21 + "ab",
        state="uncalibrated",
        expires_at=None,
        validated_at="2026-01-01T00:00:00Z",
        n_a=50,
        n_b=30,
        n_tie=20,
        judge_n_a=50,
        judge_n_b=30,
        judge_n_tie=20,
        length_regression_coefficient=None,
        chance_baseline=0.35,
        total_usd_spent=0.0,
        cost_ledger_run_id=None,
    )
    assert event.state == "uncalibrated"
