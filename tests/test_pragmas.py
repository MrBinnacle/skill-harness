"""A28 — PRAGMA smoke tests: verify that open_evidence and open_runtime return
connections with the expected PRAGMA settings applied.

The structural enforcement of A23 PRAGMA scope requires:
  - foreign_keys = 1 (enabled) on every fresh connection
  - synchronous = FULL for evidence (durability)
  - synchronous = NORMAL for runtime (re-derivable)
"""

from __future__ import annotations

from pathlib import Path

from skill_harness.storage.migrations import open_evidence, open_runtime


class TestForeignKeysPragma:
    def test_open_evidence_foreign_keys_on(self, tmp_path: Path) -> None:
        """Fresh open_evidence connection must have PRAGMA foreign_keys = 1."""
        conn = open_evidence(tmp_path / "ev.db")
        try:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row is not None
            assert row[0] == 1, f"expected foreign_keys=1, got {row[0]}"
        finally:
            conn.close()

    def test_open_runtime_foreign_keys_on(self, tmp_path: Path) -> None:
        """Fresh open_runtime connection must have PRAGMA foreign_keys = 1."""
        conn = open_runtime(tmp_path / "rt.db")
        try:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row is not None
            assert row[0] == 1, f"expected foreign_keys=1, got {row[0]}"
        finally:
            conn.close()


class TestSynchronousPragma:
    def test_open_evidence_synchronous_full(self, tmp_path: Path) -> None:
        """Evidence DB must open at synchronous=FULL (A22 durability asymmetry)."""
        conn = open_evidence(tmp_path / "ev.db")
        try:
            row = conn.execute("PRAGMA synchronous").fetchone()
            assert row is not None
            # SQLite returns 2 for FULL
            assert row[0] == 2, f"expected synchronous=2 (FULL), got {row[0]}"
        finally:
            conn.close()

    def test_open_runtime_synchronous_normal(self, tmp_path: Path) -> None:
        """Runtime DB must open at synchronous=NORMAL (A22 durability asymmetry)."""
        conn = open_runtime(tmp_path / "rt.db")
        try:
            row = conn.execute("PRAGMA synchronous").fetchone()
            assert row is not None
            # SQLite returns 1 for NORMAL
            assert row[0] == 1, f"expected synchronous=1 (NORMAL), got {row[0]}"
        finally:
            conn.close()
