"""#685: lever adjudication for the registered Stage 1A rule.

Varies each of four design levers against the #684 baseline (97 pairs, 1:1:1),
then combines. No model calls, no network, no spend.

Levers:
  1. Pairs (cap at 400).
  2. Null allocation at fixed total-epoch budgets (null_per_pair in {0.5, 1, 2}).
  3. F - N construction (registered union bound vs direct one-sided bound).
  4. Optional stopping (anytime-valid vs fixed-n look).

Stage 1 (this script): levers 2 and 3 at 300- and 1,200-epoch budgets.
Stage 2 (pairs and optional stopping) is not implemented here.

Usage:
  python scripts/screens/419/simulate_stage1a_regime_685.py --out DIR \
         [--replicates 2000] [--seed 685] [--workers N]
"""

from __future__ import annotations

import argparse
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

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

BASELINES = (0.30, 0.35, 0.40)
EFFECTS = (0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
POWER_TARGETS = (0.80, 0.90)
REPLICATES = 2_000
SEED = 685
PAIRS_CAP = 400
EPOCH_BUDGETS = (300, PAIRS_CAP * 3)
NULL_PER_PAIR_LEVELS = (0.5, 1.0, 2.0)
FN_CONSTRUCTIONS = ("union", "direct")

JointState = Literal["fp_passes_fn_fails", "fn_passes_fp_fails", "neither_passes", "both_pass"]
JOINT_STATES: tuple[JointState, ...] = (
    "fp_passes_fn_fails",
    "fn_passes_fp_fails",
    "neither_passes",
    "both_pass",
)


# ---------------------------------------------------------------------------
# Design and cell
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Design:
    n_pairs: int
    null_per_pair: float = 1.0
    fn_construction: str = "union"
    stopping: str = "anytime"

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
class LookRow:
    look: int
    p_pass: float
    p_cut: float
    p_cant_tell_yet: float
    se_pass: float
    expected_pairs: float
    expected_epochs: float


@dataclass(frozen=True)
class TerminalSample:
    lb_fp: tuple[float, ...]
    lb_fn: tuple[float, ...]
    ub_fp: tuple[float, ...]


@dataclass(frozen=True)
class CellResult:
    cell: Cell
    design: Design
    replicates: int
    per_look: tuple[LookRow, ...]
    terminal: dict[JointState, TerminalSample]
    library_calls: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def role(d: float) -> str:
    if math.isclose(d, a650.BOUNDARY, abs_tol=1e-9):
        return "calibration"
    if d <= 0.15:
        return "no-lift"
    if math.isclose(d, 0.25, abs_tol=1e-9):
        return "small real effect"
    return "real effect"


def smallest_d_reaching(curve: dict[float, float], target: float) -> float | None:
    return next((d for d in sorted(curve) if curve[d] >= target), None)


def headline(
    results: Sequence[CellResult], target: float
) -> dict[tuple[str, float, float], float | None]:
    """Per (fn_construction, p_P, p_N), smallest d whose P(PASS) at the cap reaches target.

    Reads the design fields off each result: only rows at ``PAIRS_CAP`` with
    ``null_per_pair == 1.0`` enter the curve, so a result set that carries no
    such row yields ``None`` rather than a stale pair count.
    """
    out: dict[tuple[str, float, float], float | None] = {}
    for fn_con in FN_CONSTRUCTIONS:
        for p_p in BASELINES:
            for p_n in BASELINES:
                curve = {
                    r.cell.d: r.per_look[-1].p_pass
                    for r in results
                    if (
                        r.design.fn_construction == fn_con
                        and r.design.n_pairs == PAIRS_CAP
                        and r.design.null_per_pair == 1.0
                        and (r.cell.p_placebo, r.cell.p_null) == (p_p, p_n)
                    )
                }
                out[(fn_con, p_p, p_n)] = smallest_d_reaching(curve, target)
    return out


@dataclass(frozen=True)
class TargetCheckRow:
    """One design family at one target: the smallest priced configuration meeting both halves."""

    target: float
    null_per_pair: float
    fn_construction: str
    reached: bool
    total_epochs: int | None
    n_pairs: int | None
    expected_spend: str | None
    p_pass_at_d030: float | None
    p_cut_at_d010: float | None
    missing_half: str
    trigger_fires: bool


_TARGET_HALF_ONE = "P(PASS) >= target at d = 0.30"
_TARGET_HALF_TWO = "P(CUT) >= target at d = 0.10"


def _design_family_meets_target(
    results: Sequence[CellResult],
    *,
    null_per_pair: float,
    fn_construction: str,
    epoch_budget: int,
    target: float,
) -> tuple[bool, float | None, float | None, str]:
    """Does this design family at this budget meet both halves, across every baseline?

    Returns (meets, min_p_pass_at_0_30, min_p_cut_at_0_10, missing_half).
    Both halves must hold in all nine (p_P, p_N) baseline cells.
    """
    pass_vals: list[float] = []
    cut_vals: list[float] = []
    for p_p in BASELINES:
        for p_n in BASELINES:
            pass_row = next(
                (
                    r
                    for r in results
                    if r.design.null_per_pair == null_per_pair
                    and r.design.fn_construction == fn_construction
                    and r.design.total_epochs == epoch_budget
                    and math.isclose(r.cell.d, 0.30, abs_tol=1e-9)
                    and math.isclose(r.cell.p_placebo, p_p, abs_tol=1e-9)
                    and math.isclose(r.cell.p_null, p_n, abs_tol=1e-9)
                ),
                None,
            )
            cut_row = next(
                (
                    r
                    for r in results
                    if r.design.null_per_pair == null_per_pair
                    and r.design.fn_construction == fn_construction
                    and r.design.total_epochs == epoch_budget
                    and math.isclose(r.cell.d, 0.10, abs_tol=1e-9)
                    and math.isclose(r.cell.p_placebo, p_p, abs_tol=1e-9)
                    and math.isclose(r.cell.p_null, p_n, abs_tol=1e-9)
                ),
                None,
            )
            if pass_row is None or cut_row is None:
                return False, None, None, f"missing d=0.30/d=0.10 cells for ({p_p}, {p_n})"
            pass_vals.append(pass_row.per_look[-1].p_pass)
            cut_vals.append(cut_row.per_look[-1].p_cut)
    min_pass = min(pass_vals)
    min_cut = min(cut_vals)
    missing: list[str] = []
    if min_pass < target:
        missing.append(_TARGET_HALF_ONE)
    if min_cut < target:
        missing.append(_TARGET_HALF_TWO)
    if missing:
        return False, min_pass, min_cut, " and ".join(missing)
    return True, min_pass, min_cut, ""


def target_check_rows(results: Sequence[CellResult]) -> tuple[TargetCheckRow, ...]:
    """Smallest priced configuration per design family per target, from data only.

    Both halves of the #685 target: P(PASS) >= target at d = 0.30 and
    P(CUT) >= target at d = 0.10, each required in all nine baseline cells.
    Configurations are the declared epoch budgets, ranked by total_epochs
    (the cap price). A design family that meets both halves at a budget
    reports that budget as its smallest priced configuration. The stage-2
    trigger for a target fires when no design family reaches that target.
    """
    families = sorted(
        {(r.design.null_per_pair, r.design.fn_construction) for r in results},
        key=lambda t: (t[1], t[0]),
    )
    budgets = sorted({r.design.total_epochs for r in results})
    rows: list[TargetCheckRow] = []
    reached_any: dict[float, bool] = {target: False for target in POWER_TARGETS}
    staged: dict[tuple[float, float, str], TargetCheckRow] = {}
    for target in POWER_TARGETS:
        for null_pp, fn_con in families:
            chosen: TargetCheckRow | None = None
            missing = "no configuration on this grid"
            min_pass: float | None = None
            min_cut: float | None = None
            for budget in budgets:
                meets, mp, mc, missing_half = _design_family_meets_target(
                    results,
                    null_per_pair=null_pp,
                    fn_construction=fn_con,
                    epoch_budget=budget,
                    target=target,
                )
                min_pass, min_cut = mp, mc
                missing = missing_half
                if meets:
                    sample = next(
                        r
                        for r in results
                        if r.design.null_per_pair == null_pp
                        and r.design.fn_construction == fn_con
                        and r.design.total_epochs == budget
                    )
                    chosen = TargetCheckRow(
                        target=target,
                        null_per_pair=null_pp,
                        fn_construction=fn_con,
                        reached=True,
                        total_epochs=budget,
                        n_pairs=sample.design.n_pairs,
                        expected_spend=_expected_spend(sample.per_look[-1].expected_epochs),
                        p_pass_at_d030=mp,
                        p_cut_at_d010=mc,
                        missing_half="",
                        trigger_fires=False,
                    )
                    reached_any[target] = True
                    break
            if chosen is None:
                chosen = TargetCheckRow(
                    target=target,
                    null_per_pair=null_pp,
                    fn_construction=fn_con,
                    reached=False,
                    total_epochs=None,
                    n_pairs=None,
                    expected_spend=None,
                    p_pass_at_d030=min_pass,
                    p_cut_at_d010=min_cut,
                    missing_half=missing,
                    trigger_fires=True,
                )
            staged[(target, null_pp, fn_con)] = chosen
    for target in POWER_TARGETS:
        fires = not reached_any[target]
        for (t, _null_pp, _fn_con), row in staged.items():
            if t != target:
                continue
            rows.append(
                TargetCheckRow(
                    target=row.target,
                    null_per_pair=row.null_per_pair,
                    fn_construction=row.fn_construction,
                    reached=row.reached,
                    total_epochs=row.total_epochs,
                    n_pairs=row.n_pairs,
                    expected_spend=row.expected_spend,
                    p_pass_at_d030=row.p_pass_at_d030,
                    p_cut_at_d010=row.p_cut_at_d010,
                    missing_half=row.missing_half,
                    trigger_fires=fires,
                )
            )
    return tuple(rows)


def stage2_trigger_fires(rows: Sequence[TargetCheckRow], target: float) -> bool:
    """Stage 2 is gated on Stage 1 leaving the target unmet (#685 lever split)."""
    relevant = [r for r in rows if r.target == target]
    if not relevant:
        return True
    return not any(r.reached for r in relevant)


def cell_rng(seed: int, cell: Cell) -> np.random.Generator:
    return np.random.default_rng(
        [seed, round(cell.p_full * 1000), round(cell.p_placebo * 1000), round(cell.p_null * 1000)]
    )


def calibration_holds(res: CellResult) -> bool:
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(res.replicates)
    return res.per_look[-1].p_pass <= limit


def calibration_holds_direct(res: CellResult, alpha: float) -> bool:
    limit = alpha + a650.calibration_tolerance(res.replicates, alpha)
    return res.per_look[-1].p_pass <= limit


def _bound(xs: a650.Floats, alpha: float, side: a650.Side) -> a650.Floats:
    """Vectorised one_sided_betting_bound, reusing the #684 grid machinery."""
    replicates, n = xs.shape
    grid = a650.WealthGrid(replicates, alpha, 1)
    for k in range(n):
        grid.step(xs[:, k])
    br = a650.bracket(grid, side, "one_sided")
    edge = 0.0 if side == "lower" else 1.0
    vacuous = (br.lo == edge) & (br.hi == edge)
    idle = vacuous | br.unsure
    outside = np.where(idle, 0.5, br.lo if side == "lower" else br.hi)
    inside = np.where(idle, 0.5, br.hi if side == "lower" else br.lo)
    targets = _plug_in_targets(xs, alpha)
    threshold = math.log(1.0 / alpha)
    for _ in range(64):
        mid = 0.5 * (outside + inside)
        rejected = _branch_log_wealth(xs, targets, mid, side) >= threshold
        outside = np.where(rejected, mid, outside)
        inside = np.where(rejected, inside, mid)
    out = np.where(vacuous, edge, inside)
    for r in np.flatnonzero(br.unsure).tolist():
        out[r] = one_sided_betting_bound(xs[r].tolist(), alpha=alpha, side=side)
    return out


def _plug_in_targets(xs: a650.Floats, alpha: float) -> a650.Floats:
    from skill_harness.aggregation import confidence_sequence as cs_mod

    replicates, n = xs.shape
    numer = 2.0 * math.log(1.0 / alpha)
    mean_hat = np.full(replicates, cs_mod._MEAN_PRIOR)
    var_hat = np.full(replicates, cs_mod._VAR_PRIOR)
    targets = np.empty((replicates, n))
    for k in range(n):
        t = float(k + 1)
        targets[:, k] = np.sqrt(numer / (np.maximum(var_hat, 1e-6) * t * math.log(1.0 + t)))
        x = xs[:, k]
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1)
        var_hat = np.maximum(var_hat + (resid * resid - var_hat) / (t + 1), 1e-6)
    return targets


