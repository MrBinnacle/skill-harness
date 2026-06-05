"""Repository functions for runtime.run_budget (mutable).

Columns (from migrations/runtime/0001_initial.sql):
    run_id            TEXT PRIMARY KEY
    hard_cap_usd      REAL NOT NULL
    tokens_spent_in   INTEGER NOT NULL DEFAULT 0
    tokens_spent_out  INTEGER NOT NULL DEFAULT 0
    cache_write_in    INTEGER NOT NULL DEFAULT 0
    cache_read_in     INTEGER NOT NULL DEFAULT 0
    usd_spent         REAL NOT NULL DEFAULT 0.0
    dry_run           INTEGER NOT NULL DEFAULT 1 CHECK (0|1)
    aborted_at        TEXT  (nullable)
    last_updated      TEXT NOT NULL
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import RunBudgetWrite


def insert_run_budget(conn: sqlite3.Connection, budget: RunBudgetWrite) -> None:
    """Insert a new run_budget row."""
    conn.execute(
        """
        INSERT INTO run_budget (
            run_id, hard_cap_usd, tokens_spent_in, tokens_spent_out,
            cache_write_in, cache_read_in, usd_spent, dry_run, aborted_at, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            budget.run_id,
            budget.hard_cap_usd,
            budget.tokens_spent_in,
            budget.tokens_spent_out,
            budget.cache_write_in,
            budget.cache_read_in,
            budget.usd_spent,
            budget.dry_run,
            budget.aborted_at,
            budget.last_updated,
        ),
    )


def get_run_budget_by_id(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Return the run_budget row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT run_id, hard_cap_usd, tokens_spent_in, tokens_spent_out,
               cache_write_in, cache_read_in, usd_spent, dry_run, aborted_at, last_updated
        FROM run_budget WHERE run_id = ?
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_run_budgets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all run_budget rows ordered by last_updated."""
    cur = conn.execute(
        """
        SELECT run_id, hard_cap_usd, tokens_spent_in, tokens_spent_out,
               cache_write_in, cache_read_in, usd_spent, dry_run, aborted_at, last_updated
        FROM run_budget ORDER BY last_updated
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_run_budgets_over_cap(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return run budgets where usd_spent >= hard_cap_usd."""
    cur = conn.execute(
        """
        SELECT run_id, hard_cap_usd, tokens_spent_in, tokens_spent_out,
               cache_write_in, cache_read_in, usd_spent, dry_run, aborted_at, last_updated
        FROM run_budget WHERE usd_spent >= hard_cap_usd ORDER BY last_updated
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def update_run_budget_spend(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    tokens_spent_in: int,
    tokens_spent_out: int,
    cache_write_in: int,
    cache_read_in: int,
    usd_spent: float,
    last_updated: str,
) -> None:
    """Update token and USD spend for a run."""
    conn.execute(
        """
        UPDATE run_budget
        SET tokens_spent_in = ?, tokens_spent_out = ?,
            cache_write_in = ?, cache_read_in = ?,
            usd_spent = ?, last_updated = ?
        WHERE run_id = ?
        """,
        (
            tokens_spent_in,
            tokens_spent_out,
            cache_write_in,
            cache_read_in,
            usd_spent,
            last_updated,
            run_id,
        ),
    )


def update_run_budget_aborted(
    conn: sqlite3.Connection, run_id: str, aborted_at: str, last_updated: str
) -> None:
    """Stamp aborted_at on a budget row when a run is aborted due to budget exhaustion."""
    conn.execute(
        "UPDATE run_budget SET aborted_at = ?, last_updated = ? WHERE run_id = ?",
        (aborted_at, last_updated, run_id),
    )
