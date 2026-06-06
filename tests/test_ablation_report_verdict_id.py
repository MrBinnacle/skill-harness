"""Tests that the ablation report renders a verdict_id column (Track E.3, A56).

The existing ablation report at _render_ablation_report does not surface verdict_id,
making `freeze <verdict_id>` unusable without separate DB queries. This test
verifies the column appears after the E.3 fix.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_harness.ablation.stopping import StoppingReason
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
