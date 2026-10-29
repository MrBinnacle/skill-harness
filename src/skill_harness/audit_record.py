"""Persisted, hash-bound record of a free `skill audit` run (#673).

The evidence-stage rule (#658) has an ``audited`` rung: a free audit ran and no
paid measurement exists. Its grade function may read only persisted facts, so
``skill audit --persist`` writes one JSON record per skill, and
:func:`audit_record_for` returns that record only while its sha256 still equals
the card's current SKILL.md. A stale record grants nothing.

The record is a committed file under ``docs/sers/audits/``, not an evidence
store row, so it needs no schema migration. Git keeps the history; the file
holds the latest audit only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from skill_harness import __version__
from skill_harness.extractor.parser import parse_skill_file
from skill_harness.preflight import ArtifactAuditReport

DEFAULT_AUDITS_DIR: Final[Path] = Path("docs/sers/audits")

# The skill name becomes a filename, so it must be a plain slug: no separators,
# no traversal, no case games on case-insensitive filesystems.
_SAFE_NAME: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class AuditRecordError(ValueError):
    """A record cannot be written or read safely."""


class StandingCost(BaseModel):
    """Router-listing tokens as the offline audit reports them.

    A calibrated estimate with its measured range, never an exact count. Both
    token fields are None when the frontmatter could not be measured.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    basis: Literal["calibrated_estimate"] = "calibrated_estimate"
    raw_tokens: int | None
    calibrated_tokens: int | None
    calibration_factor: float
    calibration_range: tuple[float, float]


class ClaimClassification(BaseModel):
    """What the evaluability preflight says a paid run could measure today."""

    model_config = ConfigDict(frozen=True, strict=True)

    tier1_mechanical_axes: tuple[str, ...]
    behavior_shaped: Literal["UNMEASURED"] = "UNMEASURED"
    judge_graded: Literal["UNMEASURED"] = "UNMEASURED"


class AuditRecord(BaseModel):
    """One skill's latest free audit, bound to the SKILL.md bytes it audited."""

    model_config = ConfigDict(frozen=True, strict=True)

    skill_name: str
    skill_md_sha256: str
    audit_tool_version: str
    audited_at_utc: str
    standing_cost: StandingCost
    claim_classification: ClaimClassification


def record_from_report(report: ArtifactAuditReport, *, audited_at_utc: str) -> AuditRecord:
    """Build a record from an audit report. The caller supplies the timestamp."""
    return AuditRecord(
        skill_name=report.name,
        skill_md_sha256=report.source_sha256,
        audit_tool_version=__version__,
        audited_at_utc=audited_at_utc,
        standing_cost=StandingCost(
            raw_tokens=report.standing_cost_raw,
            calibrated_tokens=report.standing_cost_calibrated,
            calibration_factor=report.standing_cost_calibration_factor,
            calibration_range=report.standing_cost_calibration_range,
        ),
        claim_classification=ClaimClassification(
            tier1_mechanical_axes=report.measurable_axes,
        ),
    )


def _record_path(skill_name: str, audits_dir: Path) -> Path:
    if not _SAFE_NAME.fullmatch(skill_name):
        raise AuditRecordError(
            f"skill name {skill_name!r} is not a lowercase slug; refusing to use it as a filename"
        )
    return audits_dir / f"{skill_name}.json"


def write_audit_record(record: AuditRecord, audits_dir: Path) -> Path:
    """Write ``<audits_dir>/<skill_name>.json``, replacing any earlier audit."""
    path = _record_path(record.skill_name, audits_dir)
    audits_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def audit_record_for(skill_md_path: Path, audits_dir: Path) -> AuditRecord | None:
    """Return the skill's audit record only if it audited the current SKILL.md.

    :returns: None when no record exists or its sha256 no longer matches.
    :raises AuditRecordError: the record file exists but does not parse.
    """
    parsed = parse_skill_file(skill_md_path)
    path = _record_path(parsed.name, audits_dir)
    if not path.is_file():
        return None
    try:
        record = AuditRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise AuditRecordError(f"{path}: not a valid audit record: {exc}") from exc
    if record.skill_md_sha256 != parsed.source_sha256 or record.skill_name != parsed.name:
        return None
    return record
