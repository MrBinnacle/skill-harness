"""Anytime-valid betting confidence sequence for bounded observations (#187).

Implements the two-sided hedged capital process with the predictable plug-in
betting fractions of Waudby-Smith & Ramdas (2024, JRSS-B; arXiv:2010.09686):

  W_t(mu) = theta * prod_i [1 + lambda_i+(mu)(X_i - mu)]
         + (1-theta) * prod_i [1 - lambda_i-(mu)(X_i - mu)]

with each lambda_i depending only on X_1..X_{i-1} (predictable), clipped so every
wealth factor stays strictly positive on X in [0, 1]. The (1-alpha) sequence is

  C_t = { mu in [0, 1] : W_t(mu) < 1/alpha }.

By Ville's inequality this is time-uniform, so the interval remains valid at a
data-dependent stopping time. Observations may be half-weights (ties = 0.5);
no Bernoulli likelihood is assumed.

Public constants
----------------
INTERVAL_METHOD_V1
    Stable method id written into SkillReport.interval_method.
DEFAULT_ALPHA
    Two-sided level (0.05 → "95%" sequence).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

INTERVAL_METHOD_V1: str = "predictable_plugin_betting_cs_v1"
DEFAULT_ALPHA: float = 0.05

# Hedged capital mix (paper default).
_THETA: float = 0.5
# Truncation scale c in (0, 1): lambda+ <= c/mu, lambda- <= c/(1-mu) keeps factors >= 1-c > 0.
_TRUNC_C: float = 0.5
# Running-variance floor (paper uses prior mass on 1/4).
_VAR_PRIOR: float = 0.25
_MEAN_PRIOR: float = 0.5
# Root-finding / grid
_N_GRID: int = 200
_BISECT_ITERS: int = 64
_MU_EPS: float = 1e-12
_LOG_WEALTH_CAP: float = 700.0  # avoid overflow in exp


@dataclass(frozen=True)
class ConfidenceSequenceResult:
    """Two-sided anytime-valid interval at the terminal sample size."""

    lo: float
    hi: float
    alpha: float
    method: str
    n: int


def betting_confidence_sequence(
    observations: Sequence[float],
    *,
    alpha: float = DEFAULT_ALPHA,
) -> ConfidenceSequenceResult:
    """Compute the terminal (1-alpha) predictable-plugin hedged confidence sequence.

    Parameters
    ----------
    observations:
        Sequence of bounded observations in [0, 1] (production uses {0, 0.5, 1}).
        Order is the evidence order; the sequence is valid at every prefix and
        therefore at any stopping time measurable w.r.t. the filtration.
    alpha:
        Two-sided error level (default 0.05).

    Returns
    -------
    ConfidenceSequenceResult with lo <= hi in [0, 1].

    Notes
    -----
    Empty input yields the vacuous interval [0, 1]. All-zero / all-one / all-tie
    sequences are handled by the same wealth process (no special-case shortcuts
    that would break the martingale property); endpoints may touch 0 or 1.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")

    xs = [float(x) for x in observations]
    for i, x in enumerate(xs):
        if not 0.0 <= x <= 1.0 or math.isnan(x):
            raise ValueError(f"observation[{i}]={x!r} not in [0, 1]")

    n = len(xs)
    if n == 0:
        return ConfidenceSequenceResult(lo=0.0, hi=1.0, alpha=alpha, method=INTERVAL_METHOD_V1, n=0)

    threshold = 1.0 / alpha
    log_threshold = math.log(threshold)

    def wealth_log(mu: float) -> float:
        return _hedged_log_wealth(xs, mu, alpha=alpha)

    # Coarse grid to bracket the in-set; refine endpoints by bisection.
    grid = [_MU_EPS + (1.0 - 2.0 * _MU_EPS) * i / _N_GRID for i in range(_N_GRID + 1)]
    inside = [wealth_log(m) < log_threshold for m in grid]

    if not any(inside):
        # Wealth exceeds 1/alpha everywhere on the grid — interval collapses to the
        # empirical mean (still a valid, possibly empty-interior, set; we return
        # a point interval at the sample mean so consumers always get lo<=hi).
        mean = sum(xs) / n
        mean = min(1.0, max(0.0, mean))
        return ConfidenceSequenceResult(
            lo=mean, hi=mean, alpha=alpha, method=INTERVAL_METHOD_V1, n=n
        )

    first = next(i for i, flag in enumerate(inside) if flag)
    last = len(inside) - 1 - next(i for i, flag in enumerate(reversed(inside)) if flag)

    # Lower endpoint: largest m <= grid[first] with wealth >= threshold, else 0.
    if first == 0:
        lo = 0.0
    else:
        lo = _bisect_crossing(
            xs,
            grid[first - 1],
            grid[first],
            alpha=alpha,
            log_threshold=log_threshold,
            find_lower=True,
        )

    # Upper endpoint: smallest m >= grid[last] with wealth >= threshold, else 1.
    if last == len(grid) - 1:
        hi = 1.0
    else:
        hi = _bisect_crossing(
            xs,
            grid[last],
            grid[last + 1],
            alpha=alpha,
            log_threshold=log_threshold,
            find_lower=False,
        )

    if lo > hi:
        # Numerical pathology — fall back to point at mean.
        mean = sum(xs) / n
        lo = hi = min(1.0, max(0.0, mean))

    return ConfidenceSequenceResult(
        lo=float(lo),
        hi=float(hi),
        alpha=alpha,
        method=INTERVAL_METHOD_V1,
        n=n,
    )


