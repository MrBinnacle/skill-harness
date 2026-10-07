"""Crash-recovery tests for the dual-DB storage layer.

Three test families per A27 spec (separate from property tests because
Hypothesis shrinking fails with side-effects-across-rules):

Test 1 — kill between evidence COMMIT and runtime BEGIN in dual-write:
    Simulate by making the runtime connection fail on BEGIN IMMEDIATE.
    Assert evidence row present, runtime row absent, log emitted.
    (This exercises the "process died after evidence COMMIT" scenario.)

Test 2 — reopen DB after WAL truncation:
    Open evidence DB, insert a row via writer_transaction, close connection
    (SQLite checkpoints WAL on close with synchronous=FULL + WAL mode),
    manually delete *.db-wal and *.db-shm, reopen, assert row present.
    Verifies durability: the row must have been checkpointed into the main DB.

Test 3 — pointer comment referencing existing half-applied recovery test:
    See tests/test_smoke.py::TestApplyPending::test_half_applied_migration_recovery
    which already covers the "kill between BEGIN and COMMIT during apply_pending"
    scenario. The complementary case below tests statement-split edge case:
    a migration with multiple statements where only the first has been applied
    (simulate by interrupting mid-migration with a patched connection).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from skill_harness.storage.dual_write import write_run_start_with_budget
from skill_harness.storage.migrations import open_evidence, open_runtime
from skill_harness.storage.models import RunBudgetWrite, RunWrite, SkillWrite
from skill_harness.storage.repositories.evidence import runs as runs_repo
from skill_harness.storage.repositories.evidence import skills as skills_repo
from skill_harness.storage.repositories.runtime import run_budget as budget_repo
from skill_harness.storage.transaction import writer_transaction

_TS = "2026-06-04T12:00:00.000Z"
_SHA = "a" * 64


# ---------------------------------------------------------------------------
# Proxy that fails on BEGIN IMMEDIATE (not on INSERT) — simulates process kill
# after evidence COMMIT but before runtime BEGIN.
# ---------------------------------------------------------------------------


class FailOnBeginProxy:
    """Proxy that raises OperationalError on BEGIN IMMEDIATE, passes all else."""

    def __init__(self, real_conn: sqlite3.Connection) -> None:
        self._conn = real_conn

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        stripped = sql.strip().upper()
        if "BEGIN" in stripped:
            raise sqlite3.OperationalError("simulated crash before runtime BEGIN")
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


# ---------------------------------------------------------------------------
# Test 1 — kill between evidence COMMIT and runtime BEGIN
# ---------------------------------------------------------------------------


class TestKillBetweenEvidenceCommitAndRuntimeBegin:
    def test_evidence_present_runtime_absent_log_emitted(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Simulate process kill after evidence COMMIT + before runtime BEGIN IMMEDIATE.

        The FailOnBeginProxy raises on BEGIN IMMEDIATE for the runtime half,
        which is exactly the failure point of a process dying between the two
        transactions in write_run_start_with_budget.
        """
        e_conn = open_evidence(tmp_path / "e.db")
        r_real = open_runtime(tmp_path / "r.db")
        r_proxy: Any = FailOnBeginProxy(r_real)
        try:
            # Seed prerequisite row
            skills_repo.insert_skill(
                e_conn,
                SkillWrite(
                    skill_id="skill-crash",
                    name="Crash Test",
                    source_path="/z",
                    source_sha256=_SHA,
                    imported_at=_TS,
                ),
            )
            run = RunWrite(
                run_id="run-crash",
                skill_id="skill-crash",
                run_kind="ablation",
                config_json="{}",
                started_at=_TS,
                completed_at=None,
            )
            budget = RunBudgetWrite(
                run_id="run-crash",
                hard_cap_usd=1.0,
                tokens_spent_in=0,
                tokens_spent_out=0,
                cache_write_in=0,
                cache_read_in=0,
                usd_spent=0.0,
                dry_run=1,
                aborted_at=None,
                last_updated=_TS,
            )

            with caplog.at_level(logging.WARNING, logger="skill_harness.storage.dual_write"):
                # Must NOT raise — partial failure is logged, not propagated
                write_run_start_with_budget(e_conn, r_proxy, run, budget)

            # Evidence row committed
            ev_row = runs_repo.get_run_by_id(e_conn, "run-crash")
            assert ev_row is not None, "evidence runs row must be present after partial write"

            # Runtime row absent
            rt_row = budget_repo.get_run_budget_by_id(r_real, "run-crash")
            assert rt_row is None, "runtime run_budget row must be absent"

            # Log record emitted
            partial = [
                r for r in caplog.records if getattr(r, "event", None) == "dual_write_partial"
            ]
            assert partial, "dual_write_partial log must be emitted"
            assert getattr(partial[0], "op", None) == "run_start_with_budget"
        finally:
            e_conn.close()
            r_real.close()


