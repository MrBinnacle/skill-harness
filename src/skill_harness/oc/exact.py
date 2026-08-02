"""Exact distribution pieces for the OC enumeration (stdlib-only, no I/O).

Everything here is closed-form finite arithmetic — no simulation, no seeds,
no scipy: the integer-parameter regularized incomplete beta reduces to a
binomial sum, and the integer-parameter beta-binomial reduces to the
negative-hypergeometric ratio. Exactness is the point (#37: reports print
ATTAINED values off the exact lattice, never nominal levels).
"""

from __future__ import annotations

from math import comb

# ---------------------------------------------------------------------------
# Regularized incomplete beta, integer parameters
# ---------------------------------------------------------------------------


def beta_cdf(x: float, a: int, b: int) -> float:
    """Exact I_x(a, b) for positive integer a, b via the binomial identity.

    I_x(a, b) = sum_{j=a}^{a+b-1} C(a+b-1, j) x^j (1-x)^(a+b-1-j)

    :param x: Evaluation point; clamped to [0, 1] (0 below, 1 above).
    :param a: First shape parameter, integer >= 1.
    :param b: Second shape parameter, integer >= 1.
    :returns: The regularized incomplete beta I_x(a, b).
    :raises ValueError: If a or b is not a positive integer.
    """
    if a < 1 or b < 1:
        raise ValueError(f"beta_cdf requires integer shapes a, b >= 1; got a={a}, b={b}")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    n = a + b - 1
    return sum(comb(n, j) * x**j * (1.0 - x) ** (n - j) for j in range(a, n + 1))


# ---------------------------------------------------------------------------
# Beta-binomial pmf, integer parameters
# ---------------------------------------------------------------------------


def beta_binomial_pmf(k: int, m: int, a: int, b: int) -> float:
    """Exact BetaBinomial(k; m, a, b) for integer a, b >= 1.

    Uses the negative-hypergeometric form (one float division, integer
    numerator/denominator):

    P(k) = C(a+k-1, k) C(b+m-k-1, m-k) / C(a+b+m-1, m)

    :param k: Number of successes, 0 <= k <= m.
    :param m: Number of trials, integer >= 0.
    :param a: First shape parameter of the mixing Beta, integer >= 1.
    :param b: Second shape parameter of the mixing Beta, integer >= 1.
    :returns: The exact pmf value.
    :raises ValueError: If parameters are out of range.
    """
    if a < 1 or b < 1:
        raise ValueError(f"beta_binomial_pmf requires a, b >= 1; got a={a}, b={b}")
    if m < 0 or not 0 <= k <= m:
        raise ValueError(f"beta_binomial_pmf requires 0 <= k <= m; got k={k}, m={m}")
    return comb(a + k - 1, k) * comb(b + m - k - 1, m - k) / comb(a + b + m - 1, m)
