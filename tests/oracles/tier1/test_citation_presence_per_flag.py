"""Tests for Citation Presence Per Flag Tier-1 metric (A14, A33).

citation_presence_per_flag = flags_with_citation / max(flags_total, 1)

Validates:
- mechanical_validity: bit-equality over 5 corpus inputs (A33)
- known-value assertions on fixed corpus
- markdown-code-block exclusion (A14 false-positive guard)
- markdown-link URL exclusion (A14 false-positive guard)
- empty string edge case
- no-flag output edge case (returns 0.0)
- does NOT make network calls (pytest-socket autouse in conftest.py)
"""

from __future__ import annotations

import pytest

from skill_harness.oracles.tier1.citation_presence_per_flag import (
    compute_citation_presence_per_flag,
)

# ---------------------------------------------------------------------------
# Corpus — 5 fixed inputs for bit-equality (A33)
# ---------------------------------------------------------------------------

_FLAG_WITH_URL = (
    "- **CRITICAL**: Missing type annotations everywhere.\n"
    "  See https://mypy.readthedocs.io/en/stable/ for the policy.\n"
)

_FLAG_WITHOUT_CITATION = "- **IMPORTANT**: The code has no tests.\n  This is bad practice.\n"

_TWO_FLAGS_ONE_CITED = (
    "- **CRITICAL**: Hallucinated API usage detected. See https://docs.python.org/\n"
    "\n"
    "- **MINOR**: Em-dash overuse.\n"
)

_FLAGS_WITH_NUMERIC_REF = (
    "- **IMPORTANT**: Over-engineering [1]\n"
    "- **CRITICAL**: Testing the mock — tautological asserts [2]\n"
)

_EMPTY = ""

CORPUS = [
    _FLAG_WITH_URL,
    _FLAG_WITHOUT_CITATION,
    _TWO_FLAGS_ONE_CITED,
    _FLAGS_WITH_NUMERIC_REF,
    _EMPTY,
]


# ---------------------------------------------------------------------------
# Mechanical validity — bit-equality (A33)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", CORPUS, ids=[f"corpus_{i}" for i in range(len(CORPUS))])
def test_citation_presence_per_flag_mechanical_validity(text: str) -> None:
    """compute_citation_presence_per_flag(case) == compute_citation_presence_per_flag(case)."""
    assert compute_citation_presence_per_flag(text) == compute_citation_presence_per_flag(text)


# ---------------------------------------------------------------------------
# Known-value assertions
# ---------------------------------------------------------------------------


def test_citation_presence_per_flag_empty() -> None:
    """Empty string → 0.0."""
    assert compute_citation_presence_per_flag("") == pytest.approx(0.0)


def test_citation_presence_per_flag_no_flags() -> None:
    """Plain prose with no flag markers → 0.0."""
    text = "This code looks fine. The logic is clear and well-tested."
    assert compute_citation_presence_per_flag(text) == pytest.approx(0.0)


def test_citation_presence_per_flag_single_flag_with_url() -> None:
    """One flag with URL citation → 1.0."""
    result = compute_citation_presence_per_flag(_FLAG_WITH_URL)
    assert result == pytest.approx(1.0)


def test_citation_presence_per_flag_single_flag_without_citation() -> None:
    """One flag with no citation → 0.0."""
    result = compute_citation_presence_per_flag(_FLAG_WITHOUT_CITATION)
    assert result == pytest.approx(0.0)


def test_citation_presence_per_flag_two_flags_one_cited() -> None:
    """Two flags, one cited → 0.5."""
    result = compute_citation_presence_per_flag(_TWO_FLAGS_ONE_CITED)
    assert result == pytest.approx(0.5)


def test_citation_presence_per_flag_numeric_refs_all_cited() -> None:
    """Two flags each with numeric ref [N] → 1.0."""
    result = compute_citation_presence_per_flag(_FLAGS_WITH_NUMERIC_REF)
    assert result == pytest.approx(1.0)


def test_citation_presence_per_flag_author_year_citation() -> None:
    """Author-year citation (Smith 2023) is detected."""
    text = "- **IMPORTANT**: Logic duplication (Smith 2023)\n"
    result = compute_citation_presence_per_flag(text)
    assert result == pytest.approx(1.0)


