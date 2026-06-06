"""SubjectClient — calls the subject model to generate outputs for ablation sampling (D.2).

Design:
- The subject model receives the rendered system prompt (Full / Ablated_k / Null)
  and a fixed user task message, and produces a text output.
- SubjectClient wraps the Anthropic SDK ``messages.create`` call.
- Dependency injection: accepts an ``anthropic.Anthropic`` client (A32 mock discipline).
- Returns ``SubjectResponse`` carrying the output text and the usage block for
  cost recording (A41: write per-call token/usd from actual response usage, never projection).
- Warmup-or-serialize discipline (A43/COST-4): ``warmup_shared_prefix()`` must be called
  once before fan-out across conditions to ensure the cache-write lands before reads.
- Error handling (A40 per-call policy):
    - Transient (429 / 500 / network): caller should retry-with-backoff.
    - Permanent (400): caller should skip-and-record.
    - Budget abort: caller handles outside this module.
- No stochastic control flow: this module generates content only; the runner owns
  all orchestration decisions (which samples to issue, which to skip, stop criteria).

Per CLAUDE.md load-bearing invariants:
- The deterministic Python layer owns orchestration. SubjectClient is a content worker.
- Never raises non-transient errors silently — always propagates so the runner can record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# SubjectCallError — local to ablation/ (do NOT add transient to OracleAPIError)
# ---------------------------------------------------------------------------


class SubjectCallError(Exception):
    """Raised when a subject model API call fails (A40 per-call policy).

    This error is LOCAL to the ablation package to avoid cross-module changes to
    src/skill_harness/oracles/errors.py (Track C scope).

    Parameters
    ----------
    message : str
        Human-readable error description.
    transient : bool
        True if the error is likely transient (429/500/network) -> retry with backoff.
        False for permanent errors (400) -> skip-and-record.
    """

    def __init__(self, message: str, transient: bool = False) -> None:
        super().__init__(message)
        self.transient: bool = transient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MODEL: str = "claude-sonnet-4-6"

# Default max_tokens for subject model responses.
# High enough to allow substantive responses without truncating short responses.
_DEFAULT_MAX_TOKENS: int = 512

# Transient HTTP status codes — caller should retry.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# SubjectResponse
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubjectResponse:
    """Response from a single subject model call.

    Fields
    ------
    output_text : str
        The text content of the model's response.
    input_tokens : int
        Number of input tokens (from usage block, A41).
    cache_read_input_tokens : int
        Prompt-cache read tokens (from usage block, A41). 0 if none.
    cache_creation_input_tokens : int
        Prompt-cache write tokens (from usage block, A41). 0 if none.
    output_tokens : int
        Number of output tokens (from usage block, A41).
    usd : float
        Estimated USD cost computed from token counts + model pricing.
    model : str
        The model ID actually used.
    stop_reason : str
        Stop reason from the API response (e.g. "end_turn", "max_tokens").
    """

    output_text: str
    input_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int
    usd: float
    model: str
    stop_reason: str


# ---------------------------------------------------------------------------
# Pricing (per-million-token rates for cost estimation, A41)
# ---------------------------------------------------------------------------
# Approximate rates for claude-sonnet-4-6. Used for USD estimation from usage.
# A41: cost written from actual response usage — these rates produce the estimate.
# Per https://platform.claude.com/docs/about-claude/pricing (2026-06).
_PRICE_PER_MTok: dict[str, dict[str, float]] = {
    # Sonnet 4.6: $3/$15 per MTok (in/out). Cache: $3.75 write / $0.30 read.
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    # Default fallback (uses same rates — adjust when other models are used).
    "_default": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}


def _estimate_usd(
    model: str,
    input_tokens: int,
    cache_read_input_tokens: int,
    cache_creation_input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate USD cost from token counts and model pricing."""
    rates = _PRICE_PER_MTok.get(model, _PRICE_PER_MTok["_default"])
    mtok = 1_000_000.0
    # Non-cache input = total input minus cache components
    plain_input = max(0, input_tokens - cache_read_input_tokens - cache_creation_input_tokens)
    cost = (
        plain_input * rates["input"] / mtok
        + cache_creation_input_tokens * rates["cache_write"] / mtok
        + cache_read_input_tokens * rates["cache_read"] / mtok
        + output_tokens * rates["output"] / mtok
    )
    return round(cost, 8)


