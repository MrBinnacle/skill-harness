"""Tests for skill_harness.extractor.pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from skill_harness.extractor.errors import ExtractorClaudeError, MalformedSkillError
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractorInstrument,
    FalsifyingCaseSchema,
)
from skill_harness.extractor.pipeline import _clause_id, _to_db_comparator, extract_skill
from skill_harness.storage.migrations import open_evidence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clause(
    index: int = 0,
    comparator: str = "increase",
    vacuity_flag: str = "none",
) -> ExtractedClause:
    fc = None
    if vacuity_flag == "none":
        fc = FalsifyingCaseSchema(
            input_population_spec="Factual prompts",
            expected_directional_pair="A beats B on specificity",
            min_reproducibility=0.8,
        )
    return ExtractedClause(
        clause_index=index,
        clause_text=f"Clause {index} text.",
        axis="specificity",
        comparator=comparator,  # type: ignore[arg-type]
        oracle_tier=1,
        vacuity_flag=vacuity_flag,  # type: ignore[arg-type]
        falsifying_case=fc,
    )


def _make_skill_file(tmp_path: Path, body: str = "# Instructions\nBe specific.\n") -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(f"---\nname: test-skill\n---\n\n{body}", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _clause_id
# ---------------------------------------------------------------------------


def test_clause_id_is_64_chars() -> None:
    cid = _clause_id("abc", 0)
    assert len(cid) == 64


def test_clause_id_deterministic() -> None:
    assert _clause_id("skill-a", 3) == _clause_id("skill-a", 3)


def test_clause_id_differs_by_index() -> None:
    assert _clause_id("skill-a", 0) != _clause_id("skill-a", 1)


def test_clause_id_differs_by_skill() -> None:
    assert _clause_id("skill-a", 0) != _clause_id("skill-b", 0)


# ---------------------------------------------------------------------------
# _to_db_comparator
# ---------------------------------------------------------------------------


def test_to_db_comparator_increase() -> None:
    assert _to_db_comparator("increase") == "increase"


def test_to_db_comparator_decrease() -> None:
    assert _to_db_comparator("decrease") == "decrease"


def test_to_db_comparator_preserve_maps_to_match() -> None:
    assert _to_db_comparator("preserve") == "match"


def test_to_db_comparator_unspecified_raises() -> None:
    with pytest.raises(ValueError, match="comparator_unspecified cannot be stored"):
        _to_db_comparator("comparator_unspecified")


# ---------------------------------------------------------------------------
# extract_skill — dry-run (no evidence_conn)
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_dry_run_returns_result(mock_call: Any, tmp_path: Path) -> None:
    mock_call.return_value = (
        [_make_clause(0), _make_clause(1)],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)

    result = extract_skill(skill_path, evidence_conn=None)

    assert result.name == "test-skill"
    assert len(result.clauses) == 2
    assert result.extractor_model == "claude-opus-5"
    mock_call.assert_called_once()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_dry_run_does_not_write_to_db(mock_call: Any, tmp_path: Path) -> None:
    mock_call.return_value = (
        [_make_clause(0)],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)

    # No evidence_conn passed → dry-run → must not touch any DB.
    extract_skill(skill_path, evidence_conn=None)

    # No DB files should exist in tmp_path.
    db_files = list(tmp_path.glob("*.db"))
    assert db_files == []


# ---------------------------------------------------------------------------
# extract_skill — with persistence
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_persists_skill_row(mock_call: Any, tmp_path: Path) -> None:
    mock_call.return_value = (
        [_make_clause(0), _make_clause(1)],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)
    evidence_conn = open_evidence(tmp_path / "evidence.db")

    try:
        result = extract_skill(skill_path, evidence_conn=evidence_conn)

        row = evidence_conn.execute(
            "SELECT skill_id, name FROM skills WHERE skill_id = ?",
            (result.skill_id,),
        ).fetchone()
        assert row is not None
        assert row[1] == "test-skill"
    finally:
        evidence_conn.close()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_persists_clause_rows(mock_call: Any, tmp_path: Path) -> None:
    mock_call.return_value = (
        [_make_clause(0), _make_clause(1)],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)
    evidence_conn = open_evidence(tmp_path / "evidence.db")

    try:
        result = extract_skill(skill_path, evidence_conn=evidence_conn)

        rows = evidence_conn.execute(
            "SELECT clause_index FROM clauses WHERE skill_id = ? ORDER BY clause_index",
            (result.skill_id,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 0
        assert rows[1][0] == 1
    finally:
        evidence_conn.close()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_stores_falsifying_case_sha256(mock_call: Any, tmp_path: Path) -> None:
    clause = _make_clause(0, comparator="increase")
    assert clause.falsifying_case is not None
    mock_call.return_value = (
        [clause],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )

    skill_path = _make_skill_file(tmp_path)
    evidence_conn = open_evidence(tmp_path / "evidence.db")

    try:
        result = extract_skill(skill_path, evidence_conn=evidence_conn)

        row = evidence_conn.execute(
            "SELECT falsifying_case_schema_sha256 FROM clauses WHERE skill_id = ?",
            (result.skill_id,),
        ).fetchone()
        assert row is not None
        expected_sha = clause.falsifying_case.sha256_hex()
        assert row[0] == expected_sha
    finally:
        evidence_conn.close()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_preserve_comparator_stored_as_match(mock_call: Any, tmp_path: Path) -> None:
    mock_call.return_value = (
        [_make_clause(0, comparator="preserve")],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)
    evidence_conn = open_evidence(tmp_path / "evidence.db")

    try:
        extract_skill(skill_path, evidence_conn=evidence_conn)

        row = evidence_conn.execute("SELECT comparator FROM clauses LIMIT 1").fetchone()
        assert row is not None
        assert row[0] == "match"
    finally:
        evidence_conn.close()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_raises_on_comparator_unspecified_at_persist(
    mock_call: Any, tmp_path: Path
) -> None:
    """C4 regression: persisting a comparator_unspecified clause must raise, not
    silently drop it. A silent drop would make the DB clause count disagree with
    the reported extraction count (corrupting Coverage/Contribution metrics) --
    see extract_skill's own ':raises ValueError' contract.
    """
    c_unspec = ExtractedClause(
        clause_index=0,
        clause_text="Be helpful.",
        axis="helpfulness",
        comparator="comparator_unspecified",
        oracle_tier=2,
        vacuity_flag="semantic_vacuous_pending_review",
        falsifying_case=None,
    )
    c_normal = _make_clause(1, comparator="increase")
    mock_call.return_value = (
        [c_unspec, c_normal],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )

    skill_path = _make_skill_file(tmp_path)
    evidence_conn = open_evidence(tmp_path / "evidence.db")

    try:
        with pytest.raises(ValueError, match="comparator_unspecified cannot be stored"):
            extract_skill(skill_path, evidence_conn=evidence_conn)

        # Persistence must abort entirely -- no skill row and no clause rows,
        # not a partial write of only the well-formed clause.
        skill_rows = evidence_conn.execute("SELECT COUNT(*) FROM skills").fetchone()
        assert skill_rows[0] == 0

        clause_rows = evidence_conn.execute("SELECT COUNT(*) FROM clauses").fetchone()
        assert clause_rows[0] == 0
    finally:
        evidence_conn.close()


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_dry_run_does_not_raise_on_comparator_unspecified(
    mock_call: Any, tmp_path: Path
) -> None:
    """Dry-run (no evidence_conn) never persists, so it must NOT raise even when
    a clause is comparator_unspecified -- the raise is a persist-time contract only.
    """
    c_unspec = ExtractedClause(
        clause_index=0,
        clause_text="Be helpful.",
        axis="helpfulness",
        comparator="comparator_unspecified",
        oracle_tier=2,
        vacuity_flag="semantic_vacuous_pending_review",
        falsifying_case=None,
    )
    mock_call.return_value = (
        [c_unspec],
        ExtractorInstrument(
            model_id="claude-opus-5", system_prompt_sha256="b" * 64, tool_schema_sha256="c" * 64
        ),
    )
    skill_path = _make_skill_file(tmp_path)

    result = extract_skill(skill_path, evidence_conn=None)

    assert len(result.clauses) == 1
    assert result.clauses[0].comparator == "comparator_unspecified"


# ---------------------------------------------------------------------------
# extract_skill — error propagation
# ---------------------------------------------------------------------------


def test_extract_skill_propagates_malformed_skill(tmp_path: Path) -> None:
    empty_md = tmp_path / "empty.md"
    empty_md.write_text("---\nname: x\n---\n", encoding="utf-8")

    with pytest.raises(MalformedSkillError):
        extract_skill(empty_md, evidence_conn=None)


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_extract_skill_propagates_claude_error(mock_call: Any, tmp_path: Path) -> None:
    mock_call.side_effect = ExtractorClaudeError("API down")
    skill_path = _make_skill_file(tmp_path)

    with pytest.raises(ExtractorClaudeError):
        extract_skill(skill_path, evidence_conn=None)
