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
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_cost_ledger_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all cost_ledger rows for a run, ordered by ts (deterministic
    tie-break on ledger_id)."""
    cur = conn.execute(
        """
        SELECT ledger_id, ts, run_id, skill_id, model_id, call_kind,
               input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        FROM cost_ledger WHERE run_id = ? ORDER BY ts, ledger_id
        """,
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def aggregate_cost_by_skill(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Roll up the fired-tax total per skill from the cost ledger.

    Groups by ``skill_id`` and sums the four token columns
    (``input_tok + cache_write_tok + cache_read_tok + output_tok``) into
    ``total_tok`` and ``usd`` into ``total_usd``. Rows with a NULL ``skill_id``
    (cost not attributable to a specific skill) are skipped. An empty ledger
    yields ``{}``.

    Returns ``{skill_id: {"total_tok": int, "total_usd": float}}``. Read-only —
    a ``GROUP BY skill_id`` aggregate needs no row order, so there is no ORDER BY
    (and therefore no timestamp-final ordering to tie-break).
    """
    cur = conn.execute(
        """
        SELECT skill_id,
               SUM(input_tok + cache_write_tok + cache_read_tok + output_tok) AS total_tok,
               SUM(usd) AS total_usd
        FROM cost_ledger
        WHERE skill_id IS NOT NULL
        GROUP BY skill_id
        """
    )
    out: dict[str, dict[str, Any]] = {}
    for skill_id, total_tok, total_usd in cur.fetchall():
        out[skill_id] = {"total_tok": int(total_tok), "total_usd": float(total_usd)}
    return out


def select_cost_ledger_since(conn: sqlite3.Connection, since_ts: str) -> list[dict[str, Any]]:
    """Return cost_ledger rows with ts >= since_ts (for rolling daily-cap check)."""
    cur = conn.execute(
        """
        SELECT ledger_id, ts, run_id, skill_id, model_id, call_kind,
               input_tok, cache_write_tok, cache_read_tok, output_tok, usd
        FROM cost_ledger WHERE ts >= ? ORDER BY ts, ledger_id
        """,
        (since_ts,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
