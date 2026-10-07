"""Unit + differential tests for the predictable-plugin betting CS (#187).

Reference vectors
-----------------
Committed endpoints below were derived offline by an *independent* reimplementation
of Waudby-Smith & Ramdas (2024 JRSS-B / arXiv:2010.09686) §4.1 hedged capital +
§4.3 predictable plug-in λ, using linear (rescaled) wealth products and a denser
grid than production. No third-party CS library is depended on (none approved for
this ticket; confseq is not installable in CI). Production
``betting_confidence_sequence`` must match these vectors within ``TOL``.

The independent reference lives in this file as ``_ref_hedged_prpl_cs`` and is
re-run on every test invocation so a silent drift of the committed numbers
against the paper equations fails closed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest
from numpy.testing import assert_allclose

from skill_harness.aggregation.confidence_sequence import (
    INTERVAL_METHOD_V1,
    betting_confidence_sequence,
    miscalibrated_nonpredictable_cs,
)

TOL = 5e-4  # root-finding / grid density slack between ref and production

# ---------------------------------------------------------------------------
# Independent reference (paper equations; linear wealth, denser grid)
# ---------------------------------------------------------------------------

_THETA = 0.5
_TRUNC_C = 0.5
_ALPHA = 0.05


def _ref_lambda(t: int, var_hat: float, cap: float) -> float:
    denom = max(var_hat, 1e-6) * float(t) * math.log(1.0 + float(t))
    target = math.sqrt(2.0 * math.log(2.0 / _ALPHA) / denom)
    return min(cap, target) if cap > 0.0 else 0.0


def _ref_wealth(xs: list[float], mu: float) -> float:
    if mu <= 0.0:
        return 1e300 if any(x > 0.0 for x in xs) else 1.0
    if mu >= 1.0:
        return 1e300 if any(x < 1.0 for x in xs) else 1.0
    mean_hat = 0.5
    var_hat = 0.25
    pos = 1.0
    neg = 1.0
    for t, x in enumerate(xs, start=1):
        lp = _ref_lambda(t, var_hat, _TRUNC_C / mu)
        lm = _ref_lambda(t, var_hat, _TRUNC_C / (1.0 - mu))
        pos *= 1.0 + lp * (x - mu)
        neg *= 1.0 - lm * (x - mu)
        # Rescale to avoid overflow while preserving θ·pos+(1-θ)·neg ratio later
        # via final combination only — keep both on comparable scale.
        scale = max(pos, neg, 1e-300)
        if scale > 1e50:
            pos /= scale
            neg /= scale
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1)
        var_hat = var_hat + (resid * resid - var_hat) / (t + 1)
        var_hat = max(var_hat, 1e-6)
    return _THETA * pos + (1.0 - _THETA) * neg


def _ref_hedged_prpl_cs(xs: Sequence[float]) -> tuple[float, float]:
    data = [float(x) for x in xs]
    if not data:
        return 0.0, 1.0
    thr = 1.0 / _ALPHA
    n_grid = 2000
    grid = [1e-12 + (1.0 - 2e-12) * i / n_grid for i in range(n_grid + 1)]
    inside = [_ref_wealth(data, m) < thr for m in grid]
    if not any(inside):
        mean = sum(data) / len(data)
        return mean, mean
    first = next(i for i, f in enumerate(inside) if f)
    last = len(inside) - 1 - next(i for i, f in enumerate(reversed(inside)) if f)
    lo = 0.0 if first == 0 else grid[first]
    hi = 1.0 if last == n_grid else grid[last]
    # Bisection polish
    if first > 0:
        a, b = grid[first - 1], grid[first]
        for _ in range(80):
            mid = 0.5 * (a + b)
            if _ref_wealth(data, mid) < thr:
                b = mid
            else:
                a = mid
        lo = b
    if last < n_grid:
        a, b = grid[last], grid[last + 1]
        for _ in range(80):
            mid = 0.5 * (a + b)
            if _ref_wealth(data, mid) < thr:
                a = mid
            else:
                b = mid
        hi = a
    return lo, hi


# Committed reference vectors (name, observations, expected lo, expected hi).
# Derived offline via ``_ref_hedged_prpl_cs`` (see module docstring).
_REF_VECTORS: tuple[tuple[str, list[float], float, float], ...] = (
    ("empty", [], 0.0, 1.0),
    ("single_half", [0.5], 0.0, 1.0),
    ("two_wins", [1.0, 1.0], 0.0, 1.0),
    ("all_zero_20", [0.0] * 20, 0.0, 0.2883064793),
    ("all_one_20", [1.0] * 20, 0.7116935207, 1.0),
    ("all_tie_20", [0.5] * 20, 0.3559178624, 0.6440821376),
    ("alternating_16", [1.0, 0.0] * 8, 0.1788349419, 0.8453084802),
    (
        "mostly_win_12",
        [1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 0.0, 1.0],
        0.4014481583,
        1.0,
    ),
    (
        "wsr_paperish_30",
        [
            0.0,
            1.0,
            1.0,
            0.0,
            1.0,
            0.0,
            0.0,
            1.0,
            1.0,
            1.0,
            0.0,
            1.0,
            0.5,
            1.0,
            0.0,
            1.0,
            1.0,
            0.0,
            1.0,
            1.0,
            0.0,
            0.5,
            1.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            1.0,
            1.0,
        ],
        0.3510841824,
        0.8416050402,
    ),
)


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Block all network I/O for every test in this module."""