def _branch_log_wealth(
    xs: a650.Floats, targets: a650.Floats, mu: a650.Floats, side: a650.Side
) -> a650.Floats:
    from skill_harness.aggregation import confidence_sequence as cs_mod

    lw = np.zeros(xs.shape[0])
    if side == "lower":
        cap = cs_mod._TRUNC_C / mu
        for k in range(xs.shape[1]):
            lw += np.log(1.0 + np.minimum(cap, targets[:, k]) * (xs[:, k] - mu))
    else:
        cap = cs_mod._TRUNC_C / (1.0 - mu)
        for k in range(xs.shape[1]):
            lw += np.log(1.0 - np.minimum(cap, targets[:, k]) * (xs[:, k] - mu))
    return lw


# ---------------------------------------------------------------------------
# Null allocation
# ---------------------------------------------------------------------------


def null_mask(n_pairs: int, null_per_pair: float) -> list[bool]:
    """Which pairs receive a Null draw under the stated allocation.

    null_per_pair = 1.0: every pair gets one Null draw.
    null_per_pair = 0.5: strictly alternating, Null-A after pair k iff k is
        even (k = 2, 4, ..., n_pairs - 1 when n_pairs is odd).
    null_per_pair = 2.0: every pair gets two Null draws (both used).
    """
    if null_per_pair == 1.0:
        return [True] * n_pairs
    if null_per_pair == 0.5:
        return [k % 2 == 1 for k in range(n_pairs)]
    if null_per_pair == 2.0:
        return [True] * n_pairs
    raise ValueError(f"unsupported null_per_pair: {null_per_pair}")


