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
  - Markdown links [text](url) are format-normalised, not blanket-excluded
    (S49 C3): a link with an external http(s) target IS a reference, so its
    URL is kept for citation matching; a link with a non-http target
    (relative path, anchor) is not a reference, so only its text is kept.
    Blanket-stripping the URL previously scored a hyperlinked source as
    UNCITED while an identical bare URL scored CITED — an arm-differential
    deflation of the citation axis.

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

# Markdown inline link: [text](url).
# Group 1 = link text, group 2 = link target. A link whose target is an
# external http(s) reference IS a citation, so its URL is preserved for
# citation detection (S49 C3); non-http targets (relative paths, anchors)
# are not references, so only the link text is kept.
_MARKDOWN_LINK: Final[re.Pattern[str]] = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

# A markdown link target that is an external reference (http/https).
_HTTP_URL: Final[re.Pattern[str]] = re.compile(r"^\s*https?://", re.IGNORECASE)

# Flag marker: a line that identifies a specific flag entry in a sentinel review.
# The severity word must appear at a recognizable flag-entry position:
#   - **CRITICAL**: foo         (bullet + severity word)
#   * IMPORTANT: bar            (bullet + severity word)
#   ## FLAG 1 — CRITICAL        (ATX heading where "FLAG" is followed by a number/ID)
#   ### FLAG 001 — IMPORTANT    (same)
#   **CRITICAL**                (bold severity label as a standalone token)
#   **FLAG:**                   (bold FLAG label)
#
# Excluded by this regex:
#   # Slop Flag Report          (heading where "Flag" is part of a title phrase, not a flag-ID)
#     → "# Slop Flag" does not match because FLAG must follow a "FLAG " prefix with number
#       OR must be a severity word (CRITICAL/IMPORTANT/MINOR) or followed by ":"
_FLAG_LINE: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*(?:"
    r"[-*]\s.*?\b(?:CRITICAL|IMPORTANT|MINOR)\b"  # bullet + severity word
    r"|[-*]\s.*?\bFLAG\b"  # bullet + FLAG word
    r"|#{1,6}\s+FLAG\s+\w"  # ATX heading: ## FLAG <id>
    r"|#{1,6}\s.*?\b(?:CRITICAL|IMPORTANT|MINOR)\b"  # ATX heading + severity
    r"|\*{1,2}(?:CRITICAL|IMPORTANT|MINOR|FLAG)\*{0,2}"  # bold severity label
    r")",
    # Case-SENSITIVE (S49 C3): only the uppercase labels a sentinel actually
    # emits are flags. re.IGNORECASE let everyday lowercase prose ("minor
    # style nits", "critical path") count as uncited flags, inflating the
    # denominator and deflating the score arm-differentially.
    re.MULTILINE,
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
    """Remove fenced code blocks and non-reference markdown link URLs.

    Fenced code content is replaced with spaces of equal length so that
    line-position offsets remain valid for flag-line detection.

    Markdown links are normalised so citation detection is not
    format-sensitive (S49 C3): a link with an external http(s) target is a
    reference, so its URL is preserved (kept alongside the link text);
    a link with a non-http target (relative path, anchor) is not a
    reference, so only the link text is kept.
    """

    # Replace fenced code blocks with whitespace of equal span
    def _blank_code(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    cleaned = _FENCED_CODE_BLOCK.sub(_blank_code, text)

    # Normalise markdown links: keep http(s) targets (they are citations),
    # drop non-http targets (keep only the link text).
    def _normalise_link(m: re.Match[str]) -> str:
        link_text, target = m.group(1), m.group(2)
        if _HTTP_URL.search(target):
            return f"{link_text} {target}"
        return link_text

    cleaned = _MARKDOWN_LINK.sub(_normalise_link, cleaned)
    return cleaned


def _extract_flag_blocks(text: str) -> list[str]:
    """Return a list of text blocks, one per detected flag.

    Each block starts at the flag line and extends to the next flag line.
    The full block (heading + body) is included to capture citations that
    may appear in the paragraph body below a heading-style flag marker.
    """
    matches = list(_FLAG_LINE.finditer(text))
    if not matches:
        return []

    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        # Block extends to the next flag start (or end of text).
        # Do NOT cut at paragraph breaks — heading-style flags (e.g.
        # "## FLAG 1 — CRITICAL\n\n**Pattern:**...") have their citations
        # in the body paragraphs below the heading line.
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
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
