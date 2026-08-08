"""Dual corpus coverage: constructible vs instantiated (#121, #136).

Two distinct figures, always reported side by side, never blended:

- **Constructible coverage** — clauses with a structurally complete
  ``falsifying_case`` / total clauses. Zero-power: offline over clause JSONL.
  Independent of ``vacuity_flag`` (#136): a flagged clause may still carry a
  complete case (detector false positive), and a non-flagged clause may lack one.
- **Instantiated coverage** — clauses with ≥1 row in ``frozen_cases`` / total
  clauses. Comes from the evidence database. When the freeze stage has never
  produced an instantiated case (or no evidence DB is supplied), this figure is
  a **named refusal**, never a fabricated ``0%``.

Also reports the case-presence x ``vacuity_flag==none`` cross-tabulation and
states whether constructible coverage is independent of ``vacuity_flag`` on
the given input or equal to the vacuity_none fraction by construction
(off-diagonal empty).

Per-skill and corpus-wide. Failed extractions and metadata rows stay out of
every denominator. Boolean-only ``falsifying_case`` schemas inherit the census
refusal (``unmeasurable_for_this_input``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, TextIO

from skill_harness.extractor.corpus_census import (
    CensusResult,
    SkillCensusRow,
    falsifying_case_complete,
    run_census,
)
from skill_harness.storage.migrations import open_evidence

_MISSING_STAGE_NOTE: Final[str] = (
    "No stage exists that converts an extractor input_population_spec into a "
    "frozen_cases.failing_input_text. Such a stage would require: draw a concrete "
    "input from the population spec; bind an oracle - a human label, or a "
    "registered mechanical scorer with metric_id / metric_version / "
    "implementation_hash. Out of scope for this measurement."
)

_REASON_NO_EVIDENCE: Final[str] = (
    "no_evidence_database: instantiated coverage requires an evidence DB path; none was supplied"
)
_REASON_NO_INSTANTIATED: Final[str] = (
    "no_instantiated_frozen_cases: clauses exist but none has an instantiated "
    "failing input in frozen_cases yet (instrument gap; freeze stage has not "
    "produced oracle-bound cases). Not a finding that clauses were checked and "
    "none is testable."
)
_REASON_NO_CLAUSES: Final[str] = "no_clauses: skill has zero authored clauses"
_REASON_MIXED_GENERATIONS: Final[str] = (
    "mixed_extractor_generations: corpus rows come from more than one extractor "
    "instrument generation; refusing to merge into one coverage figure"
)


@dataclass(frozen=True)
class CoverageFigure:
    """One coverage figure: either measured with counts, or a named refusal."""

    label: Literal["constructible", "instantiated"]
    status: Literal["measured", "refused", "unmeasurable_for_this_input"]
    reason: str | None
    numerator: int
    denominator: int

    def to_receipt(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "denominator": self.denominator,
            "label": self.label,
            "numerator": self.numerator,
            "status": self.status,
        }
        if self.status == "measured":
            base["percent"] = _percent(self.numerator, self.denominator)
            base["what_it_measures"] = _WHAT[self.label]
        else:
            base["reason"] = self.reason
            base["what_it_measures"] = _WHAT[self.label]
            # Deliberately omit percent so a reader cannot mistake a refusal for 0%.
        return base


_WHAT: Final[dict[str, str]] = {
    "constructible": (
        "fraction of clauses that carry a structurally complete falsifying_case "
        "(constructible test); zero-power, no runs"
    ),
    "instantiated": (
        "fraction of clauses with >=1 row in frozen_cases "
        "(instantiated failing input with oracle binding); engine coverage metric"
    ),
}


@dataclass(frozen=True)
class SkillCoverageRow:
    slug: str
    constructible: CoverageFigure
    instantiated: CoverageFigure


@dataclass(frozen=True)
class DetectorFalsePositive:
    """Flagged (vacuity_flag != none) clause that still carries a complete case."""

    slug: str
    clause_index: int | None
    clause_text: str
    axis: str
    vacuity_flag: str


@dataclass(frozen=True)
class CaseVacuityCrosstab:
    """Cross-tab of falsifying-case presence against vacuity_flag == 'none'."""

    none_with_case: int
    none_without_case: int
    flagged_with_case: int
    flagged_without_case: int
    # independent: off-diagonal non-empty, so constructible can disagree with
    # vacuity_none/total. equal_by_construction: off-diagonal empty on this input
    # (case presence coincides with vacuity_flag==none).
    constructible_vs_vacuity_flag: Literal["independent", "equal_by_construction"]
    detector_false_positives: tuple[DetectorFalsePositive, ...]

    def to_receipt(self) -> dict[str, Any]:
        return {
            "cells": {
                "flagged_with_case": self.flagged_with_case,
                "flagged_without_case": self.flagged_without_case,
                "none_with_case": self.none_with_case,
                "none_without_case": self.none_without_case,
            },
            "constructible_vs_vacuity_flag": self.constructible_vs_vacuity_flag,
            "detector_false_positives": [
                {
                    "axis": fp.axis,
                    "clause_index": fp.clause_index,
                    "clause_text": fp.clause_text,
                    "slug": fp.slug,
                    "vacuity_flag": fp.vacuity_flag,
                }
                for fp in self.detector_false_positives
            ],
            "detector_false_positives_count": len(self.detector_false_positives),
            "what_it_measures": (
                "cross-tab of structurally complete falsifying_case presence "
                "against vacuity_flag=='none'; flagged_with_case cells are "
                "detector false positives (surfaced, not discarded)"
            ),
        }


@dataclass(frozen=True)
class CoverageResult:
    """Dual coverage receipt: constructible + instantiated, per skill and corpus."""

    input_path: str
    evidence_path: str | None
    extractor_model: str | None
    system_prompt_sha256: str | None
    tool_schema_sha256: str | None
    extractor_generation_status: Literal["known", "unknown", "mixed"]
    extractor_generation_reason: str | None
    rows_total: int
    metadata_rows_skipped: int
    skills_covered: int
    failed_extraction_slugs: tuple[str, ...]
    total_clauses: int
    corpus_constructible: CoverageFigure
    corpus_instantiated: CoverageFigure
    per_skill: tuple[SkillCoverageRow, ...]
    missing_stage_note: str
    case_vacuity_crosstab: CaseVacuityCrosstab

    def to_receipt(self) -> dict[str, Any]:
        failed = list(self.failed_extraction_slugs)
        return {
            "case_vacuity_crosstab": self.case_vacuity_crosstab.to_receipt(),
            "corpus": {
                "constructible_coverage": self.corpus_constructible.to_receipt(),
                "instantiated_coverage": self.corpus_instantiated.to_receipt(),
                "total_clauses": self.total_clauses,
            },
            "evidence_path": self.evidence_path,
            "extractor_generation": {
                "reason": self.extractor_generation_reason,
                "status": self.extractor_generation_status,
                "system_prompt_sha256": self.system_prompt_sha256,
                "tool_schema_sha256": self.tool_schema_sha256,
            },
            "extractor_model": self.extractor_model,
            "failed_extractions": {"count": len(failed), "slugs": failed},
            "input_path": self.input_path,
            "metadata_rows_skipped": self.metadata_rows_skipped,
            "missing_stage_note": self.missing_stage_note,
            "per_skill": [
                {
                    "constructible_coverage": row.constructible.to_receipt(),
                    "instantiated_coverage": row.instantiated.to_receipt(),
                    "slug": row.slug,
                }
                for row in self.per_skill
            ],
            "rows_total": self.rows_total,
            "skills_covered": self.skills_covered,
            "system_prompt_sha256": self.system_prompt_sha256,
            "tool_schema_sha256": self.tool_schema_sha256,
        }


def _percent(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return float(f"{(100.0 * count) / total:.6f}")


def _constructible_figure(row: SkillCensusRow) -> CoverageFigure:
    if row.falsifying_case_status == "unmeasurable_for_this_input":
        return CoverageFigure(
            label="constructible",
            status="unmeasurable_for_this_input",
            reason=row.falsifying_case_reason,
            numerator=0,
            denominator=row.total_clauses,
        )
    return CoverageFigure(
        label="constructible",
        status="measured",
        reason=None,
        numerator=row.constructible_count,
        denominator=row.total_clauses,
    )


def _corpus_constructible(census: CensusResult) -> CoverageFigure:
    if census.falsifying_case_status == "unmeasurable_for_this_input":
        return CoverageFigure(
            label="constructible",
            status="unmeasurable_for_this_input",
            reason=census.falsifying_case_reason,
            numerator=0,
            denominator=census.total_clauses,
        )
    # Constructible = structurally complete FC / total clauses (not vacuity-none only).
    complete = sum(row.constructible_count for row in census.per_skill)
    return CoverageFigure(
        label="constructible",
        status="measured",
        reason=None,
        numerator=complete,
        denominator=census.total_clauses,
    )


def _load_instantiated_index(
    evidence_path: Path,
) -> tuple[dict[tuple[str, int], bool], int]:
    """Return ((skill_name, clause_index) -> has_frozen_case, total_frozen_case_rows).

    skill_name is ``skills.name`` and is matched to JSONL ``slug``.
    """
    conn = open_evidence(evidence_path)
    try:
        frozen_total = int(conn.execute("SELECT COUNT(*) FROM frozen_cases").fetchone()[0])
        rows = conn.execute(
            """
            SELECT s.name, c.clause_index,
                   EXISTS(
                       SELECT 1 FROM frozen_cases f WHERE f.clause_id = c.clause_id
                   ) AS has_frozen
            FROM clauses c
            JOIN skills s ON s.skill_id = c.skill_id
            """
        ).fetchall()
        index: dict[tuple[str, int], bool] = {}
        for name, clause_index, has_frozen in rows:
            index[(str(name), int(clause_index))] = bool(has_frozen)
        return index, frozen_total
    finally:
        conn.close()


def _parse_clause_index(clause: Mapping[str, Any]) -> int | None:
    raw = clause.get("clause_index")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _skill_clauses_by_slug(input_path: Path) -> dict[str, list[Mapping[str, Any]]]:
    """slug -> clauses for ok skills (metadata / failed excluded)."""
    text = Path(input_path).read_text(encoding="utf-8")
    out: dict[str, list[Mapping[str, Any]]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            continue
        if "record_type" in obj or "slug" not in obj:
            continue
        if not bool(obj.get("ok", True)):
            continue
        slug = str(obj["slug"])
        raw = obj.get("clauses")
        clauses: list[Mapping[str, Any]] = []
        if isinstance(raw, list):
            clauses = [c for c in raw if isinstance(c, Mapping)]
        out[slug] = clauses
    return out


def _build_case_vacuity_crosstab(
    clauses_by_slug: Mapping[str, list[Mapping[str, Any]]],
) -> CaseVacuityCrosstab:
    """Cross-tab case presence against vacuity_flag==none; surface detector FPs."""
    none_with = 0
    none_without = 0
    flagged_with = 0
    flagged_without = 0
    fps: list[DetectorFalsePositive] = []
    for slug in sorted(clauses_by_slug):
        for clause in clauses_by_slug[slug]:
            is_none = clause.get("vacuity_flag") == "none"
            has_case = falsifying_case_complete(clause)
            if is_none and has_case:
                none_with += 1
            elif is_none and not has_case:
                none_without += 1
            elif (not is_none) and has_case:
                flagged_with += 1
                vacuity = clause.get("vacuity_flag")
                axis = clause.get("axis")
                text = clause.get("clause_text")
                fps.append(
                    DetectorFalsePositive(
                        slug=slug,
                        clause_index=_parse_clause_index(clause),
                        clause_text=text if isinstance(text, str) else "",
                        axis=axis if isinstance(axis, str) else "",
                        vacuity_flag=str(vacuity) if vacuity is not None else "",
                    )
                )
            else:
                flagged_without += 1
    # Off-diagonal empty <=> case presence coincides with vacuity_flag==none.
    if none_without == 0 and flagged_with == 0:
        relation: Literal["independent", "equal_by_construction"] = "equal_by_construction"
    else:
        relation = "independent"
    return CaseVacuityCrosstab(
        none_with_case=none_with,
        none_without_case=none_without,
        flagged_with_case=flagged_with,
        flagged_without_case=flagged_without,
        constructible_vs_vacuity_flag=relation,
        detector_false_positives=tuple(fps),
    )


def _instantiated_for_scope(
    *,
    denominator: int,
    instantiated_count: int,
    evidence_supplied: bool,
    corpus_frozen_total: int | None,
) -> CoverageFigure:
    if not evidence_supplied:
        return CoverageFigure(
            label="instantiated",
            status="refused",
            reason=_REASON_NO_EVIDENCE,
            numerator=0,
            denominator=denominator,
        )
    if denominator == 0:
        return CoverageFigure(
            label="instantiated",
            status="refused",
            reason=_REASON_NO_CLAUSES,
            numerator=0,
            denominator=0,
        )
    # Corpus-wide instrument gap: freeze stage never produced any case.
    if corpus_frozen_total is not None and corpus_frozen_total == 0:
        return CoverageFigure(
            label="instantiated",
            status="refused",
            reason=_REASON_NO_INSTANTIATED,
            numerator=0,
            denominator=denominator,
        )
    # Per-skill: zero tested clauses for this skill is the same instrument gap
    # at skill scope (engine raises no_instantiated_frozen_cases).
    if instantiated_count == 0:
        return CoverageFigure(
            label="instantiated",
            status="refused",
            reason=_REASON_NO_INSTANTIATED,
            numerator=0,
            denominator=denominator,
        )
    return CoverageFigure(
        label="instantiated",
        status="measured",
        reason=None,
        numerator=instantiated_count,
        denominator=denominator,
    )


def run_coverage(
    input_path: Path | str,
    *,
    evidence_path: Path | str | None = None,
) -> CoverageResult:
    """Compute dual coverage for clause JSONL, optionally joined to an evidence DB."""
    path = Path(input_path)
    census = run_census(path)
    clauses_by_slug = _skill_clauses_by_slug(path)

    evidence_posix: str | None = None
    inst_index: dict[tuple[str, int], bool] = {}
    corpus_frozen_total: int | None = None
    if evidence_path is not None:
        epath = Path(evidence_path)
        evidence_posix = epath.as_posix()
        inst_index, corpus_frozen_total = _load_instantiated_index(epath)

    evidence_supplied = evidence_path is not None
    mixed_generations = census.corpus_figures_status == "refused"

    per_skill_rows: list[SkillCoverageRow] = []
    corpus_instantiated_num = 0

    for skill_row in census.per_skill:
        slug = skill_row.slug
        constructible = _constructible_figure(skill_row)
        clauses = clauses_by_slug.get(slug, [])
        inst_count = 0
        if evidence_supplied:
            for clause in clauses:
                idx = _parse_clause_index(clause)
                if idx is None:
                    continue
                if inst_index.get((slug, idx), False):
                    inst_count += 1
            corpus_instantiated_num += inst_count
        instantiated = _instantiated_for_scope(
            denominator=skill_row.total_clauses,
            instantiated_count=inst_count,
            evidence_supplied=evidence_supplied,
            corpus_frozen_total=corpus_frozen_total,
        )
        per_skill_rows.append(
            SkillCoverageRow(
                slug=slug,
                constructible=constructible,
                instantiated=instantiated,
            )
        )

    if mixed_generations:
        corpus_constructible = CoverageFigure(
            label="constructible",
            status="refused",
            reason=census.corpus_figures_reason or _REASON_MIXED_GENERATIONS,
            numerator=0,
            denominator=census.total_clauses,
        )
        corpus_instantiated = CoverageFigure(
            label="instantiated",
            status="refused",
            reason=census.corpus_figures_reason or _REASON_MIXED_GENERATIONS,
            numerator=0,
            denominator=census.total_clauses,
        )
    else:
        corpus_constructible = _corpus_constructible(census)
        corpus_instantiated = _instantiated_for_scope(
            denominator=census.total_clauses,
            instantiated_count=corpus_instantiated_num if evidence_supplied else 0,
            evidence_supplied=evidence_supplied,
            corpus_frozen_total=corpus_frozen_total,
        )

    crosstab = _build_case_vacuity_crosstab(clauses_by_slug)

    return CoverageResult(
        input_path=path.as_posix(),
        evidence_path=evidence_posix,
        extractor_model=census.extractor_model,
        system_prompt_sha256=census.system_prompt_sha256,
        tool_schema_sha256=census.tool_schema_sha256,
        extractor_generation_status=census.extractor_generation_status,
        extractor_generation_reason=census.extractor_generation_reason,
        rows_total=census.rows_total,
        metadata_rows_skipped=census.metadata_rows_skipped,
        skills_covered=census.skills_covered,
        failed_extraction_slugs=census.failed_extraction_slugs,
        total_clauses=census.total_clauses,
        corpus_constructible=corpus_constructible,
        corpus_instantiated=corpus_instantiated,
        per_skill=tuple(per_skill_rows),
        missing_stage_note=_MISSING_STAGE_NOTE,
        case_vacuity_crosstab=crosstab,
    )


def receipt_json_bytes(result: CoverageResult) -> bytes:
    """Canonical JSON receipt bytes — sorted keys, stable separators, trailing newline."""
    payload = json.dumps(
        result.to_receipt(),
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
    )
    return (payload + "\n").encode("utf-8")


def write_receipt(result: CoverageResult, path: Path | str) -> None:
    """Write the canonical JSON receipt to ``path``."""
    Path(path).write_bytes(receipt_json_bytes(result))


def _format_figure(fig: CoverageFigure, *, indent: str = "    ") -> list[str]:
    lines = [
        f"{indent}{fig.label}_coverage:",
        f"{indent}  what: {_WHAT[fig.label]}",
        f"{indent}  status: {fig.status}",
    ]
    if fig.status == "measured":
        pct = _percent(fig.numerator, fig.denominator)
        lines.append(f"{indent}  measured: {fig.numerator}/{fig.denominator} ({pct}%)")
    else:
        lines.append(f"{indent}  reason: {fig.reason}")
        lines.append(f"{indent}  denominator_clauses: {fig.denominator} (no percentage emitted)")
    return lines


def format_human_report(result: CoverageResult) -> str:
    """Deterministic human-readable dual-coverage report."""
    xtab = result.case_vacuity_crosstab
    lines: list[str] = [
        "corpus coverage (constructible vs instantiated)",
        f"  input: {result.input_path}",
        f"  evidence: {result.evidence_path!s}",
        f"  extractor_model: {result.extractor_model!s}",
        f"  system_prompt_sha256: {result.system_prompt_sha256!s}",
        f"  tool_schema_sha256: {result.tool_schema_sha256!s}",
        (
            f"  extractor_generation: {result.extractor_generation_status}"
            + (
                f" ({result.extractor_generation_reason})"
                if result.extractor_generation_reason
                else ""
            )
        ),
        f"  rows_total: {result.rows_total}",
        f"  metadata_rows_skipped: {result.metadata_rows_skipped}",
        f"  skills_covered: {result.skills_covered}",
        (
            f"  failed_extractions: {len(result.failed_extraction_slugs)}"
            f" {list(result.failed_extraction_slugs)}"
        ),
        f"  total_clauses: {result.total_clauses}",
        "  corpus-wide:",
    ]
    lines.extend(_format_figure(result.corpus_constructible, indent="    "))
    lines.extend(_format_figure(result.corpus_instantiated, indent="    "))
    lines.append("  case_presence_x_vacuity_flag_none:")
    lines.append(f"    none_with_case: {xtab.none_with_case}")
    lines.append(f"    none_without_case: {xtab.none_without_case}")
    lines.append(f"    flagged_with_case: {xtab.flagged_with_case}")
    lines.append(f"    flagged_without_case: {xtab.flagged_without_case}")
    lines.append(f"  constructible_coverage_vs_vacuity_flag: {xtab.constructible_vs_vacuity_flag}")
    if xtab.constructible_vs_vacuity_flag == "independent":
        lines.append(
            "    note: constructible coverage is independent of vacuity_flag "
            "on this input (off-diagonal non-empty)"
        )
    else:
        lines.append(
            "    note: constructible coverage equals vacuity_flag==none "
            "fraction by construction on this input (off-diagonal empty)"
        )
    lines.append(
        f"  detector_false_positives: {len(xtab.detector_false_positives)}"
        " (flagged clauses that still carry a complete falsifying_case)"
    )
    for fp in xtab.detector_false_positives:
        idx = "None" if fp.clause_index is None else str(fp.clause_index)
        lines.append(
            f"    - slug={fp.slug} clause_index={idx} "
            f"vacuity_flag={fp.vacuity_flag} axis={fp.axis!r} "
            f"text={fp.clause_text!r}"
        )
    lines.append("  per_skill:")
    for row in result.per_skill:
        lines.append(f"    slug: {row.slug}")
        lines.extend(_format_figure(row.constructible, indent="      "))
        lines.extend(_format_figure(row.instantiated, indent="      "))
    lines.append("  missing_stage_note:")
    lines.append(f"    {result.missing_stage_note}")
    return "\n".join(lines) + "\n"


def emit_report(
    result: CoverageResult,
    *,
    stdout: TextIO,
    receipt_path: Path | str | None = None,
) -> None:
    """Write the human report to ``stdout`` and optionally a JSON receipt."""
    stdout.write(format_human_report(result))
    if receipt_path is not None:
        write_receipt(result, receipt_path)


# Public surface for the dual-coverage measurement.
__all__ = [
    "CaseVacuityCrosstab",
    "CoverageFigure",
    "CoverageResult",
    "DetectorFalsePositive",
    "SkillCoverageRow",
    "emit_report",
    "format_human_report",
    "receipt_json_bytes",
    "run_coverage",
    "write_receipt",
]
