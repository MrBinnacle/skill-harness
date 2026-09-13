"""Sequential stopping rule for ablation sampling (A8, A44).

Implements the Beta-Binomial posterior sequential test on the DISCORDANT
TABLE (#368 Path C, ruled 2026-08-31; see docs/INVARIANTS.md section 8):
  Prior: Beta(1, 1) (uniform)
  Update: Beta(1 + x_f, 1 + x_n), where x_f = comparisons Full won and
          x_n = comparisons Ablated_k won. Ties are RECORDED and never
          enter the posterior.
  PASS  : P(q > 0.60) >= 0.95
  FAIL  : P(q > 0.60) <= 0.05
  STOP  : N_max reached without pass/fail -> UNMEASURED(underpowered_nmax)

The estimand is q = P(Full wins | discordant). A tie is a concordant
comparison: Full and Ablated_k scored equal on the axis, so it carries no
directional information about which is better. Crediting half a win and half
a loss for it does not encode ignorance, it fabricates an observation, and it
drags the posterior mean toward 0.50 in proportion to a quantity that says
nothing about the sign of the effect. That is the defect #347 measured and
#368 ruled on.

Ties are still counted, because the tie count is not worthless: it is the
evidence about the discordance rate d, and the net lift delta = d(2q - 1)
needs both. This module reports q. The effect-size floor that stops a large q
on two discordant comparisons from certifying a benefit is applied by
``ablation/path_c.py``, which reads the tie count back out.

Sampling schedule (A8):
  N_min = 8   - minimum DISCORDANT comparisons before the first stop check
  N_inc = 4   - batch size between stop checks
  N_max = 40  - hard cap on TOTAL comparisons (no calls past this)

The two gates read different counts on purpose. N_max bounds spend, and a
comparison costs the same whether or not it turns out to be a tie, so it
counts total comparisons. N_min bounds evidence, and a tie is not evidence
about q, so it counts discordant comparisons. Reading N_min off the total
would let a tie-dominated clause reach its first stop check with almost no
directional evidence, which is the state the old encoding papered over by
filling the posterior with half-observations.

Design:
- The stopping module is PURELY deterministic computation - no DB, no API calls.
- The runner calls check_stop() after each N_inc batch to decide whether to continue.
- scipy.stats.beta.sf (survival function) evaluates P(q > 0.60) from the posterior.

Per the pass rule (locked - do not silently retune thresholds; see
docs/INVARIANTS.md #1): P(rate > 0.60) >= 0.95 under Beta(1,1) updated to
Beta(1+w, 1+n-w). On a clause with no ties this module computes exactly that,
because x_f = w and x_n = n - w. The migration is therefore a no-op wherever
the blended rate and the conditional rate coincide, and changes only clauses
that recorded ties, which is precisely the footprint of the defect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Locked constants (A8, A44 — do NOT change without a [values decision])
# ---------------------------------------------------------------------------

N_MIN: Final[int] = 8
"""Minimum samples per condition pair before first stop check."""

N_INC: Final[int] = 4
"""Increment between stop checks after N_MIN is reached."""

N_MAX: Final[int] = 40
"""Hard sample cap per condition pair (A44: no batches past N_MAX)."""

# Pass/fail thresholds (pass rule — locked; see docs/INVARIANTS.md #1)
WIN_RATE_THRESHOLD: Final[float] = 0.60
PASS_PROB_THRESHOLD: Final[float] = 0.95
FAIL_PROB_THRESHOLD: Final[float] = 0.05


# ---------------------------------------------------------------------------
# StoppingReason
# ---------------------------------------------------------------------------


class StoppingReason(StrEnum):
    """Reason a sampling loop terminated (A44 — recorded in run config snapshot)."""

    PASSED = "passed"
    """P(win_rate > 0.60) >= 0.95 — clause passed."""

    FAILED = "failed"
    """P(win_rate > 0.60) <= 0.05 — clause failed."""

    UNDERPOWERED_NMAX = "underpowered_nmax"
    """N_MAX reached without a stop → UNMEASURED(underpowered)."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """Budget cap exceeded before N_MAX — sampling aborted."""


# ---------------------------------------------------------------------------
# StopDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StopDecision:
    """Result of a stop check after processing N comparisons.

    Fields
    ------
    should_stop : bool
        True if sampling should terminate NOW (regardless of reason).
    stopping_reason : StoppingReason | None
        Set when should_stop=True. None when sampling should continue.
    posterior_alpha : float
        Beta posterior alpha = 1 + x_f (discordant comparisons Full won).
    posterior_beta : float
        Beta posterior beta = 1 + x_n (discordant comparisons Ablated_k won).
    p_win_rate_exceeds_threshold : float
        P(q > WIN_RATE_THRESHOLD) under the current posterior, where q is the
        conditional win rate P(Full wins | discordant).
    n_samples : int
        TOTAL comparisons drawn, ties included. This is the spend count and
        the number N_MAX is read against; it is NOT the number of
        observations in the posterior.
    w_accumulator : float
        Legacy blended win-weight (Win=1, Tie=0.5, Loss=0). Retained as a
        RECORD of what was observed so an existing reader does not silently
        change meaning, and so the superseded encoding stays reconstructible
        from a stored decision. It no longer determines the posterior: see
        docs/INVARIANTS.md section 8 and #368.
    n_discordant : int
        Comparisons that carried a direction, x_f + x_n. This is the evidence
        count and the number N_MIN is read against.
    x_full_wins : int
        Discordant comparisons Full won (x_f).
    x_ablated_wins : int
        Discordant comparisons Ablated_k won (x_n).
    n_ties : int
        Concordant comparisons. Excluded from the posterior over q, and
        carried because the discordance rate d = n_discordant / n_samples is
        what the Path C effect-size floor needs (ablation/path_c.py).
    """

    should_stop: bool
    stopping_reason: StoppingReason | None
    posterior_alpha: float
    posterior_beta: float
    p_win_rate_exceeds_threshold: float
    n_samples: int
    w_accumulator: float
    n_discordant: int
    x_full_wins: int
    x_ablated_wins: int
    n_ties: int


# ---------------------------------------------------------------------------
# BetaBinomialAccumulator
# ---------------------------------------------------------------------------


class BetaBinomialAccumulator:
    """Accumulates a discordant table and evaluates the stopping rule.

    Usage
    -----
    acc = BetaBinomialAccumulator()
    for observation in observations:
        acc.add(observation)  # 1.0 = win, 0.5 = tie, 0.0 = loss
    decision = acc.check_stop()

    Notes
    -----
    - observation is the directional comparison score: does Full beat Ablated_k on axis X?
      Win=1.0 (Full wins), Tie=0.5, Loss=0.0 (Ablated_k wins / Full does not beat Ablated_k).
    - The accepted observation values are UNCHANGED. ``delta_to_observation``
      still returns 0.5 for a tie, because the encoding was never the defect
      (#368): a tie is a real, observed, correctly-labelled outcome. What
      changed is what this class does with it. A tie is now counted, not
      credited to both sides of the posterior.
    - Only admissible observations should be added (caller responsibility).
    - The accumulator is MUTABLE — call add() then check_stop() as samples arrive.
    """

    def __init__(self) -> None:
        self._x_f: int = 0  # discordant comparisons Full won
        self._x_n: int = 0  # discordant comparisons Ablated_k won
        self._ties: int = 0  # concordant comparisons (recorded, not credited)

    @property
    def n(self) -> int:
        """TOTAL comparisons added so far, ties included (the spend count)."""
        return self._x_f + self._x_n + self._ties

    @property
    def n_discordant(self) -> int:
        """Comparisons carrying a direction, x_f + x_n (the evidence count)."""
        return self._x_f + self._x_n

    @property
    def x_full_wins(self) -> int:
        """Discordant comparisons Full won (x_f)."""
        return self._x_f

    @property
    def x_ablated_wins(self) -> int:
        """Discordant comparisons Ablated_k won (x_n)."""
        return self._x_n

    @property
    def n_ties(self) -> int:
        """Concordant comparisons recorded."""
        return self._ties

    @property
    def w(self) -> float:
        """Legacy blended win-weight (sum of 1.0/0.5/0.0 per comparison).

        Kept as a record of the observations, not as a posterior input. See
        ``StopDecision.w_accumulator``.
        """
        return float(self._x_f) + 0.5 * float(self._ties)

    def add(self, observation: float) -> None:
        """Add a directional comparison result.

        :param observation: 1.0 (win), 0.5 (tie), or 0.0 (loss).
        :raises ValueError: If observation is not one of the allowed values.
        """
        if observation not in {0.0, 0.5, 1.0}:
            raise ValueError(
                f"Observation must be 0.0 (loss), 0.5 (tie), or 1.0 (win); got {observation!r}"
            )
        if observation == 1.0:
            self._x_f += 1
        elif observation == 0.0:
            self._x_n += 1
        else:
            self._ties += 1

    def _posterior(self) -> tuple[float, float]:
        """Return (alpha, beta) for the current Beta posterior over q.

        Prior Beta(1, 1). Update: Beta(1 + x_f, 1 + x_n). Ties do not appear:
        conditioning on the discordant table is the estimand of record
        (docs/INVARIANTS.md section 8).
        """
        return 1.0 + float(self._x_f), 1.0 + float(self._x_n)

    def p_exceeds(self) -> float:
        """P(q > WIN_RATE_THRESHOLD) under the current Beta posterior."""
        alpha, beta_param = self._posterior()
        # beta_dist.sf(x, a, b) = P(X > x) for X ~ Beta(a, b)
        return float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))

    def _decide(self, should_stop: bool, reason: StoppingReason | None) -> StopDecision:
        """Build a StopDecision from the current state (single construction site)."""
        alpha, beta_param = self._posterior()
        return StopDecision(
            should_stop=should_stop,
            stopping_reason=reason,
            posterior_alpha=alpha,
            posterior_beta=beta_param,
            p_win_rate_exceeds_threshold=float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param)),
            n_samples=self.n,
            w_accumulator=self.w,
            n_discordant=self.n_discordant,
            x_full_wins=self._x_f,
            x_ablated_wins=self._x_n,
            n_ties=self._ties,
        )

    def check_stop(self) -> StopDecision:
        """Evaluate the sequential stopping rule.

        Returns a StopDecision; should_stop=True when:
        - p >= PASS_PROB_THRESHOLD (PASSED)
        - p <= FAIL_PROB_THRESHOLD (FAILED)
        - n >= N_MAX (UNDERPOWERED_NMAX) - caller is responsible for NOT calling
          this beyond N_MAX; this is the hard-stop gate.

        should_stop=False when n_discordant < N_MIN (not enough directional
        evidence for a first check) OR FAIL < p < PASS (inconclusive - add
        more samples).

        The N_MAX gate reads the TOTAL comparison count and the N_MIN gate
        reads the DISCORDANT count. A tie costs a sample but supplies no
        evidence about q, so it must extend the spend and must not advance
        the evidence bar.

        :returns: StopDecision with full posterior metadata.
        """
        p = self.p_exceeds()

        # Hard cap - N_MAX total comparisons reached
        if self.n >= N_MAX:
            if p >= PASS_PROB_THRESHOLD:
                return self._decide(True, StoppingReason.PASSED)
            if p <= FAIL_PROB_THRESHOLD:
                return self._decide(True, StoppingReason.FAILED)
            return self._decide(True, StoppingReason.UNDERPOWERED_NMAX)

        # Before N_MIN discordant comparisons: never stop (not enough evidence)
        if self.n_discordant < N_MIN:
            return self._decide(False, None)

        # After N_MIN: check thresholds
        if p >= PASS_PROB_THRESHOLD:
            return self._decide(True, StoppingReason.PASSED)

        if p <= FAIL_PROB_THRESHOLD:
            return self._decide(True, StoppingReason.FAILED)

        # Inconclusive - add more samples (up to next N_INC boundary check)
        return self._decide(False, None)


def legacy_halfupdate_decision(wins: int, losses: int, ties: int) -> StopDecision:
    """The SUPERSEDED half-update rule, preserved as a named reference.

    Beta(1 + w, 1 + n - w) with w = wins + 0.5 * ties and n = wins + losses +
    ties: the encoding #368 replaced. It is not a production path and nothing
    in ``src/`` calls it.

    It exists so the tie-sensitivity detector
    (``tests/test_halfupdate_tie_sensitivity.py``) keeps a live subject. That
    detector proves the divergence between the two encodings is large enough
    to move a shipped verdict. Once the production accumulator conditions on
    the discordant table, the divergence against the production path is
    identically zero, and a positive control measured against zero is a
    vacuous control that would pass forever without testing anything. Keeping
    the superseded arithmetic addressable keeps that control honest: it still
    measures the real gap between the two encodings, and it still fails if
    that gap ever closes for a reason other than this migration.

    :param wins: Comparisons Full won.
    :param losses: Comparisons Ablated_k won.
    :param ties: Concordant comparisons.
    :returns: The StopDecision the half-update rule would have produced.
    :raises ValueError: If any count is negative.
    """
    if wins < 0 or losses < 0 or ties < 0:
        raise ValueError(f"counts must be >= 0; got wins={wins}, losses={losses}, ties={ties}")
    n = wins + losses + ties
    w = float(wins) + 0.5 * float(ties)
    alpha = 1.0 + w
    beta_param = 1.0 + (float(n) - w)
    p = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))

    if n >= N_MAX:
        if p >= PASS_PROB_THRESHOLD:
            reason: StoppingReason | None = StoppingReason.PASSED
        elif p <= FAIL_PROB_THRESHOLD:
            reason = StoppingReason.FAILED
        else:
            reason = StoppingReason.UNDERPOWERED_NMAX
        should_stop = True
    elif n < N_MIN:
        reason, should_stop = None, False
    elif p >= PASS_PROB_THRESHOLD:
        reason, should_stop = StoppingReason.PASSED, True
    elif p <= FAIL_PROB_THRESHOLD:
        reason, should_stop = StoppingReason.FAILED, True
    else:
        reason, should_stop = None, False

    return StopDecision(
        should_stop=should_stop,
        stopping_reason=reason,
        posterior_alpha=alpha,
        posterior_beta=beta_param,
        p_win_rate_exceeds_threshold=p,
        n_samples=n,
        w_accumulator=w,
        n_discordant=wins + losses,
        x_full_wins=wins,
        x_ablated_wins=losses,
        n_ties=ties,
    )


def next_check_at(n: int) -> int:
    """Return the sample count at which the next stop check should occur.

    Schedule: first check at N_MIN, then every N_INC thereafter.
    Calls beyond N_MAX should never happen (caller enforces this).

    :param n: Current sample count.
    :returns: The sample count at which to call check_stop() next.
    """
    if n < N_MIN:
        return N_MIN
    # Next multiple of N_INC after current n, but no higher than N_MAX
    next_batch = ((n // N_INC) + 1) * N_INC
    return min(next_batch, N_MAX)