def null_draw_counts(n_pairs: int, null_per_pair: float) -> a650.Ints:
    """Number of actual Null epochs after each Full/Placebo pair."""
    draws_when_scheduled = 1 if null_per_pair <= 1.0 else 2
    return np.array(
        [
            0 if not scheduled else draws_when_scheduled
            for scheduled in null_mask(n_pairs, null_per_pair)
        ],
        dtype=np.int64,
    )


# ---------------------------------------------------------------------------
# Simulation core
# ---------------------------------------------------------------------------


QUANTILES = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)


def per_look_rows(
    stop_at: a650.Ints,
    passed: a650.Bools,
    cut: a650.Bools,
    n_pairs: int,
    epochs_profile: a650.Floats,
) -> tuple[LookRow, ...]:
    reps = len(stop_at)
    rows = []
    for k in range(1, n_pairs + 1):
        stopped = stop_at <= k
        p_pass = float(np.mean(stopped & passed))
        p_cut = float(np.mean(stopped & cut))
        used = np.minimum(stop_at, k)
        rows.append(
            LookRow(
                look=k,
                p_pass=p_pass,
                p_cut=p_cut,
                p_cant_tell_yet=1.0 - p_pass - p_cut,
                se_pass=math.sqrt(p_pass * (1.0 - p_pass) / reps),
                expected_pairs=float(np.mean(used)),
                expected_epochs=float(np.mean(epochs_profile[used])),
            )
        )
    return tuple(rows)


