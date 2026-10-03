"""#718: Stage 2 of #685 — stopping design x pairs, zero-spend simulator.

Stage 1 varied Null allocation and the F - N construction under the registered
anytime rule and found no design that reaches the power target. Stage 2 varies
the stopping design and the number of pairs together, so a reader can see, for
each stopping design, the smallest priced configuration that meets the target,
or that none does.

No model calls, no network, no spend.

The four stopping designs (``stopping`` column):

  anytime           The registered rule, as the #685 simulator runs it.
                    The reference row; F - N construction may be union or
                    direct; pass alpha 0.0209; starting wealth 1.0.
  anytime-tuned     The same anytime-valid test, with a bet sized for a
                    declared alternative. Direct F - N only. Starting wealth
                    1.0, 0.5 or 0.25.
  fixed-n-betting   One look at n, with a fixed-time betting bound.
                    Direct F - N only. Pass alpha 0.0209, 0.0105 or 0.005.
  fixed-n-score     One look at n, with a score test against the margin.
                    Direct F - N only. Pass alpha 0.0209, 0.0105 or 0.005.

CUT alpha is 0.05 on every row. Output goes under
``docs/findings/data/stage1a-regime-685-stage2/``.

Usage:
  python scripts/screens/419/simulate_stage1a_regime_685_stage2.py --out DIR \
         [--replicates 2000] [--seed 685] [--workers N] [--reduced]
  python scripts/screens/419/simulate_stage1a_regime_685_stage2.py --out DIR --rebuild
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import simulate_a_design as a650
import simulate_stage1a_regime_685 as s685

Stopping = Literal["anytime", "anytime-tuned", "fixed-n-betting", "fixed-n-score"]
STOPPINGS: tuple[Stopping, ...] = (
    "anytime",
    "anytime-tuned",
    "fixed-n-betting",
    "fixed-n-score",
)
NEW_DESIGN_STOPPINGS: tuple[Stopping, ...] = (
    "anytime-tuned",
    "fixed-n-betting",
    "fixed-n-score",
)

BASELINES = s685.BASELINES
EFFECTS = s685.EFFECTS
POWER_TARGETS = s685.POWER_TARGETS
REPLICATES = 2000
SEED = 685
PAIRS = (100, 200, 300, 400, 500, 600, 800)
NULL_PER_PAIR = (1.0, 0.5)
FIXED_PASS_ALPHAS = (0.0209, 0.0105, 0.005)
STARTING_WEALTHS = (1.0, 0.5, 0.25)
FN_ANYTIME = ("union", "direct")
FN_NEW_DESIGN = ("direct",)
BOUNDARY = a650.BOUNDARY
PASS_ALPHA = a650.PASS_ALPHA
FUTILITY_ALPHA = a650.FUTILITY_ALPHA

REDUCED_PAIRS = (100,)
REDUCED_NULL_PER_PAIR = (1.0, 0.5)
REDUCED_EFFECTS = (0.00, 0.10, 0.20, 0.30)
REDUCED_REPLICATES = 200

DESIGN_FIELDS = (
    "n_full",
    "n_placebo",
    "n_null",
    "total_epochs",
    "null_per_pair",
    "fn_construction",
    "stopping",
    "pass_alpha",
    "starting_wealth",
)
_RATE_FIELDS = (
    "p_fp_half",
    "p_fn_half",
    "p_joint_pass",
    "p_cut",
    "p_cant_tell_yet",
    "se_pass",
)
_PRICE_FIELDS = ("expected_pairs", "expected_epochs", "expected_spend", "price_range")
_NOT_REACHED = "not reached"

# Declared sizing alternatives for the tuned bet (fixed before the first pair).
_TUNED_PASS_ALT_P_ARM = (0.65, 0.35)  # d = 0.30 at p_P = p_N = 0.35
_TUNED_CUT_ALT_P_ARM = (0.45, 0.35)  # d = 0.10 at p_P = 0.35
_TUNED_M0 = 0.6
_TUNED_TRUNC = 0.5


# ---------------------------------------------------------------------------
# Design and cell
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Design:
    n_pairs: int
    null_per_pair: float = 1.0
    fn_construction: str = "direct"
    stopping: str = "anytime"
    pass_alpha: float = PASS_ALPHA
    starting_wealth: float = 1.0

    @property
    def n_full(self) -> int:
        return self.n_pairs

    @property
    def n_placebo(self) -> int:
        return self.n_pairs

    @property
    def n_null(self) -> int:
        if self.null_per_pair == 0.5:
            return self.n_pairs // 2
        return round(self.null_per_pair * self.n_pairs)

    @property
    def total_epochs(self) -> int:
        return self.n_full + self.n_placebo + self.n_null


@dataclass(frozen=True)
class Cell:
    p_full: float
    p_placebo: float
    p_null: float

    @property
    def d(self) -> float:
        return round(self.p_full - self.p_placebo, 10)


@dataclass(frozen=True)
class Row:
    """One (cell, design) result at the design's read time."""

    cell: Cell
    design: Design
    replicates: int
    p_fp_half: float
    p_fn_half: float
    p_joint_pass: float
    p_cut: float
    p_cant_tell_yet: float
    se_pass: float
    expected_pairs: float
    expected_epochs: float
    holds_level: bool
    per_look: tuple[s685.LookRow, ...] = ()


# ---------------------------------------------------------------------------
# Helpers reused from #685
# ---------------------------------------------------------------------------

role = s685.role
true_fp_diff = s685.true_fp_diff
true_fn_diff = s685.true_fn_diff
is_pass_calibration_cell = s685.is_pass_calibration_cell
is_cut_calibration_cell = s685.is_cut_calibration_cell
is_calibration_cell = s685.is_calibration_cell
cell_rng = s685.cell_rng
_price = s685._price
_expected_spend = s685._expected_spend
_PRICE_LO = s685._PRICE_LO
_PRICE_HI = s685._PRICE_HI
_PRICE_CAP = s685._PRICE_CAP
JOINT_STATES = s685.JOINT_STATES
diagonal_cells = s685.diagonal_cells


# ---------------------------------------------------------------------------
# Tuned-bet sizing: lambda fixed before the first pair
# ---------------------------------------------------------------------------


def x_alt_distribution(p_a: float, p_b: float) -> tuple[tuple[float, float], ...]:
    """Distribution of X = (A - B + 1)/2 for independent Bernoulli arms."""
    p_equal = p_a * p_b + (1.0 - p_a) * (1.0 - p_b)
    return (
        (1.0, p_a * (1.0 - p_b)),
        (0.5, p_equal),
        (0.0, (1.0 - p_a) * p_b),
    )


def expected_log_wealth_factor(
    lam: float,
    m0: float,
    dist: tuple[tuple[float, float], ...],
    *,
    upward: bool,
) -> float:
    """E[log(1 + lam*(X - m0))] under ``dist``; -inf when a factor is non-positive."""
    total = 0.0
    for x, p in dist:
        factor = 1.0 + lam * ((x - m0) if upward else (m0 - x))
        if factor <= 0.0:
            return -math.inf
        total += p * math.log(factor)
    return total


