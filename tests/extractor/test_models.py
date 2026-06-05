"""Tests for skill_harness.extractor.models."""

from __future__ import annotations

import json

import pytest

from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    FalsifyingCaseSchema,
)

# ---------------------------------------------------------------------------
# FalsifyingCaseSchema
# ---------------------------------------------------------------------------


def _valid_fc(**overrides: object) -> dict:  # type: ignore[type-arg]
    base: dict = {  # type: ignore[type-arg]
        "input_population_spec": "Short factual prompts requiring a single-sentence answer",
        "expected_directional_pair": "A (with clause) uses bullet list; B (without) uses prose",
        "min_reproducibility": 0.8,
    }
    base.update(overrides)
    return base


def test_falsifying_case_schema_valid() -> None:
    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    assert fc.min_reproducibility == 0.8


def test_falsifying_case_schema_sha256_is_64_chars() -> None:
    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    sha = fc.sha256_hex()
    assert len(sha) == 64


def test_falsifying_case_schema_sha256_is_deterministic() -> None:
    fc1 = FalsifyingCaseSchema.model_validate(_valid_fc())
    fc2 = FalsifyingCaseSchema.model_validate(_valid_fc())
    assert fc1.sha256_hex() == fc2.sha256_hex()


def test_falsifying_case_schema_sha256_changes_with_content() -> None:
    fc1 = FalsifyingCaseSchema.model_validate(_valid_fc())
    fc2 = FalsifyingCaseSchema.model_validate(_valid_fc(min_reproducibility=0.9))
    assert fc1.sha256_hex() != fc2.sha256_hex()


def test_falsifying_case_sha256_matches_manual_json() -> None:
    """SHA-256 must equal hashlib.sha256(json.dumps(model_dump(), sort_keys=True))."""
    import hashlib

    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    expected = hashlib.sha256(
        json.dumps(fc.model_dump(), sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert fc.sha256_hex() == expected


def test_falsifying_case_rejects_zero_reproducibility() -> None:
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(min_reproducibility=0.0))


def test_falsifying_case_rejects_reproducibility_above_one() -> None:
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(min_reproducibility=1.1))


def test_falsifying_case_rejects_empty_input_spec() -> None:
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(input_population_spec=""))


# ---------------------------------------------------------------------------
# ExtractedClause — construction helpers
# ---------------------------------------------------------------------------


def _valid_clause(**overrides: object) -> dict:  # type: ignore[type-arg]
    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    base: dict = {  # type: ignore[type-arg]
        "clause_index": 0,
        "clause_text": "Always use bullet lists for enumerated items.",
        "axis": "list_usage",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        "falsifying_case": fc,
    }
    base.update(overrides)
    return base


def test_extracted_clause_valid() -> None:
    clause = ExtractedClause.model_validate(_valid_clause())
    assert clause.axis == "list_usage"


def test_extracted_clause_db_comparator_increase() -> None:
    clause = ExtractedClause.model_validate(_valid_clause(comparator="increase"))
    assert clause.db_comparator() == "increase"


def test_extracted_clause_db_comparator_decrease() -> None:
    clause = ExtractedClause.model_validate(_valid_clause(comparator="decrease"))
    assert clause.db_comparator() == "decrease"


def test_extracted_clause_db_comparator_preserve_maps_to_match() -> None:
    clause = ExtractedClause.model_validate(_valid_clause(comparator="preserve"))
    assert clause.db_comparator() == "match"


def test_extracted_clause_db_comparator_unspecified_passthrough() -> None:
    """comparator_unspecified passes through from db_comparator; pipeline rejects it."""
    clause = ExtractedClause.model_validate(
        _valid_clause(
            comparator="comparator_unspecified",
            vacuity_flag="semantic_vacuous_pending_review",
            falsifying_case=None,
        )
    )
    assert clause.db_comparator() == "comparator_unspecified"


# ---------------------------------------------------------------------------
# ExtractedClause — vacuity / falsifying_case invariant
# ---------------------------------------------------------------------------


def test_none_vacuity_requires_falsifying_case() -> None:
    with pytest.raises(Exception, match="falsifying_case is required"):
        ExtractedClause.model_validate(_valid_clause(vacuity_flag="none", falsifying_case=None))


def test_semantic_vacuous_forbids_falsifying_case() -> None:
    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    with pytest.raises(Exception, match="falsifying_case must be None"):
        ExtractedClause.model_validate(
            _valid_clause(
                vacuity_flag="semantic_vacuous_pending_review",
                falsifying_case=fc,
            )
        )


def test_semantic_vacuous_without_falsifying_case_is_valid() -> None:
    clause = ExtractedClause.model_validate(
        _valid_clause(
            vacuity_flag="semantic_vacuous_pending_review",
            falsifying_case=None,
            comparator="comparator_unspecified",
        )
    )
    assert clause.vacuity_flag == "semantic_vacuous_pending_review"
    assert clause.falsifying_case is None


def test_clause_index_must_be_non_negative() -> None:
    with pytest.raises(Exception):
        ExtractedClause.model_validate(_valid_clause(clause_index=-1))


def test_clause_rejects_invalid_oracle_tier() -> None:
    with pytest.raises(Exception):
        ExtractedClause.model_validate(_valid_clause(oracle_tier=4))


def test_clause_rejects_invalid_comparator() -> None:
    with pytest.raises(Exception):
        ExtractedClause.model_validate(_valid_clause(comparator="sideways"))


def test_clause_rejects_invalid_vacuity_flag() -> None:
    with pytest.raises(Exception):
        ExtractedClause.model_validate(_valid_clause(vacuity_flag="mechanical_vacuous"))


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------


def test_extraction_result_valid() -> None:
    clause = ExtractedClause.model_validate(_valid_clause())
    sha = "a" * 64
    result = ExtractionResult(
        skill_id=sha,
        name="test-skill",
        source_path="/tmp/SKILL.md",
        source_sha256=sha,
        clauses=[clause],
        raw_frontmatter={"name": "test-skill"},
    )
    assert result.name == "test-skill"
    assert len(result.clauses) == 1


def test_extraction_result_sha256_length_enforced() -> None:
    clause = ExtractedClause.model_validate(_valid_clause())
    with pytest.raises(Exception):
        ExtractionResult(
            skill_id="tooshort",
            name="bad",
            source_path="/tmp/SKILL.md",
            source_sha256="tooshort",  # must be 64 chars
            clauses=[clause],
            raw_frontmatter={},
        )
