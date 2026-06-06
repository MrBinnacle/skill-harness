"""Hedge Index Tier-1 metric (A14, A33).

Hedge Index = number_of_hedge_token_matches / max(word_count, 1)

The wordlist is loaded once at import time from a committed JSON fixture:
  tests/oracles/tier1/fixtures/hedge_wordlist.json

The SHA-256 of that file becomes this metric's implementation_hash so that
frozen regression cases can be re-audited when the wordlist changes.

Design decisions:
- Matching is case-insensitive, whole-word (word-boundary anchored regex).
- Multi-word hedges (e.g. "I think", "in general") are matched before
  single-word hedges to avoid double-counting.
- Word count uses simple whitespace splitting (consistent with other metrics).
- Pure Python, no network calls.

Per CLAUDE.md metric-provenance invariant: wordlist SHA-256 is stored as
implementation_hash.  DO NOT inline the wordlist here — it must remain in
the committed JSON fixture so the hash is stable.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Wordlist fixture path
# ---------------------------------------------------------------------------

# Resolved relative to this file's location: src/skill_harness/oracles/tier1/
# -> up 4 levels to project root -> tests/oracles/tier1/fixtures/
_THIS_DIR: Final[Path] = Path(__file__).parent
_PROJECT_ROOT: Final[Path] = _THIS_DIR.parents[3]  # src/../../../
WORDLIST_PATH: Final[Path] = (
    _PROJECT_ROOT / "tests" / "oracles" / "tier1" / "fixtures" / "hedge_wordlist.json"
)


def implementation_hash() -> str:
    """Return SHA-256 hex digest of the committed wordlist fixture file."""
    raw = WORDLIST_PATH.read_bytes()
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Load wordlist at module import time
# ---------------------------------------------------------------------------


def _load_wordlist(path: Path) -> list[str]:
    """Load hedge phrases from the committed JSON fixture.

    Returns phrases sorted longest-first so multi-word phrases are
    matched before single-word subsets (prevents double-counting).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    phrases: list[str] = data["hedges"]
    return sorted(phrases, key=lambda p: len(p.split()), reverse=True)


_HEDGE_PHRASES: Final[list[str]] = _load_wordlist(WORDLIST_PATH)

# Pre-compile patterns: longest multi-word first, then single-word.
# Each pattern is word-boundary anchored and case-insensitive.
_HEDGE_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)
    for phrase in _HEDGE_PHRASES
]


# ---------------------------------------------------------------------------
# Public metric function
# ---------------------------------------------------------------------------


def compute_hedge_index(text: str) -> float:
    """Compute the Hedge Index for ``text``.

    Returns
    -------
    float
        hedge_match_count / max(word_count, 1).
        Returns 0.0 for empty strings.

    Algorithm
    ---------
    1. Strip the text of matches (greedy longest-first) to avoid
       double-counting overlapping phrases.
    2. Count remaining words with simple whitespace split.
    3. Divide match count by word count.
    """
    if not text.strip():
        return 0.0

    word_count = len(text.split())
    if word_count == 0:
        return 0.0

    # Count matches, consuming matched spans to avoid double-counting.
    working = text
    match_count = 0
    for pattern in _HEDGE_PATTERNS:
        found = pattern.findall(working)
        if found:
            match_count += len(found)
            # Replace matched spans with spaces to prevent overlap re-matching.
            working = pattern.sub(" ", working)

    return match_count / word_count