def tuned_lambda(
    m0: float,
    dist: tuple[tuple[float, float], ...],
    *,
    upward: bool,
) -> float:
    """lambda >= 0 maximising expected log wealth under the declared alternative.

    Truncated so every wealth factor stays positive: lambda <= _TRUNC_C / m0
    for an upward bet (the x = 0 factor is 1 - trunc > 0) and
    lambda <= _TRUNC_C / (1 - m0) for a downward bet (the x = 1 factor is
    1 - trunc > 0). The objective is concave in lambda (log of an affine
    function, averaged), so a ternary search on the truncated interval
    converges to the maximiser. The bet may never depend on the outcome it
    multiplies: this constant is computed once, before the first pair.
    """
    lam_cap = (_TUNED_TRUNC / m0) if upward else (_TUNED_TRUNC / (1.0 - m0))
    lo, hi = 0.0, lam_cap
    for _ in range(80):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        f1 = expected_log_wealth_factor(m1, m0, dist, upward=upward)
        f2 = expected_log_wealth_factor(m2, m0, dist, upward=upward)
        if f1 < f2:
            lo = m1
        else:
            hi = m2
    return 0.5 * (lo + hi)


_PASS_ALT_DIST = x_alt_distribution(*_TUNED_PASS_ALT_P_ARM)
_CUT_ALT_DIST = x_alt_distribution(*_TUNED_CUT_ALT_P_ARM)
LAMBDA_FP_PASS = tuned_lambda(_TUNED_M0, _PASS_ALT_DIST, upward=True)
LAMBDA_FP_CUT = tuned_lambda(_TUNED_M0, _CUT_ALT_DIST, upward=False)
LAMBDA_FN_PASS = LAMBDA_FP_PASS  # same observation construction, same alternative


class TunedWealth:
    """One wealth process per replicate: W0 * prod(1 + lambda*(x - m0)).

    ``lambda`` is a constant fixed before the first pair. ``upward`` selects
    the PASS bet (1 + lambda*(x - m0)); ``downward`` the CUT bet
    (1 + lambda*(m0 - x)). The running maximum of the wealth is what crosses
    1/alpha.
    """

    def __init__(
        self,
        replicates: int,
        w0: float,
        lam: float,
        m0: float,
        *,
        upward: bool,
    ) -> None:
        self.lam = float(lam)
        self.m0 = float(m0)
        self.upward = bool(upward)
        start = math.log(w0)
        self.log_w = np.full(replicates, start, dtype=np.float64)
        self.running_max = np.full(replicates, start, dtype=np.float64)

    def step(self, x: np.ndarray) -> None:
        if self.upward:
            self.log_w += np.log1p(self.lam * (x - self.m0))
        else:
            self.log_w += np.log1p(self.lam * (self.m0 - x))
        self.running_max = np.maximum(self.running_max, self.log_w)

    def rejects(self, alpha: float) -> np.ndarray:
        return self.running_max >= math.log(1.0 / alpha)


# ---------------------------------------------------------------------------
# Fixed-time hedged betting (Waudby-Smith and Ramdas, JRSSB 2023, Thm 3, Rmk 3)
# ---------------------------------------------------------------------------


def fixed_n_log_wealth(
    xs: np.ndarray,
    alpha: float,
    m0: float,
    *,
    upward: bool,
) -> np.ndarray:
    """Final log wealth at horizon n, with the bet at step t scaled for n.

    The predictable fraction is sqrt(2 log(1/alpha) / (n * var_hat_t)) —
    scaled for the horizon n, not for the time t — truncated so every factor
    stays positive. The bound is the set of means whose final wealth stays
    below 1/alpha; PASS rejects when that set excludes m0 on the lower side,
    CUT when it excludes m0 on the upper side.
    """
    replicates, n = xs.shape
    if n < 1:
        return np.zeros(replicates, dtype=np.float64)
    log_w = np.zeros(replicates, dtype=np.float64)
    mean_hat = np.full(replicates, 0.5, dtype=np.float64)
    var_hat = np.full(replicates, 0.25, dtype=np.float64)
    numer = 2.0 * math.log(1.0 / alpha)
    trunc = _TUNED_TRUNC / m0 if upward else _TUNED_TRUNC / (1.0 - m0)
    for k in range(n):
        t = float(k + 1)
        denom = np.maximum(var_hat, 1e-6) * float(n)
        lam = np.minimum(np.sqrt(numer / denom), trunc)
        x = xs[:, k]
        if upward:
            log_w += np.log1p(lam * (x - m0))
        else:
            log_w += np.log1p(lam * (m0 - x))
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1.0)
        var_hat = np.maximum(var_hat + (resid * resid - var_hat) / (t + 1.0), 1e-6)
    return log_w


def fixed_n_rejects(xs: np.ndarray, alpha: float, m0: float, *, upward: bool) -> np.ndarray:
    """Reject when final wealth at m0 reaches 1/alpha (the bound excludes m0)."""
    return fixed_n_log_wealth(xs, alpha, m0, upward=upward) >= math.log(1.0 / alpha)


# ---------------------------------------------------------------------------
# Score tests
# ---------------------------------------------------------------------------


def tango_score_z(b: int, c: int, n: int, delta0: float) -> float:
    """Tango (1998) score test for paired binary data against margin delta0.

    With b pairs (F correct, P wrong), c pairs (F wrong, P correct) and n
    pairs: A = 2n, B = -b - c + (2n - b + c) delta0, C = -c delta0 (1 - delta0),
    q = (sqrt(B^2 - 4AC) - B) / (2A),
    z = (b - c - n delta0) / sqrt(n (2q + delta0 (1 - delta0))).

    At delta0 = 0 this equals McNemar's (b - c) / sqrt(b + c). A zero
    denominator yields 0.0: no evidence either way.
    """
    if n <= 0:
        return 0.0
    a_mat = 2.0 * n
    b_mat = -b - c + (2.0 * n - b + c) * delta0
    c_mat = -c * delta0 * (1.0 - delta0)
    disc = b_mat * b_mat - 4.0 * a_mat * c_mat
    if disc < 0.0:
        return 0.0
    q = (math.sqrt(disc) - b_mat) / (2.0 * a_mat)
    denom_sq = n * (2.0 * q + delta0 * (1.0 - delta0))
    if denom_sq <= 0.0:
        return 0.0
    return (b - c - n * delta0) / math.sqrt(denom_sq)


