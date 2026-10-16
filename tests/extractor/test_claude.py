"""Tests for skill_harness.extractor.claude (mocked API calls)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skill_harness.extractor.claude import call_extract_clauses
from skill_harness.extractor.errors import ExtractorClaudeError


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the direct-Anthropic auth path regardless of host environment.

    These are mocked-SDK unit tests, but ``_make_extractor_client`` resolves auth
    from env BEFORE the mocked client is constructed — with no key (CI) every test
    raised ExtractorClaudeError; with a real OPENROUTER_API_KEY (a dev machine) the
    fallback path would silently swap the model id under test.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


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
    vacuity_kind: str | None = None,
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
    else:
        base["vacuity_kind"] = vacuity_kind if vacuity_kind is not None else "weak_directive"
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

    clauses, instrument = call_extract_clauses("Some skill body text.")
    assert len(clauses) == 1
    assert clauses[0].clause_index == 0
    assert clauses[0].axis == "specificity"
    assert instrument.model_id == "claude-opus-5"
    assert len(instrument.system_prompt_sha256) == 64
    assert len(instrument.tool_schema_sha256) == 64


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_api_call_uses_strict_tool_and_no_sampling_params(
    mock_anthropic_cls: MagicMock,
) -> None:
    """Strict tool use is the enforced schema contract; Opus 5 rejects sampling knobs."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
    )

    call_extract_clauses("Some skill body text.")

    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["max_tokens"] == 16000
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs
    tools = kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "extract_clauses"
    assert tools[0]["strict"] is True


@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_returns_multiple_clauses(mock_anthropic_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(i) for i in range(5)]})]
    )

    clauses, _instrument = call_extract_clauses("Body text.")
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

    clauses, _instrument = call_extract_clauses("Vague skill.")
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
def test_partial_validation_failure_raises(mock_anthropic_cls: MagicMock) -> None:
    """Any per-clause validation failure aborts the whole extraction.

    Silent drop would record fewer clauses in evidence than source_sha256
    attests, corrupting Coverage/Contribution metrics.
    """
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    invalid_raw: dict[str, Any] = {
        "clause_index": 1,
        "clause_text": "Something",
        "axis": "formality",
        "comparator": "increase",
        "oracle_tier": 1,
        "vacuity_flag": "none",
        # Incomplete falsifying_case — empty required field still fails (#136 keeps
        # FalsifyingCaseSchema strict; only the vacuity coupling was removed).
        "falsifying_case": {
            "input_population_spec": "",
            "expected_directional_pair": "A beats B",
            "min_reproducibility": 0.5,
        },
    }

    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [_valid_raw_clause(0), invalid_raw]})]
    )

    with pytest.raises(ExtractorClaudeError, match="1 of 2 clauses failed validation"):
        call_extract_clauses("Body.")


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
        "falsifying_case": {
            "input_population_spec": "pop",
            "expected_directional_pair": "pair",
            "min_reproducibility": 0.0,  # out of range — still rejected
        },
    }

    mock_client.messages.create.return_value = _make_response(
        [_make_tool_use_block({"clauses": [invalid_raw]})]
    )

    with pytest.raises(ExtractorClaudeError, match="failed validation"):
        call_extract_clauses("Body.")


# ---------------------------------------------------------------------------
# call_extract_clauses — retry on transient 'clauses field of unexpected type: str'
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.time.sleep")
@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_retries_once_on_clauses_field_unexpected_type_str(
    mock_anthropic_cls: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """First call returns 'clauses' as a str (transient anomaly); second call succeeds.

    The extractor must retry exactly once and return the clauses from the
    second call.  One retry is the bounded scope per the punch-list spec.
    """
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    # First response: 'clauses' is a string — the observed transient anomaly
    bad_response = _make_response([_make_tool_use_block({"clauses": "unexpected string content"})])
    # Second response: valid
    good_response = _make_response([_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})])
    mock_client.messages.create.side_effect = [bad_response, good_response]

    clauses, _instrument = call_extract_clauses("Some skill body text.")
    assert len(clauses) == 1
    assert clauses[0].clause_index == 0
    assert mock_client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)


@patch("skill_harness.extractor.claude.time.sleep")
@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_no_retry_flag_raises_immediately_on_clauses_field_str(
    mock_anthropic_cls: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """With no_retry=True the error propagates on the first call without a retry."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    bad_response = _make_response([_make_tool_use_block({"clauses": "unexpected string content"})])
    mock_client.messages.create.return_value = bad_response

    with pytest.raises(ExtractorClaudeError, match="unexpected type"):
        call_extract_clauses("Some body.", no_retry=True)

    assert mock_client.messages.create.call_count == 1
    mock_sleep.assert_not_called()


@patch("skill_harness.extractor.claude.time.sleep")
@patch("skill_harness.extractor.claude.anthropic.Anthropic")
def test_retry_exhausted_raises_after_two_calls(
    mock_anthropic_cls: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    """When both calls return the transient error, the second raises ExtractorClaudeError."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    bad_response = _make_response([_make_tool_use_block({"clauses": "unexpected string content"})])
    mock_client.messages.create.return_value = bad_response

    with pytest.raises(ExtractorClaudeError, match="unexpected type"):
        call_extract_clauses("Some body.")

    assert mock_client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1)
