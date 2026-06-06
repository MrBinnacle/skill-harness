"""Tests for Hedge Index Tier-1 metric (A14, A33).

Validates:
- mechanical_validity: metric_fn(case) == metric_fn(case) (bit-equality) for 5 corpus inputs
- known_value assertions on fixed corpus
- wordlist loaded from committed JSON fixture (not hardcoded)
- wordlist SHA-256 is stable (implementation_hash discipline per CLAUDE.md metric-provenance)
"""

from __future__ import annotations

import hashlib
import json

import pytest

from skill_harness.oracles.tier1.hedge_index import (
    WORDLIST_PATH,
    compute_hedge_index,
    implementation_hash,
)

# ---------------------------------------------------------------------------
# Corpus — 5 fixed inputs with known hedge counts
# ---------------------------------------------------------------------------

CORPUS = [
    # (text, expected_score)
    # Score = number of hedge token matches (case-insensitive, whole-word) / word_count
    # Using small examples so scores are manually verifiable.
    ("The result is clear.", 0.0),
    ("Maybe the result is clear.", 1 / 5),
    ("Perhaps it might be correct.", 2 / 5),
    ("I think this could possibly work in some cases.", 3 / 9),
    ("", 0.0),  # edge: empty string → 0
]


# ---------------------------------------------------------------------------
# Mechanical validity — bit-equality (A33)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,_expected", CORPUS, ids=[f"corpus_{i}" for i in range(len(CORPUS))])
def test_hedge_index_mechanical_validity(text: str, _expected: float) -> None:
    """metric_fn(case) == metric_fn(case) — bit-for-bit deterministic."""
    assert compute_hedge_index(text) == compute_hedge_index(text)


# ---------------------------------------------------------------------------
# Known-value assertions
# ---------------------------------------------------------------------------


def test_hedge_index_known_value_no_hedges() -> None:
    """Plain declarative sentence has zero hedge score."""
    assert compute_hedge_index("The result is clear.") == pytest.approx(0.0)


def test_hedge_index_known_value_one_hedge() -> None:
    """'Maybe' is a single hedge in a 5-word sentence."""
    score = compute_hedge_index("Maybe the result is clear.")
    assert score == pytest.approx(1 / 5)


def test_hedge_index_known_value_two_hedges() -> None:
    """'Perhaps' + 'might' = 2 hedges in 5 words."""
    score = compute_hedge_index("Perhaps it might be correct.")
    assert score == pytest.approx(2 / 5)


def test_hedge_index_known_value_empty_string() -> None:
    """Empty string returns 0.0 (no division-by-zero)."""
    assert compute_hedge_index("") == pytest.approx(0.0)


def test_hedge_index_known_value_case_insensitive() -> None:
    """Hedge detection is case-insensitive."""
    lower = compute_hedge_index("maybe this works")
    upper = compute_hedge_index("MAYBE this works")
    mixed = compute_hedge_index("Maybe This Works")
    assert lower == upper == mixed


# ---------------------------------------------------------------------------
# Wordlist fixture discipline (metric provenance)
# ---------------------------------------------------------------------------


def test_wordlist_loaded_from_committed_fixture() -> None:
    """Wordlist path points to the committed JSON fixture, not inline code."""
    assert WORDLIST_PATH.exists(), f"Wordlist fixture missing: {WORDLIST_PATH}"
    data = json.loads(WORDLIST_PATH.read_text(encoding="utf-8"))
    assert "hedges" in data, "Wordlist JSON must have a 'hedges' key"
    assert len(data["hedges"]) > 0


def test_implementation_hash_stable() -> None:
    """implementation_hash() == SHA-256(wordlist file) — must be stable."""
    raw = WORDLIST_PATH.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    assert implementation_hash() == expected
