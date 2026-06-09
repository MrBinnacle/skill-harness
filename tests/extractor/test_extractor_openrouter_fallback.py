"""Tests for extractor OpenRouter fallback (_make_extractor_client).

TDD discipline: tests written BEFORE implementation (RED first).

Covers the (ANTHROPIC_API_KEY x OPENROUTER_API_KEY) env-var matrix for
_make_extractor_client, plus an integration test confirming that
call_extract_clauses threads base_url + api_key through to the
anthropic.Anthropic constructor when only OPENROUTER_API_KEY is set.

Mock discipline:
- All tests offline (no live API calls; pytest-socket discipline preserved).
- monkeypatch for env isolation — never mutate os.environ directly.
- anthropic.Anthropic constructor patched to capture construction kwargs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from skill_harness.extractor.claude import call_extract_clauses
from skill_harness.extractor.errors import ExtractorClaudeError

# The verified OpenRouter Anthropic-compat base_url (confirmed from
# https://openrouter.ai/anthropic/claude-sonnet-4.6/api).
_OPENROUTER_ANTHROPIC_BASE_URL = "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# Helpers (mirrors test_claude.py pattern)
# ---------------------------------------------------------------------------


def _make_tool_use_block(input_data: dict[str, Any]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_clauses"
    block.input = input_data
    return block


def _make_response(
    content: list[MagicMock],
    stop_reason: str = "tool_use",
) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.stop_reason = stop_reason
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


def _empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both API key env vars so tests start from a clean slate."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Test 1: ANTHROPIC_API_KEY present — direct path, no OpenRouter, no warning
# ---------------------------------------------------------------------------


def test_extractor_client_anthropic_direct_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ANTHROPIC_API_KEY set: constructs direct Anthropic client (no base_url override)
    and emits no stderr warning."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with patch("skill_harness.extractor.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        from skill_harness.extractor.claude import _make_extractor_client

        _client, model_id = _make_extractor_client()

    # Anthropic direct: no base_url kwarg passed
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert "base_url" not in call_kwargs, (
        "Direct Anthropic path must NOT pass base_url to the constructor"
    )

    # No stderr warning on the direct path
    captured = capsys.readouterr()
    assert captured.err == "", "No warning expected on direct Anthropic path"

    # Model id should be the bare Anthropic model name
    assert not model_id.startswith("anthropic/"), (
        "Direct path model_id must be bare (e.g. 'claude-sonnet-4-6'), not provider-prefixed"
    )


# ---------------------------------------------------------------------------
# Test 1b: BOTH keys set — ANTHROPIC_API_KEY wins (precedence rule)
# ---------------------------------------------------------------------------


def test_extractor_client_anthropic_direct_when_both_keys_set(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both ANTHROPIC_API_KEY and OPENROUTER_API_KEY set: ANTHROPIC_API_KEY wins.

    Makes the precedence rule (ANTHROPIC first, OPENROUTER second) explicit-by-test
    rather than implicit-by-code-reading. Mirrors test 1's shape: no base_url
    override, no stderr warning, bare model name returned.
    """
    _empty_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    with patch("skill_harness.extractor.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        from skill_harness.extractor.claude import _make_extractor_client

        _client, model_id = _make_extractor_client()

    # ANTHROPIC_API_KEY wins: no base_url kwarg passed
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert "base_url" not in call_kwargs, (
        "When both keys are set, ANTHROPIC_API_KEY wins — no base_url override expected"
    )

    # No stderr warning (we did not fall back to OpenRouter)
    captured = capsys.readouterr()
    assert captured.err == "", (
        "No warning expected when ANTHROPIC_API_KEY is present,"
        " even with OPENROUTER_API_KEY also set"
    )

    # Model id should be the bare Anthropic model name (not provider-prefixed)
    assert not model_id.startswith("anthropic/"), (
        "Direct path model_id must be bare (e.g. 'claude-sonnet-4-6'), not provider-prefixed"
    )


# ---------------------------------------------------------------------------
# Test 2: Only OPENROUTER_API_KEY present — fallback path, warning emitted
# ---------------------------------------------------------------------------


def test_extractor_client_openrouter_fallback_when_only_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No ANTHROPIC_API_KEY but OPENROUTER_API_KEY set: constructs Anthropic client
    with base_url=OpenRouter Anthropic-compat URL and emits a stderr warning naming
    OPENROUTER_API_KEY and OpenRouter."""
    _empty_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    with patch("skill_harness.extractor.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        from skill_harness.extractor.claude import _make_extractor_client

        _client, model_id = _make_extractor_client()

    # base_url must point to the OpenRouter Anthropic-compat endpoint
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert "base_url" in call_kwargs, "OpenRouter fallback must pass base_url to constructor"
    assert call_kwargs["base_url"] == _OPENROUTER_ANTHROPIC_BASE_URL, (
        f"base_url must be {_OPENROUTER_ANTHROPIC_BASE_URL!r}, got {call_kwargs['base_url']!r}"
    )

    # api_key must be the OPENROUTER_API_KEY value
    assert call_kwargs.get("api_key") == "sk-or-test", (
        "OpenRouter fallback must pass OPENROUTER_API_KEY as api_key"
    )

    # model_id must be provider-prefixed for OpenRouter
    assert model_id.startswith("anthropic/"), (
        "OpenRouter fallback model_id must be provider-prefixed"
        " (e.g. 'anthropic/claude-sonnet-4.6')"
    )

    # Warning must name both OPENROUTER_API_KEY and OpenRouter
    captured = capsys.readouterr()
    assert "OPENROUTER_API_KEY" in captured.err, "stderr warning must name OPENROUTER_API_KEY"
    assert "OpenRouter" in captured.err, "stderr warning must name OpenRouter"


# ---------------------------------------------------------------------------
# Test 3: Neither key set — ExtractorClaudeError naming both env vars
# ---------------------------------------------------------------------------


def test_extractor_client_raises_when_no_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When neither ANTHROPIC_API_KEY nor OPENROUTER_API_KEY is set, _make_extractor_client
    raises ExtractorClaudeError whose message names both env vars."""
    _empty_env(monkeypatch)

    from skill_harness.extractor.claude import _make_extractor_client

    with pytest.raises(ExtractorClaudeError) as exc_info:
        _make_extractor_client()

    error_msg = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in error_msg, (
        "Error must name ANTHROPIC_API_KEY so operators know what to set"
    )
    assert "OPENROUTER_API_KEY" in error_msg, (
        "Error must name OPENROUTER_API_KEY so operators know the alternative"
    )


# ---------------------------------------------------------------------------
# Test 4: Integration — call_extract_clauses uses OpenRouter when ANTHROPIC absent
# ---------------------------------------------------------------------------


@patch("skill_harness.extractor.claude.time.sleep")
def test_call_extract_clauses_uses_openrouter_when_anthropic_key_absent(
    mock_sleep: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_extract_clauses constructs Anthropic SDK with OpenRouter base_url and api_key
    when ANTHROPIC_API_KEY is absent and OPENROUTER_API_KEY is present.

    Verifies end-to-end threading: _make_extractor_client -> anthropic.Anthropic
    constructor -> messages.create call completes with valid response.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-integration-test")

    with patch("skill_harness.extractor.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_tool_use_block({"clauses": [_valid_raw_clause(0)]})]
        )

        clauses = call_extract_clauses("Test skill body.")

    # Anthropic constructor must have been called with OpenRouter base_url + api_key
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs.get("base_url") == _OPENROUTER_ANTHROPIC_BASE_URL, (
        f"Expected base_url={_OPENROUTER_ANTHROPIC_BASE_URL!r}, "
        f"got base_url={call_kwargs.get('base_url')!r}"
    )
    assert call_kwargs.get("api_key") == "sk-or-integration-test", (
        "api_key must be the OPENROUTER_API_KEY value"
    )

    # messages.create must have been called with the provider-prefixed model ID
    create_kwargs = mock_client.messages.create.call_args.kwargs
    assert create_kwargs.get("model", "").startswith("anthropic/"), (
        f"messages.create model must be provider-prefixed for OpenRouter, "
        f"got {create_kwargs.get('model')!r}"
    )

    # Extraction must succeed and return valid clauses
    assert len(clauses) == 1
    assert clauses[0].clause_index == 0
