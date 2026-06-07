"""CLI integration tests for `run evaluate-skill` (Track E.3, A54).

TDD: written RED first (against the stub), GREEN after implementation.

Exit-code matrix:
  0 = no UNMEASURED in the family (all PASSED / FAILED / CONFOUNDED)
  2 = ≥1 UNMEASURED
  1 = hard error (precondition fail; aggregation exception)

All tests tagged 'not live' — no Anthropic API calls.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from skill_harness.cli.main import cli
from skill_harness.storage.migrations import open_evidence, open_runtime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TS = "2026-06-06T10:00:00.000Z"
_TS2 = "2026-06-06T11:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64

SKILL_ID = "skill-eval-001"
RUN_ID = "run-eval-001"
CLAUSE_ID = "clause-eval-001"
AXIS = "verbosity"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _invoke(*args: str, env: dict[str, str] | None = None) -> Any:
    runner = CliRunner()
    merged_env: dict[str, str] = {"COLUMNS": "200"}
    if env is not None:
        merged_env.update(env)
    return runner.invoke(cli, list(args), env=merged_env)


def open_both(tmp_path: Path) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    return ev, rt


def _insert_skill(conn: sqlite3.Connection, skill_id: str = SKILL_ID) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Test Skill', '/path/to/skill.md', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_clause(
    conn: sqlite3.Connection,
    clause_id: str = CLAUSE_ID,
    skill_id: str = SKILL_ID,
    axis: str = AXIS,
    clause_index: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
        " VALUES (?, ?, ?, ?, ?, ?, 'decrease', 1, 'none')",
        (clause_id, skill_id, clause_index, clause_index, f"Clause text {clause_id}", axis),
    )


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str = RUN_ID,
    skill_id: str = SKILL_ID,
    completed: bool = True,
    family_size: int = 1,
) -> None:
    config = json.dumps(
        {
            "run_id": run_id,
            "skill_id": skill_id,
            "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
            "subject_model": "claude-sonnet-4-6",
            "user_message": "test",
            "family_size": family_size,
            "stopping_reasons": {},
        },
        sort_keys=True,
    )
    completed_at = _TS2 if completed else None
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (run_id, skill_id, config, _TS, completed_at),
    )


def _insert_run_progress(
    conn: sqlite3.Connection,
    run_id: str = RUN_ID,
    state: str = "completed",
) -> None:
    conn.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, ?, 10, 10, ?)",
        (run_id, state, _TS2),
    )


def _insert_metric_version(
    conn: sqlite3.Connection,
    metric_id: str = AXIS,
    version: str = "1.0.0",
) -> None:
    conn.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, ?, ?, 1, 1, 1, ?)",
        (metric_id, version, _SHA2, _TS),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    sample_id: str,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
    condition: str = "full",
    sample_index: int = 0,
) -> None:
    output_text = f"Sample output for {sample_id}"
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at, sample_index)"
        " VALUES (?, ?, ?, ?, 'claude-sonnet-4-6', ?, ?, ?, ?)",
        (
            sample_id,
            run_id,
            clause_id,
            condition,
            output_text,
            sha256_of(output_text),
            _TS,
            sample_index,
        ),
    )


def _insert_verdict(
    conn: sqlite3.Connection,
    verdict_id: str,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
    axis: str = AXIS,
    sample_a_id: str = "sa",
    sample_b_id: str = "sb",
    observation: float = 1.0,
    admissibility_state: str = "admissible",
    comparison: str = "full_vs_ablated",
    metric_id: str = AXIS,
    metric_version: str = "1.0.0",
) -> None:
    conn.execute(
        """INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version,
            admissibility_state, written_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (
            verdict_id,
            run_id,
            clause_id,
            axis,
            comparison,
            sample_a_id,
            sample_b_id,
            observation,
            metric_id,
            metric_version,
            admissibility_state,
            _TS,
        ),
    )


def _insert_frozen_case(
    conn: sqlite3.Connection,
    frozen_case_id: str,
    clause_id: str = CLAUSE_ID,
    axis: str = AXIS,
    run_id: str = RUN_ID,
    metric_id: str = AXIS,
    metric_version: str = "1.0.0",
) -> None:
    failing_text = f"failing-input-{frozen_case_id}"
    conn.execute(
        """INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, metric_id, metric_version, implementation_hash,
            run_id, axis
        ) VALUES (?, ?, ?, ?, 'mechanical', ?, ?, ?, ?, ?)""",
        (
            frozen_case_id,
            clause_id,
            failing_text,
            sha256_of(failing_text),
            metric_id,
            metric_version,
            _SHA2,
            run_id,
            axis,
        ),
    )


