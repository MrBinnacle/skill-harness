"""CLI integration tests for `diff skill` (Track E.3, A55).

TDD: written RED first (against the stub), GREEN after implementation.

Exit-code matrix (A58):
  Default: exit 0 if diff ran (semantic success)
  --exit-on-divergence: exit 2 if any clause differs from 'unchanged'
  exit 1 on hard error (precondition fail)

All tests tagged 'not live' — no Anthropic API calls.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

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

SKILL_A = "skill-diff-a"
SKILL_B = "skill-diff-b"
RUN_A = "run-diff-a"
RUN_B = "run-diff-b"
CLAUSE_A = "clause-diff-a"
CLAUSE_B = "clause-diff-b"
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


def _insert_skill(conn: sqlite3.Connection, skill_id: str) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Test Skill', '/path/to/skill.md', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_clause(
    conn: sqlite3.Connection,
    clause_id: str,
    skill_id: str,
    axis: str = AXIS,
    clause_index: int = 0,
    clause_text: str = "Default clause text for testing purposes.",
) -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
        " VALUES (?, ?, ?, ?, ?, ?, 'decrease', 1, 'none')",
        (clause_id, skill_id, clause_index, clause_index, clause_text, axis),
    )


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    skill_id: str,
    clause_id: str,
    completed: bool = True,
    subject_model: str = "claude-sonnet-4-6",
) -> None:
    config = json.dumps(
        {
            "run_id": run_id,
            "skill_id": skill_id,
            "clauses": [{"clause_id": clause_id, "axis": AXIS}],
            "subject_model": subject_model,
            "user_message": "test",
            "family_size": 1,
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
    run_id: str,
    state: str = "completed",
) -> None:
    conn.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, ?, 10, 10, ?)",
        (run_id, state, _TS2),
    )


def _insert_metric_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, ?, ?, 1, 1, 1, ?)",
        (AXIS, "1.0.0", _SHA2, _TS),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    sample_id: str,
    run_id: str,
    clause_id: str,
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
    run_id: str,
    clause_id: str,
    sample_a_id: str,
    sample_b_id: str,
    observation: float = 1.0,
) -> None:
    conn.execute(
        """INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version,
            admissibility_state, written_at
        ) VALUES (?, ?, ?, ?, 'full_vs_ablated', ?, ?, ?, 1, ?, '1.0.0', 'admissible', ?)""",
        (verdict_id, run_id, clause_id, AXIS, sample_a_id, sample_b_id, observation, AXIS, _TS),
    )


def _insert_frozen_case(
    conn: sqlite3.Connection,
    frozen_case_id: str,
    clause_id: str,
    run_id: str,
) -> None:
    failing_text = f"failing-input-{frozen_case_id}"
    conn.execute(
        """INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, metric_id, metric_version, implementation_hash,
            run_id, axis
        ) VALUES (?, ?, ?, ?, 'mechanical', ?, '1.0.0', ?, ?, ?)""",
        (
            frozen_case_id,
            clause_id,
            failing_text,
            sha256_of(failing_text),
            AXIS,
            _SHA2,
            run_id,
            AXIS,
        ),
    )


def _seed_skill_with_passed_clause(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    skill_id: str,
    run_id: str,
    clause_id: str,
    clause_text: str = "Default clause text for testing purposes.",
    n_wins: int = 9,
    subject_model: str = "claude-sonnet-4-6",
) -> None:
    """Seed a skill with enough evidence to produce a PASSED clause + frozen case."""
    _insert_skill(ev, skill_id=skill_id)
    _insert_clause(ev, clause_id=clause_id, skill_id=skill_id, clause_text=clause_text)
    _insert_metric_version(ev)
    _insert_run(
        ev, run_id=run_id, skill_id=skill_id, clause_id=clause_id, subject_model=subject_model
    )
    _insert_run_progress(rt, run_id=run_id, state="completed")
    for i in range(n_wins):
        sa = f"sa-{run_id}-{i}"
        sb = f"sb-{run_id}-{i}"
        _insert_sample(ev, sa, run_id=run_id, clause_id=clause_id, condition="full", sample_index=i)
        _insert_sample(
            ev, sb, run_id=run_id, clause_id=clause_id, condition="ablated", sample_index=i
        )
        _insert_verdict(
            ev,
            verdict_id=f"v-{run_id}-{i}",
            run_id=run_id,
            clause_id=clause_id,
            sample_a_id=sa,
            sample_b_id=sb,
            observation=1.0,
        )
    _insert_frozen_case(ev, frozen_case_id=f"fc-{run_id}", clause_id=clause_id, run_id=run_id)


def _seed_underpowered_skill(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    skill_id: str,
    run_id: str,
    clause_id: str,
    clause_text: str = "Default clause text for testing purposes.",
) -> None:
    """Seed a skill with only 2 verdicts → UNMEASURED."""
    _insert_skill(ev, skill_id=skill_id)
    _insert_clause(ev, clause_id=clause_id, skill_id=skill_id, clause_text=clause_text)
    _insert_metric_version(ev)
    _insert_run(ev, run_id=run_id, skill_id=skill_id, clause_id=clause_id)
    _insert_run_progress(rt, run_id=run_id, state="completed")
    for i in range(2):
        sa = f"sa-{run_id}-{i}"
        sb = f"sb-{run_id}-{i}"
        _insert_sample(ev, sa, run_id=run_id, clause_id=clause_id, condition="full", sample_index=i)
        _insert_sample(
            ev, sb, run_id=run_id, clause_id=clause_id, condition="ablated", sample_index=i
        )
        _insert_verdict(
            ev,
            verdict_id=f"v-{run_id}-{i}",
            run_id=run_id,
            clause_id=clause_id,
            sample_a_id=sa,
            sample_b_id=sb,
            observation=1.0,
        )
    # Instantiated frozen case required for aggregation; underpowered still → UNMEASURED.
    _insert_frozen_case(ev, frozen_case_id=f"fc-under-{run_id}", clause_id=clause_id, run_id=run_id)


# ---------------------------------------------------------------------------
# Tests: Precondition failures
# ---------------------------------------------------------------------------


class TestDiffSkillPreconditions:
    def test_incomplete_run_in_skill_a_exits_1(self, tmp_path: Path) -> None:
        """diff skill fails exit 1 if skill A has an incomplete run."""
        ev, rt = open_both(tmp_path)
        # skill A: incomplete run
        _insert_skill(ev, skill_id=SKILL_A)
        _insert_run(ev, run_id=RUN_A, skill_id=SKILL_A, clause_id=CLAUSE_A, completed=False)
        _insert_run_progress(rt, run_id=RUN_A, state="running")
        # skill B: no runs at all (simpler)
        _insert_skill(ev, skill_id=SKILL_B)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for incomplete run in skill A, "
            f"got {result.exit_code}:\n{result.output}"
        )

    def test_no_runs_in_skill_b_exits_1(self, tmp_path: Path) -> None:
        """diff skill fails exit 1 if skill B has no completed runs."""
        ev, rt = open_both(tmp_path)
        # skill A: complete
        _seed_skill_with_passed_clause(ev, rt, SKILL_A, RUN_A, CLAUSE_A)
        # skill B: no runs
        _insert_skill(ev, skill_id=SKILL_B)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for no runs in skill B, got {result.exit_code}:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: Same skill → all unchanged
# ---------------------------------------------------------------------------


class TestDiffSkillSameSkill:
    def test_diff_same_skill_all_unchanged_exits_0(self, tmp_path: Path) -> None:
        """diff skill A A → all clauses unchanged, exit 0."""
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(ev, rt, SKILL_A, RUN_A, CLAUSE_A)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_A,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0 for diff of same skill, got {result.exit_code}:\n{result.output}"
        )

    def test_diff_same_skill_exit_on_divergence_still_0(self, tmp_path: Path) -> None:
        """diff skill A A --exit-on-divergence → all unchanged, exit 0 (not 2)."""
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(ev, rt, SKILL_A, RUN_A, CLAUSE_A)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_A,
            "--exit-on-divergence",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0 for unchanged diff with --exit-on-divergence, "
            f"got {result.exit_code}:\n{result.output}"
        )
        output = result.output.lower()
        assert "unchanged" in output, f"Expected 'unchanged' in output:\n{result.output}"


# ---------------------------------------------------------------------------
# Tests: Different status → exit-on-divergence
# ---------------------------------------------------------------------------


class TestDiffSkillDivergence:
    def test_different_status_exits_0_without_flag(self, tmp_path: Path) -> None:
        """diff skill A B where statuses differ → exit 0 by default."""
        ev, rt = open_both(tmp_path)
        # A has PASSED clause (same text)
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_A,
            RUN_A,
            CLAUSE_A,
            clause_text="Same clause text so they can match.",
        )
        # B has UNMEASURED clause (same text → same sha256 → aligned)
        _seed_underpowered_skill(
            ev,
            rt,
            SKILL_B,
            RUN_B,
            CLAUSE_B,
            clause_text="Same clause text so they can match.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        # Default: semantic success (diff ran), exit 0
        assert result.exit_code == 0, (
            f"Expected exit 0 for diff without --exit-on-divergence, "
            f"got {result.exit_code}:\n{result.output}"
        )

    def test_different_status_exit_on_divergence_exits_2(self, tmp_path: Path) -> None:
        """diff skill A B --exit-on-divergence where statuses differ → exit 2."""
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_A,
            RUN_A,
            CLAUSE_A,
            clause_text="Same clause text so they can match.",
        )
        _seed_underpowered_skill(
            ev,
            rt,
            SKILL_B,
            RUN_B,
            CLAUSE_B,
            clause_text="Same clause text so they can match.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--exit-on-divergence",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 2, (
            f"Expected exit 2 for divergent diff with --exit-on-divergence, "
            f"got {result.exit_code}:\n{result.output}"
        )

    def test_new_clause_in_b_shows_in_output(self, tmp_path: Path) -> None:
        """When B has a clause not in A (no sha match), output shows 'new'."""
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_A,
            RUN_A,
            CLAUSE_A,
            clause_text="Unique clause text for skill A only.",
        )
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_B,
            RUN_B,
            CLAUSE_B,
            clause_text="Completely different clause text for skill B only.",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
        output = result.output.lower()
        # Should mention new or removed since no matching clauses
        assert "new" in output or "removed" in output, (
            f"Expected 'new' or 'removed' in diff output:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: JSON format
# ---------------------------------------------------------------------------


class TestDiffSkillJsonFormat:
    def test_json_format_produces_parseable_output(self, tmp_path: Path) -> None:
        """--format=json diff output is valid JSON with report_schema_version."""
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(ev, rt, SKILL_A, RUN_A, CLAUSE_A)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_A,
            "--format=json",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
        report = json.loads(result.output)
        assert "report_schema_version" in report
        assert "clauses" in report
        assert report["skill_id_a"] == SKILL_A
        assert report["skill_id_b"] == SKILL_A


# ---------------------------------------------------------------------------
# Tests: help string (acceptance gate)
# ---------------------------------------------------------------------------


class TestDiffSkillHelp:
    def test_help_shows_format_and_exit_on_divergence(self) -> None:
        """--help must document --format and --exit-on-divergence flags."""
        result = _invoke("diff", "skill", "--help")
        assert "--format" in result.output, f"--format must appear in help:\n{result.output}"
        assert "--exit-on-divergence" in result.output, (
            f"--exit-on-divergence must appear in help:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: M6 — invalid --format values rejected with exit 2
# ---------------------------------------------------------------------------


class TestDiffSkillFormatRejected:
    def test_format_csv_rejected_exit_2(self) -> None:
        """M6: --format=csv is not in click.Choice(['rich', 'json']) → exit 2."""
        result = _invoke("diff", "skill", "skill-a", "skill-b", "--format=csv")
        assert result.exit_code == 2, f"Expected exit 2 for --format=csv, got {result.exit_code}"

    def test_format_md_rejected_exit_2(self) -> None:
        """M6: --format=md is not in click.Choice(['rich', 'json']) → exit 2."""
        result = _invoke("diff", "skill", "skill-a", "skill-b", "--format=md")
        assert result.exit_code == 2, f"Expected exit 2 for --format=md, got {result.exit_code}"


# ---------------------------------------------------------------------------
# Tests: C1 — subject_model swap triggers metric_drift
# ---------------------------------------------------------------------------

_CLAUSE_TEXT_C1 = "Clause text for C1 subject_model metric_drift test."
SKILL_C1_A = "skill-c1-sonnet"
SKILL_C1_B = "skill-c1-opus"
RUN_C1_A = "run-c1-sonnet"
RUN_C1_B = "run-c1-opus"
CLAUSE_C1_A = "clause-c1-a"
CLAUSE_C1_B = "clause-c1-b"


class TestDiffSkillSubjectModelMetricDrift:
    def test_diff_skill_subject_model_swap_marks_metric_drift(self, tmp_path: Path) -> None:
        """C1 falsifying test: skill A (sonnet) vs skill B (opus) → metric_drift.

        A55 mandates metric_drift triggers on ANY of four axes. subject_model is
        one of those axes. Two otherwise-identical skills that differ only in
        subject_model must be flagged as metric_drift (not regressed/improved).

        Was RED against the pre-fix code (subject_model not checked).
        Must be GREEN after C1 fix (subject_model threaded through ClauseReport
        and checked in diff_skill).
        """
        ev, rt = open_both(tmp_path)
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_C1_A,
            RUN_C1_A,
            CLAUSE_C1_A,
            clause_text=_CLAUSE_TEXT_C1,
            n_wins=30,
            subject_model="claude-sonnet-4-6",
        )
        _seed_skill_with_passed_clause(
            ev,
            rt,
            SKILL_C1_B,
            RUN_C1_B,
            CLAUSE_C1_B,
            clause_text=_CLAUSE_TEXT_C1,
            n_wins=30,
            subject_model="claude-opus-4-7",
        )
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_C1_A,
            SKILL_C1_B,
            "--format=json",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
        diff = json.loads(result.output)
        assert "clauses" in diff
        assert len(diff["clauses"]) > 0, "Expected at least one clause diff"

        clause_diff = diff["clauses"][0]
        assert clause_diff["delta"] == "metric_drift", (
            f"Expected delta='metric_drift' when subject_model differs, "
            f"got {clause_diff['delta']!r}. "
            "subject_model is a required A55 comparability axis (C1 fix)."
        )
        assert "metric_drift_reason" in clause_diff
        assert clause_diff["metric_drift_reason"] is not None
        assert "subject_model" in clause_diff["metric_drift_reason"], (
            f"Expected 'subject_model' in metric_drift_reason, got "
            f"{clause_diff['metric_drift_reason']!r}"
        )


# ---------------------------------------------------------------------------
# Tests: T9 zero-axis alignment pinning
# ---------------------------------------------------------------------------


def _seed_no_verdict_skill(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    skill_id: str,
    run_id: str,
    clause_id: str,
    clause_text: str = "Clause with no verdicts for alignment test.",
) -> None:
    """Seed a skill with a run but NO verdicts → UNMEASURED(no_data), metric_id_per_axis={}."""
    _insert_skill(ev, skill_id=skill_id)
    _insert_clause(ev, clause_id=clause_id, skill_id=skill_id, clause_text=clause_text)
    _insert_metric_version(ev)
    _insert_run(ev, run_id=run_id, skill_id=skill_id, clause_id=clause_id)
    _insert_run_progress(rt, run_id=run_id, state="completed")
    # No samples or verdicts inserted → clause has no admissible data
    # Instantiated frozen case required for aggregation precondition.
    _insert_frozen_case(ev, frozen_case_id=f"fc-nov-{run_id}", clause_id=clause_id, run_id=run_id)


class TestDiffSkillZeroAxisAlignment:
    def test_zero_verdict_clause_uses_empty_axis_key(self, tmp_path: Path) -> None:
        """T9: clause with no admissible verdicts → axis_key='' and delta='unchanged'.

        When metric_id_per_axis == {} (no verdicts), the alignment key defaults to "".
        Two skills with an identical zero-verdict clause must align as "unchanged".
        This pins the v0.2 limitation documented at cli/main.py:1269.
        """
        ev, rt = open_both(tmp_path)
        clause_text = "Zero-verdict clause text for alignment pinning test."
        _seed_no_verdict_skill(ev, rt, SKILL_A, RUN_A, CLAUSE_A, clause_text=clause_text)
        _seed_no_verdict_skill(ev, rt, SKILL_B, RUN_B, CLAUSE_B, clause_text=clause_text)
        ev.close()
        rt.close()

        result = _invoke(
            "diff",
            "skill",
            SKILL_A,
            SKILL_B,
            "--format=json",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}:\n{result.output}"
        diff = json.loads(result.output)
        assert "clauses" in diff
        assert len(diff["clauses"]) > 0, "Expected at least one clause diff"

        for clause_diff in diff["clauses"]:
            assert clause_diff["axis"] == "", (
                f"Expected axis_key='' for zero-verdict clause, got {clause_diff['axis']!r}"
            )
            assert clause_diff["delta"] == "unchanged", (
                f"Expected delta='unchanged' for matching zero-verdict clauses, "
                f"got {clause_diff['delta']!r}"
            )
