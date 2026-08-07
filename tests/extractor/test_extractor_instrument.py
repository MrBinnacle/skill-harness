"""Extractor instrument identity (#135).

Pins:
- every ExtractionResult carries model + prompt hash + tool-schema hash
- hashes are taken from the strings actually sent on the API request
- editing the prompt text changes the recorded prompt hash
- compare_extractor_generations reports different when only prompt hash differs
- legacy corpus rows lacking the triple are generation-unknown (no crash)
- corpus readers refuse to merge distinct generations into one figure
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skill_harness.extractor.claude import (
    _EXTRACT_CLAUSES_SCHEMA,
    _SYSTEM_PROMPT,
    _call_once,
    _extract_clauses_tools,
    _instrument_from_request,
    call_extract_clauses,
)
from skill_harness.extractor.corpus_census import run_census
from skill_harness.extractor.corpus_coverage import run_coverage
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    ExtractorInstrument,
    FalsifyingCaseSchema,
    compare_extractor_generations,
    instrument_from_mapping,
)
from skill_harness.extractor.pipeline import extract_skill


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


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


def _valid_raw_clause(index: int = 0) -> dict[str, Any]:
    return {
        "clause_index": index,
        "clause_text": f"Clause text {index}",
        "axis": "specificity",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        "falsifying_case": {
            "input_population_spec": "Factual questions",
            "expected_directional_pair": "A more specific than B",
            "min_reproducibility": 0.75,
        },
    }


def _expected_prompt_sha(system: str) -> str:
    return hashlib.sha256(system.encode("utf-8")).hexdigest()


def _expected_schema_sha(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Hashes from actual request strings
# ---------------------------------------------------------------------------


def test_instrument_hashes_match_request_payload_strings() -> None:
    """Hashes must equal sha256 of the exact system/tools values sent."""
    system = _SYSTEM_PROMPT
    tools = _extract_clauses_tools()
    instrument = _instrument_from_request("claude-opus-5", system, tools)
    assert instrument.system_prompt_sha256 == _expected_prompt_sha(system)
    assert instrument.tool_schema_sha256 == _expected_schema_sha(tools[0]["input_schema"])
    assert instrument.tool_schema_sha256 == _expected_schema_sha(_EXTRACT_CLAUSES_SCHEMA)


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_call_extract_clauses_records_hashes_of_kwargs_sent(
    mock_anthropic_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
    )

    _clauses, instrument = call_extract_clauses("body")

    kwargs = mock_client.messages.create.call_args.kwargs
    assert instrument.system_prompt_sha256 == _expected_prompt_sha(kwargs["system"])
    assert instrument.tool_schema_sha256 == _expected_schema_sha(kwargs["tools"][0]["input_schema"])
    assert instrument.model_id == kwargs["model"]


def test_editing_prompt_text_changes_recorded_hash() -> None:
    tools = _extract_clauses_tools()
    base = _instrument_from_request("claude-opus-5", _SYSTEM_PROMPT, tools)
    edited = _instrument_from_request(
        "claude-opus-5",
        _SYSTEM_PROMPT + "\n# one-character edit marker\n",
        tools,
    )
    assert base.system_prompt_sha256 != edited.system_prompt_sha256
    assert base.tool_schema_sha256 == edited.tool_schema_sha256
    assert base.model_id == edited.model_id


def test_editing_tool_schema_changes_recorded_hash() -> None:
    tools_a = _extract_clauses_tools()
    tools_b = _extract_clauses_tools()
    # Mutate a copy of the schema object graph as would happen if the schema
    # definition changed before the request is built.
    tools_b[0] = dict(tools_b[0])
    schema_b = dict(tools_b[0]["input_schema"])
    schema_b["description"] = "edited schema marker"
    tools_b[0]["input_schema"] = schema_b
    a = _instrument_from_request("claude-opus-5", _SYSTEM_PROMPT, tools_a)
    b = _instrument_from_request("claude-opus-5", _SYSTEM_PROMPT, tools_b)
    assert a.tool_schema_sha256 != b.tool_schema_sha256


# ---------------------------------------------------------------------------
# ExtractionResult carries the triple on every row
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_extract_skill_result_carries_full_instrument_triple(
    mock_anthropic_cls: MagicMock,
    tmp_path: Path,
) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
    )
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: pin-test\n---\n\n# Be specific.\n", encoding="utf-8")

    result = extract_skill(skill, evidence_conn=None)

    assert isinstance(result, ExtractionResult)
    assert result.extractor_model == "claude-opus-5"
    assert len(result.system_prompt_sha256) == 64
    assert len(result.tool_schema_sha256) == 64
    # Hashes match the live request kwargs, not a constant.
    kwargs = mock_client.messages.create.call_args.kwargs
    assert result.system_prompt_sha256 == _expected_prompt_sha(kwargs["system"])
    assert result.tool_schema_sha256 == _expected_schema_sha(kwargs["tools"][0]["input_schema"])
    assert result.instrument().model_id == result.extractor_model


def test_extraction_result_requires_instrument_fields() -> None:
    """Fields are required — optional None would restore the ambiguity #135 removes."""
    clause = ExtractedClause(
        clause_index=0,
        clause_text="x",
        axis="specificity",
        comparator="increase",
        oracle_tier=1,
        vacuity_flag="none",
        falsifying_case=FalsifyingCaseSchema(
            input_population_spec="p",
            expected_directional_pair="A>B",
            min_reproducibility=0.5,
        ),
    )
    with pytest.raises(Exception):
        ExtractionResult(  # type: ignore[call-arg]
            skill_id="a" * 64,
            name="n",
            source_path="/x",
            source_sha256="a" * 64,
            clauses=[clause],
            raw_frontmatter={},
            extractor_model="claude-opus-5",
        )