def _joint_state(lb_fp: float, lb_fn: float) -> JointState:
    fp = lb_fp >= a650.BOUNDARY
    fn = lb_fn >= a650.BOUNDARY
    if fp and fn:
        return "both_pass"
    if fp:
        return "fp_passes_fn_fails"
    if fn:
        return "fn_passes_fp_fails"
    return "neither_passes"


def _terminal_bounds_union(
    full: a650.Ints, placebo: a650.Ints, null_used: a650.Ints, pass_alpha: float
) -> tuple[a650.Floats, a650.Floats, a650.Floats]:
    """Union-bound terminal bounds: registered construction."""
    xs_fp = (full - placebo + 1) / 2.0
    half = pass_alpha / 2
    lb_fp = 2 * _bound(xs_fp, pass_alpha, "lower") - 1
    ub_fp = 2 * _bound(xs_fp, a650.FUTILITY_ALPHA, "upper") - 1
    lb_fn = _bound(full.astype(np.float64), half, "lower") - _bound(
        null_used.astype(np.float64), half, "upper"
    )
    return lb_fp, ub_fp, lb_fn


def _terminal_bounds_direct(
    full: a650.Ints, placebo: a650.Ints, xs_fn: a650.Floats, pass_alpha: float
) -> tuple[a650.Floats, a650.Floats, a650.Floats]:
    """Direct one-sided bound on mu_F - mu_N at alpha."""
    xs_fp = (full - placebo + 1) / 2.0
    lb_fp = 2 * _bound(xs_fp, pass_alpha, "lower") - 1
    ub_fp = 2 * _bound(xs_fp, a650.FUTILITY_ALPHA, "upper") - 1
    lb_fn = 2 * _bound(xs_fn, pass_alpha, "lower") - 1
    return lb_fp, ub_fp, lb_fn


def tally_terminal(
    full: a650.Ints,
    placebo: a650.Ints,
    null_used: a650.Ints,
    xs_fn: a650.Floats,
    fn_construction: str,
    pass_alpha: float,
) -> dict[JointState, TerminalSample]:
    if fn_construction == "direct":
        lb_fp, ub_fp, lb_fn = _terminal_bounds_direct(full, placebo, xs_fn, pass_alpha)
    else:
        lb_fp, ub_fp, lb_fn = _terminal_bounds_union(full, placebo, null_used, pass_alpha)
    if bool(np.any(ub_fp < a650.BOUNDARY)):
        raise RuntimeError("an open replicate has UB(F - P) < 0.20")
    states = [_joint_state(float(f), float(n)) for f, n in zip(lb_fp, lb_fn, strict=True)]
    out: dict[JointState, TerminalSample] = {}
    for state in JOINT_STATES:
        idx = [i for i, s in enumerate(states) if s == state]
        out[state] = TerminalSample(
            lb_fp=tuple(float(lb_fp[i]) for i in idx),
            lb_fn=tuple(float(lb_fn[i]) for i in idx),
            ub_fp=tuple(float(ub_fp[i]) for i in idx),
        )
    return out


def _quantiles(values: Sequence[float]) -> list[str]:
    if not values:
        return ["NA" for _ in QUANTILES]
    return [f"{float(q):.4f}" for q in np.quantile(np.asarray(values), QUANTILES)]


