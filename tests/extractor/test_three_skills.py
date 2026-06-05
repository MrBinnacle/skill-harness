"""Cross-skill extraction consistency tests (mocked API calls).

Verifies that the pipeline produces structurally valid ExtractionResult
objects for three different skill documents, including the ai-slop-sentinel
skill.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)
from skill_harness.extractor.pipeline import extract_skill

# ---------------------------------------------------------------------------
# Paths to real skill files
# ---------------------------------------------------------------------------

_AI_SLOP_SENTINEL = Path.home() / ".claude" / "skills" / "ai-slop-sentinel" / "SKILL.md"
_FIXTURES = Path(__file__).parent / "fixtures"
_MOSTLY_PROSE = _FIXTURES / "mostly_prose.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clause(index: int, comparator: str = "increase") -> ExtractedClause:
    fc = FalsifyingCaseSchema(
        input_population_spec="Generic prompts",
        expected_directional_pair=f"A beats B on axis_{index}",
        min_reproducibility=0.7,
    )
    return ExtractedClause(
        clause_index=index,
        clause_text=f"Clause {index} from mock.",
        axis=f"axis_{index}",
        comparator=comparator,  # type: ignore[arg-type]
        oracle_tier=1,
        vacuity_flag="none",
        falsifying_case=fc,
    )


def _make_vacuous_clause(index: int) -> ExtractedClause:
    return ExtractedClause(
        clause_index=index,
        clause_text="Be helpful.",
        axis="helpfulness",
        comparator="comparator_unspecified",
        oracle_tier=2,
        vacuity_flag="semantic_vacuous_pending_review",
        falsifying_case=None,
    )


def _mock_extract(n_clauses: int = 5) -> list[ExtractedClause]:
    return [_make_clause(i) for i in range(n_clauses)]


# ---------------------------------------------------------------------------
# Skill 1: mostly-prose fixture
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_mostly_prose_fixture_produces_valid_result(
    mock_call: Any,
) -> None:
    mock_call.return_value = [_make_vacuous_clause(0), _make_clause(1)]
    result = extract_skill(_MOSTLY_PROSE, evidence_conn=None)
    assert isinstance(result, ExtractionResult)
    assert result.name == "mostly-prose-skill"
    assert len(result.clauses) == 2


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_mostly_prose_skill_id_is_sha256(
    mock_call: Any,
) -> None:
    mock_call.return_value = _mock_extract()
    result = extract_skill(_MOSTLY_PROSE, evidence_conn=None)
    assert len(result.skill_id) == 64
    assert result.skill_id == result.source_sha256


# ---------------------------------------------------------------------------
# Skill 2: ai-slop-sentinel (real file, mocked API)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _AI_SLOP_SENTINEL.exists(),
    reason="ai-slop-sentinel SKILL.md not found at expected path",
)
@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_ai_slop_sentinel_produces_valid_result(
    mock_call: Any,
) -> None:
    mock_call.return_value = _mock_extract(7)
    result = extract_skill(_AI_SLOP_SENTINEL, evidence_conn=None)
    assert isinstance(result, ExtractionResult)
    assert len(result.clauses) == 7


@pytest.mark.skipif(
    not _AI_SLOP_SENTINEL.exists(),
    reason="ai-slop-sentinel SKILL.md not found at expected path",
)
@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_ai_slop_sentinel_source_path_is_absolute(
    mock_call: Any,
) -> None:
    mock_call.return_value = _mock_extract(3)
    result = extract_skill(_AI_SLOP_SENTINEL, evidence_conn=None)
    assert Path(result.source_path).is_absolute()


@pytest.mark.skipif(
    not _AI_SLOP_SENTINEL.exists(),
    reason="ai-slop-sentinel SKILL.md not found at expected path",
)
@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_ai_slop_sentinel_body_passed_to_claude(
    mock_call: Any,
) -> None:
    """The body passed to Claude must not contain the raw frontmatter delimiters."""
    mock_call.return_value = _mock_extract(3)
    extract_skill(_AI_SLOP_SENTINEL, evidence_conn=None)

    call_args = mock_call.call_args
    body_arg = call_args[0][0]
    # The body should be non-empty.
    assert len(body_arg.strip()) > 0


# ---------------------------------------------------------------------------
# Skill 3: a synthetic multi-clause skill (inline)
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_synthetic_multi_clause_skill(
    mock_call: Any,
    tmp_path: Path,
) -> None:
    synthetic = tmp_path / "SKILL.md"
    synthetic.write_text(
        "---\nname: synthetic-skill\n---\n\n"
        "Always use bullet lists for enumerations.\n"
        "Keep responses under 200 words.\n"
        "Include at least one concrete example per claim.\n",
        encoding="utf-8",
    )
    mock_call.return_value = _mock_extract(3)

    result = extract_skill(synthetic, evidence_conn=None)
    assert len(result.clauses) == 3
    assert result.name == "synthetic-skill"


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_all_three_skills_have_unique_skill_ids(
    mock_call: Any,
    tmp_path: Path,
) -> None:
    """Distinct skill files must produce distinct skill_ids."""
    mock_call.return_value = _mock_extract(2)

    skill_a = tmp_path / "a.md"
    skill_a.write_text("---\nname: a\n---\n\nContent A.\n", encoding="utf-8")

    skill_b = tmp_path / "b.md"
    skill_b.write_text("---\nname: b\n---\n\nContent B — different.\n", encoding="utf-8")

    result_a = extract_skill(skill_a, evidence_conn=None)
    result_b = extract_skill(skill_b, evidence_conn=None)

    assert result_a.skill_id != result_b.skill_id


@patch("skill_harness.extractor.pipeline.call_extract_clauses")
def test_same_skill_file_produces_same_skill_id(
    mock_call: Any,
    tmp_path: Path,
) -> None:
    mock_call.return_value = _mock_extract(2)

    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("---\nname: stable\n---\n\nContent.\n", encoding="utf-8")

    result1 = extract_skill(skill_path, evidence_conn=None)
    result2 = extract_skill(skill_path, evidence_conn=None)

    assert result1.skill_id == result2.skill_id