# ---------------------------------------------------------------------------
# SubjectClient
# ---------------------------------------------------------------------------


class SubjectClient:
    """Wraps the Anthropic SDK for subject model calls during ablation sampling.

    Parameters
    ----------
    client : anthropic.Anthropic | None
        SDK client. If None, one is created from the environment (ANTHROPIC_API_KEY).
    model : str
        Subject model ID. Defaults to ``claude-sonnet-4-6``.
    max_tokens : int
        Maximum output tokens per call.
    """

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = client if client is not None else anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Call the subject model with the given system blocks and user message.

        :param system_blocks: Rendered system blocks (from ConditionRenderer) including
            cache_control markers (A43).
        :param user_message: The task prompt sent to the model.
        :returns: SubjectResponse with output text and usage data.
        :raises SubjectCallError: On API errors (both transient and permanent).
            The ``transient`` attribute on the error indicates retry eligibility.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_blocks,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIStatusError as exc:
            transient = exc.status_code in _TRANSIENT_STATUS_CODES
            raise SubjectCallError(
                f"Subject model call failed (status={exc.status_code}): {exc.message}",
                transient=transient,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise SubjectCallError(
                f"Subject model connection error: {exc}",
                transient=True,
            ) from exc

        # Extract text content
        output_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                output_text += block.text

        # Extract usage (A41: always from actual response, never projection)
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        usd = _estimate_usd(
            model=self._model,
            input_tokens=input_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
            output_tokens=output_tokens,
        )

        return SubjectResponse(
            output_text=output_text,
            input_tokens=input_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
            output_tokens=output_tokens,
            usd=usd,
            model=response.model,
            stop_reason=response.stop_reason or "unknown",
        )

    def warmup_shared_prefix(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Send a warmup call to write the shared prefix to the prompt cache (A43/COST-4).

        This call MUST complete before fan-out across conditions begins, so the
        cache-write lands before any reads. The response is returned but may be
        discarded by the caller (the output is not used as a sample).

        :param system_blocks: System blocks for the shared prefix (base system + skill prefix).
        :param user_message: Canonical task message.
        :returns: SubjectResponse (caller may discard content, but cost is real).
        """
        return self.call(system_blocks=system_blocks, user_message=user_message)


# ---------------------------------------------------------------------------
# Cost projection (worst-case, for pre-call budget gate A42)
# ---------------------------------------------------------------------------


def project_call_cost(
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    cache_hit_fraction: float = 0.0,
) -> float:
    """Project worst-case cost for a single subject call (A42 pre-call gate).

    Uses non-cached input rate for worst-case projection (cache hit uncertain
    at gate time). The gate uses this value to decide whether to proceed.

    :param model: Model ID.
    :param estimated_input_tokens: Estimated input token count (projection).
    :param estimated_output_tokens: Estimated output token count (projection).
    :param cache_hit_fraction: Expected cache hit fraction (0.0 = worst case = no cache).
    :returns: Projected USD cost.
    """
    rates = _PRICE_PER_MTok.get(model, _PRICE_PER_MTok["_default"])
    mtok = 1_000_000.0
    # Worst case: assume all input is uncached (cache_hit_fraction=0)
    cached_tokens = int(estimated_input_tokens * cache_hit_fraction)
    uncached_tokens = estimated_input_tokens - cached_tokens
    cost = (
        uncached_tokens * rates["input"] / mtok
        + cached_tokens * rates["cache_read"] / mtok
        + estimated_output_tokens * rates["output"] / mtok
    )
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Output SHA-256 (for sample provenance)
# ---------------------------------------------------------------------------


def sha256_of_output(text: str) -> str:
    """Return the SHA-256 hex digest of the UTF-8-encoded output text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