def run_cell(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    pass_alpha: float = a650.PASS_ALPHA,
) -> CellResult:
    """Run one cell: draw streams, apply the rule, record per-look and terminal.

    Supports variable null allocation and union/direct F-N construction.
    """
    horizon = design.n_pairs
    rng = cell_rng(seed, cell)
    full = (rng.random((replicates, horizon)) < cell.p_full).astype(np.int64)
    placebo = (rng.random((replicates, horizon)) < cell.p_placebo).astype(np.int64)
    null_all = (rng.random((replicates, horizon, 2)) < cell.p_null).astype(np.int64)
    null_draws = null_draw_counts(horizon, design.null_per_pair)
    null_counts = np.cumsum(null_draws)
    fn_mask = null_draws > 0
    fn_counts = np.cumsum(fn_mask)
    scheduled_nulls = [(k, count) for k, count in enumerate(null_draws) if count]
    if scheduled_nulls:
        null_used = np.concatenate([null_all[:, k, :count] for k, count in scheduled_nulls], axis=1)
        null_mean = np.array(
            [null_all[:, k, :count].mean(axis=1) for k, count in scheduled_nulls]
        ).T
    else:
        null_used = np.empty((replicates, 0), dtype=np.int64)
        null_mean = np.empty((replicates, 0), dtype=np.float64)
    xs_fn_all = (full[:, fn_mask] - null_mean + 1) / 2.0

    half = pass_alpha / 2

    # --- Anytime-valid rule ---
    fp_fut = a650.WealthGrid(replicates, a650.FUTILITY_ALPHA, 1)
    fp_pass = a650.WealthGrid(replicates, pass_alpha, 1)
    f_pass = a650.WealthGrid(replicates, half, 1)
    n_pass = a650.WealthGrid(replicates, half, 1)
    if design.fn_construction == "direct":
        fn_diff = a650.WealthGrid(replicates, pass_alpha, 1)

    xs_fp_all = (full - placebo + 1) / 2.0
    xs_f_all = full.astype(np.float64)

    stop_at = np.full(replicates, horizon + 1, dtype=np.int64)
    passed = np.zeros(replicates, dtype=np.bool_)
    cut = np.zeros(replicates, dtype=np.bool_)
    calls = 0

    for k in range(horizon):
        fp_fut.step(xs_fp_all[:, k])
        fp_pass.step(xs_fp_all[:, k])
        f_pass.step(xs_f_all[:, k])
        for null_draw in range(null_draws[k]):
            n_pass.step(null_all[:, k, null_draw].astype(np.float64))
        if design.fn_construction == "direct" and fn_mask[k]:
            fn_diff.step(xs_fn_all[:, fn_counts[k] - 1])

        ub = a650.bracket(fp_fut, "upper", "one_sided")
        lb = a650.bracket(fp_pass, "lower", "one_sided")

        if design.fn_construction == "direct":
            lb_fn_br = a650.bracket(fn_diff, "lower", "one_sided")
        else:
            lb_f_br = a650.bracket(f_pass, "lower", "one_sided")
            ub_n_br = a650.bracket(n_pass, "upper", "one_sided")

        for r in np.flatnonzero(stop_at > horizon).tolist():
            xs_fp = xs_fp_all[r, : k + 1].tolist()
            xs_f = xs_f_all[r, : k + 1].tolist()
            xs_n = null_used[r, : null_counts[k]].astype(np.float64).tolist()
            used = 0

            def _exact(xs: list[float], alpha: float, side: a650.Side) -> float:
                nonlocal used
                used += 1
                return float(a650.one_sided_betting_bound(xs, alpha=alpha, side=side))

            # CUT check
            if ub.unsure[r] or not (
                2 * ub.hi[r] - 1 < a650.BOUNDARY or 2 * ub.lo[r] - 1 >= a650.BOUNDARY
            ):
                cut_now = 2 * _exact(xs_fp, a650.FUTILITY_ALPHA, "upper") - 1 < a650.BOUNDARY
            else:
                cut_now = bool(2 * ub.hi[r] - 1 < a650.BOUNDARY)
            if cut_now:
                stop_at[r] = k + 1
                cut[r] = True
                calls += used
                continue

            # F-P pass check
            if lb.unsure[r] or not (
                2 * lb.lo[r] - 1 >= a650.BOUNDARY or 2 * lb.hi[r] - 1 < a650.BOUNDARY
            ):
                fp_clears = 2 * _exact(xs_fp, pass_alpha, "lower") - 1 >= a650.BOUNDARY
            else:
                fp_clears = bool(2 * lb.lo[r] - 1 >= a650.BOUNDARY)
            if not fp_clears:
                calls += used
                continue

            # F-N pass check
            if design.fn_construction == "direct":
                fn_sure_yes = 2 * lb_fn_br.lo[r] - 1 >= a650.BOUNDARY
                fn_sure_no = 2 * lb_fn_br.hi[r] - 1 < a650.BOUNDARY
                if lb_fn_br.unsure[r] or not (fn_sure_yes or fn_sure_no):
                    xs_fn = xs_fn_all[r, : fn_counts[k]].tolist()
                    fn_clears = 2 * _exact(xs_fn, pass_alpha, "lower") - 1 >= a650.BOUNDARY
                else:
                    fn_clears = bool(fn_sure_yes)
            else:
                f_sure_yes = lb_f_br.lo[r] - ub_n_br.hi[r] >= a650.BOUNDARY
                f_sure_no = lb_f_br.hi[r] - ub_n_br.lo[r] < a650.BOUNDARY
                if lb_f_br.unsure[r] or ub_n_br.unsure[r] or not (f_sure_yes or f_sure_no):
                    fn_clears = (
                        _exact(xs_f, half, "lower") - _exact(xs_n, half, "upper") >= a650.BOUNDARY
                    )
                else:
                    fn_clears = bool(f_sure_yes)

            if fn_clears:
                stop_at[r] = k + 1
                passed[r] = True
            calls += used

    unresolved = stop_at > horizon
    unresolved_full = full[unresolved]
    unresolved_placebo = placebo[unresolved]
    unresolved_null = null_used[unresolved]
    unresolved_fn = xs_fn_all[unresolved]

    null_cum = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(null_draws)))
    epochs_profile = (2.0 * np.arange(horizon + 1) + null_cum).astype(np.float64)

    return CellResult(
        cell=cell,
        design=design,
        replicates=replicates,
        per_look=per_look_rows(stop_at, passed, cut, horizon, epochs_profile),
        terminal=tally_terminal(
            unresolved_full,
            unresolved_placebo,
            unresolved_null,
            unresolved_fn,
            design.fn_construction,
            pass_alpha,
        ),
        library_calls=calls,
    )


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


