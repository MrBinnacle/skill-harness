"""Tests for Compliance Proxy Tier-1 metric (A14, A33).

Compliance Proxy = honest heuristic: count of directive-keyword matches
(case-insensitive, whole-word) / word_count.

Directive keywords per A14 PRD §12 redefinition: words that signal the
output is acting on an instruction directive (e.g. following a 'must',
'shall', 'should', 'do', 'don't', 'always', 'never', 'ensure', 'require',
'forbid', 'avoid', 'must not', 'shall not').

This is a heuristic proxy for compliance — it cannot measure true compliance,
only surface-level directive-keyword density.  Used as a Tier-1 mechanical
metric because it is deterministic and falsifiable; it is NOT a semantic oracle.

Validates:
- mechanical_validity: bit-equality over 5 corpus inputs
- known_value assertions on fixed corpus
- directive keyword set is non-empty
- empty string edge case
"""

from __future__ import annotations

import pytest

from skill_harness.oracles.tier1.compliance_proxy import (
    DIRECTIVE_KEYWORDS,
    compute_compliance_proxy,
)

# ---------------------------------------------------------------------------
# Corpus — 5 fixed inputs
# ---------------------------------------------------------------------------

CORPUS = [
    "The sky is blue.",
    "You must always wash your hands.",
    "Never ignore the warning signs.",
    "Ensure the door is closed and avoid loud noises.",
    "",
]


# ---------------------------------------------------------------------------
# Mechanical validity — bit-equality (A33)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS, ids=[f"corpus_{i}" for i in range(len(CORPUS))])
def test_compliance_proxy_mechanical_validity(text: str) -> None:
    """compute_compliance_proxy(case) == compute_compliance_proxy(case)."""
    assert compute_compliance_proxy(text) == compute_compliance_proxy(text)


# ---------------------------------------------------------------------------
# Known-value assertions
# ---------------------------------------------------------------------------


def test_compliance_proxy_no_directives() -> None:
    """Plain sentence with no directive keywords → 0.0."""
    assert compute_compliance_proxy("The sky is blue.") == pytest.approx(0.0)


def test_compliance_proxy_empty_string() -> None:
    """Empty string → 0.0 (no division by zero)."""
    assert compute_compliance_proxy("") == pytest.approx(0.0)


def test_compliance_proxy_must_always() -> None:
    """'must' + 'always' in 6-word sentence → 2/6."""
    score = compute_compliance_proxy("You must always wash your hands.")
    assert score == pytest.approx(2 / 6)


def test_compliance_proxy_never() -> None:
    """'never' in 5-word sentence → 1/5."""
    score = compute_compliance_proxy("Never ignore the warning signs.")
    assert score == pytest.approx(1 / 5)


def test_compliance_proxy_case_insensitive() -> None:
    """Directive keyword matching is case-insensitive."""
    lower = compute_compliance_proxy("must always do this")
    upper = compute_compliance_proxy("MUST ALWAYS DO THIS")
    mixed = compute_compliance_proxy("Must Always Do This")
    assert lower == upper == mixed


def test_compliance_proxy_returns_float() -> None:
    """compute_compliance_proxy returns a float."""
    result = compute_compliance_proxy("Some text.")
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Directive keywords non-empty (implementation guard)
# ---------------------------------------------------------------------------


def test_directive_keywords_non_empty() -> None:
    """DIRECTIVE_KEYWORDS must be a non-empty frozenset."""
    assert isinstance(DIRECTIVE_KEYWORDS, frozenset)
    assert len(DIRECTIVE_KEYWORDS) > 0


def test_directive_keywords_include_must() -> None:
    """'must' must be in DIRECTIVE_KEYWORDS."""
    assert "must" in DIRECTIVE_KEYWORDS


def test_directive_keywords_include_never() -> None:
    """'never' must be in DIRECTIVE_KEYWORDS."""
    assert "never" in DIRECTIVE_KEYWORDS


def test_directive_keywords_include_always() -> None:
    """'always' must be in DIRECTIVE_KEYWORDS."""
    assert "always" in DIRECTIVE_KEYWORDS
