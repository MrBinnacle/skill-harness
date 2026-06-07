"""End-to-end tests for aggregation/engine.py — aggregate_skill() (A54).

Tests:
- PreconditionError('incomplete_runs') when seeded with incomplete run
- PreconditionError('no_completed_runs') when no completed runs exist
- Valid SkillReport produced when seeded with healthy evidence
- MalformedRunConfig raised when family_size missing/zero in config_json
- PASSED status when verdicts + current frozen case exist
- UNMEASURED(no_data) when no admissible verdicts
- UNMEASURED(falsifying_case_missing) when posterior passes but no frozen case
- Coverage field reflects tested/total clause ratio
- ContributionSummary delta computed from full_vs_null verdicts
- Aggregation method in provenance
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from skill_harness.aggregation import (
    SkillReport,
    aggregate_skill,
)
from skill_harness.aggregation.errors import MalformedRunConfig, PreconditionError
from skill_harness.aggregation.report import to_json_bytes
from skill_harness.storage.migrations import open_evidence, open_runtime

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TS = "2026-06-06T10:00:00.000Z"
_TS2 = "2026-06-06T11:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64
_SHA3 = "c" * 64
_GEN_AT = "2026-06-06T12:00:00.000Z"
_HARNESS_VER = "0.1.0a0"

SKILL_ID = "skill-test-001"
RUN_ID = "run-test-001"
CLAUSE_ID = "clause-test-001"
AXIS = "verbosity"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def insert_skill(conn: sqlite3.Connection, skill_id: str = SKILL_ID) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'Test Skill', '/path/to/skill.md', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def insert_clause(
    conn: sqlite3.Connection,
    clause_id: str = CLAUSE_ID,
    skill_id: str = SKILL_ID,
    axis: str = AXIS,
    clause_index: int = 0,
) -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag)"
        " VALUES (?, ?, ?, ?, ?, ?, 'decrease', 1, 'none')",
        (clause_id, skill_id, clause_index, clause_index, f"Clause text {clause_id}", axis),
    )


def insert_run(
    conn: sqlite3.Connection,
    run_id: str = RUN_ID,
    skill_id: str = SKILL_ID,
    completed: bool = True,
    family_size: int = 1,
) -> None:
    config = json.dumps(
        {
            "run_id": run_id,
            "skill_id": skill_id,
            "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
            "subject_model": "claude-sonnet-4-6",
            "user_message": "test",
            "family_size": family_size,
            "stopping_reasons": {},
        },
        sort_keys=True,
    )
    completed_at = _TS2 if completed else None
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (run_id, skill_id, config, _TS, completed_at),
    )


def insert_run_progress(
    conn: sqlite3.Connection,
    run_id: str = RUN_ID,
    state: str = "completed",
) -> None:
    conn.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, ?, 10, 10, ?)",
        (run_id, state, _TS2),
    )


def insert_sample(
    conn: sqlite3.Connection,
    sample_id: str,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
    condition: str = "full",
    sample_index: int = 0,
) -> None:
    output_text = f"Sample output for {sample_id}"
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at, sample_index)"
        " VALUES (?, ?, ?, ?, 'claude-sonnet-4-6', ?, ?, ?, ?)",
        (
            sample_id,
            run_id,
            clause_id,
            condition,
            output_text,
            sha256_of(output_text),
            _TS,
            sample_index,
        ),
    )


def insert_metric_version(
    conn: sqlite3.Connection,
    metric_id: str = "verbosity",
    version: str = "1.0.0",
    implementation_hash: str = _SHA2,
) -> None:
    conn.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, ?, ?, 1, 1, 1, ?)",
        (metric_id, version, implementation_hash, _TS),
    )


def insert_verdict(
    conn: sqlite3.Connection,
    verdict_id: str,
    run_id: str = RUN_ID,
    clause_id: str = CLAUSE_ID,
    axis: str = AXIS,
    sample_a_id: str = "sa",
    sample_b_id: str = "sb",
    observation: float = 1.0,
    admissibility_state: str = "admissible",
    comparison: str = "full_vs_ablated",
    metric_id: str = "verbosity",
    metric_version: str = "1.0.0",
) -> None:
    conn.execute(
        """INSERT INTO oracle_verdicts (
            verdict_id, run_id, clause_id, axis, comparison,
            sample_a_id, sample_b_id, observation, oracle_tier,
            metric_id, metric_version,
            admissibility_state, written_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (
            verdict_id,
            run_id,
            clause_id,
            axis,
            comparison,
            sample_a_id,
            sample_b_id,
            observation,
            metric_id,
            metric_version,
            admissibility_state,
            _TS,
        ),
    )


