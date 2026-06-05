"""Repository functions for evidence.metric_versions (append-only).

Columns (from migrations/evidence/0001_initial.sql):
    metric_id                     TEXT NOT NULL  (composite PK with version)
    version                       TEXT NOT NULL
    implementation_hash           TEXT NOT NULL
    tier                          INTEGER NOT NULL CHECK (1|2|3)
    audited                       INTEGER NOT NULL DEFAULT 0 CHECK (0|1)
    mechanical_validity_test_passed INTEGER NOT NULL DEFAULT 0 CHECK (0|1)
    registered_at                 TEXT NOT NULL
    PRIMARY KEY (metric_id, version)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from skill_harness.storage.models import MetricVersionWrite


def insert_metric_version(conn: sqlite3.Connection, mv: MetricVersionWrite) -> None:
    """Insert a new metric_version row."""
    conn.execute(
        """
        INSERT INTO metric_versions (
            metric_id, version, implementation_hash, tier,
            audited, mechanical_validity_test_passed, registered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mv.metric_id,
            mv.version,
            mv.implementation_hash,
            mv.tier,
            mv.audited,
            mv.mechanical_validity_test_passed,
            mv.registered_at,
        ),
    )


def get_metric_version(
    conn: sqlite3.Connection, metric_id: str, version: str
) -> dict[str, Any] | None:
    """Return the metric_version row for (metric_id, version), or None."""
    cur = conn.execute(
        """
        SELECT metric_id, version, implementation_hash, tier,
               audited, mechanical_validity_test_passed, registered_at
        FROM metric_versions WHERE metric_id = ? AND version = ?
        """,
        (metric_id, version),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=True))


def list_metric_versions(conn: sqlite3.Connection, metric_id: str) -> list[dict[str, Any]]:
    """Return all versions of a metric, ordered by registered_at."""
    cur = conn.execute(
        """
        SELECT metric_id, version, implementation_hash, tier,
               audited, mechanical_validity_test_passed, registered_at
        FROM metric_versions WHERE metric_id = ? ORDER BY registered_at
        """,
        (metric_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def select_metric_versions_by_tier(conn: sqlite3.Connection, tier: int) -> list[dict[str, Any]]:
    """Return all metric_version rows with a given tier."""
    cur = conn.execute(
        """
        SELECT metric_id, version, implementation_hash, tier,
               audited, mechanical_validity_test_passed, registered_at
        FROM metric_versions WHERE tier = ? ORDER BY metric_id, registered_at
        """,
        (tier,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
