"""Gate-2 discordant stopping rule for the ablation lane (#368).

Routes tie-heavy clause decisions through the Gate-2 three-sided paired rule
(``oc/gate2.py``), consuming the registered design form and thresholds from
Amendment 4 of ``docs/findings/v0.2-preregistration.md`` (RAT-0001).

When ties are present the scalar half-update encoding dilutes the posterior
toward 0.50 (#347 item 5 finding). The discordant table (McNemar/sign-test
convention) is the estimand of record (INVARIANTS §8, ruled 2026-08-31 on
#368). This module is the production stopping path for the ablation runner:
``DiscordantStoppingAccumulator`` replaces ``BetaBinomialAccumulator`` at the
runner seam.

The scalar ``BetaBinomialAccumulator`` (``stopping.py``) remains the legacy
artifact for zero-tie cases inside this module and for calibration/sizing
callers, and is NOT modified (#42: parallel machinery, not a refactor).

Registered thresholds (Amendment 4, PR #386, RAT-0001):
  gamma = 0.90, delta_min = 0.20, q_min = 0.70

Blocked by: nothing.
Revisit if: #420's re-pick changes gamma or delta_min; or the grid limits in
  INVARIANTS §8 are exceeded (w, l > 60 or t > 80).
"""

from __future__ import annotations

from typing import Final

from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.ablation.stopping import (
    FAIL_PROB_THRESHOLD,
    N_MAX,
    N_MIN,
    PASS_PROB_THRESHOLD,
    WIN_RATE_THRESHOLD,
    BetaBinomialAccumulator,
    StopDecision,
    StoppingReason,
)
from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec, gate2_decide

# ---------------------------------------------------------------------------
# Registered design (Amendment 4, PR #386, RAT-0001)
# ---------------------------------------------------------------------------
# gamma and delta_min/q_min are consumed by reference from the ratification
# record. n_pairs for the sequential stop-check is the total observation count
# at that check (wins + losses + ties), not the fixed paired-lane row n=32.
# The build therefore does not wait on #420's fresh record for n.

RAT_ID: Final[str] = "RAT-0001"
RAT_SOURCE: Final[str] = "docs/ratifications/RAT-0001-git-pull-rebase-trap.md"
_GATE2_GAMMA: Final[float] = 0.90
_GATE2_DELTA_MIN: Final[float] = 0.20
_GATE2_Q_MIN: Final[float] = 0.70


def registered_thresholds() -> dict[str, float | str]:
    """Thresholds and ratification id recorded into runs.config_json (#368)."""
    return {
        "rat_id": RAT_ID,
        "rat_source": RAT_SOURCE,
        "gamma": _GATE2_GAMMA,
        "delta_min": _GATE2_DELTA_MIN,
        "q_min": _GATE2_Q_MIN,
        "encoding": "discordant-gate2",
    }


def _registered_design(n_pairs: int) -> Gate2Design:
    """Build a Gate2Design from the registered thresholds and current n.

    :param n_pairs: Total observation count (wins + losses + ties).
    :returns: A Gate2Design with the registered parameters.
    :raises ValueError: If n_pairs < 1.
    """
    return Gate2Design(
        n_pairs=n_pairs,
        gamma=_GATE2_GAMMA,
        mme=MMESpec(delta_min=_GATE2_DELTA_MIN, q_min=_GATE2_Q_MIN),
    )


# ---------------------------------------------------------------------------
# Gate-2 stopping decision
# ---------------------------------------------------------------------------


