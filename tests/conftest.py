"""Shared pytest fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from skill_harness.storage.migrations import open_evidence, open_runtime


@pytest.fixture()
def evidence_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Fresh append-only evidence DB with all migrations applied."""
    conn = open_evidence(tmp_path / "evidence.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def runtime_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Fresh mutable runtime DB with all migrations applied."""
    conn = open_runtime(tmp_path / "runtime.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def evidence_db_savepoint(evidence_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Provide the evidence DB connection for use in Hypothesis property tests.

    Property tests should wrap EACH @given example body in a per-example
    SAVEPOINT/ROLLBACK envelope so examples are isolated from each other:

        conn.execute("SAVEPOINT hyp_example")
        try:
            <test body>
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    Per A28: property tests use this fixture; smoke tests use evidence_db.
    The per-example SAVEPOINT must be managed inside the @given function body
    because a pytest fixture runs once per test function, not once per Hypothesis
    example.  This fixture guarantees a fresh DB (via evidence_db) and documents
    the required SAVEPOINT usage pattern.
    """
    yield evidence_db
