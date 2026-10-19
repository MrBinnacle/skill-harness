"""Exact distribution pieces for the OC enumeration (stdlib-only, no I/O).

Everything here is closed-form finite arithmetic — no simulation, no seeds,
no scipy: the integer-parameter regularized incomplete beta reduces to a
binomial sum, the integer-parameter beta-binomial reduces to the
negative-hypergeometric ratio, and the Dirichlet net-lift tail reduces to an
exact rational polygon integral (the integer-parameter Dirichlet density is a
polynomial, and the tail region is a half-plane cut of the simplex).
Exactness is the point (#37: reports print ATTAINED values off the exact
lattice, never nominal levels).
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from functools import cache
from math import comb, factorial

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


# ---------------------------------------------------------------------------
# Dirichlet net-lift tail, integer parameters
# ---------------------------------------------------------------------------


@cache
def _delta_tail_exact(c: Fraction, a_f: int, a_n: int, a_t: int) -> Fraction:
    """Exact P(p_f - p_n >= c) for (p_f, p_n, p_t) ~ Dirichlet(a_f, a_n, a_t).

    Rational polygon integration, OUTER variable p_n: the region
    {p_f - p_n >= c} cut from the simplex is, for c in [0, 1), the set
    p_n in [0, (1-c)/2], p_f in [p_n + c, 1 - p_n]. The density is a
    polynomial with integer exponents, so every piece integrates to an exact
    Fraction (binomial expansions; no quadrature, no cancellation risk).

    The independent reference implementation integrates with the OPPOSITE
    variable order (outer p_f) - the test literals are cross-derivation.
    """
    if c >= 1:
        return Fraction(0)
    if c <= -1:
        return Fraction(1)
    if c < 0:
        # {p_f - p_n >= c} is the complement of {p_n - p_f > -c}; the
        # boundary line has zero probability, so complement the mirrored
        # positive tail with the discordant roles relabelled.
        return 1 - _delta_tail_exact(-c, a_n, a_f, a_t)
    x = (1 - c) / 2
    top = a_f + a_n + a_t
    xpow = [Fraction(1)]
    cpow = [Fraction(1)]
    for _ in range(top):
        xpow.append(xpow[-1] * x)
        cpow.append(cpow[-1] * c)
    # Inner integral over p_f from L = p_n + c to S = 1 - p_n of
    # p_f^(a_f-1) (S - p_f)^(a_t-1), expanded binomially, splits into a
    # j-independent S^(a_f+a_t-1) piece (constant K below) minus the
    # L-dependent pieces; the outer p_n integral of each is polynomial.
    k_const = sum(Fraction(comb(a_t - 1, j) * (-1) ** j, a_f + j) for j in range(a_t))
    i1 = sum(
        Fraction(comb(a_f + a_t - 1, r) * (-1) ** r, a_n + r) * xpow[a_n + r]
        for r in range(a_f + a_t)
    )
    total = k_const * i1
    for j in range(a_t):
        c_j = Fraction(comb(a_t - 1, j) * (-1) ** j, a_f + j)
        e_s, e_l = a_t - 1 - j, a_f + j
        i2 = Fraction(0)
        for r in range(e_s + 1):
            base = comb(e_s, r) * (-1) ** r
            for s in range(e_l + 1):
                i2 += (
                    Fraction(base * comb(e_l, s))
                    * cpow[e_l - s]
                    * xpow[a_n + r + s]
                    / (a_n + r + s)
                )
        total -= c_j * i2
    norm = Fraction(
        factorial(top - 1),
        factorial(a_f - 1) * factorial(a_n - 1) * factorial(a_t - 1),
    )
    return norm * total


def dirichlet_delta_tail(c: float, a_f: int, a_n: int, a_t: int) -> float:
    """Exact P(p_f - p_n >= c) under Dirichlet(a_f, a_n, a_t), integer params.

    The Gate-2 posterior primitive (#37 item 3): with observed discordant
    counts the reference-prior posterior on (p_f, p_n, pooled ties) is
    Dirichlet with integer parameters, and the net lift delta = p_f - p_n is
    the reported effect scale. At c = 0 this reduces to the beta identity
    P(q > 1/2) = 1 - I_.5(a_f, a_n) (pinned by the seam tests).

    :param c: Net-lift margin in [-1, 1]; values outside clamp to 0/1 tails.
        Converted to an exact Fraction via its shortest decimal repr, so a
        registered decimal knob like 0.15 means exactly 3/20.
    :param a_f: Full-only-win cell parameter, integer >= 1.
    :param a_n: Null-only-win cell parameter, integer >= 1.
    :param a_t: Pooled tie-cells parameter, integer >= 1.
    :returns: The exact tail probability as a float.
    :raises ValueError: If any parameter is not a positive integer.
    """
    if a_f < 1 or a_n < 1 or a_t < 1:
        raise ValueError(
            f"dirichlet_delta_tail requires integer parameters >= 1; "
            f"got a_f={a_f}, a_n={a_n}, a_t={a_t}"
        )
    return float(_delta_tail_exact(Fraction(Decimal(repr(c))), a_f, a_n, a_t))
