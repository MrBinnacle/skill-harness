"""Dual-DB write helpers for the three known call sites (A25).

Each helper commits to evidence first, then to runtime. This ordering is
evidence-first per A25 (adopted 3-vs-1 over SECURITY's runtime-first framing):
the failure mode is an orphan evidence row with no runtime counterpart — which
is detectable by a reconciler query — rather than a committed runtime row
with no corresponding evidence row, which would be structurally undetectable
from evidence.

Sequence per A25 (verbatim):
    BEGIN IMMEDIATE on evidence → INSERT evidence → COMMIT evidence
                               → BEGIN IMMEDIATE on runtime → INSERT runtime → COMMIT runtime

Each half uses writer_transaction(conn) in its own ``with`` block.
TWO separate ``with`` blocks — NOT nested — so evidence and runtime
transactions never overlap.

On runtime COMMIT failure:
    Caught inside the helper. A structured WARNING is logged with event,
    op, evidence_pk, runtime_table, error_class, error_msg fields.
    The helper does NOT raise. The gap is reconciler-eligible per A25
    (future ``skill audit`` / D7 will detect orphan evidence rows).

On evidence INSERT failure:
    Re-raised. No evidence row was committed; there is nothing to be
    orphaned. The failure is the only correct outcome.

ATTACH DATABASE is forbidden in production paths (A25).
v0.1 enforcement is convention + this docstring; a CI grep ban on ATTACH
may be added in A.4.
"""

from __future__ import annotations

import logging
import sqlite3

from skill_harness.storage.models import (
    CalibrationEventWrite,
    CostLedgerWrite,
    CurrentCalibrationWrite,
    OracleVerdictWrite,
    RunBudgetWrite,
    RunWrite,
)
from skill_harness.storage.repositories.evidence import (
    calibration_events as calib_repo,
)
from skill_harness.storage.repositories.evidence import (
    oracle_verdicts as verdicts_repo,
)
from skill_harness.storage.repositories.evidence import (
    runs as runs_repo,
)
from skill_harness.storage.repositories.runtime import (
    cost_ledger as cost_repo,
)
from skill_harness.storage.repositories.runtime import (
    current_calibration as cal_ptr_repo,
)
from skill_harness.storage.repositories.runtime import (
    run_budget as budget_repo,
)
from skill_harness.storage.transaction import writer_transaction

_log = logging.getLogger("skill_harness.storage.dual_write")

_MAX_ERROR_MSG_CHARS = 500


def write_verdict_with_cost_entry(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    verdict: OracleVerdictWrite,
    cost_entry: CostLedgerWrite,
) -> None:
    """Track D dual-write: append oracle_verdict + append cost_ledger entry.

    **Historical / reconciler-only (#81).** This helper is dormant (zero live
    callers) and deliberately uses the raw ``insert_oracle_verdict`` repository
    path so reconciler and historical backfill inserts may omit pin columns
    (#41 no-retrofit). New verdict mints MUST NOT use this helper — route
    through ``mint_oracle_verdict`` (which requires an ``ArticleFingerprint``).

    Evidence side: INSERT oracle_verdicts (append-only; audit truth).
    Runtime side:  INSERT cost_ledger (operational accounting).

    Evidence-first sequence per A25. On runtime failure the gap is logged and
    the helper returns; the orphan verdict row is reconciler-eligible (D7).
    On evidence failure the exception propagates — no orphan can exist.
    """
    # --- Evidence half ---
    with writer_transaction(evidence_conn):
        # Historical/reconciler path — see docstring (#81). Not a new-mint site.
        verdicts_repo.insert_oracle_verdict(evidence_conn, verdict)

    # --- Runtime half ---
    try:
        with writer_transaction(runtime_conn):
            cost_repo.insert_cost_ledger_entry(runtime_conn, cost_entry)
    except Exception as exc:
        _log.warning(
            "dual_write partial failure: evidence committed, runtime not written",
            extra={
                "event": "dual_write_partial",
                "op": "verdict_with_cost_entry",
                "evidence_pk": verdict.verdict_id,
                "runtime_table": "cost_ledger",
                "error_class": type(exc).__name__,
                "error_msg": str(exc)[:_MAX_ERROR_MSG_CHARS],
            },
        )


def write_run_start_with_budget(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    run: RunWrite,
    budget: RunBudgetWrite,
) -> None:
    """Track D run initialization: append runs row + insert run_budget row.

    Evidence side: INSERT runs (terminal evidence the run started; append-only).
    Runtime side:  INSERT run_budget (mutable counter).

    Evidence-first sequence per A25. On runtime failure the gap is logged;
    the orphan runs row is reconciler-eligible. On evidence failure the
    exception propagates.
    """
    # --- Evidence half ---
    with writer_transaction(evidence_conn):
        runs_repo.insert_run(evidence_conn, run)

    # --- Runtime half ---
    try:
        with writer_transaction(runtime_conn):
            budget_repo.insert_run_budget(runtime_conn, budget)
    except Exception as exc:
        _log.warning(
            "dual_write partial failure: evidence committed, runtime not written",
            extra={
                "event": "dual_write_partial",
                "op": "run_start_with_budget",
                "evidence_pk": run.run_id,
                "runtime_table": "run_budget",
                "error_class": type(exc).__name__,
                "error_msg": str(exc)[:_MAX_ERROR_MSG_CHARS],
            },
        )


def write_calibration_event_with_pointer(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    event: CalibrationEventWrite,
    pointer: CurrentCalibrationWrite,
) -> None:
    """Track C calibration write: append calibration_event + upsert current_calibration.

    Evidence side: INSERT calibration_events (immutable history; append-only).
    Runtime side:  INSERT OR REPLACE current_calibration (mutable pointer to latest
                   calibration for (judge_id, axis)).

    The runtime side is an upsert (INSERT OR REPLACE on the known judge_id+axis PK)
    because the pointer must always reflect the latest calibration event.

    Evidence-first sequence per A25. On runtime failure the gap is logged;
    the orphan calibration_event row is reconciler-eligible. On evidence failure
    the exception propagates.
    """
    # --- Evidence half ---
    with writer_transaction(evidence_conn):
        calib_repo.insert_calibration_event(evidence_conn, event)

    # --- Runtime half ---
    try:
        with writer_transaction(runtime_conn):
            cal_ptr_repo.upsert_current_calibration(runtime_conn, pointer)
    except Exception as exc:
        _log.warning(
            "dual_write partial failure: evidence committed, runtime not written",
            extra={
                "event": "dual_write_partial",
                "op": "calibration_event_with_pointer",
                "evidence_pk": event.calibration_event_id,
                "runtime_table": "current_calibration",
                "error_class": type(exc).__name__,
                "error_msg": str(exc)[:_MAX_ERROR_MSG_CHARS],
            },
        )