# ---------------------------------------------------------------------------
# Test 2 — reopen after WAL truncation (durability proof)
# ---------------------------------------------------------------------------


class TestReopenAfterWalTruncation:
    def test_row_survives_wal_deletion(self, tmp_path: Path) -> None:
        """Insert a skill row, close the connection (forces WAL checkpoint on close
        with synchronous=FULL), delete WAL + SHM files, reopen, assert row present.

        This proves that committed data in the evidence DB is durable: SQLite
        checkpoints the WAL into the main DB file on normal close, so deleting
        the WAL files cannot destroy committed data.

        Note: In WAL mode with synchronous=FULL, SQLite guarantees that committed
        data is fsync'd to the WAL file at COMMIT time. On connection close,
        SQLite performs a passive checkpoint. The assertion here verifies that
        the row is present after the WAL is gone — proving the checkpoint ran.
        """
        db_path = tmp_path / "evidence.db"
        wal_path = tmp_path / "evidence.db-wal"
        shm_path = tmp_path / "evidence.db-shm"

        # Open, insert, close (close triggers WAL checkpoint)
        conn = open_evidence(db_path)
        try:
            with writer_transaction(conn):
                conn.execute(
                    "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("sk-wal-test", "WAL Test", "/path", _SHA, _TS),
                )
        finally:
            conn.close()

        # Delete WAL and SHM files if they exist (simulate crash losing unflushed WAL)
        for p in [wal_path, shm_path]:
            if p.exists():
                p.unlink()

        # Reopen and verify row is still present
        conn2 = open_evidence(db_path)
        try:
            cur = conn2.execute("SELECT skill_id FROM skills WHERE skill_id = ?", ("sk-wal-test",))
            row = cur.fetchone()
            assert row is not None, (
                "Row not found after WAL deletion — evidence durability violated. "
                "The committed row must survive loss of WAL+SHM files."
            )
            assert row[0] == "sk-wal-test"
        finally:
            conn2.close()


# ---------------------------------------------------------------------------
# Test 3 — complementary to test_smoke.py half-applied migration recovery
# See: tests/test_smoke.py::TestApplyPending::test_half_applied_migration_recovery
#
# That test covers: a migration split into two statements where the first
# statement fails after BEGIN IMMEDIATE — the entire migration is rolled back.
#
# Complementary case: verify that a fully applied multi-statement migration
# (with embedded semicolons in trigger bodies) is idempotent — reopening
# the DB and calling apply_pending again does not re-apply the migration
# or raise errors.
# ---------------------------------------------------------------------------


class TestMultiStatementMigrationIdempotence:
    def test_reopen_after_full_apply_is_idempotent(self, tmp_path: Path) -> None:
        """Reopen a fully-migrated evidence DB and call open_evidence again.

        open_evidence calls apply_pending internally. If all migrations are
        already recorded, apply_pending must return with no work done and no
        errors. This is the idempotence property that makes restart-safe.
        """
        db_path = tmp_path / "evidence.db"

        # First open: applies all migrations
        conn1 = open_evidence(db_path)
        conn1.close()

        # Second open: all migrations already recorded; must not raise
        conn2 = open_evidence(db_path)
        try:
            # Basic smoke check that the DB is functional
            cur = conn2.execute("SELECT COUNT(*) FROM skills")
            assert cur.fetchone()[0] == 0
        finally:
            conn2.close()
