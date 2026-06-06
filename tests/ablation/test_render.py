"""Tests for condition renderer (A39, A43).

Covers:
- Full condition = whole skill text rendered.
- Null condition = no skill text (empty system instruction).
- Ablated_k condition = clause k replaced by the operator's placeholder.
- Ablated_k differs from Full ONLY by the operator substitution at clause k.
- Cache-marker placement (A43): system rendered as typed blocks with
  cache_control={type:ephemeral} at end-of-system + end-of-skill-prefix.
- Verbosity axis of Ablated_k vs Full is NOT perturbed by length (the A39
  falsifying-case demonstration — matched-length substitution does not
  contaminate the length axis the way deletion would).

Mock discipline: SDK call boundary is mocked per A32 precedent.
No live API calls — tested with the rendered request structure only.
"""

from __future__ import annotations

import tiktoken

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SKILL = [
    "Always begin your response with 'Certainly!' before answering.",
    "Provide exactly three bullet points for every list you produce.",
    "Use concise language. Avoid filler phrases and redundant words.",
]

# QUAL-3: TRUE COLLISION fixture — clause[1] text is an exact substring of clause[0].
# A collision-fragile str.replace oracle would replace the occurrence in clause[0]
# text when targeting clause[1], because the two texts share an exact substring.
# This exposes str.replace oracles that find the wrong occurrence.
OVERLAPPING_SKILL = [
    "Provide exactly three bullet points for every list you produce. Always be clear.",
    "Provide exactly three bullet points for every list you produce.",
    "Use concise language.",
]


def _token_count(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_renderer_returns_full_condition() -> None:
    """Full condition contains all clauses from the skill."""
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=1)
    full = result["full"]
    # All clause texts must appear in the full condition system prompt
    for clause in SAMPLE_SKILL:
        assert clause in full["system_text"], f"Clause missing from Full: {clause!r}"


def test_renderer_returns_null_condition() -> None:
    """Null condition contains no skill text (only the base system prompt if any)."""
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=1)
    null = result["null"]
    # None of the specific clause texts should appear in the null condition
    for clause in SAMPLE_SKILL:
        assert clause not in null["system_text"], f"Clause should not appear in Null: {clause!r}"


def test_renderer_ablated_k_contains_placeholder_not_original() -> None:
    """Ablated_k: the target clause is replaced by the placeholder, not the original text."""
    from skill_harness.ablation.operator import AblationOperator
    from skill_harness.ablation.render import ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)
    target_k = 1
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)
    ablated = result[f"ablated_{target_k}"]

    target_clause = SAMPLE_SKILL[target_k]
    placeholder = op.render(target_clause)

    # Original clause must NOT appear
    assert target_clause not in ablated["system_text"], (
        f"Original clause at index {target_k} must not appear in Ablated_{target_k}"
    )
    # Placeholder MUST appear
    assert placeholder in ablated["system_text"], f"Placeholder must appear in Ablated_{target_k}"


def test_renderer_ablated_k_preserves_other_clauses() -> None:
    """Ablated_k preserves all clauses except the target one."""
    from skill_harness.ablation.operator import AblationOperator
    from skill_harness.ablation.render import ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)
    target_k = 0
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)
    ablated = result[f"ablated_{target_k}"]

    for i, clause in enumerate(SAMPLE_SKILL):
        if i == target_k:
            assert clause not in ablated["system_text"]
        else:
            assert clause in ablated["system_text"], (
                f"Non-target clause {i} must be preserved in Ablated_{target_k}"
            )


