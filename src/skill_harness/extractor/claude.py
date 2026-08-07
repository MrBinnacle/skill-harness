"""Claude API wrapper for clause extraction.

Uses the Anthropic Python SDK with tool-use to extract structured clause
data from a skill body. Model: ``claude-opus-5`` (model-pinning
convention for Track B execution work).

Tool design:
- Single tool ``extract_clauses`` with an ``input_schema`` that accepts a
  list of clause objects.
- ``tool_choice={"type": "tool", "name": "extract_clauses"}`` forces Claude
  to use the tool (no free-text fallback).
- ``strict: True`` on the tool definition makes the API guarantee
  ``tool_use.input`` validates against the schema exactly.
- The raw body is embedded verbatim in the user message.

D4 note: extractor calibration is deferred to v0.2 — no (extractor_id,
skill_genre) record is written here.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any, cast

import anthropic
from pydantic import ValidationError

from skill_harness.extractor.errors import ExtractorClaudeError
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractorInstrument,
    FalsifyingCaseSchema,
)
from skill_harness.oracles.tier1.axis_registry import TIER1_AXES

_MODEL = "claude-opus-5"

# OpenRouter Anthropic-compatible Messages API endpoint.
# Verified from https://openrouter.ai/anthropic/claude-sonnet-4.6/api (2026-06-09):
# the quickstart shows anthropic.Anthropic(base_url="https://openrouter.ai/api/v1").
_OPENROUTER_ANTHROPIC_BASE_URL = "https://openrouter.ai/api/v1"

# Provider-prefixed model ID required by the OpenRouter Anthropic-compat endpoint.
_OPENROUTER_MODEL = "anthropic/claude-opus-5"


def _render_axis_catalog() -> str:
    """Render the registered Tier-1 axes as aligned prompt lines.

    Built from ``TIER1_AXES`` rather than typed out here, so the prompt cannot
    drift from the scorers that actually exist (#117 — the hand-typed copy this
    replaces had already lost an axis). Column width follows the longest
    registered name, so alignment survives axes being added or removed.
    """
    width = max((len(axis.name) for axis in TIER1_AXES), default=0)
    return "\n".join(f"  {axis.name.ljust(width)}  — {axis.description}" for axis in TIER1_AXES)


_SYSTEM_PROMPT_BODY = """\
You are a clause extraction specialist for a deterministic LLM skill evaluation harness.

Your task is to identify every *behavioral clause* in the skill document and return them \
as structured data via the extract_clauses tool.

A behavioral clause is a directive that:
1. Claims to cause a measurable change in model output on a specific axis (e.g. formality, \
length, specificity, instruction_following).
2. Can in principle be ablated (removed) and the effect measured.
3. Has a direction: it either increases, decreases, or preserves a measurable axis.

Instructions:
- Extract EVERY clause, including weak or potentially vacuous ones.
- For each clause, identify the measurement axis (a short noun phrase), the comparator \
(increase/decrease/preserve/comparator_unspecified), and the preferred oracle tier \
(1=mechanical counting, 2=human judge, 3=real-world consequence).
- Mark vacuity_flag as "semantic_vacuous_pending_review" when the clause is vague, \
metaphorical, or lacks a constructible falsifying case (e.g. "be helpful", "sound natural").
- For non-vacuous clauses (vacuity_flag="none"), you MUST provide a falsifying_case with:
  * input_population_spec: what kinds of inputs to draw from
  * expected_directional_pair: describe a (A=with clause, B=without clause) pair where A \
should beat B on the axis
  * min_reproducibility: fraction of draws that should reproduce the direction (0.0-1.0)
- clause_index must be 0-based and reflect authoring order.
- Do not invent clauses not present in the document.

