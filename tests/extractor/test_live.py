"""Live integration test: calls the real Anthropic API.

Marked ``@pytest.mark.live`` — excluded from CI's run (``-m "not live"``,
which local runs should mirror; a bare ``pytest`` does NOT deselect it).
Run explicitly with::

    pytest -m live tests/extractor/test_live.py

Requires ANTHROPIC_API_KEY in the environment.

Exit criteria (per dispatch spec): ``skill init <path>`` on
ai-slop-sentinel/SKILL.md emits ≥5 clauses, each with
axis/comparator/oracle_tier/vacuity_flag populated, and
falsifying_case_schema_sha256 populated for constructible clauses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_harness.extractor.pipeline import extract_skill

_AI_SLOP_SENTINEL = Path.home() / ".claude" / "skills" / "ai-slop-sentinel" / "SKILL.md"


@pytest.mark.live
@pytest.mark.skipif(
    not _AI_SLOP_SENTINEL.exists(),
    reason="ai-slop-sentinel SKILL.md not found at expected path",
)
def test_live_extract_ai_slop_sentinel() -> None:
    """Full end-to-end extraction of ai-slop-sentinel/SKILL.md.

    Assertions:
    - At least 5 clauses extracted.
    - Every clause has axis, comparator, oracle_tier, vacuity_flag populated.
    - Every clause with vacuity_flag='none' has a non-None falsifying_case.
    - The falsifying_case.sha256_hex() is a 64-char hex string.
    """
    result = extract_skill(_AI_SLOP_SENTINEL, evidence_conn=None)

    assert len(result.clauses) >= 5, (
        f"Expected ≥5 clauses, got {len(result.clauses)}. "
        f"Clauses: {[c.clause_text[:40] for c in result.clauses]}"
    )

    for clause in result.clauses:
        # Required fields populated.
        assert clause.axis, f"Clause {clause.clause_index}: axis is empty"
        assert clause.comparator in (
            "increase",
            "decrease",
            "preserve",
            "comparator_unspecified",
        ), f"Clause {clause.clause_index}: invalid comparator '{clause.comparator}'"
        assert clause.oracle_tier in (1, 2, 3), (
            f"Clause {clause.clause_index}: invalid oracle_tier {clause.oracle_tier}"
        )
        assert clause.vacuity_flag in ("none", "semantic_vacuous_pending_review"), (
            f"Clause {clause.clause_index}: invalid vacuity_flag '{clause.vacuity_flag}'"
        )

        # Falsifying case populated for non-vacuous clauses.
        if clause.vacuity_flag == "none":
            assert clause.falsifying_case is not None, (
                f"Clause {clause.clause_index} has vacuity_flag='none' but no falsifying_case"
            )
            sha = clause.falsifying_case.sha256_hex()
            assert len(sha) == 64, (
                f"Clause {clause.clause_index}: sha256_hex length {len(sha)} != 64"
            )
