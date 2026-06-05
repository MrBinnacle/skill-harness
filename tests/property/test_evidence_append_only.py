"""A27 — Property-based tests for the append-only invariant.

P1: For all evidence tables EXCEPT runs, any UPDATE or DELETE after INSERT raises
    sqlite3.IntegrityError matching r'append_only_violation: <table>'.

P2: For the runs table (A20 carve-out):
    - UPDATE of immutable columns (skill_id, run_kind, config_json, started_at)
      raises IntegrityError matching r'append_only_violation:.*runs.*immutable'
    - Single UPDATE of completed_at (NULL → value) SUCCEEDS
    - Second UPDATE of completed_at raises IntegrityError

FK closure: each test ensures required parent rows are inserted before the
child row under test, using the PRAGMA foreign_key_list approach.  Parent IDs
are fixed constants (not drawn from Hypothesis) to keep the strategy simple
and deterministic.  Hypothesis generates variation in the child row's PK and
non-FK text fields.

Hypothesis settings per A27:
    @settings(max_examples=50, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])

Isolation: each @given example uses the SAVEPOINT pattern from conftest so
examples are isolated from each other (A28).
"""

from __future__ import annotations

import sqlite3

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from skill_harness.storage.models import (
    CalibrationEventWrite,
    ClauseWrite,
    ConfoundEventWrite,
    FrozenCaseWrite,
    JudgeWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunWrite,
    SampleWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence import calibration_events as calib_repo
from skill_harness.storage.repositories.evidence import clauses as clauses_repo
from skill_harness.storage.repositories.evidence import confound_events as confound_repo
from skill_harness.storage.repositories.evidence import frozen_cases as frozen_repo
from skill_harness.storage.repositories.evidence import judges as judges_repo
from skill_harness.storage.repositories.evidence import metric_versions as mv_repo
from skill_harness.storage.repositories.evidence import oracle_verdicts as verdicts_repo
from skill_harness.storage.repositories.evidence import runs as runs_repo
from skill_harness.storage.repositories.evidence import samples as samples_repo
from skill_harness.storage.repositories.evidence import skills as skills_repo

# ---------------------------------------------------------------------------
# Constants shared across all examples
# ---------------------------------------------------------------------------

_TS = "2026-06-05T00:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64

# Fixed parent IDs used by FK chains (same in every example; SAVEPOINTs roll
# back child rows but parent rows inserted once stay for the duration of the
# test function because they are inserted outside the per-example SAVEPOINT).
_SKILL_ID = "prop-skill-1"
_CLAUSE_ID = "prop-clause-1"
_METRIC_ID = "prop-metric"
_METRIC_VER = "1.0.0"
_JUDGE_ID = "prop-judge-1"
_CALIB_ID = "prop-calib-1"
_RUN_ID_BASE = "prop-run"
_SAMPLE_A_ID = "prop-sample-a"
_SAMPLE_B_ID = "prop-sample-b"

# ---------------------------------------------------------------------------
# FK-chain seed helpers
# ---------------------------------------------------------------------------


def _seed_skill(conn: sqlite3.Connection) -> None:
    """Insert the shared parent skill row (idempotent via INSERT OR IGNORE)."""
    conn.execute(
        "INSERT OR IGNORE INTO skills "
        "(skill_id, name, source_path, source_sha256, imported_at) VALUES (?,?,?,?,?)",
        (_SKILL_ID, "PropSkill", "/tmp/prop.md", _SHA, _TS),
    )


def _seed_clause(conn: sqlite3.Connection) -> None:
    _seed_skill(conn)
    conn.execute(
        "INSERT OR IGNORE INTO clauses "
        "(clause_id, skill_id, clause_index, rendering_index, clause_text, "
        "axis, comparator, oracle_tier, vacuity_flag, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (_CLAUSE_ID, _SKILL_ID, 0, 0, "PropClause.", "axis_x", "increase", 1, "none", _TS),
    )


def _seed_metric_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO metric_versions "
        "(metric_id, version, implementation_hash, tier, audited, "
        "mechanical_validity_test_passed, registered_at) VALUES (?,?,?,?,?,?,?)",
        (_METRIC_ID, _METRIC_VER, _SHA, 1, 1, 1, _TS),
    )


def _seed_judge(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO judges (judge_id, model_id, system_prompt_sha256, created_at) "
        "VALUES (?,?,?,?)",
        (_JUDGE_ID, "claude-sonnet-4-6", _SHA, _TS),
    )


