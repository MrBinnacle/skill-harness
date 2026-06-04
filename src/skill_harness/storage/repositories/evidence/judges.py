"""Repository functions for evidence.judges (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    judge_id             TEXT PRIMARY KEY
    model_id             TEXT NOT NULL
    system_prompt_sha256 TEXT NOT NULL
    created_at           TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import JudgeWrite


def insert_judge(conn: sqlite3.Connection, judge: JudgeWrite) -> None:
    """Insert a new judge row."""
    conn.execute(
        """
        INSERT INTO judges (judge_id, model_id, system_prompt_sha256, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (judge.judge_id, judge.model_id, judge.system_prompt_sha256, judge.created_at),
    )


def get_judge_by_id(conn: sqlite3.Connection, judge_id: str) -> dict[str, Any] | None:
    """Return the judge row as a dict, or None if not found."""
    cur = conn.execute(
        "SELECT judge_id, model_id, system_prompt_sha256, created_at"
        " FROM judges WHERE judge_id = ?",
        (judge_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "judge_id": row[0],
        "model_id": row[1],
        "system_prompt_sha256": row[2],
        "created_at": row[3],
    }


def list_judges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all judge rows ordered by created_at."""
    cur = conn.execute(
        "SELECT judge_id, model_id, system_prompt_sha256, created_at"
        " FROM judges ORDER BY created_at"
    )
    return [
        {
            "judge_id": row[0],
            "model_id": row[1],
            "system_prompt_sha256": row[2],
            "created_at": row[3],
        }
        for row in cur.fetchall()
    ]


def select_judges_by_model(conn: sqlite3.Connection, model_id: str) -> list[dict[str, Any]]:
    """Return all judge rows for a given model_id."""
    cur = conn.execute(
        "SELECT judge_id, model_id, system_prompt_sha256, created_at"
        " FROM judges WHERE model_id = ?",
        (model_id,),
    )
    return [
        {
            "judge_id": row[0],
            "model_id": row[1],
            "system_prompt_sha256": row[2],
            "created_at": row[3],
        }
        for row in cur.fetchall()
    ]
