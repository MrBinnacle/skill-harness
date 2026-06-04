"""Repository functions for evidence.oracle_verdicts (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    verdict_id              TEXT PRIMARY KEY
    run_id                  TEXT NOT NULL REFERENCES runs
    clause_id               TEXT NOT NULL REFERENCES clauses
    axis                    TEXT NOT NULL
    comparison              TEXT NOT NULL CHECK (full_vs_ablated|full_vs_null)
    sample_a_id             TEXT NOT NULL REFERENCES samples
    sample_b_id             TEXT NOT NULL REFERENCES samples
    observation             REAL NOT NULL CHECK (0.0|0.5|1.0)
    oracle_tier             INTEGER NOT NULL CHECK (1|2|3)
    metric_id               TEXT  (nullable)
    metric_version          TEXT  (nullable)
    judge_id                TEXT REFERENCES judges  (nullable)
    calibration_event_id    TEXT REFERENCES calibration_events  (nullable)
    position_swap_agreement INTEGER CHECK (0|1)  (nullable — NULL for Tier-1)
    admissibility_state     TEXT NOT NULL CHECK (admissible|inadmissible)
    inadmissibility_reason  TEXT  (nullable)
    written_at              TEXT NOT NULL

A29 — use get_admissible_verdicts() (queries the VIEW) for aggregation;
      use get_all_verdicts_for_audit() (queries raw table) for auditing.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import OracleVerdictWrite


def insert_oracle_verdict(conn: sqlite3.Connection, verdict: OracleVerdictWrite) -> None:
    """Insert a new oracle_verdict row."""
    conn.execute(
        """
        INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version, judge_id, calibration_event_id,
            position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            verdict.verdict_id,
            verdict.run_id,
            verdict.clause_id,
            verdict.axis,
            verdict.comparison,
            verdict.sample_a_id,
            verdict.sample_b_id,
            verdict.observation,
            verdict.oracle_tier,
            verdict.metric_id,
            verdict.metric_version,
            verdict.judge_id,
            verdict.calibration_event_id,
            verdict.position_swap_agreement,
            verdict.admissibility_state,
            verdict.inadmissibility_reason,
            verdict.written_at,
        ),
    )


def get_verdict_by_id(conn: sqlite3.Connection, verdict_id: str) -> dict[str, Any] | None:
    """Return the oracle_verdict row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE verdict_id = ?
        """,
        (verdict_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def get_admissible_verdicts(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return admissible, non-confounded verdicts for a run via the VIEW.

    Per A29: reads the admissible_verdicts VIEW (created in migration 0003),
    which enforces both admissibility_state = 'admissible' AND absence of
    confound_events with delta_kind = 'confound_flagged' for the same
    (run_id, primary_clause_id).

    Use this for aggregation. Use get_all_verdicts_for_audit() for auditing.
    """
    cur = conn.execute(
        "SELECT * FROM admissible_verdicts WHERE run_id = ?",
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def get_all_verdicts_for_audit(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return ALL verdicts for a run (including inadmissible/confounded).

    Per A29 naming discipline: the _for_audit suffix makes the intent explicit
    and distinguishes this from the aggregation-safe get_admissible_verdicts().
    """
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE run_id = ? ORDER BY written_at
        """,
        (run_id,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def list_verdicts_for_clause(conn: sqlite3.Connection, clause_id: str) -> list[dict[str, Any]]:
    """Return all verdicts for a clause, ordered by written_at."""
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE clause_id = ? ORDER BY written_at
        """,
        (clause_id,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def select_verdicts_by_admissibility(
    conn: sqlite3.Connection, admissibility_state: str
) -> list[dict[str, Any]]:
    """Return all verdicts with a given admissibility_state."""
    cur = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis, comparison,
               sample_a_id, sample_b_id, observation, oracle_tier,
               metric_id, metric_version, judge_id, calibration_event_id,
               position_swap_agreement, admissibility_state, inadmissibility_reason, written_at
        FROM oracle_verdicts WHERE admissibility_state = ? ORDER BY written_at
        """,
        (admissibility_state,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "verdict_id": row[0],
        "run_id": row[1],
        "clause_id": row[2],
        "axis": row[3],
        "comparison": row[4],
        "sample_a_id": row[5],
        "sample_b_id": row[6],
        "observation": row[7],
        "oracle_tier": row[8],
        "metric_id": row[9],
        "metric_version": row[10],
        "judge_id": row[11],
        "calibration_event_id": row[12],
        "position_swap_agreement": row[13],
        "admissibility_state": row[14],
        "inadmissibility_reason": row[15],
        "written_at": row[16],
    }
