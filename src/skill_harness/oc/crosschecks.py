"""Frequentist cross-checks for Gate-2 reports (#37 item 4).

Three pure functions, all stdlib (the normal quantile comes from
``statistics.NormalDist``):

- mid-p McNemar test - the recommended small-sample paired test; the exact
  conditional test is banned by name (Fagerland, Lydersen & Laake 2013,
  BMC Med Res Methodol 13:91: conditional mean attained type-I 0.0201 vs
  mid-p 0.0349 with zero violations across all 9,595 scenarios; "We do not
  recommend use of the McNemar exact conditional test ... in any situation").
- Newcombe 1998 paired-difference interval (Stat Med 17:2635, method 10:
  square-and-add Wilson intervals with a phi correction for pairing) - the
  Wald interval is banned (#37: it can overshoot [-1, 1] at small n).
- Tango 1998 score interval (Stat Med 17:891), computed by deterministic
  bisection inversion of the score statistic (the PropCIs ``scoreci.mp``
  canonical form; Yang, Sun & Hardin 2013 give a closed-form alternative -
  inversion-vs-closed-form is an implementation detail below this API).

Reports print delta with BOTH intervals plus a concordance flag (#37); the
Altham-1971 reference-prior bridge is the report template's citation, not a
computation here.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb, sqrt
from statistics import NormalDist

# ---------------------------------------------------------------------------
# mid-p McNemar
# ---------------------------------------------------------------------------


def mcnemar_midp(x_f: int, x_n: int) -> float:
    """Two-sided mid-p McNemar test on the discordant counts.

    Conditional on k = x_f + x_n discordant pairs, X ~ Binomial(k, 1/2)
    under the null; with m = max(x_f, x_n) the mid-p is
    2 * P(X > m) + P(X = m), capped at 1 (the FLL 2013 form: the exact
    conditional two-sided p minus the observed point probability). Exact
    Fraction arithmetic internally. Zero-discordant returns 1.0 - no
    directional evidence either way.

    :param x_f: Full-only-win pairs observed.
    :param x_n: Null-only-win pairs observed.
    :returns: The two-sided mid-p value in [0, 1].
    :raises ValueError: If a count is negative.
    """
    if x_f < 0 or x_n < 0:
        raise ValueError(f"counts must be >= 0; got x_f={x_f}, x_n={x_n}")
    k = x_f + x_n
    if k == 0:
        return 1.0
    m = max(x_f, x_n)
    tail_gt = sum(comb(k, j) for j in range(m + 1, k + 1))
    point = comb(k, m)
    return float(min(Fraction(2 * tail_gt + point, 2**k), Fraction(1)))


# ---------------------------------------------------------------------------
# Newcombe 1998 paired-difference interval (method 10)
# ---------------------------------------------------------------------------


def _z_quantile(level: float) -> float:
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must lie in (0, 1); got {level}")
    return NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)


def _wilson(x: int, n: int, z: float) -> tuple[float, float]:
    center = (x + z * z / 2.0) / (n + z * z)
    half = z * sqrt(x * (n - x) / n + z * z / 4.0) / (n + z * z)
    return center - half, center + half


def newcombe_interval(
    both_pass: int, x_f: int, x_n: int, both_fail: int, *, level: float = 0.95
) -> tuple[float, float]:
    """Newcombe (1998) interval for the paired difference delta = p1 - p2.

    Square-and-add of the two marginal Wilson intervals with the phi
    correction for pairing (method 10; transcribed from the published
    formula as implemented in biostatUZH::confIntPairedProportion, and
    anchored to the Altman 2000 worked example in the seam tests). The phi
    numerator carries Newcombe's continuity adjustment (B - n/2 when
    B > n/2, B when B < 0, else 0); a zero denominator sets phi = 0 per
    Newcombe's stated convention. Needs the FULL 2x2 table - the tie split
    enters the pairing correction even though delta itself does not use it.

    :param both_pass: Pairs where both arms pass.
    :param x_f: Full-only-win pairs.
    :param x_n: Null-only-win pairs.
    :param both_fail: Pairs where both arms fail.
    :param level: Two-sided confidence level in (0, 1); default 0.95.
    :returns: (lower, upper) for delta = (x_f - x_n) / n, inside [-1, 1].
    :raises ValueError: If any cell is negative, the table is empty, or the
        level is out of range.
    """
    cells = (both_pass, x_f, x_n, both_fail)
    if any(v < 0 for v in cells):
        raise ValueError(f"all four cells must be >= 0; got {cells}")
    n = sum(cells)
    if n == 0:
        raise ValueError("the 2x2 table must contain at least one pair")
    z = _z_quantile(level)
    r, s, t, u = cells
    p1, p2 = (r + s) / n, (r + t) / n
    delta = p1 - p2
    l1, u1 = _wilson(r + s, n, z)
    l2, u2 = _wilson(r + t, n, z)
    denom_sq = (r + s) * (t + u) * (r + t) * (s + u)
    if denom_sq > 0:
        b = r * u - s * t
        c = b - n / 2.0 if b > n / 2.0 else (float(b) if b < 0 else 0.0)
        phi = c / sqrt(denom_sq)
    else:
        phi = 0.0
    lower = delta - sqrt((p1 - l1) ** 2 - 2.0 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    upper = delta + sqrt((p2 - l2) ** 2 - 2.0 * phi * (p2 - l2) * (u1 - p1) + (u1 - p1) ** 2)
    return lower, upper


# ---------------------------------------------------------------------------
# Tango 1998 score interval
# ---------------------------------------------------------------------------


def _tango_score(delta0: float, x_f: int, x_n: int, n: int) -> float:
    """Score statistic T(delta0) for delta = (x_f - x_n) / n.

    Constrained MLE of the null-only cell probability from the quadratic
    (Tango 1998; the PropCIs scoreci.mp parametrization with their (b, c)
    mapped to (x_n, x_f))."""
    p_a = 2.0 * n
    p_b = -x_n - x_f + (2.0 * n - x_f + x_n) * delta0
    p_c = -x_n * delta0 * (1.0 - delta0)
    disc = p_b * p_b - 4.0 * p_a * p_c
    q21 = (sqrt(disc if disc > 0.0 else 0.0) - p_b) / (2.0 * p_a)
    den = n * (2.0 * q21 + delta0 * (1.0 - delta0))
    num = x_f - x_n - n * delta0
    if den <= 0.0:
        return float("-inf") if num < 0.0 else float("inf")
    return num / sqrt(den)


def tango_interval(x_f: int, x_n: int, n: int, *, level: float = 0.95) -> tuple[float, float]:
    """Tango (1998) score interval for the paired difference delta.

    Deterministic bisection inversion of the score test: the upper limit is
    the delta0 where T(delta0) crosses -z, the lower where it crosses +z
    (T is decreasing in delta0 and T(delta_hat) = 0). Edge rules per the
    canonical implementation: x_f = n pins the upper limit at exactly 1,
    x_n = n pins the lower at exactly -1. Anchored in the seam tests to the
    published floppy-eyelid literal (PMC10763857 Table 2).

    :param x_f: Full-only-win pairs.
    :param x_n: Null-only-win pairs.
    :param n: Total pairs, >= 1, with x_f + x_n <= n.
    :param level: Two-sided confidence level in (0, 1); default 0.95.
    :returns: (lower, upper) for delta = (x_f - x_n) / n, inside [-1, 1].
    :raises ValueError: If the counts are inconsistent or the level is out
        of range.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1; got {n}")
    if x_f < 0 or x_n < 0 or x_f + x_n > n:
        raise ValueError(f"need x_f, x_n >= 0 with x_f + x_n <= n={n}; got x_f={x_f}, x_n={x_n}")
    z = _z_quantile(level)
    delta_hat = (x_f - x_n) / n

    def _bisect(lo: float, hi: float, crossing: float) -> float:
        # Invariant: T(lo) > crossing > T(hi); endpoints never evaluated.
        for _ in range(100):
            mid = (lo + hi) / 2.0
            if _tango_score(mid, x_f, x_n, n) > crossing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    upper = 1.0 if x_f == n else _bisect(delta_hat, 1.0, -z)
    lower = -1.0 if x_n == n else _bisect(-1.0, delta_hat, z)
    return lower, upper
