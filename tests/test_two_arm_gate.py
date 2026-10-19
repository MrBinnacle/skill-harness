"""Tests for the two-arm posterior-difference gate (DIF screen K7).

Per the DIF design-council record (K7): independent Beta(1+w, 1+n-w) posteriors
per condition; gate on P(p_treatment - p_control > delta) >= prob_threshold,
two-sided on arm
direction (treatment-better / null / treatment-worse). delta and threshold
are frozen pre-spend by the caller's pre-registration.
"""

from __future__ import annotations

import pytest

from skill_harness.aggregation.two_arm import (
    TwoArmOutcome,
    two_arm_gate,
)

DELTA = 0.1
THRESHOLD = 0.95


# ---------------------------------------------------------------------------
# Outcome regions
# ---------------------------------------------------------------------------


class TestOutcomeRegions:
    def test_extreme_separation_is_treatment_better(self) -> None:
        result = two_arm_gate(8, 8, 0, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.outcome is TwoArmOutcome.TREATMENT_BETTER
        assert result.p_treatment_better >= THRESHOLD
        assert result.p_treatment_worse < 0.05

    def test_extreme_reverse_is_treatment_worse(self) -> None:
        """Reactance region (Burger/Girgis/Manning): the single-tail precedent
        stat would absorb this into 'no lift'; the two-sided gate must not."""
        result = two_arm_gate(0, 8, 8, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.outcome is TwoArmOutcome.TREATMENT_WORSE
        assert result.p_treatment_worse >= THRESHOLD

    def test_equal_arms_is_null(self) -> None:
        result = two_arm_gate(4, 8, 4, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.outcome is TwoArmOutcome.NULL

    def test_modest_effect_at_registered_power_is_null(self) -> None:
        """Power floor (K7/R6): at ~8 epochs per arm only transformative
        (~>=0.5 absolute) separations resolve; a 0.375 gap stays NULL."""
        result = two_arm_gate(6, 8, 3, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.outcome is TwoArmOutcome.NULL


# ---------------------------------------------------------------------------
# Probability computation
# ---------------------------------------------------------------------------


class TestProbabilities:
    def test_identical_arms_zero_delta_is_half(self) -> None:
        result = two_arm_gate(4, 8, 4, 8, delta=0.0, prob_threshold=THRESHOLD)
        assert result.p_treatment_better == pytest.approx(0.5, abs=1e-6)
        assert result.p_treatment_worse == pytest.approx(0.5, abs=1e-6)

    def test_swap_symmetry(self) -> None:
        forward = two_arm_gate(6, 8, 2, 8, delta=DELTA, prob_threshold=THRESHOLD)
        swapped = two_arm_gate(2, 8, 6, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert forward.p_treatment_better == pytest.approx(swapped.p_treatment_worse, abs=1e-9)
        assert forward.p_treatment_worse == pytest.approx(swapped.p_treatment_better, abs=1e-9)

    def test_monotone_in_treatment_passes(self) -> None:
        low = two_arm_gate(5, 8, 4, 8, delta=DELTA, prob_threshold=THRESHOLD)
        high = two_arm_gate(7, 8, 4, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert high.p_treatment_better > low.p_treatment_better

    def test_probabilities_are_probabilities(self) -> None:
        result = two_arm_gate(3, 8, 5, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert 0.0 <= result.p_treatment_better <= 1.0
        assert 0.0 <= result.p_treatment_worse <= 1.0
        # d > delta and d < -delta are disjoint events for delta >= 0
        assert result.p_treatment_better + result.p_treatment_worse <= 1.0 + 1e-9

    def test_posterior_parameters_are_uniform_prior_updates(self) -> None:
        result = two_arm_gate(6, 8, 2, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.treatment_alpha == pytest.approx(7.0)
        assert result.treatment_beta == pytest.approx(3.0)
        assert result.control_alpha == pytest.approx(3.0)
        assert result.control_beta == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeat_calls_bit_identical(self) -> None:
        a = two_arm_gate(6, 8, 3, 8, delta=DELTA, prob_threshold=THRESHOLD)
        b = two_arm_gate(6, 8, 3, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert a == b


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        ("t_pass", "t_n", "c_pass", "c_n"),
        [
            (-1, 8, 4, 8),
            (9, 8, 4, 8),
            (4, 8, -1, 8),
            (4, 8, 9, 8),
            (0, 0, 4, 8),
            (4, 8, 0, 0),
        ],
    )
    def test_bad_counts_rejected(self, t_pass: int, t_n: int, c_pass: int, c_n: int) -> None:
        with pytest.raises(ValueError, match=r"(pass|trials)"):
            two_arm_gate(t_pass, t_n, c_pass, c_n, delta=DELTA, prob_threshold=THRESHOLD)

    @pytest.mark.parametrize("delta", [-0.01, 1.0, 1.5])
    def test_bad_delta_rejected(self, delta: float) -> None:
        with pytest.raises(ValueError, match="delta"):
            two_arm_gate(4, 8, 4, 8, delta=delta, prob_threshold=THRESHOLD)

    @pytest.mark.parametrize("threshold", [0.5, 0.4, 1.01])
    def test_bad_threshold_rejected(self, threshold: float) -> None:
        """threshold must exceed 0.5 so the two outcome regions are mutually
        exclusive (P(d>delta) + P(d<-delta) <= 1)."""
        with pytest.raises(ValueError, match="prob_threshold"):
            two_arm_gate(4, 8, 4, 8, delta=DELTA, prob_threshold=threshold)


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------


class TestRationale:
    @pytest.mark.parametrize(
        ("t_pass", "c_pass"),
        [(8, 0), (0, 8), (4, 4)],
    )
    def test_rationale_nonempty(self, t_pass: int, c_pass: int) -> None:
        result = two_arm_gate(t_pass, 8, c_pass, 8, delta=DELTA, prob_threshold=THRESHOLD)
        assert result.rationale.strip()
