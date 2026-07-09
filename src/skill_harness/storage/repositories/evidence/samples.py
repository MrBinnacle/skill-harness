"""Repository functions for evidence.samples (append-only).

Columns (from migrations/evidence/0001_initial.sql + 0300_track_d_ablation.sql):
    sample_id                   TEXT PRIMARY KEY
    run_id                      TEXT NOT NULL REFERENCES runs
    clause_id                   TEXT NOT NULL REFERENCES clauses
    condition                   TEXT NOT NULL CHECK (full|ablated|null)
    subject_model               TEXT NOT NULL
    subject_seed                TEXT  (nullable)
    output_text                 TEXT NOT NULL
    output_sha256               TEXT NOT NULL
    sampled_at                  TEXT NOT NULL
    sample_index                INTEGER NOT NULL DEFAULT -1  (A40 idempotency key)
    input_tokens                INTEGER DEFAULT NULL         (A41 cost re-derivable)
    cache_read_input_tokens     INTEGER DEFAULT NULL
    cache_creation_input_tokens INTEGER DEFAULT NULL
    output_tokens               INTEGER DEFAULT NULL
    usd                         REAL DEFAULT NULL
    harness_pin_json            TEXT DEFAULT NULL            (0500 v0.2 subject pin)
    harness_pin_fingerprint     TEXT DEFAULT NULL            (0500 v0.2 subject pin)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import SampleWrite


def insert_sample(conn: sqlite3.Connection, sample: SampleWrite) -> None:
    """Insert a new sample row (A40 sample_index + A41 cost + 0500 pin columns)."""
    conn.execute(
        """
        INSERT INTO samples (
            sample_id, run_id, clause_id, condition,
            subject_model, subject_seed, output_text, output_sha256, sampled_at,
            sample_index, input_tokens, cache_read_input_tokens,
            cache_creation_input_tokens, output_tokens, usd,
            harness_pin_json, harness_pin_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample.sample_id,
            sample.run_id,
            sample.clause_id,
            sample.condition,
            sample.subject_model,
            sample.subject_seed,
            sample.output_text,
            sample.output_sha256,
            sample.sampled_at,
            sample.sample_index,
            sample.input_tokens,
            sample.cache_read_input_tokens,
            sample.cache_creation_input_tokens,
            sample.output_tokens,
            sample.usd,
            sample.harness_pin_json,
            sample.harness_pin_fingerprint,
        ),
    )


def get_sample_by_id(conn: sqlite3.Connection, sample_id: str) -> dict[str, Any] | None:
    """Return the sample row as a dict, or None if not found."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE sample_id = ?
        """,
        (sample_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_samples_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Return all samples for a run, ordered by sampled_at."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE run_id = ? ORDER BY sampled_at
        """,
        (run_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_samples_by_condition(
    conn: sqlite3.Connection, run_id: str, condition: str
) -> list[dict[str, Any]]:
    """Return samples for a run filtered by condition."""
    cur = conn.execute(
        """
        SELECT sample_id, run_id, clause_id, condition,
               subject_model, subject_seed, output_text, output_sha256, sampled_at
        FROM samples WHERE run_id = ? AND condition = ? ORDER BY sampled_at
        """,
        (run_id, condition),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
