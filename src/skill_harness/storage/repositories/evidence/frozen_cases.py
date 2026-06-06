"""Repository functions for evidence.frozen_cases (append-only).

Columns (from migrations/evidence/0001_initial.sql + 0400_freeze_provenance.sql):
    frozen_case_id        TEXT PRIMARY KEY
    clause_id             TEXT NOT NULL REFERENCES clauses
    failing_input_text    TEXT NOT NULL
    failing_input_sha256  TEXT NOT NULL
    oracle_source         TEXT NOT NULL CHECK (human|mechanical)
    labeled_by            TEXT  (nullable — required when oracle_source = 'human')
    labeled_at            TEXT  (nullable — required when oracle_source = 'human')
    metric_id             TEXT  (nullable — required when oracle_source = 'mechanical')
    metric_version        TEXT  (nullable — required when oracle_source = 'mechanical')
    implementation_hash   TEXT  (nullable — required when oracle_source = 'mechanical')
    frozen_at             TEXT NOT NULL
    verdict_id            TEXT REFERENCES oracle_verdicts  (nullable — legacy compat, A56)
    run_id                TEXT REFERENCES runs              (nullable — legacy compat, A56)
    axis                  TEXT                              (nullable — legacy compat, A56)
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from skill_harness.storage.models import FrozenCaseWrite


def insert_frozen_case(conn: sqlite3.Connection, case: FrozenCaseWrite) -> None:
    """Insert a new frozen_case row."""
    conn.execute(
        """
        INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, labeled_by, labeled_at,
            metric_id, metric_version, implementation_hash, frozen_at,
            verdict_id, run_id, axis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case.frozen_case_id,
            case.clause_id,
            case.failing_input_text,
            case.failing_input_sha256,
            case.oracle_source,
            case.labeled_by,
            case.labeled_at,
            case.metric_id,
            case.metric_version,
            case.implementation_hash,
            case.frozen_at,
            case.verdict_id,
            case.run_id,
            case.axis,
        ),
    )


def freeze_verdict(
    conn: sqlite3.Connection,
    verdict_id: str,
    oracle_source: str,  # 'mechanical' only in v0.1; v0.2 adds 'human'
    *,
    labeled_by: str | None = None,
    labeled_at: str | None = None,
) -> str:
    """Promote a FAILING verdict into frozen_cases. Returns frozen_case_id.

    Eligibility (validated, raises on violation):
    - verdict.observation in {0.0, 0.5}   (FAILING side)
    - verdict.admissibility_state == 'admissible'
    - verdict.oracle_source == 'mechanical' (Tier-1 only in v0.1 — A56)
    - verdict's parent runs.completed_at IS NOT NULL (also enforced by BEFORE INSERT trigger)

    Idempotent: duplicate freeze (same clause_id, axis, failing_input_sha256) raises
    sqlite3.IntegrityError; the caller (CLI) MAY catch + report 'already frozen'
    with exit 0 per A48 discipline.

    Provenance auto-fill: (metric_id, metric_version, implementation_hash) copied
    from the verdict's metric_versions row at insert time (A3 write-time snapshot).
    failing_input_text derived from samples.output_text (the falsifying side per
    verdict.sample_b_id — the ablated condition sample per TEST-ARCH/SCHEMA).
    """
    # --- eligibility: oracle_source ---
    if oracle_source != "mechanical":
        raise ValueError(f"oracle_source must be 'mechanical' in v0.1 (A56); got {oracle_source!r}")

    # --- fetch verdict ---
    verdict_row = conn.execute(
        """
        SELECT verdict_id, run_id, clause_id, axis,
               observation, admissibility_state,
               oracle_tier, metric_id, metric_version,
               sample_a_id, sample_b_id
        FROM oracle_verdicts WHERE verdict_id = ?
        """,
        (verdict_id,),
    ).fetchone()
    if verdict_row is None:
        raise ValueError(f"verdict_id not found: {verdict_id!r}")

    (
        _vrd_id,
        run_id,
        clause_id,
        axis,
        observation,
        admissibility_state,
        _oracle_tier,
        metric_id,
        metric_version,
        _sample_a_id,
        sample_b_id,
    ) = verdict_row

    # --- eligibility: observation on FAILING side ---
    if observation not in (0.0, 0.5):
        raise ValueError(
            f"verdict.observation must be 0.0 or 0.5 (FAILING side) to freeze; "
            f"got {observation!r}. Winning verdicts (1.0) cannot be frozen."
        )

    # --- eligibility: admissibility ---
    if admissibility_state != "admissible":
        raise ValueError(
            f"verdict.admissibility_state must be 'admissible'; got {admissibility_state!r}"
        )

    # --- eligibility: parent run complete (Python-layer check; trigger also enforces) ---
    run_row = conn.execute("SELECT completed_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None or run_row[0] is None:
        raise ValueError(
            f"parent run {run_id!r} must have completed_at set before freezing a verdict"
        )

    # --- provenance auto-fill from metric_versions (write-time snapshot per A3) ---
    implementation_hash: str | None = None
    if metric_id is not None and metric_version is not None:
        mv_row = conn.execute(
            "SELECT implementation_hash FROM metric_versions WHERE metric_id = ? AND version = ?",
            (metric_id, metric_version),
        ).fetchone()
        if mv_row is not None:
            implementation_hash = mv_row[0]

    # --- failing_input_text from sample_b_id (ablated condition) ---
    sample_row = conn.execute(
        "SELECT output_text, output_sha256 FROM samples WHERE sample_id = ?",
        (sample_b_id,),
    ).fetchone()
    if sample_row is None:
        raise ValueError(f"sample_b_id {sample_b_id!r} not found in samples table")
    failing_input_text, _output_sha256 = sample_row
    failing_input_sha256 = hashlib.sha256(failing_input_text.encode("utf-8")).hexdigest()

    # --- build and insert ---
    frozen_case_id = str(uuid.uuid4())
    frozen_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    case = FrozenCaseWrite(
        frozen_case_id=frozen_case_id,
        clause_id=clause_id,
        failing_input_text=failing_input_text,
        failing_input_sha256=failing_input_sha256,
        oracle_source=oracle_source,
        labeled_by=labeled_by,
        labeled_at=labeled_at,
        metric_id=metric_id,
        metric_version=metric_version,
        implementation_hash=implementation_hash,
        frozen_at=frozen_at,
        verdict_id=verdict_id,
        run_id=run_id,
        axis=axis,
    )
    insert_frozen_case(conn, case)
    return frozen_case_id


def get_frozen_case_by_id(conn: sqlite3.Connection, frozen_case_id: str) -> dict[str, Any] | None:
    """Return the frozen_case row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at,
               verdict_id, run_id, axis
        FROM frozen_cases WHERE frozen_case_id = ?
        """,
        (frozen_case_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_frozen_cases_for_clause(conn: sqlite3.Connection, clause_id: str) -> list[dict[str, Any]]:
    """Return all frozen cases for a clause, ordered by frozen_at."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at,
               verdict_id, run_id, axis
        FROM frozen_cases WHERE clause_id = ? ORDER BY frozen_at
        """,
        (clause_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_frozen_cases_by_oracle_source(
    conn: sqlite3.Connection, oracle_source: str
) -> list[dict[str, Any]]:
    """Return all frozen cases with a given oracle_source."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at,
               verdict_id, run_id, axis
        FROM frozen_cases WHERE oracle_source = ? ORDER BY frozen_at
        """,
        (oracle_source,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
