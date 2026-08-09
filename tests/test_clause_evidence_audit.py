"""Tests for skill init --out and skill audit --extraction (#157)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from skill_harness.cli.main import _SKILL_CLAUSES_LEGEND, cli
from skill_harness.extractor.clause_evidence import (
    INSTANTIATED_COVERAGE_REFUSAL,
    UNREVIEWED_SEMANTIC_VACUOUS_LABEL,
    append_extraction_result,
    load_clause_evidence,
    no_extraction_outcome,
)
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)
from skill_harness.preflight import audit_skill_artifact

GOOD_SKILL = """---
name: processing-pdfs
description: Extracts text and tables from PDF files. Use when working with PDFs.
---

# PDF Processing

Use pdfplumber for text extraction from `scripts/helper.py`.
"""


def _write_skill(tmp_path: Path, content: str = GOOD_SKILL) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    return p


def _sha_for_skill(path: Path) -> str:
    return audit_skill_artifact(path).source_sha256


def _make_result(
    *,
    source_sha256: str,
    name: str = "processing-pdfs",
    with_instrument: bool = True,
    n_clauses: int | None = None,
    clauses: list[ExtractedClause] | None = None,
) -> ExtractionResult:
    fc = FalsifyingCaseSchema(
        input_population_spec="PDF extraction prompts",
        expected_directional_pair="A cites source; B does not",
        min_reproducibility=0.8,
    )
    if clauses is None:
        n = 2 if n_clauses is None else n_clauses
        clauses = [
            ExtractedClause(
                clause_index=0,
                clause_text="Be concise when summarizing tables.",
                axis="verbosity",
                comparator="decrease",
                oracle_tier=1,
                vacuity_flag="none",
                falsifying_case=fc,
            ),
            ExtractedClause(
                clause_index=1,
                clause_text="Prefer elegance in layout.",
                axis="elegance",
                comparator="increase",
                oracle_tier=2,
                vacuity_flag="semantic_vacuous_pending_review",
                vacuity_kind="weak_directive",
                vacuity_reason="elegance is not a measurable axis",
                falsifying_case=None,
            ),
        ]
        if n == 0:
            clauses = []
        elif n == 1:
            clauses = clauses[:1]
        elif n > 2:
            extra = [
                ExtractedClause(
                    clause_index=i,
                    clause_text=f"Clause {i}.",
                    axis="specificity",
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case=None,
                )
                for i in range(2, n)
            ]
            clauses = clauses + extra
    return ExtractionResult(
        skill_id=source_sha256,
        name=name,
        source_path="/tmp/SKILL.md",
        source_sha256=source_sha256,
        clauses=clauses,
        raw_frontmatter={"name": name},
        extractor_model="claude-opus-5" if with_instrument else "x",
        system_prompt_sha256=("b" * 64) if with_instrument else ("0" * 64),
        tool_schema_sha256=("c" * 64) if with_instrument else ("1" * 64),
    )


def _clause_evidence_section(out: str) -> str:
    markers = (
        "Clause evidence (zero-power)",
        "Clause evidence: UNMEASURED",
    )
    idxs = [out.find(m) for m in markers if out.find(m) >= 0]
    assert idxs, f"no clause evidence section in:\n{out}"
    return out[min(idxs) :]


# ---------------------------------------------------------------------------
# AC1: skill init --out
# ---------------------------------------------------------------------------


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_out_writes_round_trippable_jsonl(
    mock_extract: Any, tmp_path: Path
) -> None:
    skill = _write_skill(tmp_path)
    sha = "a" * 64
    mock_extract.return_value = _make_result(source_sha256=sha)
    out = tmp_path / "extraction.jsonl"

    result = CliRunner().invoke(
        cli, ["skill", "init", str(skill), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    loaded = ExtractionResult.model_validate_json(lines[0])
    assert loaded.source_sha256 == sha
    assert len(loaded.clauses) == 2


@patch("skill_harness.cli.main.StorageContext")
@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_out_works_with_execute(
    mock_extract: Any, mock_ctx_cls: Any, tmp_path: Path
) -> None:
    skill = _write_skill(tmp_path)
    sha = "d" * 64
    mock_extract.return_value = _make_result(source_sha256=sha)
    mock_ctx = mock_ctx_cls.return_value.__enter__.return_value
    mock_ctx.evidence_conn = object()
    out = tmp_path / "with_exec.jsonl"

    result = CliRunner().invoke(
        cli, ["skill", "init", "--execute", str(skill), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    loaded = ExtractionResult.model_validate_json(out.read_text(encoding="utf-8").strip())
    assert loaded.source_sha256 == sha


@patch("skill_harness.cli.main.extract_skill")
def test_skill_init_out_same_sha_refuses_exit_1(
    mock_extract: Any, tmp_path: Path
) -> None:
    skill = _write_skill(tmp_path)
    sha = "e" * 64
    mock_extract.return_value = _make_result(source_sha256=sha)
    out = tmp_path / "dup.jsonl"
    append_extraction_result(out, _make_result(source_sha256=sha))

    result = CliRunner().invoke(
        cli, ["skill", "init", str(skill), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "refusing to append" in result.output
    assert sha[:16] in result.output
    assert "not stable across runs" in result.output
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1


# ---------------------------------------------------------------------------
# AC2: audit without --extraction
# ---------------------------------------------------------------------------


def test_audit_without_extraction_adds_no_extraction_line(tmp_path: Path) -> None:
    path = _write_skill(tmp_path)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "Clause evidence: UNMEASURED (no_extraction:" in section
    assert "skill init --out" in section
    assert section.count("Clause evidence:") == 1


# ---------------------------------------------------------------------------
# AC3 / AC6: happy path
# ---------------------------------------------------------------------------


def test_audit_extraction_happy_path(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "ext.jsonl"
    append_extraction_result(out, _make_result(source_sha256=sha))

    result = CliRunner().invoke(
        cli,
        ["skill", "audit", str(skill), "--extraction", str(out)],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "Clause evidence (zero-power) -- from extraction output" in section
    assert "extractor claude-opus-5" in section
    assert "prompt " + ("b" * 12) in section
    assert "schema " + ("c" * 12) in section
    assert "verbosity" in section
    assert "weak_directive (advisory)" in section
    assert UNREVIEWED_SEMANTIC_VACUOUS_LABEL in section
    assert "as of current scorer registry" in section.lower()
    assert "Constructible coverage:" in section
    assert INSTANTIATED_COVERAGE_REFUSAL in section
    # Separate lines: constructible and instantiated must not share a line.
    lines = section.splitlines()
    c_lines = [ln for ln in lines if "Constructible coverage:" in ln]
    i_lines = [ln for ln in lines if "Instantiated coverage:" in ln]
    assert len(c_lines) == 1
    assert len(i_lines) == 1
    assert c_lines[0] != i_lines[0]
    assert "Constructible coverage:" not in i_lines[0]
    assert "Instantiated coverage:" not in c_lines[0]


# ---------------------------------------------------------------------------
# AC4: each refusal state
# ---------------------------------------------------------------------------


def test_audit_extraction_no_match(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    out = tmp_path / "ext.jsonl"
    append_extraction_result(out, _make_result(source_sha256="f" * 64))
    sha = _sha_for_skill(skill)

    result = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "no_matching_extraction" in section
    assert sha[:16] in section
    assert "UNMEASURED" in section
    assert not any(
        tok == "0" and "coverage" in ln.lower()
        for ln in section.splitlines()
        for tok in ln.split()
    ) or "no_matching" in section  # refusal, not bare zero coverage


def test_audit_extraction_duplicates(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "dup.jsonl"
    # Bypass append guard to simulate an ambiguous file.
    row = _make_result(source_sha256=sha).model_dump_json()
    out.write_text(row + "\n" + row + "\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "ambiguous_duplicate_rows" in section
    assert "2 rows" in section
    assert "refusing to choose" in section


def test_audit_extraction_legacy_missing_instrument(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "legacy.jsonl"
    # Legacy row: drop instrument fields after dump.
    data = json.loads(_make_result(source_sha256=sha).model_dump_json())
    del data["extractor_model"]
    del data["system_prompt_sha256"]
    del data["tool_schema_sha256"]
    out.write_text(json.dumps(data) + "\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "legacy_extraction_missing_instrument_identity" in section
    assert "UNMEASURED" in section


def test_audit_extraction_unreadable_empty_file(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    out = tmp_path / "empty.jsonl"
    out.write_text("", encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "unreadable_extraction_file" in section
    assert "0 valid rows" in section


def test_audit_extraction_unreadable_all_garbage(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    out = tmp_path / "garbage.jsonl"
    out.write_text("not-json\n{bad\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "unreadable_extraction_file" in section


def test_audit_extraction_flag_absent_is_no_extraction(tmp_path: Path) -> None:
    """AC4 flag-absent case: same as AC2; never blank, never bare zero."""
    path = _write_skill(tmp_path)
    result = CliRunner().invoke(cli, ["skill", "audit", str(path)])
    assert result.exit_code == 0, result.output
    assert "Clause evidence: UNMEASURED (no_extraction:" in result.output
    # Must not end the audit with a bare "0" as the evidence figure.
    section = _clause_evidence_section(result.output).strip()
    assert section != "0"
    assert "Clause evidence:" in section


def test_audit_extraction_unparseable_lines_warn(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "mixed.jsonl"
    good = _make_result(source_sha256=sha).model_dump_json()
    out.write_text("NOT JSON\n" + good + "\n{also bad\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["skill", "audit", str(skill), "--extraction", str(out)],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    assert "extractor claude-opus-5" in section
    assert "unparseable line" in section.lower()
    assert "2" in section


# ---------------------------------------------------------------------------
# AC5: audit opens no SQLite
# ---------------------------------------------------------------------------


def test_audit_never_opens_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "ext.jsonl"
    append_extraction_result(out, _make_result(source_sha256=sha))

    def _boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("audit must not open sqlite3")

    monkeypatch.setattr(sqlite3, "connect", _boom)

    r1 = CliRunner().invoke(cli, ["skill", "audit", str(skill)])
    assert r1.exit_code == 0, r1.output
    assert "no_extraction" in r1.output

    r2 = CliRunner().invoke(
        cli, ["skill", "audit", str(skill), "--extraction", str(out)]
    )
    assert r2.exit_code == 0, r2.output
    assert "Clause evidence (zero-power)" in r2.output

    assert not (tmp_path / "evidence.db").exists()
    assert list(tmp_path.glob("*.db")) == []


# ---------------------------------------------------------------------------
# AC7: ASCII-only new render path
# ---------------------------------------------------------------------------


def test_clause_evidence_section_is_ascii_only(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    sha = _sha_for_skill(skill)
    out = tmp_path / "ext.jsonl"
    # Include non-ascii in untrusted reason; sanitize must not introduce non-ascii
    # from our fixed strings. Reason may contain unicode from model; the ticket
    # requires NEW printed strings (fixed labels) to be ASCII. Guard the fixed
    # refusal / title / summary vocabulary by checking module constants and the
    # section with a plain-ASCII reason.
    result_obj = _make_result(source_sha256=sha)
    append_extraction_result(out, result_obj)

    result = CliRunner().invoke(
        cli,
        ["skill", "audit", str(skill), "--extraction", str(out)],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    section = _clause_evidence_section(result.output)
    # Fixed vocabulary lines must be ASCII. Strip table box-drawing from Rich
    # by checking the plain summary / title lines we own.
    from skill_harness.extractor import clause_evidence as ce

    owned = "\n".join(
        [
            ce.SECTION_TITLE,
            ce.REASON_NO_EXTRACTION,
            ce.REASON_LEGACY,
            ce.REASON_UNREADABLE,
            ce.INSTANTIATED_COVERAGE_REFUSAL,
            ce.SAME_SHA_APPEND_REFUSAL.format(path="x", sha16="a" * 16),
            ce.REASON_NO_MATCHING.format(sha16="a" * 16, path="x"),
            ce.REASON_AMBIGUOUS.format(n=2),
            ce.UNREVIEWED_SEMANTIC_VACUOUS_LABEL,
            *ce.format_summary_lines(
                load_clause_evidence(out, sha).measured.summary  # type: ignore[union-attr]
            ),
            ce.format_refusal_line(no_extraction_outcome()),
        ]
    )
    offenders = sorted({ch for ch in owned if not ch.isascii()})
    assert not offenders, f"non-ASCII in new clause-evidence strings: {offenders!r}"

    # Happy-path section body without Rich table borders: instrument + summary.
    for line in section.splitlines():
        if line.startswith("extractor ") or line.startswith("clauses:") or line.startswith(
            "flagged:"
        ) or line.startswith("scoreable-axis:") or line.startswith(
            "Constructible coverage:"
        ) or line.startswith("Instantiated coverage:") or line.startswith(
            "Clause evidence"
        ):
            bad = sorted({ch for ch in line if not ch.isascii()})
            assert not bad, f"non-ASCII in owned line {line!r}: {bad!r}"


def test_skill_clauses_legend_notes_extraction_carrier() -> None:
    assert "skill init --out" in _SKILL_CLAUSES_LEGEND
    assert "skill audit --extraction" in _SKILL_CLAUSES_LEGEND
    assert "vacuity kind and reason are not stored in the DB" in _SKILL_CLAUSES_LEGEND
    note_line = next(
        ln for ln in _SKILL_CLAUSES_LEGEND.splitlines() if ln.startswith("Note:")
    )
    offenders = sorted({ch for ch in note_line if not ch.isascii()})
    assert not offenders, f"non-ASCII in legend note: {offenders!r}"


def test_skill_clauses_legend_appears_in_cli(tmp_path: Path) -> None:
    from skill_harness.storage.migrations import open_evidence
    from skill_harness.storage.models import ClauseWrite, SkillWrite
    from skill_harness.storage.repositories.evidence.clauses import insert_clause
    from skill_harness.storage.repositories.evidence.skills import insert_skill
    from skill_harness.storage.transaction import writer_transaction

    evidence_db = tmp_path / "evidence.db"
    skill_id = "legend-157"
    ev = open_evidence(evidence_db)
    try:
        with writer_transaction(ev):
            insert_skill(
                ev,
                SkillWrite(
                    skill_id=skill_id,
                    name="legend-skill",
                    source_path="/tmp/SKILL.md",
                    source_sha256="c" * 64,
                    imported_at="2026-06-06T00:00:00.000000+00:00",
                ),
            )
            insert_clause(
                ev,
                ClauseWrite(
                    clause_id="clause-157",
                    skill_id=skill_id,
                    clause_index=0,
                    rendering_index=0,
                    clause_text="Be concise.",
                    axis="verbosity",
                    comparator="decrease",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256="abc123",
                    created_at="2026-06-06T00:00:00.000000+00:00",
                ),
            )
    finally:
        ev.close()

    result = CliRunner().invoke(
        cli, ["skill", "clauses", skill_id, "--evidence-db", str(evidence_db)]
    )
    assert result.exit_code == 0, result.output
    assert "skill init --out" in result.output
    assert "skill audit --extraction" in result.output
