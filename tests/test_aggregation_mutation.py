"""Mutation-killing tests for aggregation/ (#166).

Each test pins external behaviour that a surviving mutmut mutant flipped.
Standing rule: a kill is demonstrated by failing under the mutant and passing
on real code (verified via mutmut apply / mutmut run of the named mutant).
"""

from __future__ import annotations

import math

import pytest

from skill_harness.aggregation.two_arm import (
    TwoArmOutcome,
    _p_difference_exceeds,
    two_arm_gate,
)


class TestTwoArmBoundaryContracts:
    """Kill boundary / echo / label mutants in two_arm.py."""

    def test_single_trial_arm_is_valid(self) -> None:
        """n_trials >= 1 includes exactly 1 (kills n_trials < 2 / <= 1)."""
        result = two_arm_gate(1, 1, 0, 1, delta=0.0, prob_threshold=0.95)
        assert result.outcome in {
            TwoArmOutcome.TREATMENT_BETTER,
            TwoArmOutcome.TREATMENT_WORSE,
            TwoArmOutcome.NULL,
        }
        assert result.treatment_alpha == pytest.approx(2.0)
        assert result.treatment_beta == pytest.approx(1.0)

    def test_prob_threshold_one_is_valid(self) -> None:
        """prob_threshold may be exactly 1.0 (kills `<= 1.0` → `< 1.0`)."""
        result = two_arm_gate(4, 8, 4, 8, delta=0.1, prob_threshold=1.0)
        assert result.outcome is TwoArmOutcome.NULL
        assert result.prob_threshold == 1.0

    def test_result_echoes_delta_and_threshold(self) -> None:
        """Result carries the pre-registered constants (kills delta=None / threshold=None)."""
        result = two_arm_gate(5, 10, 3, 10, delta=0.15, prob_threshold=0.9)
        assert result.delta == 0.15
        assert result.prob_threshold == 0.9
        assert isinstance(result.delta, float)
        assert isinstance(result.prob_threshold, float)

    def test_invalid_treatment_trials_message_uses_treatment_label(self) -> None:
        with pytest.raises(ValueError, match=r"^treatment_trials must be >= 1"):
            two_arm_gate(0, 0, 1, 1, delta=0.1, prob_threshold=0.95)

    def test_invalid_control_trials_message_uses_control_label(self) -> None:
        with pytest.raises(ValueError, match=r"^control_trials must be >= 1"):
            two_arm_gate(1, 1, 0, 0, delta=0.1, prob_threshold=0.95)

    def test_gate_at_exact_threshold_is_directional(self) -> None:
        """`>= prob_threshold` includes equality (kills `>=` → `>`).

        Construct counts where the computed P lands extremely close to 1.0 and
        use threshold equal to the computed p so equality is the decision edge.
        """
        # Extreme separation → p_better essentially 1.0; threshold=1.0 forces
        # the equality branch: outcome is BETTER iff p_better >= 1.0.
        # With finite quadrature p may be slightly under 1; use the returned p.
        probe = two_arm_gate(40, 40, 0, 40, delta=0.0, prob_threshold=0.99)
        p = probe.p_treatment_better
        assert p >= 0.99
        # Re-run with threshold exactly equal to p (within float repr).
        at_eq = two_arm_gate(40, 40, 0, 40, delta=0.0, prob_threshold=p)
        assert at_eq.outcome is TwoArmOutcome.TREATMENT_BETTER
        # Symmetric reverse arm.
        probe_w = two_arm_gate(0, 40, 40, 40, delta=0.0, prob_threshold=0.99)
        pw = probe_w.p_treatment_worse
        at_eq_w = two_arm_gate(0, 40, 40, 40, delta=0.0, prob_threshold=pw)
        assert at_eq_w.outcome is TwoArmOutcome.TREATMENT_WORSE

    def test_null_rationale_states_power_floor_contract(self) -> None:
        """Rationale text is part of the operator-facing contract for NULL.

        Assert the concatenated clause as one string so adjacent-literal XX/case
        mutants cannot keep both halves matching independently.
        """
        result = two_arm_gate(4, 8, 4, 8, delta=0.1, prob_threshold=0.95)
        assert result.outcome is TwoArmOutcome.NULL
        assert (
            "No transformative effect resolved on this model/fixture; this is "
            "not evidence that no effect exists (registered power floor)."
        ) in result.rationale

    def test_difference_exceeds_integrates_to_unit_interval(self) -> None:
        """Quadrature upper bound is the unit interval support of Beta."""
        # P(X-Y > -1) for unit-supported betas is ~1; a wrong upper limit of 2
        # still works, but P(X-Y > 0) must stay a probability.
        p = _p_difference_exceeds(3.0, 3.0, 3.0, 3.0, 0.0)
        assert 0.0 <= p <= 1.0
        assert p == pytest.approx(0.5, abs=1e-6)
        # Clamp ceiling is 1.0: even pathological inputs must not exceed 1.
        p_hi = _p_difference_exceeds(50.0, 1.0, 1.0, 50.0, -0.5)
        assert p_hi <= 1.0 + 1e-15
        assert math.isfinite(p_hi)
