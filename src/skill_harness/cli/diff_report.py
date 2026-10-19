"""DiffReport dataclass + JSON serialisation for `diff skill` (Track E.3, A55).

Schema version: "1.0.0" — mirrors SkillReport versioning discipline.
Byte-stable for identical evidence (sort_keys=True in to_json_bytes).

Status delta enum (A55):
  regressed     — A's status was better than B's
  improved      — B's status is better than A's
  unchanged     — both have the same status
  new           — clause exists in B but not A (no sha256 match)
  removed       — clause exists in A but not B
  metric_drift  — metric_id, metric_version, or ablation_operator_hash differ
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

REPORT_SCHEMA_VERSION = "1.0.0"

# Status ordering for improved/regressed comparison (A55).
# Lower = worse, higher = better.
_STATUS_RANK: dict[str, int] = {
    "FAILED": 0,
    "CONFOUNDED": 1,
    "UNMEASURED": 2,
    "PASSED": 3,
}


def status_delta(status_a: str, status_b: str) -> str:
    """Compute the per-clause status delta per A55 ordering.

    Ordering (low→high): FAILED < CONFOUNDED < UNMEASURED < PASSED

    Returns one of: 'regressed' | 'improved' | 'unchanged' | 'metric_drift'
    (caller is responsible for 'new' and 'removed').
    """
    rank_a = _STATUS_RANK.get(status_a, 2)  # unknown → UNMEASURED rank
    rank_b = _STATUS_RANK.get(status_b, 2)
    if rank_a == rank_b:
        return "unchanged"
    if rank_b > rank_a:
        return "improved"
    return "regressed"


@dataclass(frozen=True)
class ClauseDiff:
    """Per-clause diff result."""

    clause_text_sha256: str
    axis: str
    status_a: str | None  # None when 'new' (not in A)
    status_b: str | None  # None when 'removed' (not in B)
    delta: str  # regressed | improved | unchanged | new | removed | metric_drift
    # Optional detail fields for metric_drift
    metric_drift_reason: str | None


@dataclass(frozen=True)
class DiffReport:
    """Top-level diff report between two SkillReports.

    Produced by `diff skill <skill_id_a> <skill_id_b>`.
    Serialised by to_json_dict() / to_json_bytes().
    """

    report_schema_version: str  # always "1.0.0"
    skill_id_a: str
    skill_id_b: str
    generated_at_utc: str  # ISO8601 — caller-supplied
    harness_version: str
    clauses: tuple[ClauseDiff, ...]
    divergent: bool  # True if any clause delta != 'unchanged'


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _clause_diff_to_dict(cd: ClauseDiff) -> dict[str, Any]:
    return {
        "clause_text_sha256": cd.clause_text_sha256,
        "axis": cd.axis,
        "status_a": cd.status_a,
        "status_b": cd.status_b,
        "delta": cd.delta,
        "metric_drift_reason": cd.metric_drift_reason,
    }


def to_json_dict(report: DiffReport) -> dict[str, Any]:
    """Convert DiffReport to a JSON-serialisable dict."""
    return {
        "report_schema_version": report.report_schema_version,
        "skill_id_a": report.skill_id_a,
        "skill_id_b": report.skill_id_b,
        "generated_at_utc": report.generated_at_utc,
        "harness_version": report.harness_version,
        "clauses": [_clause_diff_to_dict(c) for c in report.clauses],
        "divergent": report.divergent,
    }


def to_json_bytes(report: DiffReport) -> bytes:
    """Serialise DiffReport to UTF-8 JSON bytes (byte-stable, sort_keys=True)."""
    d = to_json_dict(report)
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
