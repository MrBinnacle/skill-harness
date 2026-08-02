"""Tests that the ablation report renders a verdict_id column (Track E.3, A56).

CF-E3-1 (Phase 3 carry-forward, now complete): verdict_id is threaded through
ClauseResult (ablation/runner.py). Real ablation runs render the UUID in the
verdict_id column, making `freeze <verdict_id>` discoverable from the report.

Mock-based tests (TestAblationReportVerdictIdColumn) verify rendering shape.
Real-ClauseResult tests (TestRealClauseResultRendersVerdictId) verify that the
field is populated and rendered for sampled clauses, and None/'—' for verdictless
paths (BLOCKER-1 tier2_uncalibrated, QUAL-1 length_confounded).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from skill_harness.ablation.runner import ClauseResult
from skill_harness.ablation.stopping import StopDecision, StoppingReason
from skill_harness.cli.main import cli
from tests.ratification_fixture import ratified_exec_args

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
                *ratified_exec_args("skill-test"),
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
                *ratified_exec_args("skill-test"),
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
                *ratified_exec_args("skill-test"),
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
                *ratified_exec_args("skill-test"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert verdict_id_1 in result.output, (
            f"verdict_id_1 {verdict_id_1!r} must appear:\n{result.output}"
        )
        assert verdict_id_2 in result.output, (
            f"verdict_id_2 {verdict_id_2!r} must appear:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# CF-E3-1: real ClauseResult WITH verdict_id renders the UUID (not "—")
# ---------------------------------------------------------------------------


class TestRealClauseResultRendersVerdictId:
    def test_real_clause_result_renders_verdict_id_uuid(self) -> None:
        """CF-E3-1: a real ClauseResult with verdict_id renders the UUID in the report.

        After CF-E3-1 threads verdict_id through ClauseResult, real ablation runs
        should render the UUID (not "—") in the verdict_id column, making
        `freeze <verdict_id>` discoverable from the ablation report output.
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
        expected_verdict_id = "cf-e3-1-real-uuid-12345678"
        real_result = ClauseResult(
            clause_id="real-clause-cf-e3-1",
            stopping_reason=StoppingReason.PASSED,
            stop_decision=real_stop_decision,
            samples_collected=11,
            length_confounded=False,
            verdict_id=expected_verdict_id,
        )
        assert hasattr(real_result, "verdict_id"), (
            "ClauseResult must have a verdict_id field after CF-E3-1 is implemented."
        )
        assert real_result.verdict_id == expected_verdict_id

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[real_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                *ratified_exec_args("skill-test"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        assert expected_verdict_id in result.output, (
            f"verdict_id {expected_verdict_id!r} must appear in ablation report.\n"
            f"Output:\n{result.output}"
        )

    def test_real_clause_result_verdictless_renders_dash(self) -> None:
        """CF-E3-1: a real ClauseResult with verdict_id=None renders '—'.

        Genuinely verdictless clauses (UNMEASURED before sampling: tier2_uncalibrated,
        length_confounded) set verdict_id=None. The renderer must still show '—'.
        """
        real_stop_decision = StopDecision(
            should_stop=True,
            stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
            posterior_alpha=1.0,
            posterior_beta=1.0,
            p_win_rate_exceeds_threshold=0.0,
            n_samples=0,
            w_accumulator=0.0,
        )
        real_result = ClauseResult(
            clause_id="real-clause-unmeasured",
            stopping_reason=StoppingReason.UNDERPOWERED_NMAX,
            stop_decision=real_stop_decision,
            samples_collected=0,
            length_confounded=False,
            unmeasured_reason="tier2_uncalibrated",
            verdict_id=None,
        )
        assert real_result.verdict_id is None

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[real_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-test",
                *ratified_exec_args("skill-test"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 2, f"Expected exit 2 (UNMEASURED):\n{result.output}"
        assert "—" in result.output, (
            f"Expected '—' placeholder for None verdict_id.\nOutput:\n{result.output}"
        )