def pairs_for_epoch_budget(epoch_budget: int, null_per_pair: float) -> int:
    """Return the integral Full/Placebo-pair count that spends ``epoch_budget`` exactly."""
    pair_half_epochs = int(2 * (2 + null_per_pair))
    budget_half_epochs = 2 * epoch_budget
    if budget_half_epochs % pair_half_epochs:
        raise ValueError(
            f"epoch budget {epoch_budget} cannot be divided across {null_per_pair} Nulls per pair"
        )
    return budget_half_epochs // pair_half_epochs


def stage1_grid() -> list[tuple[Cell, Design]]:
    """Stage 1: null allocation x F-N construction at fixed epoch budgets."""
    jobs: list[tuple[Cell, Design]] = []
    for p_p in BASELINES:
        for p_n in BASELINES:
            for d in EFFECTS:
                cell = Cell(round(p_p + d, 10), p_p, p_n)
                for epoch_budget in EPOCH_BUDGETS:
                    for null_pp in NULL_PER_PAIR_LEVELS:
                        for fn_con in FN_CONSTRUCTIONS:
                            design = Design(
                                n_pairs=pairs_for_epoch_budget(epoch_budget, null_pp),
                                null_per_pair=null_pp,
                                fn_construction=fn_con,
                            )
                            jobs.append((cell, design))
    return jobs


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_DESIGN_HEADER = "n_full\tn_placebo\tn_null\ttotal_epochs\tnull_per_pair\tfn_construction\tstopping"
_CELL_HEADER = "p_full\tp_placebo\tp_null\td\trole"
_NOT_REACHED = "not reached on this grid"
_PRICE_LO = 0.083
_PRICE_HI = 0.087
_PRICE_CAP = 0.30


def _design_cols(design: Design) -> str:
    return (
        f"{design.n_full}\t{design.n_placebo}\t{design.n_null}\t{design.total_epochs}"
        f"\t{design.null_per_pair:.2f}\t{design.fn_construction}\t{design.stopping}"
    )


def _cell_cols(cell: Cell) -> str:
    return (
        f"{cell.p_full:.2f}\t{cell.p_placebo:.2f}\t{cell.p_null:.2f}\t{cell.d:.2f}\t{role(cell.d)}"
    )


def _price(total_epochs: int) -> str:
    lo = total_epochs * _PRICE_LO
    hi = total_epochs * _PRICE_HI
    cap = total_epochs * _PRICE_CAP
    return f"${lo:.2f}-${hi:.2f} (cap ${cap:.2f})"


def _expected_spend(expected_epochs: float) -> str:
    lo = expected_epochs * _PRICE_LO
    hi = expected_epochs * _PRICE_HI
    return f"${lo:.2f}-${hi:.2f}"


def per_look_tsv(results: Sequence[CellResult]) -> str:
    lines = [
        f"{_DESIGN_HEADER}\t{_CELL_HEADER}\treplicates\tlook\tp_pass\tp_cut"
        "\tp_cant_tell_yet\tse_pass\texpected_pairs\texpected_epochs"
        "\texpected_spend\tprice_range"
    ]
    for res in results:
        price = _price(res.design.total_epochs)
        lines += [
            f"{_design_cols(res.design)}\t{_cell_cols(res.cell)}\t{res.replicates}\t{row.look}"
            f"\t{row.p_pass:.5f}\t{row.p_cut:.5f}\t{row.p_cant_tell_yet:.5f}\t{row.se_pass:.5f}"
            f"\t{row.expected_pairs:.3f}\t{row.expected_epochs:.3f}"
            f"\t{_expected_spend(row.expected_epochs)}\t{price}"
            for row in res.per_look
        ]
    return "\n".join(lines) + "\n"


def terminal_tsv(results: Sequence[CellResult]) -> str:
    qnames = [f"q{round(q * 100):02d}" for q in QUANTILES]
    stat_cols = "\t".join(f"{name}_{q}" for name in ("lb_fp", "lb_fn", "ub_fp") for q in qnames)
    lines = [
        f"{_DESIGN_HEADER}\t{_CELL_HEADER}\treplicates\tjoint_state\tcount\tshare\tse_share"
        f"\texpected_epochs\texpected_spend\tprice_range\t{stat_cols}"
    ]
    for res in results:
        price = _price(res.design.total_epochs)
        expected_epochs = res.per_look[-1].expected_epochs
        spend = _expected_spend(expected_epochs)
        for state in JOINT_STATES:
            t = res.terminal[state]
            share = len(t.lb_fp) / res.replicates
            se_share = math.sqrt(share * (1.0 - share) / res.replicates)
            stats = [*_quantiles(t.lb_fp), *_quantiles(t.lb_fn), *_quantiles(t.ub_fp)]
            lines.append(
                f"{_design_cols(res.design)}\t{_cell_cols(res.cell)}\t{res.replicates}\t{state}"
                f"\t{len(t.lb_fp)}\t{share:.8f}\t{se_share:.8f}\t{expected_epochs:.3f}"
                f"\t{spend}\t{price}\t" + "\t".join(stats)
            )
    return "\n".join(lines) + "\n"


