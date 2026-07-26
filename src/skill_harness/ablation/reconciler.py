"""Cost reconciler for ablation runs (A41).

Design (A41):
- Per-call token/usd is written onto evidence.samples rows inside the evidence
  transaction (synchronous=FULL). This makes spend durable at power loss.
- runtime.cost_ledger is a PROJECTION written in a separate runtime transaction.
  If a crash occurs between the evidence commit and the runtime commit, the
  cost_ledger will be missing some entries.
- The reconciler detects this gap: sum(evidence.samples.usd WHERE run_id=X)
  vs sum(cost_ledger.usd WHERE run_id=X). If they disagree, the reconciler
  back-fills the cost_ledger from evidence.

This module contains ONLY pure computation + storage access (no API calls).
The runner calls reconcile_run_cost() after completion to ensure consistency.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from skill_harness.storage.models import CostLedgerWrite
from skill_harness.storage.repositories.runtime.cost_ledger import (
    insert_cost_ledger_entry,
)
from skill_harness.storage.transaction import writer_transaction

# ---------------------------------------------------------------------------
# Reconciliation logic
# ---------------------------------------------------------------------------


def get_evidence_cost_sum(evidence_conn: sqlite3.Connection, run_id: str) -> float:
    """Sum usd from evidence.samples for a given run_id (A41 primary source).

    :param evidence_conn: Open evidence DB connection.
    :param run_id: Run to sum costs for.
    :returns: Sum of per-call USD costs from evidence (source of truth).
    """
    cur = evidence_conn.execute(
        "SELECT COALESCE(SUM(usd), 0.0) FROM samples WHERE run_id = ? AND usd IS NOT NULL",
        (run_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row else 0.0


def get_ledger_cost_sum(runtime_conn: sqlite3.Connection, run_id: str) -> float:
    """Sum usd from runtime.cost_ledger for a given run_id (projection).

    :param runtime_conn: Open runtime DB connection.
    :param run_id: Run to sum costs for.
    :returns: Sum of USD costs from the ledger projection.
    """
    cur = runtime_conn.execute(
        "SELECT COALESCE(SUM(usd), 0.0) FROM cost_ledger WHERE run_id = ?",
        (run_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row else 0.0


def reconcile_run_cost(
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    run_id: str,
    model_id: str,
    skill_id: str | None = None,
    *,
    tolerance: float = 1e-6,
) -> bool:
    """Back-fill cost_ledger if evidence sum differs from ledger sum (A41).

    The reconciler:
    1. Sums evidence.samples.usd for the run (source of truth).
    2. Sums runtime.cost_ledger.usd for the run (projection).
    3. If they differ by more than tolerance:
       - Inserts a single catch-up row in cost_ledger with the gap amount.
    4. Returns True if a back-fill was needed, False if already in sync.

    :param evidence_conn: Open evidence DB connection.
    :param runtime_conn: Open runtime DB connection.
    :param run_id: Run to reconcile.
    :param model_id: Model ID for the back-fill ledger entry.
    :param skill_id: Skill ID for the back-fill ledger entry (optional).
    :param tolerance: Absolute difference below which sums are considered equal.
    :returns: True if a back-fill was performed.
    """
    evidence_total = get_evidence_cost_sum(evidence_conn, run_id)
    ledger_total = get_ledger_cost_sum(runtime_conn, run_id)

    gap = evidence_total - ledger_total
    if abs(gap) <= tolerance:
        return False  # Already in sync

    # Back-fill: insert a reconciliation entry covering the gap
    now = datetime.now(UTC).isoformat()
    entry = CostLedgerWrite(
        ts=now,
        run_id=run_id,
        skill_id=skill_id,
        model_id=model_id,
        call_kind="subject",  # cost_ledger.call_kind CHECK (subject|judge)
        input_tok=0,  # tokens already recorded per-sample in evidence
        cache_write_tok=0,
        cache_read_tok=0,
        output_tok=0,
        usd=gap,
    )
    with writer_transaction(runtime_conn):
        insert_cost_ledger_entry(runtime_conn, entry)

    return True


def get_run_samples_with_cost(
    evidence_conn: sqlite3.Connection, run_id: str
) -> list[dict[str, Any]]:
    """Return all sample rows with cost data for a run (A41 re-derivability).

    :param evidence_conn: Open evidence DB connection.
    :param run_id: Run to query.
    :returns: List of sample dicts with cost columns.
    """
    cur = evidence_conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition, sample_index,
               input_tokens, cache_read_input_tokens, cache_creation_input_tokens,
               output_tokens, usd
        FROM samples
        WHERE run_id = ? AND usd IS NOT NULL
        ORDER BY sampled_at, sample_id
        """,
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
