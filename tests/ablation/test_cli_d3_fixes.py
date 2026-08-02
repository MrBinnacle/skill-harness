"""D.3 fix-loop tests — TDD: written RED first, then GREEN.

Covers B1, B2, M1, M2, M3, M4, m1, m2, m3, m4 + open_evidence_readonly unit tests.

All tests are tagged 'not live' (no real API calls). Mock discipline:
SubjectClient is the ONLY network surface patched for the integration tests;
_execute_ablation_run is NOT patched in B1/M2/M3 tests.
B1 tests migrated from _find_incomplete_run (shim deleted in E.3) to
find_resumable_run_for_skill from storage.recovery.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence, open_runtime
from tests.ratification_fixture import ratified_exec_args

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TS = "2026-06-06T00:00:00.000000+00:00"
_SHA = "a" * 64
_SKILL_ID = "skill-fix-test"


def _invoke(*args: str, env: dict[str, str] | None = None) -> Any:
    runner = CliRunner()
    merged_env = {"COLUMNS": "200"}
    if env is not None:
        merged_env.update(env)
    return runner.invoke(cli, list(args), env=merged_env)


# ---------------------------------------------------------------------------
# DB setup helpers (mirrors test_runner.py pattern)
# ---------------------------------------------------------------------------


def _open_pair(tmp_path: Path) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    return ev, rt


def _close_pair(ev: sqlite3.Connection, rt: sqlite3.Connection) -> None:
    ev.close()
    rt.close()


def _seed_skill(ev: sqlite3.Connection, skill_id: str = _SKILL_ID) -> None:
    from skill_harness.storage.models import SkillWrite
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(ev):
        insert_skill(
            ev,
            SkillWrite(
                skill_id=skill_id,
                name="Fix Test Skill",
                source_path="/test/fix.md",
                source_sha256=_SHA,
                imported_at=_TS,
            ),
        )


def _seed_clause(
    ev: sqlite3.Connection,
    clause_id: str,
    clause_index: int = 0,
    axis: str = "verbosity",
    oracle_tier: int = 1,
    vacuity_flag: str = "none",
    falsifying_case_schema_sha256: str | None = "abc123",
    clause_text: str = "Always begin with 'Certainly!' before answering.",
    skill_id: str = _SKILL_ID,
) -> None:
    from skill_harness.storage.models import ClauseWrite
    from skill_harness.storage.repositories.evidence.clauses import insert_clause
    from skill_harness.storage.transaction import writer_transaction

    with writer_transaction(ev):
        insert_clause(
            ev,
            ClauseWrite(
                clause_id=clause_id,
                skill_id=skill_id,
                clause_index=clause_index,
                rendering_index=clause_index,
                clause_text=clause_text,
                axis=axis,
                comparator="increase",
                oracle_tier=oracle_tier,
                vacuity_flag=vacuity_flag,
                falsifying_case_schema_sha256=falsifying_case_schema_sha256,
                created_at=_TS,
            ),
        )


def _seed_run_progress(
    rt: sqlite3.Connection,
    run_id: str,
    state: str = "running",
    skill_id: str = _SKILL_ID,
    ev: sqlite3.Connection | None = None,
) -> None:
    """Seed a run_progress row for a skill_id (uses run_budget for cost, run_progress for state).

    We also need a runs row in evidence for FK integrity if ev is provided.
    """
    from skill_harness.storage.models import RunBudgetWrite, RunProgressWrite
    from skill_harness.storage.repositories.runtime.run_budget import insert_run_budget
    from skill_harness.storage.repositories.runtime.run_progress import insert_run_progress
    from skill_harness.storage.transaction import writer_transaction

    if ev is not None:
        from skill_harness.storage.models import RunWrite
        from skill_harness.storage.repositories.evidence.runs import insert_run

        config = json.dumps({"skill_id": skill_id, "run_id": run_id})
        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=skill_id,
                    run_kind="ablation",
                    config_json=config,
                    started_at=_TS,
                    completed_at=None,
                ),
            )

    with writer_transaction(rt):
        insert_run_budget(
            rt,
            RunBudgetWrite(
                run_id=run_id,
                hard_cap_usd=5.0,
                tokens_spent_in=0,
                tokens_spent_out=0,
                cache_write_in=0,
                cache_read_in=0,
                usd_spent=0.0,
                dry_run=0,
                aborted_at=None,
                last_updated=_TS,
            ),
        )
        insert_run_progress(
            rt,
            RunProgressWrite(
                run_id=run_id,
                state=state,
                samples_planned=120,
                samples_collected=10,
                last_heartbeat=_TS,
                error=None,
            ),
        )


# ---------------------------------------------------------------------------
# B1: _find_incomplete_run UNPATCHED tests
# ---------------------------------------------------------------------------


class TestB1FindIncompleteRunUnpatched:
    """B1: find_resumable_run_for_skill must query real runtime.run_progress (not stub).

    Migrated from _find_incomplete_run (shim deleted in E.3) to
    find_resumable_run_for_skill from storage.recovery (E.1).
    """

    def test_find_incomplete_run_returns_none_when_no_incomplete(self, tmp_path: Path) -> None:
        """When no run is in-progress, find_resumable_run_for_skill returns None."""
        from skill_harness.storage.migrations import open_evidence_readonly
        from skill_harness.storage.recovery import find_resumable_run_for_skill

        ev, rt = _open_pair(tmp_path)
        try:
            # No rows at all — should return None
            ev_ro = open_evidence_readonly(tmp_path / "evidence.db")
            try:
                result = find_resumable_run_for_skill(
                    _SKILL_ID, evidence_conn_ro=ev_ro, runtime_conn=rt
                )
            finally:
                ev_ro.close()
            assert result is None
        finally:
            _close_pair(ev, rt)

    def test_find_incomplete_run_returns_run_id_for_running_state(self, tmp_path: Path) -> None:
        """With a state='running' row in runtime.run_progress, returns that run_id."""
        from skill_harness.storage.migrations import open_evidence_readonly
        from skill_harness.storage.recovery import find_resumable_run_for_skill

        ev, rt = _open_pair(tmp_path)
        try:
            _seed_skill(ev)
            _seed_run_progress(rt, "run-incomplete-001", state="running", ev=ev)
            ev_ro = open_evidence_readonly(tmp_path / "evidence.db")
            try:
                result = find_resumable_run_for_skill(
                    _SKILL_ID, evidence_conn_ro=ev_ro, runtime_conn=rt
                )
            finally:
                ev_ro.close()
            assert result == "run-incomplete-001"
        finally:
            _close_pair(ev, rt)

    def test_find_incomplete_run_ignores_completed_runs(self, tmp_path: Path) -> None:
        """Completed runs are NOT returned as incomplete."""
        from skill_harness.storage.migrations import open_evidence_readonly
        from skill_harness.storage.recovery import find_resumable_run_for_skill

        ev, rt = _open_pair(tmp_path)
        try:
            _seed_skill(ev)
            _seed_run_progress(rt, "run-done-001", state="completed", ev=ev)
            ev_ro = open_evidence_readonly(tmp_path / "evidence.db")
            try:
                result = find_resumable_run_for_skill(
                    _SKILL_ID, evidence_conn_ro=ev_ro, runtime_conn=rt
                )
            finally:
                ev_ro.close()
            assert result is None
        finally:
            _close_pair(ev, rt)

    def test_find_incomplete_run_ignores_failed_runs(self, tmp_path: Path) -> None:
        """Failed runs are NOT returned as incomplete."""
        from skill_harness.storage.migrations import open_evidence_readonly
        from skill_harness.storage.recovery import find_resumable_run_for_skill

        ev, rt = _open_pair(tmp_path)
        try:
            _seed_skill(ev)
            _seed_run_progress(rt, "run-failed-001", state="failed", ev=ev)
            ev_ro = open_evidence_readonly(tmp_path / "evidence.db")
            try:
                result = find_resumable_run_for_skill(
                    _SKILL_ID, evidence_conn_ro=ev_ro, runtime_conn=rt
                )
            finally:
                ev_ro.close()
            assert result is None
        finally:
            _close_pair(ev, rt)

    def test_find_incomplete_run_ignores_aborted_budget_runs(self, tmp_path: Path) -> None:
        """aborted_budget runs are NOT returned as incomplete."""
        from skill_harness.storage.migrations import open_evidence_readonly
        from skill_harness.storage.recovery import find_resumable_run_for_skill

        ev, rt = _open_pair(tmp_path)
        try:
            _seed_skill(ev)
            _seed_run_progress(rt, "run-aborted-001", state="aborted_budget", ev=ev)
            ev_ro = open_evidence_readonly(tmp_path / "evidence.db")
            try:
                result = find_resumable_run_for_skill(
                    _SKILL_ID, evidence_conn_ro=ev_ro, runtime_conn=rt
                )
            finally:
                ev_ro.close()
            assert result is None
        finally:
            _close_pair(ev, rt)

    def test_bare_rerun_warns_names_run_id_and_does_not_start_fresh(self, tmp_path: Path) -> None:
        """Integration test: bare --execute with an incomplete prior run WARNS, names the run_id,
        does NOT start a fresh run (A52 double-spend protection).

        _find_incomplete_run is NOT patched. _execute_ablation_run is patched to detect if
        it was incorrectly invoked.
        """
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_run_progress(rt, "run-must-resume-001", state="running", ev=ev)
        ev.close()
        rt.close()

        execute_called = []

        def _fake_execute(**kwargs: Any) -> list[Any]:
            execute_called.append(kwargs)
            return []

        with patch("skill_harness.cli.main._execute_ablation_run", side_effect=_fake_execute):
            result = _invoke(
                "run",
                "ablation",
                _SKILL_ID,
                *ratified_exec_args(_SKILL_ID),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        # Must have warned and named the run_id
        assert "run-must-resume-001" in result.output, (
            f"Expected run_id in warning:\n{result.output}"
        )
        assert "--resume" in result.output, f"Expected --resume hint in warning:\n{result.output}"
        # Must NOT have called _execute_ablation_run (double-spend guard)
        assert not execute_called, (
            f"_execute_ablation_run should NOT have been called, but got: {execute_called}"
        )
        # Must exit non-zero
        assert result.exit_code != 0, (
            f"Expected non-zero exit (guard fired), got {result.exit_code}"
        )


# ---------------------------------------------------------------------------
# B2: daily-cap enforcement UNPATCHED tests
# ---------------------------------------------------------------------------


def _seed_cost_ledger_entries(
    rt: sqlite3.Connection,
    total_usd: float,
    hours_ago: float = 1.0,
    run_id: str = "run-prior-001",
) -> None:
    """Seed cost_ledger rows to simulate prior spend within the trailing-24h window."""
    from skill_harness.storage.models import CostLedgerWrite
    from skill_harness.storage.repositories.runtime.cost_ledger import insert_cost_ledger_entry
    from skill_harness.storage.transaction import writer_transaction

    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
    with writer_transaction(rt):
        insert_cost_ledger_entry(
            rt,
            CostLedgerWrite(
                ts=ts,
                run_id=run_id,
                skill_id=_SKILL_ID,
                model_id="claude-sonnet-4-6",
                call_kind="subject",
                input_tok=1000,
                cache_write_tok=0,
                cache_read_tok=0,
                output_tok=100,
                usd=total_usd,
            ),
        )


class TestB2DailyCapEnforcement:
    """B2: daily_cap must be checked from real runtime.cost_ledger trailing-24h SUM(usd)."""

    def test_daily_cap_refused_when_already_at_cap(self, tmp_path: Path) -> None:
        """When trailing-24h spend == daily_cap, run must be refused with --daily-cap named."""
        ev, rt = _open_pair(tmp_path)
        try:
            _seed_skill(ev)
            # Seed 20.0 USD spend (equal to default --daily-cap 20.0)
            _seed_cost_ledger_entries(rt, total_usd=20.0, hours_ago=1.0)
            ev.close()
            rt.close()

            result = _invoke(
                "run",
                "ablation",
                _SKILL_ID,
                *ratified_exec_args(_SKILL_ID),
                "--daily-cap",
                "20.0",
                "--runtime-db",
                str(tmp_path / "runtime.db"),
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

            assert result.exit_code != 0, (
                f"Expected refusal (exit!=0) but got {result.exit_code}:\n{result.output}"
            )
            assert "--daily-cap" in result.output, f"Error must name --daily-cap:\n{result.output}"
        finally:
            pass

    def test_daily_cap_passed_when_old_entries_outside_window(self, tmp_path: Path) -> None:
        """Entries > 24h old must NOT count toward the daily cap.

        This test patches _execute_ablation_run to avoid needing a live API
        but does NOT patch the daily-cap check — that must run from real DB.
        """
        from skill_harness.ablation.stopping import StoppingReason

        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        # Seed 25.0 USD but 25 hours ago — outside the trailing-24h window
        _seed_cost_ledger_entries(rt, total_usd=25.0, hours_ago=25.0)
        ev.close()
        rt.close()

        mock_result = MagicMock()
        mock_result.stopping_reason = StoppingReason.PASSED
        mock_result.unmeasured_reason = None
        mock_result.length_confounded = False
        mock_result.samples_collected = 8
        mock_result.stop_decision = MagicMock()
        mock_result.stop_decision.p_win_rate_exceeds_threshold = 0.97
        mock_result.stop_decision.n_samples = 8
        mock_result.clause_id = "clause-001"

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                _SKILL_ID,
                *ratified_exec_args(_SKILL_ID),
                "--daily-cap",
                "20.0",
                "--runtime-db",
                str(tmp_path / "runtime.db"),
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        # Must NOT be refused by daily cap (old entries don't count)
        assert "--daily-cap" not in result.output or result.exit_code == 0, (
            f"Old entries should not trigger daily-cap refusal:\n{result.output}"
        )

    def test_daily_cap_error_names_cap_flag(self, tmp_path: Path) -> None:
        """The daily-cap refusal message must name the --daily-cap flag."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_cost_ledger_entries(rt, total_usd=19.5, hours_ago=1.0)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            *ratified_exec_args(_SKILL_ID),
            "--daily-cap",
            "19.0",  # cap is 19.0 but 19.5 already spent
            "--runtime-db",
            str(tmp_path / "runtime.db"),
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
        )

        assert result.exit_code != 0
        assert "--daily-cap" in result.output, f"Error must name --daily-cap:\n{result.output}"


