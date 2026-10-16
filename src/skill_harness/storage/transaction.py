"""Single-writer transaction context manager for SQLite connections.

v0.1 single-writer-per-connection mechanism (A26):
SQLite ``BEGIN IMMEDIATE`` + 5-second ``busy_timeout`` (already set in
``open_db()``) is THE writer-exclusion mechanism. No in-process
``queue.Queue`` + writer thread is used. Application discipline: writes
from a single thread per DB connection. A ``threading.Lock`` per
``Connection`` MAY be adopted as belt-and-braces ONLY as a wrapper around
``BEGIN IMMEDIATE`` (not as a queue).
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator


@contextlib.contextmanager
def writer_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Context manager that wraps body in a SQLite ``BEGIN IMMEDIATE`` transaction.

    Enter  = ``BEGIN IMMEDIATE`` (acquires write lock immediately; blocks until
              ``busy_timeout`` if another writer holds the lock).
    Commit = ``COMMIT`` on clean exit.
    Abort  = ``ROLLBACK`` on exception; the ROLLBACK itself is suppressed via
             ``contextlib.suppress(sqlite3.Error)`` because an already-rolled-back
             transaction (e.g. from a constraint violation that auto-aborted the
             transaction) raises ``sqlite3.OperationalError: cannot rollback - no
             transaction is active``, which is benign — the abort already happened.

    v0.1 single-writer mechanism (A26): ``BEGIN IMMEDIATE`` + 5s ``busy_timeout``
    (set in ``open_db()``) is the writer-exclusion primitive. No in-process
    ``queue.Queue`` is involved.

    :param conn: An open ``sqlite3.Connection`` in autocommit mode
                 (``isolation_level=None``).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise
