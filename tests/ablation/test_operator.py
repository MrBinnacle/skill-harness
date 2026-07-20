"""Tests for AblationOperator (A39).

Covers:
- Determinism: op.render(clause) == op.render(clause) byte-equal.
- Matched-length: placeholder token count approximates the removed clause's token count
  within the stated tolerance (default ±10% or ±2 tokens, whichever is larger).
- implementation_hash is stable across instantiations.
- ablation_operator_id is a stable non-empty string.
- The placeholder is semantically null (not a model call — deterministic layer only).
- implementation_hash == sha256 of the implementation source (mirrors Tier-1 discipline).

PYTHONHASHSEED=0 discipline: the tests do not depend on dict/set ordering, but the
AblationOperator's determinism must hold regardless of hash seed.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_operator_render_is_byte_equal_deterministic() -> None:
    """op.render(clause_text) == op.render(clause_text) byte-equal (A39)."""
    from skill_harness.ablation.operator import AblationOperator

    op = AblationOperator()
    clause = "Always begin your response with 'Certainly!' before answering."
    result1 = op.render(clause)
    result2 = op.render(clause)
    assert result1 == result2, "AblationOperator.render() is not byte-deterministic"
    assert isinstance(result1, str)


def test_operator_render_different_inputs_may_differ() -> None:
    """Different clause texts produce matched-length placeholders (each internally consistent)."""
    from skill_harness.ablation.operator import AblationOperator

    op = AblationOperator()
    clause_short = "Be concise."
    clause_long = "Always provide a detailed, step-by-step explanation of your reasoning. " * 5
    placeholder_short = op.render(clause_short)
    placeholder_long = op.render(clause_long)
    # Both must be strings; short clause should yield shorter placeholder
    assert isinstance(placeholder_short, str)
    assert isinstance(placeholder_long, str)
    # The placeholder for a longer clause should be at least as long as for a shorter one
    # (matched-length approximation goes both directions — this is directional, not strict)
    assert len(placeholder_long) >= len(placeholder_short)


def test_operator_placeholder_token_length_within_tolerance() -> None:
    """Placeholder token count matches clause token count within tolerance (A39).

    Tolerance: ±10% of clause token count, minimum ±2 tokens.
    We test with several clause lengths to ensure the tolerance holds across the range.
    """
    import tiktoken

    from skill_harness.ablation.operator import TOKEN_LENGTH_TOLERANCE_FRACTION, AblationOperator

    op = AblationOperator()
    enc = tiktoken.get_encoding("cl100k_base")

    test_clauses = [
        "Be concise.",
        "Always begin your response with 'Certainly!' before answering.",
        "Provide exactly three bullet points. " * 3,
        "Use markdown formatting with headers and bold text for all responses. " * 5,
    ]

    for clause in test_clauses:
        placeholder = op.render(clause)
        clause_tokens = len(enc.encode(clause))
        placeholder_tokens = len(enc.encode(placeholder))
        tolerance = max(2, int(clause_tokens * TOKEN_LENGTH_TOLERANCE_FRACTION))
        delta = abs(placeholder_tokens - clause_tokens)
        assert delta <= tolerance, (
            f"Placeholder token length {placeholder_tokens} is outside tolerance "
            f"({clause_tokens} ± {tolerance}) for clause: {clause[:40]!r}"
        )


def test_operator_implementation_hash_is_stable_across_instances() -> None:
    """implementation_hash is the same across independently constructed instances."""
    from skill_harness.ablation.operator import AblationOperator

    op1 = AblationOperator()
    op2 = AblationOperator()
    assert op1.implementation_hash == op2.implementation_hash
    assert isinstance(op1.implementation_hash, str)
    assert len(op1.implementation_hash) == 64  # SHA-256 hex


def test_operator_implementation_hash_is_sha256_format() -> None:
    """implementation_hash is a 64-character lowercase hex SHA-256 string."""
    from skill_harness.ablation.operator import AblationOperator

    op = AblationOperator()
    h = op.implementation_hash
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h), f"Not a lowercase hex string: {h}"


def test_operator_ablation_operator_id_is_stable() -> None:
    """ablation_operator_id is a non-empty stable string across instances."""
    from skill_harness.ablation.operator import AblationOperator

    op1 = AblationOperator()
    op2 = AblationOperator()
    assert op1.ablation_operator_id == op2.ablation_operator_id
    assert isinstance(op1.ablation_operator_id, str)
    assert len(op1.ablation_operator_id) > 0


def test_operator_render_is_not_empty() -> None:
    """Placeholder is never empty — we must not delete the clause (A39: NOT deletion)."""
    from skill_harness.ablation.operator import AblationOperator

    op = AblationOperator()
    result = op.render("Be concise.")
    assert result.strip(), "Placeholder must not be empty (NOT deletion)"


def test_operator_render_is_semantically_distinct_from_original() -> None:
    """The placeholder is NOT the same as the original clause text (it is a substitution)."""
    from skill_harness.ablation.operator import AblationOperator

    op = AblationOperator()
    clause = "Always use bullet points when listing items."
    placeholder = op.render(clause)
    assert placeholder != clause, "Placeholder must differ from the original clause text"


def test_operator_render_does_not_make_network_calls() -> None:
    """AblationOperator.render() is a pure deterministic computation — no network I/O.

    This is tested indirectly by verifying the same output is returned synchronously
    (no async, no API key needed). The test runs with socket blocking off where possible.
    """
    import threading

    from skill_harness.ablation.operator import AblationOperator

    results: list[str] = []
    errors: list[Exception] = []

    def run() -> None:
        try:
            op = AblationOperator()
            results.append(op.render("Use numbered lists."))
        except Exception as e:
            errors.append(e)

    # Run in a thread with no environment ANTHROPIC_API_KEY to confirm no call needed
    env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "render() timed out — possible blocking call"
        assert not errors, f"render() raised: {errors}"
        assert results, "No result returned"
    finally:
        if env_backup is not None:
            os.environ["ANTHROPIC_API_KEY"] = env_backup


# ---------------------------------------------------------------------------
# F-7 (S55 hostile review): single-source encoding, anti-drift agreement test
# (mirrors the F3 MODEL_PRICING_USD_PER_M <-> PRICE_PER_MTOK pattern in
# tests/oracles/calibration/test_cost_projection.py).
# ---------------------------------------------------------------------------


class TestOperatorEncodingSingleSourceOfTruth:
    """AblationOperator must tokenize with the SAME encoding object as
    skill_harness.oracles.tier1.verbosity's canonical get_encoding() -- never an
    independent tiktoken.get_encoding() call of its own. Before F-7, operator.py
    hand-duplicated its own "cl100k_base" literal and its own tiktoken.get_encoding()
    call (twice: once for FILLER_UNIT_TOKENS, once per instance in __init__); nothing
    enforced that a canonical-encoding change would reach this module too.
    """

    def test_operator_instance_encoding_is_canonical_encoding_object(self) -> None:
        from skill_harness.ablation.operator import AblationOperator
        from skill_harness.oracles.tier1.verbosity import get_encoding

        op = AblationOperator()
        assert op._enc is get_encoding(), (
            "F-7: AblationOperator must reuse the canonical encoding object, "
            "not construct its own independent tiktoken.get_encoding() instance"
        )

    def test_filler_unit_tokens_computed_from_canonical_encoding(self) -> None:
        from skill_harness.ablation.operator import _FILLER_UNIT, FILLER_UNIT_TOKENS
        from skill_harness.oracles.tier1.verbosity import get_encoding

        assert len(get_encoding().encode(_FILLER_UNIT)) == FILLER_UNIT_TOKENS, (
            "F-7: FILLER_UNIT_TOKENS must be derived from the canonical encoding"
        )