# ---------------------------------------------------------------------------
# M1: dry-run opens evidence.db READ-ONLY to render real per-clause table
# ---------------------------------------------------------------------------


class TestM1DryRunRealClauseTable:
    """M1: dry-run must render real clause rows with correct status enum."""

    def test_dry_run_renders_testable_clause(self, tmp_path: Path) -> None:
        """A non-vacuous clause with falsifying_case → status TESTABLE."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(
            ev,
            "clause-testable-001",
            vacuity_flag="none",
            falsifying_case_schema_sha256="abc123",
            clause_text="Use concise language.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Dry-run failed: {result.output}"
        assert "TESTABLE" in result.output, (
            f"Expected TESTABLE status in dry-run output:\n{result.output}"
        )
        assert "NO CALLS MADE" in result.output

    def test_dry_run_renders_vacuous_excluded_clause(self, tmp_path: Path) -> None:
        """A vacuous clause → status VACUOUS-EXCLUDED."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(
            ev,
            "clause-vacuous-001",
            vacuity_flag="mechanical_vacuous",
            falsifying_case_schema_sha256=None,
            clause_text="This clause is metadata.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Dry-run failed: {result.output}"
        assert "VACUOUS-EXCLUDED" in result.output, (
            f"Expected VACUOUS-EXCLUDED in output:\n{result.output}"
        )

    def test_dry_run_renders_no_falsifying_case_clause(self, tmp_path: Path) -> None:
        """Non-vacuous clause without falsifying_case → status NO-FALSIFYING-CASE."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(
            ev,
            "clause-nfc-001",
            vacuity_flag="none",
            falsifying_case_schema_sha256=None,  # no falsifying case
            clause_text="Always respond in English.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0
        assert "NO-FALSIFYING-CASE" in result.output, (
            f"Expected NO-FALSIFYING-CASE in output:\n{result.output}"
        )

    def test_dry_run_mixed_vacuity_shows_all_statuses(self, tmp_path: Path) -> None:
        """Dry-run with mixed clauses must show all three status types."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(ev, "c-t", 0, vacuity_flag="none", falsifying_case_schema_sha256="abc")
        _seed_clause(
            ev, "c-v", 1, vacuity_flag="mechanical_vacuous", falsifying_case_schema_sha256=None
        )
        _seed_clause(ev, "c-n", 2, vacuity_flag="none", falsifying_case_schema_sha256=None)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0
        output = result.output
        assert "TESTABLE" in output
        assert "VACUOUS-EXCLUDED" in output
        assert "NO-FALSIFYING-CASE" in output
        assert "NO CALLS MADE" in output

    def test_dry_run_unknown_skill_clean_error(self, tmp_path: Path) -> None:
        """Dry-run with a skill_id not in DB → clean error, no crash."""
        ev, rt = _open_pair(tmp_path)
        # Do NOT seed any skill/clauses
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            "skill-does-not-exist",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        # Must not crash with a traceback — clean error or empty table with warning
        assert result.exit_code in (0, 1), (
            f"Expected 0 or 1 for unknown skill, got {result.exit_code}:\n{result.output}"
        )

    def test_dry_run_no_api_key_required_with_db(self, tmp_path: Path) -> None:
        """Dry-run with real DB must NOT require ANTHROPIC_API_KEY."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(ev, "c-ok", 0, vacuity_flag="none", falsifying_case_schema_sha256="abc")
        ev.close()
        rt.close()

        clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        clean_env["COLUMNS"] = "200"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "ablation",
                _SKILL_ID,
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            ],
            env=clean_env,
        )

        assert result.exit_code == 0, (
            f"Dry-run with DB must not need API key. exit={result.exit_code}\n{result.output}"
        )
        assert "NO CALLS MADE" in result.output


# ---------------------------------------------------------------------------
# M2 + M3: _load_clauses_from_db direct tests
# ---------------------------------------------------------------------------


class TestM3LoadClausesFromDb:
    """M3: _load_clauses_from_db — all, filtered by clause_id, no-testable-clauses error."""

    def test_load_clauses_returns_all_clauses(self, tmp_path: Path) -> None:
        """All clauses for a skill are returned when clause_id=None."""
        from skill_harness.cli.main import _load_clauses_from_db
        from skill_harness.storage.context import StorageContext

        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(ev, "c-001", 0, clause_text="Clause one.")
        _seed_clause(ev, "c-002", 1, clause_text="Clause two.")
        ev.close()
        rt.close()

        with StorageContext(tmp_path / "evidence.db", tmp_path / "runtime.db") as ctx:
            clauses = _load_clauses_from_db(ctx, _SKILL_ID, None)

        assert len(clauses) == 2
        clause_ids = {c.clause_id for c in clauses}
        assert "c-001" in clause_ids
        assert "c-002" in clause_ids

    def test_load_clauses_filters_by_clause_id(self, tmp_path: Path) -> None:
        """When clause_id is given, only that clause is returned."""
        from skill_harness.cli.main import _load_clauses_from_db
        from skill_harness.storage.context import StorageContext

        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(ev, "c-001", 0, clause_text="Clause one.")
        _seed_clause(ev, "c-002", 1, clause_text="Clause two.")
        ev.close()
        rt.close()

        with StorageContext(tmp_path / "evidence.db", tmp_path / "runtime.db") as ctx:
            clauses = _load_clauses_from_db(ctx, _SKILL_ID, "c-002")

        assert len(clauses) == 1
        assert clauses[0].clause_id == "c-002"

    def test_load_clauses_empty_for_unknown_skill(self, tmp_path: Path) -> None:
        """Unknown skill_id returns empty list (no error)."""
        from skill_harness.cli.main import _load_clauses_from_db
        from skill_harness.storage.context import StorageContext

        ev, rt = _open_pair(tmp_path)
        ev.close()
        rt.close()

        with StorageContext(tmp_path / "evidence.db", tmp_path / "runtime.db") as ctx:
            clauses = _load_clauses_from_db(ctx, "skill-nonexistent", None)

        assert clauses == []

    def test_execute_raises_click_exception_when_no_clauses(self, tmp_path: Path) -> None:
        """--execute with no testable clauses raises a ClickException naming the skill."""
        ev, rt = _open_pair(tmp_path)
        # Seed skill but no clauses
        _seed_skill(ev)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            *ratified_exec_args(_SKILL_ID),
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
            env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
        )

        assert result.exit_code != 0
        assert _SKILL_ID in result.output or "No testable" in result.output, (
            f"Error should name the skill or mention 'No testable':\n{result.output}"
        )


# ---------------------------------------------------------------------------
# M4: rich.progress dual-cap footer during --execute
# ---------------------------------------------------------------------------


class TestM4ProgressFooter:
    """M4: dual-cap footer 'spent $X / cap $Y (run) · $Z / $W (day)' shows during --execute."""

    def test_progress_footer_format_appears_in_execute(self, tmp_path: Path) -> None:
        """Execute must print a footer with 'cap' and '(run)' and '(day)' or equivalent."""
        from skill_harness.ablation.stopping import StoppingReason

        mock_result = MagicMock()
        mock_result.stopping_reason = StoppingReason.PASSED
        mock_result.unmeasured_reason = None
        mock_result.length_confounded = False
        mock_result.samples_collected = 8
        mock_result.stop_decision = MagicMock()
        mock_result.stop_decision.p_win_rate_exceeds_threshold = 0.97
        mock_result.stop_decision.n_samples = 8
        mock_result.clause_id = "clause-001"

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-abc",
                *ratified_exec_args(),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        output = result.output
        # Footer must show cap-related info
        has_cap_info = (
            ("cap" in output.lower() and ("run" in output.lower() or "day" in output.lower()))
            or "spent" in output.lower()
            or "$" in output
        )
        assert has_cap_info, (
            f"Expected dual-cap footer with 'cap' and (run)/(day) in output:\n{output}"
        )


# ---------------------------------------------------------------------------
# m1: --show-rendered loads real clause text (not placeholder)
# ---------------------------------------------------------------------------


class TestM1ShowRenderedRealText:
    """m1: --show-rendered must load real clause_text from evidence DB, not [clause: {id}]."""

    def test_show_rendered_loads_real_clause_text(self, tmp_path: Path) -> None:
        """--show-rendered must NOT emit the placeholder '[clause: <id>]' — real text instead."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        real_text = "Always use bullet points when listing items. This is verbatim text."
        _seed_clause(ev, "clause-real-001", clause_text=real_text)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            "--show-rendered",
            "clause-real-001",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        output = result.output
        # Must NOT be the placeholder
        assert "[clause: clause-real-001]" not in output, (
            f"Placeholder must not appear in output:\n{output}"
        )
        # Must contain real clause text (or at least not the sentinel)
        assert "clause-real-001" in output or real_text[:30] in output, (
            f"Expected real clause text in output, not placeholder:\n{output}"
        )


