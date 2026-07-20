"""Repository functions for the Stage-0 screen store (migration 0501).

Columns (from migrations/evidence/0501_screen_store.sql):
    screen_runs
        screen_run_id           TEXT PRIMARY KEY
        skill_name              TEXT NOT NULL
        subject_model           TEXT NOT NULL
        harness_pin_fingerprint TEXT
        source_eval_task_id     TEXT NOT NULL
        source_eval_sha256      TEXT NOT NULL
        admissibility_state     TEXT NOT NULL CHECK (admissible|inadmissible)
        inadmissibility_reason  TEXT
        created_at              TEXT NOT NULL
        ingested_at             TEXT NOT NULL
    screen_trials
        screen_trial_id     TEXT PRIMARY KEY
        screen_run_id       TEXT NOT NULL REFERENCES screen_runs
        epoch               INTEGER NOT NULL
        passed              INTEGER NOT NULL CHECK (0|1)
        scorer_name         TEXT NOT NULL
        scorer_explanation  TEXT
        output_sha256       TEXT NOT NULL
        sampled_at          TEXT NOT NULL
        UNIQUE (screen_run_id, epoch)

Screens are append-only and firewalled from the paired evidence model; both
tables carry BEFORE UPDATE/DELETE triggers. p0 is DERIVED here (Discipline 6),
never stored: mean(passed) over the trials of ADMISSIBLE screen_runs per skill.

Evidence repos export only insert_*/get_*/select_*/derive_* per A24.
"""

from __future__ import annotations

import sqlite3
from typing import Any, NamedTuple

from skill_harness.storage.models import ScreenRunWrite, ScreenTrialWrite


def insert_screen_run(conn: sqlite3.Connection, run: ScreenRunWrite) -> None:
    """Insert a new screen_run row."""
    conn.execute(
        """
        INSERT INTO screen_runs (
            screen_run_id, skill_name, subject_model, harness_pin_fingerprint,
            source_eval_task_id, source_eval_sha256, admissibility_state,
            inadmissibility_reason, created_at, ingested_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.screen_run_id,
            run.skill_name,
            run.subject_model,
            run.harness_pin_fingerprint,
            run.source_eval_task_id,
            run.source_eval_sha256,
            run.admissibility_state,
            run.inadmissibility_reason,
            run.created_at,
            run.ingested_at,
        ),
    )


def insert_screen_trial(conn: sqlite3.Connection, trial: ScreenTrialWrite) -> None:
    """Insert a new screen_trial row."""
    conn.execute(
        """
        INSERT INTO screen_trials (
            screen_trial_id, screen_run_id, epoch, passed, scorer_name,
            scorer_explanation, output_sha256, sampled_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trial.screen_trial_id,
            trial.screen_run_id,
            trial.epoch,
            trial.passed,
            trial.scorer_name,
            trial.scorer_explanation,
            trial.output_sha256,
            trial.sampled_at,
        ),
    )


def get_screen_run_by_id(conn: sqlite3.Connection, screen_run_id: str) -> dict[str, Any] | None:
    """Return the screen_run row as a dict, or None if not found (idempotency check)."""
    cur = conn.execute(
        """
        SELECT screen_run_id, skill_name, subject_model, harness_pin_fingerprint,
               source_eval_task_id, source_eval_sha256, admissibility_state,
               inadmissibility_reason, created_at, ingested_at
        FROM screen_runs WHERE screen_run_id = ?
        """,
        (screen_run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


class ScreenP0(NamedTuple):
    """Derived p0 for one skill: the bare (Null) arm's pass rate over admissible trials."""

    skill_name: str
    p0: float
    n_pass: int
    n_trials: int
    n_admissible_screens: int


def derive_p0_by_skill(conn: sqlite3.Connection) -> list[ScreenP0]:
    """Derive p0 per skill over ADMISSIBLE screen trials (Discipline 6 — never stored).

    p0 = mean(passed) over every trial belonging to an admissible screen_run for
    the skill. Inadmissible screens (apparatus voids) are excluded — their
    evidence remains in the store, but they do not enter the derivation.

    Skills whose screens are ALL inadmissible produce no row (n_trials would be
    zero; p0 is undefined). Ordered by skill_name for stable output.
    """
    cur = conn.execute(
        """
        SELECT sr.skill_name,
               SUM(st.passed)                 AS n_pass,
               COUNT(st.screen_trial_id)      AS n_trials,
               COUNT(DISTINCT sr.screen_run_id) AS n_screens
        FROM screen_runs sr
        JOIN screen_trials st ON st.screen_run_id = sr.screen_run_id
        WHERE sr.admissibility_state = 'admissible'
        GROUP BY sr.skill_name
        ORDER BY sr.skill_name
        """
    )
    out: list[ScreenP0] = []
    for skill_name, n_pass, n_trials, n_screens in cur.fetchall():
        out.append(
            ScreenP0(
                skill_name=skill_name,
                p0=n_pass / n_trials,
                n_pass=int(n_pass),
                n_trials=int(n_trials),
                n_admissible_screens=int(n_screens),
            )
        )
    return out
