"""#141 — separate weak_directive from not_a_directive under the vacuity flag.

Pins external behaviour: ExtractedClause carries vacuity_kind, the system prompt
states both conditions (without defining weak_directive via case-constructibility),
JSONL serialisation preserves the field, census surfaces report the two counts
separately, and storage vacuity_flag values stay unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skill_harness.extractor.claude import (
    _EXTRACT_CLAUSES_SCHEMA,
    _SYSTEM_PROMPT,
    call_extract_clauses,
)
from skill_harness.extractor.corpus_census import format_human_report, run_census
from skill_harness.extractor.models import ExtractedClause, FalsifyingCaseSchema

_REPO = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO / "tests" / "fixtures" / "corpus_census"


def _fc(**overrides: object) -> FalsifyingCaseSchema:
    base: dict[str, object] = {
        "input_population_spec": "Short factual prompts",
        "expected_directional_pair": "A beats B on the axis",
        "min_reproducibility": 0.8,
    }
    base.update(overrides)
    return FalsifyingCaseSchema.model_validate(base)


def _clause(**overrides: object) -> ExtractedClause:
    data: dict[str, object] = {
        "clause_index": 0,
        "clause_text": "Always use bullet lists for enumerated items.",
        "axis": "list_usage",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        "vacuity_kind": None,
        "falsifying_case": _fc(),
    }
    data.update(overrides)
    return ExtractedClause.model_validate(data)


# ---------------------------------------------------------------------------
# Model: vacuity_kind couples to vacuity_flag
# ---------------------------------------------------------------------------


def test_weak_directive_clause_carries_kind() -> None:
    """Condition (a): behavioural but too vague/metaphorical."""
    clause = _clause(
        clause_text="Be helpful.",
        axis="helpfulness",
        comparator="comparator_unspecified",
        vacuity_flag="semantic_vacuous_pending_review",
        vacuity_kind="weak_directive",
        falsifying_case=None,
    )
    assert clause.vacuity_flag == "semantic_vacuous_pending_review"
    assert clause.vacuity_kind == "weak_directive"


def test_not_a_directive_trigger_condition() -> None:
    """Condition (b): trigger condition is not a behavioural directive."""
    text = (
        "Invoke when user asks to evaluate, pressure test, validate, or "
        "decide go/no-go on an initiative with meaningful downside."
    )
    clause = _clause(
        clause_text=text,
        axis="trigger",
        comparator="comparator_unspecified",
        vacuity_flag="semantic_vacuous_pending_review",
        vacuity_kind="not_a_directive",
        falsifying_case=None,
    )
    assert clause.vacuity_kind == "not_a_directive"
    assert clause.vacuity_flag == "semantic_vacuous_pending_review"


def test_not_a_directive_factual_statement() -> None:
    """Condition (b): factual/heuristic statement is not a behavioural directive."""
    text = (
        "Encoding ties as `0.5` and updating `Beta(1+w, 1+n-w)` with "
        "`w = sum_of_encoded_outcomes` is a quasi-Bayesian heuristic."
    )
    clause = _clause(
        clause_text=text,
        axis="encoding",
        comparator="comparator_unspecified",
        vacuity_flag="semantic_vacuous_pending_review",
        vacuity_kind="not_a_directive",
        falsifying_case=None,
    )
    assert clause.vacuity_kind == "not_a_directive"


def test_normal_testable_clause_remains_none() -> None:
    clause = _clause()
    assert clause.vacuity_flag == "none"
    assert clause.vacuity_kind is None


def test_flagged_without_kind_rejected() -> None:
    with pytest.raises(Exception, match="vacuity_kind"):
        _clause(
            vacuity_flag="semantic_vacuous_pending_review",
            vacuity_kind=None,
            falsifying_case=None,
            comparator="comparator_unspecified",
        )


def test_none_flag_rejects_non_null_kind() -> None:
    with pytest.raises(Exception, match="vacuity_kind"):
        _clause(vacuity_flag="none", vacuity_kind="weak_directive")


def test_false_positive_label_is_not_a_kind_value() -> None:
    """Detector must not self-report false_positive as a vacuity_kind."""
    with pytest.raises(Exception):
        _clause(
            vacuity_flag="semantic_vacuous_pending_review",
            vacuity_kind="false_positive",
            falsifying_case=None,
            comparator="comparator_unspecified",
        )


# ---------------------------------------------------------------------------
# Three false-positive shapes must remain vacuity_flag == none
# ---------------------------------------------------------------------------


def test_long_technical_directive_is_none() -> None:
    text = (
        "When the user supplies a multi-step migration plan with explicit "
        "rollback criteria, enumerate each step as a numbered checklist item "
        "and attach the rollback predicate to that item before executing."
    )
    clause = _clause(clause_text=text, axis="structure_score", comparator="increase")
    assert clause.vacuity_flag == "none"
    assert clause.vacuity_kind is None


def test_never_x_constraint_directive_is_none() -> None:
    clause = _clause(
        clause_text="Never invent citations; if no source is available, say so.",
        axis="citation_presence_per_flag",
        comparator="increase",
    )
    assert clause.vacuity_flag == "none"
    assert clause.vacuity_kind is None


def test_directive_with_embedded_rationale_is_none() -> None:
    text = (
        "Prefer short sentences because long ones raise cognitive load; "
        "cap each sentence at 25 words when explaining a procedure."
    )
    clause = _clause(clause_text=text, axis="verbosity", comparator="decrease")
    assert clause.vacuity_flag == "none"
    assert clause.vacuity_kind is None


# ---------------------------------------------------------------------------
# JSONL serialisation carries vacuity_kind
# ---------------------------------------------------------------------------


def test_jsonl_serialisation_includes_kind_for_each_condition() -> None:
    weak = _clause(
        clause_text="Sound natural.",
        axis="naturalness",
        comparator="comparator_unspecified",
        vacuity_flag="semantic_vacuous_pending_review",
        vacuity_kind="weak_directive",
        falsifying_case=None,
    )
    non_dir = _clause(
        clause_index=1,
        clause_text="Invoke when the user asks for a go/no-go decision.",
        axis="trigger",
        comparator="comparator_unspecified",
        vacuity_flag="semantic_vacuous_pending_review",
        vacuity_kind="not_a_directive",
        falsifying_case=None,
    )
    none_clause = _clause(clause_index=2)
    lines = [
        json.dumps(weak.model_dump(mode="json"), ensure_ascii=True, sort_keys=True),
        json.dumps(non_dir.model_dump(mode="json"), ensure_ascii=True, sort_keys=True),
        json.dumps(none_clause.model_dump(mode="json"), ensure_ascii=True, sort_keys=True),
    ]
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["vacuity_kind"] == "weak_directive"
    assert parsed[1]["vacuity_kind"] == "not_a_directive"
    assert parsed[2]["vacuity_kind"] is None
    assert parsed[2]["vacuity_flag"] == "none"


# ---------------------------------------------------------------------------
# System prompt: two conditions, no case-constructibility definition of (a)
# ---------------------------------------------------------------------------


def test_prompt_states_both_conditions_with_examples() -> None:
    assert "weak_directive" in _SYSTEM_PROMPT
    assert "not_a_directive" in _SYSTEM_PROMPT
    assert "be helpful" in _SYSTEM_PROMPT.lower() or '"be helpful"' in _SYSTEM_PROMPT
    assert "sound natural" in _SYSTEM_PROMPT.lower() or '"sound natural"' in _SYSTEM_PROMPT
    assert "go/no-go" in _SYSTEM_PROMPT
    assert "quasi-Bayesian" in _SYSTEM_PROMPT or "quasi-bayesian" in _SYSTEM_PROMPT.lower()


def test_prompt_states_constructible_case_is_none_even_if_long_technical_hedged() -> None:
    assert "constructible falsifying case is vacuity_flag" in _SYSTEM_PROMPT or (
        "constructible falsifying case is" in _SYSTEM_PROMPT
        and 'vacuity_flag "none"' in _SYSTEM_PROMPT
    )
    assert "long, technical, or hedged" in _SYSTEM_PROMPT


def test_prompt_does_not_define_weak_directive_via_case_constructibility() -> None:
    """#141 / #136: must not re-couple condition (a) to falsifying-case presence."""
    assert "lacks a constructible falsifying case" not in _SYSTEM_PROMPT