def _seed_calibration_event(conn: sqlite3.Connection) -> None:
    _seed_judge(conn)
    conn.execute(
        "INSERT OR IGNORE INTO calibration_events "
        "(calibration_event_id, judge_id, axis, pairwise_agreement, "
        "position_consistency, pair_set_size, pair_set_sha256, state, validated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (_CALIB_ID, _JUDGE_ID, "axis_x", 0.9, 0.9, 50, _SHA, "calibrated", _TS),
    )


def _seed_run(conn: sqlite3.Connection, run_id: str) -> None:
    _seed_skill(conn)
    conn.execute(
        "INSERT OR IGNORE INTO runs "
        "(run_id, skill_id, run_kind, config_json, started_at) VALUES (?,?,?,?,?)",
        (run_id, _SKILL_ID, "ablation", "{}", _TS),
    )


def _seed_samples(conn: sqlite3.Connection, run_id: str) -> None:
    _seed_clause(conn)
    _seed_run(conn, run_id)
    conn.execute(
        "INSERT OR IGNORE INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, "
        "output_text, output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
        (_SAMPLE_A_ID, run_id, _CLAUSE_ID, "full", "claude-sonnet-4-6", "out", _SHA, _TS),
    )
    conn.execute(
        "INSERT OR IGNORE INTO samples "
        "(sample_id, run_id, clause_id, condition, subject_model, "
        "output_text, output_sha256, sampled_at) VALUES (?,?,?,?,?,?,?,?)",
        (_SAMPLE_B_ID, run_id, _CLAUSE_ID, "ablated", "claude-sonnet-4-6", "out2", _SHA2, _TS),
    )


# ---------------------------------------------------------------------------
# Shared @settings decorator — A27 spec + function_scoped_fixture suppression
# ---------------------------------------------------------------------------

_SUPPRESS = [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
_PROP_SETTINGS = settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS)

# ---------------------------------------------------------------------------
# Safe text strategy — printable ASCII, no C0 controls
# ---------------------------------------------------------------------------

_safe_text = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_",
    ),
)

# ---------------------------------------------------------------------------
# P1 helper — assert that UPDATE / DELETE on table raises append_only_violation
# ---------------------------------------------------------------------------


def _assert_update_raises(
    conn: sqlite3.Connection, table: str, pk_col: str, pk_val: object
) -> None:
    """Assert that UPDATE on the given row raises IntegrityError with the expected msg."""
    with pytest.raises(sqlite3.IntegrityError, match=f"append_only_violation: {table}"):
        conn.execute(
            f"UPDATE {table} SET {pk_col} = {pk_col} WHERE {pk_col} = ?",
            (pk_val,),
        )


def _assert_delete_raises(
    conn: sqlite3.Connection, table: str, pk_col: str, pk_val: object
) -> None:
    """Assert that DELETE on the given row raises IntegrityError with the expected msg."""
    with pytest.raises(sqlite3.IntegrityError, match=f"append_only_violation: {table}"):
        conn.execute(
            f"DELETE FROM {table} WHERE {pk_col} = ?",
            (pk_val,),
        )


# ---------------------------------------------------------------------------
# P1 — skills
# ---------------------------------------------------------------------------


