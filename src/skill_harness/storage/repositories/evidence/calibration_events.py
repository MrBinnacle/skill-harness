"""Repository functions for evidence.calibration_events (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    calibration_event_id        TEXT PRIMARY KEY
    judge_id                    TEXT NOT NULL REFERENCES judges
    axis                        TEXT NOT NULL
    pairwise_agreement          REAL NOT NULL CHECK (0 to 1)
    position_consistency        REAL NOT NULL CHECK (0 to 1)
    length_controlled_agreement REAL  (nullable)
    cohen_kappa                 REAL  (nullable)
    pair_set_size               INTEGER NOT NULL CHECK (>= 50)
    pair_set_sha256             TEXT NOT NULL
    state                       TEXT NOT NULL CHECK (calibrated|conditional|uncalibrated|expired)
    expires_at                  TEXT  (nullable)
    validated_at                TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import CalibrationEventWrite


def insert_calibration_event(conn: sqlite3.Connection, event: CalibrationEventWrite) -> None:
    """Insert a new calibration_event row."""
    conn.execute(
        """
        INSERT INTO calibration_events (
            calibration_event_id, judge_id, axis,
            pairwise_agreement, position_consistency, length_controlled_agreement,
            cohen_kappa, pair_set_size, pair_set_sha256,
            state, expires_at, validated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.calibration_event_id,
            event.judge_id,
            event.axis,
            event.pairwise_agreement,
            event.position_consistency,
            event.length_controlled_agreement,
            event.cohen_kappa,
            event.pair_set_size,
            event.pair_set_sha256,
            event.state,
            event.expires_at,
            event.validated_at,
        ),
    )


def get_calibration_event_by_id(
    conn: sqlite3.Connection, calibration_event_id: str
) -> dict[str, Any] | None:
    """Return the calibration_event row, or None if not found."""
    cur = conn.execute(
        """
        SELECT calibration_event_id, judge_id, axis,
               pairwise_agreement, position_consistency, length_controlled_agreement,
               cohen_kappa, pair_set_size, pair_set_sha256,
               state, expires_at, validated_at
        FROM calibration_events WHERE calibration_event_id = ?
        """,
        (calibration_event_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_calibration_events_for_judge_axis(
    conn: sqlite3.Connection, judge_id: str, axis: str
) -> list[dict[str, Any]]:
    """Return calibration events for a (judge_id, axis) pair, newest first."""
    cur = conn.execute(
        """
        SELECT calibration_event_id, judge_id, axis,
               pairwise_agreement, position_consistency, length_controlled_agreement,
               cohen_kappa, pair_set_size, pair_set_sha256,
               state, expires_at, validated_at
        FROM calibration_events
        WHERE judge_id = ? AND axis = ?
        ORDER BY validated_at DESC
        """,
        (judge_id, axis),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def select_calibration_events_by_state(
    conn: sqlite3.Connection, state: str
) -> list[dict[str, Any]]:
    """Return calibration events matching a given state."""
    cur = conn.execute(
        """
        SELECT calibration_event_id, judge_id, axis,
               pairwise_agreement, position_consistency, length_controlled_agreement,
               cohen_kappa, pair_set_size, pair_set_sha256,
               state, expires_at, validated_at
        FROM calibration_events WHERE state = ? ORDER BY validated_at DESC
        """,
        (state,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "calibration_event_id": row[0],
        "judge_id": row[1],
        "axis": row[2],
        "pairwise_agreement": row[3],
        "position_consistency": row[4],
        "length_controlled_agreement": row[5],
        "cohen_kappa": row[6],
        "pair_set_size": row[7],
        "pair_set_sha256": row[8],
        "state": row[9],
        "expires_at": row[10],
        "validated_at": row[11],
    }