def _seed_all_passed(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    n_wins: int = 9,
    skill_id: str = SKILL_ID,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
) -> None:
    """Seed evidence that produces a PASSED clause (with frozen case at current version)."""
    _insert_skill(ev, skill_id=skill_id)
    _insert_clause(ev, clause_id=clause_id, skill_id=skill_id)
    _insert_metric_version(ev)
    _insert_run(ev, run_id=run_id, skill_id=skill_id)
    _insert_run_progress(rt, run_id=run_id, state="completed")
    for i in range(n_wins):
        sa = f"sa-{i}"
        sb = f"sb-{i}"
        _insert_sample(ev, sa, run_id=run_id, clause_id=clause_id, condition="full", sample_index=i)
        _insert_sample(
            ev, sb, run_id=run_id, clause_id=clause_id, condition="ablated", sample_index=i
        )
        _insert_verdict(
            ev,
            verdict_id=f"v-{i}",
            run_id=run_id,
            clause_id=clause_id,
            sample_a_id=sa,
            sample_b_id=sb,
            observation=1.0,
        )
    _insert_frozen_case(ev, frozen_case_id="fc-001", clause_id=clause_id, run_id=run_id)


def _seed_underpowered(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    skill_id: str = SKILL_ID,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
) -> None:
    """Seed evidence that produces an UNMEASURED clause (only 2 verdicts — below N_min=8)."""
    _insert_skill(ev, skill_id=skill_id)
    _insert_clause(ev, clause_id=clause_id, skill_id=skill_id)
    _insert_metric_version(ev)
    _insert_run(ev, run_id=run_id, skill_id=skill_id)
    _insert_run_progress(rt, run_id=run_id, state="completed")
    for i in range(2):
        sa = f"sa-{i}"
        sb = f"sb-{i}"
        _insert_sample(ev, sa, run_id=run_id, clause_id=clause_id, condition="full", sample_index=i)
        _insert_sample(
            ev, sb, run_id=run_id, clause_id=clause_id, condition="ablated", sample_index=i
        )
        _insert_verdict(
            ev,
            verdict_id=f"v-{i}",
            run_id=run_id,
            clause_id=clause_id,
            sample_a_id=sa,
            sample_b_id=sb,
            observation=1.0,
        )


# ---------------------------------------------------------------------------
# Tests: No completed runs → exit 1
# ---------------------------------------------------------------------------


class TestEvaluateSkillNoRuns:
    def test_zero_runs_exits_1_with_message(self, tmp_path: Path) -> None:
        """evaluate-skill with zero completed runs → exit 1, user-friendly message."""
        ev, rt = open_both(tmp_path)
        _insert_skill(ev)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for no completed runs, got {result.exit_code}:\n{result.output}"
        )
        # Must name the skill_id and hint to run ablation
        assert SKILL_ID in result.output, f"Must name skill_id:\n{result.output}"
        assert "ablation" in result.output.lower(), f"Must hint to run ablation:\n{result.output}"

    def test_zero_runs_no_api_calls(self, tmp_path: Path) -> None:
        """evaluate-skill with zero runs must NOT call the Anthropic API."""
        ev, rt = open_both(tmp_path)
        _insert_skill(ev)
        ev.close()
        rt.close()

        anthropic_called = []

        with patch("anthropic.Anthropic", side_effect=lambda **kw: anthropic_called.append(kw)):
            _invoke(
                "run",
                "evaluate-skill",
                SKILL_ID,
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        assert not anthropic_called, "Anthropic API must not be called by evaluate-skill"


# ---------------------------------------------------------------------------
# Tests: Incomplete runs → exit 1
# ---------------------------------------------------------------------------


class TestEvaluateSkillIncompleteRuns:
    def test_incomplete_run_exits_1_with_resume_hint(self, tmp_path: Path) -> None:
        """evaluate-skill with incomplete run → exit 1, names run_id, hints --resume."""
        ev, rt = open_both(tmp_path)
        _insert_skill(ev)
        _insert_run(ev, completed=False)
        _insert_run_progress(rt, state="running")
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for incomplete run, got {result.exit_code}:\n{result.output}"
        )
        assert RUN_ID in result.output, f"Must name the incomplete run_id:\n{result.output}"
        assert "--resume" in result.output, f"Must hint --resume:\n{result.output}"


# ---------------------------------------------------------------------------
# Tests: Dry-run flag (preflight only)
# ---------------------------------------------------------------------------


