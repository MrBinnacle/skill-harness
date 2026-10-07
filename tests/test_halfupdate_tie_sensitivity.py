"""Half-update tie sensitivity detector (#347, falsification plan item 5).

Holds wins and losses fixed, varies tie count, and asserts a documented
sensitivity bound on how far the posterior and stopping decision can move
between the half-update encoding (Tie=0.5, n+=1) and a drop-ties recompute
(filtering observation == 0.5).

Both arms drive the production accumulator (`BetaBinomialAccumulator`). The
drop-ties arm is a comparison oracle built inside the test: no production
drop-ties path exists, and this ticket does not add one. Building it here is
what makes the sensitivity measurable.

When the measured sensitivity is large enough to change a shipped verdict, or
to exceed a bound registered below, the affected scenarios carry
`pytest.mark.xfail(strict=True)` pointing at the findings document. Do not
widen the bound to silence them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from skill_harness.ablation.stopping import (
    BetaBinomialAccumulator,
    StopDecision,
    legacy_halfupdate_decision,
)

# ---------------------------------------------------------------------------
# Sensitivity bounds (registered before measurement; justified below)
# ---------------------------------------------------------------------------
# Decision thresholds sit at P >= 0.95 (PASS) and P <= 0.05 (FAIL). A move of
# 0.25 in P(rate > 0.60) is a quarter of the unit interval and more than half
# the distance from a decisive PASS mass to the inconclusive band midpoint.
# Anything larger is material even when the shipped verdict has not yet flipped.
MAX_P_SENSITIVITY: Final[float] = 0.25

# Posterior means under the locked prior span [0, 1]. A 0.15 absolute shift is
# enough to move a mean across the 0.60 win-rate threshold from a clear win
# signal (e.g. 0.70 → 0.55) while still leaving room for ordinary tie noise.
# Verdict agreement is the hard gate; this bound catches pre-flip drift.
MAX_POSTERIOR_MEAN_SHIFT: Final[float] = 0.15

_FINDING: Final[str] = "docs/findings/halfupdate-tie-sensitivity.md"


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
# first stop-check boundary. win-heavy scenarios (w=8, l=0) with ties produce
# actual verdict flips: drop-ties says PASSED while half-update remains
# inconclusive (stopping_reason is None).
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

# Registered exceedances / verdict flips under the production accumulator.
#
# ALL THREE ARE NOW EMPTY (#368, Path C). The production accumulator
# conditions on the discordant table, so a tie no longer moves the posterior
# and every scenario below agrees with its drop-ties recompute exactly. The
# seven marks that stood here were removed one at a time, each only after the
# assertion it covered began to pass and with its bound unchanged, which is
# the acceptance the ruling required.
#
# The machinery is kept rather than deleted. Strict xfail is how this file
# reports a regression that is understood and measured rather than one that
# is merely red, and re-registering a scenario is the intended way to record
# a future exceedance. An empty set here is a claim: nothing on the fixture
# grid currently exceeds a registered bound.
_XFAIL_MEAN_SHIFT: Final[frozenset[str]] = frozenset()
_XFAIL_P_SENSITIVITY: Final[frozenset[str]] = frozenset()
_XFAIL_VERDICT: Final[frozenset[str]] = frozenset()


def _xfail_mark(
    scenario_label: str,
    bucket: frozenset[str],
    invariant: str,
) -> pytest.MarkDecorator | None:
    if scenario_label not in bucket:
        return None
    return pytest.mark.xfail(
        strict=True,
        reason=(
            f"finding: {_FINDING} (scenario {scenario_label!r}; severity WRONG_NUMBER; {invariant})"
        ),
    )


def _mean_params() -> list[object]:
    params: list[object] = []
    for scenario in SCENARIOS:
        marks = []
        mark = _xfail_mark(
            scenario.label,
            _XFAIL_MEAN_SHIFT,
            f"posterior mean shift exceeds bound {MAX_POSTERIOR_MEAN_SHIFT}",
        )
        if mark is not None:
            marks.append(mark)
        params.append(pytest.param(scenario, id=scenario.label, marks=marks))
    return params


def _p_params() -> list[object]:
    params: list[object] = []
    for scenario in SCENARIOS:
        marks = []
        mark = _xfail_mark(
            scenario.label,
            _XFAIL_P_SENSITIVITY,
            f"P(rate > theta) divergence exceeds bound {MAX_P_SENSITIVITY}",
        )
        if mark is not None:
            marks.append(mark)
        params.append(pytest.param(scenario, id=scenario.label, marks=marks))
    return params


def _verdict_params() -> list[object]:
    params: list[object] = []
    for scenario in SCENARIOS:
        marks = []
        mark = _xfail_mark(
            scenario.label,
            _XFAIL_VERDICT,
            "tie encoding changes shipped verdict",
        )
        if mark is not None:
            marks.append(mark)
        params.append(pytest.param(scenario, id=scenario.label, marks=marks))
    return params


# ---------------------------------------------------------------------------
# Production arms
# ---------------------------------------------------------------------------


def _accumulate(wins: int, losses: int, ties: int = 0) -> StopDecision:
    """Drive the production accumulator; return its stop decision."""
    acc = BetaBinomialAccumulator()
    for _ in range(wins):
        acc.add(1.0)
    for _ in range(losses):
        acc.add(0.0)
    for _ in range(ties):
        acc.add(0.5)
    return acc.check_stop()


def _halfupdate(wins: int, losses: int, ties: int) -> StopDecision:
    """Half-update arm: every observation enters the production accumulator."""
    return _accumulate(wins, losses, ties)


def _dropties(wins: int, losses: int) -> StopDecision:
    """Drop-ties oracle: ties filtered out before accumulation.

    Matches the recompute the falsification plan names (filter observation == 0.5).
    """
    return _accumulate(wins, losses, ties=0)


def _posterior_mean(decision: StopDecision) -> float:
    return decision.posterior_alpha / (decision.posterior_alpha + decision.posterior_beta)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHalfUpdateTieSensitivity:
    """Paired scenarios: fixed wins/losses, varying tie counts.

    Asserts that the half-update and drop-ties posteriors stay within
    documented sensitivity bounds. Known exceedances and verdict flips carry
    strict xfails pointing at the findings document.
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
            f"(half-update mean={hu_mean:.6f}, drop-ties mean={dt_mean:.6f})"
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
            f"(half-update p={hu_p:.6f}, drop-ties p={dt_p:.6f})"
        )

    @pytest.mark.parametrize("scenario", _verdict_params())
    def test_stopping_decision_agreement(self, scenario: Scenario) -> None:
        """Half-update and drop-ties must reach the same stopping verdict.

        If they disagree, the tie encoding is material to the shipped verdict.
        """
        hu_reason = _halfupdate(scenario.wins, scenario.losses, scenario.ties).stopping_reason
        dt_reason = _dropties(scenario.wins, scenario.losses).stopping_reason

        assert hu_reason == dt_reason, (
            f"stopping verdict differs: half-update={hu_reason}, "
            f"drop-ties={dt_reason} for scenario {scenario.label!r}"
        )

    def test_fixture_proves_detector_fires(self) -> None:
        """Positive control: the extreme fixture exceeds every documented bound.

        REPOINTED BY #368, and the reason is the point of the control.

        This test used to compare the production accumulator against the
        drop-ties oracle. Path C made the production accumulator condition on
        the discordant table, so those two arms now agree exactly and the
        divergence is identically zero. Left as it was, the control would
        have gone red; loosened, it would have passed on a measurement of
        nothing. Its own docstring pre-registered this outcome -- "if a future
        encoding change collapses the divergence below the bounds, this test
        goes red and the fixture must be revisited" -- and this is that
        revision.

        The subject is now the SUPERSEDED half-update arithmetic
        (``legacy_halfupdate_decision``), which is what the bounds were
        always about. The bounds themselves are unchanged. The control still
        answers the question it was built to answer: is the gap between the
        two encodings large enough to move a shipped verdict? It fires on the
        same fixture, at the same thresholds, and it still fails loudly if
        that gap ever closes for a reason other than this migration -- which
        would mean the superseded arithmetic had been quietly altered, or the
        fixture had drifted off the region where the encodings disagree.
        """
        # Extreme scenario: 7 wins, 1 loss, 30 ties (n=38 < N_MAX).
        hu = legacy_halfupdate_decision(7, 1, 30)
        dt = _dropties(7, 1)

        hu_p = hu.p_win_rate_exceeds_threshold
        dt_p = dt.p_win_rate_exceeds_threshold
        divergence = abs(hu_p - dt_p)
        assert divergence > MAX_P_SENSITIVITY, (
            f"detector did not fire: P(rate > theta) divergence {divergence:.6f} "
            f"is at or below bound {MAX_P_SENSITIVITY} for extreme scenario "
            f"(7w, 1l, 30t). half-update p={hu_p:.6f}, drop-ties p={dt_p:.6f}"
        )

        hu_mean = _posterior_mean(hu)
        dt_mean = _posterior_mean(dt)
        mean_shift = abs(hu_mean - dt_mean)
        assert mean_shift > MAX_POSTERIOR_MEAN_SHIFT, (
            f"detector did not fire: posterior mean shift {mean_shift:.6f} "
            f"is at or below bound {MAX_POSTERIOR_MEAN_SHIFT} for extreme "
            f"scenario (7w, 1l, 30t). half-update mean={hu_mean:.6f}, "
            f"drop-ties mean={dt_mean:.6f}"
        )

    def test_production_accumulator_no_longer_dilutes(self) -> None:
        """The migration's own claim, asserted rather than assumed.

        The control above proves the superseded encoding still diverges. This
        one proves the PRODUCTION path no longer does, on the same extreme
        fixture. Without it the suite could go green on an accumulator that
        had merely stopped being exercised.
        """
        prod = _halfupdate(7, 1, 30)
        dt = _dropties(7, 1)

        assert prod.posterior_alpha == dt.posterior_alpha
        assert prod.posterior_beta == dt.posterior_beta
        assert prod.p_win_rate_exceeds_threshold == dt.p_win_rate_exceeds_threshold
        assert prod.stopping_reason == dt.stopping_reason
        # The ties are recorded, not discarded: Path C reads them back out to
        # apply the effect-size floor (see ablation/path_c.py).
        assert prod.n_ties == 30
        assert prod.n_discordant == 8
        assert prod.n_samples == 38
        # And the superseded weight stays reconstructible from the decision.
        assert prod.w_accumulator == 7.0 + 0.5 * 30

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
