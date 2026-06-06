"""Tests for src/skill_harness/storage/recovery.py (A61).

Tests:
- find_incomplete_runs returns only incomplete runs for the given skill_id
- find_incomplete_runs excludes completed/failed/aborted_budget states
- find_incomplete_runs does Python-side join (not cross-DB SQL)
- run_is_complete returns True iff runs.completed_at IS NOT NULL
- find_resumable_run_for_skill returns the most-recent resumable run, or None
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from skill_harness.storage.migrations import open_evidence, open_runtime
from skill_harness.storage.recovery import (
    IncompleteRun,
    find_incomplete_runs,
    find_resumable_run_for_skill,
    run_is_complete,
)

_TS = "2026-06-06T10:00:00.000Z"
_TS2 = "2026-06-06T11:00:00.000Z"
_SHA = "a" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_skill(conn: sqlite3.Connection, skill_id: str) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'S', '/p', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    skill_id: str,
    completed: bool = False,
) -> None:
    completed_at = _TS if completed else None
    config = json.dumps({"skill_id": skill_id})
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (run_id, skill_id, config, _TS, completed_at),
    )


def _insert_run_progress(
    conn: sqlite3.Connection,
    run_id: str,
    state: str = "running",
    last_heartbeat: str = _TS,
) -> None:
    conn.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, ?, 10, 0, ?)",
        (run_id, state, last_heartbeat),
    )


# ---------------------------------------------------------------------------
# Tests: find_incomplete_runs
# ---------------------------------------------------------------------------


class TestFindIncompleteRuns:
    def test_returns_incomplete_run_for_skill(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="running")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 1
            assert results[0].run_id == "run1"
            assert results[0].skill_id == "sk1"
        finally:
            ev.close()
            rt.close()

    def test_excludes_completed_state(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="completed")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 0
        finally:
            ev.close()
            rt.close()

    def test_excludes_failed_state(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="failed")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 0
        finally:
            ev.close()
            rt.close()

    def test_excludes_aborted_budget_state(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="aborted_budget")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 0
        finally:
            ev.close()
            rt.close()

    def test_filters_by_skill_id(self, tmp_path: Path) -> None:
        """Two skills: find_incomplete_runs returns only the queried skill's runs."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_skill(ev, "sk2")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run(ev, "run2", "sk2", completed=False)
            _insert_run_progress(rt, "run1", state="running")
            _insert_run_progress(rt, "run2", state="running")

            results_sk1 = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results_sk1) == 1
            assert results_sk1[0].run_id == "run1"
            assert results_sk1[0].skill_id == "sk1"

            results_sk2 = find_incomplete_runs("sk2", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results_sk2) == 1
            assert results_sk2[0].run_id == "run2"
        finally:
            ev.close()
            rt.close()

    def test_returns_multiple_incomplete_runs(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run(ev, "run2", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="running", last_heartbeat=_TS)
            _insert_run_progress(rt, "run2", state="draining", last_heartbeat=_TS2)

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 2
            run_ids = {r.run_id for r in results}
            assert run_ids == {"run1", "run2"}
        finally:
            ev.close()
            rt.close()

    def test_returns_empty_when_no_incomplete_runs(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=True)
            _insert_run_progress(rt, "run1", state="completed")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert results == []
        finally:
            ev.close()
            rt.close()

    def test_returns_empty_for_unknown_skill(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            results = find_incomplete_runs("nonexistent", evidence_conn_ro=ev, runtime_conn=rt)
            assert results == []
        finally:
            ev.close()
            rt.close()

    def test_result_is_incomplete_run_dataclass(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="pending")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 1
            result = results[0]
            assert isinstance(result, IncompleteRun)
            assert result.run_id == "run1"
            assert result.state == "pending"
            assert result.skill_id == "sk1"
        finally:
            ev.close()
            rt.close()

    def test_pending_state_included(self, tmp_path: Path) -> None:
        """'pending' is non-terminal — must be returned."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="pending")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 1
        finally:
            ev.close()
            rt.close()

    def test_draining_state_included(self, tmp_path: Path) -> None:
        """'draining' is non-terminal — must be returned."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="draining")

            results = find_incomplete_runs("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert len(results) == 1
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: run_is_complete
# ---------------------------------------------------------------------------


class TestRunIsComplete:
    def test_returns_true_when_completed_at_set(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=True)
            assert run_is_complete("run1", evidence_conn_ro=ev) is True
        finally:
            ev.close()

    def test_returns_false_when_completed_at_null(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            assert run_is_complete("run1", evidence_conn_ro=ev) is False
        finally:
            ev.close()

    def test_returns_false_for_unknown_run_id(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        try:
            assert run_is_complete("nonexistent-run", evidence_conn_ro=ev) is False
        finally:
            ev.close()


# ---------------------------------------------------------------------------
# Tests: find_resumable_run_for_skill
# ---------------------------------------------------------------------------


class TestFindResumableRunForSkill:
    def test_returns_none_when_no_incomplete_runs(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            result = find_resumable_run_for_skill("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert result is None
        finally:
            ev.close()
            rt.close()

    def test_returns_run_id_when_one_incomplete(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="running")

            result = find_resumable_run_for_skill("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert result == "run1"
        finally:
            ev.close()
            rt.close()

    def test_returns_first_result_from_find_incomplete_runs(self, tmp_path: Path) -> None:
        """When multiple incomplete runs exist, returns one (first from find_incomplete_runs)."""
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=False)
            _insert_run(ev, "run2", "sk1", completed=False)
            _insert_run_progress(rt, "run1", state="running")
            _insert_run_progress(rt, "run2", state="draining")

            result = find_resumable_run_for_skill("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert result is not None
            assert result in {"run1", "run2"}
        finally:
            ev.close()
            rt.close()

    def test_returns_none_for_unknown_skill(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            result = find_resumable_run_for_skill(
                "nonexistent", evidence_conn_ro=ev, runtime_conn=rt
            )
            assert result is None
        finally:
            ev.close()
            rt.close()

    def test_returns_none_when_only_completed_runs_exist(self, tmp_path: Path) -> None:
        ev = open_evidence(tmp_path / "evidence.db")
        rt = open_runtime(tmp_path / "runtime.db")
        try:
            _insert_skill(ev, "sk1")
            _insert_run(ev, "run1", "sk1", completed=True)
            _insert_run_progress(rt, "run1", state="completed")

            result = find_resumable_run_for_skill("sk1", evidence_conn_ro=ev, runtime_conn=rt)
            assert result is None
        finally:
            ev.close()
            rt.close()
