"""Adversarial prompt-injection guard for Tier-2 judge inputs (A38 layer 4).

``detect_meta_tokens`` applies a heuristic regex short-circuit to candidate
outputs BEFORE they are passed to the judge.  A match means the output
contains patterns commonly used for prompt-injection attacks.

Matched verdicts are stored as inadmissible with reason ``'suspected_injection'``.
They are NOT silently dropped — every evidence row is preserved for audit per
the append-only evidence invariant (CLAUDE.md Evidence model).

The guard is cost-zero: no extra Claude calls are made.  It fires before the
judge is invoked so no API credits are spent on suspected injections.

Regex pattern (verbatim per A38):
    r"(?i)ignore (previous|prior) instructions|new instructions:|<system>|</output_[ab]>"

This covers 4 pattern classes:
1. "ignore previous/prior instructions" (case-insensitive)
2. "new instructions:" (case-insensitive)
3. <system> tag
4. </output_a> or </output_b> closing tags (common XML-delimiter escapes)

A38 layer 4 records this as a "heuristic short-circuit" — it is not a complete
injection defense.  Position-swap (layer 5) catches content-anchored injections
that move with the response.  Both layers are needed.
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Meta-token detection regex (verbatim from A38)
# ---------------------------------------------------------------------------

_META_TOKEN_PATTERN: Final = re.compile(
    r"(?i)ignore (previous|prior) instructions|new instructions:|<system>|</output_[ab]>"
)


def detect_meta_tokens(text: str) -> bool:
    """Return True if ``text`` contains injection-pattern signatures.

    The check is case-insensitive for all patterns except the XML tag
    patterns which are already covered by the (?i) flag.

    :param text: Candidate output text to scan.
    :returns: True if a meta-token pattern is detected, False otherwise.
    """
    return bool(_META_TOKEN_PATTERN.search(text))
