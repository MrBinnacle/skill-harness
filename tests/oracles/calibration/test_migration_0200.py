"""Tests for migration 0200_calibration_event_extensions.sql (A37).

Verifies:
- Migration 0200 applies cleanly to a fresh DB (no errors).
- calibration_events table has all 10 new columns after migration.
- Existing append-only triggers still fire for calibration_events after migration.
- The migration is discoverable by discover() without duplicate-version error.
- Column defaults are NULL (not zero) for all 10 new columns.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_evidence_with_migrations(tmp_path: Path) -> sqlite3.Connection:
    """Open a fresh evidence DB with all migrations applied."""
    from skill_harness.storage.migrations import (
        EVIDENCE_MIGRATIONS_DIR,
        apply_pending,
        discover,
        open_db,
    )

    conn = open_db(str(tmp_path / "evidence.db"), synchronous="FULL")
    migrations = discover(EVIDENCE_MIGRATIONS_DIR)
    apply_pending(conn, migrations)
    return conn


def _get_column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Migration discovery (no duplicate-version error)
# ---------------------------------------------------------------------------


def test_migration_0200_discovered_without_error(tmp_path: Path) -> None:
    """discover() must return migrations including 0200 without raising."""
    from skill_harness.storage.migrations import EVIDENCE_MIGRATIONS_DIR, discover

    migrations = discover(EVIDENCE_MIGRATIONS_DIR)
    versions = [m.version for m in migrations]
    assert 200 in versions, f"Migration 0200 not found. Found versions: {versions}"


# ---------------------------------------------------------------------------
# Migration applies cleanly
# ---------------------------------------------------------------------------


def test_migration_0200_applies_cleanly(tmp_path: Path) -> None:
    """A fresh DB must have migration 0200 applied without error."""
    conn = _open_evidence_with_migrations(tmp_path)
    # Verify schema_migrations records 0200
    cur = conn.execute("SELECT migration_id FROM schema_migrations WHERE migration_id LIKE '0200%'")
    rows = cur.fetchall()
    assert len(rows) == 1, f"Expected 1 row for 0200_*, found: {rows}"
    conn.close()


# ---------------------------------------------------------------------------
# All 10 new columns present
# ---------------------------------------------------------------------------


def test_calibration_events_has_10_new_columns(tmp_path: Path) -> None:
    """After migration 0200, calibration_events must have all 10 A37 columns."""
    conn = _open_evidence_with_migrations(tmp_path)
    cols = _get_column_names(conn, "calibration_events")
    required = [
        "n_a",
        "n_b",
        "n_tie",
        "judge_n_a",
        "judge_n_b",
        "judge_n_tie",
        "length_regression_coefficient",
        "chance_baseline",
        "total_usd_spent",
        "cost_ledger_run_id",
    ]
    for col in required:
        assert col in cols, f"Column '{col}' missing from calibration_events. Got: {cols}"
    conn.close()


# ---------------------------------------------------------------------------
# Column defaults are NULL
# ---------------------------------------------------------------------------


def test_new_columns_default_to_null(tmp_path: Path) -> None:
    """All 10 new columns must default to NULL (not 0 or empty string)."""
    conn = _open_evidence_with_migrations(tmp_path)

    # Insert a judge and a minimal calibration event
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        INSERT INTO judges (judge_id, model_id, system_prompt_sha256)
        VALUES ('j1', 'claude-sonnet-4-6', 'abc123')
        """
    )
    conn.execute(
        """
        INSERT INTO calibration_events (
            calibration_event_id, judge_id, axis,
            pairwise_agreement, position_consistency,
            pair_set_size, pair_set_sha256, state, validated_at
        ) VALUES (
            'evt1', 'j1', 'clarity', 0.75, 0.85, 100,
            'sha256abc', 'calibrated', '2026-01-01T00:00:00Z'
        )
        """
    )
    conn.execute("COMMIT")

    cur = conn.execute(
        """
        SELECT n_a, n_b, n_tie, judge_n_a, judge_n_b, judge_n_tie,
               length_regression_coefficient, chance_baseline,
               total_usd_spent, cost_ledger_run_id
        FROM calibration_events WHERE calibration_event_id = 'evt1'
        """
    )
    row = cur.fetchone()
    assert row is not None
    for i, val in enumerate(row):
        assert val is None, f"Column index {i} should be NULL but got {val!r}"
    conn.close()


# ---------------------------------------------------------------------------
# Append-only trigger preserved after migration
# ---------------------------------------------------------------------------


def test_calibration_events_update_still_raises_after_migration(tmp_path: Path) -> None:
    """The BEFORE UPDATE trigger on calibration_events must still fire post-migration."""
    conn = _open_evidence_with_migrations(tmp_path)

    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """
        INSERT INTO judges (judge_id, model_id, system_prompt_sha256)
        VALUES ('j2', 'claude-sonnet-4-6', 'def456')
        """
    )
    conn.execute(
        """
        INSERT INTO calibration_events (
            calibration_event_id, judge_id, axis,
            pairwise_agreement, position_consistency,
            pair_set_size, pair_set_sha256, state, validated_at
        ) VALUES (
            'evt2', 'j2', 'clarity', 0.75, 0.85, 100,
            'sha256def', 'calibrated', '2026-01-01T00:00:00Z'
        )
        """
    )
    conn.execute("COMMIT")

    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
        conn.execute("UPDATE calibration_events SET axis='other' WHERE calibration_event_id='evt2'")
    conn.close()


def test_calibration_events_delete_still_raises_after_migration(tmp_path: Path) -> None:
    """The BEFORE DELETE trigger on calibration_events must still fire post-migration."""
    conn = _open_evidence_with_migrations(tmp_path)

    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO judges (judge_id, model_id, system_prompt_sha256) VALUES ('j3', 'm', 'x')"
    )
    conn.execute(
        """
        INSERT INTO calibration_events (
            calibration_event_id, judge_id, axis,
            pairwise_agreement, position_consistency,
            pair_set_size, pair_set_sha256, state, validated_at
        ) VALUES ('evt3', 'j3', 'clarity', 0.75, 0.85, 100, 'sha', 'calibrated', '2026-01-01')
        """
    )
    conn.execute("COMMIT")

    with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
        conn.execute("DELETE FROM calibration_events WHERE calibration_event_id='evt3'")
    conn.close()
