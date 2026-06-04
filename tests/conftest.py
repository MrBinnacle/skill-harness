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
