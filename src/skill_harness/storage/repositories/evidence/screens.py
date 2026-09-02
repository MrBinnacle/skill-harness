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

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any, NamedTuple

from skill_harness.storage.models import (
    ScreenRunSupersessionWrite,
    ScreenRunWrite,
    ScreenTrialWrite,
)
from skill_harness.storage.transaction import writer_transaction


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


def supersede_screen_run(
    conn: sqlite3.Connection,
    *,
    superseded_screen_run_id: str,
    reason: str,
    admissibility_state: str,
    inadmissibility_reason: str | None,
    skill_name: str,
    subject_model: str,
    harness_pin_fingerprint: str | None,
    source_eval_task_id: str,
    source_eval_sha256: str,
    created_at: str,
) -> str:
    """Append a new screen_run row that supersedes an existing one.

    The superseded row is never touched. The new row carries the corrected
    evidence-admissibility and copies the trials from the superseded run.
    Returns the new screen_run_id.

    :raises SupersededScreenRunError: the superseded screen_run_id does not
        exist or is already superseded.
    """
    existing = get_screen_run_by_id(conn, superseded_screen_run_id)
    if existing is None:
        raise SupersededScreenRunError(
            f"screen_run_id {superseded_screen_run_id!r} not found; "
            "cannot supersede a nonexistent run"
        )

    already = conn.execute(
        "SELECT 1 FROM screen_run_supersessions WHERE superseded_screen_run_id = ?",
        (superseded_screen_run_id,),
    ).fetchone()
    if already is not None:
        raise SupersededScreenRunError(
            f"screen_run_id {superseded_screen_run_id!r} is already superseded"
        )

    new_id = hashlib.sha256(
        f"screen-supersede:{superseded_screen_run_id}:{reason}".encode()
    ).hexdigest()
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    supersession = ScreenRunSupersessionWrite(
        superseded_screen_run_id=superseded_screen_run_id,
        superseding_screen_run_id=new_id,
        reason=reason,
    )

    with writer_transaction(conn):
        insert_screen_run(
            conn,
            ScreenRunWrite(
                screen_run_id=new_id,
                skill_name=skill_name,
                subject_model=subject_model,
                harness_pin_fingerprint=harness_pin_fingerprint,
                source_eval_task_id=source_eval_task_id,
                source_eval_sha256=source_eval_sha256,
                admissibility_state=admissibility_state,
                inadmissibility_reason=inadmissibility_reason,
                created_at=created_at,
                ingested_at=now,
            ),
        )

        trials = conn.execute(
            "SELECT epoch, passed, scorer_name, scorer_explanation, output_sha256 "
            "FROM screen_trials WHERE screen_run_id = ? ORDER BY epoch",
            (superseded_screen_run_id,),
        ).fetchall()
        for epoch, passed, scorer_name, scorer_explanation, output_sha256 in trials:
            insert_screen_trial(
                conn,
                ScreenTrialWrite(
                    screen_trial_id=str(uuid.uuid4()),
                    screen_run_id=new_id,
                    epoch=epoch,
                    passed=passed,
                    scorer_name=scorer_name,
                    scorer_explanation=scorer_explanation,
                    output_sha256=output_sha256,
                    sampled_at=now,
                ),
            )

        conn.execute(
            "INSERT INTO screen_run_supersessions "
            "(superseded_screen_run_id, superseding_screen_run_id, reason) "
            "VALUES (?, ?, ?)",
            (
                supersession.superseded_screen_run_id,
                supersession.superseding_screen_run_id,
                supersession.reason,
            ),
        )

    return new_id


class SupersededScreenRunError(ValueError):
    """Raised when a supersession operation references an invalid screen_run_id."""


class ScreenP0(NamedTuple):
    """Derived p0 for one skill: the bare (Null) arm's pass rate over admissible trials."""

    skill_name: str
    p0: float
    n_pass: int
    n_trials: int
    n_admissible_screens: int