Registered Tier-1 mechanical scorer names (PREFER these exact strings for axis when the \
clause semantics match — an exact match enables automatic mechanical measurement):
"""

# Concatenated rather than interpolated: the prompt body is prose that may grow
# braces, and an f-string over it would turn the next literal brace into a
# formatting bug in a string nobody type-checks.
_SYSTEM_PROMPT = _SYSTEM_PROMPT_BODY + _render_axis_catalog() + "\n"

# ⛔ JSON-Schema keywords that strict tool use REJECTS with a 400.
#
# Verified live against ``claude-opus-5`` on 2026-08-05, four calls:
#   no-strict + full schema          -> 200
#   strict    + full schema          -> 400 "For 'integer' type, property 'minimum'
#                                            is not supported"
#   strict    - numeric bounds       -> 200
#   strict    - length/pattern only  -> 400  (so length keywords are NOT the offender)
#
# `minLength` and friends are fine and are deliberately NOT listed here.
#
# This is enforced by a structural test rather than by review, because the failure is
# invisible to every offline check: the extractor's unit tests mock the Anthropic client,
# so a schema the API rejects still passes lint, mypy --strict and the full CI matrix.
# The only thing that catches it is walking the schema for banned keys.
_STRICT_BANNED_KEYWORDS: frozenset[str] = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
)

# JSON Schema for the extract_clauses tool input.
_EXTRACT_CLAUSES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "clauses": {
            "type": "array",
            "description": "List of all behavioral clauses extracted from the skill document.",
            "items": {
                "type": "object",
                "required": [
                    "clause_index",
                    "clause_text",
                    "axis",
                    "comparator",
                    "oracle_tier",
                    "vacuity_flag",
                ],
                "properties": {
                    "clause_index": {
                        "type": "integer",
                        # ⛔ NO numeric bounds here. Strict tool use rejects `minimum` /
                        # `maximum` / `exclusiveMinimum` with a 400 (see _STRICT_BANNED_KEYWORDS).
                        # The bound is not lost: ExtractedClause.clause_index is
                        # Annotated[int, Field(ge=0)] and rejects a negative after the call.
                        "description": "Zero-based authoring-order index. Must be >= 0.",
                    },
                    "clause_text": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Verbatim or lightly condensed clause text.",
                    },
                    "axis": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Measurement axis (short noun phrase).",
                    },
                    "comparator": {
                        "type": "string",
                        "enum": ["increase", "decrease", "preserve", "comparator_unspecified"],
                        "description": "Directional claim on the axis.",
                    },
                    "oracle_tier": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "Preferred oracle tier.",
                    },
                    "vacuity_flag": {
                        "type": "string",
                        "enum": ["none", "semantic_vacuous_pending_review"],
                        "description": "Vacuity classification.",
                    },
                    "falsifying_case": {
                        "type": "object",
                        "description": "Required when vacuity_flag is 'none'.",
                        "required": [
                            "input_population_spec",
                            "expected_directional_pair",
                            "min_reproducibility",
                        ],
                        "properties": {
                            "input_population_spec": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "expected_directional_pair": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "min_reproducibility": {
                                "type": "number",
                                # ⛔ NO numeric bounds — see clause_index above. The range is
                                # enforced by FalsifyingCaseSchema.min_reproducibility, which
                                # is Annotated[float, Field(gt=0.0, le=1.0)].
                                "description": "Reproducibility floor in (0.0, 1.0].",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        }
    },
    "required": ["clauses"],
    "additionalProperties": False,
}


def _make_extractor_client() -> tuple[anthropic.Anthropic, str]:
    """Resolve the Anthropic client for clause extraction.

    Returns a ``(client, model_id)`` tuple.  The ``model_id`` is what should be
    passed to ``messages.create`` — for direct Anthropic it is the bare model name
    (``_MODEL``); for the OpenRouter fallback it is the provider-prefixed form
    (``_OPENROUTER_MODEL``, e.g. ``"anthropic/claude-opus-5"``).

    Resolution rules:

    - If ``ANTHROPIC_API_KEY`` is set: return a default Anthropic client + bare model.
    - Else if ``OPENROUTER_API_KEY`` is set: return an Anthropic SDK client with
      ``base_url=_OPENROUTER_ANTHROPIC_BASE_URL`` + ``api_key=OPENROUTER_API_KEY``,
      and emit a stderr warning.
    - Else: raise :class:`ExtractorClaudeError` naming both env vars.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        return anthropic.Anthropic(), _MODEL

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        print(
            f"[INFO] skill init: ANTHROPIC_API_KEY not set; routing extractor via OpenRouter"
            f" (base_url={_OPENROUTER_ANTHROPIC_BASE_URL}) using OPENROUTER_API_KEY."
            f" The Anthropic SDK is unchanged; only the endpoint differs.",
            file=sys.stderr,
        )
        client = anthropic.Anthropic(
            api_key=openrouter_key,
            base_url=_OPENROUTER_ANTHROPIC_BASE_URL,
        )
        return client, _OPENROUTER_MODEL

    raise ExtractorClaudeError(
        "No API key found for clause extraction. Set ANTHROPIC_API_KEY (Anthropic direct)"
        " or OPENROUTER_API_KEY (OpenRouter fallback) to proceed."
    )


def _extract_clauses_tools() -> list[dict[str, Any]]:
    """Build the tools list actually passed to ``messages.create``.

    Constructed once per call so the tool-schema hash is taken from the same
    object graph the request uses (a mock cannot diverge from production).
    """
    return [
        {
            "name": "extract_clauses",
            "description": ("Return all behavioral clauses extracted from the skill document."),
            "input_schema": _EXTRACT_CLAUSES_SCHEMA,
            "strict": True,
        }
    ]


def _instrument_from_request(
    model: str,
    system: str,
    tools: list[dict[str, Any]],
) -> ExtractorInstrument:
    """Hash the exact system prompt and tool schema strings sent to the API."""
    system_prompt_sha256 = hashlib.sha256(system.encode("utf-8")).hexdigest()
    # Canonical JSON of the input_schema (the tool schema identity), matching
    # judge_id's tool_schema_sha256 construction.
    schema = tools[0]["input_schema"]
    schema_bytes = json.dumps(schema, sort_keys=True, ensure_ascii=True).encode("utf-8")
    tool_schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()
    return ExtractorInstrument(
        model_id=model,
        system_prompt_sha256=system_prompt_sha256,
        tool_schema_sha256=tool_schema_sha256,
    )