def _constrained_null_mle(
    k_f: int, n_f: int, k_n: int, n_n: int, delta0: float
) -> tuple[float, float]:
    """(p_tilde_F, p_tilde_N) maximising the binomial likelihood subject to
    p_F - p_N = delta0. Solved by bisection on p_N = q in the feasible interval.
    """
    if n_f <= 0 or n_n <= 0:
        return 0.0, 0.0
    q_lo = max(0.0, -delta0)
    q_hi = min(1.0, 1.0 - delta0)
    if q_hi <= q_lo:
        return min(1.0, max(0.0, q_lo + delta0)), min(1.0, max(0.0, q_lo))

    def score(q: float) -> float:
        p = q + delta0
        if p <= 0.0 or p >= 1.0 or q <= 0.0 or q >= 1.0:
            return 0.0
        return k_f / p - (n_f - k_f) / (1.0 - p) + k_n / q - (n_n - k_n) / (1.0 - q)

    lo, hi = q_lo, q_hi
    s_lo = score(lo + 1e-12)
    s_hi = score(hi - 1e-12)
    if s_lo <= 0.0:
        q = lo
    elif s_hi >= 0.0:
        q = hi
    else:
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if score(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        q = 0.5 * (lo + hi)
    p = q + delta0
    return min(1.0, max(0.0, p)), min(1.0, max(0.0, q))


def farrington_manning_z(k_f: int, n_f: int, k_n: int, n_n: int, delta0: float) -> float:
    """Farrington-Manning score test for p_F - p_N = delta0.

    z = (p_hat_F - p_hat_N - delta0) / sqrt(p_tilde_F(1-p_tilde_F)/n_F +
    p_tilde_N(1-p_tilde_N)/n_N), where the tilde values maximise the binomial
    likelihood subject to p_F - p_N = delta0. A zero denominator yields 0.0.
    """
    if n_f <= 0 or n_n <= 0:
        return 0.0
    p_f_hat = k_f / n_f
    p_n_hat = k_n / n_n
    p_t, n_t = _constrained_null_mle(k_f, n_f, k_n, n_n, delta0)
    var = p_t * (1.0 - p_t) / n_f + n_t * (1.0 - n_t) / n_n
    if var <= 0.0:
        return 0.0
    return (p_f_hat - p_n_hat - delta0) / math.sqrt(var)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_quantile(p: float) -> float:
    """Inverse standard normal CDF by bisection on math.erf."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Simulation paths: the branch on ``stopping``
# ---------------------------------------------------------------------------


def _se(p: float, replicates: int) -> float:
    return math.sqrt(p * (1.0 - p) / replicates)


def _fixed_n_look_row(
    design: Design, *, p_pass: float, p_cut: float, replicates: int
) -> s685.LookRow:
    return s685.LookRow(
        look=design.n_pairs,
        p_pass=p_pass,
        p_cut=p_cut,
        p_cant_tell_yet=max(0.0, 1.0 - p_pass - p_cut),
        se_pass=_se(p_pass, replicates),
        expected_pairs=float(design.n_pairs),
        expected_epochs=float(design.total_epochs),
    )


def _row_from_anytime(cell: Cell, design: Design, result: s685.CellResult) -> Row:
    """Convert a #685 CellResult into a stage-2 Row, deriving the half rates.

    P(F-P half) = P(joint PASS) + P(F-P cleared | unresolved at cap) * P(unresolved).
    The same identity holds for the F-N half. CUT rows contribute to neither half.
    """
    last = result.per_look[-1]
    p_pass = last.p_pass
    p_cut = last.p_cut
    unresolved = max(0.0, 1.0 - p_pass - p_cut)
    term = result.terminal
    n_unres = sum(len(t.lb_fp) for t in term.values())
    if n_unres > 0:
        n_fp = len(term["fp_passes_fn_fails"].lb_fp)
        n_fn = len(term["fn_passes_fp_fails"].lb_fp)
        p_fp_half = p_pass + unresolved * (n_fp / n_unres)
        p_fn_half = p_pass + unresolved * (n_fn / n_unres)
    else:
        p_fp_half = p_pass
        p_fn_half = p_pass
    p_joint = p_pass
    holds = _row_calibration_holds_for_alpha(
        cell=cell,
        p_pass=p_joint,
        p_cut=p_cut,
        pass_alpha=design.pass_alpha,
        replicates=result.replicates,
    )
    return Row(
        cell=cell,
        design=design,
        replicates=result.replicates,
        p_fp_half=p_fp_half,
        p_fn_half=p_fn_half,
        p_joint_pass=p_joint,
        p_cut=p_cut,
        p_cant_tell_yet=max(0.0, 1.0 - p_joint - p_cut),
        se_pass=last.se_pass,
        expected_pairs=last.expected_pairs,
        expected_epochs=last.expected_epochs,
        holds_level=holds,
        per_look=result.per_look,
    )


def _row_calibration_holds_for_alpha(
    *,
    cell: Cell,
    p_pass: float,
    p_cut: float,
    pass_alpha: float,
    replicates: int,
) -> bool:
    ok = True
    if is_pass_calibration_cell(cell):
        limit = pass_alpha + a650.calibration_tolerance(replicates, pass_alpha)
        ok = p_pass <= limit and ok
    if is_cut_calibration_cell(cell):
        cut_limit = FUTILITY_ALPHA + a650.calibration_tolerance(replicates, FUTILITY_ALPHA)
        ok = p_cut <= cut_limit and ok
    return ok


def row_calibration_holds(row: Row) -> bool:
    """Both calibration halves that apply to this row, at its read time.

    PASS is checked wherever true F-P or F-N sits at or below BOUNDARY, against
    the row's own pass_alpha plus 3 MC SE. CUT is checked wherever true F-P sits
    at or above BOUNDARY, against FUTILITY_ALPHA plus 3 MC SE.
    """
    return row.holds_level


def is_nonfatal_calibration_failure(row: Row) -> bool:
    """A fixed-n-score row that fails calibration: labelled, not fatal.

    It is left out of the headline. Every other design's failure fails the run.
    """
    return (not row.holds_level) and row.design.stopping == "fixed-n-score"


def headline_includes(row: Row) -> bool:
    """A row enters the headline only if it actually holds its level."""
    return row.holds_level


def run_cell(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    pass_alpha_override: float | None = None,
) -> Row:
    """Run one cell under the design's stopping rule. Branches on ``stopping``.

    ``pass_alpha_override`` loosens or tightens the RULE the simulation applies
    while the row keeps the alpha it declares. Calibration reads the declared
    ``design.pass_alpha``, so an override that makes the rule too liberal is
    visible to the calibration read. The negative controls use it.
    """
    rule_alpha = design.pass_alpha if pass_alpha_override is None else pass_alpha_override
    sim_design = Design(
        n_pairs=design.n_pairs,
        null_per_pair=design.null_per_pair,
        fn_construction=design.fn_construction,
        stopping=design.stopping,
        pass_alpha=rule_alpha,
        starting_wealth=design.starting_wealth,
    )
    if sim_design.stopping == "anytime":
        return _run_anytime(cell, design, replicates=replicates, seed=seed, rule_alpha=rule_alpha)
    if sim_design.stopping == "anytime-tuned":
        return _run_anytime_tuned(
            cell, design, replicates=replicates, seed=seed, rule_alpha=rule_alpha
        )
    if sim_design.stopping == "fixed-n-betting":
        return _run_fixed_n_betting(
            cell, design, replicates=replicates, seed=seed, rule_alpha=rule_alpha
        )
    if sim_design.stopping == "fixed-n-score":
        return _run_fixed_n_score(
            cell, design, replicates=replicates, seed=seed, rule_alpha=rule_alpha
        )
    raise ValueError(f"unknown stopping rule: {design.stopping!r}")


def _run_anytime(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    rule_alpha: float | None = None,
) -> Row:
    """The registered rule, as the #685 simulator runs it.

    Delegates to s685.run_cell so the reference row matches the committed #685
    data byte-for-byte at the same seed, pair count, construction and alpha.
    The row keeps design.pass_alpha; only the rule the simulation applies may
    be overridden.
    """
    alpha = design.pass_alpha if rule_alpha is None else rule_alpha
    s_design = s685.Design(
        n_pairs=design.n_pairs,
        null_per_pair=design.null_per_pair,
        fn_construction=design.fn_construction,
        stopping="anytime",
    )
    result = s685.run_cell(cell, s_design, replicates=replicates, seed=seed, pass_alpha=alpha)
    return _row_from_anytime(cell, design, result)


def _draw_streams(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Full, Placebo, Null-all, null_draws and fn_mask, matching #685 draws."""
    horizon = design.n_pairs
    rng = cell_rng(seed, cell)
    full = (rng.random((replicates, horizon)) < cell.p_full).astype(np.int64)
    placebo = (rng.random((replicates, horizon)) < cell.p_placebo).astype(np.int64)
    null_all = (rng.random((replicates, horizon, 2)) < cell.p_null).astype(np.int64)
    null_draws = s685.null_draw_counts(horizon, design.null_per_pair)
    fn_mask = null_draws > 0
    return full, placebo, null_all, null_draws, fn_mask


def _null_used_and_fn_obs(
    full: np.ndarray,
    placebo: np.ndarray,
    null_all: np.ndarray,
    null_draws: np.ndarray,
    fn_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """(null_used stream, xs_fn observations) on scheduled-null pairs."""
    replicates = full.shape[0]
    scheduled = [(k, int(c)) for k, c in enumerate(null_draws) if c]
    if not scheduled:
        return (
            np.empty((replicates, 0), dtype=np.int64),
            np.empty((replicates, 0), dtype=np.float64),
        )
    null_used = np.concatenate([null_all[:, k, :c] for k, c in scheduled], axis=1)
    null_mean = np.array([null_all[:, k, :c].mean(axis=1) for k, c in scheduled]).T
    xs_fn = (full[:, fn_mask] - null_mean + 1) / 2.0
    return null_used, xs_fn


def _run_anytime_tuned(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    rule_alpha: float | None = None,
) -> Row:
    """Same anytime-valid test, bet sized for the declared alternative.

    For PASS on F-P: x = (F - P + 1)/2, null mean m0 = 0.6, wealth after t
    pairs is W0 times the product over i <= t of (1 + lambda (x_i - m0)),
    with lambda >= 0 the constant that maximises expected log wealth under the
    declared design alternative (d = 0.30 at p_P = 0.35). Reject when the
    running maximum of the wealth reaches 1/alpha. CUT mirrors it: null
    d >= 0.20, bet downward, sized for d = 0.10, alpha 0.05. The direct F-N
    test uses the same construction on the Full-minus-mean-Null observation.
    W0 is design.starting_wealth.
    """
    full, placebo, null_all, null_draws, fn_mask = _draw_streams(
        cell, design, replicates=replicates, seed=seed
    )
    _null_used, xs_fn = _null_used_and_fn_obs(full, placebo, null_all, null_draws, fn_mask)
    xs_fp = (full - placebo + 1) / 2.0
    w0 = design.starting_wealth
    alpha = design.pass_alpha if rule_alpha is None else rule_alpha
    horizon = design.n_pairs

    fp_pass = TunedWealth(replicates, w0, LAMBDA_FP_PASS, _TUNED_M0, upward=True)
    fp_cut = TunedWealth(replicates, w0, LAMBDA_FP_CUT, _TUNED_M0, upward=False)
    fn_pass = TunedWealth(replicates, w0, LAMBDA_FN_PASS, _TUNED_M0, upward=True)

    stop_at = np.full(replicates, horizon + 1, dtype=np.int64)
    passed = np.zeros(replicates, dtype=np.bool_)
    cut = np.zeros(replicates, dtype=np.bool_)
    fn_counts = np.cumsum(fn_mask.astype(np.int64))

    for k in range(horizon):
        fp_pass.step(xs_fp[:, k])
        fp_cut.step(xs_fp[:, k])
        if fn_mask[k]:
            fn_pass.step(xs_fn[:, fn_counts[k] - 1])
        for r in np.flatnonzero(stop_at > horizon).tolist():
            if fp_cut.rejects(FUTILITY_ALPHA)[r]:
                stop_at[r] = k + 1
                cut[r] = True
                continue
            if not fp_pass.rejects(alpha)[r]:
                continue
            if fn_pass.rejects(alpha)[r]:
                stop_at[r] = k + 1
                passed[r] = True

    p_joint = float(np.mean(passed))
    p_cut = float(np.mean(cut))
    p_cant = max(0.0, 1.0 - p_joint - p_cut)
    unresolved = stop_at > horizon
    n_unres = int(np.sum(unresolved))
    if n_unres > 0:
        fp_clear = fp_pass.rejects(alpha)[unresolved]
        fn_clear = fn_pass.rejects(alpha)[unresolved]
        p_fp_half = p_joint + p_cant * float(np.mean(fp_clear))
        p_fn_half = p_joint + p_cant * float(np.mean(fn_clear))
    else:
        p_fp_half = p_joint
        p_fn_half = p_joint

    null_cum = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(null_draws)))
    epochs_profile = (2.0 * np.arange(horizon + 1) + null_cum).astype(np.float64)
    used = np.minimum(stop_at, horizon)
    expected_epochs = float(np.mean(epochs_profile[used]))
    expected_pairs = float(np.mean(used))

    look_rows = s685.per_look_rows(stop_at, passed, cut, horizon, epochs_profile)
    holds = _row_calibration_holds_for_alpha(
        cell=cell,
        p_pass=p_joint,
        p_cut=p_cut,
        pass_alpha=design.pass_alpha,
        replicates=replicates,
    )
    return Row(
        cell=cell,
        design=design,
        replicates=replicates,
        p_fp_half=p_fp_half,
        p_fn_half=p_fn_half,
        p_joint_pass=p_joint,
        p_cut=p_cut,
        p_cant_tell_yet=p_cant,
        se_pass=_se(p_joint, replicates),
        expected_pairs=expected_pairs,
        expected_epochs=expected_epochs,
        holds_level=holds,
        per_look=look_rows,
    )