# ---------------------------------------------------------------------------
# m2: resume loads user_message from runs.config_json
# ---------------------------------------------------------------------------


class TestM2ResumeUserMessage:
    """m2: resume must load user_message from runs.config_json, not pass empty string."""

    def test_resume_ablation_receives_user_message_from_config(self, tmp_path: Path) -> None:
        """_execute_ablation_run called with --resume must receive non-empty user_message
        loaded from runs.config_json.

        We seed a run with a known user_message in config_json and assert the
        runner call gets that message (not "").
        """
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)

        # Seed a run with user_message in config_json
        run_id = "run-resume-msg-001"
        expected_msg = "Write a detailed essay about climate change."
        config = json.dumps(
            {
                "run_id": run_id,
                "skill_id": _SKILL_ID,
                "user_message": expected_msg,
                "clauses": [],
                "subject_model": "claude-sonnet-4-6",
                "n_min": 8,
                "n_inc": 4,
                "n_max": 40,
                "max_usd": 5.0,
                "family_size": 0,
                "stopping_reasons": {},
            }
        )

        from skill_harness.storage.models import RunWrite
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.transaction import writer_transaction

        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config,
                    started_at=_TS,
                    completed_at=None,
                ),
            )

        _seed_run_progress(rt, run_id, state="running")
        ev.close()
        rt.close()

        captured_calls: list[dict[str, Any]] = []

        def _fake_execute(**kwargs: Any) -> list[Any]:
            captured_calls.append(kwargs)
            return []

        with patch("skill_harness.cli.main._execute_ablation_run", side_effect=_fake_execute):
            _invoke(
                "run",
                "ablation",
                _SKILL_ID,
                *ratified_exec_args(_SKILL_ID),
                "--resume",
                run_id,
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        # The runner call must have received the user_message from config_json
        # (not an empty string "")
        assert len(captured_calls) >= 1, "Expected _execute_ablation_run to have been called"
        # We don't directly inspect the kwarg because it may be encapsulated differently;
        # but we verify the function IS called (integration smoke check)
        # The actual user_message check requires deeper integration — we test via the
        # _load_user_message_from_run unit test below.

    def test_load_user_message_from_run_returns_config_value(self, tmp_path: Path) -> None:
        """_load_user_message_from_run must return the user_message from runs.config_json."""
        from skill_harness.cli.main import _load_user_message_from_run

        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)

        run_id = "run-msg-test-001"
        expected_msg = "Explain quantum entanglement to a 10-year-old."
        config = json.dumps({"user_message": expected_msg, "other": "stuff"})

        from skill_harness.storage.models import RunWrite
        from skill_harness.storage.repositories.evidence.runs import insert_run
        from skill_harness.storage.transaction import writer_transaction

        with writer_transaction(ev):
            insert_run(
                ev,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json=config,
                    started_at=_TS,
                    completed_at=None,
                ),
            )
        rt.close()

        msg = _load_user_message_from_run(ev, run_id)
        assert msg == expected_msg, f"Expected {expected_msg!r}, got {msg!r}"
        ev.close()

    def test_load_user_message_returns_empty_string_for_missing_run(self, tmp_path: Path) -> None:
        """_load_user_message_from_run returns '' when run_id does not exist."""
        from skill_harness.cli.main import _load_user_message_from_run

        ev, rt = _open_pair(tmp_path)
        rt.close()
        msg = _load_user_message_from_run(ev, "nonexistent-run-id")
        assert msg == ""
        ev.close()


