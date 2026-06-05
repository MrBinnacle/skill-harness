"""Tests for skill_harness.extractor.claude (mocked API calls)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skill_harness.extractor.claude import call_extract_clauses
from skill_harness.extractor.errors import ExtractorClaudeError

# ---------------------------------------------------------------------------
# Helpers to build fake Anthropic response objects
# ---------------------------------------------------------------------------


def _make_tool_use_block(input_data: dict[str, Any]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_clauses"
    block.input = input_data
    return block


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_response(
    content: list[MagicMock],
    stop_reason: str = "tool_use",
) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.stop_reason = stop_reason
    return resp


def _valid_raw_clause(
    index: int = 0,
    vacuity_flag: str = "none",
    comparator: str = "increase",
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "clause_index": index,
        "clause_text": f"Clause text {index}",
        "axis": "specificity",
        "comparator": comparator,
        "oracle_tier": 1,
        "vacuity_flag": vacuity_flag,
    }
    if vacuity_flag == "none":
        base["falsifying_case"] = {
            "input_population_spec": "Factual questions requiring specific answers",
            "expected_directional_pair": "A more specific than B",
            "min_reproducibility": 0.75,
        }
    return base


# ---------------------------------------------------------------------------
# call_extract_clauses — happy path
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_returns_clauses_on_success(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
    )

    clauses = call_extract_clauses("Some skill body text.")
    assert len(clauses) == 1
    assert clauses[0].clause_index == 0
    assert clauses[0].axis == "specificity"


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_returns_multiple_clauses(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(i) for i in range(5)]})]
    )

    clauses = call_extract_clauses("Body text.")
    assert len(clauses) == 5


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_handles_semantic_vacuous_clause(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [
            _make_tool_use_block(
                {
                    "clauses": [
                        _valid_raw_clause(
                            0,
                            vacuity_flag="semantic_vacuous_pending_review",
                            comparator="comparator_unspecified",
                        )
                    ]
                }
            )
        ]
    )

    clauses = call_extract_clauses("Vague skill.")
    assert len(clauses) == 1
    assert clauses[0].vacuity_flag == "semantic_vacuous_pending_review"
    assert clauses[0].falsifying_case is None


# ---------------------------------------------------------------------------
# call_extract_clauses — no tool_use block
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_raises_when_no_tool_use_block(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_text_block("Sorry, I cannot do that.")],
        stop_reason="end_turn",
    )

    with pytest.raises(ExtractorClaudeError, match="did not call the extract_clauses tool"):
        call_extract_clauses("Some body.")


# ---------------------------------------------------------------------------
# call_extract_clauses — empty clauses list
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_raises_when_clauses_list_empty(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": []})]
    )

    with pytest.raises(ExtractorClaudeError, match="zero clauses"):
        call_extract_clauses("Some body.")


# ---------------------------------------------------------------------------
# call_extract_clauses — API error propagation
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_raises_extractor_claude_error_on_api_error(mock_anthropic_cls: MagicMock) -> None:
    import anthropic as sdk

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = sdk.APIConnectionError(request=MagicMock())

    with pytest.raises(ExtractorClaudeError, match="Anthropic API error"):
        call_extract_clauses("Some body.")


# ---------------------------------------------------------------------------
# call_extract_clauses — partial validation failure
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_partial_validation_failure_returns_valid_subset(mock_anthropic_cls: MagicMock) -> None:
    """When some clauses fail validation but at least one passes, return the valid ones."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    invalid_raw: dict[str, Any] = {
        "clause_index": 1,
        "clause_text": "Something",
        "axis": "formality",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        # Missing falsifying_case — should fail validation
    }

    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0), invalid_raw]})]
    )

    clauses = call_extract_clauses("Body.")
    assert len(clauses) == 1
    assert clauses[0].clause_index == 0


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_all_clauses_fail_validation_raises(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    invalid_raw: dict[str, Any] = {
        "clause_index": 0,
        "clause_text": "Something",
        "axis": "formality",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        # Missing falsifying_case
    }

    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [invalid_raw]})]
    )

    with pytest.raises(ExtractorClaudeError, match="failed validation"):
        call_extract_clauses("Body.")