def _run_fixed_n_betting(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    rule_alpha: float | None = None,
) -> Row:
    """One look at n, with a fixed-time hedged betting bound.

    The bet at step t uses only outcomes before t and is scaled for the
    horizon n, not for the time t. The bound is the set of means whose final
    wealth stays below 1/alpha. No interim read: expected epochs equal the cap.
    """
    full, placebo, null_all, null_draws, fn_mask = _draw_streams(
        cell, design, replicates=replicates, seed=seed
    )
    _null_used, xs_fn = _null_used_and_fn_obs(full, placebo, null_all, null_draws, fn_mask)
    xs_fp = (full - placebo + 1) / 2.0
    alpha = design.pass_alpha if rule_alpha is None else rule_alpha
    m0 = _TUNED_M0
    fn_rejects = (
        fixed_n_rejects(xs_fn, alpha, m0, upward=True)
        if xs_fn.shape[1] > 0
        else np.zeros(replicates, dtype=np.bool_)
    )
    fp_pass = fixed_n_rejects(xs_fp, alpha, m0, upward=True)
    fp_cut = fixed_n_rejects(xs_fp, FUTILITY_ALPHA, m0, upward=False)
    passed = fp_pass & fn_rejects
    cut = fp_cut & ~passed
    p_joint = float(np.mean(passed))
    p_cut = float(np.mean(cut))
    p_cant = max(0.0, 1.0 - p_joint - p_cut)
    p_fp = float(np.mean(fp_pass))
    p_fn = float(np.mean(fn_rejects)) if xs_fn.shape[1] > 0 else 0.0
    holds = _row_calibration_holds_for_alpha(
        cell=cell,
        p_pass=p_joint,
        p_cut=p_cut,
        pass_alpha=design.pass_alpha,
        replicates=replicates,
    )
    look = _fixed_n_look_row(design, p_pass=p_joint, p_cut=p_cut, replicates=replicates)
    return Row(
        cell=cell,
        design=design,
        replicates=replicates,
        p_fp_half=p_fp,
        p_fn_half=p_fn,
        p_joint_pass=p_joint,
        p_cut=p_cut,
        p_cant_tell_yet=p_cant,
        se_pass=look.se_pass,
        expected_pairs=look.expected_pairs,
        expected_epochs=look.expected_epochs,
        holds_level=holds,
        per_look=(look,),
    )


