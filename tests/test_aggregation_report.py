"""Tests for aggregation/report.py — SkillReport serialization (A60).

Coverage:
- to_json_dict produces all required top-level keys
- report_schema_version = "1.0.0"
- to_json_bytes is byte-stable for identical input
- to_json_bytes is UTF-8 with trailing newline
- Nested structures serialise correctly (tuples → lists, etc.)
- Round-trip: to_json_dict → skill_report_from_dict reconstructs equal fields
"""

from __future__ import annotations

import json

from skill_harness.aggregation.report import (
    REPORT_SCHEMA_VERSION,
    ClauseReport,
    ContributionSummary,
    SkillReport,
    VectorSummary,
    skill_report_from_dict,
    to_json_bytes,
    to_json_dict,
)

# ---------------------------------------------------------------------------
# Fixture: minimal valid SkillReport
# ---------------------------------------------------------------------------


def make_clause_report(
    clause_id: str = "c1",
    status: str = "PASSED",
    sub_reason: str | None = None,
    p: float = 0.97,
    n: int = 12,
    w: float = 9.0,
) -> ClauseReport:
    return ClauseReport(
        clause_id=clause_id,
        status=status,
        sub_reason=sub_reason,
        posterior_mean=0.75,
        credible_interval_95=(0.55, 0.90),
        p_win_gt_threshold=p,
        frozen_case_count_at_current_metric_version=1,
        metric_id_per_axis={"verbosity": "metric_v1"},
        metric_version_per_axis={"verbosity": "1.0.0"},
        ablation_operator_hash="abc123",
        run_ids_aggregated=("run-001",),
        n_verdicts=n,
        w_observation_sum=w,
    )


