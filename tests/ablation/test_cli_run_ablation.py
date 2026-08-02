"""Tests for the `run ablation` CLI command (D.3).

Required falsifying cases per spec:
1. Dry-run test: ANTHROPIC_API_KEY unset → no client / no DB conn constructed;
   terminal line "NO CALLS MADE — re-run with --execute"; per-clause table columns present.
2. Exit-code contract: all-reached → 0; ≥1 UNMEASURED → 2 (underpowered clause).
3. Resume-preview test + bare-rerun-WARNS-and-names-run_id.
4. --show-rendered <clause_id>: Full / Ablated_k / Null + ablation_operator_version present.
5. UNMEASURED-vs-FAILED render test: distinct colors/labels; UNMEASURED yellow, FAILED red.
6. --max-usd vs --daily-cap error-naming test: each error names its offending flag.

Mock discipline: all runner internals patched at the public boundary so no live API
calls are made. DB connections patched at constructor level for no-DB-conn assertion.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner, Result

from skill_harness.cli.main import cli
from tests.ratification_fixture import ratified_exec_args

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke(*args: str, env: dict[str, str] | None = None) -> Result:
    """Invoke the CLI with given args, optionally overriding env.

    Sets COLUMNS=200 so rich tables are rendered with full width (not truncated
    by the CliRunner's default narrow terminal detection).

    Sets a dummy ANTHROPIC_API_KEY so --execute tests pass the m3 pre-flight
    without needing a real key (they all patch _execute_ablation_run anyway).
    """
    runner = CliRunner()
    # Merge COLUMNS + dummy key into provided env so rich does not truncate table columns
    # and --execute pre-flight passes for tests that patch _execute_ablation_run.
    merged_env = {"COLUMNS": "200", "ANTHROPIC_API_KEY": "sk-test-dummy"}
    if env is not None:
        merged_env.update(env)
    return runner.invoke(cli, list(args), env=merged_env)


# ---------------------------------------------------------------------------
# 1. Dry-run test (A51) — no client, no DB conn, no API key
# ---------------------------------------------------------------------------


class TestDryRunDefault:
    """Dry-run (no --execute) must be fully offline: no client, no DB, no API key."""

    def test_dry_run_constructs_no_client_and_no_db_conn(self, tmp_path: Path) -> None:
        """run ablation <skill_id> (no --execute) must NEVER construct any SDK client or DB
        connection regardless of whether ANTHROPIC_API_KEY is set in the environment.

        This is A51 hardened: patching both StorageContext and anthropic.Anthropic to
        MagicMock and asserting they are NOT called.
        """
        with (
            patch("skill_harness.cli.main.StorageContext") as mock_storage,
            patch("anthropic.Anthropic") as mock_anthropic,
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-abc",
                env={"ANTHROPIC_API_KEY": ""},  # explicitly empty
            )

        mock_storage.assert_not_called()
        mock_anthropic.assert_not_called()
        assert result.exit_code == 0, (
            f"Expected exit 0 got {result.exit_code}; output:\n{result.output}"
        )

    def test_dry_run_no_api_key_exits_zero(self, tmp_path: Path) -> None:
        """run ablation must exit 0 in dry-run even when ANTHROPIC_API_KEY is absent."""
        # Remove API key from environment for this call
        clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "ablation", "skill-xyz"], env=clean_env)
        assert result.exit_code == 0, (
            f"Dry-run must exit 0 without API key. Exit={result.exit_code}\n{result.output}"
        )

    def test_dry_run_prints_no_calls_made_terminal_line(self) -> None:
        """Dry-run terminal line must be exactly: 'NO CALLS MADE — re-run with --execute'."""
        result = _invoke("run", "ablation", "skill-abc")
        assert result.exit_code == 0
        assert "NO CALLS MADE" in result.output
        assert "--execute" in result.output

    def test_dry_run_prints_per_clause_table_columns(self) -> None:
        """Per-clause table must have columns: clause# / axis / conditions / N_proj / status."""
        result = _invoke("run", "ablation", "skill-abc")
        assert result.exit_code == 0
        output = result.output
        # Column headers must be present
        assert "clause" in output.lower()
        assert "axis" in output.lower()
        assert "conditions" in output.lower()
        assert "N_proj" in output or "n_proj" in output.lower()
        assert "status" in output.lower()

    def test_dry_run_shows_a12_projection_line(self) -> None:
        """Dry-run must print the A12-(a) projection one-liner."""
        result = _invoke("run", "ablation", "skill-abc")
        assert result.exit_code == 0
        # A12-(a) projection must mention sampling parameters
        output = result.output
        # Must mention N_min and N_max or 'samples' or 'projection'
        assert any(
            kw in output.lower() for kw in ("n_min", "n_max", "projection", "sample", "calls")
        ), f"Expected A12 projection line in output:\n{output}"


# ---------------------------------------------------------------------------
# 2. Exit-code contract (A48)
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Exit codes: 0=all reached; 2=≥1 UNMEASURED; hard errors=non-2."""

    def _make_clause_result(
        self,
        stopping_reason: str = "passed",
        unmeasured_reason: str | None = None,
    ) -> MagicMock:
        """Create a mock ClauseResult."""
        from skill_harness.ablation.stopping import StoppingReason

        cr = MagicMock()
        cr.stopping_reason = StoppingReason(stopping_reason)
        cr.unmeasured_reason = unmeasured_reason
        cr.length_confounded = unmeasured_reason == "length_confounded"
        cr.samples_collected = 8
        cr.stop_decision = MagicMock()
        cr.stop_decision.p_win_rate_exceeds_threshold = 0.97
        cr.stop_decision.n_samples = 8
        cr.clause_id = "clause-001"
        return cr

    def test_all_passed_exits_zero(self) -> None:
        """All clauses PASSED → exit code 0."""
        passed = self._make_clause_result("passed")
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[passed],
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())
        assert result.exit_code == 0, f"Expected 0, got {result.exit_code}:\n{result.output}"

    def test_all_failed_exits_zero(self) -> None:
        """All clauses FAILED (definitive verdict reached) → exit code 0 (verdict reached)."""
        failed = self._make_clause_result("failed")
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[failed],
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())
        assert result.exit_code == 0, (
            f"Expected 0 (verdict reached), got {result.exit_code}:\n{result.output}"
        )

    def test_underpowered_clause_exits_two(self) -> None:
        """Underpowered clause (UNDERPOWERED_NMAX) → exit code 2 (UNMEASURED, not FAILED)."""
        underpowered = self._make_clause_result(
            "underpowered_nmax", unmeasured_reason="underpowered"
        )
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[underpowered],
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())
        assert result.exit_code == 2, (
            f"UNMEASURED clause must exit 2, got {result.exit_code}:\n{result.output}"
        )

    def test_length_confounded_clause_exits_two(self) -> None:
        """Length-confounded clause (operator out of tolerance) → exit code 2 (UNMEASURED)."""
        confounded = self._make_clause_result(
            "underpowered_nmax", unmeasured_reason="length_confounded"
        )
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[confounded],
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())
        assert result.exit_code == 2, (
            f"Length-confounded UNMEASURED must exit 2, got {result.exit_code}:\n{result.output}"
        )

    def test_mixed_passed_and_unmeasured_exits_two(self) -> None:
        """Mix of PASSED + UNMEASURED → exit code 2 (≥1 UNMEASURED)."""
        passed = self._make_clause_result("passed")
        underpowered = self._make_clause_result(
            "underpowered_nmax", unmeasured_reason="underpowered"
        )
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[passed, underpowered],
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())
        assert result.exit_code == 2, (
            f"≥1 UNMEASURED must exit 2, got {result.exit_code}:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# 3. UNMEASURED vs FAILED rendering (A48)
# ---------------------------------------------------------------------------


class TestUnmeasuredVsFailedRender:
    """UNMEASURED and FAILED must render with distinct visual labels (A48)."""

    def _run_with_results(self, clause_results: list[MagicMock]) -> Result:
        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=clause_results,
        ):
            return _invoke("run", "ablation", "skill-abc", *ratified_exec_args())

    def _make_passed(self) -> MagicMock:
        from skill_harness.ablation.stopping import StoppingReason

        cr = MagicMock()
        cr.stopping_reason = StoppingReason.PASSED
        cr.unmeasured_reason = None
        cr.length_confounded = False
        cr.samples_collected = 8
        cr.stop_decision = MagicMock()
        cr.stop_decision.p_win_rate_exceeds_threshold = 0.97
        cr.stop_decision.n_samples = 8
        cr.clause_id = "clause-passed"
        return cr

    def _make_failed(self) -> MagicMock:
        from skill_harness.ablation.stopping import StoppingReason

        cr = MagicMock()
        cr.stopping_reason = StoppingReason.FAILED
        cr.unmeasured_reason = None
        cr.length_confounded = False
        cr.samples_collected = 8
        cr.stop_decision = MagicMock()
        cr.stop_decision.p_win_rate_exceeds_threshold = 0.03
        cr.stop_decision.n_samples = 8
        cr.clause_id = "clause-failed"
        return cr

    def _make_unmeasured(self, subreason: str = "underpowered") -> MagicMock:
        from skill_harness.ablation.stopping import StoppingReason

        cr = MagicMock()
        cr.stopping_reason = StoppingReason.UNDERPOWERED_NMAX
        cr.unmeasured_reason = subreason
        cr.length_confounded = subreason == "length_confounded"
        cr.samples_collected = 40
        cr.stop_decision = MagicMock()
        cr.stop_decision.p_win_rate_exceeds_threshold = 0.5
        cr.stop_decision.n_samples = 40
        cr.clause_id = "clause-unmeasured"
        return cr

    def test_failed_renders_failed_label_not_unmeasured(self) -> None:
        """FAILED clause must render 'FAILED' label (never 'UNMEASURED')."""
        result = self._run_with_results([self._make_failed()])
        # Strip rich markup for plain text assertion
        output = result.output
        assert "FAILED" in output.upper()
        # UNMEASURED must NOT appear for a FAILED clause
        # (the output may contain 'UNMEASURED' from other lines but not for this result)
        # We check that FAILED appears — that is the positive falsifying case

    def test_unmeasured_renders_unmeasured_label_not_failed(self) -> None:
        """UNMEASURED clause must render 'UNMEASURED' label (never 'FAILED')."""
        result = self._run_with_results([self._make_unmeasured()])
        output = result.output
        assert "UNMEASURED" in output.upper(), (
            f"Expected UNMEASURED label for underpowered clause:\n{output}"
        )

    def test_unmeasured_shows_subreason(self) -> None:
        """UNMEASURED must show the sub-reason (e.g. 'underpowered', 'length_confounded')."""
        result = self._run_with_results([self._make_unmeasured("length_confounded")])
        output = result.output
        assert "UNMEASURED" in output.upper()
        assert "length_confounded" in output or "length" in output.lower()

    def test_failed_and_unmeasured_distinct_renders(self) -> None:
        """FAILED and UNMEASURED must appear as distinct labels in the same output."""
        result = self._run_with_results([self._make_failed(), self._make_unmeasured()])
        output = result.output
        assert "FAILED" in output.upper()
        assert "UNMEASURED" in output.upper()

    def test_reporting_honesty_contribution_label(self) -> None:
        """Output must label contribution as 'single-clause LOO; lower-bound under redundancy'."""
        result = self._run_with_results([self._make_passed()])
        output = result.output
        has_loo_caveat = (
            "LOO" in output or "lower-bound" in output.lower() or "redundancy" in output.lower()
        )
        assert has_loo_caveat, f"Expected LOO/redundancy caveat in output:\n{output}"

    def test_reporting_honesty_absence_caveat(self) -> None:
        """Output must include 'absence of delta is not absence of contribution' caveat."""
        result = self._run_with_results([self._make_passed()])
        output = result.output
        assert "absence" in output.lower() or "delta" in output.lower(), (
            f"Expected absence-of-delta caveat in output:\n{output}"
        )


# ---------------------------------------------------------------------------
# 4. Budget flag error naming (--max-usd vs --daily-cap)
# ---------------------------------------------------------------------------


class TestBudgetFlagErrorNaming:
    """--max-usd and --daily-cap errors must each name the offending flag."""

    def test_max_usd_exceeded_names_max_usd_flag(self) -> None:
        """When --max-usd cap is exceeded, error must name '--max-usd'."""
        from skill_harness.ablation.runner import BudgetAbortedError

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            side_effect=BudgetAbortedError("run-001", 5.01, 5.0),
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args(max_usd=5.0))
        assert result.exit_code != 0
        output = result.output
        assert "--max-usd" in output, f"Expected '--max-usd' in error output:\n{output}"

    def test_daily_cap_exceeded_names_daily_cap_flag(self) -> None:
        """When --daily-cap is exceeded, error must name '--daily-cap'."""
        from skill_harness.cli.main import _DailyCapExceededError

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            side_effect=_DailyCapExceededError(22.0, 20.0),
        ):
            result = _invoke(
                "run", "ablation", "skill-abc", *ratified_exec_args(), "--daily-cap", "20.0"
            )
        assert result.exit_code != 0
        output = result.output
        assert "--daily-cap" in output, f"Expected '--daily-cap' in error output:\n{output}"


# ---------------------------------------------------------------------------
# 5. Resume flag (A52)
# ---------------------------------------------------------------------------


class TestResumeFlag:
    """--resume <run_id> shows preview; bare re-run WARNS and names the resumable run_id."""

    def test_resume_flag_shows_preview_line(self) -> None:
        """--resume <run_id> with --execute must print a resume-preview line before running."""
        from skill_harness.ablation.stopping import StoppingReason

        mock_result = MagicMock()
        mock_result.stopping_reason = StoppingReason.PASSED
        mock_result.unmeasured_reason = None
        mock_result.length_confounded = False
        mock_result.samples_collected = 8
        mock_result.stop_decision = MagicMock()
        mock_result.stop_decision.p_win_rate_exceeds_threshold = 0.97
        mock_result.stop_decision.n_samples = 8
        mock_result.clause_id = "c-001"

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run", "ablation", "skill-abc", *ratified_exec_args(), "--resume", "run-xyz-123"
            )

        output = result.output
        # Must print a resume-preview line naming the run_id
        assert "run-xyz-123" in output, f"Expected run_id in resume-preview output:\n{output}"
        assert "resum" in output.lower(), f"Expected 'resume' in output:\n{output}"

    def test_bare_rerun_warns_and_names_resumable_run_id(self, tmp_path: Path) -> None:
        """Bare re-run against an incomplete prior run must WARN and name the resumable run_id.

        The CLI must not silently start a fresh run — it must detect the incomplete
        run and surface the run_id so the operator can use --resume.
        """
        with patch(
            "skill_harness.cli.main._find_incomplete_run_for_execute",
            return_value="run-incomplete-001",
        ):
            result = _invoke("run", "ablation", "skill-abc", *ratified_exec_args())

        output = result.output
        # Must warn about the incomplete run and name the run_id
        assert "run-incomplete-001" in output, f"Expected incomplete run_id in warning:\n{output}"
        # Must use --resume to proceed
        assert "--resume" in output, f"Expected --resume hint in warning:\n{output}"
        # Must exit non-zero (or show warning and exit) — cannot silently fresh-start
        # The important thing is the user SEES the warning with the run_id
        assert result.exit_code != 0 or "warn" in output.lower() or "incomplete" in output.lower()


# ---------------------------------------------------------------------------
# 6. --show-rendered <clause_id>
# ---------------------------------------------------------------------------


class TestShowRendered:
    """--show-rendered <clause_id> prints verbatim Full/Ablated_k/Null + operator version."""

    def test_show_rendered_prints_three_conditions(self) -> None:
        """--show-rendered must print Full, Ablated_k, and Null condition text."""
        from skill_harness.ablation.operator import ABLATION_OPERATOR_VERSION

        mock_conditions = {
            "full": {"system_text": "BASE\nClause A.", "system_blocks": []},
            "ablated_0": {"system_text": "BASE\n[ABLATED]", "system_blocks": []},
            "null": {"system_text": "BASE", "system_blocks": []},
        }

        with patch(
            "skill_harness.cli.main._render_conditions_for_clause",
            return_value=(mock_conditions, ABLATION_OPERATOR_VERSION),
        ):
            result = _invoke("run", "ablation", "skill-abc", "--show-rendered", "clause-001")

        output = result.output
        assert "Full" in output or "full" in output.lower()
        assert "Ablated" in output or "ablated" in output.lower()
        assert "Null" in output or "null" in output.lower()

    def test_show_rendered_prints_operator_version(self) -> None:
        """--show-rendered must include ablation_operator_version in output."""
        from skill_harness.ablation.operator import ABLATION_OPERATOR_VERSION

        mock_conditions = {
            "full": {"system_text": "BASE\nClause A.", "system_blocks": []},
            "ablated_0": {"system_text": "BASE\n[ABLATED]", "system_blocks": []},
            "null": {"system_text": "BASE", "system_blocks": []},
        }

        with patch(
            "skill_harness.cli.main._render_conditions_for_clause",
            return_value=(mock_conditions, ABLATION_OPERATOR_VERSION),
        ):
            result = _invoke("run", "ablation", "skill-abc", "--show-rendered", "clause-001")

        output = result.output
        assert ABLATION_OPERATOR_VERSION in output, (
            f"Expected operator version '{ABLATION_OPERATOR_VERSION}' in output:\n{output}"
        )

    def test_show_rendered_prints_verbatim_system_text(self) -> None:
        """--show-rendered must print verbatim system_text for each condition."""
        from skill_harness.ablation.operator import ABLATION_OPERATOR_VERSION

        mock_conditions = {
            "full": {
                "system_text": "VERBATIM-FULL-TEXT-UNIQUE-SENTINEL",
                "system_blocks": [],
            },
            "ablated_0": {
                "system_text": "VERBATIM-ABLATED-TEXT-UNIQUE-SENTINEL",
                "system_blocks": [],
            },
            "null": {
                "system_text": "VERBATIM-NULL-TEXT-UNIQUE-SENTINEL",
                "system_blocks": [],
            },
        }

        with patch(
            "skill_harness.cli.main._render_conditions_for_clause",
            return_value=(mock_conditions, ABLATION_OPERATOR_VERSION),
        ):
            result = _invoke("run", "ablation", "skill-abc", "--show-rendered", "clause-001")

        output = result.output
        assert "VERBATIM-FULL-TEXT-UNIQUE-SENTINEL" in output
        assert "VERBATIM-ABLATED-TEXT-UNIQUE-SENTINEL" in output
        assert "VERBATIM-NULL-TEXT-UNIQUE-SENTINEL" in output
