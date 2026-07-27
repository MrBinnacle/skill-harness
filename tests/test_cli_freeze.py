"""CLI integration tests for `freeze <verdict_id>` (Track E.3, A56).

TDD: written RED first (against the stub), GREEN after implementation.

Exit-code matrix (A58 / A56):
  0 = frozen or already frozen (idempotent)
  1 = validation refused (ineligibility, missing verdict, incomplete parent)

Signature fix: arg is <verdict_id>, NOT <sample_id>.

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
_SKILL_ID = "skill-freeze-001"
_CLAUSE_ID = "clause-freeze-001"
_RUN_ID = "run-freeze-001"
_VERDICT_ID = "verdict-freeze-001"
_AXIS = "verbosity"


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


def _seed_base(ev: sqlite3.Connection) -> None:
    """Seed skill, clause, metric_version."""
    ev.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Test', '/test.md', ?, ?)",
        (_SKILL_ID, _SHA, _TS),
    )
    ev.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
        " VALUES (?, ?, 0, 0, 'Clause text.', ?, 'decrease', 1, 'none')",
        (_CLAUSE_ID, _SKILL_ID, _AXIS),
    )
    ev.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, '1.0.0', ?, 1, 1, 1, ?)",
        (_AXIS, _SHA2, _TS),
    )


def _insert_run(
    ev: sqlite3.Connection,
    run_id: str = _RUN_ID,
    completed: bool = True,
) -> None:
    completed_at = _TS2 if completed else None
    config = json.dumps({"skill_id": _SKILL_ID, "run_id": run_id, "family_size": 1})
    ev.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (run_id, _SKILL_ID, config, _TS, completed_at),
    )


def _insert_samples(ev: sqlite3.Connection, sa_id: str, sb_id: str, run_id: str = _RUN_ID) -> None:
    for sample_id, condition in [(sa_id, "full"), (sb_id, "ablated")]:
        output_text = f"Sample output for {sample_id}"
        ev.execute(
            "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
            " subject_model, output_text, output_sha256, sampled_at, sample_index)"
            " VALUES (?, ?, ?, ?, 'claude-sonnet-4-6', ?, ?, ?, 0)",
            (
                sample_id,
                run_id,
                _CLAUSE_ID,
                condition,
                output_text,
                sha256_of(output_text),
                _TS,
            ),
        )


def _insert_verdict(
    ev: sqlite3.Connection,
    verdict_id: str = _VERDICT_ID,
    run_id: str = _RUN_ID,
    sa_id: str = "sa-001",
    sb_id: str = "sb-001",
    observation: float = 0.0,  # FAILING side by default
    admissibility_state: str = "admissible",
) -> None:
    ev.execute(
        """INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version,
            admissibility_state, written_at
        ) VALUES (?, ?, ?, ?, 'full_vs_ablated', ?, ?, ?, 1, ?, '1.0.0', ?, ?)""",
        (
            verdict_id,
            run_id,
            _CLAUSE_ID,
            _AXIS,
            sa_id,
            sb_id,
            observation,
            _AXIS,
            admissibility_state,
            _TS,
        ),
    )


def _seed_freezable_verdict(
    ev: sqlite3.Connection,
    verdict_id: str = _VERDICT_ID,
    run_id: str = _RUN_ID,
    observation: float = 0.0,  # FAILING
    admissibility_state: str = "admissible",
    run_completed: bool = True,
) -> None:
    """Seed a complete eligible verdict (failing, admissible, complete run)."""
    _seed_base(ev)
    _insert_run(ev, run_id=run_id, completed=run_completed)
    _insert_samples(ev, sa_id="sa-001", sb_id="sb-001", run_id=run_id)
    _insert_verdict(
        ev,
        verdict_id=verdict_id,
        run_id=run_id,
        sa_id="sa-001",
        sb_id="sb-001",
        observation=observation,
        admissibility_state=admissibility_state,
    )


# ---------------------------------------------------------------------------
# Tests: Signature fix — verdict_id not sample_id
# ---------------------------------------------------------------------------


class TestFreezeSignature:
    def test_help_shows_verdict_id_not_sample_id(self) -> None:
        """freeze --help must show <verdict_id> (NOT <sample_id>)."""
        result = _invoke("freeze", "--help")
        assert "verdict_id" in result.output.lower(), (
            f"'verdict_id' must appear in help output:\n{result.output}"
        )
        assert "sample_id" not in result.output.lower(), (
            f"'sample_id' must NOT appear in help output (signature fix A56):\n{result.output}"
        )

    def test_help_shows_execute_flag(self) -> None:
        """freeze --help must document --execute flag."""
        result = _invoke("freeze", "--help")
        assert "--execute" in result.output, f"--execute must appear in help:\n{result.output}"

    def test_help_shows_oracle_source_flag(self) -> None:
        """freeze --help must document --oracle-source flag."""
        result = _invoke("freeze", "--help")
        assert "--oracle-source" in result.output, (
            f"--oracle-source must appear in help:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: Dry-run (default) — no DB write
# ---------------------------------------------------------------------------


class TestFreezeDryRun:
    def test_dry_run_prints_would_freeze_and_exits_0(self, tmp_path: Path) -> None:
        """freeze <verdict_id> (no --execute) → dry-run output, no write, exit 0."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0 for dry-run, got {result.exit_code}:\n{result.output}"
        )
        output = result.output.upper()
        assert "WOULD" in output or "DRY" in output, (
            f"Dry-run must print WOULD or DRY in output:\n{result.output}"
        )
        assert _VERDICT_ID in result.output, f"Dry-run must name the verdict_id:\n{result.output}"

    def test_dry_run_does_not_write_to_db(self, tmp_path: Path) -> None:
        """freeze <verdict_id> (no --execute) must NOT write to frozen_cases."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        _invoke(
            "freeze",
            _VERDICT_ID,
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        ev_check = open_evidence(tmp_path / "evidence.db")
        try:
            rows = ev_check.execute("SELECT frozen_case_id FROM frozen_cases").fetchall()
            assert rows == [], f"Dry-run must NOT write to frozen_cases; found rows: {rows}"
        finally:
            ev_check.close()

    def test_dry_run_missing_verdict_exits_1(self, tmp_path: Path) -> None:
        """freeze nonexistent-verdict (no --execute) → exit 1, clear error."""
        ev, rt = open_both(tmp_path)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            "nonexistent-verdict-id",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for missing verdict, got {result.exit_code}:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: Execute path — actual write
# ---------------------------------------------------------------------------


class TestFreezeExecute:
    def test_execute_writes_frozen_case(self, tmp_path: Path) -> None:
        """freeze <verdict_id> --execute writes a row to frozen_cases and exits 0."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0 after --execute, got {result.exit_code}:\n{result.output}"
        )

        ev_check = open_evidence(tmp_path / "evidence.db")
        try:
            rows = ev_check.execute(
                "SELECT frozen_case_id FROM frozen_cases WHERE verdict_id = ?",
                (_VERDICT_ID,),
            ).fetchall()
            assert len(rows) == 1, f"Expected 1 frozen_case row, found {len(rows)}"
        finally:
            ev_check.close()

    def test_execute_prints_frozen_case_id(self, tmp_path: Path) -> None:
        """freeze --execute must print the new frozen_case_id in output."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        # Output must mention a frozen_case_id (some UUID-like string)
        assert "frozen" in result.output.lower(), f"Output must mention 'frozen':\n{result.output}"

    def test_double_freeze_idempotent_exits_0(self, tmp_path: Path) -> None:
        """freeze <verdict_id> --execute a second time → already frozen, exit 0 (idempotent A48)."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        # First freeze
        r1 = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )
        assert r1.exit_code == 0, f"First freeze failed:\n{r1.output}"

        # Second freeze — must be idempotent
        r2 = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )
        assert r2.exit_code == 0, (
            f"Second freeze must exit 0 (idempotent), got {r2.exit_code}:\n{r2.output}"
        )
        assert "already frozen" in r2.output.lower(), (
            f"Second freeze must say 'already frozen':\n{r2.output}"
        )


