"""Repository functions for runtime.skill_imports_staging (mutable).

Columns (from migrations/runtime/0001_initial.sql):
    staging_id   TEXT PRIMARY KEY
    source_path  TEXT NOT NULL
    state        TEXT NOT NULL CHECK (parsing|extracted|rejected|promoted)
    notes        TEXT  (nullable)
    updated_at   TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import SkillImportsStagingWrite


def insert_skill_import_staging(
    conn: sqlite3.Connection, staging: SkillImportsStagingWrite
) -> None:
    """Insert a new skill_imports_staging row."""
    conn.execute(
        """
        INSERT INTO skill_imports_staging (staging_id, source_path, state, notes, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (staging.staging_id, staging.source_path, staging.state, staging.notes, staging.updated_at),
    )


def get_skill_import_staging_by_id(
    conn: sqlite3.Connection, staging_id: str
) -> dict[str, Any] | None:
    """Return the staging row as a dict, or None if not found."""
    cur = conn.execute(
        "SELECT staging_id, source_path, state, notes, updated_at"
        " FROM skill_imports_staging WHERE staging_id = ?",
        (staging_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_skill_import_stagings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all staging rows ordered by updated_at (deterministic tie-break
    on staging_id)."""
    cur = conn.execute(
        "SELECT staging_id, source_path, state, notes, updated_at"
        " FROM skill_imports_staging ORDER BY updated_at, staging_id"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_skill_import_stagings_by_state(
    conn: sqlite3.Connection, state: str
) -> list[dict[str, Any]]:
    """Return staging rows in a given state."""
    cur = conn.execute(
        "SELECT staging_id, source_path, state, notes, updated_at"
        " FROM skill_imports_staging WHERE state = ?",
        (state,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def update_skill_import_staging_state(
    conn: sqlite3.Connection, staging_id: str, state: str, updated_at: str, notes: str | None = None
) -> None:
    """Update the state (and optionally notes) of a staging row."""
    conn.execute(
        "UPDATE skill_imports_staging SET state = ?, notes = ?, updated_at = ?"
        " WHERE staging_id = ?",
        (state, notes, updated_at, staging_id),
    )


def delete_skill_import_staging(conn: sqlite3.Connection, staging_id: str) -> None:
    """Delete a staging row (cleanup after promotion or rejection)."""
    conn.execute(
        "DELETE FROM skill_imports_staging WHERE staging_id = ?",
        (staging_id,),
    )
