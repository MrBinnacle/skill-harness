"""Claude API wrapper for clause extraction.

Uses the Anthropic Python SDK with tool-use to extract structured clause
data from a skill body. Model: ``claude-sonnet-4-6`` (per CLAUDE.md
model-pinning for Track B execution work).

Tool design:
- Single tool ``extract_clauses`` with an ``input_schema`` that accepts a
  list of clause objects.
- ``tool_choice={"type": "tool", "name": "extract_clauses"}`` forces Claude
  to use the tool (no free-text fallback).
- The raw body is embedded verbatim in the user message.

D4 note: extractor calibration is deferred to v0.2 — no (extractor_id,
skill_genre) record is written here.
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import ValidationError

from skill_harness.extractor.errors import ExtractorClaudeError
from skill_harness.extractor.models import ExtractedClause, FalsifyingCaseSchema

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
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
  verbosity                     — output token/word count
  hedge_index                   — proportion of hedge words (maybe, perhaps, could, etc.)
  structure_score               — heading and paragraph-break density
  compliance_proxy              — directive-keyword density
  citation_presence_per_flag    — fraction of flagged items that include a citation marker
"""

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
                        "minimum": 0,
                        "description": "Zero-based authoring-order index.",
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
                                "exclusiveMinimum": 0.0,
                                "maximum": 1.0,
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


def call_extract_clauses(body: str) -> list[ExtractedClause]:
    """Call Claude to extract clauses from ``body``.

    :param body: The skill document body text (post-frontmatter).
    :returns: List of ``ExtractedClause`` objects.
    :raises ExtractorClaudeError: On API error, empty result, or validation
        failure deserializing the tool call response.
    """
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=8192,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "name": "extract_clauses",
                    "description": (
                        "Return all behavioral clauses extracted from the skill document."
                    ),
                    "input_schema": _EXTRACT_CLAUSES_SCHEMA,
                }
            ],
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

    return clauses
