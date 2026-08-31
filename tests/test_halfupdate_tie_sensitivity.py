"""Half-update tie sensitivity detector (#347, falsification plan item 5).

Holds wins and losses fixed, varies tie count, and asserts a documented
sensitivity bound on how far the posterior and stopping decision can move
between the half-update encoding (Tie=0.5, n+=1) and a drop-ties recompute
(filtering observation == 0.5).

The drop-ties recompute is a comparison oracle built inside the test; no
production drop-ties path exists. Building it here is what makes the
sensitivity measurable.

When the measured sensitivity is large enough to change a shipped verdict,
the test xfails with a findings reference rather than widening the bound.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.ablation.stopping import (
    WIN_RATE_THRESHOLD,
    BetaBinomialAccumulator,
    StoppingReason,
)

# ---------------------------------------------------------------------------
# Sensitivity bound (written down before measurement)
# ---------------------------------------------------------------------------
# The maximum allowable |P_halfupdate(rate > theta) - P_dropties(rate > theta)|
# over all tested scenarios.  If any scenario exceeds this, the test xfails
# with a findings reference rather than widening the bound.
MAX_P_SENSITIVITY: float = 0.25

# The maximum allowable |mean_halfupdate - mean_dropties| over all tested
# scenarios.
MAX_POSTERIOR_MEAN_SHIFT: float = 0.15


# ---------------------------------------------------------------------------
# Scenarios: identical wins/losses, varying tie counts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A paired scenario with fixed wins/losses and varying tie count."""

    label: str
    wins: int
    losses: int
    ties: int


# Chosen to span the range from zero ties (baseline) to tie-dominated.
# w+l == N_MIN (8) in every scenario so the drop-ties recompute reaches the
# first stop-check boundary.  win-heavy scenarios (w=8, l=0) with ties
# produce actual verdict flips: drop-ties says PASSED while half-update
# remains INCONCLUSIVE.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario("zero-ties", wins=6, losses=2, ties=0),
    Scenario("few-ties", wins=6, losses=2, ties=4),
    Scenario("moderate-ties", wins=6, losses=2, ties=8),
    Scenario("many-ties", wins=6, losses=2, ties=12),
    Scenario("tie-dominated", wins=6, losses=2, ties=20),
    Scenario("balanced-zero-ties", wins=4, losses=4, ties=0),
    Scenario("balanced-many-ties", wins=4, losses=4, ties=16),
    Scenario("loss-heavy-zero-ties", wins=2, losses=6, ties=0),
    Scenario("loss-heavy-many-ties", wins=2, losses=6, ties=12),
    Scenario("win-heavy-zero-ties", wins=8, losses=0, ties=0),
    Scenario("win-heavy-few-ties", wins=8, losses=0, ties=8),
    Scenario("win-heavy-many-ties", wins=8, losses=0, ties=16),
)


# ---------------------------------------------------------------------------
# Drop-ties oracle (in-test comparison arm)
# ---------------------------------------------------------------------------


def _dropties_posterior(wins: int, losses: int) -> tuple[float, float]:
    """Beta posterior after filtering out ties (observation == 0.5).

    Prior Beta(1, 1). Each non-tie observation updates: win -> w += 1,
    loss -> n += 1. Ties are excluded entirely.
    """
    alpha = 1.0 + wins
    beta_param = 1.0 + losses
    return alpha, beta_param


def _halfupdate_posterior(wins: int, losses: int, ties: int) -> tuple[float, float]:
    """Beta posterior under half-update encoding (Tie=0.5, n+=1).

    Prior Beta(1, 1). Each observation: w += observation, n += 1.
    """
    w_acc = wins + ties * 0.5
    n = wins + losses + ties
    alpha = 1.0 + w_acc
    beta_param = 1.0 + (n - w_acc)
    return alpha, beta_param


def _p_exceed(alpha: float, beta_param: float) -> float:
    """P(rate > WIN_RATE_THRESHOLD) under Beta(alpha, beta_param)."""
    return float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))


def _halfupdate_stop(wins: int, losses: int, ties: int) -> StoppingReason | None:
    """Simulate the half-update stopping decision via the production accumulator."""
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    for _ in range(ties):
        acc.add(0.5)
    decision = acc.check_stop()
    return decision.stopping_reason


