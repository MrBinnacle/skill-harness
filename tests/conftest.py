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
def evidence_db_for_property_tests(evidence_db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Provide the evidence DB connection for use in Hypothesis property tests.

    This fixture does NOT acquire a SAVEPOINT itself. pytest's fixture scope
    (function-level) and Hypothesis's example loop (many examples per test
    function) make per-example isolation in the fixture impossible: the fixture
    runs once when the test function is invoked, but @given drives many examples
    inside that single function call.

    CALLERS MUST manually wrap each @given body in SAVEPOINT / ROLLBACK TO /
    RELEASE so that examples are isolated from each other:

        conn.execute("SAVEPOINT hyp_example")
        try:
            <test body>
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    See tests/test_hypothesis_savepoint_isolation.py for the canonical pattern.

    Per A28: property tests use this fixture; smoke tests use evidence_db directly.
    """
    yield evidence_db
