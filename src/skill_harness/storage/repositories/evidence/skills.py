"""Repository functions for evidence.skills (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    skill_id      TEXT PRIMARY KEY
    name          TEXT NOT NULL
    source_path   TEXT NOT NULL
    source_sha256 TEXT NOT NULL
    imported_at   TEXT NOT NULL  (ISO 8601, set by caller or DB DEFAULT)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import SkillWrite


def insert_skill(conn: sqlite3.Connection, skill: SkillWrite) -> None:
    """Insert a new skill row. Raises sqlite3.IntegrityError on duplicate skill_id."""
    conn.execute(
        """
        INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (skill.skill_id, skill.name, skill.source_path, skill.source_sha256, skill.imported_at),
    )


def get_skill_by_id(conn: sqlite3.Connection, skill_id: str) -> dict[str, Any] | None:
    """Return the skill row as a dict, or None if not found."""
    cur = conn.execute(
        "SELECT skill_id, name, source_path, source_sha256, imported_at"
        " FROM skills WHERE skill_id = ?",
        (skill_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "skill_id": row[0],
        "name": row[1],
        "source_path": row[2],
        "source_sha256": row[3],
        "imported_at": row[4],
    }


def list_skills(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all skill rows ordered by imported_at."""
    cur = conn.execute(
        "SELECT skill_id, name, source_path, source_sha256, imported_at"
        " FROM skills ORDER BY imported_at"
    )
    return [
        {
            "skill_id": row[0],
            "name": row[1],
            "source_path": row[2],
            "source_sha256": row[3],
            "imported_at": row[4],
        }
        for row in cur.fetchall()
    ]


def select_skills_by_source_sha256(
    conn: sqlite3.Connection, source_sha256: str
) -> list[dict[str, Any]]:
    """Return skill rows matching a given source SHA-256."""
    cur = conn.execute(
        "SELECT skill_id, name, source_path, source_sha256, imported_at"
        " FROM skills WHERE source_sha256 = ?",
        (source_sha256,),
    )
    return [
        {
            "skill_id": row[0],
            "name": row[1],
            "source_path": row[2],
            "source_sha256": row[3],
            "imported_at": row[4],
        }
        for row in cur.fetchall()
    ]