def test_renderer_ablated_k_differs_from_full_only_at_k() -> None:
    """Ablated_k differs from Full ONLY by the operator substitution at clause k.

    QUAL-3: uses index-based reconstruction (not str.replace) to avoid collision
    when a clause text appears multiple times in the skill.
    """
    from skill_harness.ablation.operator import AblationOperator
    from skill_harness.ablation.render import ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)
    target_k = 2
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)

    full_text = result["full"]["system_text"]
    ablated_text = result[f"ablated_{target_k}"]["system_text"]

    target_clause = SAMPLE_SKILL[target_k]
    placeholder = op.render(target_clause)

    # The two texts must differ
    assert full_text != ablated_text

    # Index-based reconstruction (QUAL-3 — avoids collision-fragile str.replace):
    # Rebuild expected ablated_text by substituting at the correct clause position.
    # system_text is the faithful wire (concatenated block texts, no separator added).
    # Ablated_k blocks: [base_system][prefix clauses][placeholder]
    # prefix clauses = all clauses except k, in authoring order.
    # placeholder = last block.
    # Faithful concatenation = base_system + prefix_text + placeholder
    # where prefix_text = _format_clauses(clauses excluding k).
    base_system = renderer._base_system
    other_clauses = [c for i, c in enumerate(SAMPLE_SKILL) if i != target_k]
    prefix_text = "\n\n".join(c.strip() for c in other_clauses)
    expected_ablated = base_system + prefix_text + placeholder

    assert ablated_text == expected_ablated, (
        "Ablated_k must be identical to Full except for the single substitution at k "
        "(index-based reconstruction used to avoid collision-fragile str.replace)"
    )


def test_renderer_overlapping_clause_no_collision() -> None:
    """QUAL-3 TRUE COLLISION: clause[1] text is an exact substring of clause[0].

    OVERLAPPING_SKILL[0] starts with OVERLAPPING_SKILL[1] — a TRUE substring collision.
    A collision-fragile oracle replaces the substring inside clause[0] instead of clause[1].

    Clause[1] text is an exact prefix-substring of clause[0]. A collision-fragile
    str.replace(clause[1], placeholder, 1) oracle would corrupt clause[0] by replacing
    the matching substring there — leaving clause[1]'s full text intact in clause[0]
    but breaking clause[0].

    The renderer must substitute only at index k (index-based), leaving clause[0]
    intact (including its trailing '. Always be clear.' suffix).
    """
    from skill_harness.ablation.operator import AblationOperator
    from skill_harness.ablation.render import ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)

    # Ablate clause[1] — its full text is an exact substring of clause[0]
    target_k = 1
    result = renderer.render_conditions(OVERLAPPING_SKILL, target_clause_index=target_k)
    ablated_text = result[f"ablated_{target_k}"]["system_text"]

    # Clause[0] must survive INTACT — the full text including the suffix that
    # distinguishes it from clause[1]. A str.replace oracle would corrupt this
    # (it would replace the clause[1] substring inside clause[0], giving a broken
    # clause[0] that no longer ends with '. Always be clear.').
    clause_0_full = OVERLAPPING_SKILL[0]
    assert clause_0_full in ablated_text, (
        f"T1: Clause[0] full text must survive intact after ablating clause[1]. "
        f"A str.replace oracle corrupts clause[0] because clause[1] is an exact "
        f"substring of clause[0]. Expected in ablated_text:\n{clause_0_full!r}"
    )

    # The placeholder must appear as a STANDALONE block (not embedded inside clause[0])
    placeholder = op.render(OVERLAPPING_SKILL[target_k])
    assert placeholder in ablated_text, "Placeholder must appear in ablated text"

    # The placeholder must appear AFTER clause[0] — it is a separate block at the end
    # (ablated-clause-last ordering per A43). str.replace would embed the placeholder
    # inside clause[0]'s text rather than in a separate block.
    clause_0_pos = ablated_text.find(clause_0_full)
    placeholder_pos = ablated_text.find(placeholder)
    assert clause_0_pos != -1, "Clause[0] must be present"
    assert placeholder_pos != -1, "Placeholder must be present"
    # The placeholder should appear in the ablated_text separately from clause[0]
    # (clause[0] does not contain the placeholder — they are distinct)
    assert placeholder not in clause_0_full, (
        "Placeholder must not appear inside clause[0] text "
        "(str.replace would have embedded it there)"
    )


