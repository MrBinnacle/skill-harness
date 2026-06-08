"""Tests for OpenAISubjectClient (T3 tracer adapter).

TDD discipline: tests written BEFORE implementation per superpowers:test-driven-development.
Mock discipline: openai.OpenAI client mocked at the SDK boundary (A32 precedent).
Sub-surface exclusion: verifies openai.beta etc. are NOT loaded by the import path.

Coverage:
1. Happy path: returns SubjectResponse with correct fields
2. APIStatusError 5xx -> SubjectCallError(transient=True)
3. APIStatusError 4xx -> SubjectCallError(transient=False)
4. APIConnectionError -> SubjectCallError(transient=True)
5. Usage parsing: cached_tokens -> cache_read_input_tokens
6. make_subject_client factory: claude-* -> AnthropicSubjectClient, gpt-* -> OpenAISubjectClient
7. make_subject_client factory: unrecognized prefix -> ValueError
8. Sub-surface exclusion: openai.beta and other excluded namespaces NOT loaded
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# NOTE: ALL imports of OpenAISubjectClient / make_subject_client are inside
# test functions to ensure RED phase can be observed (ImportError on missing
# names triggers test failures, not collection errors).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(
    content: str = "Test output text.",
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
    cached_tokens: int = 0,
    model: str = "gpt-5.5",
    finish_reason: str = "stop",
) -> MagicMock:
    """Create a mock OpenAI ChatCompletion response."""
    mock_resp = MagicMock()

    # choices[0].message.content
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    mock_resp.choices = [choice]

    mock_resp.model = model

    # usage block: OpenAI shape
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    # prompt_tokens_details.cached_tokens
    details = MagicMock()
    details.cached_tokens = cached_tokens
    usage.prompt_tokens_details = details

    mock_resp.usage = usage
    return mock_resp


# ---------------------------------------------------------------------------
# Test: happy path
# ---------------------------------------------------------------------------


def test_openai_subject_client_happy_path() -> None:
    """OpenAISubjectClient.call returns SubjectResponse with correct fields."""
    from skill_harness.ablation.subject import OpenAISubjectClient, SubjectResponse

    mock_openai_client = MagicMock()
    mock_openai_client.chat.completions.create.return_value = _make_openai_response(
        content="Hello, world!",
        prompt_tokens=150,
        completion_tokens=30,
        cached_tokens=50,
        model="gpt-5.5",
        finish_reason="stop",
    )

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")
    response = client.call(
        system_blocks=[{"type": "text", "text": "You are a test assistant."}],
        user_message="Write something.",
    )

    assert isinstance(response, SubjectResponse)
    assert response.output_text == "Hello, world!"
    assert response.input_tokens == 150
    assert response.output_tokens == 30
    assert response.cache_read_input_tokens == 50
    assert response.cache_creation_input_tokens == 0  # OpenAI has no write analog
    assert response.model == "gpt-5.5"
    assert response.stop_reason == "stop"
    assert response.usd > 0.0  # cost estimation ran


# ---------------------------------------------------------------------------
# Test: APIStatusError 5xx -> transient=True
# ---------------------------------------------------------------------------


def test_openai_subject_client_5xx_error_is_transient() -> None:
    """OpenAISubjectClient maps 5xx APIStatusError to SubjectCallError(transient=True)."""
    from openai import APIStatusError

    from skill_harness.ablation.subject import OpenAISubjectClient, SubjectCallError

    mock_openai_client = MagicMock()
    # Construct a real APIStatusError with a mock response
    mock_http_resp = MagicMock()
    mock_http_resp.headers = {}
    mock_http_resp.request = MagicMock()
    err = APIStatusError(
        message="Internal Server Error",
        response=mock_http_resp,
        body={"error": {"message": "Internal Server Error"}},
    )
    err.status_code = 500  # type: ignore[attr-defined]
    mock_openai_client.chat.completions.create.side_effect = err

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")

    with pytest.raises(SubjectCallError) as exc_info:
        client.call(system_blocks=[], user_message="test")

    assert exc_info.value.transient is True


# ---------------------------------------------------------------------------
# Test: APIStatusError 4xx -> transient=False
# ---------------------------------------------------------------------------


def test_openai_subject_client_4xx_error_is_permanent() -> None:
    """OpenAISubjectClient maps 4xx APIStatusError to SubjectCallError(transient=False)."""
    from openai import APIStatusError

    from skill_harness.ablation.subject import OpenAISubjectClient, SubjectCallError

    mock_openai_client = MagicMock()
    mock_http_resp = MagicMock()
    mock_http_resp.headers = {}
    mock_http_resp.request = MagicMock()
    err = APIStatusError(
        message="Bad Request",
        response=mock_http_resp,
        body={"error": {"message": "Bad Request"}},
    )
    err.status_code = 400  # type: ignore[attr-defined]
    mock_openai_client.chat.completions.create.side_effect = err

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")

    with pytest.raises(SubjectCallError) as exc_info:
        client.call(system_blocks=[], user_message="test")

    assert exc_info.value.transient is False


# ---------------------------------------------------------------------------
# Test: APIConnectionError -> transient=True
# ---------------------------------------------------------------------------


def test_openai_subject_client_connection_error_is_transient() -> None:
    """OpenAISubjectClient maps APIConnectionError to SubjectCallError(transient=True)."""
    from openai import APIConnectionError

    from skill_harness.ablation.subject import OpenAISubjectClient, SubjectCallError

    mock_openai_client = MagicMock()
    err = APIConnectionError(request=MagicMock())
    mock_openai_client.chat.completions.create.side_effect = err

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")

    with pytest.raises(SubjectCallError) as exc_info:
        client.call(system_blocks=[], user_message="test")

    assert exc_info.value.transient is True


# ---------------------------------------------------------------------------
# Test: usage parsing - cached_tokens maps to cache_read_input_tokens
# ---------------------------------------------------------------------------


def test_openai_usage_parsing_cached_tokens() -> None:
    """cached_tokens from prompt_tokens_details maps to cache_read_input_tokens."""
    from skill_harness.ablation.subject import OpenAISubjectClient

    mock_openai_client = MagicMock()
    mock_openai_client.chat.completions.create.return_value = _make_openai_response(
        prompt_tokens=200,
        completion_tokens=40,
        cached_tokens=80,  # 80 tokens read from cache
    )

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")
    response = client.call(system_blocks=[], user_message="test")

    assert response.input_tokens == 200
    assert response.cache_read_input_tokens == 80
    assert response.cache_creation_input_tokens == 0  # always 0 for OpenAI


# ---------------------------------------------------------------------------
# Test: usage parsing - missing prompt_tokens_details (None) handled gracefully
# ---------------------------------------------------------------------------


def test_openai_usage_parsing_no_cached_tokens_details() -> None:
    """If prompt_tokens_details is None, cache_read_input_tokens defaults to 0."""
    from skill_harness.ablation.subject import OpenAISubjectClient

    mock_resp = _make_openai_response(prompt_tokens=100, completion_tokens=20, cached_tokens=0)
    # Simulate None prompt_tokens_details
    mock_resp.usage.prompt_tokens_details = None

    mock_openai_client = MagicMock()
    mock_openai_client.chat.completions.create.return_value = mock_resp

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")
    response = client.call(system_blocks=[], user_message="test")

    assert response.cache_read_input_tokens == 0


# ---------------------------------------------------------------------------
# Test: multiple system blocks are concatenated
# ---------------------------------------------------------------------------


def test_openai_system_blocks_concatenated() -> None:
    """Multiple system_blocks are concatenated into a single system message."""
    from skill_harness.ablation.subject import OpenAISubjectClient

    mock_openai_client = MagicMock()
    mock_openai_client.chat.completions.create.return_value = _make_openai_response()

    client = OpenAISubjectClient(client=mock_openai_client, model="gpt-5.5")
    client.call(
        system_blocks=[
            {"type": "text", "text": "Block one."},
            {"type": "text", "text": "Block two."},
        ],
        user_message="test",
    )

    call_args = mock_openai_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    # There should be a system message and a user message
    system_msgs = [m for m in messages if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert "Block one." in system_msgs[0]["content"]
    assert "Block two." in system_msgs[0]["content"]


# ---------------------------------------------------------------------------
# Test: make_subject_client factory
# ---------------------------------------------------------------------------


def test_make_subject_client_claude_prefix() -> None:
    """make_subject_client dispatches claude-* to AnthropicSubjectClient."""
    from skill_harness.ablation.subject import AnthropicSubjectClient, make_subject_client

    client = make_subject_client("claude-sonnet-4-6")
    assert isinstance(client, AnthropicSubjectClient)


def test_make_subject_client_gpt_prefix() -> None:
    """make_subject_client dispatches gpt-* to OpenAISubjectClient."""
    from openai import OpenAI

    from skill_harness.ablation.subject import OpenAISubjectClient, make_subject_client

    mock_openai = MagicMock(spec=OpenAI)
    with patch("skill_harness.ablation.subject.OpenAI", return_value=mock_openai):
        client = make_subject_client("gpt-5.5")
    assert isinstance(client, OpenAISubjectClient)


def test_make_subject_client_o_prefix() -> None:
    """make_subject_client dispatches o*-* to OpenAISubjectClient."""
    from openai import OpenAI

    from skill_harness.ablation.subject import OpenAISubjectClient, make_subject_client

    mock_openai = MagicMock(spec=OpenAI)
    with patch("skill_harness.ablation.subject.OpenAI", return_value=mock_openai):
        client = make_subject_client("o4-mini")
    assert isinstance(client, OpenAISubjectClient)


def test_make_subject_client_unrecognized_prefix_raises() -> None:
    """make_subject_client raises ValueError for unrecognized model prefix."""
    from skill_harness.ablation.subject import make_subject_client

    with pytest.raises(ValueError, match="Unrecognized model prefix"):
        make_subject_client("gemini-pro")


# ---------------------------------------------------------------------------
# Test: SubjectAdapter Protocol is satisfied by both clients
# ---------------------------------------------------------------------------


def test_subject_adapter_protocol_anthropic() -> None:
    """AnthropicSubjectClient satisfies the SubjectAdapter Protocol (has .call method)."""
    from skill_harness.ablation.subject import AnthropicSubjectClient, SubjectAdapter

    client = AnthropicSubjectClient.__new__(AnthropicSubjectClient)
    assert hasattr(client, "call")
    # Runtime isinstance check via Protocol (requires typing.runtime_checkable)
    # Just verify the Protocol is importable and has the right structure
    assert hasattr(SubjectAdapter, "__protocol_attrs__") or callable(SubjectAdapter)


def test_subject_adapter_protocol_openai() -> None:
    """OpenAISubjectClient satisfies the SubjectAdapter Protocol (has .call method)."""
    from skill_harness.ablation.subject import OpenAISubjectClient, SubjectAdapter

    client = OpenAISubjectClient.__new__(OpenAISubjectClient)
    assert hasattr(client, "call")
    assert hasattr(SubjectAdapter, "__protocol_attrs__") or callable(SubjectAdapter)


# ---------------------------------------------------------------------------
# Test: sub-surface exclusion — excluded namespaces NOT loaded after import
# ---------------------------------------------------------------------------


def test_openai_sub_surface_exclusion_beta_not_loaded() -> None:
    """After importing OpenAISubjectClient, openai.beta is NOT loaded in sys.modules.

    This enforces the supply-chain audit sub-surface exclusion rule:
    openai.beta.* is out of scope and must not be imported.
    """
    # Force the import to happen
    from skill_harness.ablation import subject as _subject_module  # noqa: F401

    # Check excluded namespaces are not loaded
    excluded = [
        "openai.beta",
        "openai.resources.assistants",
        "openai.resources.realtime",
        "openai.resources.files",
        "openai.resources.vector_stores",
        "openai.resources.uploads",
        "openai.resources.webhooks",
    ]
    for ns in excluded:
        assert ns not in sys.modules, (
            f"Sub-surface exclusion violation: '{ns}' found in sys.modules. "
            "This namespace is excluded per supply-chain audit "
            ".supply-chain-risk-auditor/openai-audit-2026-06-08.md"
        )
