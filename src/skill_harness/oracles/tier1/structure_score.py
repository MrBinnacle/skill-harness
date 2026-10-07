"""Structure Score Tier-1 metric (A14, A33).

Structure Score = (heading_count + paragraph_break_count) / max(word_count, 1)

Definitions:
- heading_count: number of ATX markdown headings (``^#{1,6} `` pattern,
  multiline).  The ``#`` must be at the start of a line and followed by
  exactly one space before the heading text.
- paragraph_break_count: number of ``\\n\\n`` sequences (double newlines).
- word_count: number of whitespace-delimited tokens in the original text
  (including heading markers, punctuation, etc.) — simple split() for
  consistency with other metrics.

Design decisions:
- Pure Python regex, no network calls.
- Returns 0.0 for empty strings (no ZeroDivisionError).
- word_count uses the raw text (including ``#`` markers) to keep the
  denominator consistent with other metrics that use word counts.

Per A33 halt condition: if you need a more sophisticated definition (e.g.
normalising by sentence count), halt and surface the choice.  The current
implementation is the minimal honest interpretation of §3b's description:
"heading-count / paragraph-count regex-based score".
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Pre-compiled patterns
# ---------------------------------------------------------------------------

# ATX heading: ``#`` at line start (after optional leading whitespace per
# CommonMark, but we keep it strict — must be at column 0 for simplicity).
_HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#{1,6} ", re.MULTILINE)

# Paragraph break: one or more blank lines (two or more consecutive newlines).
_PARA_BREAK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\n\n")


# ---------------------------------------------------------------------------
# Public component functions (tested independently)
# ---------------------------------------------------------------------------


def count_headings(text: str) -> int:
    """Return the number of ATX markdown headings in ``text``."""
    return len(_HEADING_PATTERN.findall(text))


def count_paragraph_breaks(text: str) -> int:
    """Return the number of ``\\n\\n`` paragraph breaks in ``text``."""
    return len(_PARA_BREAK_PATTERN.findall(text))


# ---------------------------------------------------------------------------
# Public metric function
# ---------------------------------------------------------------------------


def compute_structure_score(text: str) -> float:
    """Compute the Structure Score for ``text``.

    Returns
    -------
    float
        (heading_count + paragraph_break_count) / max(word_count, 1).
        Returns 0.0 for empty strings.
    """
    if not text.strip():
        return 0.0

    word_count = len(text.split())
    if word_count == 0:
        return 0.0

    structural_elements = count_headings(text) + count_paragraph_breaks(text)
    return structural_elements / word_count
