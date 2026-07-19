"""Sequential stopping rule for ablation sampling (A8, A44).

Implements the Beta-Binomial posterior sequential test:
  Prior: Beta(1, 1) (uniform)
  Update: Beta(1 + w, 1 + n - w) where w = sum of Win/Tie contributions
          Win = 1.0, Tie = 0.5, Loss = 0.0 (A10 half-update encoding)
  PASS  : P(win_rate > 0.60) >= 0.95
  FAIL  : P(win_rate > 0.60) <= 0.05
  STOP  : N_max reached without pass/fail → UNMEASURED(underpowered_nmax)

Sampling schedule (A8):
  N_min = 8   — minimum samples before first stop check
  N_inc = 4   — batch size between stop checks
  N_max = 40  — hard cap (no calls past this)

Design:
- The stopping module is PURELY deterministic computation — no DB, no API calls.
- The runner calls check_stop() after each N_inc batch to decide whether to continue.
- w and n accumulate fractional values due to Tie = 0.5 half-update encoding (A10).
- scipy.stats.beta.sf (survival function) evaluates P(rate > 0.60) from the posterior.

Per the pass rule (locked — do not silently retune thresholds; see docs/INVARIANTS.md #1):
  "P(win_rate > 0.60) >= 0.95 under Beta(1,1) -> Beta(1+w, 1+n-w)"
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

# Pass/fail thresholds (CLAUDE.md pass rule — locked)
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
    """Result of a stop check after processing N samples.

    Fields
    ------
    should_stop : bool
        True if sampling should terminate NOW (regardless of reason).
    stopping_reason : StoppingReason | None
        Set when should_stop=True. None when sampling should continue.
    posterior_alpha : float
        Beta posterior alpha = 1 + w (wins accumulator).
    posterior_beta : float
        Beta posterior beta = 1 + (n - w) (losses accumulator).
    p_win_rate_exceeds_threshold : float
        P(win_rate > WIN_RATE_THRESHOLD) under the current posterior.
    n_samples : int
        Number of directional comparisons included in this posterior.
    w_accumulator : float
        Accumulated win-weight (Win=1, Tie=0.5, Loss=0 per comparison).
    """

    should_stop: bool
    stopping_reason: StoppingReason | None
    posterior_alpha: float
    posterior_beta: float
    p_win_rate_exceeds_threshold: float
    n_samples: int
    w_accumulator: float


# ---------------------------------------------------------------------------
# BetaBinomialAccumulator
# ---------------------------------------------------------------------------


class BetaBinomialAccumulator:
    """Accumulates wins/ties/losses and evaluates the Beta-Binomial stopping rule.

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
    - Only admissible observations should be added (caller responsibility).
    - The accumulator is MUTABLE — call add() then check_stop() as samples arrive.
    """

    def __init__(self) -> None:
        self._w: float = 0.0  # win-weight accumulator (fractional due to ties)
        self._n: float = 0.0  # sample count (int but stored as float for type uniformity)

    @property
    def n(self) -> int:
        """Number of observations added so far."""
        return int(self._n)

    @property
    def w(self) -> float:
        """Win-weight accumulator (sum of 1.0/0.5/0.0 per observation)."""
        return self._w

    def add(self, observation: float) -> None:
        """Add a directional comparison result.

        :param observation: 1.0 (win), 0.5 (tie), or 0.0 (loss).
        :raises ValueError: If observation is not one of the allowed values.
        """
        if observation not in {0.0, 0.5, 1.0}:
            raise ValueError(
                f"Observation must be 0.0 (loss), 0.5 (tie), or 1.0 (win); got {observation!r}"
            )
        self._w += observation
        self._n += 1.0

    def _posterior(self) -> tuple[float, float]:
        """Return (alpha, beta) for the current Beta posterior.

        Prior Beta(1, 1). Update: Beta(1+w, 1+(n-w)).
        """
        alpha = 1.0 + self._w
        beta_param = 1.0 + (self._n - self._w)
        return alpha, beta_param

    def p_exceeds(self) -> float:
        """P(win_rate > WIN_RATE_THRESHOLD) under the current Beta posterior."""
        alpha, beta_param = self._posterior()
        # beta_dist.sf(x, a, b) = P(X > x) for X ~ Beta(a, b)
        return float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))

    def check_stop(self) -> StopDecision:
        """Evaluate the sequential stopping rule.

        Returns a StopDecision; should_stop=True when:
        - p >= PASS_PROB_THRESHOLD (PASSED)
        - p <= FAIL_PROB_THRESHOLD (FAILED)
        - n >= N_MAX (UNDERPOWERED_NMAX) — caller is responsible for NOT calling
          this beyond N_MAX; this is the hard-stop gate.

        should_stop=False when n < N_MIN (not enough data for first check) OR
        FAIL < p < PASS (inconclusive — add more samples).

        :returns: StopDecision with full posterior metadata.
        """
        alpha, beta_param = self._posterior()
        p = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta_param))
        n = int(self._n)

        # Hard cap — N_MAX reached without a decisive posterior
        if n >= N_MAX:
            if p >= PASS_PROB_THRESHOLD:
                reason: StoppingReason | None = StoppingReason.PASSED
                stop = True
            elif p <= FAIL_PROB_THRESHOLD:
                reason = StoppingReason.FAILED
                stop = True
            else:
                reason = StoppingReason.UNDERPOWERED_NMAX
                stop = True
            return StopDecision(
                should_stop=stop,
                stopping_reason=reason,
                posterior_alpha=alpha,
                posterior_beta=beta_param,
                p_win_rate_exceeds_threshold=p,
                n_samples=n,
                w_accumulator=self._w,
            )

        # Before N_MIN: never stop (not enough data)
        if n < N_MIN:
            return StopDecision(
                should_stop=False,
                stopping_reason=None,
                posterior_alpha=alpha,
                posterior_beta=beta_param,
                p_win_rate_exceeds_threshold=p,
                n_samples=n,
                w_accumulator=self._w,
            )

        # After N_MIN: check thresholds
        if p >= PASS_PROB_THRESHOLD:
            return StopDecision(
                should_stop=True,
                stopping_reason=StoppingReason.PASSED,
                posterior_alpha=alpha,
                posterior_beta=beta_param,
                p_win_rate_exceeds_threshold=p,
                n_samples=n,
                w_accumulator=self._w,
            )

        if p <= FAIL_PROB_THRESHOLD:
            return StopDecision(
                should_stop=True,
                stopping_reason=StoppingReason.FAILED,
                posterior_alpha=alpha,
                posterior_beta=beta_param,
                p_win_rate_exceeds_threshold=p,
                n_samples=n,
                w_accumulator=self._w,
            )

        # Inconclusive — add more samples (up to next N_INC boundary check)
        return StopDecision(
            should_stop=False,
            stopping_reason=None,
            posterior_alpha=alpha,
            posterior_beta=beta_param,
            p_win_rate_exceeds_threshold=p,
            n_samples=n,
            w_accumulator=self._w,
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
