"""Repository functions for evidence.confound_events (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    confound_event_id   TEXT PRIMARY KEY
    run_id              TEXT NOT NULL REFERENCES runs
    primary_clause_id   TEXT NOT NULL REFERENCES clauses
    affected_clause_id  TEXT REFERENCES clauses  (nullable — NULL for orphan axes)
    axis                TEXT NOT NULL
    delta               REAL NOT NULL
    null_sigma          REAL NOT NULL
    k_threshold         REAL NOT NULL
    delta_kind          TEXT NOT NULL CHECK (confound_flagged|observed_unclaimed_delta)
    detected_at         TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import ConfoundEventWrite


def insert_confound_event(conn: sqlite3.Connection, event: ConfoundEventWrite) -> None:
    """Insert a new confound_event row."""
    conn.execute(
        """
        INSERT INTO confound_events (
            confound_event_id, run_id, primary_clause_id, affected_clause_id,
            axis, delta, null_sigma, k_threshold, delta_kind, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.confound_event_id,
            event.run_id,
            event.primary_clause_id,
            event.affected_clause_id,
            event.axis,
            event.delta,
            event.null_sigma,
            event.k_threshold,
            event.delta_kind,
            event.detected_at,
        ),
    )


def get_confound_event_by_id(
    conn: sqlite3.Connection, confound_event_id: str
) -> dict[str, Any] | None:
    """Return the confound_event row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT confound_event_id, run_id, primary_clause_id, affected_clause_id,
               axis, delta, null_sigma, k_threshold, delta_kind, detected_at
        FROM confound_events WHERE confound_event_id = ?
        """,
        (confound_event_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_confound_events_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all confound events for a run, ordered by detected_at
    (deterministic tie-break on confound_event_id)."""
    cur = conn.execute(
        """
        SELECT confound_event_id, run_id, primary_clause_id, affected_clause_id,
               axis, delta, null_sigma, k_threshold, delta_kind, detected_at
        FROM confound_events WHERE run_id = ? ORDER BY detected_at, confound_event_id
        """,
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_confound_events_by_kind(
    conn: sqlite3.Connection, delta_kind: str
) -> list[dict[str, Any]]:
    """Return confound events matching a given delta_kind."""
    cur = conn.execute(
        """
        SELECT confound_event_id, run_id, primary_clause_id, affected_clause_id,
               axis, delta, null_sigma, k_threshold, delta_kind, detected_at
        FROM confound_events WHERE delta_kind = ? ORDER BY detected_at, confound_event_id
        """,
        (delta_kind,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
