"""Gate-2 discordant stopping rule for the ablation lane (#368).

Routes tie-heavy clause decisions through the Gate-2 three-sided paired rule
(``oc/gate2.py``), consuming the registered design form and thresholds from
Amendment 4 of ``docs/findings/v0.2-preregistration.md``.

When ties are present (observation count includes concordant pairs), the scalar
half-update encoding dilutes the posterior toward 0.50 (#347 item 5 finding).
The discordant table (McNemar/sign-test convention) is the estimand of record
(INVARIANTS §8, ruled 2026-08-31 on #368). This module routes tie-heavy
decisions through Gate-2's Dirichlet posterior over the discordant lattice,
producing a ``StopDecision`` compatible with the existing ablation runner.

The scalar ``BetaBinomialAccumulator`` (``stopping.py`) remains the legacy
artifact for zero-tie cases and is NOT modified (#42: parallel machinery,
not a refactor).

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
# record. n_pairs is the total observation count at the current stop-check.

_GATE2_GAMMA: Final[float] = 0.90
_GATE2_DELTA_MIN: Final[float] = 0.20
_GATE2_Q_MIN: Final[float] = 0.70


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
    (unchanged legacy path). When ties > 0, the decision comes from
    Gate-2's three-sided rule over the discordant table; the posterior
    parameters and ``p_win_rate_exceeds_threshold`` are computed from the
    discordant-only ``Beta(1+w, 1+l)``, matching the drop-ties encoding
    (INVARIANTS §8: discordant table is the estimand of record).

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

    # No ties: scalar path (unchanged)
    if ties == 0:
        acc = BetaBinomialAccumulator()
        for _ in range(wins):
            acc.add(1.0)
        for _ in range(losses):
            acc.add(0.0)
        return acc.check_stop()

    # Ties present: route through Gate-2
    n_pairs = wins + losses + ties
    design = _registered_design(n_pairs)
    decision = gate2_decide(design, wins, losses)

    # Posterior from discordant-only Beta(1+w, 1+l)
    alpha = 1.0 + wins
    beta_param = 1.0 + losses
    p = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))

    # Map Gate-2 decision to stopping reason.
    # When Gate-2 certifies (BENEFIT/HARM), that decision takes priority.
    # When Gate-2 is UNRESOLVED, fall back to the scalar thresholds on the
    # discordant-only Beta — this matches the drop-ties recompute and ensures
    # the two paths agree on the fixture scenarios (#368).
    if decision == Gate2Decision.BENEFIT:
        should_stop = True
        reason = StoppingReason.PASSED
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

    return StopDecision(
        should_stop=should_stop,
        stopping_reason=reason,
        posterior_alpha=alpha,
        posterior_beta=beta_param,
        p_win_rate_exceeds_threshold=p,
        n_samples=wins + losses,
        w_accumulator=float(wins),
    )
