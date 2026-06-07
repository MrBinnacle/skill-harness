"""Citation Presence Per Flag Tier-1 metric (A14, A33).

citation_presence_per_flag = flags_with_citation / max(flags_total, 1)

This metric corresponds to the ai-slop-sentinel clause 0 axis: every FLAG
the sentinel emits must cite a watch entry (source). A flag without a
citation is itself slop ("A flag without a citation is itself slop" per
the ai-slop-sentinel SKILL.md).

Mechanical interpretation: scan a sentinel review output for FLAG markers
and check whether each has a citation within the same paragraph/block.

Flag detection:
  A line matching r'^\\s*[-*]\\s.*\\b(?:CRITICAL|IMPORTANT|MINOR)\\b' OR
  a line containing '**FLAG:**', '[FLAG]', or a severity label in the
  expected sentinel output shape (Critical/Important/Minor bullet).

Citation detection (per A14, markdown-code-block and markdown-link excluded):
  Matches any of:
  - Numeric reference: \\[\\d+\\]
  - Author-year: \\([A-Z][a-z]+\\s+\\d{4}\\)
  - URL: https?://\\S+

A flag block = the flag line + continuation lines until the next flag or
double-newline (paragraph boundary). A flag "has a citation" if the block
contains at least one citation marker.

False-positive exclusions (A14):
  - Content inside ```...``` fenced code blocks is excluded (citations
    inside code would be false matches).
  - Content inside [text](url) markdown links is excluded from URL matching
    because the URL is not a citation marker in context — it IS the inline
    link target, not a reference.

Design decisions:
  - Pure Python, no network calls.
  - PYTHONHASHSEED=0 discipline: all regex operations are deterministic;
    no set iteration used in score computation.
  - Returns 0.0 for empty strings and for outputs with no flag markers
    (a non-review output naturally has no flags; score 0.0 is the correct
    non-zero-citation answer but should be excluded from aggregation via
    the falsifying-case spec — the extractor's falsifying_case requires
    sentinel-format input where flags should appear).
  - returns float in [0.0, 1.0].
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Pre-compiled patterns
# ---------------------------------------------------------------------------

# Fenced code block: ```...``` (non-greedy, dotall)
_FENCED_CODE_BLOCK: Final[re.Pattern[str]] = re.compile(r"```.*?```", re.DOTALL)

# Markdown inline link: [text](url) — exclude the url part from citation matching
# We remove the whole [text](url) construct; keep "text" but drop "(url)"
_MARKDOWN_LINK: Final[re.Pattern[str]] = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# Flag marker: bullet line starting with -, *, or ** that contains a severity word
# Matches lines like:
#   - **CRITICAL**: foo
#   * Important: bar
#   - [FLAG] baz
#   **FLAG:** something
_FLAG_LINE: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*(?:[-*]|\*{1,2})\s*.*?\b(?:CRITICAL|IMPORTANT|MINOR|FLAG)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Citation markers (after fenced-code and markdown-link stripping):
#   [1], [23], [123] — numeric reference style
#   (Smith 2023), (Van der Berg 2021) — author-year style
#   https://... or http://... — URL reference
_CITATION: Final[re.Pattern[str]] = re.compile(
    r"\[\d+\]"  # numeric ref
    r"|"
    r"\([A-Z][a-z]+(?:\s+[A-Za-z]+)*\s+\d{4}\)"  # author-year
    r"|"
    r"https?://\S+"  # URL
)

# Paragraph separator (two or more newlines = end of a flag block)
_PARA_SEP: Final[re.Pattern[str]] = re.compile(r"\n\n+")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_markup(text: str) -> str:
    """Remove fenced code blocks and markdown link URLs from text.

    Fenced code content is replaced with spaces of equal length so that
    line-position offsets remain valid for flag-line detection.
    Markdown link URLs are stripped but the link text is kept.
    """

    # Replace fenced code blocks with whitespace of equal span
    def _blank_code(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    cleaned = _FENCED_CODE_BLOCK.sub(_blank_code, text)
    # Remove markdown link URL targets; keep link text
    cleaned = _MARKDOWN_LINK.sub(r"\1", cleaned)
    return cleaned


def _extract_flag_blocks(text: str) -> list[str]:
    """Return a list of text blocks, one per detected flag.

    Each block starts at the flag line and extends to the next paragraph
    separator or the next flag line (whichever comes first).
    """
    matches = list(_FLAG_LINE.finditer(text))
    if not matches:
        return []

    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        # Determine end: next flag start or paragraph break
        next_flag_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        # Find earliest paragraph break between start and next_flag_start
        para_m = _PARA_SEP.search(text, start, next_flag_start)
        end = para_m.start() if para_m else next_flag_start

        blocks.append(text[start:end])

    return blocks


def _block_has_citation(block: str) -> bool:
    """Return True if the block contains at least one citation marker."""
    return _CITATION.search(block) is not None


# ---------------------------------------------------------------------------
# Public metric function
# ---------------------------------------------------------------------------


def compute_citation_presence_per_flag(text: str) -> float:
    """Compute the Citation Presence Per Flag score for ``text``.

    Returns
    -------
    float
        flags_with_citation / max(flags_total, 1).
        Returns 0.0 for empty strings or text with no flag markers.

    Notes
    -----
    Deterministic for a given input (regex-based, no hash randomisation
    dependency). Satisfies the A33 bit-equality requirement.
    """
    if not text.strip():
        return 0.0

    cleaned = _strip_markup(text)
    blocks = _extract_flag_blocks(cleaned)

    if not blocks:
        return 0.0

    flags_with_citation = sum(1 for b in blocks if _block_has_citation(b))
    return flags_with_citation / len(blocks)