def _run_fixed_n_score(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    rule_alpha: float | None = None,
) -> Row:
    """One look at n, with a score test against the margin.

    F-P: Tango's 1998 score test for paired binary data against
    delta0 = 0.20. PASS rejects for large z at the row's alpha. F-N: the
    Farrington-Manning score test. CUT is the mirrored one-sided F-P test at
    0.05 (reject for small z).

    The Farrington-Manning marginals are the Full successes over all pairs and
    the Null successes over the Null draws that were scheduled.
    """
    full, placebo, null_all, null_draws, fn_mask = _draw_streams(
        cell, design, replicates=replicates, seed=seed
    )
    _null_used, xs_fn = _null_used_and_fn_obs(full, placebo, null_all, null_draws, fn_mask)
    n = design.n_pairs
    alpha = design.pass_alpha if rule_alpha is None else rule_alpha
    delta0 = BOUNDARY
    b = ((full == 1) & (placebo == 0)).sum(axis=1)
    c = ((full == 0) & (placebo == 1)).sum(axis=1)
    z_fp = np.array(
        [tango_score_z(int(bb), int(cc), n, delta0) for bb, cc in zip(b, c, strict=True)]
    )
    if xs_fn.shape[1] > 0:
        k_f = full.sum(axis=1)
        k_n = _null_used.sum(axis=1)
        n_null = int(fn_mask.sum())
        z_fn = np.array(
            [
                farrington_manning_z(int(ff), n, int(nn), n_null, delta0)
                for ff, nn in zip(k_f, k_n, strict=True)
            ]
        )
    else:
        z_fn = np.full(replicates, -math.inf, dtype=np.float64)

    z_pass_crit = _normal_quantile(1.0 - alpha)
    z_cut_crit = _normal_quantile(FUTILITY_ALPHA)  # negative; CUT rejects for small z
    fp_pass = z_fp >= z_pass_crit
    fn_pass = z_fn >= z_pass_crit
    passed = fp_pass & fn_pass
    cut = (z_fp <= z_cut_crit) & ~passed
    p_joint = float(np.mean(passed))
    p_cut = float(np.mean(cut))
    p_cant = max(0.0, 1.0 - p_joint - p_cut)
    p_fp = float(np.mean(fp_pass))
    p_fn = float(np.mean(fn_pass)) if xs_fn.shape[1] > 0 else 0.0
    holds = _row_calibration_holds_for_alpha(
        cell=cell,
        p_pass=p_joint,
        p_cut=p_cut,
        pass_alpha=design.pass_alpha,
        replicates=replicates,
    )
    look = _fixed_n_look_row(design, p_pass=p_joint, p_cut=p_cut, replicates=replicates)
    return Row(
        cell=cell,
        design=design,
        replicates=replicates,
        p_fp_half=p_fp,
        p_fn_half=p_fn,
        p_joint_pass=p_joint,
        p_cut=p_cut,
        p_cant_tell_yet=p_cant,
        se_pass=look.se_pass,
        expected_pairs=look.expected_pairs,
        expected_epochs=look.expected_epochs,
        holds_level=holds,
        per_look=(look,),
    )


# ---------------------------------------------------------------------------
# Calibration read and exit code
# ---------------------------------------------------------------------------


def calibration_exit_code(rows: Sequence[Row]) -> int:
    """Exit code from the calibration read.

    0 iff every calibration row holds its level, except fixed-n-score rows that
    fail: those are labelled as not holding their level and left out of the
    headline, and they do not fail the run. Every other design's failure does.
    """
    cal = [r for r in rows if is_calibration_cell(r.cell)]
    return 0 if all(r.holds_level or is_nonfatal_calibration_failure(r) for r in cal) else 1


# ---------------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadlineRow:
    stopping: str
    pass_alpha: float
    starting_wealth: float
    target: float
    reached: bool
    n_pairs: int | None
    null_per_pair: float | None
    fn_construction: str | None
    total_epochs: int | None
    expected_spend: str | None
    cap_price: str | None
    p_pass_at_d030: float | None
    p_cut_at_d010: float | None
    missing_half: str
    any_row_holds_level: bool


def _group_key(row: Row) -> tuple[str, float, float]:
    return (row.design.stopping, row.design.pass_alpha, row.design.starting_wealth)


def _diagonal_minima(
    rows: Sequence[Row],
    *,
    stopping: str,
    pass_alpha: float,
    starting_wealth: float,
    n_pairs: int,
    null_per_pair: float,
    fn_construction: str,
    d: float,
) -> tuple[float | None, float | None]:
    """(min P(joint PASS) or P(CUT), missing) over the three diagonal cells."""
    diag = diagonal_cells()
    vals: list[float] = []
    for p_p, p_n in diag:
        match = next(
            (
                r
                for r in rows
                if r.design.stopping == stopping
                and math.isclose(r.design.pass_alpha, pass_alpha, abs_tol=1e-12)
                and math.isclose(r.design.starting_wealth, starting_wealth, abs_tol=1e-12)
                and r.design.n_pairs == n_pairs
                and math.isclose(r.design.null_per_pair, null_per_pair, abs_tol=1e-9)
                and r.design.fn_construction == fn_construction
                and math.isclose(r.cell.d, d, abs_tol=1e-9)
                and math.isclose(r.cell.p_placebo, p_p, abs_tol=1e-9)
                and math.isclose(r.cell.p_null, p_n, abs_tol=1e-9)
            ),
            None,
        )
        if match is None:
            return None, f"missing d={d:.2f} diagonal cell ({p_p:.2f}, {p_n:.2f})"
        vals.append(match.p_joint_pass if d >= 0.25 else match.p_cut)
    return min(vals), ""


def _config_key(row: Row) -> tuple[int, float, float, int, float, str]:
    """Rank configs by cap price (total_epochs), then expected epochs, then pairs."""
    return (
        row.design.total_epochs,
        row.expected_epochs,
        row.design.n_pairs,
        row.design.null_per_pair,
        row.design.n_pairs,
        row.design.fn_construction,
    )


