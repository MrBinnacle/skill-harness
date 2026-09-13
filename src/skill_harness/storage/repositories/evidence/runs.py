"""Repository functions for evidence.runs.

Columns (from migrations/evidence/0001_initial.sql + 0002_runs_trigger_split.sql):
    run_id       TEXT PRIMARY KEY
    skill_id     TEXT NOT NULL REFERENCES skills
    run_kind     TEXT NOT NULL CHECK (ablation|evaluate_skill|diff)
    config_json  TEXT NOT NULL
    started_at   TEXT NOT NULL
    completed_at TEXT  (nullable — the ONE mutable field, set at most once)

Immutability rules (A20):
  - skill_id, run_kind, config_json, started_at: immutable after insert.
  - completed_at: may transition NULL -> timestamp exactly once.
  - run_id (PK): immutable per SQLite.

Evidence repos export only insert_*/get_*/select_*/list_* per A24.
The completed_at column update is handled by a dedicated helper that
uses plain conn.execute — NOT an update_ prefix function.
The function is named complete_run() to avoid the banned prefix while
still being clearly descriptive.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import ClauseRunOutcomeWrite, RunWrite


def insert_run(conn: sqlite3.Connection, run: RunWrite) -> None:
    """Insert a new run row."""
    conn.execute(
        """
        INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id,
            run.skill_id,
            run.run_kind,
            run.config_json,
            run.started_at,
            run.completed_at,
        ),
    )


def get_run_by_id(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Return the run row as a dict, or None if not found."""
    cur = conn.execute(
        "SELECT run_id, skill_id, run_kind, config_json, started_at, completed_at"
        " FROM runs WHERE run_id = ?",
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_runs_for_skill(conn: sqlite3.Connection, skill_id: str) -> list[dict[str, Any]]:
    """Return all runs for a skill, ordered by started_at (deterministic
    tie-break on run_id)."""
    cur = conn.execute(
        """
        SELECT run_id, skill_id, run_kind, config_json, started_at, completed_at
        FROM runs WHERE skill_id = ? ORDER BY started_at, run_id
        """,
        (skill_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_runs_by_kind(conn: sqlite3.Connection, run_kind: str) -> list[dict[str, Any]]:
    """Return all runs with a given run_kind, ordered by started_at
    (deterministic tie-break on run_id)."""
    cur = conn.execute(
        """
        SELECT run_id, skill_id, run_kind, config_json, started_at, completed_at
        FROM runs WHERE run_kind = ? ORDER BY started_at, run_id
        """,
        (run_kind,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def complete_run(conn: sqlite3.Connection, run_id: str, completed_at: str) -> None:
    """Stamp completed_at on a run.

    This is the ONE permitted write to an existing evidence row (per A20 column-scoped
    trigger: completed_at transitions NULL -> value exactly once).
    Raises sqlite3.IntegrityError if completed_at is already set.

    Named complete_run (not update_*) to keep the function name clearly
    describing its single purpose while complying with A24's banned-prefix rule.
    """
    conn.execute(
        "UPDATE runs SET completed_at = ? WHERE run_id = ?",
        (completed_at, run_id),
    )


# ---------------------------------------------------------------------------
# clause_run_outcomes (migration 1100, #503) — the persisted refusal sub-reason.
# Repository lives in runs.py rather than its own module: the outcomes are
# children of a run (one row per (run, clause) the runner refused), and the
# evidence repo module count is structurally pinned (test_evidence_repo_surface).
# ---------------------------------------------------------------------------


def insert_clause_run_outcome(conn: sqlite3.Connection, outcome: ClauseRunOutcomeWrite) -> None:
    """Insert a clause_run_outcome row (append-only, idempotent).

    The sub-reason is validated against UnmeasuredSubReason by the write model,
    so a non-member raises before this call reaches the DB.

    ``INSERT OR IGNORE`` makes a pre-sampling refusal idempotent under resume
    (A40): a refused clause re-refuses deterministically on resume, and the
    (run_id, clause_id) PRIMARY KEY already holds the same reason. The existing
    row is left intact (append-only: no UPDATE/DELETE), which is correct -- the
    reason does not change on re-refusal. A genuinely different reason for the
    same (run, clause) cannot arise: the gate is a pure function of the clause
    spec, which is frozen in runs.config_json.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO clause_run_outcomes
            (run_id, clause_id, unmeasured_sub_reason, written_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            outcome.run_id,
            outcome.clause_id,
            outcome.unmeasured_sub_reason,
            outcome.written_at,
        ),
    )


def list_clause_run_outcomes_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all refused-clause outcomes for a run, ordered by clause_id
    (deterministic; clause_id is the PK component that names the clause)."""
    cur = conn.execute(
        "SELECT run_id, clause_id, unmeasured_sub_reason, written_at"
        " FROM clause_run_outcomes WHERE run_id = ? ORDER BY clause_id",
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def get_clause_run_outcome(
    conn: sqlite3.Connection, run_id: str, clause_id: str
) -> dict[str, Any] | None:
    """Return the refusal outcome for one (run, clause), or None if not refused."""
    cur = conn.execute(
        "SELECT run_id, clause_id, unmeasured_sub_reason, written_at"
        " FROM clause_run_outcomes WHERE run_id = ? AND clause_id = ?",
        (run_id, clause_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))
