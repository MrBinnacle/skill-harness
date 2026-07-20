"""SkillReport dataclass + JSON serialisation (A60).

Schema version: "1.3.0" (semver). v0.1 lifetime is 1.x additive-only.
  1.1.0 — A55 comparability axes (subject_model, user_message_sha256).
  1.2.0 — coverage_warnings field on VectorSummary (M3 pre-tag fix).
  1.3.0 — is_prior_only field on ClauseReport (B5 hostile-review fix): True when a
          clause has zero admissible observations, so posterior_mean/CI/p_win_gt_threshold
          are an uninformative Beta(1,1) PRIOR (posterior_mean=0.5 etc.), not a
          measurement. The numeric fields keep their existing type/semantics
          (additive-only) — is_prior_only is the required guard a consumer must check
          before treating them as measured data.
Any breaking change (field removal, type change, rename) requires:
  1. Major version bump.
  2. A ``diff skill`` consumer compatibility check (E.3 territory).

Wire format rules (A60):
  - ``to_json_bytes`` produces UTF-8 bytes with sorted keys, no internal timestamps
    (only the top-level ``generated_at_utc`` field carries a timestamp).
  - Byte-stable: identical evidence → identical bytes (sort_keys=True,
    separators=(',', ':'), no datetime.now() calls inside this module).
  - Do NOT add Rich/Markdown rendering here — that is E.3 territory.

Caller responsibilities:
  - Supply ``generated_at_utc`` as an ISO8601 string. This module never calls
    datetime.now() (the determinism contract per the spec).
  - Supply ``harness_version`` from the installed package metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

REPORT_SCHEMA_VERSION = "1.3.0"


@dataclass(frozen=True)
class VectorSummary:
    """§16 clause-status vector."""

    passed: int
    failed: int
    confounded: int
    unmeasured: int
    unmeasured_breakdown: dict[str, int]  # sub_reason -> count
    coverage: float  # tested_clauses / total_clauses
    # per-root-cause UNMEASURED explanations (M3 pre-tag fix)
    coverage_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContributionSummary:
    """Full-vs-Null delta summary (A50 framing).

    full_vs_null_delta:
        Mean observation delta between Full and Null conditions across all
        admissible full_vs_null verdicts. None when no such verdicts exist.

    label:
        Fixed framing string per A50 — captures LOO/redundancy limitation.
    """

    full_vs_null_delta: float | None
    label: str = "single-clause LOO; lower-bound under redundancy"


@dataclass(frozen=True)
class ClauseReport:
    """Per-clause aggregation result row."""

    clause_id: str
    status: str  # ClauseStatus value
    sub_reason: str | None  # UnmeasuredSubReason value when status=UNMEASURED
    posterior_mean: float
    credible_interval_95: tuple[float, float]
    p_win_gt_threshold: float
    frozen_case_count_at_current_metric_version: int
    metric_id_per_axis: dict[str, str]  # axis -> metric_id
    metric_version_per_axis: dict[str, str]  # axis -> metric_version
    ablation_operator_hash: str
    run_ids_aggregated: tuple[str, ...]
    n_verdicts: int
    w_observation_sum: float
    # A55 comparability axes added in schema 1.1.0 (A60 additive bump)
    subject_model: str | None  # model used for all runs; "MIXED" if divergent across runs
    user_message_sha256: str | None  # sha256 of user_message from config_json; "MIXED" if divergent
    # B5 (schema 1.3.0): True when this clause has zero admissible observations —
    # posterior_mean/credible_interval_95/p_win_gt_threshold are an uninformative
    # Beta(1,1) PRIOR, not a measurement. Consumers MUST check this before treating
    # the numeric fields as measured data.
    is_prior_only: bool = False


@dataclass(frozen=True)
class SkillReport:
    """Top-level skill aggregation report.

    Produced by ``aggregate_skill()`` and serialised by ``to_json_dict()`` /
    ``to_json_bytes()``. Rich/Markdown rendering is E.3 territory.
    """

    report_schema_version: str  # always REPORT_SCHEMA_VERSION ("1.1.0")
    skill_id: str
    generated_at_utc: str  # ISO8601 — caller-supplied; never datetime.now() here
    harness_version: str
    aggregation_method: str  # "ebmom_hierarchical" | "bh_fdr_fallback" | "unpooled"
    aggregation_provenance: dict[str, object]
    clauses: tuple[ClauseReport, ...]
    vector: VectorSummary
    coverage: float  # tested_clauses / total_clauses
    contribution: ContributionSummary


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _clause_to_dict(clause: ClauseReport) -> dict[str, object]:
    return {
        "clause_id": clause.clause_id,
        "status": clause.status,
        "sub_reason": clause.sub_reason,
        "posterior_mean": clause.posterior_mean,
        "credible_interval_95": list(clause.credible_interval_95),
        "p_win_gt_threshold": clause.p_win_gt_threshold,
        "frozen_case_count_at_current_metric_version": (
            clause.frozen_case_count_at_current_metric_version
        ),
        "metric_id_per_axis": dict(clause.metric_id_per_axis),
        "metric_version_per_axis": dict(clause.metric_version_per_axis),
        "ablation_operator_hash": clause.ablation_operator_hash,
        "run_ids_aggregated": list(clause.run_ids_aggregated),
        "n_verdicts": clause.n_verdicts,
        "w_observation_sum": clause.w_observation_sum,
        "subject_model": clause.subject_model,
        "user_message_sha256": clause.user_message_sha256,
        "is_prior_only": clause.is_prior_only,
    }


def _vector_to_dict(vector: VectorSummary) -> dict[str, object]:
    return {
        "passed": vector.passed,
        "failed": vector.failed,
        "confounded": vector.confounded,
        "unmeasured": vector.unmeasured,
        "unmeasured_breakdown": dict(vector.unmeasured_breakdown),
        "coverage": vector.coverage,
        "coverage_warnings": list(vector.coverage_warnings),
    }


def _contribution_to_dict(contribution: ContributionSummary) -> dict[str, object]:
    return {
        "full_vs_null_delta": contribution.full_vs_null_delta,
        "label": contribution.label,
    }


def to_json_dict(report: SkillReport) -> dict[str, object]:
    """Convert a SkillReport to a JSON-serialisable dict.

    All nested dataclasses are flattened to plain Python types (dict/list/str/float/int/None).
    The output is byte-stable when serialised with sort_keys=True (no internal timestamps
    or random state).
    """
    return {
        "report_schema_version": report.report_schema_version,
        "skill_id": report.skill_id,
        "generated_at_utc": report.generated_at_utc,
        "harness_version": report.harness_version,
        "aggregation_method": report.aggregation_method,
        "aggregation_provenance": dict(report.aggregation_provenance),
        "clauses": [_clause_to_dict(c) for c in report.clauses],
        "vector": _vector_to_dict(report.vector),
        "coverage": report.coverage,
        "contribution": _contribution_to_dict(report.contribution),
    }


def to_json_bytes(report: SkillReport) -> bytes:
    """Serialise a SkillReport to UTF-8 JSON bytes.

    Byte-stable for identical evidence:
      - sort_keys=True  (canonical key order)
      - separators=(',', ':')  (compact, no trailing whitespace)
      - trailing newline (POSIX convention)

    The single non-deterministic field is ``generated_at_utc`` (caller-supplied).
    All other fields are derived from the DB evidence deterministically.
    """
    d = to_json_dict(report)
    return (
        json.dumps(d, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        + b"\n"
    )


# ---------------------------------------------------------------------------
# Convenience: build from dataclass dict (for tests)
# ---------------------------------------------------------------------------


def skill_report_from_dict(d: dict[str, Any]) -> SkillReport:
    """Reconstruct a SkillReport from a to_json_dict() output (for round-trip tests).

    Not used in production paths — E.3 reads structured data, not re-parses JSON.
    Uses Any for d because JSON round-trip loses type information.
    """
    clauses = tuple(
        ClauseReport(
            clause_id=str(c["clause_id"]),
            status=str(c["status"]),
            sub_reason=c.get("sub_reason"),
            posterior_mean=float(c["posterior_mean"]),
            credible_interval_95=(
                float(c["credible_interval_95"][0]),
                float(c["credible_interval_95"][1]),
            ),
            p_win_gt_threshold=float(c["p_win_gt_threshold"]),
            frozen_case_count_at_current_metric_version=int(
                c["frozen_case_count_at_current_metric_version"]
            ),
            metric_id_per_axis=dict(c["metric_id_per_axis"]),
            metric_version_per_axis=dict(c["metric_version_per_axis"]),
            ablation_operator_hash=str(c["ablation_operator_hash"]),
            run_ids_aggregated=tuple(str(r) for r in c["run_ids_aggregated"]),
            n_verdicts=int(c["n_verdicts"]),
            w_observation_sum=float(c["w_observation_sum"]),
            subject_model=c.get("subject_model"),
            user_message_sha256=c.get("user_message_sha256"),
            is_prior_only=bool(c.get("is_prior_only", False)),
        )
        for c in d["clauses"]
    )
    vec: dict[str, Any] = d["vector"]
    vector = VectorSummary(
        passed=int(vec["passed"]),
        failed=int(vec["failed"]),
        confounded=int(vec["confounded"]),
        unmeasured=int(vec["unmeasured"]),
        unmeasured_breakdown=dict(vec["unmeasured_breakdown"]),
        coverage=float(vec["coverage"]),
        coverage_warnings=list(vec.get("coverage_warnings", [])),
    )
    contrib: dict[str, Any] = d["contribution"]
    delta = contrib["full_vs_null_delta"]
    contribution = ContributionSummary(
        full_vs_null_delta=float(delta) if delta is not None else None,
        label=str(contrib["label"]),
    )
    return SkillReport(
        report_schema_version=str(d["report_schema_version"]),
        skill_id=str(d["skill_id"]),
        generated_at_utc=str(d["generated_at_utc"]),
        harness_version=str(d["harness_version"]),
        aggregation_method=str(d["aggregation_method"]),
        aggregation_provenance=dict(d["aggregation_provenance"]),
        clauses=clauses,
        vector=vector,
        coverage=float(d["coverage"]),
        contribution=contribution,
    )
