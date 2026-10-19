"""Concurrent writer serialization test for the evidence DB.

Proves that SQLite's BEGIN IMMEDIATE + 5s busy_timeout absorbs write contention
between two threads without manual locking:

  - Two threads, each with its OWN evidence connection (single-thread-per-connection
    discipline per A26).
  - Each thread writes a DISTINCT skill row inside writer_transaction.
  - Thread 1 holds the writer lock briefly (time.sleep(0.05) between INSERT and
    exit of writer_transaction) to force contention.
  - After both threads complete, both rows must be present.

The test PROVES that no manual threading.Lock is needed for v0.1 — SQLite's own
locking + busy_timeout handles the contention.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.transaction import writer_transaction

_TS = "2026-06-04T12:00:00.000Z"
_SHA = "a" * 64


def _writer_thread(
    db_path: Path,
    skill_id: str,
    errors: list[Exception],
    hold_seconds: float = 0.0,
) -> None:
    """Open a connection, insert a skill row via writer_transaction, close.

    If hold_seconds > 0, sleep inside the transaction to simulate a long-running
    writer (forces contention if two threads race).
    """
    conn = open_evidence(db_path)
    try:
        with writer_transaction(conn):
            conn.execute(
                "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (skill_id, f"Skill {skill_id}", "/path", _SHA, _TS),
            )
            if hold_seconds > 0:
                time.sleep(hold_seconds)
    except Exception as exc:
        errors.append(exc)
    finally:
        conn.close()


class TestConcurrentWritersSerialize:
    def test_two_threads_both_commit(self, tmp_path: Path) -> None:
        """Two threads with separate connections write without raising.

        Thread 1 holds the writer lock for 0.1 s to force Thread 2 to wait
        on BEGIN IMMEDIATE. SQLite's busy_timeout (5000 ms, set in open_db)
        absorbs the wait. Both rows must be present after both joins.
        """
        db_path = tmp_path / "evidence.db"

        # Pre-create the DB with migrations (must happen before threads open it)
        conn_init = open_evidence(db_path)
        conn_init.close()

        errors: list[Exception] = []

        t1 = threading.Thread(
            target=_writer_thread,
            args=(db_path, "skill-thread-1", errors, 0.1),
        )
        t2 = threading.Thread(
            target=_writer_thread,
            args=(db_path, "skill-thread-2", errors, 0.0),
        )

        t1.start()
        # Small delay so t1 acquires the lock first
        time.sleep(0.01)
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not t1.is_alive(), "Thread 1 did not complete within timeout"
        assert not t2.is_alive(), "Thread 2 did not complete within timeout"
        assert errors == [], f"Thread(s) raised: {errors}"

        # Verify both rows are present
        conn_verify = open_evidence(db_path)
        try:
            cur = conn_verify.execute(
                "SELECT skill_id FROM skills WHERE skill_id IN (?, ?) ORDER BY skill_id",
                ("skill-thread-1", "skill-thread-2"),
            )
            rows = [r[0] for r in cur.fetchall()]
            assert rows == ["skill-thread-1", "skill-thread-2"], (
                f"Expected both skill rows; got: {rows}"
            )
        finally:
            conn_verify.close()

    def test_single_thread_baseline(self, tmp_path: Path) -> None:
        """Baseline: single-thread write succeeds (no contention)."""
        db_path = tmp_path / "evidence.db"
        errors: list[Exception] = []

        _writer_thread(db_path, "skill-solo", errors)

        assert errors == []
        conn_verify = open_evidence(db_path)
        try:
            cur = conn_verify.execute(
                "SELECT skill_id FROM skills WHERE skill_id = ?", ("skill-solo",)
            )
            assert cur.fetchone() is not None
        finally:
            conn_verify.close()
