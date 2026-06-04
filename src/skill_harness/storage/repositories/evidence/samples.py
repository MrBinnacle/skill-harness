"""Repository functions for evidence.samples (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    sample_id      TEXT PRIMARY KEY
    run_id         TEXT NOT NULL REFERENCES runs
    clause_id      TEXT NOT NULL REFERENCES clauses
    condition      TEXT NOT NULL CHECK (full|ablated|null)
    subject_model  TEXT NOT NULL
    subject_seed   TEXT  (nullable)
    output_text    TEXT NOT NULL
    output_sha256  TEXT NOT NULL
    sampled_at     TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import SampleWrite


def insert_sample(conn: sqlite3.Connection, sample: SampleWrite) -> None:
    """Insert a new sample row."""
    conn.execute(
        """
        INSERT INTO samples (
            sample_id, run_id, clause_id, condition,
            subject_model, subject_seed, output_text, output_sha256, sampled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample.sample_id,
            sample.run_id,
            sample.clause_id,
            sample.condition,
            sample.subject_model,
            sample.subject_seed,
            sample.output_text,
            sample.output_sha256,
            sample.sampled_at,
        ),
    )


def get_sample_by_id(conn: sqlite3.Connection, sample_id: str) -> dict[str, Any] | None:
    """Return the sample row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE sample_id = ?
        """,
        (sample_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_samples_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all samples for a run, ordered by sampled_at."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE run_id = ? ORDER BY sampled_at
        """,
        (run_id,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def select_samples_by_condition(
    conn: sqlite3.Connection, run_id: str, condition: str
) -> list[dict[str, Any]]:
    """Return samples for a run filtered by condition."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE run_id = ? AND condition = ? ORDER BY sampled_at
        """,
        (run_id, condition),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "sample_id": row[0],
        "run_id": row[1],
        "clause_id": row[2],
        "condition": row[3],
        "subject_model": row[4],
        "subject_seed": row[5],
        "output_text": row[6],
        "output_sha256": row[7],
        "sampled_at": row[8],
    }