class TestP1Skills:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            skill_id = f"sk-{suffix[:12]}"
            skills_repo.insert_skill(
                conn,
                SkillWrite(
                    skill_id=skill_id,
                    name=suffix,
                    source_path="/t.md",
                    source_sha256=_SHA,
                    imported_at=_TS,
                ),
            )
            _assert_update_raises(conn, "skills", "skill_id", skill_id)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            skill_id = f"sk-{suffix[:12]}"
            skills_repo.insert_skill(
                conn,
                SkillWrite(
                    skill_id=skill_id,
                    name=suffix,
                    source_path="/t.md",
                    source_sha256=_SHA,
                    imported_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "skills", "skill_id", skill_id)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — clauses
# ---------------------------------------------------------------------------


class TestP1Clauses:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_skill(conn)
            clause_id = f"cl-{suffix[:12]}"
            clauses_repo.insert_clause(
                conn,
                ClauseWrite(
                    clause_id=clause_id,
                    skill_id=_SKILL_ID,
                    clause_index=1,
                    rendering_index=1,
                    clause_text=suffix,
                    axis="ax",
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256=None,
                    created_at=_TS,
                ),
            )
            _assert_update_raises(conn, "clauses", "clause_id", clause_id)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_skill(conn)
            clause_id = f"cl-{suffix[:12]}"
            clauses_repo.insert_clause(
                conn,
                ClauseWrite(
                    clause_id=clause_id,
                    skill_id=_SKILL_ID,
                    clause_index=1,
                    rendering_index=1,
                    clause_text=suffix,
                    axis="ax",
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256=None,
                    created_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "clauses", "clause_id", clause_id)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — metric_versions (composite PK: metric_id + version)
# ---------------------------------------------------------------------------


class TestP1MetricVersions:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            mid = f"m-{suffix[:10]}"
            mv_repo.insert_metric_version(
                conn,
                MetricVersionWrite(
                    metric_id=mid,
                    version="1.0.0",
                    implementation_hash=_SHA,
                    tier=1,
                    audited=1,
                    mechanical_validity_test_passed=1,
                    registered_at=_TS,
                ),
            )
            with pytest.raises(
                sqlite3.IntegrityError, match="append_only_violation: metric_versions"
            ):
                conn.execute(
                    "UPDATE metric_versions SET audited = audited"
                    " WHERE metric_id = ? AND version = ?",
                    (mid, "1.0.0"),
                )
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            mid = f"m-{suffix[:10]}"
            mv_repo.insert_metric_version(
                conn,
                MetricVersionWrite(
                    metric_id=mid,
                    version="1.0.0",
                    implementation_hash=_SHA,
                    tier=1,
                    audited=1,
                    mechanical_validity_test_passed=1,
                    registered_at=_TS,
                ),
            )
            with pytest.raises(
                sqlite3.IntegrityError, match="append_only_violation: metric_versions"
            ):
                conn.execute(
                    "DELETE FROM metric_versions WHERE metric_id = ? AND version = ?",
                    (mid, "1.0.0"),
                )
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — judges
# ---------------------------------------------------------------------------


class TestP1Judges:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            jid = f"j-{suffix[:12]}"
            judges_repo.insert_judge(
                conn,
                JudgeWrite(judge_id=jid, model_id="m", system_prompt_sha256=_SHA, created_at=_TS),
            )
            _assert_update_raises(conn, "judges", "judge_id", jid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            jid = f"j-{suffix[:12]}"
            judges_repo.insert_judge(
                conn,
                JudgeWrite(judge_id=jid, model_id="m", system_prompt_sha256=_SHA, created_at=_TS),
            )
            _assert_delete_raises(conn, "judges", "judge_id", jid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — calibration_events
# ---------------------------------------------------------------------------


class TestP1CalibrationEvents:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_judge(conn)
            cid = f"c-{suffix[:12]}"
            calib_repo.insert_calibration_event(
                conn,
                CalibrationEventWrite(
                    calibration_event_id=cid,
                    judge_id=_JUDGE_ID,
                    axis="ax",
                    pairwise_agreement=0.9,
                    position_consistency=0.9,
                    length_controlled_agreement=None,
                    cohen_kappa=None,
                    pair_set_size=50,
                    pair_set_sha256=_SHA,
                    state="calibrated",
                    expires_at=None,
                    validated_at=_TS,
                ),
            )
            _assert_update_raises(conn, "calibration_events", "calibration_event_id", cid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_judge(conn)
            cid = f"c-{suffix[:12]}"
            calib_repo.insert_calibration_event(
                conn,
                CalibrationEventWrite(
                    calibration_event_id=cid,
                    judge_id=_JUDGE_ID,
                    axis="ax",
                    pairwise_agreement=0.9,
                    position_consistency=0.9,
                    length_controlled_agreement=None,
                    cohen_kappa=None,
                    pair_set_size=50,
                    pair_set_sha256=_SHA,
                    state="calibrated",
                    expires_at=None,
                    validated_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "calibration_events", "calibration_event_id", cid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — samples
# ---------------------------------------------------------------------------


class TestP1Samples:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-samp-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_run(conn, run_id)
            sid = f"s-{suffix[:12]}"
            samples_repo.insert_sample(
                conn,
                SampleWrite(
                    sample_id=sid,
                    run_id=run_id,
                    clause_id=_CLAUSE_ID,
                    condition="full",
                    subject_model="m",
                    subject_seed=None,
                    output_text="out",
                    output_sha256=_SHA,
                    sampled_at=_TS,
                ),
            )
            _assert_update_raises(conn, "samples", "sample_id", sid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-samp-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_run(conn, run_id)
            sid = f"s-{suffix[:12]}"
            samples_repo.insert_sample(
                conn,
                SampleWrite(
                    sample_id=sid,
                    run_id=run_id,
                    clause_id=_CLAUSE_ID,
                    condition="full",
                    subject_model="m",
                    subject_seed=None,
                    output_text="out",
                    output_sha256=_SHA,
                    sampled_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "samples", "sample_id", sid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — oracle_verdicts
# ---------------------------------------------------------------------------


class TestP1OracleVerdicts:
    # oracle_tier=1 requires: judge_id IS NULL, calibration_event_id IS NULL,
    # metric_id IS NOT NULL (per CHECK constraint in 0001_initial.sql).
    # Use _seed_metric_version to satisfy the FK + the NOT NULL requirement.

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-ov-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_samples(conn, run_id)
            _seed_metric_version(conn)
            vid = f"v-{suffix[:12]}"
            verdicts_repo.insert_oracle_verdict(
                conn,
                OracleVerdictWrite(
                    verdict_id=vid,
                    run_id=run_id,
                    clause_id=_CLAUSE_ID,
                    axis="ax",
                    comparison="full_vs_ablated",
                    sample_a_id=_SAMPLE_A_ID,
                    sample_b_id=_SAMPLE_B_ID,
                    observation=1.0,
                    oracle_tier=1,
                    metric_id=_METRIC_ID,
                    metric_version=_METRIC_VER,
                    judge_id=None,
                    calibration_event_id=None,
                    position_swap_agreement=None,
                    admissibility_state="admissible",
                    inadmissibility_reason=None,
                    written_at=_TS,
                ),
            )
            _assert_update_raises(conn, "oracle_verdicts", "verdict_id", vid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-ov-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_samples(conn, run_id)
            _seed_metric_version(conn)
            vid = f"v-{suffix[:12]}"
            verdicts_repo.insert_oracle_verdict(
                conn,
                OracleVerdictWrite(
                    verdict_id=vid,
                    run_id=run_id,
                    clause_id=_CLAUSE_ID,
                    axis="ax",
                    comparison="full_vs_ablated",
                    sample_a_id=_SAMPLE_A_ID,
                    sample_b_id=_SAMPLE_B_ID,
                    observation=1.0,
                    oracle_tier=1,
                    metric_id=_METRIC_ID,
                    metric_version=_METRIC_VER,
                    judge_id=None,
                    calibration_event_id=None,
                    position_swap_agreement=None,
                    admissibility_state="admissible",
                    inadmissibility_reason=None,
                    written_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "oracle_verdicts", "verdict_id", vid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — confound_events
# ---------------------------------------------------------------------------


class TestP1ConfoundEvents:
    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-ce-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_run(conn, run_id)
            ceid = f"ce-{suffix[:12]}"
            confound_repo.insert_confound_event(
                conn,
                ConfoundEventWrite(
                    confound_event_id=ceid,
                    run_id=run_id,
                    primary_clause_id=_CLAUSE_ID,
                    affected_clause_id=None,
                    axis="ax",
                    delta=0.3,
                    null_sigma=0.1,
                    k_threshold=2.0,
                    delta_kind="confound_flagged",
                    detected_at=_TS,
                ),
            )
            _assert_update_raises(conn, "confound_events", "confound_event_id", ceid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        run_id = f"run-ce-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_run(conn, run_id)
            ceid = f"ce-{suffix[:12]}"
            confound_repo.insert_confound_event(
                conn,
                ConfoundEventWrite(
                    confound_event_id=ceid,
                    run_id=run_id,
                    primary_clause_id=_CLAUSE_ID,
                    affected_clause_id=None,
                    axis="ax",
                    delta=0.3,
                    null_sigma=0.1,
                    k_threshold=2.0,
                    delta_kind="confound_flagged",
                    detected_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "confound_events", "confound_event_id", ceid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P1 — frozen_cases
# ---------------------------------------------------------------------------


class TestP1FrozenCases:
    # oracle_source='mechanical' requires metric_id, metric_version,
    # implementation_hash all NOT NULL (per CHECK constraint in 0001_initial.sql).
    # Seed the metric_version parent row to satisfy the FK.

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_metric_version(conn)
            fcid = f"fc-{suffix[:12]}"
            frozen_repo.insert_frozen_case(
                conn,
                FrozenCaseWrite(
                    frozen_case_id=fcid,
                    clause_id=_CLAUSE_ID,
                    failing_input_text="bad input",
                    failing_input_sha256=_SHA,
                    oracle_source="mechanical",
                    labeled_by=None,
                    labeled_at=None,
                    metric_id=_METRIC_ID,
                    metric_version=_METRIC_VER,
                    implementation_hash=_SHA,
                    frozen_at=_TS,
                ),
            )
            _assert_update_raises(conn, "frozen_cases", "frozen_case_id", fcid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_delete_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        conn = evidence_db_for_property_tests
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_clause(conn)
            _seed_metric_version(conn)
            fcid = f"fc-{suffix[:12]}"
            frozen_repo.insert_frozen_case(
                conn,
                FrozenCaseWrite(
                    frozen_case_id=fcid,
                    clause_id=_CLAUSE_ID,
                    failing_input_text="bad input",
                    failing_input_sha256=_SHA,
                    oracle_source="mechanical",
                    labeled_by=None,
                    labeled_at=None,
                    metric_id=_METRIC_ID,
                    metric_version=_METRIC_VER,
                    implementation_hash=_SHA,
                    frozen_at=_TS,
                ),
            )
            _assert_delete_raises(conn, "frozen_cases", "frozen_case_id", fcid)
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")


# ---------------------------------------------------------------------------
# P2 — runs carve-out (A20)
# ---------------------------------------------------------------------------


class TestP2Runs:
    """Property P2: runs immutable-column triggers + completed_at single-shot."""

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_update_immutable_columns_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        """UPDATE of skill_id, run_kind, config_json, or started_at raises
        IntegrityError matching the runs_immutable_columns trigger message."""
        conn = evidence_db_for_property_tests
        run_id = f"r2-{suffix[:12]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_skill(conn)
            runs_repo.insert_run(
                conn,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json="{}",
                    started_at=_TS,
                    completed_at=None,
                ),
            )
            # Each of the four immutable columns should raise
            for col, val in [
                ("skill_id", _SKILL_ID),
                ("run_kind", "ablation"),
                ("config_json", "{}"),
                ("started_at", _TS),
            ]:
                with pytest.raises(
                    sqlite3.IntegrityError,
                    match=r"append_only_violation:.*runs.*immutable",
                ):
                    conn.execute(
                        f"UPDATE runs SET {col} = ? WHERE run_id = ?",
                        (val, run_id),
                    )
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_completed_at_single_shot_succeeds(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        """First UPDATE of completed_at (NULL → value) SUCCEEDS."""
        conn = evidence_db_for_property_tests
        run_id = f"r2-ok-{suffix[:10]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_skill(conn)
            runs_repo.insert_run(
                conn,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json="{}",
                    started_at=_TS,
                    completed_at=None,
                ),
            )
            # First UPDATE of completed_at must succeed (no exception)
            conn.execute(
                "UPDATE runs SET completed_at = ? WHERE run_id = ?",
                (_TS, run_id),
            )
            cur = conn.execute("SELECT completed_at FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            assert row is not None and row[0] == _TS
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

    @given(suffix=_safe_text)
    @_PROP_SETTINGS
    def test_completed_at_second_update_raises(
        self, evidence_db_for_property_tests: sqlite3.Connection, suffix: str
    ) -> None:
        """Second UPDATE of completed_at raises IntegrityError (single-shot rule)."""
        conn = evidence_db_for_property_tests
        run_id = f"r2-once-{suffix[:8]}"
        conn.execute("SAVEPOINT hyp_example")
        try:
            _seed_skill(conn)
            runs_repo.insert_run(
                conn,
                RunWrite(
                    run_id=run_id,
                    skill_id=_SKILL_ID,
                    run_kind="ablation",
                    config_json="{}",
                    started_at=_TS,
                    completed_at=None,
                ),
            )
            # First update succeeds
            conn.execute("UPDATE runs SET completed_at = ? WHERE run_id = ?", (_TS, run_id))
            # Second update must raise
            with pytest.raises(
                sqlite3.IntegrityError,
                match=r"runs\.completed_at is immutable once set",
            ):
                conn.execute("UPDATE runs SET completed_at = ? WHERE run_id = ?", (_TS, run_id))
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")
