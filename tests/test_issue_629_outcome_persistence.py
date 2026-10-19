"""Tests for issue #629 -- an ``external_check_missing`` refusal left no row.

Migration 1100 CHECK-constrained ``unmeasured_sub_reason`` to ten literals.
``external_check_missing`` (#555) was added to ``UnmeasuredSubReason`` later and
never reached the CHECK. ``insert_clause_run_outcome`` wrote with
``INSERT OR IGNORE``, and SQLite's OR IGNORE also skips a CHECK violation, so the
refusal was dropped from the evidence store without an error.

These tests pin the repair:

* The CHECK literal list in the live schema equals the enumeration (drift guard).
* An ``external_check_missing`` refusal persists one row naming the sought axis
  in ``sought_oracle``; a ``tier2_uncalibrated`` refusal persists one row with
  ``sought_oracle`` NULL.
* Migration 1300 rebuilds the table without losing a row and keeps both
  append-only triggers.
* A write the store did not keep raises instead of passing silently.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from skill_harness.aggregation.status import UnmeasuredSubReason
from skill_harness.storage.migrations import (
    EVIDENCE_MIGRATIONS_DIR,
    apply_pending,
    discover,
    open_db,
    open_evidence,
    open_runtime,
)
from skill_harness.storage.models import ClauseRunOutcomeWrite, RunWrite
from skill_harness.storage.repositories.evidence.runs import (
    get_clause_run_outcome,
    insert_clause_run_outcome,
    insert_run,
    list_clause_run_outcomes_for_run,
)
from skill_harness.storage.transaction import writer_transaction
from tests.ablation.test_runner import (
    _make_clause,
    _make_runner,
    _seed_clause,
    _seed_skill,
)

_SKILL_ID = "skill-test"
_USER_MSG = "Write a paragraph about testing."
_TS = "2026-09-22T00:00:00.000Z"
_REBUILD_VERSION = 1300

_CHECK_RE = re.compile(
    r"unmeasured_sub_reason\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*unmeasured_sub_reason"
    r"\s+IN\s*\((?P<literals>[^)]*)\)",
    re.IGNORECASE,
)


@pytest.fixture()
def db_pair(tmp_path: Path) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    try:
        _seed_skill(ev)
        yield ev, rt
    finally:
        ev.close()
        rt.close()


def _seed_run_and_clause(ev: sqlite3.Connection, run_id: str, clause_id: str) -> None:
    _seed_clause(ev, _make_clause(clause_id))
    with writer_transaction(ev):
        insert_run(
            ev,
            RunWrite(
                run_id=run_id,
                skill_id=_SKILL_ID,
                run_kind="ablation",
                config_json="{}",
                started_at=_TS,
                completed_at=None,
            ),
        )


def _check_literals(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='clause_run_outcomes'"
    ).fetchone()
    assert row is not None, "clause_run_outcomes is missing from the evidence schema"
    match = _CHECK_RE.search(row[0])
    assert match is not None, f"no unmeasured_sub_reason CHECK found in: {row[0]}"
    return set(re.findall(r"'([^']*)'", match.group("literals")))


def _run_one_clause(
    ev: sqlite3.Connection, rt: sqlite3.Connection, clause: Any, run_id: str
) -> list[Any]:
    runner, _ = _make_runner(ev, rt)
    results: list[Any] = runner.run_ablation(
        skill_id=_SKILL_ID,
        clauses=[clause],
        user_message=_USER_MSG,
        max_usd=10.0,
        run_id=run_id,
    )
    return results


class TestCheckMatchesEnumeration:
    def test_check_literals_equal_unmeasured_sub_reason_members(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, _ = db_pair
        assert _check_literals(ev) == {m.value for m in UnmeasuredSubReason}


class TestRunnerPersistsEveryRefusal:
    def test_external_check_missing_refusal_persists_one_row_naming_the_axis(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = db_pair
        clause = _make_clause(
            "clause-protected",
            "Never delete protected comments.",
            0,
            "protected_comment_deletion",
        )
        _seed_clause(ev, clause)

        results = _run_one_clause(ev, rt, clause, "external-missing-run")
        assert results[0].unmeasured_reason is UnmeasuredSubReason.EXTERNAL_CHECK_MISSING

        outcomes = list_clause_run_outcomes_for_run(ev, "external-missing-run")
        assert len(outcomes) == 1, f"expected one persisted outcome, got {outcomes}"
        assert outcomes[0]["unmeasured_sub_reason"] == "external_check_missing"
        assert outcomes[0]["sought_oracle"] == "protected_comment_deletion"

    def test_tier2_refusal_persists_one_row_without_a_sought_oracle(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, rt = db_pair
        clause = _make_clause("clause-tier2", "Be persuasive.", 0, "verbosity", oracle_tier=2)
        _seed_clause(ev, clause)

        _run_one_clause(ev, rt, clause, "tier2-run")

        outcomes = list_clause_run_outcomes_for_run(ev, "tier2-run")
        assert len(outcomes) == 1, f"expected one persisted outcome, got {outcomes}"
        assert outcomes[0]["unmeasured_sub_reason"] == "tier2_uncalibrated"
        assert outcomes[0]["sought_oracle"] is None


class TestRebuildMigration:
    def test_rebuild_keeps_existing_rows_and_adds_a_null_sought_oracle(
        self, tmp_path: Path
    ) -> None:
        migrations = discover(EVIDENCE_MIGRATIONS_DIR)
        before = [m for m in migrations if m.version <= 1200]
        rebuild = [m for m in migrations if m.version == _REBUILD_VERSION]

        conn = open_db(tmp_path / "evidence.db", synchronous="FULL")
        try:
            apply_pending(conn, before)
            _seed_skill(conn)
            _seed_run_and_clause(conn, "legacy-run", "legacy-clause")
            with writer_transaction(conn):
                conn.execute(
                    "INSERT INTO clause_run_outcomes"
                    " (run_id, clause_id, unmeasured_sub_reason, written_at)"
                    " VALUES (?, ?, ?, ?)",
                    ("legacy-run", "legacy-clause", "tier2_uncalibrated", _TS),
                )

            applied = apply_pending(conn, rebuild)

            assert applied == [f"{_REBUILD_VERSION:04d}_clause_run_outcomes_rebuild"]
            row = get_clause_run_outcome(conn, "legacy-run", "legacy-clause")
            assert row == {
                "run_id": "legacy-run",
                "clause_id": "legacy-clause",
                "unmeasured_sub_reason": "tier2_uncalibrated",
                "written_at": _TS,
                "sought_oracle": None,
            }
        finally:
            conn.close()

    def test_append_only_triggers_still_refuse_update_and_delete(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, _ = db_pair
        _seed_run_and_clause(ev, "ao-run", "ao-clause")
        with writer_transaction(ev):
            insert_clause_run_outcome(
                ev,
                ClauseRunOutcomeWrite(
                    run_id="ao-run",
                    clause_id="ao-clause",
                    unmeasured_sub_reason="tier2_uncalibrated",
                    written_at=_TS,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            ev.execute("UPDATE clause_run_outcomes SET unmeasured_sub_reason = 'no_data'")
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            ev.execute("DELETE FROM clause_run_outcomes")


class TestWriteCannotBeSilentlySkipped:
    def test_a_row_the_check_refuses_raises(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        from skill_harness.storage.errors import ClauseRunOutcomeNotStoredError

        ev, _ = db_pair
        _seed_run_and_clause(ev, "loud-run", "loud-clause")
        outside_the_check = ClauseRunOutcomeWrite.model_construct(
            run_id="loud-run",
            clause_id="loud-clause",
            unmeasured_sub_reason="not_a_member",
            written_at=_TS,
        )

        with pytest.raises(ClauseRunOutcomeNotStoredError, match="loud-clause"):
            insert_clause_run_outcome(ev, outside_the_check)
        assert get_clause_run_outcome(ev, "loud-run", "loud-clause") is None

    def test_an_identical_rewrite_on_resume_is_success(
        self, db_pair: tuple[sqlite3.Connection, sqlite3.Connection]
    ) -> None:
        ev, _ = db_pair
        _seed_run_and_clause(ev, "resume-run", "resume-clause")
        outcome = ClauseRunOutcomeWrite(
            run_id="resume-run",
            clause_id="resume-clause",
            unmeasured_sub_reason="tier2_uncalibrated",
            written_at=_TS,
        )

        insert_clause_run_outcome(ev, outcome)
        insert_clause_run_outcome(ev, outcome)

        assert len(list_clause_run_outcomes_for_run(ev, "resume-run")) == 1
