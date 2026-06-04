"""Smoke tests — verify the scaffold is wired."""

from __future__ import annotations

import sqlite3

import pytest

import skill_harness
from skill_harness.cli.main import cli
from skill_harness.storage.migrations import discover


def test_package_imports() -> None:
    assert skill_harness.__version__


def test_cli_object_exists() -> None:
    assert cli.name == "cli"


def test_migration_discover_empty_dir(tmp_path) -> None:
    assert discover(tmp_path) == []


def test_evidence_db_creates_tables(evidence_db: sqlite3.Connection) -> None:
    cur = evidence_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
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
    cur = runtime_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
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
    evidence_db.execute(
        "UPDATE runs SET completed_at='2026-06-03T01:00:00Z' WHERE run_id='r1'"
    )
    # Second mutation must abort
    with pytest.raises(sqlite3.IntegrityError, match="completed_at is immutable"):
        evidence_db.execute(
            "UPDATE runs SET completed_at='2026-06-03T02:00:00Z' WHERE run_id='r1'"
        )


def test_runtime_db_is_mutable(runtime_db: sqlite3.Connection) -> None:
    """Runtime tables explicitly DO allow UPDATE/DELETE."""
    runtime_db.execute(
        "INSERT INTO run_progress (run_id, state, samples_planned, last_heartbeat) VALUES (?,?,?,?)",
        ("r1", "pending", 100, "2026-06-03T00:00:00Z"),
    )
    runtime_db.execute("UPDATE run_progress SET state='running' WHERE run_id='r1'")
    cur = runtime_db.execute("SELECT state FROM run_progress WHERE run_id='r1'")
    assert cur.fetchone()[0] == "running"