def make_skill_report(
    skill_id: str = "skill-abc",
    clause_reports: tuple[ClauseReport, ...] | None = None,
) -> SkillReport:
    if clause_reports is None:
        clause_reports = (make_clause_report(),)
    vector = VectorSummary(
        passed=1,
        failed=0,
        confounded=0,
        unmeasured=0,
        unmeasured_breakdown={},
        coverage=1.0,
    )
    contribution = ContributionSummary(
        full_vs_null_delta=0.25,
        label="single-clause LOO; lower-bound under redundancy",
    )
    return SkillReport(
        report_schema_version=REPORT_SCHEMA_VERSION,
        skill_id=skill_id,
        generated_at_utc="2026-06-06T12:00:00.000Z",
        harness_version="0.1.0a0",
        aggregation_method="ebmom_hierarchical",
        aggregation_provenance={
            "alpha_hat": 3.5,
            "beta_hat": 2.1,
            "sample_mean": 0.625,
            "sample_var": 0.012,
            "k_clauses": 10,
            "family_size_used": 10,
        },
        clauses=clause_reports,
        vector=vector,
        coverage=1.0,
        contribution=contribution,
    )


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_report_schema_version_constant(self) -> None:
        assert REPORT_SCHEMA_VERSION == "1.0.0"

    def test_schema_version_in_dict(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        assert d["report_schema_version"] == "1.0.0"

    def test_schema_version_in_bytes(self) -> None:
        report = make_skill_report()
        data = json.loads(to_json_bytes(report))
        assert data["report_schema_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Required top-level keys
# ---------------------------------------------------------------------------


REQUIRED_TOP_LEVEL_KEYS = {
    "report_schema_version",
    "skill_id",
    "generated_at_utc",
    "harness_version",
    "aggregation_method",
    "aggregation_provenance",
    "clauses",
    "vector",
    "coverage",
    "contribution",
}


class TestRequiredKeys:
    def test_all_required_keys_present(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        missing = REQUIRED_TOP_LEVEL_KEYS - set(d.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_clause_required_keys(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        clause_keys = {
            "clause_id",
            "status",
            "sub_reason",
            "posterior_mean",
            "credible_interval_95",
            "p_win_gt_threshold",
            "frozen_case_count_at_current_metric_version",
            "metric_id_per_axis",
            "metric_version_per_axis",
            "ablation_operator_hash",
            "run_ids_aggregated",
            "n_verdicts",
            "w_observation_sum",
        }
        for clause_dict in d["clauses"]:  # type: ignore[union-attr]
            missing = clause_keys - set(clause_dict.keys())
            assert not missing, f"Missing clause keys: {missing}"

    def test_vector_required_keys(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        vector_keys = {
            "passed",
            "failed",
            "confounded",
            "unmeasured",
            "unmeasured_breakdown",
            "coverage",
        }
        vec = d["vector"]
        assert isinstance(vec, dict)
        missing = vector_keys - set(vec.keys())  # type: ignore[union-attr]
        assert not missing

    def test_contribution_required_keys(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        contrib_keys = {"full_vs_null_delta", "label"}
        contrib = d["contribution"]
        assert isinstance(contrib, dict)
        missing = contrib_keys - set(contrib.keys())  # type: ignore[union-attr]
        assert not missing


# ---------------------------------------------------------------------------
# Byte stability
# ---------------------------------------------------------------------------


class TestByteStability:
    def test_byte_stable_identical_input(self) -> None:
        """Same input → identical bytes."""
        report = make_skill_report()
        b1 = to_json_bytes(report)
        b2 = to_json_bytes(report)
        assert b1 == b2

    def test_byte_stable_same_content_different_instances(self) -> None:
        """Two independently-constructed identical reports → identical bytes."""
        r1 = make_skill_report()
        r2 = make_skill_report()
        assert to_json_bytes(r1) == to_json_bytes(r2)

    def test_different_skill_id_different_bytes(self) -> None:
        r1 = make_skill_report(skill_id="skill-a")
        r2 = make_skill_report(skill_id="skill-b")
        assert to_json_bytes(r1) != to_json_bytes(r2)

    def test_trailing_newline(self) -> None:
        report = make_skill_report()
        b = to_json_bytes(report)
        assert b.endswith(b"\n")

    def test_valid_utf8(self) -> None:
        report = make_skill_report()
        b = to_json_bytes(report)
        decoded = b.decode("utf-8")  # should not raise
        assert len(decoded) > 0

    def test_sorted_keys(self) -> None:
        """JSON output uses sorted keys (byte-stable contract)."""
        report = make_skill_report()
        b = to_json_bytes(report)
        d = json.loads(b)
        keys = list(d.keys())
        assert keys == sorted(keys)

    def test_compact_separators(self) -> None:
        """Output uses compact separators (no space after : or ,)."""
        report = make_skill_report()
        b = to_json_bytes(report)
        text = b.decode("utf-8")
        # No ": " or ", " in compact JSON (outside string values)
        # Crude but effective: check the raw structure
        assert '": ' not in text.split('"skill_id"')[0] or True  # OK if in values
        # More robust: re-parse and re-encode with same settings
        reparsed = json.dumps(json.loads(b), sort_keys=True, separators=(",", ":")).encode("utf-8")
        assert b == reparsed + b"\n"


# ---------------------------------------------------------------------------
# Serialisation correctness
# ---------------------------------------------------------------------------


class TestSerialisationCorrectness:
    def test_tuples_serialised_as_lists(self) -> None:
        """credible_interval_95 (tuple) → list in JSON."""
        report = make_skill_report()
        d = to_json_dict(report)
        clause = d["clauses"][0]  # type: ignore[index]
        ci = clause["credible_interval_95"]  # type: ignore[index]
        assert isinstance(ci, list)
        assert len(ci) == 2

    def test_run_ids_aggregated_serialised_as_list(self) -> None:
        report = make_skill_report()
        d = to_json_dict(report)
        clause = d["clauses"][0]  # type: ignore[index]
        assert isinstance(clause["run_ids_aggregated"], list)  # type: ignore[index]

    def test_sub_reason_none_serialised(self) -> None:
        """PASSED clause with sub_reason=None → null in JSON."""
        report = make_skill_report()
        d = to_json_dict(report)
        clause = d["clauses"][0]  # type: ignore[index]
        assert clause["status"] == "PASSED"
        assert clause["sub_reason"] is None  # type: ignore[index]

    def test_unmeasured_with_sub_reason(self) -> None:
        """UNMEASURED clause with sub_reason → serialised correctly."""
        cr = make_clause_report(
            status="UNMEASURED",
            sub_reason="no_data",
            p=0.5,
        )
        report = make_skill_report(clause_reports=(cr,))
        d = to_json_dict(report)
        clause = d["clauses"][0]  # type: ignore[index]
        assert clause["status"] == "UNMEASURED"  # type: ignore[index]
        assert clause["sub_reason"] == "no_data"  # type: ignore[index]

    def test_full_vs_null_delta_none(self) -> None:
        """ContributionSummary with delta=None → null in JSON."""
        vector = VectorSummary(
            passed=0,
            failed=0,
            confounded=0,
            unmeasured=1,
            unmeasured_breakdown={"no_data": 1},
            coverage=0.0,
        )
        report = SkillReport(
            report_schema_version=REPORT_SCHEMA_VERSION,
            skill_id="s",
            generated_at_utc="2026-06-06T00:00:00Z",
            harness_version="0.1.0",
            aggregation_method="unpooled",
            aggregation_provenance={"k_clauses": 1, "reason": "k_below_10", "family_size_used": 1},
            clauses=(make_clause_report(status="UNMEASURED", sub_reason="no_data"),),
            vector=vector,
            coverage=0.0,
            contribution=ContributionSummary(full_vs_null_delta=None),
        )
        d = to_json_dict(report)
        assert d["contribution"]["full_vs_null_delta"] is None  # type: ignore[index]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_round_trip_preserves_skill_id(self) -> None:
        report = make_skill_report(skill_id="round-trip-test")
        reconstructed = skill_report_from_dict(to_json_dict(report))
        assert reconstructed.skill_id == report.skill_id

    def test_round_trip_preserves_clause_count(self) -> None:
        clauses = (
            make_clause_report("c1"),
            make_clause_report("c2", status="FAILED", p=0.02),
        )
        report = make_skill_report(clause_reports=clauses)
        reconstructed = skill_report_from_dict(to_json_dict(report))
        assert len(reconstructed.clauses) == 2

    def test_round_trip_preserves_vector(self) -> None:
        report = make_skill_report()
        reconstructed = skill_report_from_dict(to_json_dict(report))
        assert reconstructed.vector.passed == report.vector.passed
        assert reconstructed.vector.coverage == report.vector.coverage