def miscalibrated_nonpredictable_cs(
    observations: Sequence[float],
    *,
    alpha: float = DEFAULT_ALPHA,
) -> ConfidenceSequenceResult:
    """Deliberately invalid CS: lambda depends on the *current* observation.

    Used only by the calibration poison-direction test to prove the harness can
    catch a non-predictable (lookahead) betting construction. Not for production.
    """
    xs = [float(x) for x in observations]
    n = len(xs)
    if n == 0:
        return ConfidenceSequenceResult(
            lo=0.0, hi=1.0, alpha=alpha, method="poison_nonpredictable_v1", n=0
        )
    log_threshold = math.log(1.0 / alpha)
    grid = [_MU_EPS + (1.0 - 2.0 * _MU_EPS) * i / _N_GRID for i in range(_N_GRID + 1)]

    def wealth_log(mu: float) -> float:
        return _poison_log_wealth(xs, mu, alpha=alpha)

    inside = [wealth_log(m) < log_threshold for m in grid]
    if not any(inside):
        mean = sum(xs) / n
        return ConfidenceSequenceResult(
            lo=mean, hi=mean, alpha=alpha, method="poison_nonpredictable_v1", n=n
        )
    first = next(i for i, flag in enumerate(inside) if flag)
    last = len(inside) - 1 - next(i for i, flag in enumerate(reversed(inside)) if flag)
    lo = 0.0 if first == 0 else grid[first]
    hi = 1.0 if last == len(grid) - 1 else grid[last]
    # Intentionally tight: shrink toward the sample mean (false precision).
    mean = sum(xs) / n
    width = max(hi - lo, 0.0) * 0.25
    lo2 = max(0.0, mean - width / 2.0)
    hi2 = min(1.0, mean + width / 2.0)
    return ConfidenceSequenceResult(
        lo=lo2, hi=hi2, alpha=alpha, method="poison_nonpredictable_v1", n=n
    )


# ---------------------------------------------------------------------------
# Wealth process
# ---------------------------------------------------------------------------