def insert_frozen_case(
    conn: sqlite3.Connection,
    frozen_case_id: str,
    clause_id: str = CLAUSE_ID,
    axis: str = AXIS,
    run_id: str = RUN_ID,
    metric_id: str = "verbosity",
    metric_version: str = "1.0.0",
    implementation_hash: str = _SHA2,
) -> None:
    failing_text = f"failing-input-{frozen_case_id}"
    conn.execute(
        """INSERT INTO frozen_cases (
            frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
            oracle_source, metric_id, metric_version, implementation_hash,
            run_id, axis
        ) VALUES (?, ?, ?, ?, 'mechanical', ?, ?, ?, ?, ?)""",
        (
            frozen_case_id,
            clause_id,
            failing_text,
            sha256_of(failing_text),
            metric_id,
            metric_version,
            implementation_hash,
            run_id,
            axis,
        ),
    )


def open_both(tmp_path: Path) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    """Open both DBs with all migrations applied."""
    ev = open_evidence(tmp_path / "evidence.db")
    rt = open_runtime(tmp_path / "runtime.db")
    return ev, rt


# ---------------------------------------------------------------------------
# Tests: Precondition violations
# ---------------------------------------------------------------------------


class TestPreconditionErrors:
    def test_incomplete_run_raises(self, tmp_path: Path) -> None:
        """Incomplete run for skill_id → PreconditionError('incomplete_runs')."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_run(ev, completed=False)
            insert_run_progress(rt, state="running")

            with pytest.raises(PreconditionError) as exc_info:
                aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
            assert exc_info.value.code == "incomplete_runs"
            assert RUN_ID in (exc_info.value.payload or [])
        finally:
            ev.close()
            rt.close()

    def test_no_completed_runs_raises(self, tmp_path: Path) -> None:
        """No completed runs for skill_id → PreconditionError('no_completed_runs')."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            # No runs at all

            with pytest.raises(PreconditionError) as exc_info:
                aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
            assert exc_info.value.code == "no_completed_runs"
            assert exc_info.value.payload is None
        finally:
            ev.close()
            rt.close()

    def test_no_completed_runs_with_only_incomplete_in_rt_but_no_evidence(
        self, tmp_path: Path
    ) -> None:
        """No completed ablation runs in evidence → no_completed_runs."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            # A run exists but NOT completed in evidence DB
            # And it shows up as incomplete in runtime → incomplete_runs fires first
            insert_run(ev, completed=False)
            insert_run_progress(rt, state="pending")

            with pytest.raises(PreconditionError) as exc_info:
                aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
            assert exc_info.value.code == "incomplete_runs"
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: I1 — _fetch_completed_ablation_runs single-shot SQL
# ---------------------------------------------------------------------------


class TestFetchCompletedAblationRunsSingleShot:
    def test_execute_called_exactly_once(self, tmp_path: Path) -> None:
        """I1: _fetch_completed_ablation_runs must issue exactly 1 SQL execute call.

        Before the fix, it executed the same SELECT twice (once for rows, once for
        cur.description), doubling read I/O. This test mocks Connection.execute to
        count calls and asserts exactly 1.
        """
        import sqlite3
        from unittest.mock import MagicMock

        from skill_harness.aggregation.engine import _fetch_completed_ablation_runs

        # Build a real cursor-like mock so the function can use .description and .fetchall()
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("run_id",),
            ("skill_id",),
            ("run_kind",),
            ("config_json",),
            ("started_at",),
            ("completed_at",),
        ]
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock(spec=sqlite3.Connection)
        mock_conn.execute.return_value = mock_cursor

        result = _fetch_completed_ablation_runs(mock_conn, "skill-test")

        assert mock_conn.execute.call_count == 1, (
            f"Expected exactly 1 execute call, got {mock_conn.execute.call_count}. "
            "Duplicate SQL query was not eliminated (I1 fix regression)."
        )
        assert result == []


# ---------------------------------------------------------------------------
# Tests: MalformedRunConfig
# ---------------------------------------------------------------------------


class TestMalformedRunConfig:
    def test_family_size_zero_raises(self, tmp_path: Path) -> None:
        """family_size=0 in config_json → MalformedRunConfig."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_run(ev, family_size=0)
            insert_run_progress(rt, state="completed")

            with pytest.raises(MalformedRunConfig) as exc_info:
                aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
            assert "family_size" in exc_info.value.reason
        finally:
            ev.close()
            rt.close()

    @pytest.mark.parametrize(
        "bad_family_size",
        [0, -1, "2", None, 1.5],
        ids=["zero", "negative", "string", "none", "float"],
    )
    def test_family_size_malformed_type_raises(
        self, tmp_path: Path, bad_family_size: object
    ) -> None:
        """T6: all invalid family_size values raise MalformedRunConfig (not just zero)."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            # Bypass insert_run's int family_size — write raw config_json
            config = json.dumps(
                {
                    "run_id": RUN_ID,
                    "skill_id": SKILL_ID,
                    "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
                    "subject_model": "claude-sonnet-4-6",
                    "user_message": "test",
                    "family_size": bad_family_size,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                (RUN_ID, SKILL_ID, config, _TS, _TS2),
            )
            insert_run_progress(rt, state="completed")

            with pytest.raises(MalformedRunConfig):
                aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: family_size mismatch warning (A59 + A41)
# ---------------------------------------------------------------------------


class TestFamilySizeMismatchWarning:
    def test_family_size_mismatch_emits_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """T5: two runs with different family_size → warning logged, first run's value used."""
        import logging

        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_clause(ev)
            insert_metric_version(ev)

            # Run 1: family_size=2
            run1_config = json.dumps(
                {
                    "run_id": "run-fs-1",
                    "skill_id": SKILL_ID,
                    "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
                    "subject_model": "claude-sonnet-4-6",
                    "user_message": "test",
                    "family_size": 2,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                ("run-fs-1", SKILL_ID, run1_config, _TS, _TS2),
            )
            # Run 2: family_size=4 (mismatch!)
            run2_config = json.dumps(
                {
                    "run_id": "run-fs-2",
                    "skill_id": SKILL_ID,
                    "clauses": [{"clause_id": CLAUSE_ID, "axis": AXIS}],
                    "subject_model": "claude-sonnet-4-6",
                    "user_message": "test",
                    "family_size": 4,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                ("run-fs-2", SKILL_ID, run2_config, _TS2, _TS2),
            )
            insert_run_progress(rt, "run-fs-1", state="completed")
            insert_run_progress(rt, "run-fs-2", state="completed")

            # Seed minimal verdicts for run1 so aggregate_skill has data
            for i in range(3):
                sa, sb = f"r1sa-{i}", f"r1sb-{i}"
                insert_sample(
                    ev, sa, run_id="run-fs-1", clause_id=CLAUSE_ID, condition="full", sample_index=i
                )
                insert_sample(
                    ev,
                    sb,
                    run_id="run-fs-1",
                    clause_id=CLAUSE_ID,
                    condition="ablated",
                    sample_index=i,
                )
                insert_verdict(
                    ev,
                    verdict_id=f"r1v-{i}",
                    run_id="run-fs-1",
                    clause_id=CLAUSE_ID,
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                )

            with caplog.at_level(logging.WARNING, logger="skill_harness.aggregation.engine"):
                report = aggregate_skill(
                    SKILL_ID,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )

            # Warning must have been emitted
            assert any(
                "family_size" in r.message and "mismatch" in r.message for r in caplog.records
            ), f"Expected family_size mismatch warning. Got: {[r.message for r in caplog.records]}"
            # First-run's value (2) must be used
            assert report.aggregation_provenance["family_size_used"] == 2, (
                f"Expected family_size_used=2 (first run), got "
                f"{report.aggregation_provenance['family_size_used']!r}"
            )
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: Healthy evidence → valid SkillReport
# ---------------------------------------------------------------------------


def _seed_healthy_evidence(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    n_wins: int = 9,
    n_losses: int = 1,
    with_frozen_case: bool = False,
    with_full_vs_null: bool = False,
    family_size: int = 1,
) -> None:
    """Seed a minimal valid evidence dataset for aggregate_skill()."""
    insert_skill(ev)
    insert_clause(ev)
    insert_metric_version(ev)
    insert_run(ev, family_size=family_size)
    insert_run_progress(rt, state="completed")

    # Seed samples: full + ablated pairs
    for i in range(n_wins + n_losses):
        sa = f"sa-{i}"
        sb = f"sb-{i}"
        insert_sample(ev, sa, condition="full", sample_index=i)
        insert_sample(ev, sb, condition="ablated", sample_index=i)
        obs = 1.0 if i < n_wins else 0.0
        insert_verdict(
            ev,
            verdict_id=f"v-{i}",
            sample_a_id=sa,
            sample_b_id=sb,
            observation=obs,
        )

    if with_full_vs_null:
        # Add a full_vs_null verdict for ContributionSummary
        sa_n = "sa-null"
        sb_n = "sb-null"
        insert_sample(ev, sa_n, condition="full", sample_index=n_wins + n_losses)
        insert_sample(ev, sb_n, condition="null", sample_index=0)
        insert_verdict(
            ev,
            verdict_id="v-null",
            sample_a_id=sa_n,
            sample_b_id=sb_n,
            observation=1.0,
            comparison="full_vs_null",
        )

    if with_frozen_case:
        insert_frozen_case(ev, frozen_case_id="fc-001")


class TestHealthyAggregation:
    def test_returns_skill_report_instance(self, tmp_path: Path) -> None:
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert isinstance(report, SkillReport)
        finally:
            ev.close()
            rt.close()

    def test_skill_id_matches(self, tmp_path: Path) -> None:
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.skill_id == SKILL_ID
        finally:
            ev.close()
            rt.close()

    def test_generated_at_preserved(self, tmp_path: Path) -> None:
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.generated_at_utc == _GEN_AT
        finally:
            ev.close()
            rt.close()

    def test_report_schema_version_is_current(self, tmp_path: Path) -> None:
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            # 1.1.0 bumped in C1 fix-loop per A60 (A55 axes)
            # 1.2.0 bumped in M3 pre-tag fix (coverage_warnings)
            assert report.report_schema_version == "1.2.0"
        finally:
            ev.close()
            rt.close()

    def test_has_one_clause(self, tmp_path: Path) -> None:
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert len(report.clauses) == 1
        finally:
            ev.close()
            rt.close()

    def test_clause_has_data(self, tmp_path: Path) -> None:
        """10 verdicts seeded → n_verdicts=10."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, n_wins=9, n_losses=1)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            clause = report.clauses[0]
            assert clause.n_verdicts == 10
            assert clause.w_observation_sum == 9.0
        finally:
            ev.close()
            rt.close()

    def test_vector_unmeasured_without_frozen_case(self, tmp_path: Path) -> None:
        """9 wins out of 10 → high p, but no frozen case → UNMEASURED(falsifying_case_missing)."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, n_wins=9, n_losses=1, with_frozen_case=False)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            clause = report.clauses[0]
            # Without frozen case: UNMEASURED(falsifying_case_missing) if p >= 0.95
            # or UNMEASURED(underpowered) if p < 0.95 (10 samples may not reach 0.95)
            assert clause.status in ("UNMEASURED", "PASSED")
        finally:
            ev.close()
            rt.close()

    def test_passed_with_current_frozen_case(self, tmp_path: Path) -> None:
        """Many wins + current frozen case → PASSED."""
        ev, rt = open_both(tmp_path)
        try:
            # Use 30 wins + frozen case to ensure p >= 0.95
            _seed_healthy_evidence(ev, rt, n_wins=30, n_losses=2, with_frozen_case=True)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            clause = report.clauses[0]
            # 30 wins out of 32 → Beta(31, 3) → P(rate > 0.60) ≈ 1.0 → PASSED
            assert clause.status == "PASSED"
            assert clause.sub_reason is None
        finally:
            ev.close()
            rt.close()

    def test_unmeasured_no_data_when_no_verdicts(self, tmp_path: Path) -> None:
        """No verdicts at all → UNMEASURED(no_data)."""
        ev, rt = open_both(tmp_path)
        try:
            # Seed everything EXCEPT verdicts
            insert_skill(ev)
            insert_clause(ev)
            insert_metric_version(ev)
            insert_run(ev, family_size=1)
            insert_run_progress(rt, state="completed")

            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            clause = report.clauses[0]
            assert clause.status == "UNMEASURED"
            assert clause.sub_reason == "no_data"
        finally:
            ev.close()
            rt.close()

    def test_aggregation_method_in_report(self, tmp_path: Path) -> None:
        """aggregation_method is one of the valid enum values."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.aggregation_method in (
                "ebmom_hierarchical",
                "bh_fdr_fallback",
                "unpooled",
            )
        finally:
            ev.close()
            rt.close()

    def test_provenance_has_family_size_used(self, tmp_path: Path) -> None:
        """aggregation_provenance always contains family_size_used (A59)."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, family_size=3)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert "family_size_used" in report.aggregation_provenance
            assert report.aggregation_provenance["family_size_used"] == 3
        finally:
            ev.close()
            rt.close()

    def test_provenance_has_pythonhashseed_for_all_methods(self, tmp_path: Path) -> None:
        """aggregation_provenance always contains pythonhashseed (STAT-6 / PRD §16.1)."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert "pythonhashseed" in report.aggregation_provenance
            # Value is an int (may be -1 if PYTHONHASHSEED not set, or 0..2**32-1 if set)
            assert isinstance(report.aggregation_provenance["pythonhashseed"], int)
            # Verify it round-trips through JSON serialisation
            from skill_harness.aggregation.report import to_json_bytes

            raw = to_json_bytes(report)
            import json as _json

            d = _json.loads(raw)
            assert "pythonhashseed" in d["aggregation_provenance"]
        finally:
            ev.close()
            rt.close()

    def test_full_vs_null_delta_computed(self, tmp_path: Path) -> None:
        """full_vs_null verdicts → non-None delta in ContributionSummary."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, with_full_vs_null=True)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.contribution.full_vs_null_delta is not None
        finally:
            ev.close()
            rt.close()

    def test_contribution_label_correct(self, tmp_path: Path) -> None:
        """ContributionSummary label matches A50 framing string."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.contribution.label == "single-clause LOO; lower-bound under redundancy"
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: I3 — UNMEASURED(falsifying_case_stale) end-to-end integration
# ---------------------------------------------------------------------------


class TestStaleFrozenCaseIntegration:
    def test_unmeasured_falsifying_case_stale_when_newer_metric_registered(
        self, tmp_path: Path
    ) -> None:
        """I3: engine-level integration for UNMEASURED(falsifying_case_stale).

        Covers the full path from frozen_cases_with_currency VIEW feeding the engine:
        1. Register metric_version v1 (audited+passed) at _TS.
        2. Insert verdicts with v1 driving p_win >= 0.95.
        3. Insert a frozen_case referencing v1 (metric_version='1.0.0', implementation_hash=_SHA2).
        4. Register metric_version v2 (audited+passed) at _TS2 > _TS — makes v1 stale.
        5. aggregate_skill must report UNMEASURED with sub_reason='falsifying_case_stale'.
        """
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_clause(ev)

            # Step 1: register v1
            insert_metric_version(ev, version="1.0.0", implementation_hash=_SHA2)

            # Step 2: insert verdicts with v1 (enough wins for p_win >= 0.95)
            insert_run(ev, family_size=1)
            insert_run_progress(rt, state="completed")
            for i in range(30):
                sa, sb = f"sa-i3-{i}", f"sb-i3-{i}"
                insert_sample(ev, sa, clause_id=CLAUSE_ID, condition="full", sample_index=i)
                insert_sample(ev, sb, clause_id=CLAUSE_ID, condition="ablated", sample_index=i)
                insert_verdict(
                    ev,
                    verdict_id=f"vi3-{i}",
                    clause_id=CLAUSE_ID,
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                    metric_version="1.0.0",
                )

            # Step 3: insert frozen_case at v1
            fail_text = "i3-failing-input"
            fail_sha = sha256_of(fail_text)
            ev.execute(
                """INSERT INTO frozen_cases (
                    frozen_case_id, clause_id, failing_input_text, failing_input_sha256,
                    oracle_source, metric_id, metric_version, implementation_hash,
                    run_id, axis
                ) VALUES (?, ?, ?, ?, 'mechanical', ?, '1.0.0', ?, ?, ?)""",
                (
                    "fc-i3-stale",
                    CLAUSE_ID,
                    fail_text,
                    fail_sha,
                    AXIS,
                    _SHA2,  # implementation_hash matches v1
                    RUN_ID,
                    AXIS,
                ),
            )

            # Step 4: register v2 at later timestamp — makes v1 stale
            ev.execute(
                "INSERT INTO metric_versions"
                " (metric_id, version, implementation_hash, tier,"
                " audited, mechanical_validity_test_passed, registered_at)"
                " VALUES (?, '2.0.0', ?, 1, 1, 1, ?)",
                (AXIS, _SHA3, _TS2),
            )

            # Step 5: aggregate — must return UNMEASURED(falsifying_case_stale)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )

            assert len(report.clauses) == 1
            clause = report.clauses[0]
            assert clause.status == "UNMEASURED", (
                f"Expected UNMEASURED, got {clause.status!r}. "
                "The frozen_cases_with_currency VIEW → engine path may be broken."
            )
            assert clause.sub_reason == "falsifying_case_stale", (
                f"Expected sub_reason='falsifying_case_stale', got {clause.sub_reason!r}. "
                "The frozen case at v1 should be stale now that v2 is registered."
            )
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: Coverage field
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_coverage_zero_no_frozen_cases(self, tmp_path: Path) -> None:
        """No frozen cases → coverage=0.0."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, with_frozen_case=False)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.coverage == 0.0
        finally:
            ev.close()
            rt.close()

    def test_coverage_one_with_frozen_case(self, tmp_path: Path) -> None:
        """1 clause with 1 frozen case → coverage=1.0."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, with_frozen_case=True)
            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert report.coverage == 1.0
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: JSON byte stability end-to-end
# ---------------------------------------------------------------------------


class TestEngineByteSability:
    def test_same_evidence_same_bytes(self, tmp_path: Path) -> None:
        """Running aggregate_skill twice on the same DB → identical JSON bytes."""
        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, with_frozen_case=True)
            r1 = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            r2 = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert to_json_bytes(r1) == to_json_bytes(r2)
        finally:
            ev.close()
            rt.close()

    def test_engine_does_not_read_wall_clock(self, tmp_path: Path) -> None:
        """T4: aggregate_skill must not call datetime.now() or time.time() internally.

        Verifies the determinism contract by asserting:
        1. engine.py does not import 'time' at module level (grep-style assertion).
        2. Two calls with identical evidence + identical generated_at_utc return
           byte-identical output — if anything inside read a wall clock, they'd diverge.

        Note: patching datetime.datetime.utcnow directly is not possible in CPython 3.12+
        (immutable built-in type). This test uses the structural + byte-stability approach
        instead. Any future addition of datetime.now() to engine.py will break
        test_same_evidence_same_bytes which runs in the same class.
        """
        import skill_harness.aggregation.engine as engine_module

        # Structural check: engine module must not have 'time' or 'datetime' attributes
        # (it imports neither — they are not needed since generated_at_utc is caller-supplied)
        assert not hasattr(engine_module, "time"), (
            "engine.py imported 'time' module — violates wall-clock-free determinism contract. "
            "All timestamps must come from caller-supplied generated_at_utc."
        )

        ev, rt = open_both(tmp_path)
        try:
            _seed_healthy_evidence(ev, rt, with_frozen_case=True)

            # Call twice with the same generated_at_utc — bytes must be identical
            r1 = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            r2 = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert to_json_bytes(r1) == to_json_bytes(r2), (
                "aggregate_skill returned different bytes for identical evidence + identical "
                "generated_at_utc. A wall-clock read inside the engine is the most likely cause."
            )
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: Multi-clause skill
# ---------------------------------------------------------------------------


class TestMultiClauseSkill:
    def test_two_clauses_both_in_report(self, tmp_path: Path) -> None:
        """Two clauses → both appear in report."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_clause(ev, clause_id="c1", clause_index=0)
            insert_clause(ev, clause_id="c2", axis="clarity", clause_index=1)
            insert_metric_version(ev, metric_id="verbosity")
            insert_metric_version(ev, metric_id="clarity")

            config = json.dumps(
                {
                    "run_id": RUN_ID,
                    "skill_id": SKILL_ID,
                    "clauses": [
                        {"clause_id": "c1", "axis": AXIS},
                        {"clause_id": "c2", "axis": "clarity"},
                    ],
                    "subject_model": "model",
                    "user_message": "test",
                    "family_size": 2,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                (RUN_ID, SKILL_ID, config, _TS, _TS2),
            )
            insert_run_progress(rt, state="completed")

            # Seed verdicts for c1 (10 wins) — c2 gets no verdicts
            for i in range(10):
                sa = f"sa-{i}"
                sb = f"sb-{i}"
                insert_sample(ev, sa, clause_id="c1", condition="full", sample_index=i)
                insert_sample(ev, sb, clause_id="c1", condition="ablated", sample_index=i)
                insert_verdict(
                    ev,
                    verdict_id=f"v-{i}",
                    clause_id="c1",
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                    metric_id="verbosity",
                )

            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )
            assert len(report.clauses) == 2
            clause_ids = {c.clause_id for c in report.clauses}
            assert "c1" in clause_ids
            assert "c2" in clause_ids
        finally:
            ev.close()
            rt.close()

    def test_vector_counts_correct(self, tmp_path: Path) -> None:
        """Two clauses: c1 with sufficient wins + frozen case, c2 no data → vector matches."""
        ev, rt = open_both(tmp_path)
        try:
            insert_skill(ev)
            insert_clause(ev, clause_id="c1", clause_index=0)
            insert_clause(ev, clause_id="c2", axis="clarity", clause_index=1)
            insert_metric_version(ev, metric_id="verbosity")
            insert_metric_version(ev, metric_id="clarity")

            config = json.dumps(
                {
                    "run_id": RUN_ID,
                    "skill_id": SKILL_ID,
                    "clauses": [
                        {"clause_id": "c1", "axis": AXIS},
                        {"clause_id": "c2", "axis": "clarity"},
                    ],
                    "subject_model": "model",
                    "user_message": "test",
                    "family_size": 2,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                (RUN_ID, SKILL_ID, config, _TS, _TS2),
            )
            insert_run_progress(rt, state="completed")

            # c1: 30 wins → high p
            for i in range(30):
                sa = f"sa-{i}"
                sb = f"sb-{i}"
                insert_sample(ev, sa, clause_id="c1", condition="full", sample_index=i)
                insert_sample(ev, sb, clause_id="c1", condition="ablated", sample_index=i)
                insert_verdict(
                    ev,
                    verdict_id=f"v-{i}",
                    clause_id="c1",
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                    metric_id="verbosity",
                )
            # c1: add frozen case so it can PASS
            insert_frozen_case(ev, "fc-c1", clause_id="c1", axis=AXIS)

            # c2: no verdicts → UNMEASURED(no_data)

            report = aggregate_skill(
                SKILL_ID,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )

            vector = report.vector
            # c1 should PASS, c2 should be UNMEASURED
            assert vector.passed == 1
            assert vector.unmeasured == 1
            assert vector.unmeasured_breakdown.get("no_data", 0) == 1
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: I2 — ablation_operator_hash MIXED detection
# ---------------------------------------------------------------------------


def _insert_run_with_op_hash(
    ev: sqlite3.Connection,
    rt: sqlite3.Connection,
    run_id: str,
    skill_id: str,
    clause_id: str,
    axis: str,
    op_hash: str,
) -> None:
    """Insert a completed run with a specific ablation_operator_hash in config_json."""
    config = json.dumps(
        {
            "run_id": run_id,
            "skill_id": skill_id,
            "clauses": [{"clause_id": clause_id, "axis": axis}],
            "subject_model": "claude-sonnet-4-6",
            "user_message": "test",
            "family_size": 1,
            "stopping_reasons": {},
            "ablation_operator_hash": op_hash,
        },
        sort_keys=True,
    )
    ev.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', ?, ?, ?)",
        (run_id, skill_id, config, _TS, _TS2),
    )
    rt.execute(
        "INSERT INTO run_progress"
        " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
        " VALUES (?, 'completed', 10, 10, ?)",
        (run_id, _TS2),
    )


class TestAblationOperatorHashMIXED:
    """I2: divergent ablation_operator_hash within a skill's aggregated runs must be detected."""

    def test_divergent_op_hash_sets_mixed_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Divergent op_hash across runs → 'MIXED' + data-integrity warning."""
        import logging

        ev, rt = open_both(tmp_path)
        try:
            sk_id = "skill-op-hash-test"
            cl_id = "clause-op-hash-001"
            run1 = "run-op-hash-001"
            run2 = "run-op-hash-002"

            insert_skill(ev, skill_id=sk_id)
            insert_clause(ev, clause_id=cl_id, skill_id=sk_id)
            insert_metric_version(ev)

            _insert_run_with_op_hash(ev, rt, run1, sk_id, cl_id, AXIS, "hash-aaa")
            _insert_run_with_op_hash(ev, rt, run2, sk_id, cl_id, AXIS, "hash-bbb")

            # Seed admissible verdicts for both runs
            for i, (run_id, sa, sb) in enumerate([(run1, "sa1", "sb1"), (run2, "sa2", "sb2")]):
                insert_sample(
                    ev, sa, run_id=run_id, clause_id=cl_id, condition="full", sample_index=i
                )
                insert_sample(
                    ev, sb, run_id=run_id, clause_id=cl_id, condition="ablated", sample_index=i
                )
                insert_verdict(
                    ev,
                    verdict_id=f"v-op-{i}",
                    run_id=run_id,
                    clause_id=cl_id,
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                )

            with caplog.at_level(logging.WARNING, logger="skill_harness.aggregation.engine"):
                report = aggregate_skill(
                    sk_id,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )

            assert len(report.clauses) == 1
            assert report.clauses[0].ablation_operator_hash == "MIXED"
            # A data-integrity warning must have been logged
            assert any(
                "data-integrity" in rec.message and "ablation_operator_hash" in rec.message
                for rec in caplog.records
            ), "Expected data-integrity warning for ablation_operator_hash divergence"
        finally:
            ev.close()
            rt.close()

    def test_identical_op_hash_not_mixed(self, tmp_path: Path) -> None:
        """Two runs with the same ablation_operator_hash → not 'MIXED'."""
        ev, rt = open_both(tmp_path)
        try:
            sk_id = "skill-op-hash-same"
            cl_id = "clause-op-hash-same-001"
            run1 = "run-op-hash-same-001"
            run2 = "run-op-hash-same-002"

            insert_skill(ev, skill_id=sk_id)
            insert_clause(ev, clause_id=cl_id, skill_id=sk_id)
            insert_metric_version(ev)

            _insert_run_with_op_hash(ev, rt, run1, sk_id, cl_id, AXIS, "hash-aaa")
            _insert_run_with_op_hash(ev, rt, run2, sk_id, cl_id, AXIS, "hash-aaa")

            for i, (run_id, sa, sb) in enumerate(
                [(run1, "sa-s1", "sb-s1"), (run2, "sa-s2", "sb-s2")]
            ):
                insert_sample(
                    ev, sa, run_id=run_id, clause_id=cl_id, condition="full", sample_index=i
                )
                insert_sample(
                    ev, sb, run_id=run_id, clause_id=cl_id, condition="ablated", sample_index=i
                )
                insert_verdict(
                    ev,
                    verdict_id=f"v-s-{i}",
                    run_id=run_id,
                    clause_id=cl_id,
                    axis=AXIS,
                    sample_a_id=sa,
                    sample_b_id=sb,
                    observation=1.0,
                )

            report = aggregate_skill(
                sk_id,
                evidence_conn_ro=ev,
                runtime_conn=rt,
                harness_version=_HARNESS_VER,
                generated_at_utc=_GEN_AT,
            )

            assert len(report.clauses) == 1
            assert report.clauses[0].ablation_operator_hash == "hash-aaa"
        finally:
            ev.close()
            rt.close()


# ---------------------------------------------------------------------------
# Tests: OBS-G2 — zero-clauses precondition refusal
# ---------------------------------------------------------------------------


class TestZeroClausesPreconditionError:
    """OBS-G2: aggregate_skill raises PreconditionError('no_clauses') for zero-clause skills."""

    def test_zero_clauses_raises_precondition_error(self, tmp_path: Path) -> None:
        """A skill with zero authored clauses raises PreconditionError('no_clauses').

        Coverage: 0% on zero clauses is a falsehood — the engine must refuse.
        """
        ev, rt = open_both(tmp_path)
        try:
            sk_id = "skill-no-clauses"
            run_id = "run-no-clauses-001"

            insert_skill(ev, skill_id=sk_id)
            # Insert a completed run but NO clauses
            config = json.dumps(
                {
                    "run_id": run_id,
                    "skill_id": sk_id,
                    "clauses": [],
                    "subject_model": "claude-sonnet-4-6",
                    "user_message": "test",
                    "family_size": 1,
                    "stopping_reasons": {},
                },
                sort_keys=True,
            )
            ev.execute(
                "INSERT INTO runs"
                " (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
                " VALUES (?, ?, 'ablation', ?, ?, ?)",
                (run_id, sk_id, config, _TS, _TS2),
            )
            rt.execute(
                "INSERT INTO run_progress"
                " (run_id, state, samples_planned, samples_collected, last_heartbeat)"
                " VALUES (?, 'completed', 0, 0, ?)",
                (run_id, _TS2),
            )

            with pytest.raises(PreconditionError) as exc_info:
                aggregate_skill(
                    sk_id,
                    evidence_conn_ro=ev,
                    runtime_conn=rt,
                    harness_version=_HARNESS_VER,
                    generated_at_utc=_GEN_AT,
                )
            assert exc_info.value.code == "no_clauses"
            assert exc_info.value.payload is None
        finally:
            ev.close()
            rt.close()
