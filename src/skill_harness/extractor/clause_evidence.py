"""Clause evidence from extraction JSONL for ``skill audit --extraction`` (#157).

Zero-power join of an offline audit's ``source_sha256`` against a full
``ExtractionResult`` JSONL produced by ``skill init --out``. No API key, no
evidence DB -- the JSONL is the only carrier of ``vacuity_kind`` /
``vacuity_reason`` (operator ruling on issue 142: no migration).

Named refusal reasons (extractor-layer vocabulary; deliberately NOT members of
``aggregation.status.UnmeasuredSubReason`` -- that enum is the aggregation-layer
verdict vocabulary and unifying vocabularies is separately-tracked ask-first
work). Pattern matches ``corpus_coverage.py`` status + named-reason:

- ``no_extraction`` -- ``--extraction`` flag absent entirely.
- ``no_matching_extraction`` -- JSONL has zero rows whose ``source_sha256``
  equals the audited skill's sha (skill edited since extraction, or wrong file).
- ``ambiguous_duplicate_rows`` -- more than one matching row. Extraction output
  is not stable across runs (#152); refusing to choose one.
- ``legacy_extraction_missing_instrument_identity`` -- matching row lacks the
  instrument triple (``instrument_from_mapping`` returns None); predates the
  generation stamp.
- ``unreadable_extraction_file`` -- empty or fully-unparseable JSONL (0 valid
  rows after scan).

Also: unparseable line(s) encountered while scanning are counted; when any
exist a warning line naming the count is appended beside the section (happy
path or refusal other than unreadable).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from skill_harness.extractor.corpus_census import (
    _UNREVIEWED_SEMANTIC_VACUOUS_LABEL,
    falsifying_case_complete,
)
from skill_harness.extractor.models import (
    ExtractionResult,
    ExtractorInstrument,
    instrument_from_mapping,
)
from skill_harness.oracles.tier1.axis_registry import AxisScoreability, classify_axis

# Re-export the issue-123 label so render sites import one symbol, not a fork.
UNREVIEWED_SEMANTIC_VACUOUS_LABEL: Final[str] = _UNREVIEWED_SEMANTIC_VACUOUS_LABEL

SECTION_TITLE: Final[str] = "Clause evidence (zero-power) -- from extraction output"

REASON_NO_EXTRACTION: Final[str] = (
    "no_extraction: clause evidence requires an extraction output; "
    "produce one with skill init --out <file>"
)
REASON_NO_MATCHING: Final[str] = (
    "no_matching_extraction: source sha {sha16}... has no row in {path}; "
    "if the skill was edited since extraction, re-run skill init --out"
)
REASON_AMBIGUOUS: Final[str] = (
    "ambiguous_duplicate_rows: {n} rows match this sha; "
    "extraction output is not stable across runs, refusing to choose"
)
REASON_LEGACY: Final[str] = (
    "legacy_extraction_missing_instrument_identity: row predates the generation stamp"
)
REASON_UNREADABLE: Final[str] = "unreadable_extraction_file: 0 valid rows"

INSTANTIATED_COVERAGE_REFUSAL: Final[str] = (
    "Instantiated coverage: REFUSED (requires the evidence database; "
    "audit does not open one -- see skill clauses / the coverage CLI)"
)

SAME_SHA_APPEND_REFUSAL: Final[str] = (
    "refusing to append: {path} already has a row for source sha {sha16}...; "
    "extraction output is not stable across runs, so a second row would make "
    "the file ambiguous. Use a new file or remove the old row."
)


class SameShaExtractionRowError(Exception):
    """Raised when ``append_extraction_result`` would create a duplicate sha row."""


@dataclass(frozen=True)
class ClauseEvidenceRow:
    """One clause row for the audit table."""

    clause_index: int
    axis: str
    scoreable: bool
    vacuity_flag: str
    vacuity_kind: str | None
    vacuity_reason: str | None
    constructible_fc: bool


@dataclass(frozen=True)
class ClauseEvidenceSummary:
    clause_count: int
    flagged_count: int
    flagged_by_kind: tuple[tuple[str, int], ...]
    scoreable_axis_count: int
    constructible_count: int


@dataclass(frozen=True)
class ClauseEvidenceMeasured:
    instrument: ExtractorInstrument
    rows: tuple[ClauseEvidenceRow, ...]
    summary: ClauseEvidenceSummary


@dataclass(frozen=True)
class ClauseEvidenceOutcome:
    """Result of joining audit source_sha256 against an extraction JSONL.

    ``kind`` is ``measured`` or a named refusal reason key (see module docstring).
    """

    kind: Literal[
        "measured",
        "no_extraction",
        "no_matching_extraction",
        "ambiguous_duplicate_rows",
        "legacy_extraction_missing_instrument_identity",
        "unreadable_extraction_file",
    ]
    refusal_detail: str | None
    measured: ClauseEvidenceMeasured | None
    unparseable_line_count: int
    match_count: int = 0


def append_extraction_result(path: Path | str, result: ExtractionResult) -> None:
    """Append one ``ExtractionResult`` JSON line to ``path``.

    Refuses with ``SameShaExtractionRowError`` when a row for the same
    ``source_sha256`` is already present. Writes the full line + newline in one
    call and flushes (atomic w.r.t. partial lines).
    """
    target = Path(path)
    sha = result.source_sha256
    if target.exists():
        for row in _iter_valid_rows(target):
            existing = row.get("source_sha256")
            if isinstance(existing, str) and existing == sha:
                raise SameShaExtractionRowError(
                    SAME_SHA_APPEND_REFUSAL.format(path=str(target), sha16=sha[:16])
                )
    line = result.model_dump_json() + "\n"
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()


def no_extraction_outcome() -> ClauseEvidenceOutcome:
    """Outcome when ``--extraction`` is absent."""
    return ClauseEvidenceOutcome(
        kind="no_extraction",
        refusal_detail=REASON_NO_EXTRACTION,
        measured=None,
        unparseable_line_count=0,
    )


def load_clause_evidence(
    extraction_path: Path | str,
    source_sha256: str,
) -> ClauseEvidenceOutcome:
    """Select and interpret extraction JSONL rows for one audited skill sha."""
    path = Path(extraction_path)
    valid_rows: list[dict[str, Any]] = []
    unparseable = 0
    if path.exists():
        valid_rows, unparseable = _scan_jsonl(path)
    if not valid_rows:
        return ClauseEvidenceOutcome(
            kind="unreadable_extraction_file",
            refusal_detail=REASON_UNREADABLE,
            measured=None,
            unparseable_line_count=unparseable,
        )

    matches = [
        row
        for row in valid_rows
        if isinstance(row.get("source_sha256"), str) and row["source_sha256"] == source_sha256
    ]
    if len(matches) == 0:
        return ClauseEvidenceOutcome(
            kind="no_matching_extraction",
            refusal_detail=REASON_NO_MATCHING.format(sha16=source_sha256[:16], path=str(path)),
            measured=None,
            unparseable_line_count=unparseable,
            match_count=0,
        )
    if len(matches) > 1:
        return ClauseEvidenceOutcome(
            kind="ambiguous_duplicate_rows",
            refusal_detail=REASON_AMBIGUOUS.format(n=len(matches)),
            measured=None,
            unparseable_line_count=unparseable,
            match_count=len(matches),
        )

    row = matches[0]
    instrument = instrument_from_mapping(row)
    if instrument is None:
        return ClauseEvidenceOutcome(
            kind="legacy_extraction_missing_instrument_identity",
            refusal_detail=REASON_LEGACY,
            measured=None,
            unparseable_line_count=unparseable,
            match_count=1,
        )

    measured = _measure_row(row, instrument)
    return ClauseEvidenceOutcome(
        kind="measured",
        refusal_detail=None,
        measured=measured,
        unparseable_line_count=unparseable,
        match_count=1,
    )


def format_refusal_line(outcome: ClauseEvidenceOutcome) -> str:
    """Single ``Clause evidence: UNMEASURED (...)`` line for a refusal outcome."""
    assert outcome.refusal_detail is not None
    return f"Clause evidence: UNMEASURED ({outcome.refusal_detail})"


def format_instrument_line(instrument: ExtractorInstrument) -> str:
    return (
        f"extractor {instrument.model_id} / "
        f"prompt {instrument.system_prompt_sha256[:12]} / "
        f"schema {instrument.tool_schema_sha256[:12]}"
    )


def format_summary_lines(summary: ClauseEvidenceSummary) -> list[str]:
    """ASCII summary block lines (no Rich markup)."""
    kind_parts = [f"{kind}={count}" for kind, count in summary.flagged_by_kind]
    kind_bit = ", ".join(kind_parts) if kind_parts else "none"
    return [
        f"clauses: {summary.clause_count}",
        (f"flagged: {summary.flagged_count} ({kind_bit}) ({UNREVIEWED_SEMANTIC_VACUOUS_LABEL})"),
        (f"scoreable-axis: {summary.scoreable_axis_count} (as of current scorer registry)"),
        f"Constructible coverage: {summary.constructible_count}/{summary.clause_count}",
        INSTANTIATED_COVERAGE_REFUSAL,
    ]


def format_unparseable_warning(count: int) -> str:
    return f"warning: {count} unparseable line(s) in extraction file (skipped)"


def _scan_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    valid: list[dict[str, Any]] = []
    unparseable = 0
    text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            unparseable += 1
            continue
        if not isinstance(obj, dict):
            unparseable += 1
            continue
        valid.append(obj)
    return valid, unparseable


def _iter_valid_rows(path: Path) -> Sequence[Mapping[str, Any]]:
    rows, _ = _scan_jsonl(path)
    return rows


def _measure_row(
    row: Mapping[str, Any],
    instrument: ExtractorInstrument,
) -> ClauseEvidenceMeasured:
    raw_clauses = row.get("clauses")
    clauses: list[Mapping[str, Any]] = []
    if isinstance(raw_clauses, list):
        for item in raw_clauses:
            if isinstance(item, Mapping):
                clauses.append(item)

    evidence_rows: list[ClauseEvidenceRow] = []
    flagged = 0
    kind_counts: dict[str, int] = {}
    scoreable_n = 0
    constructible_n = 0

    for clause in clauses:
        axis = clause.get("axis")
        axis_s = axis if isinstance(axis, str) else ""
        scoreable = classify_axis(axis_s) is AxisScoreability.TIER1_MECHANICAL
        if scoreable:
            scoreable_n += 1

        flag = clause.get("vacuity_flag")
        flag_s = flag if isinstance(flag, str) else "none"
        kind_raw = clause.get("vacuity_kind")
        kind_s = kind_raw if isinstance(kind_raw, str) else None
        reason_raw = clause.get("vacuity_reason")
        reason_s = reason_raw if isinstance(reason_raw, str) else None

        if flag_s != "none":
            flagged += 1
            key = kind_s if kind_s is not None else "unspecified"
            kind_counts[key] = kind_counts.get(key, 0) + 1

        idx_raw = clause.get("clause_index")
        idx = idx_raw if isinstance(idx_raw, int) else -1
        constructible = falsifying_case_complete(clause)
        if constructible:
            constructible_n += 1

        evidence_rows.append(
            ClauseEvidenceRow(
                clause_index=idx,
                axis=axis_s,
                scoreable=scoreable,
                vacuity_flag=flag_s,
                vacuity_kind=kind_s,
                vacuity_reason=reason_s,
                constructible_fc=constructible,
            )
        )

    flagged_by_kind = tuple(sorted(kind_counts.items(), key=lambda kv: kv[0]))
    summary = ClauseEvidenceSummary(
        clause_count=len(evidence_rows),
        flagged_count=flagged,
        flagged_by_kind=flagged_by_kind,
        scoreable_axis_count=scoreable_n,
        constructible_count=constructible_n,
    )
    return ClauseEvidenceMeasured(
        instrument=instrument,
        rows=tuple(evidence_rows),
        summary=summary,
    )
