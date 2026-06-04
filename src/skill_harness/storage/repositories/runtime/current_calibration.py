"""Repository functions for runtime.current_calibration (mutable pointer).

Columns (from migrations/runtime/0001_initial.sql):
    judge_id              TEXT NOT NULL  (composite PK with axis)
    axis                  TEXT NOT NULL
    calibration_event_id  TEXT NOT NULL  (cross-DB FK into evidence.calibration_events)
    state                 TEXT NOT NULL CHECK (calibrated|conditional|uncalibrated|expired)
    expires_at            TEXT  (nullable)
    updated_at            TEXT NOT NULL
    PRIMARY KEY (judge_id, axis)

This table is the ONLY mutable "live pointer" for calibration. The immutable
history is in evidence.calibration_events. Per A3, oracle_verdicts snapshots
calibration_event_id at write time — this table only affects FUTURE verdicts.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import CurrentCalibrationWrite


def insert_current_calibration(conn: sqlite3.Connection, cal: CurrentCalibrationWrite) -> None:
    """Insert a current_calibration row (initial calibration for a judge+axis)."""
    conn.execute(
        """
        INSERT INTO current_calibration
            (judge_id, axis, calibration_event_id, state, expires_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            cal.judge_id,
            cal.axis,
            cal.calibration_event_id,
            cal.state,
            cal.expires_at,
            cal.updated_at,
        ),
    )


def get_current_calibration(
    conn: sqlite3.Connection, judge_id: str, axis: str
) -> dict[str, Any] | None:
    """Return the current calibration pointer for (judge_id, axis), or None."""
    cur = conn.execute(
        "SELECT judge_id, axis, calibration_event_id, state, expires_at, updated_at"
        " FROM current_calibration WHERE judge_id = ? AND axis = ?",
        (judge_id, axis),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_current_calibrations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all current calibration rows."""
    cur = conn.execute(
        "SELECT judge_id, axis, calibration_event_id, state, expires_at, updated_at"
        " FROM current_calibration ORDER BY judge_id, axis"
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def select_current_calibrations_by_state(
    conn: sqlite3.Connection, state: str
) -> list[dict[str, Any]]:
    """Return current calibrations in a given state."""
    cur = conn.execute(
        "SELECT judge_id, axis, calibration_event_id, state, expires_at, updated_at"
        " FROM current_calibration WHERE state = ?",
        (state,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def update_current_calibration(
    conn: sqlite3.Connection,
    judge_id: str,
    axis: str,
    *,
    calibration_event_id: str,
    state: str,
    expires_at: str | None,
    updated_at: str,
) -> None:
    """Overwrite the calibration pointer for (judge_id, axis).

    Called on recalibration. The old pointer is gone; the immutable history
    lives in evidence.calibration_events.
    """
    conn.execute(
        """
        UPDATE current_calibration
        SET calibration_event_id = ?, state = ?, expires_at = ?, updated_at = ?
        WHERE judge_id = ? AND axis = ?
        """,
        (calibration_event_id, state, expires_at, updated_at, judge_id, axis),
    )


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "judge_id": row[0],
        "axis": row[1],
        "calibration_event_id": row[2],
        "state": row[3],
        "expires_at": row[4],
        "updated_at": row[5],
    }