# ---------------------------------------------------------------------------
# Generation comparison helper
# ---------------------------------------------------------------------------


def test_compare_same_generation() -> None:
    a = ExtractorInstrument(
        model_id="claude-opus-5",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    b = ExtractorInstrument(
        model_id="claude-opus-5",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    assert compare_extractor_generations(a, b) == "same"
    assert a.same_generation_as(b)


def test_compare_different_when_only_prompt_hash_differs() -> None:
    """Negative case: prompt-only drift is a different generation."""
    a = ExtractorInstrument(
        model_id="claude-opus-5",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    b = ExtractorInstrument(
        model_id="claude-opus-5",
        system_prompt_sha256="d" * 64,
        tool_schema_sha256="c" * 64,
    )
    assert compare_extractor_generations(a, b) == "different"
    assert not a.same_generation_as(b)


def test_compare_unknown_when_either_side_missing() -> None:
    known = ExtractorInstrument(
        model_id="claude-opus-5",
        system_prompt_sha256="b" * 64,
        tool_schema_sha256="c" * 64,
    )
    assert compare_extractor_generations(None, known) == "unknown"
    assert compare_extractor_generations(known, None) == "unknown"
    assert compare_extractor_generations(None, None) == "unknown"


def test_instrument_from_mapping_legacy_row_is_unknown() -> None:
    """Legacy rows lack prompt/schema hashes → generation-unknown, no crash."""
    row = {
        "slug": "legacy-skill",
        "ok": True,
        "extractor_model": "claude-opus-5",
        "clauses": [],
    }
    assert instrument_from_mapping(row) is None
    assert compare_extractor_generations(instrument_from_mapping(row), None) == "unknown"


def test_instrument_from_mapping_complete_triple() -> None:
    row = {
        "extractor_model": "claude-opus-5",
        "system_prompt_sha256": "b" * 64,
        "tool_schema_sha256": "c" * 64,
    }
    inst = instrument_from_mapping(row)
    assert inst is not None
    assert inst.model_id == "claude-opus-5"


# ---------------------------------------------------------------------------
# Corpus readers: legacy + mixed generations
# ---------------------------------------------------------------------------


def test_legacy_corpus_reads_as_generation_unknown(tmp_path: Path) -> None:
    """Existing fixtures without hash fields must not crash; status=unknown."""
    path = tmp_path / "legacy.jsonl"
    path.write_text(
        json.dumps(
            {
                "slug": "skill-a",
                "ok": True,
                "extractor_model": "claude-opus-5",
                "clauses": [
                    {
                        "clause_index": 0,
                        "clause_text": "be verbose",
                        "axis": "verbosity",
                        "comparator": "increase",
                        "oracle_tier": 1,
                        "vacuity_flag": "none",
                        "falsifying_case": {
                            "input_population_spec": "short",
                            "expected_directional_pair": "A>B",
                            "min_reproducibility": 0.8,
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    census = run_census(path)
    assert census.extractor_generation_status == "unknown"
    assert census.extractor_generation_reason is not None
    assert "unknown" in census.extractor_generation_reason
    assert census.system_prompt_sha256 is None
    assert census.tool_schema_sha256 is None
    assert census.corpus_figures_status == "measured"
    assert census.total_clauses == 1

    coverage = run_coverage(path)
    assert coverage.extractor_generation_status == "unknown"
    assert coverage.corpus_constructible.status == "measured"


def test_mixed_generations_refuse_corpus_merge(tmp_path: Path) -> None:
    """Two rows differing only in prompt hash → refuse blended corpus figure."""
    path = tmp_path / "mixed.jsonl"
    base_clause = {
        "clause_index": 0,
        "clause_text": "be verbose",
        "axis": "verbosity",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        "falsifying_case": {
            "input_population_spec": "short",
            "expected_directional_pair": "A>B",
            "min_reproducibility": 0.8,
        },
    }
    row_a = {
        "slug": "skill-a",
        "ok": True,
        "extractor_model": "claude-opus-5",
        "system_prompt_sha256": "b" * 64,
        "tool_schema_sha256": "c" * 64,
        "clauses": [base_clause],
    }
    row_b = {
        "slug": "skill-b",
        "ok": True,
        "extractor_model": "claude-opus-5",
        "system_prompt_sha256": "d" * 64,  # prompt-only drift
        "tool_schema_sha256": "c" * 64,
        "clauses": [base_clause],
    }
    path.write_text(
        json.dumps(row_a) + "\n" + json.dumps(row_b) + "\n",
        encoding="utf-8",
    )

    # Helper: these two rows are different generations.
    assert (
        compare_extractor_generations(
            instrument_from_mapping(row_a),
            instrument_from_mapping(row_b),
        )
        == "different"
    )

    census = run_census(path)
    assert census.extractor_generation_status == "mixed"
    assert census.corpus_figures_status == "refused"
    assert census.corpus_figures_reason is not None
    assert "mixed_extractor_generations" in census.corpus_figures_reason
    # Per-skill still available; corpus blend refused.
    assert len(census.per_skill) == 2
    assert census.falsifying_case_status == "refused"
    # Blended tallies must not look like a single measured figure.
    assert census.scoreable_axis_count == 0
    assert census.comparator_specified_count == 0

    coverage = run_coverage(path)
    assert coverage.extractor_generation_status == "mixed"
    assert coverage.corpus_constructible.status == "refused"
    assert coverage.corpus_instantiated.status == "refused"
    assert "mixed_extractor_generations" in (coverage.corpus_constructible.reason or "")
    # No percent on refused corpus figures.
    assert "percent" not in coverage.corpus_constructible.to_receipt()
    # Per-skill still measured individually.
    assert all(r.constructible.status == "measured" for r in coverage.per_skill)


def test_same_generation_corpus_merges(tmp_path: Path) -> None:
    path = tmp_path / "same.jsonl"
    clause = {
        "clause_index": 0,
        "clause_text": "be verbose",
        "axis": "verbosity",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        "falsifying_case": {
            "input_population_spec": "short",
            "expected_directional_pair": "A>B",
            "min_reproducibility": 0.8,
        },
    }
    triple = {
        "extractor_model": "claude-opus-5",
        "system_prompt_sha256": "b" * 64,
        "tool_schema_sha256": "c" * 64,
    }
    rows = [
        {"slug": "a", "ok": True, **triple, "clauses": [clause]},
        {"slug": "b", "ok": True, **triple, "clauses": [clause]},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    census = run_census(path)
    assert census.extractor_generation_status == "known"
    assert census.corpus_figures_status == "measured"
    assert census.system_prompt_sha256 == "b" * 64
    assert census.tool_schema_sha256 == "c" * 64
    assert census.total_clauses == 2
    coverage = run_coverage(path)
    assert coverage.corpus_constructible.status == "measured"
    assert coverage.corpus_constructible.numerator == 2


def test_call_once_shares_system_and_tools_with_instrument() -> None:
    """Trap guard: instrument and messages.create use the same objects."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
    )
    system = _SYSTEM_PROMPT
    tools = _extract_clauses_tools()
    instrument = _instrument_from_request("claude-opus-5", system, tools)
    _call_once(mock_client, "body", "claude-opus-5", system, tools)
    kwargs = mock_client.messages.create.call_args.kwargs
    # Identity: same objects passed through (not re-read constants).
    assert kwargs["system"] is system
    assert kwargs["tools"] is tools
    assert instrument.system_prompt_sha256 == _expected_prompt_sha(kwargs["system"])
