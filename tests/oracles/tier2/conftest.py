"""Tier-2 oracle test configuration.

Per A32:
- pytest-socket --disable-socket applied to all tests in this package via
  autouse fixture (no live network calls during unit tests).
- JudgeClient fixture provides a client with mocked
  anthropic.Anthropic.messages.create at the SDK boundary (A32).

The mock is injected via the constructor: JudgeClient(client=mock_client).
Tests never need live Anthropic credentials.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from skill_harness.oracles.tier2.judge import JudgeClient

# ---------------------------------------------------------------------------
# Network block (A32 — no live calls during unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Block all network I/O for every Tier-2 unit test.

    pytest-socket provides the ``socket_disabled`` fixture.  Any call to
    socket.socket() raises SocketBlockedError.

    Tier-2 tests that test SDK call *shapes* use mock clients; they never
    open real sockets.  This fixture guards against accidental live calls.
    """


# ---------------------------------------------------------------------------
# SDK-boundary mock helpers (A32)
# ---------------------------------------------------------------------------


def _make_tool_use_response(choice: str, rationale: str = "test rationale") -> MagicMock:
    """Build a mock Anthropic Message response with a tool_use block.

    Mirrors the structure the Anthropic SDK returns when stop_reason=="tool_use".
    """
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "report_verdict"
    tool_use_block.input = {"choice": choice, "rationale_brief": rationale}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]
    return response


def _make_malformed_response(stop_reason: str = "end_turn") -> MagicMock:
    """Build a mock response with a non-tool_use stop reason (malformed)."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I choose A"

    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = [text_block]
    return response


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Return a MagicMock wrapping anthropic.Anthropic with messages.create mocked."""
    client = MagicMock()
    # Default: return a valid "A" response for both AB and BA calls
    client.messages.create.return_value = _make_tool_use_response("A")
    return client


@pytest.fixture
def judge_client(mock_anthropic_client: MagicMock) -> JudgeClient:
    """Return a JudgeClient with a mocked Anthropic client injected."""
    from skill_harness.oracles.tier2.judge import JudgeClient

    return JudgeClient(client=mock_anthropic_client)
