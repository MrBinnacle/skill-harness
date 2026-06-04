"""Smoke tests — verify the scaffold is wired."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import skill_harness
from skill_harness.cli.main import cli
from skill_harness.storage import migrations as migrations_module
from skill_harness.storage.errors import BootstrapError, MigrationApplyError
from skill_harness.storage.migrations import (
    discover,
    open_evidence,
    open_runtime,
)


def test_package_imports() -> None:
    assert skill_harness.__version__


def test_cli_object_exists() -> None:
    assert cli.name == "cli"


def test_migration_discover_empty_dir(tmp_path) -> None:
    assert discover(tmp_path) == []


def test_evidence_db_creates_tables(evidence_db: sqlite3.Connection) -> None:
    cur = evidence_db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "schema_migrations",
        "skills",
        "clauses",
        "metric_versions",
        "judges",
        "calibration_events",
        "runs",
        "samples",
        "oracle_verdicts",
        "confound_events",
        "frozen_cases",
    }
    assert expected <= tables, f"missing: {expected - tables}"


def test_runtime_db_creates_tables(runtime_db: sqlite3.Connection) -> None:
    cur = runtime_db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "schema_migrations",
        "run_progress",
        "current_calibration",
        "skill_imports_staging",
        "run_budget",
        "cost_ledger",
    }
    assert expected <= tables, f"missing: {expected - tables}"


def test_evidence_append_only_skills(evidence_db: sqlite3.Connection) -> None:
    """SCHEMA-F1: UPDATE/DELETE on evidence tables must RAISE(ABORT)."""
    evidence_db.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
        ("sk_test", "test-skill", "/tmp/test.md", "deadbeef" * 8),
    )
    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: skills"):
        evidence_db.execute("UPDATE skills SET name='renamed' WHERE skill_id='sk_test'")
    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation: skills"):
        evidence_db.execute("DELETE FROM skills WHERE skill_id='sk_test'")


def test_runs_completed_at_is_set_once(evidence_db: sqlite3.Connection) -> None:
    evidence_db.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
        ("sk_x", "x", "/tmp/x.md", "a" * 64),
    )
    evidence_db.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) VALUES (?,?,?,?,?)",
        ("r1", "sk_x", "ablation", "{}", "2026-06-03T00:00:00Z"),
    )
    # First completion is allowed
    evidence_db.execute("UPDATE runs SET completed_at='2026-06-03T01:00:00Z' WHERE run_id='r1'")
    # Second mutation must abort
    with pytest.raises(sqlite3.IntegrityError, match="completed_at is immutable"):
        evidence_db.execute("UPDATE runs SET completed_at='2026-06-03T02:00:00Z' WHERE run_id='r1'")


def test_runtime_db_is_mutable(runtime_db: sqlite3.Connection) -> None:
    """Runtime tables explicitly DO allow UPDATE/DELETE."""
    runtime_db.execute(
        "INSERT INTO run_progress "
        "(run_id, state, samples_planned, last_heartbeat) "
        "VALUES (?,?,?,?)",
        ("r1", "pending", 100, "2026-06-03T00:00:00Z"),
    )
    runtime_db.execute("UPDATE run_progress SET state='running' WHERE run_id='r1'")
    cur = runtime_db.execute("SELECT state FROM run_progress WHERE run_id='r1'")
    assert cur.fetchone()[0] == "running"


# -------- Phase 1.5a council fixes ----------------------------------------


def test_open_evidence_raises_bootstrap_error_on_no_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A19 / RELIABILITY-F2: silently opening an evidence DB with zero
    migrations would skip every append-only trigger and let writes succeed
    that should abort. open_evidence must raise BootstrapError instead."""
    empty_migrations_dir = tmp_path / "no_migrations"
    empty_migrations_dir.mkdir()
    monkeypatch.setattr(migrations_module, "EVIDENCE_MIGRATIONS_DIR", empty_migrations_dir)
    with pytest.raises(BootstrapError, match="no evidence migrations discovered"):
        open_evidence(tmp_path / "evidence.db")


