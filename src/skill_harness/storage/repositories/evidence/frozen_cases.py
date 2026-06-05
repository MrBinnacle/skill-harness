"""Repository functions for evidence.frozen_cases (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    frozen_case_id        TEXT PRIMARY KEY
    clause_id             TEXT NOT NULL REFERENCES clauses
    failing_input_text    TEXT NOT NULL
    failing_input_sha256  TEXT NOT NULL
    oracle_source         TEXT NOT NULL CHECK (human|mechanical)
    labeled_by            TEXT  (nullable — required when oracle_source = 'human')
    labeled_at            TEXT  (nullable — required when oracle_source = 'human')
    metric_id             TEXT  (nullable — required when oracle_source = 'mechanical')
    metric_version        TEXT  (nullable — required when oracle_source = 'mechanical')
    implementation_hash   TEXT  (nullable — required when oracle_source = 'mechanical')
    frozen_at             TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import FrozenCaseWrite


def insert_frozen_case(conn: sqlite3.Connection, case: FrozenCaseWrite) -> None:
    """Insert a new frozen_case row."""
    conn.execute(
        """
        INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, labeled_by, labeled_at,
            metric_id, metric_version, implementation_hash, frozen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case.frozen_case_id,
            case.clause_id,
            case.failing_input_text,
            case.failing_input_sha256,
            case.oracle_source,
            case.labeled_by,
            case.labeled_at,
            case.metric_id,
            case.metric_version,
            case.implementation_hash,
            case.frozen_at,
        ),
    )


def get_frozen_case_by_id(conn: sqlite3.Connection, frozen_case_id: str) -> dict[str, Any] | None:
    """Return the frozen_case row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at
        FROM frozen_cases WHERE frozen_case_id = ?
        """,
        (frozen_case_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_frozen_cases_for_clause(conn: sqlite3.Connection, clause_id: str) -> list[dict[str, Any]]:
    """Return all frozen cases for a clause, ordered by frozen_at."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at
        FROM frozen_cases WHERE clause_id = ? ORDER BY frozen_at
        """,
        (clause_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_frozen_cases_by_oracle_source(
    conn: sqlite3.Connection, oracle_source: str
) -> list[dict[str, Any]]:
    """Return all frozen cases with a given oracle_source."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at
        FROM frozen_cases WHERE oracle_source = ? ORDER BY frozen_at
        """,
        (oracle_source,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