def gate2_stopping_decision(
    wins: int,
    losses: int,
    ties: int,
) -> StopDecision:
    """Route a clause's stopping decision through Gate-2 discordant machinery.

    When ties == 0, falls back to the scalar ``BetaBinomialAccumulator``
    (unchanged legacy path, including N_MIN/N_MAX). When ties > 0, the
    decision comes from Gate-2's three-sided rule over the discordant table;
    the posterior parameters and ``p_win_rate_exceeds_threshold`` are computed
    from the discordant-only ``Beta(1+w, 1+l)``, matching the drop-ties
    encoding (INVARIANTS §8: discordant table is the estimand of record).
    N_MIN and N_MAX apply to the total observation count (wins + losses + ties).

    :param wins: Number of Full-only-win (discordant) observations.
    :param losses: Number of Null-only-win (discordant) observations.
    :param ties: Number of concordant/tie observations.
    :returns: A ``StopDecision`` compatible with the ablation runner.
    :raises ValueError: If any count is negative or all counts are zero.
    """
    if wins < 0 or losses < 0 or ties < 0:
        raise ValueError(
            f"counts must be >= 0; got wins={wins}, losses={losses}, ties={ties}"
        )
    if wins + losses + ties == 0:
        raise ValueError("at least one observation is required")

    # No ties: scalar path (unchanged; carries N_MIN/N_MAX)
    if ties == 0:
        acc = BetaBinomialAccumulator()
        for _ in range(wins):
            acc.add(1.0)
        for _ in range(losses):
            acc.add(0.0)
        return acc.check_stop()

    # Ties present: route through Gate-2
    n_total = wins + losses + ties
    design = _registered_design(n_total)
    decision = gate2_decide(design, wins, losses)

    # Posterior from discordant-only Beta(1+w, 1+l)
    alpha = 1.0 + wins
    beta_param = 1.0 + losses
    p = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))

    # Map Gate-2 decision to stopping reason.
    # When Gate-2 certifies (BENEFIT/HARM), that decision takes priority.
    # When Gate-2 is UNRESOLVED (or EQUIVALENT), fall back to the scalar
    # thresholds on the discordant-only Beta — this matches the drop-ties
    # recompute and ensures the two paths agree on the fixture scenarios (#368).
    if decision == Gate2Decision.BENEFIT:
        should_stop = True
        reason: StoppingReason | None = StoppingReason.PASSED
    elif decision == Gate2Decision.HARM:
        should_stop = True
        reason = StoppingReason.FAILED
    elif p >= PASS_PROB_THRESHOLD:
        should_stop = True
        reason = StoppingReason.PASSED
    elif p <= FAIL_PROB_THRESHOLD:
        should_stop = True
        reason = StoppingReason.FAILED
    else:
        should_stop = False
        reason = None

    # N_MIN / N_MAX on total observations (schedule identity with the runner)
    if n_total < N_MIN:
        should_stop = False
        reason = None
    elif n_total >= N_MAX:
        if reason is None:
            should_stop = True
            reason = StoppingReason.UNDERPOWERED_NMAX
        else:
            should_stop = True

    return StopDecision(
        should_stop=should_stop,
        stopping_reason=reason,
        posterior_alpha=alpha,
        posterior_beta=beta_param,
        p_win_rate_exceeds_threshold=p,
        n_samples=wins + losses,
        w_accumulator=float(wins),
    )


# ---------------------------------------------------------------------------
# Production accumulator (ablation runner seam)
# ---------------------------------------------------------------------------


class DiscordantStoppingAccumulator:
    """Production stopping accumulator for the ablation lane (#368 Path C).

    Tracks win / loss / tie counts separately. ``n`` is the total observation
    count (schedule identity with the former half-update accumulator).
    ``check_stop`` routes through :func:`gate2_stopping_decision`.
    """

    def __init__(self) -> None:
        self._wins: int = 0
        self._losses: int = 0
        self._ties: int = 0

    @property
    def n(self) -> int:
        """Total observations added so far (wins + losses + ties)."""
        return self._wins + self._losses + self._ties

    @property
    def w(self) -> float:
        """Discordant win count as float (ties do not contribute)."""
        return float(self._wins)

    @property
    def wins(self) -> int:
        return self._wins

    @property
    def losses(self) -> int:
        return self._losses

    @property
    def ties(self) -> int:
        return self._ties

    def add(self, observation: float) -> None:
        """Add a directional comparison result.

        :param observation: 1.0 (win), 0.5 (tie), or 0.0 (loss).
        :raises ValueError: If observation is not one of the allowed values.
        """
        if observation == 1.0:
            self._wins += 1
        elif observation == 0.0:
            self._losses += 1
        elif observation == 0.5:
            self._ties += 1
        else:
            raise ValueError(
                f"Observation must be 0.0 (loss), 0.5 (tie), or 1.0 (win); got {observation!r}"
            )

    def check_stop(self) -> StopDecision:
        """Evaluate the Gate-2 discordant stopping rule on accumulated counts."""
        if self.n == 0:
            p = float(beta_dist.sf(WIN_RATE_THRESHOLD, 1.0, 1.0))
            return StopDecision(
                should_stop=False,
                stopping_reason=None,
                posterior_alpha=1.0,
                posterior_beta=1.0,
                p_win_rate_exceeds_threshold=p,
                n_samples=0,
                w_accumulator=0.0,
            )
        return gate2_stopping_decision(self._wins, self._losses, self._ties)