def derive_p0_by_skill(conn: sqlite3.Connection, *, fresh_pin: str | None = None) -> list[ScreenP0]:
    """Derive p0 per skill over ADMISSIBLE screen trials (Discipline 6 — never stored).

    p0 = mean(passed) over every trial belonging to an admissible screen_run for
    the skill. Inadmissible screens (apparatus voids) are excluded — their
    evidence remains in the store, but they do not enter the derivation.

    When ``fresh_pin`` is set (#382), only trials whose screen_run carries that
    exact ``harness_pin_fingerprint`` enter the derivation. Mismatched and NULL
    pins are excluded so stale instrument rows cannot silently shape p0.

    Skills whose screens are ALL inadmissible (or all pin-excluded) produce no
    row (n_trials would be zero; p0 is undefined). Ordered by skill_name for
    stable output.
    """
    if fresh_pin is None:
        cur = conn.execute(
            """
            SELECT sr.skill_name,
                   SUM(st.passed)                 AS n_pass,
                   COUNT(st.screen_trial_id)      AS n_trials,
                   COUNT(DISTINCT sr.screen_run_id) AS n_screens
            FROM screen_runs sr
            JOIN screen_trials st ON st.screen_run_id = sr.screen_run_id
            WHERE sr.admissibility_state = 'admissible'
              AND sr.screen_run_id NOT IN (
                  SELECT superseded_screen_run_id FROM screen_run_supersessions
              )
            GROUP BY sr.skill_name
            ORDER BY sr.skill_name
            """
        )
    else:
        cur = conn.execute(
            """
            SELECT sr.skill_name,
                   SUM(st.passed)                 AS n_pass,
                   COUNT(st.screen_trial_id)      AS n_trials,
                   COUNT(DISTINCT sr.screen_run_id) AS n_screens
            FROM screen_runs sr
            JOIN screen_trials st ON st.screen_run_id = sr.screen_run_id
            WHERE sr.admissibility_state = 'admissible'
              AND sr.harness_pin_fingerprint = ?
              AND sr.screen_run_id NOT IN (
                  SELECT superseded_screen_run_id FROM screen_run_supersessions
              )
            GROUP BY sr.skill_name
            ORDER BY sr.skill_name
            """,
            (fresh_pin,),
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


class StalePinSkill(NamedTuple):
    """One skill whose admissible screens carry pins other than the fresh pin (#382)."""

    skill_name: str
    stored_fingerprints: frozenset[str]


def select_stale_pin_skills(conn: sqlite3.Connection, fresh_pin: str) -> list[StalePinSkill]:
    """Return skills with admissible screens whose pin differs from ``fresh_pin``.

    A screen is stale when its ``harness_pin_fingerprint`` is not equal to the
    freshly captured pin. NULL fingerprints count as stale: a missing pin is a
    typed refusal, not a free pass into p0. Skills that also have matching-pin
    screens still appear here so the mismatch is named; ``derive_p0_by_skill``
    with ``fresh_pin`` keeps only the matching rows. Superseded runs are
    excluded (#402): a row that no longer enters p0 must not surface as a
    stale-pin refusal either.

    Ordered by skill_name for stable output. Used by ``screen verdict`` to refuse
    rows that would silently contribute stale evidence to p0 (#382).
    """
    cur = conn.execute(
        """
        SELECT sr.skill_name,
               GROUP_CONCAT(DISTINCT sr.harness_pin_fingerprint) AS mismatched_pins
        FROM screen_runs sr
        WHERE sr.admissibility_state = 'admissible'
          AND sr.screen_run_id NOT IN (
              SELECT superseded_screen_run_id FROM screen_run_supersessions
          )
          AND (
                sr.harness_pin_fingerprint IS NULL
                OR sr.harness_pin_fingerprint != ?
              )
        GROUP BY sr.skill_name
        ORDER BY sr.skill_name
        """,
        (fresh_pin,),
    )
    out: list[StalePinSkill] = []
    for skill_name, mismatched_pins in cur.fetchall():
        # GROUP_CONCAT drops NULLs; a skill with only NULL pins yields None.
        pins = frozenset(p for p in (mismatched_pins or "").split(",") if p)
        out.append(StalePinSkill(skill_name=skill_name, stored_fingerprints=pins))
    return out
