"""Repository functions for the task-frontier phase partition (migration 0700).

Three physically separate append-only tables — one per phase — sharing one row
shape. `PHASE_TABLES` is the ONLY place a phase name is turned into a table
name; every read and write below routes through it.

    task_frontier_calibration_obs   phase CHECK = 'calibration'
    task_frontier_confirmation_obs  phase CHECK = 'confirmation'
    task_frontier_matched_obs       phase CHECK = 'matched'

Columns (identical across the three, from 0700_task_frontier.sql):
    observation_id          TEXT PRIMARY KEY
    task_family_id          TEXT NOT NULL
    task_family_version     TEXT NOT NULL
    semantic_lineage_id     TEXT NOT NULL
    phase                   TEXT NOT NULL CHECK (= this table's phase)
    instance_id             TEXT NOT NULL
    arm                     TEXT NOT NULL CHECK (full|null)
    passed                  INTEGER NOT NULL CHECK (0|1)
    generator_fingerprint   TEXT NOT NULL
    oracle_fingerprint      TEXT NOT NULL
    admissibility_state     TEXT NOT NULL CHECK (admissible|inadmissible)
    inadmissibility_reason  TEXT
    observed_at             TEXT NOT NULL
    ingested_at             TEXT NOT NULL

WHY THERE IS NO `select_calibration_observations` HERE: the whole point of the
physical partition (spec #89) is that no bulk accessor for the walled-off
phases exists to be called from the effect path. `select_matched_observations`
is the estimator feed; calibration and confirmation rows are reachable only by
observation id, through `get_task_frontier_observation_by_id`, which cannot
enumerate a phase. A future ticket needing aggregate calibration facts should
expose the DECISION it derives (the selected rung), not the observations.

Evidence repos export only insert_*/get_*/select_*/derive_* per A24. Table
names are interpolated from the module-level `PHASE_TABLES` literal map only —
never from caller input — so no SQL-injection surface is opened.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Final

from skill_harness.storage.models import TASK_FRONTIER_PHASES, TaskFrontierObservationWrite

PHASE_TABLES: Final[dict[str, str]] = {
    "calibration": "task_frontier_calibration_obs",
    "confirmation": "task_frontier_confirmation_obs",
    "matched": "task_frontier_matched_obs",
}

# The map and the write model's accepted phases must agree, or a validated
# write could still fail to route. Checked at import — and with an explicit
# raise rather than `assert`, which `python -O` strips.
if set(PHASE_TABLES) != set(TASK_FRONTIER_PHASES):  # pragma: no cover — import-time invariant
    raise RuntimeError(
        f"PHASE_TABLES keys {sorted(PHASE_TABLES)} disagree with "
        f"TASK_FRONTIER_PHASES {sorted(TASK_FRONTIER_PHASES)}"
    )

_COLUMNS: Final[tuple[str, ...]] = (
    "observation_id",
    "task_family_id",
    "task_family_version",
    "semantic_lineage_id",
    "phase",
    "instance_id",
    "arm",
    "passed",
    "generator_fingerprint",
    "oracle_fingerprint",
    "admissibility_state",
    "inadmissibility_reason",
    "observed_at",
    "ingested_at",
)

_COLUMN_LIST: Final[str] = ", ".join(_COLUMNS)
_PLACEHOLDERS: Final[str] = ", ".join("?" for _ in _COLUMNS)


def insert_task_frontier_observation(
    conn: sqlite3.Connection, observation: TaskFrontierObservationWrite
) -> None:
    """Insert one observation into the partition named by its own `phase`.

    The phase has already been validated by the write model; the destination
    table follows from it mechanically, so a row cannot be filed under a phase
    it was not admitted to.
    """
    table = PHASE_TABLES[observation.phase]
    conn.execute(
        f"INSERT INTO {table} ({_COLUMN_LIST}) VALUES ({_PLACEHOLDERS})",  # noqa: S608
        (
            observation.observation_id,
            observation.task_family_id,
            observation.task_family_version,
            observation.semantic_lineage_id,
            observation.phase,
            observation.instance_id,
            observation.arm,
            observation.passed,
            observation.generator_fingerprint,
            observation.oracle_fingerprint,
            observation.admissibility_state,
            observation.inadmissibility_reason,
            observation.observed_at,
            observation.ingested_at,
        ),
    )


def get_task_frontier_observation_by_id(
    conn: sqlite3.Connection, observation_id: str
) -> dict[str, Any] | None:
    """Return one stored observation as a dict, or None if no partition holds it.

    Takes NO manifest and NO phase: the returned `phase` is the write-time
    stamp, which is what makes it usable as an audit read.

    Searches the partitions in a fixed order and returns the first hit. Ids are
    unique ACROSS the three tables only because `task_frontier.admit` refuses a
    write whose id already exists anywhere — the per-table PRIMARY KEYs alone
    cannot see across the partition. A direct writer that bypasses `admit` can
    therefore make this read ambiguous; that is one of the reasons `admit` is
    the only supported way in.
    """
    for phase in sorted(PHASE_TABLES):
        table = PHASE_TABLES[phase]
        cur = conn.execute(
            f"SELECT {_COLUMN_LIST} FROM {table} WHERE observation_id = ?",  # noqa: S608
            (observation_id,),
        )
        row = cur.fetchone()
        if row is not None:
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row, strict=True))
    return None


def select_matched_observations(
    conn: sqlite3.Connection, task_family_id: str, task_family_version: str
) -> list[dict[str, Any]]:
    """Return ADMISSIBLE matched-phase observations for one task-family version.

    The single estimator feed. It names `task_frontier_matched_obs` literally,
    so no argument a caller can pass will make it return calibration or
    confirmation evidence.

    Scoped to a family VERSION because every claim the instrument makes is
    scoped to one — a version bump is a different measurement, not more data
    for the old one. Ordered by observation_id (a unique key) so the pair
    sequence handed to `oc/gate2` is deterministic; E3 forbids resting on a
    timestamp alone.
    """
    table = PHASE_TABLES["matched"]
    cur = conn.execute(
        f"""
        SELECT {_COLUMN_LIST}
        FROM {table}
        WHERE task_family_id = ?
          AND task_family_version = ?
          AND admissibility_state = 'admissible'
        ORDER BY observation_id
        """,  # noqa: S608
        (task_family_id, task_family_version),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
