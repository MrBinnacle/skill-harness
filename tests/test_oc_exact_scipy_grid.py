"""The OC primitives, cross-checked against an independent implementation.

Falsification-plan item 4. `beta_cdf` and `beta_binomial_pmf` are float64 closed forms.
Gate 1 and Gate 2 compare posterior mass against a locked gamma, so an error large enough to
move mass across a decision boundary changes QUALIFIES to REJECTED, or the attained error
rates, or whether a frontier is ratifiable.

The existing tests reach these functions almost entirely through the gates, at moderate
parameters. The single direct check of `beta_cdf` is one hand literal at `abs=1e-9`. A hand
literal cannot cover a lattice, and the grid edge is exactly where a closed form fails.

What this compares
------------------
SciPy is an independent implementation of the same mathematics, not ground truth. Where the
two disagree the question is which is more accurate, and for these particular forms the local
implementation has a real claim:

- `beta_cdf` sums `comb(n, j) * x**j * (1-x)**(n-j)` over `j`. Every term is positive, so
  there is no catastrophic cancellation; the error is accumulated rounding, of order
  `n * eps`. Its exposure is underflow when `x` is extreme and `n` is large.
- `beta_binomial_pmf` is a ratio of three exact integer binomials. The numerator and
  denominator are exact until a single float division, so it carries about one rounding.

SciPy's `betainc` is a continued-fraction evaluation accurate to a few `eps`. Agreement to
the bound below is therefore evidence that neither has a defect, and a disagreement is worth
investigating in whichever direction it points.

The bound, registered before it was measured
--------------------------------------------
`MAX_ABS_ERROR = 1e-12`.

Justified from both ends rather than fitted. From below: double precision `eps` is about
2.2e-16, and `n` reaches 40 here, so an honest implementation should land within roughly
1e-14, and 1e-12 leaves two orders of headroom for SciPy's own error. From above: the locked
decision thresholds this feeds are separated by O(1e-2). An error that could move a decision
is at least ten orders of magnitude larger than this bound, so the bound is tight enough that
a real defect cannot hide under it, and loose enough that ordinary float arithmetic does not
trip it.

The lattice
-----------
The posterior family the instrument actually evaluates is `Beta(1 + w, 1 + n - w)` for
`w` in `0..n`, and it is swept for every `n` from `GRID_N_MIN` to `GRID_N_MAX`. A denser
sweep over arbitrary integer shapes covers the corners of the grid separately.

Note on where the grid constants live
-------------------------------------
`GRID_N_MIN` and `GRID_N_MAX` are defined in `oc/conventions.py`, not in `oc/exact.py`, and
`scripts/drift_check.py` guards both values and their documentation quotes as DC-7. They are
imported here from `conventions` for that reason.

The falsification plan does not say otherwise. Its item 4 names the three primitives and
closes that list with `(oc/exact.py)`, which is where all three live; it mentions
`GRID_N_MAX=40` separately and attributes it to no file. An earlier draft of the ticket
behind this module claimed the plan misfiled the constant. That claim was wrong and is
withdrawn on the ticket.
"""

from __future__ import annotations

from typing import Final

import pytest
from scipy.special import betainc  # type: ignore[import-untyped]

from skill_harness.oc.conventions import GRID_N_MAX, GRID_N_MIN
from skill_harness.oc.exact import beta_binomial_pmf, beta_cdf

MAX_ABS_ERROR: Final[float] = 1e-12

# Evaluation points: the neighbourhood of the locked gammas, the middle, and both extremes
# where a float64 closed form is most exposed to underflow.
EVALUATION_POINTS: Final[tuple[float, ...]] = (
    1e-12,
    1e-6,
    0.05,
    0.5,
    0.60,
    0.90,
    0.95,
    0.99,
    1.0 - 1e-6,
    1.0 - 1e-12,
)

# A sum of probabilities over a complete support should reach one to within the accumulated
# rounding of that many additions, which is far tighter than the decision scale.
PMF_SUM_TOLERANCE: Final[float] = 1e-12


def _posterior_shapes() -> list[tuple[int, int, int]]:
    """Return (n, a, b) for the Beta(1 + w, 1 + n - w) family across the whole grid."""
    return [(n, 1 + w, 1 + n - w) for n in range(GRID_N_MIN, GRID_N_MAX + 1) for w in range(n + 1)]


def test_the_grid_constants_are_the_ones_the_instrument_locks() -> None:
    """Pin the lattice this module claims to cover.

    Without this, a change to the grid bounds would silently shrink the swept region while
    every comparison below still passed on whatever remained.
    """
    assert GRID_N_MIN == 6
    assert GRID_N_MAX == 40
    assert GRID_N_MIN < GRID_N_MAX


