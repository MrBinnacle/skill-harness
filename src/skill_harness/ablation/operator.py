"""AblationOperator — versioned matched-length neutral substitution (A39).

Design:
- Produces a **deterministic, byte-stable, matched-length, semantically-null**
  placeholder for a removed clause. NOT deletion (A39: deletion conflates clause
  axis-effect with prompt coherence / length / format loss).
- The placeholder token count approximates the removed clause's token count within
  TOKEN_LENGTH_TOLERANCE_FRACTION (±10% or ±2 tokens, whichever is larger).
- ``implementation_hash`` is SHA-256 of the stable implementation-configuration
  canonical string — mirrors the Tier-1 ``metric_versions.implementation_hash``
  discipline so re-audit is possible if the operator changes version.
- ``ablation_operator_id`` is a stable version identifier string.
- NEVER calls a model — the deterministic Python layer constructs the placeholder.
- Uses ``tiktoken cl100k_base`` (version-pinned, offline) for token counting.

Algorithm:
  1. Count tokens in the input clause text (offline tiktoken).
  2. Divide the target token count by the filler unit token count to find how
     many filler units to repeat.
  3. Build the placeholder by repeating the filler unit, adding/removing partial
     units until token count is within tolerance.
  4. Return the placeholder string.

The filler unit is a semantically null, grammatically neutral phrase that:
  - Has stable tokenization across tiktoken versions
  - Produces no meaningful semantic signal to the subject model
  - Has a known, stable token count (verified in ``FILLER_UNIT_TOKENS``)

Per CLAUDE.md §10: tiktoken encoding is deterministic; PYTHONHASHSEED=0 is
not required but is enforced globally by the Tier-1 test suite.
"""

from __future__ import annotations

import hashlib
from typing import Final

import tiktoken

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ABLATION_OPERATOR_VERSION: Final[str] = "neutral-filler-v1"
"""Stable version identifier for this operator implementation."""

_ENCODING_NAME: Final[str] = "cl100k_base"

# Semantically null filler phrase. Chosen to be:
# - Grammatically neutral (imperative-ish but content-free)
# - Stable tokenization in cl100k_base across the 0.7.x series
# - Not interpretable as an instruction to the subject model
_FILLER_UNIT: Final[str] = "[ABLATED]"
"""Base filler atom. Repeated to match target token count."""

# QUAL-2: pin FILLER_UNIT_TOKENS as a module-level constant so it is assertable by callers
# and not just private instance state. Computed once at module import time via tiktoken.
# This resolves the dangling docstring reference "verified in ``FILLER_UNIT_TOKENS``" (line 27).
FILLER_UNIT_TOKENS: Final[int] = len(tiktoken.get_encoding(_ENCODING_NAME).encode(_FILLER_UNIT))
"""Stable token count of one _FILLER_UNIT atom in cl100k_base.

Pinned as a module constant (QUAL-2) so callers can assert invariants and the
docstring reference on line 27 ("verified in ``FILLER_UNIT_TOKENS``") resolves.
Change this constant whenever _FILLER_UNIT or _ENCODING_NAME changes.
"""

# Tolerance for matched-length: ±10% of clause token count, minimum ±2 tokens.
TOKEN_LENGTH_TOLERANCE_FRACTION: Final[float] = 0.10

# Implementation configuration string — hashed to produce implementation_hash.
# Change this whenever the algorithm, filler text, or encoding changes.
_IMPL_CONFIG: Final[str] = (
    f"ablation-operator version={ABLATION_OPERATOR_VERSION} "
    f"filler={_FILLER_UNIT!r} "
    f"encoding={_ENCODING_NAME} "
    f"tolerance={TOKEN_LENGTH_TOLERANCE_FRACTION}"
)


# ---------------------------------------------------------------------------
# AblationOperator
# ---------------------------------------------------------------------------


class AblationOperator:
    """Versioned matched-length neutral substitution operator.

    Parameters
    ----------
    None — all behaviour is fixed by the class constants above.

    Usage
    -----
    >>> op = AblationOperator()
    >>> placeholder = op.render("Always begin your response with 'Certainly!'.")
    >>> op.ablation_operator_id
    'neutral-filler-v1'
    >>> len(op.implementation_hash)
    64
    """

    # ------------------------------------------------------------------
    # Class-level stable attributes (shared across instances)
    # ------------------------------------------------------------------

    ablation_operator_id: str = ABLATION_OPERATOR_VERSION
    implementation_hash: str = hashlib.sha256(_IMPL_CONFIG.encode("utf-8")).hexdigest()

    def __init__(self) -> None:
        # Encoding loaded once per instance; tiktoken caches the BPE data globally.
        self._enc: tiktoken.Encoding = tiktoken.get_encoding(_ENCODING_NAME)
        # Token count of one filler atom — pinned by FILLER_UNIT_TOKENS module constant (QUAL-2).
        self._filler_unit_tokens: int = FILLER_UNIT_TOKENS
        assert self._filler_unit_tokens > 0, (
            f"FILLER_UNIT_TOKENS must be > 0; got {self._filler_unit_tokens!r} "
            f"(QUAL-2: assertion on module constant)"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, clause_text: str) -> str:
        """Return a deterministic, matched-length placeholder for ``clause_text``.

        The returned placeholder:
        - Is byte-equal across calls with the same input (deterministic).
        - Has a token count within TOKEN_LENGTH_TOLERANCE_FRACTION of the
          clause's token count (±10% or ±2 tokens, whichever is larger).
        - Does NOT contain the original clause text.
        - Is semantically null — conveys no axis-relevant signal to the model.

        :param clause_text: The original clause text being ablated.
        :returns: The placeholder string.
        """
        target_tokens = len(self._enc.encode(clause_text))
        return self._build_placeholder(target_tokens)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_placeholder(self, target_tokens: int) -> str:
        """Build a placeholder string of approximately ``target_tokens`` tokens.

        Algorithm:
        1. Compute how many whole filler units fit in target_tokens.
        2. Build an initial placeholder.
        3. Trim if over-length, pad if under-length — both by adjusting the
           filler repetition count — until within tolerance.

        The algorithm terminates because:
        - We start close to the target (whole-unit count).
        - Adjustment is monotone (add or remove one unit).
        - Tolerance guarantees a valid range exists.

        For zero-token clauses the placeholder is the single filler unit
        (we never return an empty string — NOT deletion per A39).
        """
        if target_tokens == 0:
            return _FILLER_UNIT

        filler_count = max(1, round(target_tokens / self._filler_unit_tokens))

        # Separator between units is a space — stable token boundary
        separator = " "

        def _build(count: int) -> str:
            return separator.join([_FILLER_UNIT] * count)

        placeholder = _build(filler_count)
        actual_tokens = len(self._enc.encode(placeholder))

        tolerance = max(2, int(target_tokens * TOKEN_LENGTH_TOLERANCE_FRACTION))

        # Adjust upward if under target
        while actual_tokens < target_tokens - tolerance:
            filler_count += 1
            placeholder = _build(filler_count)
            actual_tokens = len(self._enc.encode(placeholder))

        # Adjust downward if over target
        while actual_tokens > target_tokens + tolerance and filler_count > 1:
            filler_count -= 1
            placeholder = _build(filler_count)
            actual_tokens = len(self._enc.encode(placeholder))

        return placeholder
