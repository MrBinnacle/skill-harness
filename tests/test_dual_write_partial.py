"""Fault-injection tests for dual_write helpers.

Per A25 spec: 6 tests total (3 helpers x 2 cases each):
  - Test A: runtime COMMIT failure mid-helper
    * evidence row committed; runtime row absent; log emitted; helper returned without raising
  - Test B: evidence INSERT failure
    * evidence row absent (rolled back); runtime row absent; helper re-raised

Injection strategy:
    sqlite3.Connection.execute is a C built-in — patch.object cannot replace it.
    Instead we use a thin Python proxy class (FailingOnInsertProxy) that wraps
    the real connection, forwards all calls, but raises on INSERT statements.
    The dual_write helpers accept sqlite3.Connection; they only call .execute()
    on the connection, so a proxy that duck-types .execute() satisfies them.

    Because the helpers are typed as sqlite3.Connection, we must patch the
    *reference inside the helpers*. The cleaner approach: pass the proxy
    directly as the connection argument; dual_write does not use isinstance()
    checks, so the duck-typed proxy works without any module patching.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from skill_harness.audit import get_verdict_by_id
from skill_harness.storage.dual_write import (
    write_calibration_event_with_pointer,
    write_run_start_with_budget,
    write_verdict_with_cost_entry,
)
from skill_harness.storage.migrations import open_evidence, open_runtime
from skill_harness.storage.models import (
    CalibrationEventWrite,
    CostLedgerWrite,
    CurrentCalibrationWrite,
    JudgeWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunBudgetWrite,
    RunWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence import (
    calibration_events as calib_repo,
)
from skill_harness.storage.repositories.evidence import (
    judges as judges_repo,
)
from skill_harness.storage.repositories.evidence import (
    metric_versions as mv_repo,
)
from skill_harness.storage.repositories.evidence import (
    runs as runs_repo,
)
from skill_harness.storage.repositories.evidence import (
    skills as skills_repo,
)
from skill_harness.storage.repositories.runtime import (
    cost_ledger as cost_repo,
)
from skill_harness.storage.repositories.runtime import (
    current_calibration as cal_ptr_repo,
)
from skill_harness.storage.repositories.runtime import (
    run_budget as budget_repo,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TS = "2026-06-04T12:00:00.000Z"
_SHA = "a" * 64


# ---------------------------------------------------------------------------
# Proxy class: wraps a real Connection but raises on INSERT statements.
# ---------------------------------------------------------------------------


class FailOnInsertProxy:
    """Thin proxy for sqlite3.Connection that raises OperationalError on INSERT.

    Forwards BEGIN IMMEDIATE, COMMIT, ROLLBACK, and SELECT calls to the real
    connection unchanged. INSERT statements raise the configured error.

    Attributes delegated to the underlying connection so that writer_transaction
    and repo functions that call .execute() work correctly.
    """

    def __init__(
        self, real_conn: sqlite3.Connection, error_msg: str = "simulated INSERT failure"
    ) -> None:
        self._conn = real_conn
        self._error_msg = error_msg

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        stripped = sql.strip().upper()
        if stripped.startswith("INSERT"):
            raise sqlite3.OperationalError(self._error_msg)
        return self._conn.execute(sql, params)

    # Delegate close and other attributes to the real connection
    def close(self) -> None:
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_evidence_for_verdict(conn: sqlite3.Connection) -> None:
    """Insert prerequisite FK rows for oracle_verdicts."""
    skills_repo.insert_skill(
        conn,
        SkillWrite(
            skill_id="skill-1",
            name="Test",
            source_path="/x",
            source_sha256=_SHA,
            imported_at=_TS,
        ),
    )
    mv_repo.insert_metric_version(
        conn,
        MetricVersionWrite(
            metric_id="hedge_index",
            version="1.0.0",
            implementation_hash=_SHA,
            tier=1,
            audited=1,
            mechanical_validity_test_passed=1,
            registered_at=_TS,
        ),
    )
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "clause-1",
            "skill-1",
            0,
            0,
            "Test clause",
            "citation_support",
            "increase",
            1,
            "none",
            _TS,
        ),
    )
    runs_repo.insert_run(
        conn,
        RunWrite(
            run_id="run-1",
            skill_id="skill-1",
            run_kind="ablation",
            config_json="{}",
            started_at=_TS,
            completed_at=None,
        ),
    )
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition, subject_model,"
        " output_text, output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
        ("s1", "run-1", "clause-1", "full", "claude-sonnet-4-6", "text", _SHA, _TS),
    )
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition, subject_model,"
        " output_text, output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
        ("s2", "run-1", "clause-1", "ablated", "claude-sonnet-4-6", "text2", _SHA, _TS),
    )


def _make_verdict() -> OracleVerdictWrite:
    return OracleVerdictWrite(
        verdict_id="v-001",
        run_id="run-1",
        clause_id="clause-1",
        axis="citation_support",
        comparison="full_vs_ablated",
        sample_a_id="s1",
        sample_b_id="s2",
        observation=1.0,
        oracle_tier=1,
        metric_id="hedge_index",
        metric_version="1.0.0",
        judge_id=None,
        calibration_event_id=None,
        position_swap_agreement=None,
        admissibility_state="admissible",
        inadmissibility_reason=None,
        written_at=_TS,
    )


def _make_cost_entry() -> CostLedgerWrite:
    return CostLedgerWrite(
        ts=_TS,
        run_id="run-1",
        skill_id="skill-1",
        model_id="claude-sonnet-4-6",
        call_kind="subject",
        input_tok=100,
        cache_write_tok=10,
        cache_read_tok=5,
        output_tok=50,
        usd=0.001,
    )


def _seed_evidence_for_run(conn: sqlite3.Connection) -> None:
    """Insert prerequisite FK rows for runs."""
    skills_repo.insert_skill(
        conn,
        SkillWrite(
            skill_id="skill-2",
            name="Test2",
            source_path="/y",
            source_sha256=_SHA,
            imported_at=_TS,
        ),
    )


def _make_run() -> RunWrite:
    return RunWrite(
        run_id="run-2",
        skill_id="skill-2",
        run_kind="ablation",
        config_json="{}",
        started_at=_TS,
        completed_at=None,
    )


def _make_budget() -> RunBudgetWrite:
    return RunBudgetWrite(
        run_id="run-2",
        hard_cap_usd=5.0,
        tokens_spent_in=0,
        tokens_spent_out=0,
        cache_write_in=0,
        cache_read_in=0,
        usd_spent=0.0,
        dry_run=1,
        aborted_at=None,
        last_updated=_TS,
    )


def _seed_evidence_for_calibration(conn: sqlite3.Connection) -> None:
    """Insert prerequisite judge row for calibration_events."""
    judges_repo.insert_judge(
        conn,
        JudgeWrite(
            judge_id="judge-1",
            model_id="claude-sonnet-4-6",
            system_prompt_sha256=_SHA,
            created_at=_TS,
        ),
    )


def _make_calib_event() -> CalibrationEventWrite:
    return CalibrationEventWrite(
        calibration_event_id="calib-1",
        judge_id="judge-1",
        axis="citation_support",
        pairwise_agreement=0.85,
        position_consistency=0.90,
        length_controlled_agreement=0.80,
        cohen_kappa=0.70,
        pair_set_size=50,
        pair_set_sha256=_SHA,
        state="calibrated",
        expires_at=None,
        validated_at=_TS,
    )


def _make_calib_pointer() -> CurrentCalibrationWrite:
    return CurrentCalibrationWrite(
        judge_id="judge-1",
        axis="citation_support",
        calibration_event_id="calib-1",
        state="calibrated",
        expires_at=None,
        updated_at=_TS,
    )


# ===========================================================================
# write_verdict_with_cost_entry
# ===========================================================================


class TestWriteVerdictWithCostEntry:
    def test_a_runtime_commit_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test A: cost_ledger INSERT fails — evidence committed, runtime absent, log emitted."""
        e_conn = open_evidence(tmp_path / "e.db")
        r_real = open_runtime(tmp_path / "r.db")
        r_proxy: Any = FailOnInsertProxy(r_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_verdict(e_conn)

            with caplog.at_level(logging.WARNING, logger="skill_harness.storage.dual_write"):
                # helper must NOT raise
                write_verdict_with_cost_entry(e_conn, r_proxy, _make_verdict(), _make_cost_entry())

            # Evidence committed
            row = get_verdict_by_id(e_conn, "v-001")
            assert row is not None, "evidence verdict row must exist after partial write"

            # Runtime absent
            rows = cost_repo.list_cost_ledger_for_run(r_real, "run-1")
            assert rows == [], "runtime cost_ledger row must NOT exist after partial write"

            # Log emitted with required extra fields
            partial_records = [
                r for r in caplog.records if getattr(r, "event", None) == "dual_write_partial"
            ]
            assert partial_records, f"Expected dual_write_partial log; got: {caplog.records}"
            rec = partial_records[0]
            assert getattr(rec, "op", None) == "verdict_with_cost_entry"
            assert getattr(rec, "evidence_pk", None) == "v-001"
            assert getattr(rec, "runtime_table", None) == "cost_ledger"
        finally:
            e_conn.close()
            r_real.close()

    def test_b_evidence_insert_failure(self, tmp_path: Path) -> None:
        """Test B: evidence oracle_verdicts INSERT fails — both absent, helper raises."""
        e_real = open_evidence(tmp_path / "e.db")
        r_conn = open_runtime(tmp_path / "r.db")
        e_proxy: Any = FailOnInsertProxy(e_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_verdict(e_real)

            with pytest.raises(sqlite3.OperationalError, match="simulated INSERT failure"):
                write_verdict_with_cost_entry(e_proxy, r_conn, _make_verdict(), _make_cost_entry())

            # Evidence absent
            row = get_verdict_by_id(e_real, "v-001")
            assert row is None, "evidence verdict row must NOT exist after evidence INSERT failure"

            # Runtime absent
            rows = cost_repo.list_cost_ledger_for_run(r_conn, "run-1")
            assert rows == [], "runtime row must NOT exist (runtime half never started)"
        finally:
            e_real.close()
            r_conn.close()


# ===========================================================================
# write_run_start_with_budget
# ===========================================================================


class TestWriteRunStartWithBudget:
    def test_a_runtime_commit_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test A: run_budget INSERT fails — evidence run committed, runtime absent, log emitted."""
        e_conn = open_evidence(tmp_path / "e.db")
        r_real = open_runtime(tmp_path / "r.db")
        r_proxy: Any = FailOnInsertProxy(r_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_run(e_conn)

            with caplog.at_level(logging.WARNING, logger="skill_harness.storage.dual_write"):
                write_run_start_with_budget(e_conn, r_proxy, _make_run(), _make_budget())

            # Evidence committed
            row = runs_repo.get_run_by_id(e_conn, "run-2")
            assert row is not None, "evidence run row must exist after partial write"

            # Runtime absent
            row_r = budget_repo.get_run_budget_by_id(r_real, "run-2")
            assert row_r is None, "runtime run_budget row must NOT exist after partial write"

            # Log emitted
            partial_records = [
                r for r in caplog.records if getattr(r, "event", None) == "dual_write_partial"
            ]
            assert partial_records, f"Expected dual_write_partial log; got: {caplog.records}"
            rec = partial_records[0]
            assert getattr(rec, "op", None) == "run_start_with_budget"
            assert getattr(rec, "evidence_pk", None) == "run-2"
            assert getattr(rec, "runtime_table", None) == "run_budget"
        finally:
            e_conn.close()
            r_real.close()

    def test_b_evidence_insert_failure(self, tmp_path: Path) -> None:
        """Test B: evidence runs INSERT fails — both absent, helper raises."""
        e_real = open_evidence(tmp_path / "e.db")
        r_conn = open_runtime(tmp_path / "r.db")
        e_proxy: Any = FailOnInsertProxy(e_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_run(e_real)

            with pytest.raises(sqlite3.OperationalError, match="simulated INSERT failure"):
                write_run_start_with_budget(e_proxy, r_conn, _make_run(), _make_budget())

            row = runs_repo.get_run_by_id(e_real, "run-2")
            assert row is None, "evidence run row must NOT exist after evidence INSERT failure"

            row_r = budget_repo.get_run_budget_by_id(r_conn, "run-2")
            assert row_r is None, "runtime row must NOT exist"
        finally:
            e_real.close()
            r_conn.close()


# ===========================================================================
# write_calibration_event_with_pointer
# ===========================================================================


class TestWriteCalibrationEventWithPointer:
    def test_a_runtime_commit_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test A: current_calibration INSERT fails — evidence committed, runtime absent."""
        e_conn = open_evidence(tmp_path / "e.db")
        r_real = open_runtime(tmp_path / "r.db")
        r_proxy: Any = FailOnInsertProxy(r_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_calibration(e_conn)

            with caplog.at_level(logging.WARNING, logger="skill_harness.storage.dual_write"):
                write_calibration_event_with_pointer(
                    e_conn, r_proxy, _make_calib_event(), _make_calib_pointer()
                )

            # Evidence committed
            row = calib_repo.get_calibration_event_by_id(e_conn, "calib-1")
            assert row is not None, "evidence calibration_event must exist after partial write"

            # Runtime absent
            row_r = cal_ptr_repo.get_current_calibration(r_real, "judge-1", "citation_support")
            assert row_r is None, "runtime current_calibration must NOT exist after partial write"

            # Log emitted
            partial_records = [
                r for r in caplog.records if getattr(r, "event", None) == "dual_write_partial"
            ]
            assert partial_records, f"Expected dual_write_partial log; got: {caplog.records}"
            rec = partial_records[0]
            assert getattr(rec, "op", None) == "calibration_event_with_pointer"
            assert getattr(rec, "evidence_pk", None) == "calib-1"
            assert getattr(rec, "runtime_table", None) == "current_calibration"
        finally:
            e_conn.close()
            r_real.close()

    def test_b_evidence_insert_failure(self, tmp_path: Path) -> None:
        """Test B: evidence calibration_events INSERT fails — both absent, helper raises."""
        e_real = open_evidence(tmp_path / "e.db")
        r_conn = open_runtime(tmp_path / "r.db")
        e_proxy: Any = FailOnInsertProxy(e_real, "simulated INSERT failure")
        try:
            _seed_evidence_for_calibration(e_real)

            with pytest.raises(sqlite3.OperationalError, match="simulated INSERT failure"):
                write_calibration_event_with_pointer(
                    e_proxy, r_conn, _make_calib_event(), _make_calib_pointer()
                )

            row = calib_repo.get_calibration_event_by_id(e_real, "calib-1")
            assert row is None, "evidence calibration_event must NOT exist after INSERT failure"

            row_r = cal_ptr_repo.get_current_calibration(r_conn, "judge-1", "citation_support")
            assert row_r is None, "runtime row must NOT exist"
        finally:
            e_real.close()
            r_conn.close()
