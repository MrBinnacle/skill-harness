"""Deterministic census of an extracted-clause JSONL corpus (#118).

Pure arithmetic over clause records already on disk — no API calls, no model
judgment. Same input always produces the same output.

Reports how much of the corpus is mechanically measurable today (scoreable
axis, comparator specified, falsifying-case structural completeness) plus a
vacuity-flag queue-marker tally. Does not tune thresholds or reclassify
clauses to raise the measurable fraction.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, TextIO

from skill_harness.extractor.models import (
    ExtractorInstrument,
    compare_extractor_generations,
    instrument_from_mapping,
)
from skill_harness.extractor.vacuity_policy import (
    FlagEvidenceStatus,
    VacuityFlagCalibrationReceipt,
    assert_kind_precision_render_safe,
    assert_recall_not_claimed_measured,
    exclusion_label_for_flag,
    format_kind_precision_for_render,
    match_calibration_receipt,
)
from skill_harness.oracles.tier1.axis_registry import AxisScoreability, classify_axis

_COMPARATORS_SPECIFIED: Final[frozenset[str]] = frozenset({"increase", "decrease", "preserve"})
_FC_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "input_population_spec",
    "expected_directional_pair",
    "min_reproducibility",
)
_FC_UNMEASURABLE_REASON: Final[str] = (
    "clause records lack a falsifying_case object "
    "(boolean-only has_falsifying_case schema or key absent); "
    "structural completeness is unmeasurable for this input"
)
# #188: honest exclusion label is generation-scoped; this constant is the
# uncalibrated / generation-mismatch form used when no receipt matches.
# Calibrated corpora substitute the receipt-scoped label at render time.
_UNREVIEWED_SEMANTIC_VACUOUS_LABEL: Final[str] = exclusion_label_for_flag(
    flag_evidence_status="UNMEASURED_GENERATION_MISMATCH",
    calibration_receipt=None,
)
# #141: finer conditions under semantic_vacuous_pending_review.
_VACUITY_KIND_WEAK: Final[str] = "weak_directive"
_VACUITY_KIND_NOT_DIRECTIVE: Final[str] = "not_a_directive"
_WEAK_DIRECTIVE_LABEL: Final[str] = (
    "behavioural instruction too vague or metaphorical to state a direction on a measurable axis"
)
_NOT_A_DIRECTIVE_LABEL: Final[str] = (
    "clause boundary captured text that is not a behavioural directive"
)
_UNSPECIFIED_KIND_LABEL: Final[str] = "flagged without vacuity_kind (legacy extraction row)"


@dataclass(frozen=True)
class _SkillRow:
    slug: str
    ok: bool
    clauses: tuple[Mapping[str, Any], ...]
    error_type: str | None
    error: str | None
    instrument: ExtractorInstrument | None


_REASON_MIXED_GENERATIONS: Final[str] = (
    "mixed_extractor_generations: corpus rows come from more than one extractor "
    "instrument generation (model pin / system_prompt_sha256 / tool_schema_sha256); "
    "refusing to merge into one figure"
)

_REASON_GENERATION_UNKNOWN: Final[str] = (
    "extractor_generation_unknown: one or more skill rows lack the instrument "
    "triple (extractor_model, system_prompt_sha256, tool_schema_sha256); "
    "legacy rows are not assumed to match the current instrument"
)


@dataclass(frozen=True)
class SkillCensusRow:
    """Per-skill census slice (constructible / FC structural completeness)."""

    slug: str
    total_clauses: int
    falsifying_case_status: Literal["measured", "unmeasurable_for_this_input"]
    falsifying_case_reason: str | None
    falsifying_case_applicable_count: int
    falsifying_case_complete_count: int
    falsifying_case_incomplete_count: int
    constructible_count: int
    """Clauses with a structurally complete falsifying_case (any vacuity)."""


@dataclass(frozen=True)
class CensusResult:
    """Immutable census figures. Serialises to a stable JSON receipt."""

    extractor_model: str | None
    system_prompt_sha256: str | None
    tool_schema_sha256: str | None
    extractor_generation_status: Literal["known", "unknown", "mixed"]
    extractor_generation_reason: str | None
    input_path: str
    rows_total: int
    metadata_rows_skipped: int
    skills_covered: int
    failed_extraction_slugs: tuple[str, ...]
    known_clause_subtotal: int
    """Clauses across successfully-extracted rows ONLY.

    Named a subtotal, never a total: rows in ``failed_extraction_slugs``
    contributed zero clauses and an unknown number went unextracted, so a
    'total' here would report a partial denominator under a complete name.
    Per-skill rows keep ``total_clauses`` -- within one successful extraction
    the count genuinely is total.
    """
    scoreable_axis_count: int
    unscoreable_axis_count: int
    comparator_specified_count: int
    comparator_unspecified_count: int
    falsifying_case_status: Literal["measured", "unmeasurable_for_this_input", "refused"]
    falsifying_case_reason: str | None
    falsifying_case_applicable_count: int
    falsifying_case_complete_count: int
    falsifying_case_incomplete_count: int
    vacuity_none_count: int
    vacuity_semantic_pending_count: int
    vacuity_weak_directive_count: int
    vacuity_not_a_directive_count: int
    vacuity_kind_unspecified_count: int
    vacuity_other: tuple[tuple[str, int], ...]
    axis_distribution: tuple[tuple[str, int], ...]
    flag_evidence_status: FlagEvidenceStatus | Literal["mixed", "refused"] = (
        "UNMEASURED_GENERATION_MISMATCH"
    )
    flag_evidence_calibrated_count: int = 0
    flag_evidence_unmeasured_count: int = 0
    kind_evidence_advisory_count: int = 0
    kind_evidence_adjudicated_count: int = 0
    adjudicated_kind_counts: tuple[tuple[str, int], ...] = ()
    calibration_receipt_id: str | None = None
    per_skill: tuple[SkillCensusRow, ...] = ()
    # Corpus-wide tallies are refused when generations are mixed.
    corpus_figures_status: Literal["measured", "refused"] = "measured"
    corpus_figures_reason: str | None = None
    _calibration_receipt: VacuityFlagCalibrationReceipt | None = None

    def to_receipt(self) -> dict[str, Any]:
        """Build the JSON-serialisable receipt (sorted-key friendly)."""
        total = self.known_clause_subtotal
        failed_slugs = list(self.failed_extraction_slugs)
        receipt: dict[str, Any] = {
            "axis_distribution": [
                {
                    "axis": axis,
                    "count": count,
                    "percent_of_clauses": _percent(count, total),
                }
                for axis, count in self.axis_distribution
            ],
            "comparator_specified": {
                "count": self.comparator_specified_count,
                "percent_of_clauses": _percent(self.comparator_specified_count, total),
            },
            "comparator_unspecified": {
                "count": self.comparator_unspecified_count,
                "percent_of_clauses": _percent(self.comparator_unspecified_count, total),
            },
            "corpus_figures_status": self.corpus_figures_status,
            "extractor_generation": {
                "reason": self.extractor_generation_reason,
                "status": self.extractor_generation_status,
                "system_prompt_sha256": self.system_prompt_sha256,
                "tool_schema_sha256": self.tool_schema_sha256,
            },
            "extractor_model": self.extractor_model,
            "failed_extractions": {
                "count": len(failed_slugs),
                "slugs": failed_slugs,
            },
            "falsifying_case_structural_completeness": _fc_receipt_block(self),
            "input_path": self.input_path,
            "metadata_rows_skipped": self.metadata_rows_skipped,
            "per_skill": [_skill_receipt_row(row) for row in self.per_skill],
            "rows_total": self.rows_total,
            "scoreable_axis": {
                "count": self.scoreable_axis_count,
                "percent_of_clauses": _percent(self.scoreable_axis_count, total),
            },
            "skills_covered": self.skills_covered,
            "system_prompt_sha256": self.system_prompt_sha256,
            "tool_schema_sha256": self.tool_schema_sha256,
            "known_clause_subtotal": self.known_clause_subtotal,
            "unscoreable_axis": {
                "count": self.unscoreable_axis_count,
                "percent_of_clauses": _percent(self.unscoreable_axis_count, total),
            },
            "vacuity_flag_tally": {
                "none": self.vacuity_none_count,
                "other": [{"flag": flag, "count": count} for flag, count in self.vacuity_other],
                # Reviewed vs unreviewed stay separate buckets so a later
                # reviewed category cannot collapse into one undifferentiated total.
                "reviewed": {},
                "unreviewed": {
                    "semantic_vacuous_pending_review": {
                        "by_kind": {
                            "not_a_directive": {
                                "count": self.vacuity_not_a_directive_count,
                                "label": _NOT_A_DIRECTIVE_LABEL,
                                "kind_status": "ADVISORY",
                            },
                            "unspecified": {
                                "count": self.vacuity_kind_unspecified_count,
                                "label": _UNSPECIFIED_KIND_LABEL,
                                "kind_status": "ADVISORY",
                            },
                            "weak_directive": {
                                "count": self.vacuity_weak_directive_count,
                                "label": _WEAK_DIRECTIVE_LABEL,
                                "kind_status": "ADVISORY",
                            },
                        },
                        "count": self.vacuity_semantic_pending_count,
                        "label": self._exclusion_label(),
                        "flag_evidence_status": self.flag_evidence_status,
                    },
                },
            },
            "vacuity_evidence": {
                "flag_evidence_status": self.flag_evidence_status,
                "flag_evidence_calibrated_count": self.flag_evidence_calibrated_count,
                "flag_evidence_unmeasured_count": self.flag_evidence_unmeasured_count,
                "kind_evidence_advisory_count": self.kind_evidence_advisory_count,
                "kind_evidence_adjudicated_count": self.kind_evidence_adjudicated_count,
                "adjudicated_kind_counts": [
                    {"kind": k, "count": c} for k, c in self.adjudicated_kind_counts
                ],
                "calibration_receipt_id": self.calibration_receipt_id,
                "recall": "UNMEASURED",
                "kind_precision": self._kind_precision_receipt_block(),
            },
        }
        if self.corpus_figures_status == "refused":
            receipt["corpus_figures_reason"] = self.corpus_figures_reason
        # Renderer guards run on the serialised form so poison paths go RED.
        rendered = json.dumps(receipt, ensure_ascii=True, sort_keys=True)
        assert_kind_precision_render_safe(rendered, self._calibration_receipt)
        assert_recall_not_claimed_measured(rendered)
        return receipt

    def _exclusion_label(self) -> str:
        if (
            self.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
            and self._calibration_receipt is not None
        ):
            return exclusion_label_for_flag(
                flag_evidence_status="CALIBRATED_FROZEN_CAPTURE",
                calibration_receipt=self._calibration_receipt,
            )
        return _UNREVIEWED_SEMANTIC_VACUOUS_LABEL

    def _kind_precision_receipt_block(self) -> dict[str, Any] | None:
        r = self._calibration_receipt
        if r is None or self.flag_evidence_status != "CALIBRATED_FROZEN_CAPTURE":
            return None
        # Aggregate only beside class split — never a lone overall kind score.
        nad = (
            f"{r.kind_precision_not_a_directive_correct}/"
            f"{r.kind_precision_not_a_directive_n}"
        )
        wd = (
            f"{r.kind_precision_weak_directive_correct}/"
            f"{r.kind_precision_weak_directive_n}"
        )
        return {
            "aggregate": r.kind_precision_aggregate,
            "not_a_directive": nad,
            "weak_directive": wd,
            "status": "ADVISORY",
            "render": format_kind_precision_for_render(r),
        }


def _percent(count: int, total: int) -> float | None:
    if total == 0:
        return None
    # Fixed-decimal round-trip so the same ratio always serialises identically.
    return float(f"{(100.0 * count) / total:.6f}")


def _fc_receipt_block(result: CensusResult) -> dict[str, Any]:
    if result.falsifying_case_status == "unmeasurable_for_this_input":
        return {
            "reason": result.falsifying_case_reason,
            "status": "unmeasurable_for_this_input",
        }
    if result.falsifying_case_status == "refused":
        return {
            "reason": result.falsifying_case_reason,
            "status": "refused",
        }
    applicable = result.falsifying_case_applicable_count
    return {
        "applicable_clauses_vacuity_none": applicable,
        "percent_complete_of_applicable": _percent(
            result.falsifying_case_complete_count, applicable
        ),
        "status": "measured",
        "structurally_complete": result.falsifying_case_complete_count,
        "structurally_incomplete": result.falsifying_case_incomplete_count,
    }


def _skill_receipt_row(row: SkillCensusRow) -> dict[str, Any]:
    base: dict[str, Any] = {
        "constructible_count": row.constructible_count,
        "slug": row.slug,
        "total_clauses": row.total_clauses,
    }
    if row.falsifying_case_status == "unmeasurable_for_this_input":
        base["falsifying_case_structural_completeness"] = {
            "reason": row.falsifying_case_reason,
            "status": "unmeasurable_for_this_input",
        }
        return base
    applicable = row.falsifying_case_applicable_count
    base["falsifying_case_structural_completeness"] = {
        "applicable_clauses_vacuity_none": applicable,
        "percent_complete_of_applicable": _percent(row.falsifying_case_complete_count, applicable),
        "status": "measured",
        "structurally_complete": row.falsifying_case_complete_count,
        "structurally_incomplete": row.falsifying_case_incomplete_count,
    }
    base["constructible_coverage_percent_of_clauses"] = _percent(
        row.constructible_count, row.total_clauses
    )
    return base


def _is_metadata_row(row: Mapping[str, Any]) -> bool:
    if "record_type" in row:
        return True
    return "slug" not in row


def _parse_skill_row(row: Mapping[str, Any]) -> _SkillRow:
    slug = str(row["slug"])
    ok = bool(row.get("ok", True))
    raw_clauses = row.get("clauses")
    if not ok:
        clauses: tuple[Mapping[str, Any], ...] = ()
    elif isinstance(raw_clauses, list):
        clauses = tuple(c for c in raw_clauses if isinstance(c, Mapping))
    else:
        clauses = ()
    error_type = row.get("error_type")
    error = row.get("error")
    return _SkillRow(
        slug=slug,
        ok=ok,
        clauses=clauses,
        error_type=str(error_type) if error_type is not None else None,
        error=str(error) if error is not None else None,
        instrument=instrument_from_mapping(row) if ok else None,
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {line_no}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: line {line_no}: expected a JSON object")
        rows.append(obj)
    return rows


def _extract_extractor_model(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for row in rows:
        if row.get("record_type") == "header":
            model = row.get("extractor_model")
            if isinstance(model, str) and model:
                return model
    for row in rows:
        model = row.get("extractor_model")
        if isinstance(model, str) and model and not _is_metadata_row(row):
            return model
    return None


def _resolve_corpus_generation(
    skills: Sequence[_SkillRow],
) -> tuple[
    Literal["known", "unknown", "mixed"],
    str | None,
    ExtractorInstrument | None,
    Literal["measured", "refused"],
    str | None,
]:
    """Classify corpus instrument generation across ok skill rows.

    - all rows carry the same complete triple → known / measured
    - any row lacks the triple → unknown (legacy); still measured within the
      file but never assumed to match the current instrument
    - two or more distinct complete triples → mixed; refuse corpus merge
    - mix of known triple(s) and missing → mixed; refuse corpus merge
    """
    if not skills:
        return "unknown", _REASON_GENERATION_UNKNOWN, None, "measured", None

    instruments = [s.instrument for s in skills]
    known = [i for i in instruments if i is not None]
    unknown_count = len(instruments) - len(known)

    if unknown_count and not known:
        return "unknown", _REASON_GENERATION_UNKNOWN, None, "measured", None

    if unknown_count and known:
        return "mixed", _REASON_MIXED_GENERATIONS, None, "refused", _REASON_MIXED_GENERATIONS

    # All known: check pairwise identity.
    assert known
    first = known[0]
    for other in known[1:]:
        if compare_extractor_generations(first, other) != "same":
            return "mixed", _REASON_MIXED_GENERATIONS, None, "refused", _REASON_MIXED_GENERATIONS
    return "known", None, first, "measured", None


def falsifying_case_complete(clause: Mapping[str, Any]) -> bool:
    """True iff ``clause`` carries a structurally complete falsifying_case object.

    Required keys (all present, non-None, non-empty string):
    ``input_population_spec``, ``expected_directional_pair``, ``min_reproducibility``.
    A bare boolean or missing key is incomplete.
    """
    fc = clause.get("falsifying_case")
    if not isinstance(fc, Mapping):
        return False
    for key in _FC_REQUIRED_KEYS:
        if key not in fc:
            return False
        value = fc[key]
        if value is None:
            return False
        if isinstance(value, str) and value == "":
            return False
    return True


def _clauses_have_falsifying_case_key(clauses: Iterable[Mapping[str, Any]]) -> bool:
    return any("falsifying_case" in clause for clause in clauses)


def _skill_fc_row(skill: _SkillRow) -> SkillCensusRow:
    """Per-skill FC structural completeness + constructible count."""
    clauses = skill.clauses
    fc_schema_present = _clauses_have_falsifying_case_key(clauses)
    constructible = sum(1 for c in clauses if falsifying_case_complete(c))
    if not fc_schema_present:
        return SkillCensusRow(
            slug=skill.slug,
            total_clauses=len(clauses),
            falsifying_case_status="unmeasurable_for_this_input",
            falsifying_case_reason=_FC_UNMEASURABLE_REASON,
            falsifying_case_applicable_count=0,
            falsifying_case_complete_count=0,
            falsifying_case_incomplete_count=0,
            constructible_count=0,
        )
    applicable = 0
    complete = 0
    incomplete = 0
    for clause in clauses:
        if clause.get("vacuity_flag") == "none":
            applicable += 1
            if falsifying_case_complete(clause):
                complete += 1
            else:
                incomplete += 1
    return SkillCensusRow(
        slug=skill.slug,
        total_clauses=len(clauses),
        falsifying_case_status="measured",
        falsifying_case_reason=None,
        falsifying_case_applicable_count=applicable,
        falsifying_case_complete_count=complete,
        falsifying_case_incomplete_count=incomplete,
        constructible_count=constructible,
    )


def run_census(input_path: Path | str) -> CensusResult:
    """Compute the census for a clause-JSONL file at ``input_path``."""
    path = Path(input_path)
    rows = _load_jsonl(path)

    metadata_skipped = 0
    covered = 0
    failed_slugs: list[str] = []
    all_clauses: list[Mapping[str, Any]] = []
    ok_skills: list[_SkillRow] = []

    for row in rows:
        if _is_metadata_row(row):
            metadata_skipped += 1
            continue
        skill = _parse_skill_row(row)
        if not skill.ok:
            failed_slugs.append(skill.slug)
            continue
        covered += 1
        ok_skills.append(skill)
        all_clauses.extend(skill.clauses)

    failed_slugs_sorted = tuple(sorted(failed_slugs))
    gen_status, gen_reason, corpus_instrument, figures_status, figures_reason = (
        _resolve_corpus_generation(ok_skills)
    )
    extractor_model = (
        corpus_instrument.model_id
        if corpus_instrument is not None
        else _extract_extractor_model(rows)
    )
    system_prompt_sha256 = (
        corpus_instrument.system_prompt_sha256 if corpus_instrument is not None else None
    )
    tool_schema_sha256 = (
        corpus_instrument.tool_schema_sha256 if corpus_instrument is not None else None
    )

    scoreable = 0
    unscoreable = 0
    comp_specified = 0
    comp_unspecified = 0
    vacuity_none = 0
    vacuity_semantic = 0
    vacuity_weak = 0
    vacuity_not_directive = 0
    vacuity_kind_unspecified = 0
    vacuity_other_counts: dict[str, int] = {}
    axis_counts: dict[str, int] = {}
    # #188: evidence-status / adjudicated-kind tallies (adjudicated stays 0 until
    # real adjudication data is joined; kinds remain ADVISORY).
    kind_advisory_n = 0
    kind_adjudicated_n = 0
    adjudicated_kind_bucket: dict[str, int] = {}

    fc_schema_present = _clauses_have_falsifying_case_key(all_clauses)
    fc_applicable = 0
    fc_complete = 0
    fc_incomplete = 0

    for clause in all_clauses:
        axis = clause.get("axis")
        axis_str = axis if isinstance(axis, str) else ""
        axis_counts[axis_str] = axis_counts.get(axis_str, 0) + 1
        if classify_axis(axis_str) is AxisScoreability.TIER1_MECHANICAL:
            scoreable += 1
        else:
            unscoreable += 1

        comparator = clause.get("comparator")
        if comparator in _COMPARATORS_SPECIFIED:
            comp_specified += 1
        else:
            # comparator_unspecified, missing, or any other value
            comp_unspecified += 1

        vacuity = clause.get("vacuity_flag")
        if vacuity == "none":
            vacuity_none += 1
        elif vacuity == "semantic_vacuous_pending_review":
            vacuity_semantic += 1
            kind = clause.get("vacuity_kind")
            if kind == _VACUITY_KIND_WEAK:
                vacuity_weak += 1
            elif kind == _VACUITY_KIND_NOT_DIRECTIVE:
                vacuity_not_directive += 1
            else:
                vacuity_kind_unspecified += 1
            # Raw kind predictions are advisory; no adjudicated join in census.
            kind_advisory_n += 1
        else:
            flag_key = str(vacuity) if vacuity is not None else ""
            vacuity_other_counts[flag_key] = vacuity_other_counts.get(flag_key, 0) + 1

        if vacuity == "none" and fc_schema_present:
            fc_applicable += 1
            if falsifying_case_complete(clause):
                fc_complete += 1
            else:
                fc_incomplete += 1

    if figures_status == "refused":
        # Mixed generations: do not emit a blended corpus figure. Counts stay
        # at zero in the receipt so a reader cannot treat them as a single
        # instrument's tallies; per_skill rows remain the unit of analysis.
        fc_status: Literal["measured", "unmeasurable_for_this_input", "refused"] = "refused"
        fc_reason: str | None = figures_reason
        fc_applicable = 0
        fc_complete = 0
        fc_incomplete = 0
        scoreable = 0
        unscoreable = 0
        comp_specified = 0
        comp_unspecified = 0
        vacuity_none = 0
        vacuity_semantic = 0
        vacuity_weak = 0
        vacuity_not_directive = 0
        vacuity_kind_unspecified = 0
        vacuity_other_counts = {}
        axis_counts = {}
        kind_advisory_n = 0
        kind_adjudicated_n = 0
        adjudicated_kind_bucket = {}
        known_clause_subtotal = len(all_clauses)
    elif fc_schema_present:
        fc_status = "measured"
        fc_reason = None
        known_clause_subtotal = len(all_clauses)
    else:
        fc_status = "unmeasurable_for_this_input"
        fc_reason = _FC_UNMEASURABLE_REASON
        fc_applicable = 0
        fc_complete = 0
        fc_incomplete = 0
        known_clause_subtotal = len(all_clauses)

    axis_distribution = tuple(sorted(axis_counts.items(), key=lambda item: item[0]))
    vacuity_other = tuple(sorted(vacuity_other_counts.items(), key=lambda item: item[0]))
    # Per-skill figures remain available even when corpus merge is refused —
    # each skill row is a single instrument (or unknown), not a blend.
    per_skill = tuple(sorted((_skill_fc_row(s) for s in ok_skills), key=lambda r: r.slug))

    calibration = (
        match_calibration_receipt(corpus_instrument)
        if figures_status == "measured" and corpus_instrument is not None
        else None
    )
    if figures_status == "refused":
        flag_ev_status: FlagEvidenceStatus | Literal["mixed", "refused"] = "refused"
        flag_cal_n = 0
        flag_unm_n = 0
    elif calibration is not None:
        flag_ev_status = "CALIBRATED_FROZEN_CAPTURE"
        flag_cal_n = known_clause_subtotal
        flag_unm_n = 0
    else:
        flag_ev_status = "UNMEASURED_GENERATION_MISMATCH"
        flag_cal_n = 0
        flag_unm_n = known_clause_subtotal

    adjudicated_kinds = tuple(
        sorted(adjudicated_kind_bucket.items(), key=lambda item: item[0])
    )

    return CensusResult(
        extractor_model=extractor_model,
        system_prompt_sha256=system_prompt_sha256,
        tool_schema_sha256=tool_schema_sha256,
        extractor_generation_status=gen_status,
        extractor_generation_reason=gen_reason,
        input_path=path.as_posix(),
        rows_total=len(rows),
        metadata_rows_skipped=metadata_skipped,
        skills_covered=covered,
        failed_extraction_slugs=failed_slugs_sorted,
        known_clause_subtotal=known_clause_subtotal,
        scoreable_axis_count=scoreable,
        unscoreable_axis_count=unscoreable,
        comparator_specified_count=comp_specified,
        comparator_unspecified_count=comp_unspecified,
        falsifying_case_status=fc_status,
        falsifying_case_reason=fc_reason,
        falsifying_case_applicable_count=fc_applicable,
        falsifying_case_complete_count=fc_complete,
        falsifying_case_incomplete_count=fc_incomplete,
        vacuity_none_count=vacuity_none,
        vacuity_semantic_pending_count=vacuity_semantic,
        vacuity_weak_directive_count=vacuity_weak,
        vacuity_not_a_directive_count=vacuity_not_directive,
        vacuity_kind_unspecified_count=vacuity_kind_unspecified,
        vacuity_other=vacuity_other,
        axis_distribution=axis_distribution,
        flag_evidence_status=flag_ev_status,
        flag_evidence_calibrated_count=flag_cal_n,
        flag_evidence_unmeasured_count=flag_unm_n,
        kind_evidence_advisory_count=kind_advisory_n,
        kind_evidence_adjudicated_count=kind_adjudicated_n,
        adjudicated_kind_counts=adjudicated_kinds,
        calibration_receipt_id=(
            calibration.receipt_id if calibration is not None else None
        ),
        per_skill=per_skill,
        corpus_figures_status=figures_status,
        corpus_figures_reason=figures_reason,
        _calibration_receipt=calibration,
    )


def receipt_json_bytes(result: CensusResult) -> bytes:
    """Canonical JSON receipt bytes — sorted keys, stable separators, trailing newline."""
    payload = json.dumps(
        result.to_receipt(),
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
    )
    return (payload + "\n").encode("utf-8")


def format_human_report(result: CensusResult) -> str:
    """Deterministic human-readable census report."""
    total = result.known_clause_subtotal
    lines: list[str] = [
        "corpus census",
        f"  input: {result.input_path}",
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
        f"  corpus_figures_status: {result.corpus_figures_status}",
        f"  rows_total: {result.rows_total}",
        f"  metadata_rows_skipped: {result.metadata_rows_skipped}",
        f"  skills_covered: {result.skills_covered}",
        (
            f"  failed_extractions: {len(result.failed_extraction_slugs)}"
            f" {list(result.failed_extraction_slugs)}"
        ),
        f"  known_clause_subtotal: {total}",
    ]
    if result.corpus_figures_status == "refused":
        lines.append(f"  corpus_figures_reason: {result.corpus_figures_reason}")
        lines.append(
            "  note: corpus-wide tallies refused; see per_skill rows "
            "(not merged across extractor generations)"
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            (
                f"  scoreable_axis: {result.scoreable_axis_count}"
                f" ({_percent(result.scoreable_axis_count, total)}%)"
            ),
            (
                f"  unscoreable_axis: {result.unscoreable_axis_count}"
                f" ({_percent(result.unscoreable_axis_count, total)}%)"
            ),
            (
                f"  comparator_unspecified: {result.comparator_unspecified_count}"
                f" ({_percent(result.comparator_unspecified_count, total)}%)"
            ),
            (
                f"  comparator_specified: {result.comparator_specified_count}"
                f" ({_percent(result.comparator_specified_count, total)}%)"
            ),
        ]
    )
    if result.falsifying_case_status == "unmeasurable_for_this_input":
        lines.append("  falsifying_case_structural_completeness: unmeasurable_for_this_input")
        lines.append(f"    reason: {result.falsifying_case_reason}")
    elif result.falsifying_case_status == "refused":
        lines.append("  falsifying_case_structural_completeness: refused")
        lines.append(f"    reason: {result.falsifying_case_reason}")
    else:
        lines.append("  falsifying_case_structural_completeness: measured")
        lines.append(
            f"    applicable (vacuity_flag=none): {result.falsifying_case_applicable_count}"
        )
        complete_pct = _percent(
            result.falsifying_case_complete_count,
            result.falsifying_case_applicable_count,
        )
        incomplete_pct = _percent(
            result.falsifying_case_incomplete_count,
            result.falsifying_case_applicable_count,
        )
        lines.append(
            f"    structurally_complete: {result.falsifying_case_complete_count} ({complete_pct}%)"
        )
        lines.append(
            f"    structurally_incomplete: {result.falsifying_case_incomplete_count}"
            f" ({incomplete_pct}%)"
        )
    excl = result._exclusion_label()
    lines.append("  vacuity_flag_tally (queue marker; flag-based exclusion pending review):")
    lines.append(f"    none: {result.vacuity_none_count}")
    lines.append(
        f"    semantic_vacuous_pending_review: {result.vacuity_semantic_pending_count}"
        f" [{result.flag_evidence_status}] ({excl})"
    )
    lines.append(
        f"      weak_directive: {result.vacuity_weak_directive_count}"
        f" (model prediction, ADVISORY; {_WEAK_DIRECTIVE_LABEL})"
    )
    lines.append(
        f"      not_a_directive: {result.vacuity_not_a_directive_count}"
        f" (model prediction, ADVISORY; {_NOT_A_DIRECTIVE_LABEL})"
    )
    if result.vacuity_kind_unspecified_count:
        lines.append(
            f"      unspecified_kind: {result.vacuity_kind_unspecified_count}"
            f" ({_UNSPECIFIED_KIND_LABEL})"
        )
    lines.append(
        f"    kind_evidence: advisory={result.kind_evidence_advisory_count}"
        f" adjudicated={result.kind_evidence_adjudicated_count}"
    )
    if result.adjudicated_kind_counts:
        for kind, count in result.adjudicated_kind_counts:
            lines.append(f"      adjudicated_{kind}: {count}")
    else:
        lines.append("      adjudicated_kind: (none)")
    lines.append("    reviewed: (none)")
    lines.append("    recall: UNMEASURED")
    if (
        result._calibration_receipt is not None
        and result.flag_evidence_status == "CALIBRATED_FROZEN_CAPTURE"
    ):
        kp = format_kind_precision_for_render(result._calibration_receipt)
        lines.append(f"    {kp}")
    for flag, count in result.vacuity_other:
        lines.append(f"    {flag!r}: {count}")
    lines.append("  axis_distribution:")
    for axis, count in result.axis_distribution:
        lines.append(f"    {axis!r}: {count} ({_percent(count, total)}%)")
    report = "\n".join(lines) + "\n"
    assert_kind_precision_render_safe(report, result._calibration_receipt)
    assert_recall_not_claimed_measured(report)
    return report


def write_receipt(result: CensusResult, path: Path | str) -> None:
    """Write the canonical JSON receipt to ``path``."""
    Path(path).write_bytes(receipt_json_bytes(result))


def emit_report(
    result: CensusResult,
    *,
    stdout: TextIO,
    receipt_path: Path | str | None = None,
) -> None:
    """Write the human report to ``stdout`` and optionally a JSON receipt."""
    stdout.write(format_human_report(result))
    if receipt_path is not None:
        write_receipt(result, receipt_path)
