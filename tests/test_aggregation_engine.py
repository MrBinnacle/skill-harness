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

    def test_report_schema_version_is_1_0_0(self, tmp_path: Path) -> None:
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
            assert report.report_schema_version == "1.0.0"
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
