"""Tests for StorageContext context manager."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skill_harness.storage.context import StorageContext


class TestStorageContext:
    def test_opens_both_connections(self, tmp_path: Path) -> None:
        """__enter__ opens and stores both connections."""
        with StorageContext(tmp_path / "e.db", tmp_path / "r.db") as ctx:
            assert isinstance(ctx.evidence_conn, sqlite3.Connection)
            assert isinstance(ctx.runtime_conn, sqlite3.Connection)
            # Basic smoke: can execute on both
            cur = ctx.evidence_conn.execute("SELECT COUNT(*) FROM skills")
            assert cur.fetchone()[0] == 0
            cur2 = ctx.runtime_conn.execute("SELECT COUNT(*) FROM run_budget")
            assert cur2.fetchone()[0] == 0

    def test_closes_connections_on_exit(self, tmp_path: Path) -> None:
        """Connections are closed after the with block exits."""
        with StorageContext(tmp_path / "e.db", tmp_path / "r.db") as ctx:
            e = ctx.evidence_conn
            r = ctx.runtime_conn

        # After __exit__, the connections should be closed.
        # A closed SQLite connection raises ProgrammingError on execute.
        with pytest.raises(Exception):  # ProgrammingError or OperationalError
            e.execute("SELECT 1")
        with pytest.raises(Exception):
            r.execute("SELECT 1")

    def test_closes_both_on_body_exception(self, tmp_path: Path) -> None:
        """Even if the with-body raises, both connections close cleanly."""
        with pytest.raises(ValueError, match="body error"):  # noqa: SIM117
            with StorageContext(tmp_path / "e.db", tmp_path / "r.db") as ctx:
                e = ctx.evidence_conn
                r = ctx.runtime_conn
                raise ValueError("body error")

        # Both connections should still be closed
        with pytest.raises(Exception):
            e.execute("SELECT 1")
        with pytest.raises(Exception):
            r.execute("SELECT 1")

    def test_accepts_string_paths(self, tmp_path: Path) -> None:
        """Paths can be passed as strings, not just Path objects."""
        e_path = str(tmp_path / "e2.db")
        r_path = str(tmp_path / "r2.db")
        with StorageContext(e_path, r_path) as ctx:
            assert isinstance(ctx.evidence_conn, sqlite3.Connection)
            assert isinstance(ctx.runtime_conn, sqlite3.Connection)
