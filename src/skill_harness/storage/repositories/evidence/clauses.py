"""Repository functions for evidence.clauses (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    clause_id                     TEXT PRIMARY KEY
    skill_id                      TEXT NOT NULL REFERENCES skills
    clause_index                  INTEGER NOT NULL
    rendering_index               INTEGER NOT NULL
    clause_text                   TEXT NOT NULL
    axis                          TEXT NOT NULL
    comparator                    TEXT NOT NULL CHECK (increase|decrease|match)
    oracle_tier                   INTEGER NOT NULL CHECK (1|2|3)
    vacuity_flag                  TEXT NOT NULL DEFAULT 'none'
    falsifying_case_schema_sha256 TEXT  (nullable)
    created_at                    TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import ClauseWrite


def insert_clause(conn: sqlite3.Connection, clause: ClauseWrite) -> None:
    """Insert a new clause row."""
    conn.execute(
        """
        INSERT INTO clauses (
            clause_id, skill_id, clause_index, rendering_index, clause_text,
            axis, comparator, oracle_tier, vacuity_flag,
            falsifying_case_schema_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clause.clause_id,
            clause.skill_id,
            clause.clause_index,
            clause.rendering_index,
            clause.clause_text,
            clause.axis,
            clause.comparator,
            clause.oracle_tier,
            clause.vacuity_flag,
            clause.falsifying_case_schema_sha256,
            clause.created_at,
        ),
    )


def get_clause_by_id(conn: sqlite3.Connection, clause_id: str) -> dict[str, Any] | None:
    """Return the clause row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT clause_id, skill_id, clause_index, rendering_index, clause_text,
               axis, comparator, oracle_tier, vacuity_flag,
               falsifying_case_schema_sha256, created_at
        FROM clauses WHERE clause_id = ?
        """,
        (clause_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_clauses_for_skill(conn: sqlite3.Connection, skill_id: str) -> list[dict[str, Any]]:
    """Return all clause rows for a skill, ordered by clause_index."""
    cur = conn.execute(
        """
        SELECT clause_id, skill_id, clause_index, rendering_index, clause_text,
               axis, comparator, oracle_tier, vacuity_flag,
               falsifying_case_schema_sha256, created_at
        FROM clauses WHERE skill_id = ? ORDER BY clause_index
        """,
        (skill_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_clauses_by_axis(conn: sqlite3.Connection, axis: str) -> list[dict[str, Any]]:
    """Return all clause rows with a given axis."""
    cur = conn.execute(
        """
        SELECT clause_id, skill_id, clause_index, rendering_index, clause_text,
               axis, comparator, oracle_tier, vacuity_flag,
               falsifying_case_schema_sha256, created_at
        FROM clauses WHERE axis = ? ORDER BY skill_id, clause_index
        """,
        (axis,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
