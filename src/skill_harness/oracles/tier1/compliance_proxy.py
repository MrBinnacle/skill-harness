"""Compliance Proxy Tier-1 metric (A14, A33).

Compliance Proxy = directive_keyword_match_count / max(word_count, 1)

This is an honest heuristic proxy (per PRD §12 redefinition) for whether
an output contains directive-compliance language.  It is NOT a semantic
oracle for true compliance — it measures surface-level directive-keyword
density only.

Directive keywords: words/phrases that signal the output is acting on a
compliance or imperative instruction.

Halt condition (§3d): the dispatch brief states "PRD §12 doesn't fully name
the directive-keyword list".  The set below is a minimal principled set
derived from standard English imperative/deontic modal vocabulary.  If a
reviewer disagrees with specific inclusions or needs domain-specific
extensions, surface via NEEDS_CONTEXT rather than silently expanding.

Design decisions:
- Case-insensitive whole-word matching.
- Multi-word phrases (e.g. "must not") matched before single words.
- Returns 0.0 for empty strings.
- Pure Python regex, no network calls.
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Directive keyword set
# ---------------------------------------------------------------------------

# Deontic modals + imperatives that signal compliance-oriented language.
# Sorted longest-first at definition for documentation clarity;
# _build_patterns() re-sorts before compiling.
DIRECTIVE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        # Strong obligation/prohibition modals
        "must",
        "must not",
        "shall",
        "shall not",
        "should",
        "should not",
        "ought to",
        # Imperatives / prescriptive verbs
        "always",
        "never",
        "ensure",
        "require",
        "requires",
        "required",
        "forbid",
        "forbids",
        "forbidden",
        "avoid",
        "avoids",
        "do not",
        "don't",
        "do",
        # Compliance-specific phrases
        "comply",
        "complies",
        "compliant",
        "adherent",
        "adhere",
        "follow",
        "follows",
    }
)


def _build_patterns(keywords: frozenset[str]) -> list[re.Pattern[str]]:
    """Build regex patterns sorted longest-first to avoid double-counting."""
    sorted_kws = sorted(keywords, key=lambda kw: len(kw.split()), reverse=True)
    return [re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE) for kw in sorted_kws]


_DIRECTIVE_PATTERNS: Final[list[re.Pattern[str]]] = _build_patterns(DIRECTIVE_KEYWORDS)


# ---------------------------------------------------------------------------
# Public metric function
# ---------------------------------------------------------------------------


def compute_compliance_proxy(text: str) -> float:
    """Compute the Compliance Proxy score for ``text``.

    Returns
    -------
    float
        directive_keyword_match_count / max(word_count, 1).
        Returns 0.0 for empty strings.
    """
    if not text.strip():
        return 0.0

    word_count = len(text.split())
    if word_count == 0:
        return 0.0

    # Count matches, consuming spans to avoid double-counting overlaps.
    working = text
    match_count = 0
    for pattern in _DIRECTIVE_PATTERNS:
        found = pattern.findall(working)
        if found:
            match_count += len(found)
            working = pattern.sub(" ", working)

    return match_count / word_count