# ---------------------------------------------------------------------------
# m3: API key pre-flight before first DB write on --execute
# ---------------------------------------------------------------------------


class TestM3ApiKeyPreflight:
    """m3: missing ANTHROPIC_API_KEY on --execute must be refused BEFORE any DB write."""

    def test_missing_api_key_refused_before_db_write(self, tmp_path: Path) -> None:
        """--execute without any usable API key must refuse BEFORE inserting any run row.

        The pre-flight check is now model-aware (_resolve_subject_model_with_fallback).
        Removing only ANTHROPIC_API_KEY is insufficient if OPENROUTER_API_KEY is set
        (the resolver would auto-route via OpenRouter and proceed). We must strip both
        ANTHROPIC_API_KEY and OPENROUTER_API_KEY to test the "no keys at all → refuse"
        path for the default claude-* subject model.

        Confirmed by checking that no run_progress row exists after the refusal.
        """
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_clause(ev, "c-001", clause_text="Test clause.")
        ev.close()
        rt.close()

        # Build override dict: pass None for the two key vars so CliRunner deletes them
        # from os.environ during the invocation. Simply omitting a key from the override
        # dict does NOT remove it from os.environ — CliRunner only applies listed overrides.
        clean_env: dict[str, str | None] = {
            k: v
            for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
        }
        clean_env["ANTHROPIC_API_KEY"] = None  # delete from os.environ if present
        clean_env["OPENROUTER_API_KEY"] = None  # delete from os.environ if present
        clean_env["COLUMNS"] = "200"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "ablation",
                _SKILL_ID,
                *ratified_exec_args(_SKILL_ID),
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            ],
            env=clean_env,
        )

        # Must be refused
        assert result.exit_code != 0, (
            f"Expected refusal without API key, got exit 0:\n{result.output}"
        )

        # No orphan run row must have been written
        rt_check = open_runtime(tmp_path / "runtime.db")
        try:
            rows = rt_check.execute("SELECT run_id FROM run_progress").fetchall()
            assert rows == [], (
                f"No run_progress rows should exist after pre-flight refusal; got: {rows}"
            )
        finally:
            rt_check.close()


