"""Tests for three-tier admissibility state determination (A34).

N < 50    → rejected
50 ≤ N < 100 → conditional
N ≥ 100   → calibrated (if all four metric thresholds pass)
          → rejected   (if any threshold fails at N≥100)

Thresholds (A34 / llm-judge-calibration Discipline 4):
  pairwise_agreement ≥ 0.7
  position_consistency ≥ 0.8
  cohen_kappa ≥ 0.4
  length_controlled_agreement ≥ 0.65 (skipped when None — C.4 scope)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


def _determine_state():  # type: ignore[return]
    from skill_harness.oracles.calibration.command import determine_state

    return determine_state


# ---------------------------------------------------------------------------
# N < 50 → rejected regardless of metrics
# ---------------------------------------------------------------------------


def test_n_below_50_is_rejected() -> None:
    """N=49 must return rejected (insufficient pair set size)."""
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=49,
        pairwise_agreement=0.95,
        position_consistency=0.95,
        length_controlled_agreement=None,
        cohen_kappa=0.8,
    )
    assert state == "rejected"
    assert reason == "pair_set_size_below_floor"


def test_n_zero_is_rejected() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=0,
        pairwise_agreement=1.0,
        position_consistency=1.0,
        length_controlled_agreement=None,
        cohen_kappa=1.0,
    )
    assert state == "rejected"
    assert reason == "pair_set_size_below_floor"


# ---------------------------------------------------------------------------
# 50 ≤ N < 100 → conditional (regardless of threshold pass/fail)
# ---------------------------------------------------------------------------


def test_n_50_is_conditional() -> None:
    """N=50 must return conditional regardless of metric values."""
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=50,
        pairwise_agreement=0.95,
        position_consistency=0.95,
        length_controlled_agreement=None,
        cohen_kappa=0.8,
    )
    assert state == "conditional"
    assert reason == "underpowered_50_99"


def test_n_99_is_conditional() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=99,
        pairwise_agreement=0.95,
        position_consistency=0.95,
        length_controlled_agreement=None,
        cohen_kappa=0.8,
    )
    assert state == "conditional"
    assert reason == "underpowered_50_99"


def test_n_75_is_conditional_even_with_poor_metrics() -> None:
    """At 50≤N<100, state is always conditional — not rejected — per A34."""
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=75,
        pairwise_agreement=0.1,
        position_consistency=0.1,
        length_controlled_agreement=0.1,
        cohen_kappa=-0.5,
    )
    assert state == "conditional"
    assert reason == "underpowered_50_99"


# ---------------------------------------------------------------------------
# N ≥ 100 — all thresholds pass → calibrated
# ---------------------------------------------------------------------------


def test_n_100_all_thresholds_pass_is_calibrated() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.7,
        position_consistency=0.8,
        length_controlled_agreement=None,  # C.4 scope — skipped
        cohen_kappa=0.4,
    )
    assert state == "calibrated"
    assert reason is None


def test_n_200_high_metrics_is_calibrated() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=200,
        pairwise_agreement=0.90,
        position_consistency=0.95,
        length_controlled_agreement=0.85,
        cohen_kappa=0.75,
    )
    assert state == "calibrated"
    assert reason is None


# ---------------------------------------------------------------------------
# N ≥ 100 — individual threshold failures → rejected
# ---------------------------------------------------------------------------


def test_n_100_pairwise_agreement_below_threshold() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.699,  # just below 0.7
        position_consistency=0.9,
        length_controlled_agreement=None,
        cohen_kappa=0.6,
    )
    assert state == "rejected"
    assert reason == "pairwise_agreement_below_threshold"


def test_n_100_position_consistency_below_threshold() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.75,
        position_consistency=0.799,  # just below 0.8
        length_controlled_agreement=None,
        cohen_kappa=0.6,
    )
    assert state == "rejected"
    assert reason == "position_consistency_below_threshold"


def test_n_100_cohen_kappa_below_threshold() -> None:
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.75,
        position_consistency=0.85,
        length_controlled_agreement=None,
        cohen_kappa=0.399,  # just below 0.4
    )
    assert state == "rejected"
    assert reason == "cohen_kappa_below_threshold"


def test_n_100_length_controlled_below_threshold_when_provided() -> None:
    """When length_controlled_agreement is provided and below 0.65 → rejected."""
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.75,
        position_consistency=0.85,
        length_controlled_agreement=0.649,  # just below 0.65
        cohen_kappa=0.6,
    )
    assert state == "rejected"
    assert reason == "length_controlled_below_threshold"


def test_n_100_length_controlled_none_skips_check() -> None:
    """When length_controlled_agreement is None, skip threshold check (C.4 scope)."""
    determine_state = _determine_state()
    state, reason = determine_state(
        n_pairs=100,
        pairwise_agreement=0.75,
        position_consistency=0.85,
        length_controlled_agreement=None,  # C.4 not yet computed
        cohen_kappa=0.6,
    )
    assert state == "calibrated"
    assert reason is None
