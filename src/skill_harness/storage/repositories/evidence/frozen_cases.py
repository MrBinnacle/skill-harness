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

# Paired-path (full_vs_null) freeze eligibility — A-prime fallback registry (S86 council
# record — private research notes; summarized in the PRD 'freeze' section).
#
# Under a BINARY metric, a paired obs=1.0 (full_score > null_score with scores in
# {0.0, 1.0}) entails null_score == 0.0 — the Null sample failed the outcome
# oracle ABSOLUTELY, so storing it as a falsifying case is sound. Under a graded
# metric, full > null does NOT entail Null failure (full=0.8 > null=0.6), and
# freezing would mint a poisoned artifact (referee attack, hub-confirmed).
#
# The record's primary design — freeze-time re-execution of the Tier-1 metric on
# sample_b.output_text — is infeasible here: subject-path metrics score SANDBOX
# state (a file read / command exit inside the Inspect sandbox, gone at freeze
# time), while output_text stores the model completion. The record's fallback
# fires instead: eligibility = obs==1.0 AND metric registered as binary; the
# re-verify is pre-registered as the follow-on (needs per-arm scores persisted —
# D22 lane). Registration is in-code because metric_versions is append-only and
# carries no binary/graded flag (adding one is DDL, excluded from A-prime by design).
PAIRED_FREEZE_BINARY_METRIC_IDS: frozenset[str] = frozenset(
    {
        # subject/inspect_adapter.py scorers: CORRECT/INCORRECT only, mapped
        # {C: 1.0, I: 0.0} at ingest — binary by construction.
        "subject:file_contains",
        "subject:command_succeeds",
    }
)


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
    """Promote a freezable verdict into frozen_cases. Returns frozen_case_id.

    Eligibility (validated, raises on violation) — branches on verdict.comparison:

    Ablation path (comparison='full_vs_ablated', unchanged — A56):
    - verdict.observation in {0.0, 0.5}   (FAILING side)

    Paired path (comparison='full_vs_null', A-prime — S86 council record,
    private research notes; normative summary in the PRD 'freeze' section):
    - verdict.observation == 1.0 (winning epoch: Full passed, Null failed)
    - verdict.metric_id in PAIRED_FREEZE_BINARY_METRIC_IDS (binary metrics
      only — see the registry's rationale; graded metrics refuse explicitly)
    - obs=0.5 refuses: without per-arm scores it cannot distinguish a
      both-fail tie (Null genuinely failing) from a both-pass tie (Null
      PASSING — freezing it would store a passing sample as falsifying)
    - obs=0.0 refuses: the Null arm won; sample_b is a passing sample

    Both paths:
    - verdict.admissibility_state == 'admissible'
    - verdict.oracle_source == 'mechanical' (Tier-1 only in v0.1 — A56)
    - verdict's parent runs.completed_at IS NOT NULL (also enforced by BEFORE INSERT trigger)

    A paired frozen case is the Null half of the winning evidence re-encoded,
    NOT independent falsification; anti-vacuity on the paired path is
    discharged by Stage-0 + evidence admissibility (normative — PRD §18 `freeze`).

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
        SELECT verdict_id, run_id, clause_id, axis, comparison,
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
        comparison,
        observation,
        admissibility_state,
        _oracle_tier,
        metric_id,
        metric_version,
        _sample_a_id,
        sample_b_id,
    ) = verdict_row

    # --- eligibility: observation, branched on comparison ---
    if comparison == "full_vs_null":
        # A-prime paired branch: only a winning epoch under a registered-binary
        # metric proves sample_b (the Null arm) failed absolutely.
        if observation != 1.0:
            raise ValueError(
                f"paired (full_vs_null) verdicts freeze only at observation 1.0 "
                f"(winning epoch — Null failed absolutely under a binary metric); "
                f"got {observation!r}. A paired 0.5 may be a both-PASS tie and "
                f"0.0 means the Null arm won — freezing either would store a "
                f"passing Null sample as a falsifying case."
            )
        if metric_id not in PAIRED_FREEZE_BINARY_METRIC_IDS:
            raise ValueError(
                f"paired (full_vs_null) freeze requires a metric registered as "
                f"binary (one of {sorted(PAIRED_FREEZE_BINARY_METRIC_IDS)}); got "
                f"{metric_id!r}. Under a graded metric full > null does not entail "
                f"the Null sample failed — refusing to freeze a possibly-passing "
                f"sample."
            )
    elif observation not in (0.0, 0.5):
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
    """Return all frozen cases for a clause, ordered by frozen_at
    (deterministic tie-break on frozen_case_id)."""
    cur = conn.execute(
        """
        SELECT frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
               oracle_source, labeled_by, labeled_at,
               metric_id, metric_version, implementation_hash, frozen_at,
               verdict_id, run_id, axis
        FROM frozen_cases WHERE clause_id = ? ORDER BY frozen_at, frozen_case_id
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
        FROM frozen_cases WHERE oracle_source = ? ORDER BY frozen_at, frozen_case_id
        """,
        (oracle_source,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