def headline_rows(results: Sequence[Row]) -> tuple[HeadlineRow, ...]:
    """Smallest priced configuration per (stopping, pass_alpha, starting_wealth).

    The diagonal target is the minimum over the three p_P = p_N cells of
    P(joint PASS) at d = 0.30 and of P(CUT) at d = 0.10, each at or above the
    target. Rows that fail calibration are excluded unless they are fixed-n-score
    rows, which are labelled as not holding their level and left out. Configurations
    are ranked by total_epochs (the cap price), then by expected epochs.
    """
    groups = sorted({_group_key(r) for r in results})
    rows: list[HeadlineRow] = []
    for stopping, pass_alpha, w0 in groups:
        members = [
            r
            for r in results
            if _group_key(r) == (stopping, pass_alpha, w0) and headline_includes(r)
        ]
        scored = sorted(members, key=_config_key)
        for target in POWER_TARGETS:
            chosen: HeadlineRow | None = None
            missing = _NOT_REACHED
            min_pass: float | None = None
            min_cut: float | None = None
            for config in scored:
                mp, mmiss = _diagonal_minima(
                    results,
                    stopping=stopping,
                    pass_alpha=pass_alpha,
                    starting_wealth=w0,
                    n_pairs=config.design.n_pairs,
                    null_per_pair=config.design.null_per_pair,
                    fn_construction=config.design.fn_construction,
                    d=0.30,
                )
                mc, _cmiss = _diagonal_minima(
                    results,
                    stopping=stopping,
                    pass_alpha=pass_alpha,
                    starting_wealth=w0,
                    n_pairs=config.design.n_pairs,
                    null_per_pair=config.design.null_per_pair,
                    fn_construction=config.design.fn_construction,
                    d=0.10,
                )
                if mp is None or mc is None:
                    missing = mmiss or "missing diagonal cells"
                    continue
                min_pass, min_cut = mp, mc
                halves: list[str] = []
                if mp < target:
                    halves.append("P(joint PASS) >= target at d = 0.30")
                if mc < target:
                    halves.append("P(CUT) >= target at d = 0.10")
                if halves:
                    missing = " and ".join(halves)
                    continue
                chosen = HeadlineRow(
                    stopping=stopping,
                    pass_alpha=pass_alpha,
                    starting_wealth=w0,
                    target=target,
                    reached=True,
                    n_pairs=config.design.n_pairs,
                    null_per_pair=config.design.null_per_pair,
                    fn_construction=config.design.fn_construction,
                    total_epochs=config.design.total_epochs,
                    expected_spend=_expected_spend(config.expected_epochs),
                    cap_price=f"${config.design.total_epochs * _PRICE_CAP:.2f}",
                    p_pass_at_d030=mp,
                    p_cut_at_d010=mc,
                    missing_half="",
                    any_row_holds_level=True,
                )
                break
            if chosen is None:
                any_hold = any(
                    headline_includes(r)
                    for r in results
                    if _group_key(r) == (stopping, pass_alpha, w0)
                )
                chosen = HeadlineRow(
                    stopping=stopping,
                    pass_alpha=pass_alpha,
                    starting_wealth=w0,
                    target=target,
                    reached=False,
                    n_pairs=None,
                    null_per_pair=None,
                    fn_construction=None,
                    total_epochs=None,
                    expected_spend=None,
                    cap_price=None,
                    p_pass_at_d030=min_pass,
                    p_cut_at_d010=min_cut,
                    missing_half=missing,
                    any_row_holds_level=any_hold,
                )
            rows.append(chosen)
    return tuple(rows)


def headline_price_sentence(rows: Sequence[HeadlineRow]) -> str:
    """One sentence, from the data only, about cap price and expected spend at 0.80."""
    at_080 = [r for r in rows if math.isclose(r.target, 0.80, abs_tol=1e-9) and r.reached]
    cap_under = [
        r for r in at_080 if r.total_epochs is not None and r.total_epochs * _PRICE_CAP < 100.0
    ]
    spend_under = [r for r in at_080 if r.total_epochs is not None and r.expected_spend is not None]
    # Expected spend under $100 is read at the high list rate on expected epochs.
    spend_ok = False
    for r in at_080:
        if r.total_epochs is None or r.expected_spend is None:
            continue
        # expected_spend is "$lo-$hi"; parse the hi end.
        try:
            hi = float(r.expected_spend.split("-$")[1].rstrip())
        except (IndexError, ValueError):
            continue
        if hi < 100.0:
            spend_ok = True
            break
    cap_phrase = (
        "at least one design meets the 0.80 target with a cap price under $100"
        if cap_under
        else "no design meets the 0.80 target with a cap price under $100"
    )
    spend_phrase = (
        "at least one design meets it with expected spend under $100"
        if spend_ok
        else "no design meets it with expected spend under $100"
    )
    del spend_under
    return f"From the committed data: {cap_phrase}, and {spend_phrase}."


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


def _cells(effects: Sequence[float]) -> list[Cell]:
    return [
        Cell(round(p_p + d, 10), p_p, p_n)
        for p_p in BASELINES
        for p_n in BASELINES
        for d in effects
    ]


def stage2_grid() -> list[tuple[Cell, Design]]:
    """Full Stage 2 grid: stopping x pairs x null allocation x parameter variants."""
    jobs: list[tuple[Cell, Design]] = []
    for cell in _cells(EFFECTS):
        for n_pairs in PAIRS:
            for null_pp in NULL_PER_PAIR:
                for fn_con in FN_ANYTIME:
                    jobs.append(
                        (
                            cell,
                            Design(
                                n_pairs=n_pairs,
                                null_per_pair=null_pp,
                                fn_construction=fn_con,
                                stopping="anytime",
                                pass_alpha=PASS_ALPHA,
                                starting_wealth=1.0,
                            ),
                        )
                    )
                for w0 in STARTING_WEALTHS:
                    jobs.append(
                        (
                            cell,
                            Design(
                                n_pairs=n_pairs,
                                null_per_pair=null_pp,
                                fn_construction="direct",
                                stopping="anytime-tuned",
                                pass_alpha=PASS_ALPHA,
                                starting_wealth=w0,
                            ),
                        )
                    )
                for alpha in FIXED_PASS_ALPHAS:
                    for stopping in ("fixed-n-betting", "fixed-n-score"):
                        jobs.append(
                            (
                                cell,
                                Design(
                                    n_pairs=n_pairs,
                                    null_per_pair=null_pp,
                                    fn_construction="direct",
                                    stopping=stopping,
                                    pass_alpha=alpha,
                                    starting_wealth=1.0,
                                ),
                            )
                        )
    return jobs


def reduced_grid() -> list[tuple[Cell, Design]]:
    """Reduced grid for the test suite and the committed data run.

    Two pair counts, both null allocations, four effects spanning calibration
    and real-effect cells, all nine baseline cells, and every stopping design
    with its declared parameter variants.
    """
    jobs: list[tuple[Cell, Design]] = []
    for cell in _cells(REDUCED_EFFECTS):
        for n_pairs in REDUCED_PAIRS:
            for null_pp in REDUCED_NULL_PER_PAIR:
                for fn_con in FN_ANYTIME:
                    jobs.append(
                        (
                            cell,
                            Design(
                                n_pairs=n_pairs,
                                null_per_pair=null_pp,
                                fn_construction=fn_con,
                                stopping="anytime",
                                pass_alpha=PASS_ALPHA,
                                starting_wealth=1.0,
                            ),
                        )
                    )
                for w0 in STARTING_WEALTHS:
                    jobs.append(
                        (
                            cell,
                            Design(
                                n_pairs=n_pairs,
                                null_per_pair=null_pp,
                                fn_construction="direct",
                                stopping="anytime-tuned",
                                pass_alpha=PASS_ALPHA,
                                starting_wealth=w0,
                            ),
                        )
                    )
                for alpha in FIXED_PASS_ALPHAS:
                    for stopping in ("fixed-n-betting", "fixed-n-score"):
                        jobs.append(
                            (
                                cell,
                                Design(
                                    n_pairs=n_pairs,
                                    null_per_pair=null_pp,
                                    fn_construction="direct",
                                    stopping=stopping,
                                    pass_alpha=alpha,
                                    starting_wealth=1.0,
                                ),
                            )
                        )
    return jobs


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _design_cols(design: Design) -> str:
    return (
        f"{design.n_full}\t{design.n_placebo}\t{design.n_null}\t{design.total_epochs}"
        f"\t{design.null_per_pair:.2f}\t{design.fn_construction}\t{design.stopping}"
        f"\t{design.pass_alpha:.6f}\t{design.starting_wealth:.2f}"
    )