def test_ref_vectors_match_independent_reimplementation() -> None:
    """Committed fixtures still equal the independent paper reimplementation."""
    for name, xs, lo, hi in _REF_VECTORS:
        r_lo, r_hi = _ref_hedged_prpl_cs(xs)
        assert_allclose(
            [r_lo, r_hi],
            [lo, hi],
            atol=TOL,
            rtol=0.0,
            err_msg=f"committed vector drifted from independent ref: {name}",
        )


@pytest.mark.parametrize(("name", "xs", "lo", "hi"), _REF_VECTORS, ids=[v[0] for v in _REF_VECTORS])
def test_production_matches_committed_reference_vectors(
    name: str, xs: list[float], lo: float, hi: float
) -> None:
    result = betting_confidence_sequence(xs)
    assert result.method == INTERVAL_METHOD_V1
    assert result.n == len(xs)
    assert_allclose(
        [result.lo, result.hi],
        [lo, hi],
        atol=TOL,
        rtol=0.0,
        err_msg=f"production CS mismatch on {name}",
    )


def test_production_matches_independent_ref_on_random_draws() -> None:
    """Cross-check production vs independent ref on seeded random sequences."""
    import numpy as np

    rng = np.random.default_rng(187_2026_08_09)
    for n in (5, 12, 25, 40):
        for _ in range(20):
            # Observations in {0, 0.5, 1}
            u = rng.random(n)
            xs = [0.0 if v < 0.3 else (0.5 if v < 0.45 else 1.0) for v in u]
            prod = betting_confidence_sequence(xs)
            r_lo, r_hi = _ref_hedged_prpl_cs(xs)
            assert_allclose(
                [prod.lo, prod.hi],
                [r_lo, r_hi],
                atol=TOL,
                rtol=0.0,
            )


def test_interval_nested_in_unit_interval() -> None:
    xs = [0.0, 1.0, 0.5, 1.0, 0.0, 1.0, 1.0, 0.5]
    r = betting_confidence_sequence(xs)
    assert 0.0 <= r.lo <= r.hi <= 1.0


def test_rejects_out_of_range_observation() -> None:
    with pytest.raises(ValueError, match="not in"):
        betting_confidence_sequence([0.0, 1.5])


def test_deterministic() -> None:
    xs = [1.0, 0.0, 1.0, 0.5, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    a = betting_confidence_sequence(xs)
    b = betting_confidence_sequence(xs)
    assert (a.lo, a.hi) == (b.lo, b.hi)


def test_poison_construction_differs_from_valid() -> None:
    """Sanity: lookahead poison CS is not identical to the valid sequence."""
    xs = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.5, 1.0, 1.0, 0.0, 1.0, 1.0]
    good = betting_confidence_sequence(xs)
    bad = miscalibrated_nonpredictable_cs(xs)
    # Poison is intentionally tighter (false precision).
    assert (bad.hi - bad.lo) < (good.hi - good.lo)