def _call_once(
    client: anthropic.Anthropic,
    body: str,
    model: str,
    system: str,
    tools: list[dict[str, Any]],
) -> list[Any]:
    """Make a single API call and return the raw clauses list.

    ``system`` and ``tools`` must be the same objects used to build the
    :class:`ExtractorInstrument` for this call.

    :raises ExtractorClaudeError: On API error, missing tool block, wrong input type,
        or 'clauses' field of unexpected type.  The last error is the transient
        anomaly that the retry path handles.
    """
    try:
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            tools=cast(Any, tools),
            tool_choice={"type": "tool", "name": "extract_clauses"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract all behavioral clauses from the following skill document.\n\n"
                        f"<skill_document>\n{body}\n</skill_document>"
                    ),
                }
            ],
        )
    except anthropic.APIError as exc:
        raise ExtractorClaudeError(f"Anthropic API error during clause extraction: {exc}") from exc

    # Find the tool_use block.
    tool_use_block = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_clauses":
            tool_use_block = block
            break

    if tool_use_block is None:
        raise ExtractorClaudeError(
            "Claude did not call the extract_clauses tool. "
            f"Stop reason: {response.stop_reason}. "
            f"Content blocks: {[b.type for b in response.content]}"
        )

    raw_input = tool_use_block.input
    if not isinstance(raw_input, dict):
        raise ExtractorClaudeError(
            f"Claude returned tool input of unexpected type: {type(raw_input).__name__}"
        )
    raw_clauses = raw_input.get("clauses", [])
    if not isinstance(raw_clauses, list):
        raise ExtractorClaudeError(
            f"Claude returned 'clauses' field of unexpected type: {type(raw_clauses).__name__}"
        )
    return raw_clauses


def call_extract_clauses(
    body: str, *, no_retry: bool = False
) -> tuple[list[ExtractedClause], ExtractorInstrument]:
    """Call Claude to extract clauses from ``body``.

    :param body: The skill document body text (post-frontmatter).
    :param no_retry: If True, disable the single retry on transient
        ``'clauses' field of unexpected type: str`` anomaly.  Use in CI or
        test contexts that require strict-fail behaviour.
    :returns: ``(clauses, instrument)`` — validated clauses and the instrument
        triple (model pin, system-prompt hash, tool-schema hash) computed from
        the exact strings sent on the request.
    :raises ExtractorClaudeError: On API error, empty result, or validation
        failure deserializing the tool call response.
    """
    client, model_for_routing = _make_extractor_client()
    # Build request identity once; hashes and messages.create share these values.
    system = _SYSTEM_PROMPT
    tools = _extract_clauses_tools()
    instrument = _instrument_from_request(model_for_routing, system, tools)

    try:
        raw_clauses = _call_once(client, body, model_for_routing, system, tools)
    except ExtractorClaudeError as exc:
        # Retry only the specific transient anomaly where the API returns the
        # 'clauses' field as a string instead of a list.  This was observed
        # once during dogfooding (2026-06-07); a second identical call succeeds.
        # Bounded scope: this error string only, one retry, no other retries.
        if not no_retry and "unexpected type" in str(exc) and "'clauses'" in str(exc):
            print(
                "[INFO] skill init: retrying transient extractor response anomaly...",
                file=sys.stderr,
            )
            time.sleep(1)
            raw_clauses = _call_once(client, body, model_for_routing, system, tools)
        else:
            raise

    if not raw_clauses:
        raise ExtractorClaudeError(
            "Claude returned zero clauses. The skill body may be empty or purely non-behavioral."
        )

    # Deserialise each clause through the Pydantic model for validation.
    # Any failure aborts: silent drop would record fewer clauses in evidence
    # than the source_sha256 attests, corrupting Coverage/Contribution metrics.
    clauses: list[ExtractedClause] = []
    errors: list[str] = []
    for i, raw in enumerate(raw_clauses):
        if not isinstance(raw, dict):
            errors.append(f"  clause[{i}]: not a dict, got {type(raw).__name__}")
            continue
        try:
            fc_raw = raw.get("falsifying_case")
            if fc_raw is not None:
                raw["falsifying_case"] = FalsifyingCaseSchema.model_validate(fc_raw)
            clauses.append(ExtractedClause.model_validate(raw))
        except (ValidationError, ValueError) as exc:
            errors.append(f"  clause[{i}]: {exc}")

    if errors:
        raise ExtractorClaudeError(
            f"{len(errors)} of {len(raw_clauses)} clauses failed validation:\n" + "\n".join(errors)
        )

    return clauses, instrument
