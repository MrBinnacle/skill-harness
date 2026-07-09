"""Analytic sizing for the sequential stopping rule (exact, $0).

Answers, BEFORE any paid sampling: given the locked Beta-Binomial rule in
:mod:`skill_harness.ablation.stopping`, what are the exact probabilities of
PASS / FAIL / UNMEASURED(underpowered_nmax) and the expected sample count,
as a function of the generative observation distribution?

Generative model (paired Full-vs-Null, per epoch):

    d = discordance rate      P(observation != tie) = 1 - tie rate
    q = P(Full wins | discordant)

    P(win)  = d * q          -> observation 1.0
    P(tie)  = 1 - d          -> observation 0.5
    P(loss) = d * (1 - q)    -> observation 0.0

Why (d, q) and not a single "true win rate": ties carry no directional
signal under the half-update encoding but still consume samples, so the
tie rate — not the effect size — is what decides whether the rule can
reach a verdict inside N_MAX at all. The noise micro-run measures d
empirically; this module maps the measured d to the minimum detectable
q and the expected cost, filling the pre-registration MDE/sizing field
without simulation error.

Method: exact dynamic programming over the (n, 2w) lattice. The win-weight
w advances in half-steps (Tie = 0.5), so 2w is an integer in [0, 2n] and
the state space is exact — no Monte Carlo, no seeds. Stop checks are
applied exactly where the runner applies them: at N_MIN, then every N_INC,
with unconditional absorption at N_MAX.

All rule constants are imported from the stopping module — this module
must never restate them (single source of truth for the locked rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.ablation.stopping import (
    FAIL_PROB_THRESHOLD,
    N_INC,
    N_MAX,
    N_MIN,
    PASS_PROB_THRESHOLD,
    WIN_RATE_THRESHOLD,
)

# ---------------------------------------------------------------------------
# SizingResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SizingResult:
    """Exact absorption profile of the stopping rule for one (d, q) point.

    Fields
    ------
    discordance_rate : float
        d — probability an epoch is NOT a tie.
    win_given_discordant : float
        q — probability Full wins, conditional on a discordant epoch.
    p_pass : float
        Exact probability the rule terminates PASSED.
    p_fail : float
        Exact probability the rule terminates FAILED.
    p_unmeasured : float
        Exact probability of UNDERPOWERED_NMAX (no verdict inside N_MAX).
    expected_n : float
        Expected number of observations consumed (absorption time).
    """

    discordance_rate: float
    win_given_discordant: float
    p_pass: float
    p_fail: float
    p_unmeasured: float
    expected_n: float


# ---------------------------------------------------------------------------
# Exact DP
# ---------------------------------------------------------------------------


@cache
def _p_exceeds(n: int, w2: int) -> float:
    """P(win_rate > WIN_RATE_THRESHOLD) for posterior after n obs with 2w = w2."""
    w = w2 / 2.0
    return float(beta_dist.sf(WIN_RATE_THRESHOLD, 1.0 + w, 1.0 + (n - w)))


def _check_points() -> set[int]:
    """Sample counts at which the runner performs a stop check (before N_MAX)."""
    return set(range(N_MIN, N_MAX, N_INC))


def solve(discordance_rate: float, win_given_discordant: float) -> SizingResult:
    """Exactly solve the stopping rule's absorption profile for one (d, q).

    :param discordance_rate: d in [0, 1] — per-epoch probability of a
        non-tie observation.
    :param win_given_discordant: q in [0, 1] — P(Full wins | discordant).
    :returns: SizingResult with exact absorption probabilities and E[N].
    :raises ValueError: If either parameter is outside [0, 1].
    """
    d, q = discordance_rate, win_given_discordant
    if not (0.0 <= d <= 1.0 and 0.0 <= q <= 1.0):
        raise ValueError(f"d and q must lie in [0, 1]; got d={d!r}, q={q!r}")

    p_win, p_tie, p_loss = d * q, 1.0 - d, d * (1.0 - q)
    checks = _check_points()

    # alive[w2] = probability of being un-absorbed with win-weight w2/2
    alive: dict[int, float] = {0: 1.0}
    p_pass = p_fail = p_unmeasured = expected_n = 0.0

    for n in range(1, N_MAX + 1):
        stepped: dict[int, float] = {}
        for w2, pr in alive.items():
            for dw2, pp in ((2, p_win), (1, p_tie), (0, p_loss)):
                if pp > 0.0:
                    stepped[w2 + dw2] = stepped.get(w2 + dw2, 0.0) + pr * pp
        alive = stepped

        if n in checks:
            surviving: dict[int, float] = {}
            for w2, pr in alive.items():
                p = _p_exceeds(n, w2)
                if p >= PASS_PROB_THRESHOLD:
                    p_pass += pr
                    expected_n += n * pr
                elif p <= FAIL_PROB_THRESHOLD:
                    p_fail += pr
                    expected_n += n * pr
                else:
                    surviving[w2] = pr
            alive = surviving

    # N_MAX: every surviving path absorbs (mirrors check_stop's hard cap).
    for w2, pr in alive.items():
        p = _p_exceeds(N_MAX, w2)
        if p >= PASS_PROB_THRESHOLD:
            p_pass += pr
        elif p <= FAIL_PROB_THRESHOLD:
            p_fail += pr
        else:
            p_unmeasured += pr
        expected_n += N_MAX * pr

    return SizingResult(
        discordance_rate=d,
        win_given_discordant=q,
        p_pass=p_pass,
        p_fail=p_fail,
        p_unmeasured=p_unmeasured,
        expected_n=expected_n,
    )


def minimum_detectable_q(
    discordance_rate: float,
    target_power: float = 0.80,
    step: float = 0.01,
) -> float | None:
    """Smallest q with P(PASS) >= target_power at the given discordance rate.

    :param discordance_rate: d in [0, 1].
    :param target_power: Required P(PASS) (default 0.80).
    :param step: Scan resolution over q (default 0.01).
    :returns: The minimum detectable q, or None if no q <= 1.0 reaches the
        target power — i.e. the contrast is structurally unmeasurable inside
        N_MAX at this discordance rate.
    """
    n_steps = round((1.0 - 0.5) / step)
    for i in range(n_steps + 1):
        q = min(0.5 + i * step, 1.0)
        if solve(discordance_rate, q).p_pass >= target_power:
            return q
    return None
