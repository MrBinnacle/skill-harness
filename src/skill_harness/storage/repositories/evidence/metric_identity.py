"""Repository for the #209 implementation-identity bookkeeping (append-only).

Tables from ``migrations/evidence/0800_metric_implementation_identity.sql``:

* ``metric_semantic_digests`` -- which AST identity digest was recorded for a
  given ``(metric_id, version, raw implementation_hash)``.
* ``metric_implementation_restamps`` -- appended compensating records clearing a
  byte-only drift. Resolution is *latest restamp wins, else the registered row*.

The split between classification and appending is deliberate and load-bearing:
``plan_audited_metric_registration`` is documented **read-only**, and it needs the
verdict. So :func:`classify_implementation_drift` performs no writes at all, and
only the writers call :func:`append_implementation_restamp`.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from skill_harness.subject.implementation_identity import IDENTITY_DIGEST_ALGO_VERSION

__all__ = [
    "DriftClassification",
    "append_implementation_restamp",
    "classify_implementation_drift",
    "effective_implementation_hash",
    "record_semantic_digest",
    "recorded_semantic_digest",
]

RESTAMP_REASON = (
    "AST identity digest unchanged: the edit altered comments or formatting only, "
    "so the measurement implementation did not change (#209)"
)


class DriftClassification(NamedTuple):
    """The read-only verdict on a raw-hash drift.

    ``restampable`` False is always a refusal. ``reason`` is written to be shown
    to an operator verbatim, because it is the only place the distinction between
    "this store predates the repair" and "the behaviour actually changed" is
    stated.
    """

    restampable: bool
    reason: str
    metric_id: str
    version: str
    superseded_hash: str
    implementation_hash: str
    semantic_digest: str
    # True when the hash IN FORCE already equals the live module, so there is
    # nothing to repair. Callers must branch on this BEFORE ``restampable``:
    # ``restampable`` is False here too, and treating that as a refusal is the
    # bug this field exists to prevent. The append-only metric_versions row keeps
    # its original hash forever, so after one restamp the ledger hash and the live
    # hash differ permanently while the identity is perfectly settled -- comparing
    # the ledger hash instead of the effective one turns every later check into a
    # refusal. (Caught by the idempotence test, not by review.)
    is_current: bool = False


def record_semantic_digest(
    conn: sqlite3.Connection,
    *,
    metric_id: str,
    version: str,
    implementation_hash: str,
    semantic: str,
) -> None:
    """Record ``(metric_id, version, raw) -> semantic`` if not already present.

    ``INSERT OR IGNORE`` rather than an upsert: the primary key already pins one
    semantic digest per raw digest, and one raw digest cannot correspond to two
    different module bodies. There is nothing to overwrite, and the table's own
    triggers would refuse the attempt in any case.

    Caller supplies the transaction.
    """
    conn.execute(
        "INSERT OR IGNORE INTO metric_semantic_digests "
        "(metric_id, version, implementation_hash, semantic_digest, digest_algo_version) "
        "VALUES (?, ?, ?, ?, ?)",
        (metric_id, version, implementation_hash, semantic, IDENTITY_DIGEST_ALGO_VERSION),
    )


def recorded_semantic_digest(
    conn: sqlite3.Connection, *, metric_id: str, version: str, implementation_hash: str
) -> str | None:
    """The semantic digest recorded for this raw hash, or None.

    Rows carrying a different ``digest_algo_version`` are treated as ABSENT rather
    than as a match. Comparing digests across algorithms is the ambiguous
    canonicalisation the ruling says to fail closed on: two algorithms' outputs
    are not the same measurement, and a coincidental equality would authorise a
    restamp nobody computed.
    """
    row = conn.execute(
        "SELECT semantic_digest FROM metric_semantic_digests "
        "WHERE metric_id = ? AND version = ? AND implementation_hash = ? "
        "AND digest_algo_version = ?",
        (metric_id, version, implementation_hash, IDENTITY_DIGEST_ALGO_VERSION),
    ).fetchone()
    return None if row is None else str(row[0])


def _has_foreign_algo_row(
    conn: sqlite3.Connection, *, metric_id: str, version: str, implementation_hash: str
) -> bool:
    """True when a digest exists for this raw hash but under another algorithm."""
    row = conn.execute(
        "SELECT 1 FROM metric_semantic_digests "
        "WHERE metric_id = ? AND version = ? AND implementation_hash = ? "
        "AND digest_algo_version <> ? LIMIT 1",
        (metric_id, version, implementation_hash, IDENTITY_DIGEST_ALGO_VERSION),
    ).fetchone()
    return row is not None


def effective_implementation_hash(
    conn: sqlite3.Connection, *, metric_id: str, version: str, ledger_hash: str
) -> str:
    """The raw hash currently in force: latest restamp wins, else the registered row.

    This is what makes acceptance idempotent -- once a byte-only edit has been
    restamped, the next check sees no drift at all and appends nothing.
    """
    row = conn.execute(
        "SELECT implementation_hash FROM metric_implementation_restamps "
        "WHERE metric_id = ? AND version = ? AND digest_algo_version = ? "
        "ORDER BY restamp_id DESC LIMIT 1",
        (metric_id, version, IDENTITY_DIGEST_ALGO_VERSION),
    ).fetchone()
    return str(row[0]) if row is not None else ledger_hash


def classify_implementation_drift(
    conn: sqlite3.Connection,
    *,
    metric_id: str,
    version: str,
    recorded_hash: str,
    live_hash: str,
    live_semantic: str,
) -> DriftClassification:
    """Decide whether a raw-hash drift is confined to commentary. READ-ONLY.

    Fails closed on every arm that is not a positive match:

    * no semantic digest recorded for the hash in force -- this store predates the
      repair for that identity, so it holds no evidence the edit was harmless;
    * a digest recorded under a different algorithm version -- ambiguous, and
      never compared across algorithms;
    * digests differ -- the behaviour changed, which is safeguard A working.
    """
    in_force = effective_implementation_hash(
        conn, metric_id=metric_id, version=version, ledger_hash=recorded_hash
    )

    def verdict(*, restampable: bool, reason: str, is_current: bool = False) -> DriftClassification:
        return DriftClassification(
            restampable=restampable,
            reason=reason,
            metric_id=metric_id,
            version=version,
            superseded_hash=in_force,
            implementation_hash=live_hash,
            semantic_digest=live_semantic,
            is_current=is_current,
        )

    if in_force == live_hash:
        return verdict(
            restampable=False,
            is_current=True,
            reason="no drift: the raw hash in force already matches the live module",
        )

    known = recorded_semantic_digest(
        conn, metric_id=metric_id, version=version, implementation_hash=in_force
    )
    if known is None:
        if _has_foreign_algo_row(
            conn, metric_id=metric_id, version=version, implementation_hash=in_force
        ):
            return verdict(
                restampable=False,
                reason=(
                    "refusing: the recorded identity digest was computed by a different "
                    f"algorithm version than {IDENTITY_DIGEST_ALGO_VERSION!r}, so the two "
                    "are not comparable. Digests from different algorithms are never "
                    "compared. Remedy: re-register the metric identity."
                ),
            )
        return verdict(
            restampable=False,
            reason=(
                "refusing: no semantic digest was recorded for the implementation hash "
                f"in force ({in_force[:12]}), so this store predates the #209 repair for "
                "this identity and the edit cannot be shown to be harmless. Remedy: run "
                "the code matching the registered hash, or bump ORACLE_METRIC_VERSION to "
                "declare a new measurement identity."
            ),
        )

    if known != live_semantic:
        return verdict(
            restampable=False,
            reason=(
                "refusing: the AST identity digests differ "
                f"(recorded={known[:12]} live={live_semantic[:12]}), so the measurement "
                "implementation itself changed, not only its commentary. Remedy: bump "
                "ORACLE_METRIC_VERSION for the changed implementation, or run the code "
                "matching the registered hash."
            ),
        )

    return verdict(restampable=True, reason=RESTAMP_REASON)


def append_implementation_restamp(conn: sqlite3.Connection, verdict: DriftClassification) -> None:
    """Append the compensating record clearing a byte-only drift.

    Nothing is rewritten and nothing is removed: the ``metric_versions`` row keeps
    its original hash and its append-only triggers, and the correction is a new
    row in a separate append-only table. Also records the new raw hash's semantic
    digest, so resolution has a uniform lookup on the next check.

    Caller supplies the transaction.

    :raises ValueError: the verdict is not restampable. Appending on a refusal
        would convert a fail-closed decision into a bypass, so it is rejected at
        the boundary rather than trusted to callers.
    """
    if not verdict.restampable:
        raise ValueError(
            f"refusing to append a restamp for a non-restampable drift: {verdict.reason}"
        )
    conn.execute(
        "INSERT INTO metric_implementation_restamps "
        "(metric_id, version, superseded_hash, implementation_hash, semantic_digest, "
        "digest_algo_version, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            verdict.metric_id,
            verdict.version,
            verdict.superseded_hash,
            verdict.implementation_hash,
            verdict.semantic_digest,
            IDENTITY_DIGEST_ALGO_VERSION,
            verdict.reason,
        ),
    )
    record_semantic_digest(
        conn,
        metric_id=verdict.metric_id,
        version=verdict.version,
        implementation_hash=verdict.implementation_hash,
        semantic=verdict.semantic_digest,
    )
