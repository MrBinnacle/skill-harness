"""Tests for JudgeClient SDK call shape (A31).

Verifies:
- tool_use strict schema is sent (strict=True, additionalProperties=False)
- tool_choice={"type":"tool","name":"report_verdict"} is forced
- thinking={"type":"disabled"} is sent
- max_tokens fits the tool schema's own worst-case output (C1 fix; was a
  hardcoded 80 that could not fit rationale_brief's maxLength=500 contract)
- model default is claude-sonnet-4-6
- judge_id() returns sha256(model_id||system_prompt_sha256||tool_schema_sha256)
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from skill_harness.oracles.tier2.judge import JudgeClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_create_kwargs(mock_client: MagicMock) -> dict[str, Any]:
    """Extract keyword args from the first call to mock_client.messages.create."""
    assert mock_client.messages.create.called, "messages.create was not called"
    return cast("dict[str, Any]", mock_client.messages.create.call_args[1])


# ---------------------------------------------------------------------------
# SDK call shape tests
# ---------------------------------------------------------------------------


def test_judge_uses_tool_choice_forced(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """tool_choice must force the report_verdict tool."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    assert kwargs["tool_choice"] == {"type": "tool", "name": "report_verdict"}


def test_judge_uses_max_tokens_fits_schema_worst_case(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """max_tokens must be >= the tool schema's own worst-case output (C1 fix).

    Regression for C1: max_tokens=80 could not fit rationale_brief's own
    maxLength=500-char contract (worst-case ~1 token/char + JSON envelope
    overhead), causing legitimate verbose verdicts to truncate and be
    recorded as inadmissible 'judge_response_malformed'.
    """
    from skill_harness.oracles.tier2.judge import _TOOL_SCHEMA

    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)

    rationale_max_chars = _TOOL_SCHEMA["input_schema"]["properties"]["rationale_brief"]["maxLength"]
    # Conservative worst-case bound: 1 token per char (denser than any realistic
    # tokenizer output) plus a generous fixed JSON envelope allowance.
    worst_case_floor = rationale_max_chars + 40
    assert kwargs["max_tokens"] >= worst_case_floor
    assert kwargs["max_tokens"] == 560  # pins the exact derived value (500 + 60)


def test_judge_disables_thinking(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """thinking must be disabled (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    assert kwargs["thinking"] == {"type": "disabled"}


def test_judge_tool_schema_has_strict_true(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """Tool schema must have strict=True (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    tools = kwargs["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["strict"] is True


def test_judge_tool_schema_has_no_additional_properties(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """input_schema must have additionalProperties=False (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    tool = kwargs["tools"][0]
    schema = tool["input_schema"]
    assert schema["additionalProperties"] is False


def test_judge_tool_schema_choice_enum(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """choice must be an enum of exactly ['A', 'B', 'tie'] (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    tool = kwargs["tools"][0]
    choice_prop = tool["input_schema"]["properties"]["choice"]
    assert choice_prop["type"] == "string"
    assert set(choice_prop["enum"]) == {"A", "B", "tie"}


def test_judge_tool_schema_rationale_brief_max_length(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """rationale_brief must have maxLength=500 (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    tool = kwargs["tools"][0]
    rationale_prop = tool["input_schema"]["properties"]["rationale_brief"]
    assert rationale_prop.get("maxLength") == 500


def test_judge_tool_name_is_report_verdict(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """Tool name must be 'report_verdict' (A31)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    tool = kwargs["tools"][0]
    assert tool["name"] == "report_verdict"


def test_judge_default_model_is_sonnet_4_6(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """Default model must be claude-sonnet-4-6 (model-pinning convention)."""
    judge_client.evaluate_pair("output A", "output B", "clarity", "rate clarity")
    kwargs = _get_create_kwargs(mock_anthropic_client)
    assert kwargs["model"] == "claude-sonnet-4-6"


def test_judge_id_is_sha256_of_model_and_prompts() -> None:
    """judge_id() == sha256(model_id || system_prompt_sha256 || tool_schema_sha256)."""
    from skill_harness.oracles.tier2.judge import JudgeClient

    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        stop_reason="tool_use",
        content=[
            MagicMock(
                type="tool_use",
                name="report_verdict",
                input={"choice": "A", "rationale_brief": "x"},
            )
        ],
    )
    jc = JudgeClient(client=client)

    model_id = "claude-sonnet-4-6"
    # judge_id() uses canonical empty-output call: _build_prompt("", "", "axis", "rubric")
    system_prompt, tool_schema = jc._build_prompt("", "", "axis", "rubric")

    system_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    schema_bytes = json.dumps(tool_schema, sort_keys=True).encode("utf-8")
    schema_sha = hashlib.sha256(schema_bytes).hexdigest()
    combined = (model_id + system_sha + schema_sha).encode("utf-8")
    expected = hashlib.sha256(combined).hexdigest()

    assert jc.judge_id(model_id) == expected


def test_judge_id_changes_with_model() -> None:
    """judge_id() differs for different model_ids (instrument identity per A31)."""
    from skill_harness.oracles.tier2.judge import JudgeClient

    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        stop_reason="tool_use",
        content=[
            MagicMock(
                type="tool_use",
                name="report_verdict",
                input={"choice": "A", "rationale_brief": "x"},
            )
        ],
    )
    jc = JudgeClient(client=client)
    id1 = jc.judge_id("claude-sonnet-4-6")
    id2 = jc.judge_id("claude-opus-4-7")
    assert id1 != id2


def test_length_fields_use_canonical_tokenizer(
    judge_client: JudgeClient, mock_anthropic_client: MagicMock
) -> None:
    """F4 regression: JudgeVerdict.length_a/length_b must match the canonical
    cl100k_base counter (tier1/verbosity.count_tokens) exactly. judge.py used
    to re-implement tiktoken.get_encoding('cl100k_base') locally in its own
    _count_tokens(); it now imports the tier1 counter directly."""
    from skill_harness.oracles.tier1.verbosity import count_tokens

    output_a = "a short output"
    output_b = "a rather longer output with more words in it"
    verdict = judge_client.evaluate_pair(output_a, output_b, "clarity", "rate clarity")
    assert verdict.length_a == count_tokens(output_a)
    assert verdict.length_b == count_tokens(output_b)
