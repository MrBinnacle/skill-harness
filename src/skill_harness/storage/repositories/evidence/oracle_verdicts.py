"""Repository functions for evidence.oracle_verdicts (append-only).

Columns (from migrations/evidence/0001_initial.sql + 0600_model_snapshot.sql):
    verdict_id              TEXT PRIMARY KEY
    run_id                  TEXT NOT NULL REFERENCES runs
    clause_id               TEXT NOT NULL REFERENCES clauses
    axis                    TEXT NOT NULL
    comparison              TEXT NOT NULL CHECK (full_vs_ablated|full_vs_null)
    sample_a_id             TEXT NOT NULL REFERENCES samples
    sample_b_id             TEXT NOT NULL REFERENCES samples
    observation             REAL NOT NULL CHECK (0.0|0.5|1.0)
    oracle_tier             INTEGER NOT NULL CHECK (1|2|3)
    metric_id               TEXT  (nullable)
    metric_version          TEXT  (nullable)
    judge_id                TEXT REFERENCES judges  (nullable)
    calibration_event_id    TEXT REFERENCES calibration_events  (nullable)
    position_swap_agreement INTEGER CHECK (0|1)  (nullable — NULL for Tier-1)
    admissibility_state     TEXT NOT NULL CHECK (admissible|inadmissible)
    inadmissibility_reason  TEXT  (nullable)
    written_at              TEXT NOT NULL
    model_snapshot          TEXT  (nullable — 0600; pin on new mints)
    response_fingerprint    TEXT  (nullable — 0600; fallback pin)
    requalify_on_drift      INTEGER NOT NULL DEFAULT 0  (0600)
    drift_fingerprint       TEXT  (nullable — 0600; fleet-model drift token)

Write paths (#81):
    mint_oracle_verdict     — guarded new-mint entrypoint (requires ArticleFingerprint)
    insert_oracle_verdict   — raw insert for historical / reconciler / fixtures only

A29 — use get_admissible_verdicts() (queries the VIEW) for aggregation;
      use audit_all_verdicts() in skill_harness.audit for auditing (raw table).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.article_fingerprint import ArticleFingerprint
from skill_harness.storage.models import OracleVerdictWrite


def mint_oracle_verdict(
    conn: sqlite3.Connection,
    verdict: OracleVerdictWrite,
    *,
    pin: ArticleFingerprint,
) -> None:
    """Guarded new-mint entrypoint — requires a valid model pin (#81).

    All newly-minted verdicts MUST go through this function. ``pin`` is an
    ``ArticleFingerprint`` (primary ``model_snapshot``, or response-fingerprint
    fallback with ``requalify_on_drift``); construction of an unpinned fingerprint
    is rejected, so a bare write cannot slip through. Pin columns on ``verdict``
    are overwritten from ``pin``.

    Historical / reconciler inserts that must remain unpinned (#41 no-retrofit)
    use ``insert_oracle_verdict`` directly — not this function. The DB layer
    cannot distinguish new-mint from historical (nullable pin columns), so the
    structural boundary is this entrypoint, not a NOT NULL/CHECK constraint.
    """
    cols = pin.as_verdict_columns()
    pinned = verdict.model_copy(
        update={
            "model_snapshot": cols.model_snapshot,
            "response_fingerprint": cols.response_fingerprint,
            "requalify_on_drift": cols.requalify_on_drift,
            "drift_fingerprint": cols.drift_fingerprint,
        }
    )
    insert_oracle_verdict(conn, pinned)


def insert_oracle_verdict(conn: sqlite3.Connection, verdict: OracleVerdictWrite) -> None:
    """Insert an oracle_verdict row (raw repository write).

    Reserved for historical / reconciler / test-fixture inserts that may omit
    pin columns (#41 no-retrofit). New mints MUST use ``mint_oracle_verdict``.
    """
    conn.execute(
        """
        INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version, judge_id, calibration_event_id,
            position_swap_agreement, admissibility_state, inadmissibility_reason, written_at,
            model_snapshot, response_fingerprint, requalify_on_drift, drift_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            verdict.verdict_id,
            verdict.run_id,
            verdict.clause_id,
            verdict.axis,
            verdict.comparison,
            verdict.sample_a_id,
            verdict.sample_b_id,
            verdict.observation,
            verdict.oracle_tier,
            verdict.metric_id,
            verdict.metric_version,
            verdict.judge_id,
            verdict.calibration_event_id,
            verdict.position_swap_agreement,
            verdict.admissibility_state,
            verdict.inadmissibility_reason,
            verdict.written_at,
            verdict.model_snapshot,
            verdict.response_fingerprint,
            verdict.requalify_on_drift,
            verdict.drift_fingerprint,
        ),
    )


def get_admissible_verdicts(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return admissible, non-confounded verdicts for a run via the VIEW.

    Per A29: reads the admissible_verdicts VIEW (created in migration 0003),
    which enforces both admissibility_state = 'admissible' AND absence of
    confound_events with delta_kind = 'confound_flagged' for the same
    (run_id, primary_clause_id).

    Use this for aggregation. Use audit_all_verdicts() in skill_harness.audit for auditing.
    """
    cur = conn.execute(
        "SELECT * FROM admissible_verdicts WHERE run_id = ?",
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
