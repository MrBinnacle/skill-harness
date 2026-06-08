"""Subject adapters — call subject models to generate outputs for ablation sampling (D.2).

Design:
- The subject model receives the rendered system prompt (Full / Ablated_k / Null)
  and a fixed user task message, and produces a text output.
- SubjectAdapter Protocol defines the call interface.
- AnthropicSubjectClient wraps the Anthropic SDK ``messages.create`` call.
- OpenAISubjectClient wraps the OpenAI SDK ``chat.completions.create`` call.
  IMPORT RESTRICTION (supply-chain audit 2026-06-08):
    Import ONLY: ``from openai import OpenAI, OpenAIError, APIStatusError, APIConnectionError``
    DO NOT import from: openai.beta, openai.resources.realtime, openai.resources.assistants,
    openai.resources.files, openai.resources.vector_stores, openai.resources.uploads,
    openai.resources.webhooks. Violation is HALT-FOR-ESCALATION.
- make_subject_client factory dispatches on model name prefix.
- Dependency injection: clients accept SDK clients for testing (A32 mock discipline).
- Returns SubjectResponse carrying the output text and the usage block for
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
- The deterministic Python layer owns orchestration. Subject adapters are content workers.
- Never raises non-transient errors silently — always propagates so the runner can record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import anthropic

# OpenAI import — ONLY the safe surfaces (supply-chain audit 2026-06-08).
# Allowed: openai.OpenAI, openai.APIStatusError, openai.APIConnectionError.
# EXCLUDED: openai.beta.*, openai.resources.realtime, openai.resources.assistants,
#   openai.resources.files, openai.resources.vector_stores, openai.resources.uploads,
#   openai.resources.webhooks. See .supply-chain-risk-auditor/openai-audit-2026-06-08.md.
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import APIStatusError as OpenAIAPIStatusError
from openai import OpenAI

# T3 tracer adapter; supply-chain audit at .supply-chain-risk-auditor/openai-audit-2026-06-08.md

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
        NOTE: OpenAI has no cache-write analog; always 0 for OpenAI subjects.
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
# SubjectAdapter Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SubjectAdapter(Protocol):
    """Protocol for subject model adapters.

    Any class implementing this Protocol can serve as a subject in ablation sampling.
    The protocol enforces the content-worker contract: adapters generate content only;
    the runner owns all orchestration decisions.
    """

    def call(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Call the subject model and return a SubjectResponse.

        :param system_blocks: Rendered system blocks (from ConditionRenderer).
        :param user_message: The task prompt sent to the model.
        :returns: SubjectResponse with output text and usage data.
        :raises SubjectCallError: On API errors (transient or permanent).
        """
        ...

    def warmup_shared_prefix(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Send a warmup call to write the shared prefix to the prompt cache (A43/COST-4)."""
        ...


# ---------------------------------------------------------------------------
# Pricing (per-million-token rates for cost estimation, A41)
# ---------------------------------------------------------------------------
# A41: cost written from actual response usage — these rates produce the estimate.
_PRICE_PER_MTok: dict[str, dict[str, float]] = {
    # Sonnet 4.6: $3/$15 per MTok (in/out). Cache: $3.75 write / $0.30 read.
    # Per https://platform.claude.com/docs/about-claude/pricing (2026-06).
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    # GPT-5.5: $5/$30 per MTok (in/out). Cached input: $0.50/MTok.
    # Per https://developers.openai.com/api/docs/pricing (2026-06-08).
    # Note: "gpt-5" in the Tier-2 memo maps to gpt-5.5 — the current flagship
    # production model. See t3-pre-registration.md for disambiguation.
    "gpt-5.5": {
        "input": 5.00,
        "output": 30.00,
        "cache_write": 0.0,  # OpenAI has no cache-write cost (server-side)
        "cache_read": 0.50,
    },
    # GPT-5.4: $2.50/$15 per MTok (in/out). Cached input: $0.25/MTok.
    # Per https://developers.openai.com/api/docs/pricing (2026-06-08).
    "gpt-5.4": {
        "input": 2.50,
        "output": 15.00,
        "cache_write": 0.0,
        "cache_read": 0.25,
    },
    # GPT-5.4-mini: $0.75/$4.50 per MTok (in/out). Cached input: $0.075/MTok.
    # Per https://developers.openai.com/api/docs/pricing (2026-06-08).
    "gpt-5.4-mini": {
        "input": 0.75,
        "output": 4.50,
        "cache_write": 0.0,
        "cache_read": 0.075,
    },
    # Default fallback (uses Anthropic Sonnet rates — adjust when other models are used).
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
    """Estimate USD cost from token counts and model pricing (Anthropic-style)."""
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


def _estimate_usd_openai(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int,
) -> float:
    """Estimate USD cost for an OpenAI API call (A41).

    OpenAI's pricing model differs from Anthropic's:
    - ``input_tokens`` = total prompt tokens (INCLUDING cached tokens).
    - ``cache_read_input_tokens`` = subset of prompt tokens served from cache.
    - Billable non-cached input = input_tokens - cache_read_input_tokens.
    - Cached tokens billed at the lower cache_read rate.
    - OpenAI has no cache-write cost (server-managed; no cache_creation analog).
    - cache_creation_input_tokens is always 0 for OpenAI subjects.

    Pricing source: https://developers.openai.com/api/docs/pricing (2026-06-08).

    :param model: OpenAI model ID (e.g. 'gpt-5.5', 'gpt-5.4').
    :param input_tokens: Total prompt tokens (usage.prompt_tokens).
    :param output_tokens: Completion tokens (usage.completion_tokens).
    :param cache_read_input_tokens: Cached prompt tokens
        (usage.prompt_tokens_details.cached_tokens). 0 if not present.
    :returns: Estimated USD cost, rounded to 8 decimal places.
    """
    rates = _PRICE_PER_MTok.get(model, _PRICE_PER_MTok["_default"])
    mtok = 1_000_000.0
    # Non-cached input = total input minus cached subset
    non_cached_input = max(0, input_tokens - cache_read_input_tokens)
    cost = (
        non_cached_input * rates["input"] / mtok
        + cache_read_input_tokens * rates["cache_read"] / mtok
        + output_tokens * rates["output"] / mtok
    )
    return round(cost, 8)


# ---------------------------------------------------------------------------
# AnthropicSubjectClient (renamed from SubjectClient; backward-compatible alias below)
# ---------------------------------------------------------------------------


class AnthropicSubjectClient:
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
# Backward-compatible alias: SubjectClient = AnthropicSubjectClient
# ---------------------------------------------------------------------------
# runner.py and existing tests import SubjectClient. This alias preserves all
# existing behavior byte-for-byte while the rename is in flight.
SubjectClient = AnthropicSubjectClient


# ---------------------------------------------------------------------------
# OpenAISubjectClient
# ---------------------------------------------------------------------------


class OpenAISubjectClient:
    """Wraps the OpenAI SDK chat completions endpoint for ablation sampling (T3 tracer).

    IMPORT RESTRICTION: Only ``openai.OpenAI``, ``openai.APIStatusError``, and
    ``openai.APIConnectionError`` are imported. The following sub-surfaces are
    EXCLUDED per supply-chain audit 2026-06-08:
      openai.beta.*, openai.resources.realtime, openai.resources.assistants,
      openai.resources.files, openai.resources.vector_stores,
      openai.resources.uploads, openai.resources.webhooks.
    Rationale: these surfaces match the archetype family of the 2026-03 Anthropic
    Memory Tool CVEs and are not needed for chat-completions-only evaluation.

    Usage mapping vs AnthropicSubjectClient:
    - system_blocks: concatenated into a single role="system" message.
    - OpenAI usage: prompt_tokens -> input_tokens; completion_tokens -> output_tokens;
      prompt_tokens_details.cached_tokens -> cache_read_input_tokens.
    - cache_creation_input_tokens is always 0 (OpenAI has no write-cache cost analog).

    Parameters
    ----------
    client : OpenAI | None
        SDK client. If None, one is created from the environment (OPENAI_API_KEY).
    model : str
        Subject model ID (e.g. 'gpt-5.5', 'gpt-5.4').
    max_tokens : int
        Maximum completion tokens per call.
    """

    def __init__(
        self,
        client: OpenAI | None = None,
        model: str = "gpt-5.5",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = client if client is not None else OpenAI()
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
        """Call the OpenAI subject model with the given system blocks and user message.

        Maps Anthropic's system_blocks list to a single OpenAI role="system" message
        by concatenating the text fields of all blocks (separated by newlines).

        :param system_blocks: Rendered system blocks (from ConditionRenderer).
        :param user_message: The task prompt sent to the model.
        :returns: SubjectResponse with output text and usage data.
        :raises SubjectCallError: On API errors (both transient and permanent).
            The ``transient`` attribute on the error indicates retry eligibility.
        """
        # Map Anthropic's system_blocks to a single OpenAI system message.
        # Concatenate text fields from all blocks; non-text blocks are skipped.
        system_text_parts: list[str] = []
        for block in system_blocks:
            text = block.get("text", "")
            if text:
                system_text_parts.append(text)
        system_content = "\n".join(system_text_parts)

        messages: list[dict[str, str]] = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": user_message})

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=self._max_tokens,
            )
        except OpenAIAPIStatusError as exc:
            transient = exc.status_code in _TRANSIENT_STATUS_CODES
            raise SubjectCallError(
                f"OpenAI subject model call failed (status={exc.status_code}): {exc.message}",
                transient=transient,
            ) from exc
        except OpenAIAPIConnectionError as exc:
            raise SubjectCallError(
                f"OpenAI subject model connection error: {exc}",
                transient=True,
            ) from exc

        # Extract text content from first choice
        output_text = response.choices[0].message.content or ""

        # Extract usage (A41: always from actual response, never projection)
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

        # OpenAI cache-read analog: prompt_tokens_details.cached_tokens
        # OpenAI has no cache-creation analog -> always 0.
        cache_read = 0
        if usage is not None:
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                cache_read = getattr(details, "cached_tokens", 0) or 0

        usd = _estimate_usd_openai(
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
        )

        stop_reason = getattr(response.choices[0], "finish_reason", None) or "unknown"

        return SubjectResponse(
            output_text=output_text,
            input_tokens=input_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=0,  # OpenAI: no cache-write cost analog
            output_tokens=output_tokens,
            usd=usd,
            model=response.model,
            stop_reason=stop_reason,
        )

    def warmup_shared_prefix(
        self,
        system_blocks: list[dict[str, Any]],
        user_message: str,
    ) -> SubjectResponse:
        """Send a warmup call (A43/COST-4 analog for OpenAI).

        OpenAI manages caching server-side automatically; this call still warms
        the context window for the shared prefix. The response may be discarded.

        :param system_blocks: System blocks for the shared prefix.
        :param user_message: Canonical task message.
        :returns: SubjectResponse (caller may discard content, but cost is real).
        """
        return self.call(system_blocks=system_blocks, user_message=user_message)


# ---------------------------------------------------------------------------
# make_subject_client factory
# ---------------------------------------------------------------------------


def make_subject_client(model: str) -> SubjectAdapter:
    """Factory: return a SubjectAdapter for the given model.

    Dispatch table:
    - ``claude-*``    -> AnthropicSubjectClient
    - ``gpt-*``       -> OpenAISubjectClient
    - ``o*-*``        -> OpenAISubjectClient (e.g. o4-mini, o3-mini)

    :param model: Model ID string (e.g. 'claude-sonnet-4-6', 'gpt-5.5', 'o4-mini').
    :returns: A SubjectAdapter instance configured for the given model.
    :raises ValueError: If the model prefix is not recognized.
    """
    if model.startswith("claude-"):
        return AnthropicSubjectClient(model=model)
    if model.startswith("gpt-"):
        return OpenAISubjectClient(model=model)
    # o-series: o1, o3, o4 etc. Pattern: starts with 'o' followed by digit(s) then '-'
    if len(model) >= 2 and model[0] == "o" and model[1].isdigit():
        return OpenAISubjectClient(model=model)
    raise ValueError(
        f"Unrecognized model prefix for {model!r}. "
        "Supported: 'claude-*' (Anthropic), 'gpt-*' (OpenAI), 'o<digit>-*' (OpenAI o-series). "
        "Add a new prefix mapping in make_subject_client() for new providers."
    )


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
