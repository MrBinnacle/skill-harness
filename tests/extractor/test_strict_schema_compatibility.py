"""The extract_clauses schema must stay compatible with strict tool use.

⛔ WHY THIS FILE EXISTS. `strict: True` makes the API *guarantee* that
`tool_use.input` validates against the schema — but it also restricts which
JSON-Schema keywords the schema may use. Numeric bounds (`minimum`, `maximum`,
`exclusiveMinimum`, ...) are rejected with a 400 at request time.

That failure is invisible to every offline check. `tests/extractor/test_claude.py`
mocks `anthropic.Anthropic`, so a schema the real API refuses still passes lint,
`mypy --strict`, and all four CI test cells. A schema regression here breaks
100% of live extractions while CI stays green.

These tests walk the schema structurally so the incompatibility is caught without
a network call.
"""

from __future__ import annotations

from typing import Any

import pytest

from skill_harness.extractor.claude import (
    _EXTRACT_CLAUSES_SCHEMA,
    _STRICT_BANNED_KEYWORDS,
)


def _walk(node: Any, path: str = "$") -> list[tuple[str, str]]:
    """Yield ``(json_path, keyword)`` for every banned keyword anywhere in the schema."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _STRICT_BANNED_KEYWORDS:
                found.append((path, key))
            found.extend(_walk(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_walk(value, f"{path}[{i}]"))
    return found


def test_schema_uses_no_strict_incompatible_keywords() -> None:
    """The live 400 this prevents: 'For integer type, property minimum is not supported'."""
    offenders = _walk(_EXTRACT_CLAUSES_SCHEMA)
    assert offenders == [], (
        "extract_clauses schema contains keyword(s) that strict tool use rejects with a "
        f"400, breaking every live extraction: {offenders}. "
        "Numeric bounds belong on the pydantic model (ExtractedClause / "
        "FalsifyingCaseSchema), not in the tool schema."
    )


def test_walker_would_catch_a_regression() -> None:
    """The guard must actually fire — a test that can never fail guards nothing."""
    poisoned = {
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 0}},
    }
    assert _walk(poisoned) == [("$.properties.n", "minimum")]


def test_strict_preconditions_still_hold() -> None:
    """Strict mode also requires additionalProperties:false and required at each level."""
    clause = _EXTRACT_CLAUSES_SCHEMA["properties"]["clauses"]["items"]
    assert _EXTRACT_CLAUSES_SCHEMA["additionalProperties"] is False
    assert clause["additionalProperties"] is False
    assert clause["required"], "clause object must declare required fields under strict"


@pytest.mark.parametrize("keyword", ["minLength", "description", "enum"])
def test_permitted_keywords_are_not_banned(keyword: str) -> None:
    """Guard against over-correction: these are legal under strict and must stay usable.

    The live probe confirmed a schema retaining `minLength` succeeds once the numeric
    bounds are removed, so banning length keywords too would be cargo-culting.
    """
    assert keyword not in _STRICT_BANNED_KEYWORDS
