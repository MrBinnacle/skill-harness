"""Tests that the ablation report renders a verdict_id column (Track E.3, A56).

IMPORTANT — scope and limitations of this test module (T7 from ai-slop fix-loop):
These tests assert RENDERING SHAPE, not real-run behavior.

Real ClauseResult (ablation/runner.py) has NO verdict_id field — fields are:
  clause_id, stopping_reason, stop_decision, samples_collected, length_confounded,
  unmeasured_reason.
The existing tests use MagicMock with .verdict_id manually set, which proves only
"if the mock has the attribute, _render includes it." Real ablation runs render
"—" via the getattr(result, 'verdict_id', None) or '—' fallback.

Threading verdict_id through ClauseResult is CF-E3-1 (Phase 3 follow-up, NOT in this
module's scope). See docs/dispatch/track-e-ai-slop-fix-brief.md § T7 for details.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_harness.ablation.runner import ClauseResult
from skill_harness.ablation.stopping import StopDecision, StoppingReason
from skill_harness.cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(*args: str, env: dict[str, str] | None = None) -> Any:
    runner = CliRunner()
    merged_env: dict[str, str] = {"COLUMNS": "220"}
    if env is not None:
        merged_env.update(env)
    return runner.invoke(cli, list(args), env=merged_env)


def _make_result(
    clause_id: str = "clause-001",
    verdict_id: str = "verdict-abc-123",
    stopping_reason: StoppingReason = StoppingReason.PASSED,
    unmeasured_reason: str | None = None,
) -> MagicMock:
    result = MagicMock()
    result.clause_id = clause_id
    result.verdict_id = verdict_id
    result.stopping_reason = stopping_reason
    result.unmeasured_reason = unmeasured_reason
    result.length_confounded = False
    result.samples_collected = 8
    result.stop_decision = MagicMock()
    result.stop_decision.p_win_rate_exceeds_threshold = 0.97
    result.stop_decision.n_samples = 8
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAblationReportVerdictIdColumn:
    def test_verdict_id_appears_in_passed_result(self) -> None:
        """PASSED result row must include the verdict_id in the ablation report output."""
        verdict_id = "verdict-passed-xyz"
        mock_result = _make_result(
            clause_id="clause-passed-001",
            verdict_id=verdict_id,
            stopping_reason=StoppingReason.PASSED,
        )

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                "--execute",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        assert verdict_id in result.output, (
            f"verdict_id {verdict_id!r} must appear in ablation report output.\n"
            f"Output:\n{result.output}"
        )

    def test_verdict_id_appears_in_failed_result(self) -> None:
        """FAILED result row must include the verdict_id in the ablation report output."""
        verdict_id = "verdict-failed-xyz"
        mock_result = _make_result(
            clause_id="clause-failed-001",
            verdict_id=verdict_id,
            stopping_reason=StoppingReason.FAILED,
        )

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                "--execute",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 0 or result.exit_code == 2, (
            f"Unexpected exit code:\n{result.output}"
        )
        assert verdict_id in result.output, (
            f"verdict_id {verdict_id!r} must appear in ablation report output.\n"
            f"Output:\n{result.output}"
        )

    def test_verdict_id_appears_in_unmeasured_result(self) -> None:
        """UNMEASURED result row must include the verdict_id in the ablation report output."""
        verdict_id = "verdict-unmeasured-xyz"
        mock_result = _make_result(
            clause_id="clause-unm-001",
            verdict_id=verdict_id,
            stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
            unmeasured_reason="underpowered",
        )

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                "--execute",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 2, f"UNMEASURED must exit 2:\n{result.output}"
        assert verdict_id in result.output, (
            f"verdict_id {verdict_id!r} must appear in ablation report output.\n"
            f"Output:\n{result.output}"
        )

    def test_multiple_results_all_verdict_ids_present(self) -> None:
        """When multiple clause results, all their verdict_ids must appear."""
        verdict_id_1 = "verdict-multi-001"
        verdict_id_2 = "verdict-multi-002"

        mock_r1 = _make_result(
            clause_id="clause-001",
            verdict_id=verdict_id_1,
            stopping_reason=StoppingReason.PASSED,
        )
        mock_r2 = _make_result(
            clause_id="clause-002",
            verdict_id=verdict_id_2,
            stopping_reason=StoppingReason.FAILED,
        )

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_r1, mock_r2],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                "--execute",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert verdict_id_1 in result.output, (
            f"verdict_id_1 {verdict_id_1!r} must appear:\n{result.output}"
        )
        assert verdict_id_2 in result.output, (
            f"verdict_id_2 {verdict_id_2!r} must appear:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# T7: real ClauseResult (no verdict_id field) renders "—" for verdict_id column
# ---------------------------------------------------------------------------


class TestRealClauseResultRendersPlaceholder:
    def test_real_clause_result_renders_dash_for_verdict_id(self) -> None:
        """T7: a REAL ClauseResult (not MagicMock) has no verdict_id attribute.

        The ablation report renderer uses getattr(result, 'verdict_id', None) or '—'
        as a fallback. This test proves real ablation runs render '—' for the
        verdict_id column — the existing mock-based tests only prove the mock works.

        Threading verdict_id through ClauseResult is CF-E3-1 (Phase 3 follow-up).
        """
        real_stop_decision = StopDecision(
            should_stop=True,
            stopping_reason=StoppingReason.PASSED,
            posterior_alpha=10.0,
            posterior_beta=2.0,
            p_win_rate_exceeds_threshold=0.97,
            n_samples=11,
            w_accumulator=9.0,
        )
        real_result = ClauseResult(
            clause_id="real-clause-001",
            stopping_reason=StoppingReason.PASSED,
            stop_decision=real_stop_decision,
            samples_collected=11,
            length_confounded=False,
        )
        # Confirm no verdict_id on a real ClauseResult
        assert not hasattr(real_result, "verdict_id"), (
            "ClauseResult gained a verdict_id field — CF-E3-1 was implemented. "
            "Update this test to verify the real UUID is rendered instead."
        )

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[real_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                "--execute",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        # Real ClauseResult has no verdict_id → fallback "—" must appear
        assert "—" in result.output, (
            f"Expected '—' placeholder for verdict_id in ablation report for real ClauseResult.\n"
            f"Output:\n{result.output}"
        )