# ---------------------------------------------------------------------------
# Tests: Eligibility refusals → exit 1
# ---------------------------------------------------------------------------


class TestFreezeEligibilityRefusals:
    def test_passing_verdict_observation_1_exits_1(self, tmp_path: Path) -> None:
        """Verdict with observation=1.0 (PASSING side) cannot be frozen → exit 1."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev, observation=1.0)  # PASSING side
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for passing verdict (obs=1.0), "
            f"got {result.exit_code}:\n{result.output}"
        )

    def test_inadmissible_verdict_exits_1(self, tmp_path: Path) -> None:
        """Inadmissible verdict cannot be frozen → exit 1."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev, admissibility_state="inadmissible")
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for inadmissible verdict, got {result.exit_code}:\n{result.output}"
        )

    def test_incomplete_parent_run_exits_1(self, tmp_path: Path) -> None:
        """Verdict whose parent run is incomplete (completed_at IS NULL) → exit 1."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev, run_completed=False)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for incomplete parent run, got {result.exit_code}:\n{result.output}"
        )

    def test_missing_verdict_id_execute_exits_1(self, tmp_path: Path) -> None:
        """freeze nonexistent-verdict-id --execute → exit 1, clear error."""
        ev, rt = open_both(tmp_path)
        ev.close()
        rt.close()

        result = _invoke(
            "freeze",
            "nonexistent-verdict-id",
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )

        assert result.exit_code == 1, (
            f"Expected exit 1 for missing verdict_id, got {result.exit_code}:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# Tests: I4 — dry-run opens evidence DB read-only (least-privilege)
# ---------------------------------------------------------------------------


class TestFreezeDryRunOpensReadonly:
    """I4: freeze dry-run must open evidence DB read-only, not writable.

    Strategy: mock-based assertion (Windows chmod does not reliably deny
    sqlite3 write access on NTFS). Patches open_evidence (writable) to raise
    PermissionError — dry-run must succeed (fixed code uses open_evidence_readonly);
    --execute must use the writable variant.
    """

    def test_dry_run_succeeds_when_writable_open_would_raise(self, tmp_path: Path) -> None:
        """I4: freeze dry-run must NOT call open_evidence (writable).

        If dry-run calls open_evidence and it raises PermissionError, the
        command exits non-zero (RED on current code). After the fix, dry-run
        calls open_evidence_readonly and the PermissionError is never triggered.
        """
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        # Patch open_evidence at the migrations module level.
        # Local imports inside freeze command draw from this module.
        # Current code (pre-fix): calls open_evidence → PermissionError → exit 1.
        # Fixed code: calls open_evidence_readonly → succeeds → exit 0.
        with patch(
            "skill_harness.storage.migrations.open_evidence",
            side_effect=PermissionError("simulated: DB is read-only"),
        ):
            result = _invoke(
                "freeze",
                _VERDICT_ID,
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        assert result.exit_code == 0, (
            "freeze dry-run must succeed even when open_evidence (writable) raises; "
            "fixed code should call open_evidence_readonly instead. "
            f"Got exit_code={result.exit_code}:\n{result.output}"
        )

    def test_execute_calls_open_evidence_writable(self, tmp_path: Path) -> None:
        """I4 complement: freeze --execute must call open_evidence (writable)."""
        ev, rt = open_both(tmp_path)
        _seed_freezable_verdict(ev)
        ev.close()
        rt.close()

        writable_calls: list[Any] = []
        from skill_harness.storage.migrations import open_evidence as _real_oe

        def tracking_open_evidence(path: Any) -> Any:
            writable_calls.append(path)
            return _real_oe(path)

        with patch("skill_harness.storage.migrations.open_evidence", tracking_open_evidence):
            result = _invoke(
                "freeze",
                _VERDICT_ID,
                "--execute",
                "--evidence-db",
                str(tmp_path / "evidence.db"),
                "--runtime-db",
                str(tmp_path / "runtime.db"),
            )

        assert result.exit_code == 0, (
            f"Execute must exit 0, got {result.exit_code}:\n{result.output}"
        )
        assert len(writable_calls) >= 1, (
            "freeze --execute must call open_evidence (writable) at least once; "
            f"recorded calls: {writable_calls}"
        )


# ---------------------------------------------------------------------------
# Tests: Paired-path (full_vs_null) eligibility — A-prime (S86 council record)
# ---------------------------------------------------------------------------

_BINARY_METRIC = "subject:file_contains"


def _seed_paired_verdict(
    ev: sqlite3.Connection,
    verdict_id: str = _VERDICT_ID,
    observation: float = 1.0,
    metric_id: str = _BINARY_METRIC,
) -> None:
    """Seed a paired (full_vs_null) verdict with a binary subject metric."""
    _seed_base(ev)
    ev.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, '0.2.0', ?, 1, 1, 1, ?)",
        (metric_id, _SHA2, _TS),
    )
    config = json.dumps({"contrast": "full_vs_null"})
    ev.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'evaluate_skill', ?, ?, ?)",
        (_RUN_ID, _SKILL_ID, config, _TS, _TS2),
    )
    for sample_id, condition in [("sa-p-001", "full"), ("sb-p-001", "null")]:
        output_text = f"Sample output for {sample_id}"
        ev.execute(
            "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
            " subject_model, output_text, output_sha256, sampled_at, sample_index)"
            " VALUES (?, ?, ?, ?, 'claude-sonnet-4-6', ?, ?, ?, 0)",
            (sample_id, _RUN_ID, _CLAUSE_ID, condition, output_text, sha256_of(output_text), _TS),
        )
    ev.execute(
        """INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version,
            admissibility_state, written_at
        ) VALUES (?, ?, ?, 'outcome', 'full_vs_null',
            'sa-p-001', 'sb-p-001', ?, 1, ?, '0.2.0', 'admissible', ?)""",
        (verdict_id, _RUN_ID, _CLAUSE_ID, observation, metric_id, _TS),
    )


class TestFreezePairedPath:
    def test_paired_winning_verdict_freezes_exit_0(self, tmp_path: Path) -> None:
        """A-prime: paired obs=1.0 under a registered-binary metric freezes."""
        ev, rt = open_both(tmp_path)
        _seed_paired_verdict(ev, observation=1.0)
        ev.close()
        rt.close()
        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )
        assert result.exit_code == 0, f"got {result.exit_code}:\n{result.output}"
        ev = open_evidence(tmp_path / "evidence.db")
        row = ev.execute(
            "SELECT failing_input_text FROM frozen_cases WHERE verdict_id = ?", (_VERDICT_ID,)
        ).fetchone()
        ev.close()
        assert row is not None
        assert row[0] == "Sample output for sb-p-001"  # the Null-arm sample

    def test_paired_tie_refused_exit_1(self, tmp_path: Path) -> None:
        """A-prime: paired obs=0.5 may be a both-PASS tie — refused."""
        ev, rt = open_both(tmp_path)
        _seed_paired_verdict(ev, observation=0.5)
        ev.close()
        rt.close()
        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )
        assert result.exit_code == 1, f"got {result.exit_code}:\n{result.output}"
        assert "1.0" in result.output

    def test_paired_nonbinary_metric_refused_exit_1(self, tmp_path: Path) -> None:
        """A-prime: paired obs=1.0 under an unregistered (graded) metric — refused."""
        ev, rt = open_both(tmp_path)
        _seed_paired_verdict(ev, observation=1.0, metric_id="subject:graded_rubric")
        ev.close()
        rt.close()
        result = _invoke(
            "freeze",
            _VERDICT_ID,
            "--execute",
            "--evidence-db",
            str(tmp_path / "evidence.db"),
            "--runtime-db",
            str(tmp_path / "runtime.db"),
        )
        assert result.exit_code == 1, f"got {result.exit_code}:\n{result.output}"
        assert "binary" in result.output
