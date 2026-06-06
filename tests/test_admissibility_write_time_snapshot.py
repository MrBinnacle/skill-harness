"""Falsifying-case test for A3: admissibility_state is snapshotted at write time.

Per A29 (promoted from D7 into Track A): insert a verdict referencing a
calibration_event; then flip runtime.current_calibration to a different event;
assert the verdict's admissibility_state remains unchanged.

This proves the A3 invariant: admissibility is recorded at write time and never
recomputed from the current calibration pointer. A failure here means a code path
is reading current_calibration at read time, which violates CLAUDE.md Evidence model.
"""

from __future__ import annotations

import sqlite3

from skill_harness.audit import audit_all_verdicts, get_verdict_by_id
from skill_harness.storage.models import (
    CalibrationEventWrite,
    ClauseWrite,
    CurrentCalibrationWrite,
    JudgeWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunWrite,
    SampleWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence import (
    calibration_events as calib_repo,
)
from skill_harness.storage.repositories.evidence import (
    clauses as clauses_repo,
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
    current_calibration as cal_ptr_repo,
)

_TS = "2026-06-05T10:00:00.000Z"
_TS2 = "2026-06-05T11:00:00.000Z"
_SHA = "d" * 64


class TestAdmissibilityWriteTimeSnapshot:
    def test_admissibility_unchanged_after_calibration_flip(
        self,
        evidence_db: sqlite3.Connection,
        runtime_db: sqlite3.Connection,
    ) -> None:
        """A3 falsifying-case: verdict admissibility_state is unchanged after
        runtime.current_calibration is mutated post-write.

        Steps:
        1. Insert prerequisites: skill, clause, metric_version, judge, calibration_event
           (state='active'), current_calibration pointer in runtime.
        2. Insert a verdict with admissibility_state='admissible' referencing
           the original calibration_event_id.
        3. Read back the verdict; capture its admissibility_state.
        4. Mutate runtime.current_calibration: upsert to point at a different
           calibration_event (with state='expired').
        5. Re-read the verdict via audit_all_verdicts(). Assert:
           - admissibility_state is UNCHANGED (still 'admissible')
           - calibration_event_id still points at the ORIGINAL calibration event
        """
        # Step 1: Insert prerequisites in evidence DB
        skills_repo.insert_skill(
            evidence_db,
            SkillWrite(
                skill_id="skill-1",
                name="Test Skill",
                source_path="/tmp/skill.md",
                source_sha256=_SHA,
                imported_at=_TS,
            ),
        )
        clauses_repo.insert_clause(
            evidence_db,
            ClauseWrite(
                clause_id="clause-1",
                skill_id="skill-1",
                clause_index=0,
                rendering_index=0,
                clause_text="Require citations.",
                axis="citation_support",
                comparator="increase",
                oracle_tier=2,
                vacuity_flag="none",
                falsifying_case_schema_sha256=None,
                created_at=_TS,
            ),
        )
        mv_repo.insert_metric_version(
            evidence_db,
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
        judges_repo.insert_judge(
            evidence_db,
            JudgeWrite(
                judge_id="judge-1",
                model_id="claude-sonnet-4-6",
                system_prompt_sha256=_SHA,
                created_at=_TS,
            ),
        )
        # Original calibration event (state='calibrated')
        calib_repo.insert_calibration_event(
            evidence_db,
            CalibrationEventWrite(
                calibration_event_id="calib-original",
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
            ),
        )
        runs_repo.insert_run(
            evidence_db,
            RunWrite(
                run_id="run-snap",
                skill_id="skill-1",
                run_kind="ablation",
                config_json='{"k": 1, "n": 8}',
                started_at=_TS,
                completed_at=None,
            ),
        )
        samples_repo.insert_sample(
            evidence_db,
            SampleWrite(
                sample_id="s-snap-a",
                run_id="run-snap",
                clause_id="clause-1",
                condition="full",
                subject_model="claude-sonnet-4-6",
                subject_seed=None,
                output_text="Output A",
                output_sha256=_SHA,
                sampled_at=_TS,
            ),
        )
        samples_repo.insert_sample(
            evidence_db,
            SampleWrite(
                sample_id="s-snap-b",
                run_id="run-snap",
                clause_id="clause-1",
                condition="ablated",
                subject_model="claude-sonnet-4-6",
                subject_seed=None,
                output_text="Output B",
                output_sha256="e" * 64,
                sampled_at=_TS,
            ),
        )

        # Insert initial current_calibration pointer in runtime DB
        cal_ptr_repo.insert_current_calibration(
            runtime_db,
            CurrentCalibrationWrite(
                judge_id="judge-1",
                axis="citation_support",
                calibration_event_id="calib-original",
                state="calibrated",
                expires_at=None,
                updated_at=_TS,
            ),
        )

        # Step 2: Insert verdict with admissibility_state='admissible',
        # referencing the ORIGINAL calibration_event_id
        verdicts_repo.insert_oracle_verdict(
            evidence_db,
            OracleVerdictWrite(
                verdict_id="v-snap",
                run_id="run-snap",
                clause_id="clause-1",
                axis="citation_support",
                comparison="full_vs_ablated",
                sample_a_id="s-snap-a",
                sample_b_id="s-snap-b",
                observation=1.0,
                oracle_tier=2,
                metric_id=None,
                metric_version=None,
                judge_id="judge-1",
                calibration_event_id="calib-original",
                position_swap_agreement=1,
                admissibility_state="admissible",
                inadmissibility_reason=None,
                written_at=_TS,
            ),
        )

        # Step 3: Read back and capture state before mutation
        row_before = get_verdict_by_id(evidence_db, "v-snap")
        assert row_before is not None
        assert row_before["admissibility_state"] == "admissible"
        assert row_before["calibration_event_id"] == "calib-original"

        # Step 4: Insert a SECOND calibration event in evidence (new expired one),
        # then mutate runtime.current_calibration to point at it
        calib_repo.insert_calibration_event(
            evidence_db,
            CalibrationEventWrite(
                calibration_event_id="calib-new",
                judge_id="judge-1",
                axis="citation_support",
                pairwise_agreement=0.50,
                position_consistency=0.60,
                length_controlled_agreement=0.55,
                cohen_kappa=0.40,
                pair_set_size=50,
                pair_set_sha256="f" * 64,
                state="expired",
                expires_at=_TS,
                validated_at=_TS2,
                # A37 extensions (Track C.3)
                n_a=25,
                n_b=15,
                n_tie=10,
                judge_n_a=26,
                judge_n_b=14,
                judge_n_tie=10,
                length_regression_coefficient=None,
                chance_baseline=0.38,
                total_usd_spent=0.0,
                cost_ledger_run_id=None,
            ),
        )
        cal_ptr_repo.upsert_current_calibration(
            runtime_db,
            CurrentCalibrationWrite(
                judge_id="judge-1",
                axis="citation_support",
                calibration_event_id="calib-new",
                state="expired",
                expires_at=_TS,
                updated_at=_TS2,
            ),
        )

        # Step 5: Re-read via audit_all_verdicts — assert snapshot is unchanged
        audit_rows = audit_all_verdicts(evidence_db, "run-snap")
        assert len(audit_rows) == 1
        audit_row = audit_rows[0]

        assert audit_row["admissibility_state"] == "admissible", (
            "admissibility_state was recomputed from current_calibration at read time — "
            "A3 write-time snapshot invariant violated"
        )
        assert audit_row["calibration_event_id"] == "calib-original", (
            "calibration_event_id was changed from the write-time snapshot — "
            "A3 write-time snapshot invariant violated"
        )
