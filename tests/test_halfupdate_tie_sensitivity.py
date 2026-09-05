"""Half-update tie sensitivity detector (#347) + Path C migration pin (#368).

Holds wins and losses fixed, varies tie count, and asserts that the production
ablation stopping path (``DiscordantStoppingAccumulator`` / Gate-2 discordant
machinery, #368 Path C) and the drop-ties recompute (filtering observation ==
0.5) agree on stopping decisions and posterior parameters across all fixture
scenarios.

The production path is the same class the ablation runner constructs. The
drop-ties arm is a comparison oracle built inside the test: no production
drop-ties path exists as a separate module. Building it here makes agreement
measurable.

The seven strict xfails that marked the former half-update vs drop-ties
sensitivity have been removed by the ratified decision (#368), with bounds
unchanged so a regression that reintroduces divergence is still caught.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from skill_harness.ablation.gate2_stopping import DiscordantStoppingAccumulator
from skill_harness.ablation.runner import RunConfig
from skill_harness.ablation.stopping import BetaBinomialAccumulator, StopDecision, StoppingReason

# ---------------------------------------------------------------------------
# Sensitivity bounds (retained from the former measurement; production now
# agrees with drop-ties so divergence is zero — bounds still catch regression)
# ---------------------------------------------------------------------------
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
# (DiscordantStoppingAccumulator) and drop-ties agree on every scenario.
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
# Production arms — production is the runner's accumulator, not a test double
# ---------------------------------------------------------------------------


def _production(wins: int, losses: int, ties: int) -> StopDecision:
    """Production path: the same accumulator class the ablation runner uses."""
    acc = DiscordantStoppingAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    for _ in range(ties):
        acc.add(0.5)
    return acc.check_stop()


def _dropties(wins: int, losses: int) -> StopDecision:
    """Drop-ties oracle: ties filtered out before accumulation.

    Matches the recompute the falsification plan names (filter observation == 0.5).
    """
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    return acc.check_stop()


def _halfupdate_legacy(wins: int, losses: int, ties: int) -> StopDecision:
    """Legacy half-update encoding (Tie=0.5, n+=1) — not production after #368."""
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    for _ in range(ties):
        acc.add(0.5)
    return acc.check_stop()


