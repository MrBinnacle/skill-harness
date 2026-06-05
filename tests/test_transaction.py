"""Unit tests for storage.transaction.writer_transaction.

TDD order: RED (this file) then GREEN (transaction.py).

Tests cover:
- COMMIT path (clean exit commits work)
- ROLLBACK-on-exception path (exception exits roll back)
- suppress-already-rolled-back path (ROLLBACK on a dead transaction is benign)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from skill_harness.storage.migrations import open_evidence
from skill_harness.storage.transaction import writer_transaction


@pytest.fixture()
def plain_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Raw autocommit SQLite connection (no migrations) for transaction unit tests."""
    conn = sqlite3.connect(str(tmp_path / "test.db"), isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("CREATE TABLE t (val TEXT)")
    try:
        yield conn
    finally:
        conn.close()


def test_writer_transaction_commit_path(plain_conn: sqlite3.Connection) -> None:
    """Clean exit from writer_transaction commits the work."""
    with writer_transaction(plain_conn):
        plain_conn.execute("INSERT INTO t VALUES (?)", ("hello",))

    cur = plain_conn.execute("SELECT val FROM t")
    rows = cur.fetchall()
    assert rows == [("hello",)]


def test_writer_transaction_rollback_on_exception(plain_conn: sqlite3.Connection) -> None:
    """Exception inside writer_transaction rolls back — row is absent after."""
    with pytest.raises(ValueError, match="boom"), writer_transaction(plain_conn):
        plain_conn.execute("INSERT INTO t VALUES (?)", ("should_rollback",))
        raise ValueError("boom")

    cur = plain_conn.execute("SELECT val FROM t")
    rows = cur.fetchall()
    assert rows == []


def test_writer_transaction_exception_propagates(plain_conn: sqlite3.Connection) -> None:
    """The original exception is not swallowed — it re-raises after rollback."""
    with pytest.raises(RuntimeError, match="propagate me"), writer_transaction(plain_conn):
        raise RuntimeError("propagate me")


def test_writer_transaction_suppress_already_rolled_back(
    plain_conn: sqlite3.Connection,
) -> None:
    """If SQLite already rolled back (e.g. constraint violation), ROLLBACK in except
    is benign — no second exception is raised from the context manager."""

    # Simulate already-rolled-back state: insert a row, then attempt a duplicate PK
    plain_conn.execute("CREATE TABLE unique_t (id INTEGER PRIMARY KEY, val TEXT)")
    plain_conn.execute("INSERT INTO unique_t VALUES (1, 'original')")

    with pytest.raises(sqlite3.IntegrityError), writer_transaction(plain_conn):
        # This first INSERT works inside the transaction
        plain_conn.execute("INSERT INTO unique_t VALUES (2, 'new')")
        # This raises IntegrityError; SQLite may auto-abort the transaction
        plain_conn.execute("INSERT INTO unique_t VALUES (1, 'duplicate')")

    # Only the original row should survive; the transaction was rolled back
    cur = plain_conn.execute("SELECT id FROM unique_t ORDER BY id")
    assert [r[0] for r in cur.fetchall()] == [1]


def test_writer_transaction_multiple_statements(plain_conn: sqlite3.Connection) -> None:
    """Multiple INSERTs in a single writer_transaction all commit together."""
    with writer_transaction(plain_conn):
        for val in ["a", "b", "c"]:
            plain_conn.execute("INSERT INTO t VALUES (?)", (val,))

    cur = plain_conn.execute("SELECT val FROM t ORDER BY val")
    assert [r[0] for r in cur.fetchall()] == ["a", "b", "c"]


def test_writer_transaction_with_evidence_db(tmp_path: Path) -> None:
    """writer_transaction works correctly against a real evidence DB opened via open_evidence."""
    conn = open_evidence(tmp_path / "evidence.db")
    try:
        # Insert a skill row inside writer_transaction
        with writer_transaction(conn):
            conn.execute(
                "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
                " VALUES (?, ?, ?, ?, ?)",
                ("sk-001", "Test Skill", "/path/to/skill", "abc123" * 10, "2026-01-01T00:00:00Z"),
            )

        cur = conn.execute("SELECT skill_id FROM skills WHERE skill_id = ?", ("sk-001",))
        assert cur.fetchone() is not None
    finally:
        conn.close()
