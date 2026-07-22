"""Repository functions for evidence.calibration_events (append-only).

Columns (from migrations/evidence/0001_initial.sql +
         0200_calibration_event_extensions.sql):
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
    -- A37 new columns (Track C.3):
    n_a                         INTEGER  (nullable; human-pref A count)
    n_b                         INTEGER  (nullable; human-pref B count)
    n_tie                       INTEGER  (nullable; human-pref tie count)
    judge_n_a                   INTEGER  (nullable; judge verdict A count)
    judge_n_b                   INTEGER  (nullable; judge verdict B count)
    judge_n_tie                 INTEGER  (nullable; judge verdict tie count)
    length_regression_coefficient REAL   (nullable; β₁, written by C.4)
    chance_baseline             REAL     (nullable; p_e from κ formula)
    total_usd_spent             REAL     (nullable; C.4 cost ledger sum)
    cost_ledger_run_id          TEXT     (nullable; cross-DB pointer)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import CalibrationEventWrite


def insert_calibration_event(conn: sqlite3.Connection, event: CalibrationEventWrite) -> None:
    """Insert a new calibration_event row (including A37 extension columns)."""
    conn.execute(
        """
        INSERT INTO calibration_events (
            calibration_event_id, judge_id, axis,
            pairwise_agreement, position_consistency, length_controlled_agreement,
            cohen_kappa, pair_set_size, pair_set_sha256,
            state, expires_at, validated_at,
            n_a, n_b, n_tie,
            judge_n_a, judge_n_b, judge_n_tie,
            length_regression_coefficient, chance_baseline,
            total_usd_spent, cost_ledger_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            event.n_a,
            event.n_b,
            event.n_tie,
            event.judge_n_a,
            event.judge_n_b,
            event.judge_n_tie,
            event.length_regression_coefficient,
            event.chance_baseline,
            event.total_usd_spent,
            event.cost_ledger_run_id,
        ),
    )


_SELECT_ALL_COLS = """
        SELECT calibration_event_id, judge_id, axis,
               pairwise_agreement, position_consistency, length_controlled_agreement,
               cohen_kappa, pair_set_size, pair_set_sha256,
               state, expires_at, validated_at,
               n_a, n_b, n_tie, judge_n_a, judge_n_b, judge_n_tie,
               length_regression_coefficient, chance_baseline,
               total_usd_spent, cost_ledger_run_id
"""


def get_calibration_event_by_id(
    conn: sqlite3.Connection, calibration_event_id: str
) -> dict[str, Any] | None:
    """Return the calibration_event row (all columns), or None if not found."""
    cur = conn.execute(
        _SELECT_ALL_COLS + "FROM calibration_events WHERE calibration_event_id = ?",
        (calibration_event_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_calibration_events_for_judge_axis(
    conn: sqlite3.Connection, judge_id: str, axis: str
) -> list[dict[str, Any]]:
    """Return calibration events for a (judge_id, axis) pair, newest first."""
    cur = conn.execute(
        _SELECT_ALL_COLS
        + """
        FROM calibration_events
        WHERE judge_id = ? AND axis = ?
        ORDER BY validated_at DESC, calibration_event_id DESC
        """,
        (judge_id, axis),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_calibration_events_by_state(
    conn: sqlite3.Connection, state: str
) -> list[dict[str, Any]]:
    """Return calibration events matching a given state."""
    cur = conn.execute(
        _SELECT_ALL_COLS + "FROM calibration_events WHERE state = ? "
        "ORDER BY validated_at DESC, calibration_event_id DESC",
        (state,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