class TestEvaluateSkillDryRun:
    def test_dry_run_prints_preflight_no_aggregation(self, tmp_path: Path) -> None:
        """--dry-run: prints what would be aggregated, does NOT call aggregate_skill."""
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        aggregate_called = []

        with patch(
            "skill_harness.cli.main.aggregate_skill",
            side_effect=lambda *a, **kw: aggregate_called.append(kw),
        ):
            result = _invoke(
                "run",
                "evaluate-skill",
                SKILL_ID,
                "--dry-run",
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        assert result.exit_code == 0, f"dry-run must exit 0:\n{result.output}"
        assert not aggregate_called, "aggregate_skill must NOT be called in dry-run"
        assert "NO AGGREGATION DONE" in result.output, (
            f"Must print NO AGGREGATION DONE:\n{result.output}"
        )
        assert "--dry-run" in result.output, f"Must remind to remove --dry-run:\n{result.output}"


# ---------------------------------------------------------------------------
# Tests: UNMEASURED clause → exit 2
# ---------------------------------------------------------------------------


class TestEvaluateSkillUnmeasured:
    def test_unmeasured_clause_exits_2(self, tmp_path: Path) -> None:
        """evaluate-skill with ≥1 UNMEASURED clause → exit 2."""
        ev, rt = open_both(tmp_path)
        _seed_underpowered(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 2, (
            f"Expected exit 2 for UNMEASURED clause, got {result.exit_code}:\n{result.output}"
        )

    def test_unmeasured_clause_json_format_exits_2_with_status(self, tmp_path: Path) -> None:
        """evaluate-skill --format=json with UNMEASURED clause → exit 2, JSON contains status."""
        ev, rt = open_both(tmp_path)
        _seed_underpowered(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--format=json",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 2, (
            f"Expected exit 2 for UNMEASURED, got {result.exit_code}:\n{result.output}"
        )
        report = json.loads(result.output)
        assert any(c["status"] == "UNMEASURED" for c in report["clauses"]), (
            f"JSON must contain UNMEASURED clause:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: All PASSED → exit 0
# ---------------------------------------------------------------------------


class TestEvaluateSkillAllPassed:
    def test_all_passed_exits_0(self, tmp_path: Path) -> None:
        """evaluate-skill with all PASSED clauses → exit 0."""
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0 for all PASSED, got {result.exit_code}:\n{result.output}"
        )

    def test_all_passed_json_format(self, tmp_path: Path) -> None:
        """--format=json produces valid JSON with skill_id and clauses fields."""
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--format=json",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
        report = json.loads(result.output)
        assert report["skill_id"] == SKILL_ID
        assert "clauses" in report
        assert report["report_schema_version"] == "1.1.0"  # bumped in C1 fix-loop per A60

    def test_json_output_to_stdout_warnings_to_stderr(self, tmp_path: Path) -> None:
        """T8: --format=json stdout is clean JSON; warnings go to stderr (Click 8.2+ API).

        Click 8.2+ separates stderr/stdout by default. Uses result.stderr direct assertion
        (not a merged result.output check) to verify shell-pipeline safety: a warning
        written to sys.stderr during aggregate_skill must NOT contaminate result.stdout.

        Replaces the prior weaker approach (logging.getLogger(...).warning()) which did
        not assert result.stderr — the test name promised stderr separation but only proved
        happy-path JSON parses. This test uses sys.stderr.write directly so CliRunner
        captures the write in result.stderr, providing a falsifiable assertion.
        """
        import sys
        from functools import wraps

        from skill_harness.aggregation import aggregate_skill as real_aggregate_skill
        from skill_harness.aggregation.report import SkillReport, to_json_bytes

        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        sentinel_warning = "test-sentinel-warning-t8-stderr-separation\n"
        captured_report: list[SkillReport] = []

        @wraps(real_aggregate_skill)
        def aggregate_skill_with_warning(*args: object, **kwargs: object) -> SkillReport:
            sys.stderr.write(sentinel_warning)
            report = real_aggregate_skill(*args, **kwargs)  # type: ignore[arg-type]
            captured_report.append(report)
            return report

        # Click 8.2+: CliRunner() separates stdout/stderr by default.
        # result.stdout = stdout only; result.stderr = stderr only.
        runner = CliRunner()
        with patch("skill_harness.cli.main.aggregate_skill", new=aggregate_skill_with_warning):
            result = runner.invoke(
                cli,
                [
                    "run",
                    "evaluate-skill",
                    SKILL_ID,
                    "--format=json",
                    "--evidence-db",
                    str(tmp_path / "evidence.db"),
                    "--runtime-db",
                    str(tmp_path / "runtime.db"),
                ],
                env={"COLUMNS": "200"},
            )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        # result.stderr must contain the injected warning (Click 8.2+ API)
        assert sentinel_warning in result.stderr, (
            f"Expected sentinel warning in result.stderr.\n"
            f"stderr: {result.stderr!r}\nstdout: {result.stdout!r}"
        )
        # result.stdout must be byte-equal to to_json_bytes(report) — clean JSON only
        assert len(captured_report) == 1, "aggregate_skill_with_warning must be called once"
        expected_bytes = to_json_bytes(captured_report[0])
        assert result.stdout.encode("utf-8") == expected_bytes, (
            f"result.stdout must be byte-equal to to_json_bytes(report).\n"
            f"stdout: {result.stdout!r}\nexpected: {expected_bytes!r}"
        )


# ---------------------------------------------------------------------------
# Tests: Rich format (default)
# ---------------------------------------------------------------------------


class TestEvaluateSkillRichFormat:
    def test_rich_format_renders_vector_summary(self, tmp_path: Path) -> None:
        """--format=rich (default) renders a table with Passed/Failed/Unmeasured counts."""
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        # Rich table header check
        output = result.output
        # Should show clause_id column
        assert CLAUSE_ID in output or "clause" in output.lower(), (
            f"Rich output should show clause info:\n{output}"
        )

    def test_rich_format_unmeasured_row_present(self, tmp_path: Path) -> None:
        """--format=rich with UNMEASURED clause shows UNMEASURED in output."""
        ev, rt = open_both(tmp_path)
        _seed_underpowered(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 2, f"Expected exit 2:\n{result.output}"
        assert "UNMEASURED" in result.output, f"Rich output must show UNMEASURED:\n{result.output}"

    def test_rich_format_contribution_note_a50(self, tmp_path: Path) -> None:
        """Rich format must display A50 framing (LOO / lower-bound under redundancy)."""
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        result = _invoke(
            "run",
            "evaluate-skill",
            SKILL_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        output = result.output.lower()
        assert "redundancy" in output or "loo" in output or "lower-bound" in output, (
            f"Rich output must show A50 contribution framing:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: JSON byte-stability
# ---------------------------------------------------------------------------


class TestEvaluateSkillJsonByteStability:
    def test_json_output_byte_stable_for_identical_evidence(self, tmp_path: Path) -> None:
        """JSON output must be byte-stable for identical evidence (run twice → same bytes).

        The only non-deterministic field is generated_at_utc (caller-supplied).
        We patch datetime.now() to fix it.
        """
        ev, rt = open_both(tmp_path)
        _seed_all_passed(ev, rt)
        ev.close()
        rt.close()

        fixed_ts = "2026-06-06T12:00:00.000000+00:00"

        with patch("skill_harness.cli.main.datetime") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = fixed_ts
            mock_dt.now.return_value = type("MockDT", (), {"isoformat": lambda self: fixed_ts})()
            result1 = _invoke(
                "run",
                "evaluate-skill",
                SKILL_ID,
                "--format=json",
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        with patch("skill_harness.cli.main.datetime") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = fixed_ts
            mock_dt.now.return_value = type("MockDT", (), {"isoformat": lambda self: fixed_ts})()
            result2 = _invoke(
                "run",
                "evaluate-skill",
                SKILL_ID,
                "--format=json",
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        assert result1.exit_code == 0 and result2.exit_code == 0
        assert result1.output == result2.output, (
            "JSON output must be byte-stable for identical evidence"
        )


# ---------------------------------------------------------------------------
# Tests: help string (acceptance gate)
# ---------------------------------------------------------------------------


class TestEvaluateSkillHelp:
    def test_help_shows_format_and_dry_run_flags(self) -> None:
        """--help must document --format and --dry-run flags."""
        result = _invoke("run", "evaluate-skill", "--help")
        assert "--format" in result.output, f"--format must appear in help:\n{result.output}"
        assert "--dry-run" in result.output, f"--dry-run must appear in help:\n{result.output}"


# ---------------------------------------------------------------------------
# Tests: M6 — invalid --format values rejected with exit 2
# ---------------------------------------------------------------------------


class TestEvaluateSkillFormatRejected:
    def test_format_csv_rejected_exit_2(self) -> None:
        """M6: --format=csv is not in click.Choice(['rich', 'json']) → exit 2."""
        result = _invoke("run", "evaluate-skill", "any-skill", "--format=csv")
        assert result.exit_code == 2, f"Expected exit 2 for --format=csv, got {result.exit_code}"

    def test_format_md_rejected_exit_2(self) -> None:
        """M6: --format=md is not in click.Choice(['rich', 'json']) → exit 2."""
        result = _invoke("run", "evaluate-skill", "any-skill", "--format=md")
        assert result.exit_code == 2, f"Expected exit 2 for --format=md, got {result.exit_code}"
