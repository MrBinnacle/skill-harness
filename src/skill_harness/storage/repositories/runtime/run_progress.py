"""Repository functions for runtime.run_progress (mutable).

Columns (from migrations/runtime/0001_initial.sql):
    run_id            TEXT PRIMARY KEY
    state             TEXT NOT NULL CHECK (pending|running|draining|completed|failed|aborted_budget)
    samples_planned   INTEGER NOT NULL
    samples_collected INTEGER NOT NULL DEFAULT 0
    last_heartbeat    TEXT NOT NULL
    error             TEXT  (nullable)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import RunProgressWrite


def insert_run_progress(conn: sqlite3.Connection, progress: RunProgressWrite) -> None:
    """Insert a new run_progress row."""
    conn.execute(
        """
        INSERT INTO run_progress
            (run_id, state, samples_planned, samples_collected, last_heartbeat, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            progress.run_id,
            progress.state,
            progress.samples_planned,
            progress.samples_collected,
            progress.last_heartbeat,
            progress.error,
        ),
    )


def get_run_progress_by_id(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Return the run_progress row as a dict, or None if not found."""
    cur = conn.execute(
        "SELECT run_id, state, samples_planned, samples_collected, last_heartbeat, error"
        " FROM run_progress WHERE run_id = ?",
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_run_progresses_by_state(conn: sqlite3.Connection, state: str) -> list[dict[str, Any]]:
    """Return all run_progress rows in a given state."""
    cur = conn.execute(
        "SELECT run_id, state, samples_planned, samples_collected, last_heartbeat, error"
        " FROM run_progress WHERE state = ?",
        (state,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def update_run_progress(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    state: str,
    samples_collected: int,
    last_heartbeat: str,
    error: str | None = None,
) -> None:
    """Update run progress state, collected count, heartbeat, and error."""
    conn.execute(
        """
        UPDATE run_progress
        SET state = ?, samples_collected = ?, last_heartbeat = ?, error = ?
        WHERE run_id = ?
        """,
        (state, samples_collected, last_heartbeat, error, run_id),
    )


def delete_run_progress(conn: sqlite3.Connection, run_id: str) -> None:
    """Delete a run_progress row (cleanup after archival to evidence.runs)."""
    conn.execute("DELETE FROM run_progress WHERE run_id = ?", (run_id,))


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "run_id": row[0],
        "state": row[1],
        "samples_planned": row[2],
        "samples_collected": row[3],
        "last_heartbeat": row[4],
        "error": row[5],
    }
