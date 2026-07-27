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
from typing import Any, Literal, NamedTuple

from skill_harness.storage.models import MetricVersionWrite
from skill_harness.storage.transaction import writer_transaction


class MetricAuditPlan(NamedTuple):
    """What the audit-metric act would do against this store (read-only plan).

    Single source for the act's eligibility logic (S88 K6): the CLI's dry-run
    prints this plan, and :func:`register_audited_metric` executes it — no
    second copy of the refusal conditions exists.
    """

    action: Literal["register", "already_audited"]
    metric_id: str
    version: str
    implementation_hash: str


def plan_audited_metric_registration(conn: sqlite3.Connection, metric_id: str) -> MetricAuditPlan:
    """Plan the audit-metric act against this store (read-only; S88 A-double-prime).

    audited=1 attests: a deliberate operator act registered this metric
    implementation, hash-pinned against the shipped module at execution time
    (K3 — operator-attested, hash-pinned registration; NOT independent
    construct-validity review).

    :raises ValueError: metric_id not registered for the act; an audited=0 row
        already occupies (metric_id, version) (append-only — no in-place flip;
        recovery is a fresh-store re-ingest); or the existing audited row's
        hash no longer matches the live module (implementation drift).
    """
    # Function-local imports: ingest.py imports this module at its top level,
    # so the K1-mandated import direction (hash via ingest's own function,
    # never lifted — Path(__file__) must keep binding to ingest.py) has to be
    # deferred to call time to avoid a circular import.
    from skill_harness.storage.repositories.evidence.frozen_cases import (
        PAIRED_FREEZE_BINARY_METRIC_IDS,
    )
    from skill_harness.subject.ingest import (
        ORACLE_METRIC_VERSION,
        _oracle_implementation_hash,
    )

    if metric_id not in PAIRED_FREEZE_BINARY_METRIC_IDS:
        raise ValueError(
            f"metric {metric_id!r} is not registered for the audit-metric act "
            f"(conservative first cut: the subject scorers with mechanical-validity "
            f"evidence on this path). Registered metric ids: "
            f"{sorted(PAIRED_FREEZE_BINARY_METRIC_IDS)}."
        )

    live_hash = _oracle_implementation_hash()
    existing = get_metric_version(conn, metric_id, ORACLE_METRIC_VERSION)
    if existing is None:
        return MetricAuditPlan("register", metric_id, ORACLE_METRIC_VERSION, live_hash)

    if existing["audited"] != 1:
        raise ValueError(
            f"({metric_id!r}, {ORACLE_METRIC_VERSION!r}) already exists with audited=0 "
            "and metric_versions is append-only — no in-place flip exists by design. "
            "Recovery: run audit-metric --execute against a fresh store FIRST, then "
            "re-ingest the .eval logs into that fresh store (deterministic and offline)."
        )
    if existing["implementation_hash"] != live_hash:
        raise ValueError(
            f"audited row ({metric_id!r}, {ORACLE_METRIC_VERSION!r}) pins implementation_hash "
            f"{existing['implementation_hash']}, but the live module hashes to {live_hash} — "
            "implementation drift. Refusing: bump ORACLE_METRIC_VERSION for the changed "
            "code, or run the code matching the registered hash."
        )
    return MetricAuditPlan("already_audited", metric_id, ORACLE_METRIC_VERSION, live_hash)


def register_audited_metric(conn: sqlite3.Connection, metric_id: str) -> dict[str, Any]:
    """Execute the audit-metric act: insert the audited=1 row (S88 A-double-prime).

    Writes the exact row shape ingest would write, except audited=1 (design
    record §4): version = ORACLE_METRIC_VERSION, hash computed live by
    ingest's own ``_oracle_implementation_hash`` (K1), tier=1, mvtp=1
    (§12.1 evidence = the offline mechanical-validity tests, same claim
    ingest's write site makes), registered_at at ms resolution via ingest's
    ``_utcnow_iso`` (K6).

    Idempotent on the hash-MATCH arm: an existing audited row whose hash
    matches the live module is returned as-is (no second row — the PK would
    refuse anyway). All refusal arms raise via the shared plan.

    Returns the (inserted or existing) row as a dict.

    :raises ValueError: any refusal arm of :func:`plan_audited_metric_registration`.
    """
    from skill_harness.subject.ingest import _utcnow_iso

    plan = plan_audited_metric_registration(conn, metric_id)
    if plan.action == "register":
        with writer_transaction(conn):
            insert_metric_version(
                conn,
                MetricVersionWrite(
                    metric_id=plan.metric_id,
                    version=plan.version,
                    implementation_hash=plan.implementation_hash,
                    tier=1,
                    audited=1,
                    mechanical_validity_test_passed=1,
                    registered_at=_utcnow_iso(),
                ),
            )
    row = get_metric_version(conn, plan.metric_id, plan.version)
    if row is None:  # pragma: no cover — the row was just inserted or found
        raise ValueError(
            f"metric_versions row ({plan.metric_id!r}, {plan.version!r}) vanished mid-act"
        )
    return row


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
    """Return all versions of a metric, ordered by registered_at (deterministic
    tie-break on version — (metric_id, version) is the PK)."""
    cur = conn.execute(
        """
        SELECT metric_id, version, implementation_hash, tier,
               audited, mechanical_validity_test_passed, registered_at
        FROM metric_versions WHERE metric_id = ? ORDER BY registered_at, version
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
        FROM metric_versions WHERE tier = ? ORDER BY metric_id, registered_at, version
        """,
        (tier,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