def _posterior_mean(decision: StopDecision) -> float:
    return decision.posterior_alpha / (decision.posterior_alpha + decision.posterior_beta)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHalfUpdateTieSensitivity:
    """Paired scenarios: fixed wins/losses, varying tie counts.

    Asserts that the production Gate-2 path and the drop-ties recompute agree
    on stopping decisions and posterior parameters across all fixture scenarios.
    """

    @pytest.mark.parametrize("scenario", _mean_params())
    def test_posterior_mean_shift_within_bound(self, scenario: Scenario) -> None:
        """The posterior mean must not shift more than MAX_POSTERIOR_MEAN_SHIFT."""
        prod = _production(scenario.wins, scenario.losses, scenario.ties)
        dt = _dropties(scenario.wins, scenario.losses)

        prod_mean = _posterior_mean(prod)
        dt_mean = _posterior_mean(dt)
        shift = abs(prod_mean - dt_mean)

        assert shift <= MAX_POSTERIOR_MEAN_SHIFT + 1e-9, (
            f"posterior mean shift {shift:.6f} exceeds bound "
            f"{MAX_POSTERIOR_MEAN_SHIFT} for scenario {scenario.label!r} "
            f"(production mean={prod_mean:.6f}, drop-ties mean={dt_mean:.6f})"
        )

    @pytest.mark.parametrize("scenario", _p_params())
    def test_p_exceed_sensitivity_within_bound(self, scenario: Scenario) -> None:
        """P(rate > theta) must not diverge more than MAX_P_SENSITIVITY."""
        prod = _production(scenario.wins, scenario.losses, scenario.ties)
        dt = _dropties(scenario.wins, scenario.losses)

        prod_p = prod.p_win_rate_exceeds_threshold
        dt_p = dt.p_win_rate_exceeds_threshold
        divergence = abs(prod_p - dt_p)

        assert divergence <= MAX_P_SENSITIVITY + 1e-9, (
            f"P(rate > theta) divergence {divergence:.6f} exceeds bound "
            f"{MAX_P_SENSITIVITY} for scenario {scenario.label!r} "
            f"(production p={prod_p:.6f}, drop-ties p={dt_p:.6f})"
        )

    @pytest.mark.parametrize("scenario", _verdict_params())
    def test_stopping_decision_agreement(self, scenario: Scenario) -> None:
        """Production path and drop-ties must reach the same stopping verdict.

        If they disagree, the tie encoding is material to the shipped verdict.
        """
        prod_reason = _production(scenario.wins, scenario.losses, scenario.ties).stopping_reason
        dt_reason = _dropties(scenario.wins, scenario.losses).stopping_reason

        assert prod_reason == dt_reason, (
            f"stopping verdict differs: production={prod_reason}, "
            f"drop-ties={dt_reason} for scenario {scenario.label!r}"
        )

    def test_fixture_proves_legacy_halfupdate_still_diverges(self) -> None:
        """Positive control: the legacy half-update encoding still diverges.

        Pins that the detector condition remains real under the retired encoding.
        If a future change collapses half-update divergence below the bounds,
        this test goes red and the fixture must be revisited — it does not
        silently pass on a vacuous detector. Uses the original extreme fixture
        (7w, 1l, 30t) from the #347 finding.
        """
        legacy = _halfupdate_legacy(7, 1, 30)
        dt = _dropties(7, 1)

        legacy_p = legacy.p_win_rate_exceeds_threshold
        dt_p = dt.p_win_rate_exceeds_threshold
        divergence = abs(legacy_p - dt_p)
        assert divergence > MAX_P_SENSITIVITY, (
            f"detector did not fire: P(rate > theta) divergence {divergence:.6f} "
            f"is at or below bound {MAX_P_SENSITIVITY} for extreme scenario "
            f"(7w, 1l, 30t). half-update p={legacy_p:.6f}, drop-ties p={dt_p:.6f}"
        )

        legacy_mean = _posterior_mean(legacy)
        dt_mean = _posterior_mean(dt)
        mean_shift = abs(legacy_mean - dt_mean)
        assert mean_shift > MAX_POSTERIOR_MEAN_SHIFT, (
            f"detector did not fire: posterior mean shift {mean_shift:.6f} "
            f"is at or below bound {MAX_POSTERIOR_MEAN_SHIFT} for extreme "
            f"scenario (7w, 1l, 30t). half-update mean={legacy_mean:.6f}, "
            f"drop-ties mean={dt_mean:.6f}"
        )

    def test_migration_collapses_divergence_on_extreme_fixture(self) -> None:
        """Migration control: production agrees with drop-ties on the extreme fixture.

        Same (7w, 1l, 30t) counts as the legacy detector control. After #368 the
        production path must match drop-ties on posterior parameters and verdict.
        """
        prod = _production(7, 1, 30)
        dt = _dropties(7, 1)

        assert prod.stopping_reason == dt.stopping_reason
        assert prod.posterior_alpha == dt.posterior_alpha
        assert prod.posterior_beta == dt.posterior_beta
        assert abs(prod.p_win_rate_exceeds_threshold - dt.p_win_rate_exceeds_threshold) < 1e-12

    def test_zero_ties_arms_are_identical(self) -> None:
        """With zero ties the two arms must agree exactly (sanity control)."""
        prod = _production(6, 2, 0)
        dt = _dropties(6, 2)
        assert prod.posterior_alpha == dt.posterior_alpha
        assert prod.posterior_beta == dt.posterior_beta
        assert prod.p_win_rate_exceeds_threshold == dt.p_win_rate_exceeds_threshold
        assert prod.stopping_reason == dt.stopping_reason

    def test_no_sensitivity_across_tie_counts(self) -> None:
        """After migration, divergence is zero at every tie count for fixed w/l."""
        wins, losses = 6, 2
        for t in (0, 4, 8, 12, 20):
            prod = _production(wins, losses, t)
            dt = _dropties(wins, losses)
            divergence = abs(prod.p_win_rate_exceeds_threshold - dt.p_win_rate_exceeds_threshold)
            assert divergence < 1e-12, (
                f"post-migration divergence {divergence:.6f} at t={t} "
                f"(production p={prod.p_win_rate_exceeds_threshold:.6f}, "
                f"drop-ties p={dt.p_win_rate_exceeds_threshold:.6f})"
            )

    def test_win_heavy_many_ties_passes_where_halfupdate_was_inconclusive(self) -> None:
        """Gate scenario from the finding: w=8, l=0, t=16 is PASSED under production.

        Under half-update this was INCONCLUSIVE (P=0.726). Drop-ties and production
        both give PASSED (P≈0.990 via Beta(9, 1)).
        """
        prod = _production(8, 0, 16)
        dt = _dropties(8, 0)
        legacy = _halfupdate_legacy(8, 0, 16)

        assert prod.stopping_reason == StoppingReason.PASSED
        assert dt.stopping_reason == StoppingReason.PASSED
        assert legacy.stopping_reason is None
        assert abs(prod.p_win_rate_exceeds_threshold - dt.p_win_rate_exceeds_threshold) < 1e-12

    def test_runner_config_records_ratification_thresholds(self) -> None:
        """Acceptance: ratification id and thresholds land in runs.config_json."""
        import json

        config = RunConfig(
            run_id="test-run",
            skill_id="test-skill",
            clauses=[],
            subject_model="claude-sonnet-4-6",
            user_message="hi",
        )
        payload = json.loads(config.to_json())
        gate2 = payload["gate2_stopping"]
        assert gate2["rat_id"] == "RAT-0001"
        assert gate2["gamma"] == 0.90
        assert gate2["delta_min"] == 0.20
        assert gate2["q_min"] == 0.70
        assert gate2["encoding"] == "discordant-gate2"

    def test_runner_imports_discordant_accumulator(self) -> None:
        """Production seam: runner module constructs DiscordantStoppingAccumulator."""
        import inspect

        import skill_harness.ablation.runner as runner_mod

        source = inspect.getsource(runner_mod)
        assert "DiscordantStoppingAccumulator" in source
        assert "BetaBinomialAccumulator" not in source