def _cell_cols(cell: Cell) -> str:
    return (
        f"{cell.p_full:.2f}\t{cell.p_placebo:.2f}\t{cell.p_null:.2f}\t{cell.d:.2f}\t{role(cell.d)}"
    )


def per_look_tsv(rows: Sequence[Row]) -> str:
    lines = [
        "\t".join(
            (
                *DESIGN_FIELDS,
                "p_full",
                "p_placebo",
                "p_null",
                "d",
                "role",
                "replicates",
                *_RATE_FIELDS,
                *_PRICE_FIELDS,
                "holds_level",
                "look",
            )
        )
    ]
    for row in rows:
        price = _price(row.design.total_epochs)
        look = row.per_look[-1] if row.per_look else None
        if look is None:
            look = _fixed_n_look_row(
                row.design,
                p_pass=row.p_joint_pass,
                p_cut=row.p_cut,
                replicates=row.replicates,
            )
        lines.append(
            f"{_design_cols(row.design)}\t{_cell_cols(row.cell)}\t{row.replicates}"
            f"\t{row.p_fp_half:.10f}\t{row.p_fn_half:.10f}\t{row.p_joint_pass:.10f}"
            f"\t{row.p_cut:.10f}\t{row.p_cant_tell_yet:.10f}\t{row.se_pass:.10f}"
            f"\t{look.expected_pairs:.10f}\t{look.expected_epochs:.10f}"
            f"\t{_expected_spend(look.expected_epochs)}\t{price}"
            f"\t{'yes' if row.holds_level else 'NO'}\t{look.look}"
        )
    return "\n".join(lines) + "\n"


