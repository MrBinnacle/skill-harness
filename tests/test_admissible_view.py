"""Tests for the admissible_verdicts SQL VIEW (migrations/evidence/0003).

Per A29: three VIEW tests verifying the two filter conditions:
  1. admissibility_state = 'admissible'
  2. no matching confound_events row with delta_kind = 'confound_flagged'
     for the same (run_id, primary_clause_id = verdict.clause_id)
"""

from __future__ import annotations

import sqlite3

from skill_harness.storage.models import (
    ClauseWrite,
    ConfoundEventWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunWrite,
    SampleWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence import (
    clauses as clauses_repo,
)
from skill_harness.storage.repositories.evidence import (
    confound_events as confound_repo,
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

_TS = "2026-06-05T10:00:00.000Z"
_SHA = "b" * 64


def _setup_prerequisites(conn: sqlite3.Connection) -> None:
    """Insert the prerequisite rows required for oracle_verdicts + confound_events FKs."""
    skills_repo.insert_skill(
        conn,
        SkillWrite(
            skill_id="skill-1",
            name="Test Skill",
            source_path="/tmp/skill.md",
            source_sha256=_SHA,
            imported_at=_TS,
        ),
    )
    clauses_repo.insert_clause(
        conn,
        ClauseWrite(
            clause_id="clause-1",
            skill_id="skill-1",
            clause_index=0,
            rendering_index=0,
            clause_text="Require citations for factual claims.",
            axis="citation_support",
            comparator="increase",
            oracle_tier=1,
            vacuity_flag="none",
            falsifying_case_schema_sha256=None,
            created_at=_TS,
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
    runs_repo.insert_run(
        conn,
        RunWrite(
            run_id="run-1",
            skill_id="skill-1",
            run_kind="ablation",
            config_json='{"k": 1, "n": 8}',
            started_at=_TS,
            completed_at=None,
        ),
    )
    samples_repo.insert_sample(
        conn,
        SampleWrite(
            sample_id="s1",
            run_id="run-1",
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
        conn,
        SampleWrite(
            sample_id="s2",
            run_id="run-1",
            clause_id="clause-1",
            condition="ablated",
            subject_model="claude-sonnet-4-6",
            subject_seed=None,
            output_text="Output B",
            output_sha256="c" * 64,
            sampled_at=_TS,
        ),
    )


def _make_verdict(verdict_id: str, admissibility_state: str) -> OracleVerdictWrite:
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
        admissibility_state=admissibility_state,
        inadmissibility_reason=None,
        written_at=_TS,
    )


class TestAdmissibleView:
    def test_admissible_view_excludes_inadmissible(self, evidence_db: sqlite3.Connection) -> None:
        """A verdict with admissibility_state='inadmissible' MUST NOT appear in the VIEW."""
        _setup_prerequisites(evidence_db)
        verdicts_repo.insert_oracle_verdict(
            evidence_db, _make_verdict("v-inadmissible", "inadmissible")
        )
        rows = verdicts_repo.get_admissible_verdicts(evidence_db, "run-1")
        verdict_ids = [r["verdict_id"] for r in rows]
        assert "v-inadmissible" not in verdict_ids, (
            "inadmissible verdict must not appear in admissible_verdicts VIEW"
        )

    def test_admissible_view_excludes_confounded(self, evidence_db: sqlite3.Connection) -> None:
        """An admissible verdict that has a matching confound_flagged event
        for the same (run_id, primary_clause_id = verdict.clause_id)
        MUST NOT appear in the VIEW."""
        _setup_prerequisites(evidence_db)
        verdicts_repo.insert_oracle_verdict(
            evidence_db, _make_verdict("v-confounded", "admissible")
        )
        # Insert a confound_events row for the same (run_id, primary_clause_id)
        confound_repo.insert_confound_event(
            evidence_db,
            ConfoundEventWrite(
                confound_event_id="conf-1",
                run_id="run-1",
                primary_clause_id="clause-1",  # matches verdict.clause_id
                affected_clause_id=None,
                axis="verbosity",
                delta=0.35,
                null_sigma=0.10,
                k_threshold=2.0,
                delta_kind="confound_flagged",
                detected_at=_TS,
            ),
        )
        rows = verdicts_repo.get_admissible_verdicts(evidence_db, "run-1")
        verdict_ids = [r["verdict_id"] for r in rows]
        assert "v-confounded" not in verdict_ids, (
            "confounded verdict must not appear in admissible_verdicts VIEW"
        )

    def test_admissible_view_includes_clean_verdicts(self, evidence_db: sqlite3.Connection) -> None:
        """An admissible verdict with NO matching confound_flagged event
        MUST appear in the VIEW."""
        _setup_prerequisites(evidence_db)
        verdicts_repo.insert_oracle_verdict(evidence_db, _make_verdict("v-clean", "admissible"))
        rows = verdicts_repo.get_admissible_verdicts(evidence_db, "run-1")
        verdict_ids = [r["verdict_id"] for r in rows]
        assert "v-clean" in verdict_ids, (
            "clean admissible verdict must appear in admissible_verdicts VIEW"
        )
