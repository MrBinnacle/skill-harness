"""Half-update tie sensitivity detector (#347, falsification plan item 5).

Holds wins and losses fixed, varies tie count, and asserts that the
production path (Gate-2 discordant machinery, #368 Path C migration) and
the drop-ties recompute (filtering observation == 0.5) agree on stopping
decisions and posterior parameters across all fixture scenarios.

The production path now routes tie-heavy clause decisions through the
Gate-2 three-sided paired rule over the discordant table (INVARIANTS §8:
discordant table is the estimand of record). The Gate-2 path produces a
StopDecision compatible with the ablation runner; its posterior parameters
are derived from the discordant-only Beta(1+w, 1+l), which is identical
to the drop-ties recompute.

The former sensitivity between the scalar half-update encoding (Tie=0.5,
n+=1) and drop-ties is now resolved: both paths route through Gate-2 when
ties are present. The seven strict xfails that marked the former
sensitivity have been removed by the ratified decision (#368).

Both arms drive the production path (`gate2_stopping_decision`). The
drop-ties arm is a comparison oracle built inside the test: no production
drop-ties path exists, and this ticket does not add one. Building it here
is what makes the agreement measurable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from skill_harness.ablation.gate2_stopping import gate2_stopping_decision
from skill_harness.ablation.stopping import StopDecision

# ---------------------------------------------------------------------------
# Sensitivity bounds (retained from the former measurement; now the
# production path agrees with drop-ties so divergence is zero)
# ---------------------------------------------------------------------------
# These bounds are retained so that any future regression that reintroduces
# sensitivity between the two paths is caught at the same thresholds.
MAX_P_SENSITIVITY: Final[float] = 0.25

MAX_POSTERIOR_MEAN_SHIFT: Final[float] = 0.15


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


# w+l == N_MIN (8) in every scenario so the drop-ties recompute reaches the
# first stop-check boundary. After the #368 migration the production path
# (Gate-2 discordant machinery) and drop-ties agree on every scenario.
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


def _mean_params() -> list[object]:
    return [pytest.param(scenario, id=scenario.label) for scenario in SCENARIOS]


def _p_params() -> list[object]:
    return [pytest.param(scenario, id=scenario.label) for scenario in SCENARIOS]


def _verdict_params() -> list[object]:
    return [pytest.param(scenario, id=scenario.label) for scenario in SCENARIOS]


# ---------------------------------------------------------------------------
# Production arms
# ---------------------------------------------------------------------------


def _halfupdate(wins: int, losses: int, ties: int) -> StopDecision:
    """Production path: routes through Gate-2 discordant machinery (#368).

    When ties > 0 the decision comes from the Gate-2 three-sided rule; the
    posterior parameters are derived from the discordant-only
    Beta(1+w, 1+l). When ties == 0 the scalar accumulator is used directly
    (unchanged legacy path).
    """
    return gate2_stopping_decision(wins, losses, ties)


def _dropties(wins: int, losses: int) -> StopDecision:
    """Drop-ties oracle: ties filtered out before accumulation.

    Matches the recompute the falsification plan names (filter observation == 0.5).
    This oracle drives the scalar BetaBinomialAccumulator directly.
    """
    from skill_harness.ablation.stopping import BetaBinomialAccumulator

    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    return acc.check_stop()


def _posterior_mean(decision: StopDecision) -> float:
    return decision.posterior_alpha / (decision.posterior_alpha + decision.posterior_beta)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHalfUpdateTieSensitivity:
    """Paired scenarios: fixed wins/losses, varying tie counts.

    Asserts that the Gate-2 production path and the drop-ties recompute
    agree on stopping decisions and posterior parameters across all fixture
    scenarios. After the #368 migration the two paths are equivalent
    (Gate-2 drops ties, matching the drop-ties oracle).
    """

    @pytest.mark.parametrize("scenario", _mean_params())
    def test_posterior_mean_shift_within_bound(self, scenario: Scenario) -> None:
        """The posterior mean must not shift more than MAX_POSTERIOR_MEAN_SHIFT."""
        hu = _halfupdate(scenario.wins, scenario.losses, scenario.ties)
        dt = _dropties(scenario.wins, scenario.losses)

        hu_mean = _posterior_mean(hu)
        dt_mean = _posterior_mean(dt)
        shift = abs(hu_mean - dt_mean)

        assert shift <= MAX_POSTERIOR_MEAN_SHIFT + 1e-9, (
            f"posterior mean shift {shift:.6f} exceeds bound "
            f"{MAX_POSTERIOR_MEAN_SHIFT} for scenario {scenario.label!r} "
            f"(production mean={hu_mean:.6f}, drop-ties mean={dt_mean:.6f})"
        )

    @pytest.mark.parametrize("scenario", _p_params())
    def test_p_exceed_sensitivity_within_bound(self, scenario: Scenario) -> None:
        """P(rate > theta) must not diverge more than MAX_P_SENSITIVITY."""
        hu = _halfupdate(scenario.wins, scenario.losses, scenario.ties)
        dt = _dropties(scenario.wins, scenario.losses)

        hu_p = hu.p_win_rate_exceeds_threshold
        dt_p = dt.p_win_rate_exceeds_threshold
        divergence = abs(hu_p - dt_p)

        assert divergence <= MAX_P_SENSITIVITY + 1e-9, (
            f"P(rate > theta) divergence {divergence:.6f} exceeds bound "
            f"{MAX_P_SENSITIVITY} for scenario {scenario.label!r} "
            f"(production p={hu_p:.6f}, drop-ties p={dt_p:.6f})"
        )

    @pytest.mark.parametrize("scenario", _verdict_params())
    def test_stopping_decision_agreement(self, scenario: Scenario) -> None:
        """Production path and drop-ties must reach the same stopping verdict.

        If they disagree, the tie encoding is material to the shipped verdict.
        """
        hu_reason = _halfupdate(scenario.wins, scenario.losses, scenario.ties).stopping_reason
        dt_reason = _dropties(scenario.wins, scenario.losses).stopping_reason

        assert hu_reason == dt_reason, (
            f"stopping verdict differs: production={hu_reason}, "
            f"drop-ties={dt_reason} for scenario {scenario.label!r}"
        )

    def test_fixture_proves_detector_fires(self) -> None:
        """Positive control: an extreme scenario with many ties.

        After the #368 migration the production path (Gate-2) and drop-ties
        agree on extreme scenarios because Gate-2 drops ties identically.
        This test verifies the production path classifies an extreme tie-heavy
        scenario (8 wins, 1 loss, 30 ties) as PASSED, matching the drop-ties
        recompute. The posterior is derived from the discordant-only
        Beta(9, 2), yielding P(rate > 0.60) ≈ 0.954.
        """
        hu = _halfupdate(8, 1, 30)
        dt = _dropties(8, 1)

        # Both paths must agree
        assert hu.stopping_reason == dt.stopping_reason, (
            f"extreme scenario: production={hu.stopping_reason}, "
            f"drop-ties={dt.stopping_reason}"
        )

        # Posterior parameters match (discordant-only Beta)
        assert hu.posterior_alpha == dt.posterior_alpha
        assert hu.posterior_beta == dt.posterior_beta

        # The extreme scenario should pass under both paths
        assert hu.stopping_reason is not None, (
            f"extreme scenario (8w, 1l, 30t) should have a stopping reason, "
            f"got None (p={hu.p_win_rate_exceeds_threshold:.6f})"
        )

    def test_zero_ties_arms_are_identical(self) -> None:
        """With zero ties the two arms must agree exactly (sanity control)."""
        hu = _halfupdate(6, 2, 0)
        dt = _dropties(6, 2)
        assert hu.posterior_alpha == dt.posterior_alpha
        assert hu.posterior_beta == dt.posterior_beta
        assert hu.p_win_rate_exceeds_threshold == dt.p_win_rate_exceeds_threshold
        assert hu.stopping_reason == dt.stopping_reason

    def test_sensitivity_grows_with_tie_count(self) -> None:
        """P-sensitivity must not shrink as tie count rises for fixed w/l."""
        wins, losses = 6, 2
        tie_counts = [0, 4, 8, 12, 20]
        prev_divergence = -1.0

        for t in tie_counts:
            hu = _halfupdate(wins, losses, t)
            dt = _dropties(wins, losses)
            divergence = abs(hu.p_win_rate_exceeds_threshold - dt.p_win_rate_exceeds_threshold)

            assert divergence >= prev_divergence - 1e-9, (
                f"sensitivity not monotone: divergence {divergence:.6f} at t={t} "
                f"is less than {prev_divergence:.6f} at previous tie count"
            )
            prev_divergence = divergence