def _hedged_log_wealth(
    xs: list[float],
    mu: float,
    *,
    alpha: float,
) -> float:
    """Log of the hedged capital process at candidate mean ``mu``."""
    if mu <= 0.0:
        # m=0 is rejected as soon as any positive observation appears.
        if any(x > 0.0 for x in xs):
            return _LOG_WEALTH_CAP
        return 0.0  # W=1 (all zeros are consistent with mu=0)
    if mu >= 1.0:
        if any(x < 1.0 for x in xs):
            return _LOG_WEALTH_CAP
        return 0.0

    # Running mean / variance priors (predictable plug-in, WSR §4.3).
    mean_hat = _MEAN_PRIOR
    var_hat = _VAR_PRIOR
    log_pos = 0.0
    log_neg = 0.0

    for t, x in enumerate(xs, start=1):
        lam_p = _lambda_plus(mu, t, var_hat, alpha)
        lam_m = _lambda_minus(mu, t, var_hat, alpha)

        # Factors guaranteed >= 1 - _TRUNC_C > 0 by lambda clipping.
        fp = 1.0 + lam_p * (x - mu)
        fm = 1.0 - lam_m * (x - mu)
        if fp <= 0.0 or fm <= 0.0:
            # Should not happen with correct clipping; refuse rather than NaN.
            return _LOG_WEALTH_CAP
        log_pos += math.log(fp)
        log_neg += math.log(fm)

        # Predictable updates use the pre-observation mean for the residual.
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1)
        var_hat = var_hat + (resid * resid - var_hat) / (t + 1)
        var_hat = max(var_hat, 1e-6)

    # log(theta*e^{lp} + (1-theta)*e^{ln}) with stable log-sum-exp.
    a = math.log(_THETA) + log_pos
    b = math.log(1.0 - _THETA) + log_neg
    m = max(a, b)
    if m >= _LOG_WEALTH_CAP:
        return _LOG_WEALTH_CAP
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def _poison_log_wealth(xs: list[float], mu: float, *, alpha: float) -> float:
    """Non-predictable wealth: lambda uses the current residual (lookahead cheat)."""
    if mu <= 0.0 or mu >= 1.0:
        return _hedged_log_wealth(xs, mu, alpha=alpha)
    mean_hat = _MEAN_PRIOR
    var_hat = _VAR_PRIOR
    log_pos = 0.0
    log_neg = 0.0
    for t, x in enumerate(xs, start=1):
        # CHEAT: inflate lambda using the sign of (x - mu) before betting.
        base_p = _lambda_plus(mu, t, var_hat, alpha)
        base_m = _lambda_minus(mu, t, var_hat, alpha)
        if x > mu:
            lam_p = min(base_p * 3.0, _TRUNC_C / mu)
            lam_m = base_m * 0.1
        elif x < mu:
            lam_p = base_p * 0.1
            lam_m = min(base_m * 3.0, _TRUNC_C / (1.0 - mu))
        else:
            lam_p, lam_m = base_p, base_m
        fp = 1.0 + lam_p * (x - mu)
        fm = 1.0 - lam_m * (x - mu)
        fp = max(fp, 1e-15)
        fm = max(fm, 1e-15)
        log_pos += math.log(fp)
        log_neg += math.log(fm)
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1)
        var_hat = var_hat + (resid * resid - var_hat) / (t + 1)
        var_hat = max(var_hat, 1e-6)
    a = math.log(_THETA) + log_pos
    b = math.log(1.0 - _THETA) + log_neg
    m = max(a, b)
    if m >= _LOG_WEALTH_CAP:
        return _LOG_WEALTH_CAP
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def _lambda_plus(mu: float, t: int, var_hat: float, alpha: float) -> float:
    """Predictable plug-in lambda+_t(mu) in (0, c/mu]."""
    return _lambda_raw(t, var_hat, alpha, cap=_TRUNC_C / mu)


def _lambda_minus(mu: float, t: int, var_hat: float, alpha: float) -> float:
    """Predictable plug-in lambda-_t(mu) in (0, c/(1-mu)]."""
    return _lambda_raw(t, var_hat, alpha, cap=_TRUNC_C / (1.0 - mu))


def _lambda_raw(t: int, var_hat: float, alpha: float, *, cap: float) -> float:
    # lambda_t = sqrt(2 log(2/alpha) / (sigma^2_{t-1} * t * log(1+t))) and cap
    # (WSR predictable plug-in; log(2/alpha) for two-sided hedged mix).
    denom = max(var_hat, 1e-6) * float(t) * math.log(1.0 + float(t))
    target = math.sqrt(2.0 * math.log(2.0 / alpha) / denom)
    if cap <= 0.0:
        return 0.0
    return min(cap, target)


def _bisect_crossing(
    xs: list[float],
    left: float,
    right: float,
    *,
    alpha: float,
    log_threshold: float,
    find_lower: bool,
) -> float:
    """Bisection for the wealth = 1/alpha crossing between left and right.

    find_lower=True: return the smallest m in [left,right] with wealth < thresh
    (lower CS endpoint). find_lower=False: largest m with wealth < thresh.
    """
    lo_m, hi_m = left, right
    for _ in range(_BISECT_ITERS):
        mid = 0.5 * (lo_m + hi_m)
        inside = _hedged_log_wealth(xs, mid, alpha=alpha) < log_threshold
        if find_lower:
            if inside:
                hi_m = mid
            else:
                lo_m = mid
        elif inside:
            lo_m = mid
        else:
            hi_m = mid
    return hi_m if find_lower else lo_m