def summary_md(rows: Sequence[Row], replicates: int, seed: int) -> str:
    headline = headline_rows(rows)
    lines = [
        "#718 Stage 2: stopping design x pairs under #685",
        "",
        f"Replicates per cell: {replicates}. Seed: {seed}.",
        f"Stoppings: {', '.join(STOPPINGS)}.",
        f"Pairs: {PAIRS}. Null per pair: {NULL_PER_PAIR}.",
        f"Fixed-n pass alphas: {FIXED_PASS_ALPHAS}. Starting wealths: {STARTING_WEALTHS}.",
        "CUT alpha 0.05 on every row. F - N construction: direct on every new design;",
        "union only on anytime rows.",
        "",
        "## Headline: smallest priced configuration meeting the diagonal target",
        "",
        "The diagonal target is the minimum over the three p_P = p_N cells of",
        "P(joint PASS) at d = 0.30 and of P(CUT) at d = 0.10, each at or above the",
        "target. Rows that fail calibration are excluded unless they are fixed-n-score",
        "rows, which are labelled as not holding their level. Configurations are",
        "ranked by total_epochs (the cap price), then by expected epochs.",
        "",
        "| stopping | pass_alpha | starting_wealth | target | smallest priced configuration "
        "| total_epochs | expected spend | cap price | P(PASS) at d=0.30 | P(CUT) at d=0.10 "
        "| missing half | holds level |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for h in headline:
        config = (
            f"{h.n_pairs} pairs, null_pp={h.null_per_pair:.2f}, {h.fn_construction}"
            if h.reached and h.n_pairs is not None
            else _NOT_REACHED
        )
        epochs = "-" if h.total_epochs is None else str(h.total_epochs)
        spend = h.expected_spend or "-"
        cap = h.cap_price or "-"
        min_pass = "-" if h.p_pass_at_d030 is None else f"{h.p_pass_at_d030:.4f}"
        min_cut = "-" if h.p_cut_at_d010 is None else f"{h.p_cut_at_d010:.4f}"
        missing = h.missing_half or "-"
        holds = "yes" if h.any_row_holds_level else "NO"
        lines.append(
            f"| {h.stopping} | {h.pass_alpha:.4f} | {h.starting_wealth:.2f} | {h.target:.2f} "
            f"| {config} | {epochs} | {spend} | {cap} | {min_pass} | {min_cut} "
            f"| {missing} | {holds} |"
        )
    lines += [
        "",
        headline_price_sentence(headline),
        "",
        "## Calibration read",
        "",
        "P(PASS) is an error wherever the true F-P or F-N is at or below 0.20,",
        "compared against the row's pass_alpha plus 3 MC SE. P(CUT) is an error",
        "wherever the true F-P is at or above 0.20, compared against 0.05 plus",
        "3 MC SE. A fixed-n-score row that fails calibration is labelled as not",
        "holding its level and left out of the headline; it does not fail the run.",
        "Every other design's failure does.",
        "",
    ]
    cal_failures = [r for r in rows if is_calibration_cell(r.cell) and not r.holds_level]
    labelled = [
        r
        for r in rows
        if is_calibration_cell(r.cell)
        and not r.holds_level
        and r.design.stopping == "fixed-n-score"
    ]
    fatal = [r for r in cal_failures if r.design.stopping != "fixed-n-score"]
    lines.append(f"Rows that fail calibration: {len(cal_failures)}.")
    lines.append(f"Fixed-n-score rows labelled not holding level: {len(labelled)}.")
    lines.append(f"Fatal calibration failures (non-score designs): {len(fatal)}.")
    if replicates < REPLICATES:
        lines += [
            "",
            "These smoke-run results establish only the output schema under the declared",
            "independent-Bernoulli model. They do not establish operating characteristics",
            "or how many real Claude Code epochs are required.",
        ]
    else:
        lines += [
            "",
            f"These results at {replicates} replicates per cell are simulations under the",
            "declared independent-Bernoulli model at the stated baselines and effect sizes.",
            "They establish the operating characteristics of each stopping design on that",
            "model grid at the declared pair counts. They do not establish how many real",
            "Claude Code epochs are required, and they do not speak to any subject model",
            "other than the independent-Bernoulli stand-in declared here.",
        ]
    lines += [
        "",
        "## Price lines",
        "",
        f"List rates ${_PRICE_LO:.3f} and ${_PRICE_HI:.3f} per epoch; cap rate ${_PRICE_CAP:.2f}.",
        "",
        "## Pairing statement",
        "",
        "Full and Placebo are paired by launch index; under independent draws",
        "this confers no matched-pairs advantage.",
        "",
        "## Crashed-look and void-epoch rules",
        "",
        "skill-harness #697 owns the crashed-look rule and the void-epoch rule",
        "for the next paid run; this record states neither.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Rebuild path
# ---------------------------------------------------------------------------

_RUN_META_NAME = "run_meta.json"


def _write_run_meta(out_dir: Path, *, replicates: int, seed: int) -> None:
    payload = {"replicates": replicates, "seed": seed}
    (out_dir / _RUN_META_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_run_meta(out_dir: Path) -> tuple[int, int] | None:
    path = out_dir / _RUN_META_NAME
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data["replicates"]), int(data["seed"])


def _design_from_row(cells: list[str], cols: dict[str, int]) -> Design:
    return Design(
        n_pairs=int(cells[cols["n_full"]]),
        null_per_pair=float(cells[cols["null_per_pair"]]),
        fn_construction=cells[cols["fn_construction"]],
        stopping=cells[cols["stopping"]],
        pass_alpha=float(cells[cols["pass_alpha"]]),
        starting_wealth=float(cells[cols["starting_wealth"]]),
    )


def _cell_from_row(cells: list[str], cols: dict[str, int]) -> Cell:
    return Cell(
        p_full=float(cells[cols["p_full"]]),
        p_placebo=float(cells[cols["p_placebo"]]),
        p_null=float(cells[cols["p_null"]]),
    )


def _result_key(design: Design, cell: Cell) -> tuple[object, ...]:
    return (
        design.n_pairs,
        design.null_per_pair,
        design.fn_construction,
        design.stopping,
        round(design.pass_alpha, 6),
        design.starting_wealth,
        cell.p_full,
        cell.p_placebo,
        cell.p_null,
    )


def rows_from_output_dir(out_dir: Path) -> tuple[list[Row], int]:
    """Rebuild Rows from a run's per_look.tsv. I/O only; aggregation is separate."""
    per_look_path = out_dir / "per_look.tsv"
    if not per_look_path.is_file():
        raise FileNotFoundError(f"missing {per_look_path}; rebuild needs a run's per_look.tsv")
    lines = per_look_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    cols = {name: idx for idx, name in enumerate(lines[0].split("\t"))}
    order: list[tuple[object, ...]] = []
    builders: dict[tuple[object, ...], dict[str, object]] = {}
    replicates_values: set[int] = set()
    for line in lines[1:]:
        cells = line.split("\t")
        design = _design_from_row(cells, cols)
        cell = _cell_from_row(cells, cols)
        key = _result_key(design, cell)
        reps = int(cells[cols["replicates"]])
        replicates_values.add(reps)
        if key not in builders:
            order.append(key)
            builders[key] = {
                "design": design,
                "cell": cell,
                "replicates": reps,
                "p_fp_half": float(cells[cols["p_fp_half"]]),
                "p_fn_half": float(cells[cols["p_fn_half"]]),
                "p_joint_pass": float(cells[cols["p_joint_pass"]]),
                "p_cut": float(cells[cols["p_cut"]]),
                "p_cant_tell_yet": float(cells[cols["p_cant_tell_yet"]]),
                "se_pass": float(cells[cols["se_pass"]]),
                "expected_pairs": float(cells[cols["expected_pairs"]]),
                "expected_epochs": float(cells[cols["expected_epochs"]]),
                "holds": cells[cols["holds_level"]] == "yes",
                "look": int(cells[cols["look"]]),
            }
    if len(replicates_values) != 1:
        raise ValueError(f"per_look.tsv disagrees on replicates: {sorted(replicates_values)}")
    replicates = replicates_values.pop()
    rows: list[Row] = []
    for key in order:
        b = builders[key]
        design = b["design"]  # type: ignore[assignment]
        cell = b["cell"]  # type: ignore[assignment]
        p_joint = float(b["p_joint_pass"])  # type: ignore[arg-type]
        p_cut = float(b["p_cut"])  # type: ignore[arg-type]
        look = s685.LookRow(
            look=int(b["look"]),  # type: ignore[arg-type]
            p_pass=p_joint,
            p_cut=p_cut,
            p_cant_tell_yet=max(0.0, 1.0 - p_joint - p_cut),
            se_pass=float(b["se_pass"]),  # type: ignore[arg-type]
            expected_pairs=float(b["expected_pairs"]),  # type: ignore[arg-type]
            expected_epochs=float(b["expected_epochs"]),  # type: ignore[arg-type]
        )
        rows.append(
            Row(
                cell=cell,  # type: ignore[arg-type]
                design=design,  # type: ignore[arg-type]
                replicates=int(b["replicates"]),  # type: ignore[arg-type]
                p_fp_half=float(b["p_fp_half"]),  # type: ignore[arg-type]
                p_fn_half=float(b["p_fn_half"]),  # type: ignore[arg-type]
                p_joint_pass=p_joint,
                p_cut=p_cut,
                p_cant_tell_yet=float(b["p_cant_tell_yet"]),  # type: ignore[arg-type]
                se_pass=float(b["se_pass"]),  # type: ignore[arg-type]
                expected_pairs=float(b["expected_pairs"]),  # type: ignore[arg-type]
                expected_epochs=float(b["expected_epochs"]),  # type: ignore[arg-type]
                holds_level=bool(b["holds"]),  # type: ignore[arg-type]
                per_look=(look,),
            )
        )
    return rows, replicates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _run(job: tuple[Cell, Design, int, int]) -> Row:
    cell, design, replicates, seed = job
    row = run_cell(cell, design, replicates=replicates, seed=seed)
    print(
        f"({cell.d:.2f}, {cell.p_placebo:.2f}, {cell.p_null:.2f}) "
        f"n={design.n_pairs} null_pp={design.null_per_pair:.2f} "
        f"{design.stopping} {design.fn_construction} alpha={design.pass_alpha:.4f} "
        f"w0={design.starting_wealth:.2f} done",
        flush=True,
    )
    return row


def main(
    argv: Sequence[str] | None = None,
    *,
    grid: Sequence[tuple[Cell, Design]] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--replicates", type=int, default=REPLICATES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    ap.add_argument(
        "--reduced",
        action="store_true",
        help="run the reduced grid instead of the full Stage 2 grid",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "rebuild summary.md and the calibration exit code from an existing "
            "output directory (per_look.tsv) without simulation"
        ),
    )
    args = ap.parse_args(argv)
    if args.rebuild:
        rows, replicates = rows_from_output_dir(args.out)
        meta = _read_run_meta(args.out)
        seed = args.seed if meta is None else meta[1]
        if meta is not None:
            replicates = meta[0]
        summary = summary_md(rows, replicates, seed)
        (args.out / "summary.md").write_text(summary, encoding="utf-8")
        print(summary)
        return calibration_exit_code(rows)

    args.out.mkdir(parents=True, exist_ok=True)
    chosen = stage2_grid() if grid is None and not args.reduced else grid
    if chosen is None:
        chosen = reduced_grid() if args.reduced else stage2_grid()
    jobs = [(cell, design, args.replicates, args.seed) for cell, design in chosen]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_run, jobs))
    (args.out / "per_look.tsv").write_text(per_look_tsv(rows), encoding="utf-8")
    _write_run_meta(args.out, replicates=args.replicates, seed=args.seed)
    summary = summary_md(rows, args.replicates, args.seed)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    cal = [r for r in rows if is_calibration_cell(r.cell)]
    failures = [r for r in cal if not r.holds_level]
    for r in failures:
        dsg = r.design
        c = r.cell
        print(
            f"CALIBRATION FAILURE: n={dsg.n_pairs} null_pp={dsg.null_per_pair:.2f} "
            f"{dsg.stopping} {dsg.fn_construction} alpha={dsg.pass_alpha:.4f} "
            f"w0={dsg.starting_wealth:.2f} p_P={c.p_placebo:.2f} p_N={c.p_null:.2f} "
            f"d={c.d:.2f} p_joint={r.p_joint_pass:.5f} p_cut={r.p_cut:.5f} "
            f"holds_level={'yes' if r.holds_level else 'NO'} "
            f"labelled_not_holding_level={is_nonfatal_calibration_failure(r)}"
        )
    return calibration_exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