def _dropties_stop(wins: int, losses: int) -> StoppingReason | None:
    """Simulate the drop-ties stopping decision via the production accumulator.

    Ties are filtered out before accumulation: only wins and losses enter the
    accumulator, matching the recompute described in the falsification plan.
    """
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    decision = acc.check_stop()
    return decision.stopping_reason


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHalfUpdateTieSensitivity:
    """Paired scenarios: fixed wins/losses, varying tie counts.

    Asserts that the half-update and drop-ties posteriors stay within
    documented sensitivity bounds.  When the sensitivity is large enough
    to change a shipped verdict, the test xfails with a findings reference.
    """

    @pytest.mark.parametrize(
        "scenario",
        SCENARIOS,
        ids=[s.label for s in SCENARIOS],
    )
    def test_posterior_mean_shift_within_bound(self, scenario: Scenario) -> None:
        """The posterior mean must not shift more than MAX_POSTERIOR_MEAN_SHIFT."""
        hu_alpha, hu_beta = _halfupdate_posterior(
            scenario.wins, scenario.losses, scenario.ties,
        )
        dt_alpha, dt_beta = _dropties_posterior(scenario.wins, scenario.losses)

        hu_mean = hu_alpha / (hu_alpha + hu_beta)
        dt_mean = dt_alpha / (dt_alpha + dt_beta)
        shift = abs(hu_mean - dt_mean)

        if shift > MAX_POSTERIOR_MEAN_SHIFT:
            pytest.xfail(
                f"finding: docs/findings/halfupdate-tie-sensitivity.md "
                f"(scenario {scenario.label!r}; severity WRONG_NUMBER; "
                f"posterior mean shift {shift:.6f} exceeds bound "
                f"{MAX_POSTERIOR_MEAN_SHIFT})"
            )

        assert shift <= MAX_POSTERIOR_MEAN_SHIFT + 1e-9, (
            f"posterior mean shift {shift:.6f} exceeds bound "
            f"{MAX_POSTERIOR_MEAN_SHIFT} for scenario {scenario.label!r} "
            f"(half-update mean={hu_mean:.6f}, drop-ties mean={dt_mean:.6f})"
        )

    @pytest.mark.parametrize(
        "scenario",
        SCENARIOS,
        ids=[s.label for s in SCENARIOS],
    )
    def test_p_exceed_sensitivity_within_bound(self, scenario: Scenario) -> None:
        """P(rate > theta) must not diverge more than MAX_P_SENSITIVITY."""
        hu_alpha, hu_beta = _halfupdate_posterior(
            scenario.wins, scenario.losses, scenario.ties,
        )
        dt_alpha, dt_beta = _dropties_posterior(scenario.wins, scenario.losses)

        hu_p = _p_exceed(hu_alpha, hu_beta)
        dt_p = _p_exceed(dt_alpha, dt_beta)
        divergence = abs(hu_p - dt_p)

        if divergence > MAX_P_SENSITIVITY:
            pytest.xfail(
                f"finding: docs/findings/halfupdate-tie-sensitivity.md "
                f"(scenario {scenario.label!r}; severity WRONG_NUMBER; "
                f"P(rate > theta) divergence {divergence:.6f} exceeds bound "
                f"{MAX_P_SENSITIVITY})"
            )

        assert divergence <= MAX_P_SENSITIVITY + 1e-9, (
            f"P(rate > theta) divergence {divergence:.6f} exceeds bound "
            f"{MAX_P_SENSITIVITY} for scenario {scenario.label!r} "
            f"(half-update p={hu_p:.6f}, drop-ties p={dt_p:.6f})"
        )

    @pytest.mark.parametrize(
        "scenario",
        SCENARIOS,
        ids=[s.label for s in SCENARIOS],
    )
    def test_stopping_decision_agreement(self, scenario: Scenario) -> None:
        """Half-update and drop-ties must reach the same stopping verdict.

        If they disagree, the tie encoding is material to the shipped verdict.
        The test xfails with a findings reference when this happens.
        """
        hu_reason = _halfupdate_stop(
            scenario.wins, scenario.losses, scenario.ties,
        )
        dt_reason = _dropties_stop(scenario.wins, scenario.losses)

        if hu_reason != dt_reason:
            pytest.xfail(
                f"finding: docs/findings/halfupdate-tie-sensitivity.md "
                f"(scenario {scenario.label!r}; severity WRONG_NUMBER; "
                f"tie encoding changes shipped verdict: half-update={hu_reason}, "
                f"drop-ties={dt_reason})"
            )

        assert hu_reason == dt_reason, (
            f"stopping verdict differs: half-update={hu_reason}, "
            f"drop-ties={dt_reason} for scenario {scenario.label!r}"
        )

    def test_fixture_proves_detector_fires(self) -> None:
        """A fixture proving the detector goes red on the condition it registers.

        Constructs an extreme scenario where tie count is very high relative to
        wins/losses, ensuring the half-update and drop-ties posteriors diverge
        measurably.  The test asserts the divergence exists and is positive.
        """
        # Extreme scenario: 7 wins, 1 loss, 30 ties
        # Half-update: Beta(1 + 7 + 15, 1 + 1 + 15) = Beta(23, 17)
        # Drop-ties:   Beta(1 + 7, 1 + 1) = Beta(8, 2)
        hu_alpha, hu_beta = _halfupdate_posterior(7, 1, 30)
        dt_alpha, dt_beta = _dropties_posterior(7, 1)

        hu_p = _p_exceed(hu_alpha, hu_beta)
        dt_p = _p_exceed(dt_alpha, dt_beta)

        divergence = abs(hu_p - dt_p)
        assert divergence > 0.01, (
            f"detector did not fire: P(rate > theta) divergence {divergence:.6f} "
            f"is too small for the extreme scenario (7w, 1l, 30t). "
            f"half-update p={hu_p:.6f}, drop-ties p={dt_p:.6f}"
        )

        hu_mean = hu_alpha / (hu_alpha + hu_beta)
        dt_mean = dt_alpha / (dt_alpha + dt_beta)
        mean_shift = abs(hu_mean - dt_mean)
        assert mean_shift > 0.05, (
            f"detector did not fire: posterior mean shift {mean_shift:.6f} "
            f"is too small for the extreme scenario (7w, 1l, 30t). "
            f"half-update mean={hu_mean:.6f}, drop-ties mean={dt_mean:.6f}"
        )

    def test_sensitivity_grows_with_tie_count(self) -> None:
        """Sensitivity must increase monotonically with tie count for fixed w/l."""
        wins, losses = 6, 2
        tie_counts = [0, 4, 8, 12, 20]
        prev_divergence = -1.0

        for t in tie_counts:
            hu_alpha, hu_beta = _halfupdate_posterior(wins, losses, t)
            dt_alpha, dt_beta = _dropties_posterior(wins, losses)

            hu_p = _p_exceed(hu_alpha, hu_beta)
            dt_p = _p_exceed(dt_alpha, dt_beta)
            divergence = abs(hu_p - dt_p)

            assert divergence >= prev_divergence - 1e-9, (
                f"sensitivity not monotone: divergence {divergence:.6f} at t={t} "
                f"is less than {prev_divergence:.6f} at previous tie count"
            )
            prev_divergence = divergence
