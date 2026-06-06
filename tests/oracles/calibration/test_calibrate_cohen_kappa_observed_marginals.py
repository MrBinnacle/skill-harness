"""Tests for Cohen's κ (3-class) with observed marginals (A34).

Formula (Cohen 1960):
    κ = (p_o - p_e) / (1 - p_e)

    p_o = observed agreement = fraction of pairs where human and judge agreed
    p_e = chance baseline = sum_c (n_human_c/N) * (n_judge_c/N)
          for c in {A, B, tie}

The function takes per-pair (human, judge) tuples, derives marginals, and
computes both p_o and p_e from scratch. This test verifies that:

1. The formula uses *observed* marginals, NOT uniform 1/3 for each class.
2. The numerical result matches an independently derived computation.
3. Perfect agreement gives κ = 1.0.
4. No agreement above chance gives κ = 0.0 (approximately).
5. The chance_baseline (p_e) is correctly returned alongside κ.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------


def _kappa():  # type: ignore[return]
    from skill_harness.oracles.calibration.command import (
        cohen_kappa_observed_marginals,
    )

    return cohen_kappa_observed_marginals


# ---------------------------------------------------------------------------
# Perfect agreement
# ---------------------------------------------------------------------------


def test_perfect_agreement_kappa_is_one() -> None:
    """When human and judge always agree, κ = 1.0."""
    kappa_fn = _kappa()
    # 10 A, 10 B, 10 tie — perfect agreement
    pairs = [("A", "A")] * 10 + [("B", "B")] * 10 + [("tie", "tie")] * 10
    kappa, _p_e = kappa_fn(pairs)
    assert abs(kappa - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Observed marginals, not uniform
# ---------------------------------------------------------------------------


def test_kappa_uses_observed_marginals_not_uniform() -> None:
    """
    If 1/3-uniform assumption were used:
        p_e_uniform = 3 * (1/3)^2 = 1/3 ≈ 0.333

    With observed marginals where all 30 pairs are human=A, judge=A:
        p_human_A = 1.0, p_judge_A = 1.0
        p_e_observed = (1.0 * 1.0) + (0.0 * 0.0) + (0.0 * 0.0) = 1.0
        κ = (1.0 - 1.0) / (1 - 1.0) = undefined (division by zero edge case)

    More useful test: skewed distribution.
    Human: 20 A, 5 B, 5 tie. Judge: 20 A, 5 B, 5 tie. Perfect agreement.
    N = 30
    p_e_observed = (20/30)*(20/30) + (5/30)*(5/30) + (5/30)*(5/30)
                 = 0.4444 + 0.0278 + 0.0278 ≈ 0.500
    p_e_uniform  = 3 * (1/3)^2 = 0.333  ← DIFFERENT

    κ_observed = (1.0 - 0.500) / (1 - 0.500) = 1.0  (perfect agreement → κ=1)
    κ_uniform  = (1.0 - 0.333) / (1 - 0.333) = 1.0  (same for perfect agreement)

    For non-uniform but imperfect agreement, the marginal assumption matters.
    Use a case where marginals are skewed and agreement is partial:
    Human always says A (n=30); Judge says A for 20, B for 10.
    p_o = 20/30 (they agree on A for 20 pairs)
    p_e_observed = (30/30 * 20/30) + (0/30 * 10/30) + (0/30 * 0/30)
                 = (1.0 * 0.667) + 0 + 0 = 0.667
    κ_observed = (0.667 - 0.667) / (1 - 0.667) = 0.0
    p_e_uniform = 1/3*20/30 + 1/3*10/30 + 1/3*0/30 = 1/3  (wrong)
    """
    kappa_fn = _kappa()
    # Human: 30 A, 0 B, 0 tie; Judge: 20 A, 10 B, 0 tie
    # Agreement only on the 20 A+A pairs
    pairs = [("A", "A")] * 20 + [("A", "B")] * 10
    kappa, p_e = kappa_fn(pairs)

    # With observed marginals:
    # p_o = 20/30
    # p_e = (30/30) * (20/30) = 2/3
    # κ = (2/3 - 2/3) / (1 - 2/3) = 0
    expected_p_e = (30 / 30) * (20 / 30)  # ≈ 0.6667
    assert abs(p_e - expected_p_e) < 1e-9
    assert abs(kappa - 0.0) < 1e-9, f"Expected κ≈0.0, got {kappa}"

    # Verify the 1/3 uniform assumption would give different p_e
    p_e_uniform = (1 / 3) * (20 / 30) + (1 / 3) * (10 / 30) + (1 / 3) * 0
    assert abs(p_e - p_e_uniform) > 0.1, "p_e should differ from uniform assumption"


# ---------------------------------------------------------------------------
# Chance-level agreement → κ ≈ 0
# ---------------------------------------------------------------------------


def test_chance_level_agreement_kappa_near_zero() -> None:
    """When agreement matches marginals exactly, κ = 0."""
    kappa_fn = _kappa()
    # Equal marginals: human 15A, 15B; judge 15A, 15B
    # If agreement is exactly at chance: 7 or 8 A-A agreements
    # For exact κ=0: p_o must equal p_e.
    # p_e = (15/30)*(15/30) + (15/30)*(15/30) = 0.25 + 0.25 = 0.5
    # p_o = 0.5 → 15 agreements out of 30
    # Arrange: 7 A+A, 8 B+B, 8 A+B, 7 B+A = 30 total, 15 agreements
    pairs = [("A", "A")] * 7 + [("B", "B")] * 8 + [("A", "B")] * 8 + [("B", "A")] * 7
    kappa, p_e = kappa_fn(pairs)
    assert abs(p_e - 0.5) < 0.05  # marginals ~equal
    assert abs(kappa) < 0.1


# ---------------------------------------------------------------------------
# Numerical correctness against hand-computed example
# ---------------------------------------------------------------------------


def test_kappa_numerical_hand_computed() -> None:
    """Verify against a manually computed κ.

    N = 10 pairs:
      (A, A), (A, A), (A, A),   # 3 agree on A
      (B, B), (B, B),            # 2 agree on B
      (tie, tie),                # 1 agree on tie
      (A, B), (B, A),            # 2 disagree
      (A, tie), (B, tie)         # 2 disagree

    Human: A=5, B=3, tie=1 → wait, let me recount.
    Human: A,A,A,B,B,tie,A,B,A,B  → A=5, B=4, tie=1
    Judge: A,A,A,B,B,tie,B,A,tie,tie → A=4, B=3, tie=3
    Agreements: pos0(A,A), pos1(A,A), pos2(A,A), pos3(B,B), pos4(B,B), pos5(tie,tie) → 6/10

    p_o = 6/10 = 0.6
    p_e = (5/10)*(4/10) + (4/10)*(3/10) + (1/10)*(3/10)
        = 0.20 + 0.12 + 0.03 = 0.35
    κ = (0.6 - 0.35) / (1 - 0.35) = 0.25 / 0.65 ≈ 0.3846
    """
    kappa_fn = _kappa()
    pairs = [
        ("A", "A"),
        ("A", "A"),
        ("A", "A"),
        ("B", "B"),
        ("B", "B"),
        ("tie", "tie"),
        ("A", "B"),
        ("B", "A"),
        ("A", "tie"),
        ("B", "tie"),
    ]
    kappa, p_e = kappa_fn(pairs)
    expected_p_e = 0.35
    expected_kappa = (0.6 - 0.35) / (1 - 0.35)
    assert abs(p_e - expected_p_e) < 1e-9
    assert abs(kappa - expected_kappa) < 1e-9


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------


def test_kappa_returns_tuple_kappa_and_p_e() -> None:
    """Return value is (kappa: float, p_e: float) per A34 spec."""
    kappa_fn = _kappa()
    pairs = [("A", "A")] * 5 + [("B", "B")] * 5
    result = kappa_fn(pairs)
    assert isinstance(result, tuple)
    assert len(result) == 2
    kappa, p_e = result
    assert isinstance(kappa, float)
    assert isinstance(p_e, float)
    assert 0.0 <= p_e <= 1.0
