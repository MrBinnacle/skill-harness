"""Storage-layer recovery primitives shared by Track E subcommands (A61).

Lifted from the private _find_incomplete_run in cli/main.py so that
Track E.3 `evaluate-skill`, `freeze`, and the existing `run ablation`
WARN path all use the same two-step runtime→evidence lookup.

Two-DB join discipline (A25): cross-DB lookups are done at the Python
layer — no ATTACH or cross-DB SQL joins.

B4: skill_id matching uses the runs.skill_id COLUMN, never config_json. The
column is NOT NULL, FK-enforced (REFERENCES skills), and immutable after
insert (A20) — it is the single source of truth for a run's skill. Reading
skill_id back out of config_json (as this module did before B4) creates a
second, unenforced copy that can silently diverge from the column and is
also what aggregate_skill()'s own precondition-matching queries against
(runs.skill_id, engine.py:_fetch_completed_ablation_runs) — any drift between
the two routes meant an incomplete run could be missed by this module's
find_incomplete_runs() while still being aggregated over by engine.py.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from sqlite3 import Connection

from skill_harness.aggregation.errors import PreconditionError


@dataclass(frozen=True)
class IncompleteRun:
    """Summary of a non-terminal run for a specific skill."""

    run_id: str
    state: str  # from runtime.run_progress.state
    skill_id: str  # extracted from evidence.runs.config_json
    last_heartbeat_at: str  # ISO8601; last_heartbeat is NOT NULL in run_progress schema


def find_incomplete_runs(
    skill_id: str,
    *,
    evidence_conn_ro: Connection,
    runtime_conn: Connection,
) -> list[IncompleteRun]:
    """Two-step runtime→evidence lookup. Returns ALL incomplete runs for skill_id.

    Step 1: query runtime.run_progress for non-terminal states
            (NOT IN ('completed', 'failed', 'aborted_budget')).
    Step 2: open evidence read-only (caller passes it in; CLI uses
            open_evidence_readonly per A51), SELECT run_id, skill_id FROM runs
            WHERE run_id IN (...). Match skill_id via the runs.skill_id COLUMN
            (B4) — never config_json, which is an unenforced, potentially-stale
            copy.

    Python-side join per A25 (no cross-DB SQL joins). The
    evidence_conn_ro MUST be read-only (caller's responsibility);
    open_evidence_readonly already exists at storage/migrations.py.

    Sorted by run_progress.last_heartbeat DESC if available (most-recent first).
    """
    # Step 1: find non-terminal run_ids from runtime
    # Fail-closed: a DB error must NOT silently return [] (which would bypass the
    # A52/A54 precondition and allow aggregation to proceed on a corrupted DB).
    # Mirror run_is_complete's fail-closed shape.
    try:
        rows = runtime_conn.execute(
            "SELECT run_id, state, last_heartbeat FROM run_progress "
            "WHERE state NOT IN ('completed', 'failed', 'aborted_budget')"
        ).fetchall()
    except sqlite3.Error as exc:
        raise PreconditionError("recovery_query_failed", None) from exc

    if not rows:
        return []

    # Build a map: run_id -> (state, last_heartbeat)
    run_id_to_runtime: dict[str, tuple[str, str]] = {}
    for row in rows:
        run_id, state, last_heartbeat = row
        run_id_to_runtime[run_id] = (state, last_heartbeat)

    # Step 2: cross-reference with evidence.runs for skill_id filtering
    # Python-layer join — no ATTACH, no cross-DB SQL.
    # Fail-closed: same discipline as Step 1 — DB error raises, never returns [].
    # B4: filter on the runs.skill_id COLUMN, not config_json — the column is
    # authoritative (NOT NULL, FK-enforced, immutable per A20) and is what
    # engine.py's own precondition/discovery queries match against.
    placeholders = ",".join("?" for _ in run_id_to_runtime)
    try:
        ev_rows = evidence_conn_ro.execute(
            f"SELECT run_id, skill_id FROM runs WHERE run_id IN ({placeholders})",  # noqa: S608
            list(run_id_to_runtime.keys()),
        ).fetchall()
    except sqlite3.Error as exc:
        raise PreconditionError("recovery_query_failed", None) from exc

    results: list[IncompleteRun] = []
    for ev_run_id, row_skill_id in ev_rows:
        if row_skill_id != skill_id:
            continue
        state, last_heartbeat = run_id_to_runtime.get(ev_run_id, ("unknown", ""))
        results.append(
            IncompleteRun(
                run_id=ev_run_id,
                state=state,
                skill_id=skill_id,
                last_heartbeat_at=last_heartbeat,
            )
        )

    # Sort most-recent-first by last_heartbeat_at DESC (NOT NULL; str is directly sortable)
    results.sort(key=lambda r: r.last_heartbeat_at, reverse=True)
    return results


def run_is_complete(
    run_id: str,
    *,
    evidence_conn_ro: Connection,
) -> bool:
    """Returns True iff runs.completed_at IS NOT NULL for this run_id.

    Used by Track E.3 `freeze` precondition (refuse if parent incomplete) +
    Track E.2 aggregation entry gate.
    """
    try:
        row = evidence_conn_ro.execute(
            "SELECT completed_at FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    except Exception:
        return False
    if row is None:
        return False
    return row[0] is not None


def find_resumable_run_for_skill(
    skill_id: str,
    *,
    evidence_conn_ro: Connection,
    runtime_conn: Connection,
) -> str | None:
    """Returns the most-recently-heartbeated incomplete run_id for skill_id,
    or None if no incomplete run exists.

    Preserves Track D `run ablation` bare-rerun semantics (CLI uses this to
    name the resumable run_id in its WARN). Delegates to find_incomplete_runs
    + first result.
    """
    runs = find_incomplete_runs(
        skill_id,
        evidence_conn_ro=evidence_conn_ro,
        runtime_conn=runtime_conn,
    )
    if not runs:
        return None
    return runs[0].run_id
