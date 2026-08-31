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

Load-bearing invariants for this module:
- The deterministic Python layer owns orchestration. Subject adapters are content workers.
- Never raises non-transient errors silently — always propagates so the runner can record.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

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

# OpenRouter base URL (Phase A.5 pivot).
# The OpenAI SDK is used as an OpenAI-compatible gateway client; no new SDK to audit.
# OpenRouter exposes per-request cost in response.usage.cost (USD float).
_OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# cost_source Literal alias (A41 provenance):
# "openrouter_response" — usd taken directly from response.usage.cost (preferred when
#   routing through OpenRouter; reflects OpenRouter's per-provider rates + margin).
# "local_estimate"      — usd computed via _estimate_usd_openai using local pricing
#   table (used for direct OpenAI calls and as fallback when usage.cost is absent).
CostSource = Literal["openrouter_response", "local_estimate"]

_logger = logging.getLogger(__name__)


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
    cost_source : CostSource
        Provenance of the ``usd`` value (A41 audit trail). Phase A.5:
          - "openrouter_response": pulled from ``response.usage.cost`` (preferred
            when routing through OpenRouter; reflects OpenRouter's per-provider
            rates + margin).
          - "local_estimate": computed via ``_estimate_usd_openai`` /
            ``_estimate_usd`` from the local pricing table (used for direct OpenAI
            and Anthropic, and as fallback when ``usage.cost`` is absent).
        Defaults to "local_estimate" — every code path constructing a
        SubjectResponse sets this explicitly except for back-compat callers.
    """

    output_text: str
    input_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int
    usd: float
    model: str
    stop_reason: str
    cost_source: CostSource = "local_estimate"


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
# Pricing (per-million-token rates, F3: single source of truth)
# ---------------------------------------------------------------------------
# A41: cost written from actual response usage — these rates produce the estimate.
#
# F3 fix: this table used to be duplicated (hand-maintained) in
# skill_harness.oracles.calibration.cost_projection as MODEL_PRICING_USD_PER_M,
# with one overlapping entry (claude-sonnet-4-6, values agreed) and each table
# missing the other's models. cost_projection.MODEL_PRICING_USD_PER_M is now
# derived from THIS table (see the note there) so a price change here can never
# silently diverge from the pre-call budget-gate projection.
PRICE_PER_MTOK: dict[str, dict[str, float]] = {
    # Sonnet 4.6: $3/$15 per MTok (in/out). Cache: $3.75 write / $0.30 read.
    # Per https://platform.claude.com/docs/about-claude/pricing (2026-06).
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    # Opus 4.7: $5/$25 per MTok (in/out). Cache: $6.25 write / $0.50 read.
    # Per https://platform.claude.com/docs/about-claude/pricing (2026-06).
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    # Haiku 4.5: $1/$5 per MTok (in/out). Cache: $1.25 write / $0.10 read.
    # Per https://platform.claude.com/docs/about-claude/pricing (2026-06).
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
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
    # Claude Sonnet 5: $2/$10 per MTok (in/out). Cache: $2.50 write / $0.20 read.
    # Per https://platform.claude.com/docs/about-claude/pricing (2026-08).
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_write": 2.50,
        "cache_read": 0.20,
    },
    # Default fallback (uses Anthropic Sonnet rates — adjust when other models are used).
    "_default": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}


def resolve_price_key(model: str) -> str:
    """Map a subject-model identifier to its PRICE_PER_MTOK key (#302).

    PRICE_PER_MTOK is keyed on the bare vendor model name
    (``claude-sonnet-5``). The evidence store records whatever identifier the
    call was actually routed with, and that is not always the bare name: when
    ANTHROPIC_API_KEY is absent and OPENROUTER_API_KEY is present, the CLI
    rewrites ``claude-sonnet-5`` to ``anthropic/claude-sonnet-5``
    (``cli/main.py::_resolve_subject_model_with_fallback``) and the run is made
    under that routed identifier. Both forms are present in the production
    store's ``samples.subject_model`` today.

    The bare name is the canonical pricing key. The provider segment names the
    route, not the model, and vendor prices do not differ by route, so the
    prefix is stripped here at lookup rather than at ingest: the store is
    append-only, and rewriting the recorded identifier would erase which route
    a run was actually made under.

    Lookup stays exact after the strip. An unrecognised model still raises
    KeyError at the call site rather than falling back to ``_default`` - a cap
    projection must never silently price the wrong model.

    :param model: Subject-model identifier as recorded or supplied.
    :returns: The key to look up in PRICE_PER_MTOK.
    """
    _, separator, bare = model.partition("/")
    return bare if separator else model


def lookup_price_row(model: str) -> dict[str, float]:
    """Return the PRICE_PER_MTOK row for a subject model, or refuse (#333).

    Two behaviours, both required by the receipt discipline:

    1. A provider-routed identifier is normalised through ``resolve_price_key``
       before the lookup, so ``anthropic/claude-sonnet-5`` finds the
       ``claude-sonnet-5`` row instead of missing it.
    2. A model with no row raises ``KeyError`` naming the identifier the caller
       passed. It does NOT fall back to ``_default``. ``_default`` carries
       Sonnet-4.6's rates, so a silent fallback prices an unpriced model at
       $3/$15 per MTok and writes that figure to the append-only evidence store
       as if it were measured. A missing price is a typed refusal here, the
       same call ``cost_projection`` makes pre-call.

    The refusal costs at most one API call: the raised KeyError propagates out
    of ``AnthropicSubjectClient.call`` and aborts the run at its first sample,
    before a second call is paid for.

    :param model: Subject-model identifier as recorded or supplied.
    :returns: The per-million-token rate row for that model.
    :raises KeyError: If the resolved key has no row in PRICE_PER_MTOK.
    """
    key = resolve_price_key(model)
    row = PRICE_PER_MTOK.get(key)
    if row is None:
        raise KeyError(
            f"No PRICE_PER_MTOK row for subject model {model!r} "
            f"(resolved to price key {key!r}). Add the vendor's published rates to "
            "skill_harness.ablation.subject.PRICE_PER_MTOK. The harness refuses to "
            "record a cost it cannot price rather than apply the '_default' rate, "
            "which is Sonnet-4.6's and would be wrong for any other model."
        )
    return row


def _estimate_usd(
    model: str,
    input_tokens: int,
    cache_read_input_tokens: int,
    cache_creation_input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate USD cost from token counts and model pricing (Anthropic-style).

    :raises KeyError: If ``model`` has no PRICE_PER_MTOK row (#333). The
        pre-#333 behaviour silently priced such a model at the ``_default``
        (Sonnet-4.6) rate.
    """
    rates = lookup_price_row(model)
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
    rates = PRICE_PER_MTOK.get(model, PRICE_PER_MTOK["_default"])
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

    Phase A.5 — OpenRouter routing:
    When ``base_url`` is set (typically to ``_OPENROUTER_BASE_URL``), the underlying
    OpenAI client is constructed with ``base_url=...`` plus an API key resolved from
    ``OPENROUTER_API_KEY`` (taking priority) or ``OPENAI_API_KEY``. The OpenAI SDK
    is used as an OpenAI-compatible gateway client — no new SDK to audit; same
    supply-chain decision applies. OpenRouter exposes per-request cost in
    ``response.usage.cost``; when present (and ``base_url`` is set), that value
    overrides the local pricing estimate, and ``cost_source`` records the
    provenance ("openrouter_response" vs "local_estimate") for the A41 audit trail.

    Parameters
    ----------
    client : OpenAI | None
        SDK client. If None, one is created from the environment (OPENAI_API_KEY
        or OPENROUTER_API_KEY depending on ``base_url``).
    model : str
        Subject model ID. For direct OpenAI: e.g. 'gpt-5.5', 'gpt-5.4'.
        For OpenRouter (when ``base_url`` is set): the full provider-prefixed id
        e.g. 'openai/gpt-5.5' — pass-through to OpenRouter's routing layer.
    max_tokens : int
        Maximum completion tokens per call.
    base_url : str | None
        Optional override for the OpenAI SDK base URL. Set to OpenRouter's URL
        (``_OPENROUTER_BASE_URL``) to route via OpenRouter. When None, direct OpenAI.
    """

    def __init__(
        self,
        client: OpenAI | None = None,
        model: str = "gpt-5.5",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        base_url: str | None = None,
    ) -> None:
        self._base_url: str | None = base_url
        if client is not None:
            self._client = client
        elif base_url is not None:
            # OpenRouter (or other OpenAI-compatible gateway) path.
            # OPENROUTER_API_KEY takes priority; fall back to OPENAI_API_KEY.
            api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            # Direct OpenAI path: SDK auto-resolves OPENAI_API_KEY from env.
            self._client = OpenAI()
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

        # Cost-source resolution (Phase A.5, A41 provenance):
        # 1. OpenRouter path AND usage.cost present  -> use it; cost_source="openrouter_response"
        # 2. OpenRouter path AND usage.cost absent   -> log warning, fall back; "local_estimate"
        # 3. Direct OpenAI path                      -> always local estimate; "local_estimate"
        # The local-estimate fallback de-prefixes the model id ('openai/gpt-5.5' -> 'gpt-5.5')
        # so the local pricing table lookup matches.
        usd: float
        cost_source: CostSource
        usage_cost = None
        if usage is not None and self._base_url is not None:
            usage_cost = getattr(usage, "cost", None)

        if usage_cost is not None:
            usd = float(usage_cost)
            cost_source = "openrouter_response"
        else:
            if self._base_url is not None:
                _logger.warning(
                    "OpenRouter response missing usage.cost for model %r; "
                    "falling back to local pricing estimate. A41 audit trail "
                    "records cost_source='local_estimate'.",
                    self._model,
                )
            # De-prefix provider-routed ids so local pricing table matches
            # (e.g. 'openai/gpt-5.5' -> 'gpt-5.5'). Pure 'gpt-5.5' is unchanged.
            local_model_id = self._model.split("/", 1)[-1] if "/" in self._model else self._model
            usd = _estimate_usd_openai(
                model=local_model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
            )
            cost_source = "local_estimate"

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
            cost_source=cost_source,
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
    - ``<provider>/<model>`` (contains '/') -> OpenAISubjectClient routed via OpenRouter
      (base_url = ``_OPENROUTER_BASE_URL``). The FULL provider-prefixed id is passed
      through; OpenRouter expects it in ``client.chat.completions.create(model=...)``.
      OpenRouter is the authoritative validator for the provider segment — the factory
      does NOT early-reject unknown providers.
    - ``claude-*``    -> AnthropicSubjectClient
    - ``gpt-*``       -> OpenAISubjectClient (direct OpenAI, no base_url)
    - ``o<digit>-*``  -> OpenAISubjectClient (direct OpenAI; o-series e.g. o4-mini)

    :param model: Model ID string. Examples:
        - 'claude-sonnet-4-6' (Anthropic direct)
        - 'gpt-5.5' (OpenAI direct)
        - 'o4-mini' (OpenAI o-series direct)
        - 'openai/gpt-5.5' (OpenAI via OpenRouter)
        - 'anthropic/claude-3-opus' (Anthropic via OpenRouter)
        - 'google/gemini-2-pro' (Google via OpenRouter)
    :returns: A SubjectAdapter instance configured for the given model.
    :raises ValueError: If the model id matches no recognized pattern.
    """
    # OpenRouter form: any model id containing '/' routes through OpenRouter.
    # OpenRouter performs its own validation on the provider segment, so the factory
    # only enforces the '/' shape — see test_factory_openrouter_unknown_provider.
    if "/" in model:
        return OpenAISubjectClient(model=model, base_url=_OPENROUTER_BASE_URL)
    if model.startswith("claude-"):
        return AnthropicSubjectClient(model=model)
    if model.startswith("gpt-"):
        return OpenAISubjectClient(model=model)
    # o-series: o1, o3, o4 etc. Pattern: starts with 'o' followed by digit(s) then '-'
    if len(model) >= 2 and model[0] == "o" and model[1].isdigit():
        return OpenAISubjectClient(model=model)
    raise ValueError(
        f"Unrecognized model prefix for {model!r}. Supported patterns: "
        "'<provider>/<model>' (OpenRouter), 'claude-*' (Anthropic direct), "
        "'gpt-*' (OpenAI direct), 'o<digit>-*' (OpenAI o-series). "
        "Add a new prefix mapping in make_subject_client() for new direct-API providers."
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
    rates = PRICE_PER_MTOK.get(model, PRICE_PER_MTOK["_default"])
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