def _surface_lines(results: Sequence[CellResult]) -> list[str]:
    lines = [
        "| n_pairs | null_pp | fn_con | p_P | p_N | d | role | p_F | P(PASS) "
        "| SE | P(CUT) | P(CANT) | E[pairs] | cal | E[epochs] | expected spend | price |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- "
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        c, row = res.cell, res.per_look[-1]
        d_result = res.design
        r = role(c.d)
        if r == "calibration":
            holds = "yes" if calibration_holds(res) else "NO"
        elif r == "no-lift":
            holds = f"P(CUT)={row.p_cut:.4f}"
        else:
            holds = ""
        lines.append(
            f"| {d_result.n_pairs} | {d_result.null_per_pair:.2f} | {d_result.fn_construction} "
            f"| {c.p_placebo:.2f} | {c.p_null:.2f} | {c.d:.2f} | {r} | {c.p_full:.2f} | "
            f"{row.p_pass:.4f} | {row.se_pass:.4f} | {row.p_cut:.4f} | "
            f"{row.p_cant_tell_yet:.4f} | {row.expected_pairs:.1f} | {holds} | "
            f"{row.expected_epochs:.1f} | {_expected_spend(row.expected_epochs)} | "
            f"{_price(d_result.total_epochs)} |"
        )
    return lines


def _terminal_lines(results: Sequence[CellResult]) -> list[str]:
    lines = [
        "| n_pairs | null_per_pair | fn_construction | p_P | p_N | d | joint state | count "
        "| share | LB(F-P) | LB(F-N) | UB(F-P) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        c = res.cell
        d_result = res.design
        for state in JOINT_STATES:
            t = res.terminal[state]
            n = len(t.lb_fp)
            med_fp = f"{float(np.median(t.lb_fp)):.4f}" if t.lb_fp else "-"
            med_fn = f"{float(np.median(t.lb_fn)):.4f}" if t.lb_fn else "-"
            med_ub = f"{float(np.median(t.ub_fp)):.4f}" if t.ub_fp else "-"
            lines.append(
                f"| {d_result.n_pairs} | {d_result.null_per_pair:.2f} | "
                f"{d_result.fn_construction} | {c.p_placebo:.2f} | {c.p_null:.2f} | {c.d:.2f} "
                f"| {state} | {n} | {n / res.replicates:.4f} | {med_fp} | {med_fn} | {med_ub} |"
            )
    return lines


def summary_md(results: Sequence[CellResult], replicates: int, seed: int) -> str:
    se_nominal = math.sqrt(a650.PASS_ALPHA * (1 - a650.PASS_ALPHA) / replicates)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(replicates)
    lines = [
        "#685 lever adjudication: Stage 1 results",
        "",
        f"Replicates per cell: {replicates}. Seed: {seed}. MC SE of P(PASS) at the nominal "
        f"0.0209: {se_nominal:.5f}; calibration limit 0.0209 + 3 SE = {limit:.5f}.",
        "",
        "## Stage 1 designs",
        "",
        "Null allocation x F-N construction, at fixed 300- and 1,200-epoch budgets.",
        f"Null allocation levels: {NULL_PER_PAIR_LEVELS}.",
        f"F-N constructions: {FN_CONSTRUCTIONS}.",
        "",
        "## Surface at the cap (subset: n_pairs=400, null_per_pair=1.0)",
        "",
    ]
    subset = [
        r
        for r in results
        if r.design.n_pairs == PAIRS_CAP
        and r.design.null_per_pair == 1.0
        and r.design.fn_construction == "union"
    ]
    lines += _surface_lines(subset)
    lines += [
        "",
        "## Headline: smallest d with P(PASS) >= 0.80 at 400 pairs, null_per_pair=1.0",
        "",
        "| fn_construction | p_P | p_N | smallest d |",
        "| --- | --- | --- | --- |",
    ]
    for (fn_con, p_p, p_n), d in headline(results, POWER_TARGETS[0]).items():
        shown = _NOT_REACHED if d is None else f"{d:.2f}"
        lines.append(f"| {fn_con} | {p_p:.2f} | {p_n:.2f} | {shown} |")
    lines += [
        "",
        "## Headline: smallest d with P(PASS) >= 0.90 at 400 pairs, null_per_pair=1.0",
        "",
        "| fn_construction | p_P | p_N | smallest d |",
        "| --- | --- | --- | --- |",
    ]
    for (fn_con, p_p, p_n), d in headline(results, POWER_TARGETS[1]).items():
        shown = _NOT_REACHED if d is None else f"{d:.2f}"
        lines.append(f"| {fn_con} | {p_p:.2f} | {p_n:.2f} | {shown} |")
    checks = target_check_rows(results)
    lines += [
        "",
        "## Target check",
        "",
        "Both halves of the #685 target, read from the data only. A configuration "
        "meets the target when P(PASS) >= target at d = 0.30 and P(CUT) >= target "
        "at d = 0.10, each required in all nine (p_P, p_N) baseline cells. "
        "Configurations are the declared epoch budgets, ranked by total_epochs "
        "(the cap price). The smallest priced configuration that meets both halves "
        "is reported per design family; otherwise the cell reads not reached. "
        "The stage-2 trigger for a target fires when no design family reaches "
        "that target: Stage 2 (pairs and optional stopping) is gated on Stage 1 "
        "leaving the target unmet.",
        "",
        "| target | null_pp | fn_con | smallest priced configuration | total_epochs "
        "| expected spend | P(PASS) at d=0.30 | P(CUT) at d=0.10 | missing half "
        "| stage-2 trigger |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for check in checks:
        config = (
            f"{check.n_pairs} pairs"
            if check.reached and check.n_pairs is not None
            else "not reached"
        )
        epochs = "-" if check.total_epochs is None else str(check.total_epochs)
        spend = check.expected_spend or "-"
        min_pass = "-" if check.p_pass_at_d030 is None else f"{check.p_pass_at_d030:.4f}"
        min_cut = "-" if check.p_cut_at_d010 is None else f"{check.p_cut_at_d010:.4f}"
        missing = check.missing_half or "-"
        trigger = "fires" if check.trigger_fires else "does not fire"
        lines.append(
            f"| {check.target:.2f} | {check.null_per_pair:.2f} | {check.fn_construction} "
            f"| {config} | {epochs} | {spend} | {min_pass} | {min_cut} | {missing} "
            f"| {trigger} |"
        )
    lines.append("")
    for target in POWER_TARGETS:
        fires = stage2_trigger_fires(checks, target)
        status = "fires" if fires else "does not fire"
        lines.append(f"Stage-2 trigger for target {target:.2f}: {status}.")
    lines += [
        "",
        "## Price lines",
        "",
        "| n_pairs | total_epochs | price @ $0.083 | price @ $0.087 | cap @ $0.30/epoch |",
        "| --- | --- | --- | --- | --- |",
    ]
    seen_epochs: set[int] = set()
    for res in results:
        te = res.design.total_epochs
        if te not in seen_epochs:
            seen_epochs.add(te)
            lines.append(
                f"| {res.design.n_pairs} | {te} | ${te * _PRICE_LO:.2f} "
                f"| ${te * _PRICE_HI:.2f} | ${te * _PRICE_CAP:.2f} |"
            )
    lines += [
        "",
        "## Joint terminal state (subset: n_pairs=400, null_per_pair=1.0, union)",
        "",
        "Median [10th, 90th percentile]. LB(F-P) and UB(F-P) on d scale.",
        "",
    ]
    lines += _terminal_lines(subset)
    lines += [
        "",
        "## Model statement",
        "",
        "These smoke-run results establish only the output schema under the declared "
        "independent-Bernoulli model. They do not establish operating characteristics "
        "or how many real Claude Code epochs are required.",
        "",
        "## Pairing statement",
        "",
        "Full and Placebo are paired by launch index; under independent draws "
        "this confers no matched-pairs advantage.",
        "",
        "## Crashed-look and void-epoch rules",
        "",
        "skill-harness #697 owns the crashed-look rule and the void-epoch rule "
        "for the next paid run; this record states neither.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _run(job: tuple[Cell, Design, int, int, float]) -> CellResult:
    cell, design, replicates, seed, pass_alpha = job
    result = run_cell(cell, design, replicates=replicates, seed=seed, pass_alpha=pass_alpha)
    print(
        f"({cell.d:.2f}, {cell.p_placebo:.2f}, {cell.p_null:.2f}) "
        f"n={design.n_pairs} null_pp={design.null_per_pair:.2f} "
        f"{design.fn_construction} done, {result.library_calls} bound calls",
        flush=True,
    )
    return result


def main(
    argv: Sequence[str] | None = None,
    *,
    grid: Sequence[tuple[Cell, Design]] | None = None,
    pass_alpha: float = a650.PASS_ALPHA,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--replicates", type=int, default=REPLICATES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [
        (cell, design, args.replicates, args.seed, pass_alpha)
        for cell, design in (stage1_grid() if grid is None else grid)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_run, jobs))
    (args.out / "terminal_states.tsv").write_text(terminal_tsv(results), encoding="utf-8")
    (args.out / "per_look.tsv").write_text(per_look_tsv(results), encoding="utf-8")
    summary = summary_md(results, args.replicates, args.seed)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    cal_results = [r for r in results if role(r.cell.d) == "calibration"]
    all_hold = all(calibration_holds(r) for r in cal_results)
    if not all_hold:
        for r in cal_results:
            if not calibration_holds(r):
                dsg = r.design
                c = r.cell
                pp = r.per_look[-1].p_pass
                print(
                    f"CALIBRATION FAILURE: n={dsg.n_pairs} "
                    f"null_pp={dsg.null_per_pair:.2f} "
                    f"{dsg.fn_construction} p_P={c.p_placebo:.2f} "
                    f"p_N={c.p_null:.2f} p_pass={pp:.5f}"
                )
    return 0 if all_hold else 1


if __name__ == "__main__":
    sys.exit(main())