def test_tool_schema_exposes_vacuity_kind_enum() -> None:
    props = _EXTRACT_CLAUSES_SCHEMA["properties"]["clauses"]["items"]["properties"]
    assert "vacuity_kind" in props
    assert props["vacuity_kind"]["enum"] == ["weak_directive", "not_a_directive"]
    # vacuity_flag values themselves are unchanged.
    assert props["vacuity_flag"]["enum"] == ["none", "semantic_vacuous_pending_review"]


# ---------------------------------------------------------------------------
# Mocked extraction path: kinds round-trip; instrument still stamped
# ---------------------------------------------------------------------------


def _make_tool_use_block(input_data: dict[str, Any]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_clauses"
    block.input = input_data
    return block


def _make_response(content: list[MagicMock]) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.stop_reason = "tool_use"
    return resp


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_extraction_round_trips_both_kinds_and_stamps_instrument(
    mock_anthropic_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    raw_clauses = [
        {
            "clause_index": 0,
            "clause_text": "Be helpful.",
            "axis": "helpfulness",
            "comparator": "comparator_unspecified",
            "oracle_tier": 2,
            "vacuity_flag": "semantic_vacuous_pending_review",
            "vacuity_kind": "weak_directive",
        },
        {
            "clause_index": 1,
            "clause_text": "Invoke when user asks to evaluate go/no-go.",
            "axis": "trigger",
            "comparator": "comparator_unspecified",
            "oracle_tier": 2,
            "vacuity_flag": "semantic_vacuous_pending_review",
            "vacuity_kind": "not_a_directive",
        },
        {
            "clause_index": 2,
            "clause_text": "Always use bullet lists for enumerated items.",
            "axis": "structure_score",
            "comparator": "increase",
            "oracle_tier": 1,
            "vacuity_flag": "none",
            "falsifying_case": {
                "input_population_spec": "lists",
                "expected_directional_pair": "A uses bullets more",
                "min_reproducibility": 0.8,
            },
        },
    ]
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": raw_clauses})]
    )

    clauses, instrument = call_extract_clauses("body")
    assert [c.vacuity_kind for c in clauses] == [
        "weak_directive",
        "not_a_directive",
        None,
    ]
    assert [c.vacuity_flag for c in clauses] == [
        "semantic_vacuous_pending_review",
        "semantic_vacuous_pending_review",
        "none",
    ]
    # Generation identity from #135: prompt change is a new calibration generation.
    assert instrument.model_id
    assert re.fullmatch(r"[0-9a-f]{64}", instrument.system_prompt_sha256)
    assert re.fullmatch(r"[0-9a-f]{64}", instrument.tool_schema_sha256)
    # Prompt text participates in the hash (non-silent generation break).
    import hashlib

    assert (
        instrument.system_prompt_sha256
        == hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    )


# ---------------------------------------------------------------------------
# Census surface: two conditions never collapse into one count alone
# ---------------------------------------------------------------------------


def _write_split_jsonl(path: Path) -> None:
    header = {
        "record_type": "header",
        "extractor_model": "claude-opus-5",
        "calibration_generation": "fixture-vacuity-kind",
    }
    skill = {
        "slug": "split-skill",
        "ok": True,
        "extractor_model": "claude-opus-5",
        "system_prompt_sha256": "b" * 64,
        "tool_schema_sha256": "c" * 64,
        "clauses": [
            {
                "clause_index": 0,
                "clause_text": "be nice",
                "axis": "compliance_proxy",
                "comparator": "increase",
                "oracle_tier": 1,
                "vacuity_flag": "semantic_vacuous_pending_review",
                "vacuity_kind": "weak_directive",
            },
            {
                "clause_index": 1,
                "clause_text": "Invoke when user asks go/no-go.",
                "axis": "trigger",
                "comparator": "comparator_unspecified",
                "oracle_tier": 2,
                "vacuity_flag": "semantic_vacuous_pending_review",
                "vacuity_kind": "not_a_directive",
            },
            {
                "clause_index": 2,
                "clause_text": "use bullets",
                "axis": "structure_score",
                "comparator": "increase",
                "oracle_tier": 1,
                "vacuity_flag": "none",
                "falsifying_case": {
                    "input_population_spec": "lists",
                    "expected_directional_pair": "A more structured",
                    "min_reproducibility": 0.8,
                },
            },
            {
                "clause_index": 3,
                "clause_text": "legacy flagged without kind",
                "axis": "formality",
                "comparator": "increase",
                "oracle_tier": 2,
                "vacuity_flag": "semantic_vacuous_pending_review",
            },
        ],
    }
    path.write_text(
        json.dumps(header, ensure_ascii=True) + "\n" + json.dumps(skill, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def test_census_reports_two_conditions_separately(tmp_path: Path) -> None:
    path = tmp_path / "split.jsonl"
    _write_split_jsonl(path)
    result = run_census(path)
    assert result.vacuity_semantic_pending_count == 3
    assert result.vacuity_weak_directive_count == 1
    assert result.vacuity_not_a_directive_count == 1
    assert result.vacuity_kind_unspecified_count == 1
    # Conditions must not collapse into the combined total alone.
    assert result.vacuity_weak_directive_count != result.vacuity_semantic_pending_count
    assert result.vacuity_not_a_directive_count != result.vacuity_semantic_pending_count

    receipt = result.to_receipt()
    pending = receipt["vacuity_flag_tally"]["unreviewed"]["semantic_vacuous_pending_review"]
    by_kind = pending["by_kind"]
    assert by_kind["weak_directive"]["count"] == 1
    assert by_kind["not_a_directive"]["count"] == 1
    assert by_kind["unspecified"]["count"] == 1
    assert pending["count"] == 3
    # No lone combined total without the breakdown.
    assert "by_kind" in pending

    human = format_human_report(result)
    assert "weak_directive: 1" in human
    assert "not_a_directive: 1" in human
    # Combined line may exist, but each condition line must be present.
    assert "semantic_vacuous_pending_review: 3" in human


def test_census_conditions_do_not_collapse_in_legacy_fixture() -> None:
    """Legacy rows without vacuity_kind still expose separate kind buckets."""
    result = run_census(_FIXTURES / "current_gen.jsonl")
    assert result.vacuity_semantic_pending_count == 1
    # Current fixture has no vacuity_kind → unspecified bucket, not a collapse.
    assert result.vacuity_kind_unspecified_count == 1
    assert result.vacuity_weak_directive_count == 0
    assert result.vacuity_not_a_directive_count == 0
    receipt = result.to_receipt()
    by_kind = receipt["vacuity_flag_tally"]["unreviewed"]["semantic_vacuous_pending_review"][
        "by_kind"
    ]
    assert set(by_kind) == {"weak_directive", "not_a_directive", "unspecified"}


# ---------------------------------------------------------------------------
# Storage layer: vacuity_flag values / CHECK unchanged; no new column
# ---------------------------------------------------------------------------


def test_storage_vacuity_flag_check_unchanged() -> None:
    sql = (_REPO / "src/skill_harness/storage/migrations_sql/evidence/0001_initial.sql").read_text(
        encoding="utf-8"
    )
    assert (
        "CHECK (vacuity_flag IN "
        "('none','mechanical_vacuous','semantic_vacuous_pending_review'))" in sql
    )
    assert "vacuity_kind" not in sql
    # No storage-layer module should grow a vacuity_kind column from this ticket.
    storage_root = _REPO / "src" / "skill_harness" / "storage"
    offenders = [
        p
        for p in storage_root.rglob("*")
        if p.is_file() and "vacuity_kind" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
