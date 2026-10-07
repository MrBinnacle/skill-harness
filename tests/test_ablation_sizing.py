"""Tests for skill_harness.ablation.sizing — exact DP against the locked rule.

The sizing module is pure computation; every expectation here is derivable
by hand from the locked constants (N_MIN=8, N_INC=4, N_MAX=40, threshold
0.60, pass 0.95 / fail 0.05) or cross-checked against the runtime
BetaBinomialAccumulator on a deterministic path.
"""

from __future__ import annotations

import pytest

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

    Conditioning on the discordant table removes the artifact and the
    measurable region extends down to d = 0.2. The frontier does not vanish,
    it moves, and the values below are its new location.

    d = 0.1 remains genuinely unmeasurable: 40 samples yield about four
    discordant comparisons, short of the N_MIN = 8 evidence bar, so no q
    saves it. That is a structural limit rather than an encoding one, which
    is why it did not move.

    Note what this does NOT license. A detectable q at d = 0.2 is a statement
    about the scalar rule's power, not a licence to ship the clause: the net
    lift there is 0.188, below the registered delta_min, and Path C is what
    stops it. See tests/test_ablation_path_c.py.
    """
    assert minimum_detectable_q(0.4) == pytest.approx(0.87)
    assert minimum_detectable_q(0.2) == pytest.approx(0.97)
    assert minimum_detectable_q(0.1) is None


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
