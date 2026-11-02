"""Tests for skill_harness.ablation.sizing — exact DP against the locked rule.

The sizing module is pure computation; every expectation here is derivable
by hand from the locked constants (N_MIN=8, N_INC=4, N_MAX=40, threshold
0.60, pass 0.95 / fail 0.05) or cross-checked against the runtime
BetaBinomialAccumulator on a deterministic path.
"""

from __future__ import annotations

import pytest
from scipy.stats import binom  # type: ignore[import-untyped]

from skill_harness.ablation.sizing import SizingResult, minimum_detectable_q, solve
from skill_harness.ablation.stopping import (
    N_MAX,
    N_MIN,
    BetaBinomialAccumulator,
    StoppingReason,
)


def test_all_wins_passes_at_n_min_with_certainty() -> None:
    result = solve(discordance_rate=1.0, win_given_discordant=1.0)
    assert result.p_pass == pytest.approx(1.0)
    assert result.p_fail == pytest.approx(0.0)
    assert result.p_unmeasured == pytest.approx(0.0)
    assert result.expected_n == pytest.approx(float(N_MIN))


def test_all_wins_path_agrees_with_runtime_accumulator() -> None:
    # The DP says the deterministic all-wins path absorbs PASSED at N_MIN;
    # the runtime accumulator must agree on that exact path.
    acc = BetaBinomialAccumulator()
    for _ in range(N_MIN):
        acc.add(1.0)
    decision = acc.check_stop()
    assert decision.should_stop is True
    assert decision.stopping_reason is StoppingReason.PASSED
    assert decision.n_samples == N_MIN


def test_pure_ties_are_structurally_unmeasured() -> None:
    # d=0: every observation is a tie; the posterior concentrates at 0.5 and
    # never crosses either probability bound inside N_MAX.
    result = solve(discordance_rate=0.0, win_given_discordant=0.5)
    assert result.p_unmeasured == pytest.approx(1.0)
    assert result.expected_n == pytest.approx(float(N_MAX))


@pytest.mark.parametrize(
    ("q", "verdict_field"),
    [(1.0, "p_pass"), (0.0, "p_fail")],
)
def test_low_discordance_verdict_needs_n_min_discordant_by_n_max(
    q: float, verdict_field: str
) -> None:
    result = solve(discordance_rate=0.1, win_given_discordant=q)

    assert getattr(result, verdict_field) == pytest.approx(binom.sf(N_MIN - 1, N_MAX, 0.1))
    assert result.p_unmeasured == pytest.approx(binom.cdf(N_MIN - 1, N_MAX, 0.1))


def test_null_false_pass_rate_is_small() -> None:
    # q=0.5 is the no-effect null; the rule's false-PASS mass stays under 2%
    # at full discordance (exact value ~0.018).
    result = solve(discordance_rate=1.0, win_given_discordant=0.5)
    assert result.p_pass < 0.02


def test_absorption_probabilities_sum_to_one() -> None:
    for d, q in ((1.0, 0.7), (0.6, 0.9), (0.2, 0.95)):
        result = solve(d, q)
        total = result.p_pass + result.p_fail + result.p_unmeasured
        assert total == pytest.approx(1.0)
        assert 0.0 < result.expected_n <= float(N_MAX)


def test_p_pass_monotone_in_effect_size() -> None:
    grid = [solve(0.8, q).p_pass for q in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]
    assert grid == sorted(grid)


def test_minimum_detectable_q_at_full_discordance() -> None:
    assert minimum_detectable_q(1.0) == pytest.approx(0.77)


def test_low_discordance_is_structurally_unmeasurable() -> None:
    """Rewritten by #368, because the migration MOVED this frontier.

    Under the superseded half-update encoding the assertion here was
    ``minimum_detectable_q(0.4) is None``: below roughly half discordance no q
    at all reached 80% P(PASS) inside N_MAX. That was never a fact about how
    much evidence a 40%-discordant axis carries. It was an artifact of the
    encoding, which spent the sample budget crediting ties to both sides of
    the posterior until nothing could clear the bar.
    """
    assert minimum_detectable_q(0.4) == pytest.approx(0.87)
    assert minimum_detectable_q(0.25) == pytest.approx(0.99)
    assert minimum_detectable_q(0.2) is None
    assert minimum_detectable_q(0.1) is None


@pytest.mark.parametrize("d", [0.25, 0.2])
def test_p_pass_is_capped_by_the_chance_of_n_min_discordant(d: float) -> None:
    assert solve(d, 1.0).p_pass == pytest.approx(binom.sf(N_MIN - 1, N_MAX, d))


def test_out_of_range_parameters_raise() -> None:
    with pytest.raises(ValueError):
        solve(1.5, 0.5)
    with pytest.raises(ValueError):
        solve(0.5, -0.1)


def test_result_is_frozen_dataclass() -> None:
    result = solve(1.0, 1.0)
    assert isinstance(result, SizingResult)
    with pytest.raises(AttributeError):
        result.p_pass = 0.0  # type: ignore[misc]