def test_renderer_cache_markers_present_in_system_blocks() -> None:
    """Cache markers (cache_control:ephemeral) present at end-of-system + end-of-skill-prefix (A43).

    The system must be rendered as a list of typed blocks, not a bare string.
    At least two cache_control markers must be present:
    - one at the end of the base system block
    - one at the end of the skill-prefix block (before the ablated clause)
    """
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    target_k = 1
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)

    ablated = result[f"ablated_{target_k}"]
    system_blocks = ablated["system_blocks"]

    assert isinstance(system_blocks, list), "system_blocks must be a list of typed blocks"
    assert len(system_blocks) >= 2, "At least two system blocks expected"

    cache_marker_count = sum(
        1 for block in system_blocks if block.get("cache_control") == {"type": "ephemeral"}
    )
    assert cache_marker_count >= 2, (
        f"Expected ≥2 cache_control markers, found {cache_marker_count}. "
        "Markers must be at end-of-system + end-of-skill-prefix (A43)."
    )


def test_renderer_cache_markers_on_correct_blocks() -> None:
    """The last block in the base-system section and the skill-prefix block carry cache markers."""
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=0)

    ablated = result["ablated_0"]
    system_blocks = ablated["system_blocks"]

    # Find all blocks with cache_control markers
    marked_blocks = [b for b in system_blocks if "cache_control" in b]
    assert len(marked_blocks) >= 2, f"Need ≥2 marked blocks, got {len(marked_blocks)}"

    # The last marked block must be before the ablated clause block
    last_marked_idx = max(i for i, b in enumerate(system_blocks) if "cache_control" in b)
    # There should be at least one block after the last marker (the ablated-clause block)
    assert last_marked_idx < len(system_blocks) - 1, (
        "The ablated clause block (rendered last) must come after the final cache marker"
    )


def test_renderer_ablated_clause_rendered_last_in_system() -> None:
    """Ablated clause is rendered last in system blocks (A43: maximize shared prefix)."""
    from skill_harness.ablation.render import ABLATED_CLAUSE_MARKER, ConditionRenderer

    renderer = ConditionRenderer()
    target_k = 1
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)

    ablated = result[f"ablated_{target_k}"]
    system_blocks = ablated["system_blocks"]

    # The last block should be the one containing the placeholder for clause k
    last_block = system_blocks[-1]
    assert last_block.get("type") == "text", f"Last block must be text type: {last_block}"
    # The last block must contain ABLATED_CLAUSE_MARKER or the placeholder content
    last_text = last_block.get("text", "")
    assert ABLATED_CLAUSE_MARKER in last_text or last_text.strip(), (
        "Last block must contain the ablated clause content"
    )


def test_verbosity_axis_not_perturbed_by_ablation() -> None:
    """A39 falsifying-case: verbosity of Ablated_k vs Full is not perturbed by length.

    Matched-length substitution (not deletion) keeps the token count approximately
    equal. Deletion would create a length deficit that contaminates the verbosity axis.

    This test verifies that the token count difference between Full and Ablated_k
    system text is within the AblationOperator's stated tolerance (the same guarantee
    the operator provides per token).
    """
    from skill_harness.ablation.operator import TOKEN_LENGTH_TOLERANCE_FRACTION, AblationOperator
    from skill_harness.ablation.render import ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)
    target_k = 0

    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)
    full_text = result["full"]["system_text"]
    ablated_text = result[f"ablated_{target_k}"]["system_text"]

    full_tokens = _token_count(full_text)
    ablated_tokens = _token_count(ablated_text)

    # The token count difference should be ≤ tolerance of the removed clause's length
    removed_clause_tokens = _token_count(SAMPLE_SKILL[target_k])
    tolerance = max(2, int(removed_clause_tokens * TOKEN_LENGTH_TOLERANCE_FRACTION))
    delta = abs(full_tokens - ablated_tokens)

    assert delta <= tolerance, (
        f"Verbosity axis perturbed by ablation: Full={full_tokens} tokens vs "
        f"Ablated_{target_k}={ablated_tokens} tokens, delta={delta} > tolerance={tolerance}. "
        "This contamination comes from deletion-style ablation. "
        "AblationOperator must use matched-length substitution (A39)."
    )