def test_citation_presence_per_flag_returns_float() -> None:
    """compute_citation_presence_per_flag returns a float."""
    result = compute_citation_presence_per_flag("- **MINOR**: style issue\n")
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# A14 exclusion — fenced code block
# ---------------------------------------------------------------------------


def test_citation_presence_per_flag_fenced_code_excluded() -> None:
    """Citations inside fenced code blocks do not count (A14 false-positive guard)."""
    # The URL is inside a code fence; the flag has no real citation
    text = (
        "- **CRITICAL**: Some issue.\n"
        "```\n"
        "# See https://docs.python.org/ — inline code comment\n"
        "x = 1\n"
        "```\n"
    )
    result = compute_citation_presence_per_flag(text)
    # URL is inside code block; should NOT be counted as a citation
    assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# A14 exclusion — markdown inline link
# ---------------------------------------------------------------------------


def test_citation_presence_per_flag_markdown_hyperlink_is_citation() -> None:
    """A [text](http(s)://url) markdown link IS a citation (S49 C3 fix).

    A hyperlink to an external reference is a citation. Previously the
    URL was stripped with the link markup, so a hyperlinked source scored
    UNCITED while an identical *bare* URL scored CITED — an arm-differential
    deflation of the citation axis (the more-structured arm, which formats
    references as markdown links, was penalised). The http(s) target is now
    preserved for citation detection.
    """
    text = "- **IMPORTANT**: Use [the docs](https://docs.python.org/) here.\n"
    result = compute_citation_presence_per_flag(text)
    assert result == pytest.approx(1.0)


def test_citation_presence_per_flag_non_http_markdown_link_not_citation() -> None:
    """A [text](relative/path) link with no http(s) target is not a citation.

    The exclusion still holds for link targets that are not external
    references (relative paths, anchors) — only http(s) targets count.
    """
    text = "- **IMPORTANT**: See [section two](#s2) for details.\n"
    result = compute_citation_presence_per_flag(text)
    assert result == pytest.approx(0.0)


def test_citation_presence_per_flag_standalone_url_not_link() -> None:
    """A bare URL (not inside a markdown link) IS a valid citation."""
    text = "- **CRITICAL**: Hallucinated API. See https://docs.python.org/ for correct usage.\n"
    result = compute_citation_presence_per_flag(text)
    assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# S49 C3 — arm-differential deflation regressions (verdict-affecting)
# ---------------------------------------------------------------------------


def test_c3_lowercase_prose_bullets_are_not_flags() -> None:
    """Lowercase prose containing severity words must NOT count as flags (C3).

    The severity/FLAG markers are recognised case-sensitively: only the
    uppercase labels a sentinel actually emits (``**CRITICAL**``, ``## FLAG 1``)
    are flags. Everyday lowercase prose ("minor style nits", "critical path")
    is not. Previously ``re.IGNORECASE`` counted every such bullet as an
    uncited flag, inflating the denominator and deflating the score — worse
    for the arm that writes more prose. Failure scenario from the S49
    manifest: 3 cited flags + 5 prose bullets scored 3/8=0.375 instead of 1.0.
    """
    text = (
        "- **CRITICAL**: Hallucinated API. See https://docs.python.org/\n"
        "- **IMPORTANT**: Missing tests [1]\n"
        "- **MINOR**: Em-dash overuse (Smith 2023)\n"
        "- minor style nits below\n"
        "- important to note the naming here\n"
        "- the critical path is untested\n"
        "- flag any TODOs you find\n"
        "- consider a minor cleanup pass\n"
    )
    # Only the 3 uppercase-labelled flags count, and all 3 are cited.
    assert compute_citation_presence_per_flag(text) == pytest.approx(1.0)


def test_c3_no_flags_from_pure_lowercase_prose() -> None:
    """Pure lowercase prose with severity words yields zero flags → 0.0 (C3)."""
    text = (
        "- minor style nits below\n"
        "- important to note the naming here\n"
        "- the critical path is untested\n"
    )
    assert compute_citation_presence_per_flag(text) == pytest.approx(0.0)