def test_open_runtime_raises_bootstrap_error_on_no_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A19 symmetry on the runtime side."""
    empty_migrations_dir = tmp_path / "no_migrations"
    empty_migrations_dir.mkdir()
    monkeypatch.setattr(migrations_module, "RUNTIME_MIGRATIONS_DIR", empty_migrations_dir)
    with pytest.raises(BootstrapError, match="no runtime migrations discovered"):
        open_runtime(tmp_path / "runtime.db")


def test_evidence_uses_synchronous_full(evidence_db: sqlite3.Connection) -> None:
    """A22 / RELIABILITY-F5: evidence must run at synchronous=FULL so
    committed audit rows survive power loss. SQLite returns 2 for FULL."""
    value = evidence_db.execute("PRAGMA synchronous").fetchone()[0]
    assert value == 2, f"expected synchronous=FULL (2), got {value}"


def test_runtime_uses_synchronous_normal(runtime_db: sqlite3.Connection) -> None:
    """A22: runtime keeps synchronous=NORMAL (returns 1) — its state can be
    re-derived from evidence after a crash, so the throughput tradeoff is
    appropriate."""
    value = runtime_db.execute("PRAGMA synchronous").fetchone()[0]
    assert value == 1, f"expected synchronous=NORMAL (1), got {value}"


def test_runs_immutable_columns_raise_on_update(
    evidence_db: sqlite3.Connection,
) -> None:
    """A20 / SCHEMA-F3: the new column-scoped runs_immutable_columns trigger
    must abort UPDATEs to skill_id, run_kind, config_json, or started_at —
    even before the run completes (no completed_at guard)."""
    evidence_db.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
        ("sk_a", "a", "/tmp/a.md", "a" * 64),
    )
    evidence_db.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256) VALUES (?,?,?,?)",
        ("sk_b", "b", "/tmp/b.md", "b" * 64),
    )
    evidence_db.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at) VALUES (?,?,?,?,?)",
        ("r_immut", "sk_a", "ablation", "{}", "2026-06-04T00:00:00Z"),
    )
    with pytest.raises(
        sqlite3.IntegrityError,
        match="append_only_violation: runs",
    ):
        evidence_db.execute("UPDATE runs SET skill_id='sk_b' WHERE run_id='r_immut'")
    with pytest.raises(
        sqlite3.IntegrityError,
        match="append_only_violation: runs",
    ):
        evidence_db.execute(
            "UPDATE runs SET started_at='2099-01-01T00:00:00Z' WHERE run_id='r_immut'"
        )


def test_runtime_schema_migrations_append_only(
    runtime_db: sqlite3.Connection,
) -> None:
    """A21: runtime.schema_migrations is the tamper-evidence ledger; UPDATE
    and DELETE on it must abort, mirroring the evidence side. Without this,
    a rollback could erase its own footprint and the SHA-256 verification
    on next open would have nothing to check against."""
    with pytest.raises(
        sqlite3.IntegrityError,
        match="append_only_violation: schema_migrations",
    ):
        runtime_db.execute(
            "UPDATE schema_migrations SET file_sha256='deadbeef' WHERE migration_id='0001_initial'"
        )
    with pytest.raises(
        sqlite3.IntegrityError,
        match="append_only_violation: schema_migrations",
    ):
        runtime_db.execute("DELETE FROM schema_migrations WHERE migration_id='0001_initial'")


def test_migration_apply_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A18 / RELIABILITY-F1: a mid-apply failure must roll back the schema
    AND leave no schema_migrations row. Prior implementation used
    executescript inside `with conn:` in autocommit mode, which did not
    bracket the apply + ledger-INSERT atomically; a crash between them left
    the schema applied but unrecorded — the ledger then lied on next open."""
    bad_migrations_dir = tmp_path / "bad_migrations"
    bad_migrations_dir.mkdir()
    # First migration creates schema_migrations (so we have somewhere to read).
    (bad_migrations_dir / "0001_init.sql").write_text(
        "CREATE TABLE schema_migrations (migration_id TEXT PRIMARY KEY, file_sha256 TEXT NOT NULL);"
    )
    # Second migration creates a table then references a column that does not
    # exist — the CREATE INDEX fails after the CREATE TABLE has succeeded.
    (bad_migrations_dir / "0002_bad.sql").write_text(
        "CREATE TABLE thing (id INTEGER PRIMARY KEY);\n"
        "CREATE INDEX idx_thing_missing ON thing (no_such_column);\n"
    )
    monkeypatch.setattr(migrations_module, "RUNTIME_MIGRATIONS_DIR", bad_migrations_dir)
    with pytest.raises(MigrationApplyError, match="0002_bad"):
        open_runtime(tmp_path / "runtime.db")
    # Reopen with a working migrations dir pointing at the same DB file: the
    # ledger should contain only 0001_init (proving 0002_bad was rolled back),
    # and the `thing` table should not exist.
    conn = sqlite3.connect(str(tmp_path / "runtime.db"))
    try:
        ledger = {
            row[0] for row in conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
        }
        assert ledger == {"0001_init"}, f"ledger leaked partial apply: {ledger}"
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "thing" not in tables, "rolled-back table survived rollback"
    finally:
        conn.close()


def test_split_statements_preserves_trigger_bodies() -> None:
    """A18 implementation detail: the per-statement splitter must not shatter
    trigger BEGIN ... END bodies on their embedded semicolons. A naive
    str.split(';') would corrupt every append-only trigger in 0001_initial.sql."""
    sql = (
        "CREATE TABLE t (x INTEGER);\n"
        "CREATE TRIGGER t_no_update BEFORE UPDATE ON t "
        "BEGIN SELECT RAISE(ABORT, 'nope'); END;\n"
    )
    stmts = migrations_module._split_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].startswith("CREATE TABLE")
    assert "RAISE(ABORT" in stmts[1] and stmts[1].rstrip().endswith("END;")
