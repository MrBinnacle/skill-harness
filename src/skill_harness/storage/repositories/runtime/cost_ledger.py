"""Repository functions for runtime.cost_ledger (mutable, append-heavy).

Columns (from migrations/runtime/0001_initial.sql):
    ledger_id       INTEGER PRIMARY KEY AUTOINCREMENT  (omitted on INSERT)
    ts              TEXT NOT NULL DEFAULT (ISO 8601)
    run_id          TEXT  (nullable)
    skill_id        TEXT  (nullable)
    model_id        TEXT NOT NULL
    call_kind       TEXT NOT NULL CHECK (subject|judge)
    input_tok       INTEGER NOT NULL
    cache_write_tok INTEGER NOT NULL DEFAULT 0
    cache_read_tok  INTEGER NOT NULL DEFAULT 0
    output_tok      INTEGER NOT NULL
    usd             REAL NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import CostLedgerWrite


def insert_cost_ledger_entry(conn: sqlite3.Connection, entry: CostLedgerWrite) -> int:
    """Insert a new cost_ledger row. Returns the rowid (ledger_id)."""
    cur = conn.execute(
        """
        INSERT INTO cost_ledger (
            ts, run_id, skill_id, model_id, call_kind,
            input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.ts,
            entry.run_id,
            entry.skill_id,
            entry.model_id,
            entry.call_kind,
            entry.input_tok,
            entry.cache_write_tok,
            entry.cache_read_tok,
            entry.output_tok,
            entry.usd,
        ),
    )
    return cur.lastrowid or 0


def get_cost_ledger_entry_by_id(conn: sqlite3.Connection, ledger_id: int) -> dict[str, Any] | None:
    """Return the cost_ledger row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT ledger_id, ts, run_id, skill_id, model_id, call_kind,
               input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        FROM cost_ledger WHERE ledger_id = ?
        """,
        (ledger_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_cost_ledger_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all cost_ledger rows for a run, ordered by ts."""
    cur = conn.execute(
        """
        SELECT ledger_id, ts, run_id, skill_id, model_id, call_kind,
               input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        FROM cost_ledger WHERE run_id = ? ORDER BY ts
        """,
        (run_id,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def select_cost_ledger_since(conn: sqlite3.Connection, since_ts: str) -> list[dict[str, Any]]:
    """Return cost_ledger rows with ts >= since_ts (for rolling daily-cap check)."""
    cur = conn.execute(
        """
        SELECT ledger_id, ts, run_id, skill_id, model_id, call_kind,
               input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        FROM cost_ledger WHERE ts >= ? ORDER BY ts
        """,
        (since_ts,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "ledger_id": row[0],
        "ts": row[1],
        "run_id": row[2],
        "skill_id": row[3],
        "model_id": row[4],
        "call_kind": row[5],
        "input_tok": row[6],
        "cache_write_tok": row[7],
        "cache_read_tok": row[8],
        "output_tok": row[9],
        "usd": row[10],
    }
