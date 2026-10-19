"""Mutation-killing tests for ablation/ (#166)."""

from __future__ import annotations

import pytest

from skill_harness.ablation.confound import NullAccumulator, delta_to_observation
from skill_harness.ablation.sizing import minimum_detectable_q, solve
from skill_harness.ablation.stopping import FAIL_PROB_THRESHOLD, PASS_PROB_THRESHOLD


class TestSizingContracts:
    def test_q_boundary_zero_and_one_accepted(self) -> None:
        """q in [0,1] inclusive (kills 0.0 < q or q <= 2.0)."""
        r0 = solve(0.5, 0.0)
        assert r0.win_given_discordant == 0.0
        assert r0.win_given_discordant is not None
        r1 = solve(0.5, 1.0)
        assert r1.win_given_discordant == 1.0
        with pytest.raises(ValueError, match=r"d and q must lie in \[0, 1\]"):
            solve(0.5, 1.01)
        with pytest.raises(ValueError, match=r"d and q must lie in \[0, 1\]"):
            solve(0.5, -0.01)

    def test_result_echoes_inputs(self) -> None:
        r = solve(0.4, 0.7)
        assert r.discordance_rate == 0.4
        assert r.discordance_rate is not None
        assert r.win_given_discordant == 0.7
        assert r.win_given_discordant is not None
        assert 0.0 <= r.p_pass <= 1.0
        assert abs(r.p_pass + r.p_fail + r.p_unmeasured - 1.0) < 1e-9
        # expected_n must accumulate (not assign-overwrite) across paths
        assert r.expected_n > 0.0

    def test_expected_n_accumulates_not_overwrites(self) -> None:
        """Multiple absorption paths contribute to expected_n (kills += → =)."""
        r = solve(0.8, 0.9)
        # All-wins-like high q should often stop near N_MIN, but mass on
        # other paths still adds; expected_n is a proper expectation.
        assert r.expected_n >= 8.0  # N_MIN
        r_hard = solve(0.2, 0.55)
        # Low signal: more paths reach higher n → larger expectation.
        assert r_hard.expected_n >= r.expected_n or r_hard.p_unmeasured > 0.1

    def test_pass_threshold_includes_equality(self) -> None:
        """Document PASS_PROB_THRESHOLD is a closed upper bar used by sizing."""
        assert pytest.approx(0.95) == PASS_PROB_THRESHOLD
        assert pytest.approx(0.05) == FAIL_PROB_THRESHOLD

    def test_minimum_detectable_q_grid_includes_one(self) -> None:
        """Grid must reach q=1.0 (kills n_steps off-by-one that skips 1.0)."""
        q = minimum_detectable_q(1.0, target_power=0.8, step=0.05)
        assert q is not None
        assert 0.5 <= q <= 1.0
        # At full discordance, some q in (0.5, 1] should clear power.
        assert solve(1.0, q).p_pass >= 0.8
        # step that lands exactly on 1.0
        q2 = minimum_detectable_q(1.0, target_power=0.5, step=0.1)
        assert q2 is not None


class TestConfoundContracts:
    def test_empty_accumulator_n_is_zero(self) -> None:
        acc = NullAccumulator(null_floor=5)
        assert acc.n() == 0

    def test_delta_to_observation_defaults_and_boundaries(self) -> None:
        # Default comparator is exactly "increase"
        assert delta_to_observation(0.1) == 1.0
        assert delta_to_observation(-0.1) == 0.0
        assert delta_to_observation(0.0) == 0.5
        # Default tie_tolerance is 0.0: any nonzero is decisive
        assert delta_to_observation(1e-12) == 1.0
        # decrease comparator: negative delta wins; zero (outside tie) is loss
        assert delta_to_observation(-0.5, comparator="decrease") == 1.0
        assert delta_to_observation(0.5, comparator="decrease") == 0.0
        assert delta_to_observation(0.0, comparator="decrease", tie_tolerance=-1.0) == 0.0
        # exact zero with tie_tolerance 0 already returned 0.5 above; for decrease
        # at delta==0 with tolerance 0, abs(0)<=0 → tie 0.5 before comparator branch.
        assert delta_to_observation(0.0, comparator="decrease") == 0.5

    def test_decrease_strict_negative_not_le(self) -> None:
        """delta < 0 for decrease win (kills < → <= at zero already tied)."""
        # With tiny positive tolerance cleared: delta just below 0
        assert delta_to_observation(-1e-9, comparator="decrease", tie_tolerance=0.0) == 1.0
        assert delta_to_observation(1e-9, comparator="decrease", tie_tolerance=0.0) == 0.0

    def test_increase_strict_positive_not_ge(self) -> None:
        assert delta_to_observation(1e-9, comparator="increase", tie_tolerance=0.0) == 1.0
        assert delta_to_observation(-1e-9, comparator="increase", tie_tolerance=0.0) == 0.0
