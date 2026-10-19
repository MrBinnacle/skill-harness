"""Tests for Verbosity Tier-1 metric (A35).

Uses tiktoken cl100k_base for offline token counting.
Validates:
- mechanical_validity: metric_fn(case) == metric_fn(case) (bit-equality) for 5 corpus inputs
- known_value assertions (exact token counts from tiktoken cl100k_base)
- does NOT make network calls (pytest-socket autouse in conftest.py)
- ENCODING constant is 'cl100k_base'
"""

from __future__ import annotations

import pytest

from skill_harness.oracles.tier1.verbosity import (
    ENCODING_NAME,
    count_tokens,
)

# ---------------------------------------------------------------------------
# Corpus — 5 fixed inputs (token counts must be verified against tiktoken)
# ---------------------------------------------------------------------------

# These are computed by running:
#   import tiktoken; enc = tiktoken.get_encoding("cl100k_base")
#   enc.encode("...text...") → len(...)
# and frozen here for bit-equality discipline.

CORPUS = [
    # (text, expected_token_count)
    ("Hello world", 2),
    ("The quick brown fox jumps over the lazy dog.", 10),
    ("", 0),
    ("I think this could possibly work.", 7),
    ("Maybe the result is clear.", 6),
]


# ---------------------------------------------------------------------------
# Mechanical validity — bit-equality (A33)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,_expected", CORPUS, ids=[f"corpus_{i}" for i in range(len(CORPUS))])
def test_verbosity_mechanical_validity(text: str, _expected: int) -> None:
    """count_tokens(case) == count_tokens(case) — bit-for-bit deterministic."""
    assert count_tokens(text) == count_tokens(text)


# ---------------------------------------------------------------------------
# Known-value assertions
# ---------------------------------------------------------------------------


def test_verbosity_known_value_hello_world() -> None:
    """'Hello world' = 2 tokens in cl100k_base."""
    assert count_tokens("Hello world") == 2


def test_verbosity_known_value_empty_string() -> None:
    """Empty string = 0 tokens."""
    assert count_tokens("") == 0


def test_verbosity_known_value_pangram() -> None:
    """Known token count for the quick brown fox sentence (cl100k_base = 10 tokens)."""
    assert count_tokens("The quick brown fox jumps over the lazy dog.") == 10


def test_verbosity_known_value_hedge_sentence() -> None:
    """'I think this could possibly work.' = 7 tokens."""
    assert count_tokens("I think this could possibly work.") == 7


def test_verbosity_known_value_maybe_sentence() -> None:
    """'Maybe the result is clear.' = 6 tokens."""
    assert count_tokens("Maybe the result is clear.") == 6


# ---------------------------------------------------------------------------
# Encoding discipline
# ---------------------------------------------------------------------------


def test_verbosity_encoding_is_cl100k_base() -> None:
    """ENCODING_NAME must be cl100k_base (A35)."""
    assert ENCODING_NAME == "cl100k_base"


def test_verbosity_returns_int() -> None:
    """count_tokens returns an int, not float."""
    result = count_tokens("hello")
    assert isinstance(result, int)