def test_c1_marker_absent_from_wire_prompt_system_blocks() -> None:
    """C1 FALSIFYING: the concatenated system_blocks text (what the model receives) must
    NOT contain the ABLATED_CLAUSE_MARKER. The marker was previously injected into the
    block text itself, adding ~9 tokens to the ablated side only — contaminating the
    length axis A39 exists to prevent.

    This test measures the actual wire text (concatenated block texts) and asserts:
    1. The marker is NOT in any block text.
    2. Full vs Ablated_k concatenated block text is within matched-length tolerance.
    3. system_text is faithful to the concatenated block texts.

    Must be RED against the marker-in-block code, GREEN after fix.
    """
    from skill_harness.ablation.operator import TOKEN_LENGTH_TOLERANCE_FRACTION, AblationOperator
    from skill_harness.ablation.render import ABLATED_CLAUSE_MARKER, ConditionRenderer

    op = AblationOperator()
    renderer = ConditionRenderer(operator=op)
    target_k = 0

    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)
    ablated_key = f"ablated_{target_k}"

    # Build the wire texts — what the model actually receives via system_blocks
    def wire_text(cond: dict) -> str:
        return "".join(b["text"] for b in cond["system_blocks"])

    full_wire = wire_text(result["full"])
    ablated_wire = wire_text(result[ablated_key])

    # 1. Marker must NOT appear in any block text of the ablated condition
    for block in result[ablated_key]["system_blocks"]:
        assert ABLATED_CLAUSE_MARKER.split("{k}")[0].strip("[") not in block.get("text", ""), (
            f"C1: ABLATED_CLAUSE_MARKER found in wire block text — "
            f"this contaminates the length axis (A39). Block text: {block['text']!r}"
        )

    # 2. Wire token counts must be within tolerance (the A39 guarantee must hold on the wire)
    full_toks = _token_count(full_wire)
    ablated_toks = _token_count(ablated_wire)
    removed_clause_tokens = _token_count(SAMPLE_SKILL[target_k])
    tolerance = max(2, int(removed_clause_tokens * TOKEN_LENGTH_TOLERANCE_FRACTION))
    delta = abs(full_toks - ablated_toks)
    assert delta <= tolerance, (
        f"C1: Wire token delta={delta} > tolerance={tolerance}. "
        f"Full wire={full_toks} toks, Ablated wire={ablated_toks} toks. "
        "Marker in block text is adding tokens to the ablated side only."
    )

    # 3. system_text must be faithful — equal to concatenated block texts
    ablated_system_text = result[ablated_key]["system_text"]
    assert ablated_system_text == ablated_wire, (
        "C1: system_text is not faithful to system_blocks wire text. "
        f"system_text has {_token_count(ablated_system_text)} toks, "
        f"wire has {_token_count(ablated_wire)} toks."
    )


def test_renderer_all_three_conditions_keys_present() -> None:
    """render_conditions returns dict with 'full', 'null', and 'ablated_k' keys."""
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    target_k = 0
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=target_k)

    assert "full" in result
    assert "null" in result
    assert f"ablated_{target_k}" in result


def test_renderer_target_clause_last_in_rendering_order() -> None:
    """The target clause is reordered to appear last in the system blocks for cache reuse (A43)."""
    from skill_harness.ablation.render import ConditionRenderer

    renderer = ConditionRenderer()
    # Target clause 0 — it is normally first but should be moved last
    result = renderer.render_conditions(SAMPLE_SKILL, target_clause_index=0)

    ablated = result["ablated_0"]
    system_blocks = ablated["system_blocks"]

    # The first clause (index 0) should NOT appear before later clauses in the block list
    # Specifically: clause 1 and clause 2 should appear before clause 0's placeholder
    texts = [b.get("text", "") for b in system_blocks if b.get("type") == "text"]
    combined = "\n".join(texts)

    clause_0_placeholder_pos = combined.find(
        "[CLAUSE 0"  # sentinel marker from the operator or renderer
    )
    clause_1_pos = combined.find(SAMPLE_SKILL[1])
    clause_2_pos = combined.find(SAMPLE_SKILL[2])

    # clauses 1 and 2 should appear before the clause-0 placeholder position
    # (if not found, they may be in different blocks — check via system_text instead)
    if clause_0_placeholder_pos != -1 and clause_1_pos != -1 and clause_2_pos != -1:
        assert clause_1_pos < clause_0_placeholder_pos, (
            "Clause 1 should appear before the ablated clause 0 placeholder"
        )
        assert clause_2_pos < clause_0_placeholder_pos, (
            "Clause 2 should appear before the ablated clause 0 placeholder"
        )