def test_the_sweep_covers_the_whole_declared_lattice() -> None:
    """The sweep must be non-trivial, or the comparisons below prove nothing.

    A generator that yielded nothing would make every max-error assertion vacuously true,
    which is the failure the success-test-accepts-any-output card describes.
    """
    shapes = _posterior_shapes()
    expected = sum(n + 1 for n in range(GRID_N_MIN, GRID_N_MAX + 1))
    assert len(shapes) == expected
    assert {n for n, _, _ in shapes} == set(range(GRID_N_MIN, GRID_N_MAX + 1))
    assert len(EVALUATION_POINTS) >= 8


def test_beta_cdf_matches_scipy_across_the_posterior_family() -> None:
    """`beta_cdf` is the regularized incomplete beta; SciPy computes it independently."""
    worst_error = 0.0
    worst_case: tuple[int, int, float] | None = None

    for _, a, b in _posterior_shapes():
        for x in EVALUATION_POINTS:
            ours = beta_cdf(x, a, b)
            theirs = float(betainc(a, b, x))
            error = abs(ours - theirs)
            if error > worst_error:
                worst_error = error
                worst_case = (a, b, x)

    assert worst_error <= MAX_ABS_ERROR, (
        f"beta_cdf disagrees with scipy.special.betainc by {worst_error:.3e}, above the "
        f"registered bound of {MAX_ABS_ERROR:.0e}. Worst case: a={worst_case[0]}, "
        f"b={worst_case[1]}, x={worst_case[2]!r} "
        if worst_case
        else f"beta_cdf disagrees by {worst_error:.3e}"
    )


def test_beta_cdf_matches_scipy_on_arbitrary_integer_shapes_at_the_grid_edge() -> None:
    """Cover shapes off the posterior family, at the largest grid size.

    The posterior family always satisfies `a + b = n + 2`. A defect that depended on the two
    shapes being very unequal, rather than on their sum, would not show up there.
    """
    n = GRID_N_MAX
    worst_error = 0.0
    worst_case: tuple[int, int, float] | None = None

    for a in range(1, n + 2):
        for b in range(1, n + 2):
            for x in EVALUATION_POINTS:
                error = abs(beta_cdf(x, a, b) - float(betainc(a, b, x)))
                if error > worst_error:
                    worst_error = error
                    worst_case = (a, b, x)

    assert worst_error <= MAX_ABS_ERROR, (
        f"beta_cdf disagrees with scipy by {worst_error:.3e} at the grid edge, above the "
        f"registered bound of {MAX_ABS_ERROR:.0e}. Worst case: {worst_case}"
    )


def test_beta_cdf_is_monotone_and_bounded_on_the_unit_interval() -> None:
    """A cumulative distribution never decreases and never leaves [0, 1].

    This is independent of SciPy. If both implementations shared a wrong oracle, this
    property would still catch a form that breaks down at the extremes.
    """
    violations: list[str] = []
    for _, a, b in _posterior_shapes():
        previous = -1.0
        for x in EVALUATION_POINTS:
            value = beta_cdf(x, a, b)
            if not 0.0 <= value <= 1.0:
                violations.append(f"beta_cdf({x!r}, {a}, {b}) = {value!r} is outside [0, 1]")
            if value < previous - MAX_ABS_ERROR:
                violations.append(
                    f"beta_cdf decreased at x={x!r} for a={a}, b={b}: {previous!r} then {value!r}"
                )
            previous = value

    assert not violations, "beta_cdf violates the properties of a CDF:\n  " + "\n  ".join(
        violations[:20]
    )


@pytest.mark.parametrize("m", [GRID_N_MIN, 20, GRID_N_MAX])
def test_beta_binomial_masses_sum_to_one(m: int) -> None:
    """The pmf over its complete support must sum to one, under stress at n = 40."""
    worst_deviation = 0.0
    worst_case: tuple[int, int] | None = None

    for a in range(1, m + 2):
        for b in range(1, m + 2):
            total = sum(beta_binomial_pmf(k, m, a, b) for k in range(m + 1))
            deviation = abs(total - 1.0)
            if deviation > worst_deviation:
                worst_deviation = deviation
                worst_case = (a, b)

    assert worst_deviation <= PMF_SUM_TOLERANCE, (
        f"beta-binomial masses sum to 1 only within {worst_deviation:.3e} at m={m}, above "
        f"the registered tolerance of {PMF_SUM_TOLERANCE:.0e}. Worst case: a, b = "
        f"{worst_case}. A pmf that does not sum to one is not a distribution, and any mass "
        "compared against a locked gamma inherits the error."
    )


def test_beta_binomial_pmf_is_never_negative_and_never_exceeds_one() -> None:
    """A probability mass outside [0, 1] is a defect regardless of any reference."""
    m = GRID_N_MAX
    violations: list[str] = []
    for a in (1, 2, m, m + 1):
        for b in (1, 2, m, m + 1):
            for k in range(m + 1):
                value = beta_binomial_pmf(k, m, a, b)
                if not 0.0 <= value <= 1.0:
                    violations.append(f"beta_binomial_pmf({k}, {m}, {a}, {b}) = {value!r}")

    assert not violations, "beta-binomial masses outside [0, 1]:\n  " + "\n  ".join(violations[:20])