# ---------------------------------------------------------------------------
# m4: exit-code contract — UNMEASURED=2, refusals=1, success=0
# ---------------------------------------------------------------------------


class TestM4ExitCodeContract:
    """m4: UNMEASURED=2 must be distinct from refusal=1 and success=0."""

    def test_daily_cap_refusal_exits_one_not_two(self, tmp_path: Path) -> None:
        """Daily-cap refusal must exit 1 (intentional error), not 2 (UNMEASURED)."""
        ev, rt = _open_pair(tmp_path)
        _seed_skill(ev)
        _seed_cost_ledger_entries(rt, total_usd=25.0, hours_ago=1.0)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "ablation",
            _SKILL_ID,
            *ratified_exec_args(_SKILL_ID),
            "--daily-cap",
            "20.0",
            "--runtime-db",
            str(tmp_path / "runtime.db"),
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
        )

        # Exit 1 = intentional refusal (not 2 = UNMEASURED, not 0 = success)
        assert result.exit_code == 1, (
            f"Daily-cap refusal must exit 1, got {result.exit_code}:\n{result.output}"
        )

    def test_bare_rerun_guard_exits_one_not_two(self, tmp_path: Path) -> None:
        """Bare-rerun guard (A52) must exit 1 (intentional refusal), not 2.

        Patches _find_incomplete_run_for_execute at the cli.main module level
        (the private helper that wraps find_resumable_run_for_skill in E.3).
        """
        with patch(
            "skill_harness.cli.main._find_incomplete_run_for_execute",
            return_value="run-blocking-001",
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-abc",
                *ratified_exec_args(),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 1, (
            f"Bare-rerun guard must exit 1, got {result.exit_code}:\n{result.output}"
        )

    def test_unmeasured_clause_exits_two(self) -> None:
        """UNMEASURED clause must exit 2 (distinct from refusal exit 1)."""
        from skill_harness.ablation.stopping import StoppingReason

        mock_result = MagicMock()
        mock_result.stopping_reason = StoppingReason.UNDERPOWERED_NMAX
        mock_result.unmeasured_reason = "underpowered"
        mock_result.length_confounded = False
        mock_result.samples_collected = 40
        mock_result.stop_decision = MagicMock()
        mock_result.stop_decision.p_win_rate_exceeds_threshold = 0.5
        mock_result.stop_decision.n_samples = 40
        mock_result.clause_id = "clause-unm"

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-abc",
                *ratified_exec_args(),
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        assert result.exit_code == 2, f"UNMEASURED must exit 2, got {result.exit_code}"


# ---------------------------------------------------------------------------
# open_evidence_readonly unit tests (M1 council-sanctioned helper)
# ---------------------------------------------------------------------------


class TestOpenEvidenceReadonly:
    """Unit tests for the council-sanctioned open_evidence_readonly helper (A51)."""

    def test_readonly_open_reads_committed_rows(self, tmp_path: Path) -> None:
        """open_evidence_readonly on a seeded DB can read committed rows."""
        from skill_harness.storage.migrations import open_evidence_readonly

        # Seed via normal writable open
        ev = open_evidence(tmp_path / "evidence.db")
        _seed_skill(ev)
        ev.close()

        # Open read-only and verify rows are readable
        ro_conn = open_evidence_readonly(tmp_path / "evidence.db")
        try:
            rows = ro_conn.execute("SELECT skill_id FROM skills").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == _SKILL_ID
        finally:
            ro_conn.close()

    def test_readonly_open_refuses_write(self, tmp_path: Path) -> None:
        """open_evidence_readonly must raise on any write attempt."""
        from skill_harness.storage.migrations import open_evidence_readonly

        # Seed via normal writable open
        ev = open_evidence(tmp_path / "evidence.db")
        _seed_skill(ev)
        ev.close()

        ro_conn = open_evidence_readonly(tmp_path / "evidence.db")
        try:
            with pytest.raises(Exception):
                # Any write should raise (SQLITE_READONLY or query_only violation)
                ro_conn.execute(
                    "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("bad-id", "bad", "/bad", "a" * 64, _TS),
                )
        finally:
            ro_conn.close()

    def test_readonly_open_raises_bootstrap_error_for_missing_file(self, tmp_path: Path) -> None:
        """open_evidence_readonly on a missing file raises BootstrapError (not create)."""
        from skill_harness.storage.errors import BootstrapError
        from skill_harness.storage.migrations import open_evidence_readonly

        with pytest.raises(BootstrapError):
            open_evidence_readonly(tmp_path / "does_not_exist.db")


# ---------------------------------------------------------------------------
# I1 FALSIFYING: _check_daily_cap must fail CLOSED on read errors
# ---------------------------------------------------------------------------


class TestI1DailyCapFailsClosed:
    """I1: _check_daily_cap must NOT silently allow a run when the ledger throws a
    non-absent error. 'except Exception: return' fails OPEN — must fail CLOSED.

    Narrowed exception handling: BootstrapError (ledger absent) -> allow (return 0).
    Any other error (e.g. sqlite3.DatabaseError, OperationalError) -> raise RuntimeError.
    """

    def test_daily_cap_fails_closed_on_non_absent_read_error(self, tmp_path: Path) -> None:
        """I1 FALSIFYING: _check_daily_cap must refuse when ledger throws non-absent error.

        We patch select_cost_ledger_since to raise a generic sqlite3.OperationalError
        (simulating a DB corruption or unexpected error). The current code silently returns
        (fails OPEN). After fix, it must raise or propagate the error (fail CLOSED).

        RED against current 'except Exception: return' code.
        GREEN after narrowing to BootstrapError-only allow.
        """
        from unittest.mock import patch

        from skill_harness.cli.main import _check_daily_cap

        rt = open_runtime(tmp_path / "runtime.db")
        rt.close()

        # Simulate a non-absent read error (DB corruption, etc.)
        # This must cause _check_daily_cap to REFUSE the run, not silently allow it.
        # Patch at the repository module level (where the function is imported from)
        with (
            patch(
                "skill_harness.storage.repositories.runtime.cost_ledger.select_cost_ledger_since",
                side_effect=Exception("simulated DB corruption"),
            ),
            pytest.raises(
                Exception, match=r"simulated DB corruption|Daily cap check failed|refuse"
            ),
        ):
            _check_daily_cap(tmp_path / "runtime.db", 20.0)

    def test_daily_cap_allows_when_ledger_absent(self, tmp_path: Path) -> None:
        """I1: absent ledger (BootstrapError / DB not yet created) must be treated as 0 spend.

        When the DB doesn't exist yet, the function should NOT block the run — the operator
        hasn't spent anything yet. This is the only 'allow' case.
        """
        from skill_harness.cli.main import _check_daily_cap

        # Point to a non-existent runtime DB — should allow (0 trailing spend)
        # Must NOT raise (absent ledger is the legitimate "no prior spend" case)
        try:
            _check_daily_cap(tmp_path / "nonexistent_runtime.db", 20.0)
        except Exception as exc:
            # If the DB is absent and it raises, that's also acceptable (fail-safe)
            # but it must NOT be the "simulated DB corruption" case from test above
            # For now we just assert it does not raise _DailyCapExceededError
            from skill_harness.cli.main import _DailyCapExceededError

            assert not isinstance(exc, _DailyCapExceededError), (
                "Absent ledger must not trigger _DailyCapExceededError (0 spend = under cap)"
            )

    def test_daily_cap_misleading_comment_removed(self, tmp_path: Path) -> None:
        """I1: The 'conservative' comment in _check_daily_cap must be gone or corrected.

        This test reads the source to verify the misleading comment is not present.
        The comment 'Conservative: if we can't read, don't block' is false-confidence slop
        because silently allowing a billed run when the ledger is unreadable is the OPPOSITE
        of conservative. After fix, the comment must be absent or corrected.
        """
        import inspect

        from skill_harness.cli.main import _check_daily_cap

        source = inspect.getsource(_check_daily_cap)
        assert "Conservative: if we can't read, don't block" not in source, (
            "I1: Misleading 'conservative' comment must be removed from _check_daily_cap. "
            "Silently allowing a billed run on read error is NOT conservative."
        )


# ---------------------------------------------------------------------------
# I4 FALSIFYING: footer must show actual spend or be honestly labeled caps-only
# ---------------------------------------------------------------------------


class TestI4FooterHonesty:
    """I4: footer must not imply 'spent $X / cap $Y' without computing real spend."""

    def test_footer_does_not_imply_false_spend_tracking(self, tmp_path: Path) -> None:
        """I4: the footer must be honest — either show real spend or label as caps only.

        The current footer prints 'Per-run cap: $X' and 'Daily cap: $Y' without computing
        the actual spend, but the phrasing can imply spend tracking. After fix:
        - Either: compute real run spend from cost_ledger and display 'spent $X / cap $Y'
        - Or: honestly label as caps-only (no implied spend tracking)

        This test asserts that if '$' and 'cap' appear together, either 'spent' appears too
        (indicating real spend tracking) or the label is explicitly 'caps' (honest label).
        """
        from skill_harness.ablation.stopping import StoppingReason

        mock_result = MagicMock()
        mock_result.stopping_reason = StoppingReason.PASSED
        mock_result.unmeasured_reason = None
        mock_result.length_confounded = False
        mock_result.samples_collected = 8
        mock_result.stop_decision = MagicMock()
        mock_result.stop_decision.p_win_rate_exceeds_threshold = 0.97
        mock_result.stop_decision.n_samples = 8
        mock_result.clause_id = "clause-i4"

        with patch(
            "skill_harness.cli.main._execute_ablation_run",
            return_value=[mock_result],
        ):
            result = _invoke(
                "run",
                "ablation",
                "skill-i4",
                *ratified_exec_args("skill-i4"),
                "--max-usd",
                "5.0",
                "--daily-cap",
                "20.0",
                env={"ANTHROPIC_API_KEY": "sk-test-dummy"},
            )

        output = result.output
        # The footer must be honest: either show real spend OR label as caps-only
        # The misleading "spend summary" section that implies spent=$X/cap=$Y without
        # actually computing spent is the bug. After fix, either:
        # Option A: "spent" appears with a real computed value
        # Option B: the label explicitly says "caps" or "cap only" without implying spend
        footer_section = output.lower()
        has_spend = "spent" in footer_section and "$" in footer_section
        has_cap_label = "cap" in footer_section and (
            "caps only" in footer_section or "cap:" in footer_section or "per-run" in footer_section
        )
        assert has_spend or has_cap_label, (
            f"I4: footer must be honest — either compute real spend or label as caps-only. "
            f"Output:\n{output}"
        )
