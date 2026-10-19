"""Round-trip smoke tests for all evidence and runtime repository modules.

Per TDD discipline: each test is an INSERT -> SELECT round-trip proving that:
1. The repo's insert function executes without error.
2. The corresponding get/select function returns the inserted data.

Evidence-side uses the evidence_db fixture (from conftest.py).
Runtime-side uses the runtime_db fixture (from conftest.py).

Note on complete_run: runs.completed_at is the one permitted post-insert write
on evidence tables (A20 column-scoped trigger). complete_run() is tested here
as part of the runs round-trip.
"""

from __future__ import annotations

import sqlite3

import pytest

from skill_harness.audit import (
    audit_all_verdicts,
    get_verdict_by_id,
    list_verdicts_for_clause,
    select_verdicts_by_admissibility,
)
from skill_harness.storage.models import (
    CalibrationEventWrite,
    ClauseWrite,
    ConfoundEventWrite,
    CostLedgerWrite,
    CurrentCalibrationWrite,
    FrozenCaseWrite,
    JudgeWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunBudgetWrite,
    RunProgressWrite,
    RunWrite,
    SampleWrite,
    SkillImportsStagingWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence import (
    calibration_events as calib_repo,
)
from skill_harness.storage.repositories.evidence import (
    clauses as clauses_repo,
)
from skill_harness.storage.repositories.evidence import (
    confound_events as confound_repo,
)
from skill_harness.storage.repositories.evidence import (
    frozen_cases as frozen_repo,
)
from skill_harness.storage.repositories.evidence import (
    judges as judges_repo,
)
from skill_harness.storage.repositories.evidence import (
    metric_versions as mv_repo,
)
from skill_harness.storage.repositories.evidence import (
    oracle_verdicts as verdicts_repo,
)
from skill_harness.storage.repositories.evidence import (
    runs as runs_repo,
)
from skill_harness.storage.repositories.evidence import (
    samples as samples_repo,
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
from skill_harness.storage.repositories.runtime import (
    run_progress as progress_repo,
)
from skill_harness.storage.repositories.runtime import (
    skill_imports_staging as staging_repo,
)

# ---------------------------------------------------------------------------
# Shared test data helpers
# ---------------------------------------------------------------------------

_TS = "2026-06-04T12:00:00.000Z"
_SHA = "a" * 64


def _make_skill(skill_id: str = "skill-1") -> SkillWrite:
    return SkillWrite(
        skill_id=skill_id,
        name="Test Skill",
        source_path="/tmp/skill.md",
        source_sha256=_SHA,
        imported_at=_TS,
    )


def _make_clause(clause_id: str = "clause-1", skill_id: str = "skill-1") -> ClauseWrite:
    return ClauseWrite(
        clause_id=clause_id,
        skill_id=skill_id,
        clause_index=0,
        rendering_index=0,
        clause_text="Require citations for factual claims.",
        axis="citation_support",
        comparator="increase",
        oracle_tier=1,
        vacuity_flag="none",
        falsifying_case_schema_sha256=None,
        created_at=_TS,
    )


def _make_metric_version(
    metric_id: str = "hedge_index", version: str = "1.0.0"
) -> MetricVersionWrite:
    return MetricVersionWrite(
        metric_id=metric_id,
        version=version,
        implementation_hash=_SHA,
        tier=1,
        audited=1,
        mechanical_validity_test_passed=1,
        registered_at=_TS,
    )


def _make_judge(judge_id: str = "judge-1") -> JudgeWrite:
    return JudgeWrite(
        judge_id=judge_id,
        model_id="claude-sonnet-4-6",
        system_prompt_sha256=_SHA,
        created_at=_TS,
    )


def _make_calibration_event(
    event_id: str = "calib-1", judge_id: str = "judge-1"
) -> CalibrationEventWrite:
    return CalibrationEventWrite(
        calibration_event_id=event_id,
        judge_id=judge_id,
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
        # A37 extensions (Track C.3)
        n_a=40,
        n_b=7,
        n_tie=3,
        judge_n_a=41,
        judge_n_b=6,
        judge_n_tie=3,
        length_regression_coefficient=None,
        chance_baseline=0.35,
        total_usd_spent=0.0,
        cost_ledger_run_id=None,
    )


def _make_run(run_id: str = "run-1", skill_id: str = "skill-1") -> RunWrite:
    return RunWrite(
        run_id=run_id,
        skill_id=skill_id,
        run_kind="ablation",
        config_json='{"k": 1, "n": 8}',
        started_at=_TS,
        completed_at=None,
    )


def _make_sample(
    sample_id: str = "sample-1",
    run_id: str = "run-1",
    clause_id: str = "clause-1",
    sample_index: int = 0,
) -> SampleWrite:
    return SampleWrite(
        sample_id=sample_id,
        run_id=run_id,
        clause_id=clause_id,
        condition="full",
        subject_model="claude-sonnet-4-6",
        subject_seed=None,
        output_text="Here is the output with [1] citation.",
        output_sha256=_SHA,
        sampled_at=_TS,
        sample_index=sample_index,
    )


# ---------------------------------------------------------------------------
# Evidence-side round-trip tests
# ---------------------------------------------------------------------------


class TestSkillsRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        skill = _make_skill()
        skills_repo.insert_skill(evidence_db, skill)
        row = skills_repo.get_skill_by_id(evidence_db, "skill-1")
        assert row is not None
        assert row["skill_id"] == "skill-1"
        assert row["name"] == "Test Skill"

    def test_list_skills(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill("s1"))
        skills_repo.insert_skill(evidence_db, _make_skill("s2"))
        rows = skills_repo.list_skills(evidence_db)
        assert len(rows) == 2

    def test_select_by_sha256(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill("s1"))
        rows = skills_repo.select_skills_by_source_sha256(evidence_db, _SHA)
        assert len(rows) == 1

    def test_get_missing_returns_none(self, evidence_db: sqlite3.Connection) -> None:
        assert skills_repo.get_skill_by_id(evidence_db, "nonexistent") is None

    def test_append_only_rejects_update(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            evidence_db.execute("UPDATE skills SET name = 'x' WHERE skill_id = 'skill-1'")


class TestClausesRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        clause = _make_clause()
        clauses_repo.insert_clause(evidence_db, clause)
        row = clauses_repo.get_clause_by_id(evidence_db, "clause-1")
        assert row is not None
        assert row["axis"] == "citation_support"

    def test_list_for_skill(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        c1 = ClauseWrite(
            clause_id="c1",
            skill_id="skill-1",
            clause_index=0,
            rendering_index=0,
            clause_text="Clause one.",
            axis="citation_support",
            comparator="increase",
            oracle_tier=1,
            vacuity_flag="none",
            falsifying_case_schema_sha256=None,
            created_at=_TS,
        )
        c2 = ClauseWrite(
            clause_id="c2",
            skill_id="skill-1",
            clause_index=1,
            rendering_index=1,
            clause_text="Clause two.",
            axis="verbosity",
            comparator="decrease",
            oracle_tier=1,
            vacuity_flag="none",
            falsifying_case_schema_sha256=None,
            created_at=_TS,
        )
        clauses_repo.insert_clause(evidence_db, c1)
        clauses_repo.insert_clause(evidence_db, c2)
        rows = clauses_repo.list_clauses_for_skill(evidence_db, "skill-1")
        assert len(rows) == 2

    def test_select_by_axis(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        clauses_repo.insert_clause(evidence_db, _make_clause("c1"))
        rows = clauses_repo.select_clauses_by_axis(evidence_db, "citation_support")
        assert len(rows) == 1


class TestMetricVersionsRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        mv = _make_metric_version()
        mv_repo.insert_metric_version(evidence_db, mv)
        row = mv_repo.get_metric_version(evidence_db, "hedge_index", "1.0.0")
        assert row is not None
        assert row["mechanical_validity_test_passed"] == 1

    def test_list_versions(self, evidence_db: sqlite3.Connection) -> None:
        mv_repo.insert_metric_version(evidence_db, _make_metric_version("m1", "1.0.0"))
        mv_repo.insert_metric_version(evidence_db, _make_metric_version("m1", "1.1.0"))
        rows = mv_repo.list_metric_versions(evidence_db, "m1")
        assert len(rows) == 2

    def test_select_by_tier(self, evidence_db: sqlite3.Connection) -> None:
        mv_repo.insert_metric_version(evidence_db, _make_metric_version())
        rows = mv_repo.select_metric_versions_by_tier(evidence_db, 1)
        assert len(rows) == 1


class TestJudgesRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge())
        row = judges_repo.get_judge_by_id(evidence_db, "judge-1")
        assert row is not None
        assert row["model_id"] == "claude-sonnet-4-6"

    def test_list_judges(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge("j1"))
        judges_repo.insert_judge(evidence_db, _make_judge("j2"))
        rows = judges_repo.list_judges(evidence_db)
        assert len(rows) == 2

    def test_select_by_model(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge())
        rows = judges_repo.select_judges_by_model(evidence_db, "claude-sonnet-4-6")
        assert len(rows) == 1


class TestCalibrationEventsRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge())
        event = _make_calibration_event()
        calib_repo.insert_calibration_event(evidence_db, event)
        row = calib_repo.get_calibration_event_by_id(evidence_db, "calib-1")
        assert row is not None
        assert row["pairwise_agreement"] == pytest.approx(0.85)

    def test_list_for_judge_axis(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge())
        calib_repo.insert_calibration_event(evidence_db, _make_calibration_event("c1"))
        rows = calib_repo.list_calibration_events_for_judge_axis(
            evidence_db, "judge-1", "citation_support"
        )
        assert len(rows) == 1

    def test_select_by_state(self, evidence_db: sqlite3.Connection) -> None:
        judges_repo.insert_judge(evidence_db, _make_judge())
        calib_repo.insert_calibration_event(evidence_db, _make_calibration_event())
        rows = calib_repo.select_calibration_events_by_state(evidence_db, "calibrated")
        assert len(rows) == 1


class TestRunsRepo:
    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        runs_repo.insert_run(evidence_db, _make_run())
        row = runs_repo.get_run_by_id(evidence_db, "run-1")
        assert row is not None
        assert row["run_kind"] == "ablation"
        assert row["completed_at"] is None

    def test_complete_run(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        runs_repo.insert_run(evidence_db, _make_run())
        runs_repo.complete_run(evidence_db, "run-1", _TS)
        row = runs_repo.get_run_by_id(evidence_db, "run-1")
        assert row is not None
        assert row["completed_at"] == _TS

    def test_complete_run_twice_raises(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        runs_repo.insert_run(evidence_db, _make_run())
        runs_repo.complete_run(evidence_db, "run-1", _TS)
        with pytest.raises(sqlite3.IntegrityError):
            runs_repo.complete_run(evidence_db, "run-1", _TS)

    def test_list_for_skill(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        runs_repo.insert_run(evidence_db, _make_run("r1"))
        runs_repo.insert_run(evidence_db, _make_run("r2"))
        rows = runs_repo.list_runs_for_skill(evidence_db, "skill-1")
        assert len(rows) == 2

    def test_select_by_kind(self, evidence_db: sqlite3.Connection) -> None:
        skills_repo.insert_skill(evidence_db, _make_skill())
        runs_repo.insert_run(evidence_db, _make_run())
        rows = runs_repo.select_runs_by_kind(evidence_db, "ablation")
        assert len(rows) == 1


class TestSamplesRepo:
    def _setup(self, conn: sqlite3.Connection) -> None:
        skills_repo.insert_skill(conn, _make_skill())
        clauses_repo.insert_clause(conn, _make_clause())
        runs_repo.insert_run(conn, _make_run())

    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        samples_repo.insert_sample(evidence_db, _make_sample())
        row = samples_repo.get_sample_by_id(evidence_db, "sample-1")
        assert row is not None
        assert row["condition"] == "full"

    def test_list_for_run(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        # A40: samples with the same (run_id, clause_id, condition) need distinct sample_index
        samples_repo.insert_sample(evidence_db, _make_sample("s1", sample_index=0))
        samples_repo.insert_sample(evidence_db, _make_sample("s2", sample_index=1))
        rows = samples_repo.list_samples_for_run(evidence_db, "run-1")
        assert len(rows) == 2

    def test_select_by_condition(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        samples_repo.insert_sample(evidence_db, _make_sample("s1"))
        rows = samples_repo.select_samples_by_condition(evidence_db, "run-1", "full")
        assert len(rows) == 1


class TestOracleVerdictsRepo:
    def _setup(self, conn: sqlite3.Connection) -> None:
        skills_repo.insert_skill(conn, _make_skill())
        clauses_repo.insert_clause(conn, _make_clause())
        mv_repo.insert_metric_version(conn, _make_metric_version())
        runs_repo.insert_run(conn, _make_run())
        # A40: distinct sample_index values within (run_id, clause_id, condition)
        samples_repo.insert_sample(conn, _make_sample("s1", sample_index=0))
        samples_repo.insert_sample(conn, _make_sample("s2", sample_index=1))

    def _make_verdict(self, verdict_id: str = "v1") -> OracleVerdictWrite:
        return OracleVerdictWrite(
            verdict_id=verdict_id,
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

    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        verdicts_repo.insert_oracle_verdict(evidence_db, self._make_verdict())
        row = get_verdict_by_id(evidence_db, "v1")
        assert row is not None
        assert row["admissibility_state"] == "admissible"

    def test_audit_all_verdicts(self, evidence_db: sqlite3.Connection) -> None:
        """audit_all_verdicts() is the A29 canonical home for raw oracle_verdicts access."""
        self._setup(evidence_db)
        verdicts_repo.insert_oracle_verdict(evidence_db, self._make_verdict())
        rows = audit_all_verdicts(evidence_db, "run-1")
        assert len(rows) == 1

    def test_list_for_clause(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        verdicts_repo.insert_oracle_verdict(evidence_db, self._make_verdict())
        rows = list_verdicts_for_clause(evidence_db, "clause-1")
        assert len(rows) == 1

    def test_select_by_admissibility(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        verdicts_repo.insert_oracle_verdict(evidence_db, self._make_verdict())
        rows = select_verdicts_by_admissibility(evidence_db, "admissible")
        assert len(rows) == 1

    def test_admissibility_snapshot_survives_calibration_change(
        self, evidence_db: sqlite3.Connection, runtime_db: sqlite3.Connection
    ) -> None:
        """A3 falsifying-case: written admissibility_state is unchanged after
        runtime.current_calibration pointer is flipped (write-time snapshot proof)."""
        self._setup(evidence_db)
        # Create judge + calibration_event in evidence
        judges_repo.insert_judge(evidence_db, _make_judge())
        calib_repo.insert_calibration_event(evidence_db, _make_calibration_event())
        # Write verdict with admissibility_state = 'admissible'
        verdict = OracleVerdictWrite(
            verdict_id="v-snapshot",
            run_id="run-1",
            clause_id="clause-1",
            axis="citation_support",
            comparison="full_vs_ablated",
            sample_a_id="s1",
            sample_b_id="s2",
            observation=1.0,
            oracle_tier=2,
            metric_id=None,
            metric_version=None,
            judge_id="judge-1",
            calibration_event_id="calib-1",
            position_swap_agreement=1,
            admissibility_state="admissible",
            inadmissibility_reason=None,
            written_at=_TS,
        )
        verdicts_repo.insert_oracle_verdict(evidence_db, verdict)
        # Now flip runtime.current_calibration to a different (fake) event
        runtime_db.execute(
            """
            INSERT INTO current_calibration
                (judge_id, axis, calibration_event_id, state, updated_at)
            VALUES ('judge-1', 'citation_support', 'calib-FAKE', 'expired', ?)
            """,
            (_TS,),
        )
        # Assert verdict's admissibility_state is UNCHANGED — still 'admissible'
        row = get_verdict_by_id(evidence_db, "v-snapshot")
        assert row is not None
        assert row["admissibility_state"] == "admissible", (
            "admissibility_state was recomputed from runtime — write-time snapshot violated"
        )


class TestConfoundEventsRepo:
    def _setup(self, conn: sqlite3.Connection) -> None:
        skills_repo.insert_skill(conn, _make_skill())
        clauses_repo.insert_clause(conn, _make_clause())
        runs_repo.insert_run(conn, _make_run())

    def _make_confound(self, confound_id: str = "conf-1") -> ConfoundEventWrite:
        return ConfoundEventWrite(
            confound_event_id=confound_id,
            run_id="run-1",
            primary_clause_id="clause-1",
            affected_clause_id=None,
            axis="verbosity",
            delta=0.35,
            null_sigma=0.10,
            k_threshold=2.0,
            delta_kind="confound_flagged",
            detected_at=_TS,
        )

    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        confound_repo.insert_confound_event(evidence_db, self._make_confound())
        row = confound_repo.get_confound_event_by_id(evidence_db, "conf-1")
        assert row is not None
        assert row["delta_kind"] == "confound_flagged"

    def test_list_for_run(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        confound_repo.insert_confound_event(evidence_db, self._make_confound())
        rows = confound_repo.list_confound_events_for_run(evidence_db, "run-1")
        assert len(rows) == 1

    def test_select_by_kind(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        confound_repo.insert_confound_event(evidence_db, self._make_confound())
        rows = confound_repo.select_confound_events_by_kind(evidence_db, "confound_flagged")
        assert len(rows) == 1


class TestFrozenCasesRepo:
    def _make_frozen(self, case_id: str = "fc-1") -> FrozenCaseWrite:
        return FrozenCaseWrite(
            frozen_case_id=case_id,
            clause_id="clause-1",
            failing_input_text="Here is a claim without citation.",
            failing_input_sha256=_SHA,
            oracle_source="mechanical",
            labeled_by=None,
            labeled_at=None,
            metric_id="hedge_index",
            metric_version="1.0.0",
            implementation_hash=_SHA,
            frozen_at=_TS,
        )

    def _setup(self, conn: sqlite3.Connection) -> None:
        skills_repo.insert_skill(conn, _make_skill())
        clauses_repo.insert_clause(conn, _make_clause())
        mv_repo.insert_metric_version(conn, _make_metric_version())

    def test_insert_and_get(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        frozen_repo.insert_frozen_case(evidence_db, self._make_frozen())
        row = frozen_repo.get_frozen_case_by_id(evidence_db, "fc-1")
        assert row is not None
        assert row["oracle_source"] == "mechanical"

    def test_list_for_clause(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        frozen_repo.insert_frozen_case(evidence_db, self._make_frozen("fc1"))
        rows = frozen_repo.list_frozen_cases_for_clause(evidence_db, "clause-1")
        assert len(rows) == 1

    def test_select_by_oracle_source(self, evidence_db: sqlite3.Connection) -> None:
        self._setup(evidence_db)
        frozen_repo.insert_frozen_case(evidence_db, self._make_frozen())
        rows = frozen_repo.select_frozen_cases_by_oracle_source(evidence_db, "mechanical")
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Runtime-side round-trip tests
# ---------------------------------------------------------------------------


class TestSkillImportsStagingRepo:
    def _make_staging(self, staging_id: str = "stg-1") -> SkillImportsStagingWrite:
        return SkillImportsStagingWrite(
            staging_id=staging_id,
            source_path="/tmp/skill.md",
            state="parsing",
            notes=None,
            updated_at=_TS,
        )

    def test_insert_and_get(self, runtime_db: sqlite3.Connection) -> None:
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging())
        row = staging_repo.get_skill_import_staging_by_id(runtime_db, "stg-1")
        assert row is not None
        assert row["state"] == "parsing"

    def test_list_stagings(self, runtime_db: sqlite3.Connection) -> None:
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging("s1"))
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging("s2"))
        rows = staging_repo.list_skill_import_stagings(runtime_db)
        assert len(rows) == 2

    def test_select_by_state(self, runtime_db: sqlite3.Connection) -> None:
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging())
        rows = staging_repo.select_skill_import_stagings_by_state(runtime_db, "parsing")
        assert len(rows) == 1

    def test_update_state(self, runtime_db: sqlite3.Connection) -> None:
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging())
        staging_repo.update_skill_import_staging_state(runtime_db, "stg-1", "extracted", _TS)
        row = staging_repo.get_skill_import_staging_by_id(runtime_db, "stg-1")
        assert row is not None
        assert row["state"] == "extracted"

    def test_delete(self, runtime_db: sqlite3.Connection) -> None:
        staging_repo.insert_skill_import_staging(runtime_db, self._make_staging())
        staging_repo.delete_skill_import_staging(runtime_db, "stg-1")
        assert staging_repo.get_skill_import_staging_by_id(runtime_db, "stg-1") is None


class TestRunProgressRepo:
    def _make_progress(self, run_id: str = "run-1") -> RunProgressWrite:
        return RunProgressWrite(
            run_id=run_id,
            state="running",
            samples_planned=20,
            samples_collected=0,
            last_heartbeat=_TS,
            error=None,
        )

    def test_insert_and_get(self, runtime_db: sqlite3.Connection) -> None:
        progress_repo.insert_run_progress(runtime_db, self._make_progress())
        row = progress_repo.get_run_progress_by_id(runtime_db, "run-1")
        assert row is not None
        assert row["state"] == "running"

    def test_list_by_state(self, runtime_db: sqlite3.Connection) -> None:
        progress_repo.insert_run_progress(runtime_db, self._make_progress("r1"))
        rows = progress_repo.list_run_progresses_by_state(runtime_db, "running")
        assert len(rows) == 1

    def test_update(self, runtime_db: sqlite3.Connection) -> None:
        progress_repo.insert_run_progress(runtime_db, self._make_progress())
        progress_repo.update_run_progress(
            runtime_db,
            "run-1",
            state="completed",
            samples_collected=20,
            last_heartbeat=_TS,
        )
        row = progress_repo.get_run_progress_by_id(runtime_db, "run-1")
        assert row is not None
        assert row["state"] == "completed"
        assert row["samples_collected"] == 20

    def test_delete(self, runtime_db: sqlite3.Connection) -> None:
        progress_repo.insert_run_progress(runtime_db, self._make_progress())
        progress_repo.delete_run_progress(runtime_db, "run-1")
        assert progress_repo.get_run_progress_by_id(runtime_db, "run-1") is None


class TestCurrentCalibrationRepo:
    def _make_cal_ptr(self) -> CurrentCalibrationWrite:
        return CurrentCalibrationWrite(
            judge_id="judge-1",
            axis="citation_support",
            calibration_event_id="calib-1",
            state="calibrated",
            expires_at=None,
            updated_at=_TS,
        )

    def test_insert_and_get(self, runtime_db: sqlite3.Connection) -> None:
        cal_ptr_repo.insert_current_calibration(runtime_db, self._make_cal_ptr())
        row = cal_ptr_repo.get_current_calibration(runtime_db, "judge-1", "citation_support")
        assert row is not None
        assert row["state"] == "calibrated"

    def test_list(self, runtime_db: sqlite3.Connection) -> None:
        cal_ptr_repo.insert_current_calibration(runtime_db, self._make_cal_ptr())
        rows = cal_ptr_repo.list_current_calibrations(runtime_db)
        assert len(rows) == 1

    def test_select_by_state(self, runtime_db: sqlite3.Connection) -> None:
        cal_ptr_repo.insert_current_calibration(runtime_db, self._make_cal_ptr())
        rows = cal_ptr_repo.select_current_calibrations_by_state(runtime_db, "calibrated")
        assert len(rows) == 1

    def test_update(self, runtime_db: sqlite3.Connection) -> None:
        cal_ptr_repo.insert_current_calibration(runtime_db, self._make_cal_ptr())
        cal_ptr_repo.update_current_calibration(
            runtime_db,
            "judge-1",
            "citation_support",
            calibration_event_id="calib-2",
            state="expired",
            expires_at=_TS,
            updated_at=_TS,
        )
        row = cal_ptr_repo.get_current_calibration(runtime_db, "judge-1", "citation_support")
        assert row is not None
        assert row["calibration_event_id"] == "calib-2"
        assert row["state"] == "expired"


class TestRunBudgetRepo:
    def _make_budget(self, run_id: str = "run-1") -> RunBudgetWrite:
        return RunBudgetWrite(
            run_id=run_id,
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

    def test_insert_and_get(self, runtime_db: sqlite3.Connection) -> None:
        budget_repo.insert_run_budget(runtime_db, self._make_budget())
        row = budget_repo.get_run_budget_by_id(runtime_db, "run-1")
        assert row is not None
        assert row["hard_cap_usd"] == pytest.approx(5.0)

    def test_list(self, runtime_db: sqlite3.Connection) -> None:
        budget_repo.insert_run_budget(runtime_db, self._make_budget("r1"))
        rows = budget_repo.list_run_budgets(runtime_db)
        assert len(rows) == 1

    def test_select_over_cap(self, runtime_db: sqlite3.Connection) -> None:
        bw = RunBudgetWrite(
            run_id="run-over",
            hard_cap_usd=1.0,
            tokens_spent_in=0,
            tokens_spent_out=0,
            cache_write_in=0,
            cache_read_in=0,
            usd_spent=1.5,
            dry_run=0,
            aborted_at=None,
            last_updated=_TS,
        )
        budget_repo.insert_run_budget(runtime_db, bw)
        rows = budget_repo.select_run_budgets_over_cap(runtime_db)
        assert len(rows) == 1

    def test_update_spend(self, runtime_db: sqlite3.Connection) -> None:
        budget_repo.insert_run_budget(runtime_db, self._make_budget())
        budget_repo.update_run_budget_spend(
            runtime_db,
            "run-1",
            tokens_spent_in=100,
            tokens_spent_out=50,
            cache_write_in=10,
            cache_read_in=5,
            usd_spent=0.01,
            last_updated=_TS,
        )
        row = budget_repo.get_run_budget_by_id(runtime_db, "run-1")
        assert row is not None
        assert row["tokens_spent_in"] == 100
        assert row["usd_spent"] == pytest.approx(0.01)

    def test_update_aborted(self, runtime_db: sqlite3.Connection) -> None:
        budget_repo.insert_run_budget(runtime_db, self._make_budget())
        budget_repo.update_run_budget_aborted(runtime_db, "run-1", _TS, _TS)
        row = budget_repo.get_run_budget_by_id(runtime_db, "run-1")
        assert row is not None
        assert row["aborted_at"] == _TS


class TestCostLedgerRepo:
    def _make_entry(self) -> CostLedgerWrite:
        return CostLedgerWrite(
            ts=_TS,
            run_id="run-1",
            skill_id=None,
            model_id="claude-sonnet-4-6",
            call_kind="subject",
            input_tok=100,
            cache_write_tok=10,
            cache_read_tok=5,
            output_tok=50,
            usd=0.001,
        )

    def test_insert_and_get(self, runtime_db: sqlite3.Connection) -> None:
        ledger_id = cost_repo.insert_cost_ledger_entry(runtime_db, self._make_entry())
        assert ledger_id > 0
        row = cost_repo.get_cost_ledger_entry_by_id(runtime_db, ledger_id)
        assert row is not None
        assert row["call_kind"] == "subject"

    def test_list_for_run(self, runtime_db: sqlite3.Connection) -> None:
        cost_repo.insert_cost_ledger_entry(runtime_db, self._make_entry())
        rows = cost_repo.list_cost_ledger_for_run(runtime_db, "run-1")
        assert len(rows) == 1

    def test_select_since(self, runtime_db: sqlite3.Connection) -> None:
        cost_repo.insert_cost_ledger_entry(runtime_db, self._make_entry())
        rows = cost_repo.select_cost_ledger_since(runtime_db, "2026-01-01T00:00:00.000Z")
        assert len(rows) == 1

    def test_select_since_excludes_old(self, runtime_db: sqlite3.Connection) -> None:
        cost_repo.insert_cost_ledger_entry(runtime_db, self._make_entry())
        rows = cost_repo.select_cost_ledger_since(runtime_db, "2027-01-01T00:00:00.000Z")
        assert len(rows) == 0
