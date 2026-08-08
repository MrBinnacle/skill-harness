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


# ---------------------------------------------------------------------------
# ExtractedClause — vacuity and falsifying_case are independent (#136)
# ---------------------------------------------------------------------------


def test_four_combinations_of_flag_and_case_all_valid() -> None:
    """(flagged, not flagged) x (case present, case absent) must all construct."""
    fc = FalsifyingCaseSchema.model_validate(_valid_fc())
    combos: list[tuple[str, FalsifyingCaseSchema | None]] = [
        ("none", fc),
        ("none", None),
        ("semantic_vacuous_pending_review", fc),
        ("semantic_vacuous_pending_review", None),
    ]
    for flag, case in combos:
        clause = ExtractedClause.model_validate(
            _valid_clause(
                vacuity_flag=flag,
                falsifying_case=case,
                comparator="comparator_unspecified" if flag != "none" else "increase",
            )
        )
        assert clause.vacuity_flag == flag
        if case is None:
            assert clause.falsifying_case is None
        else:
            assert clause.falsifying_case is not None


def test_falsifying_case_schema_strictness_unchanged() -> None:
    """FalsifyingCaseSchema stays strict: empty required field and OOR min_repro rejected."""
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(input_population_spec=""))
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(expected_directional_pair=""))
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(min_reproducibility=0.0))
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate(_valid_fc(min_reproducibility=1.1))
    with pytest.raises(Exception):
        FalsifyingCaseSchema.model_validate({**_valid_fc(), "extra_field": "nope"})
    assert FalsifyingCaseSchema.model_config.get("strict") is True
    assert FalsifyingCaseSchema.model_config.get("extra") == "forbid"


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
        extractor_model="claude-opus-5",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    assert result.name == "test-skill"
    assert len(result.clauses) == 1
    assert result.extractor_model == "claude-opus-5"
    assert result.system_prompt_sha256 == "b" * 64
    assert result.tool_schema_sha256 == "c" * 64


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
            extractor_model="claude-opus-5",
            system_prompt_sha256="b" * 64,
            tool_schema_sha256="c" * 64,
        )
