"""#650: operating characteristics of the #621 A-world design at the ledger level. No model calls.

Three arms, Full-A, Placebo-A and Null-A, are independent Bernoulli streams. Full and Placebo
pair by launch index (the i-th draw of each), as the #649 launcher pairs them, and the pair's
x = (F - P + 1) / 2 is bounded and mapped back by d = 2x - 1. After every pair the rule the #649
launcher registers is applied:

  UB(F - P) < 0.20, one-sided at 0.05                                  -> CUT (no_lift)
  LB(F - P) >= 0.20, one-sided at 0.0209, and
  LB(mu_F) - UB(mu_N) >= 0.20, each one-sided at 0.0209 / 2            -> PASS
  otherwise                                                            -> continue, to n_max

The one-sided bounds come from single capital processes (``one_sided_betting_bound``). Each cell
also runs the same rule with the two edges of the two-sided hedged sequence
(``betting_confidence_sequence``) on the same draws, so the gain from the one-sided construction
is visible.

The rule at a look does not depend on the cap, so one run to the largest horizon gives every
smaller cap exactly: a replicate that stops at look k counts as stopped for every n_max >= k.

Speed. Calling the bound functions at every look is O(n^2) pure Python per replicate. The
simulation therefore carries the same wealth processes on the same mu grid for all replicates
at once. The exact bound lies between the first grid point outside the rejection set, in scan
order, and its rejected neighbour, so the grid gives an interval that holds the exact bound.
When that interval does not settle a decision, when no grid point survives, or when any grid
log-wealth sits within ``_TIE_EPS`` of the threshold, the decision is taken from the bound
function itself on that prefix. Every decision therefore equals the bound function's;
``tests/test_simulate_a_design_650.py`` checks that directly.

Usage:
  python scripts/screens/419/simulate_a_design.py --out DIR [--replicates 2000] [--seed 650]
         [--horizon 120]
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

from skill_harness.aggregation import confidence_sequence as cs_mod
from skill_harness.aggregation.confidence_sequence import (
    DEFAULT_ALPHA,
    betting_confidence_sequence,
)

Outcome = Literal["CUT_NO_LIFT", "A_PASSES_EARLY", "UNRESOLVED_CONTINUE"]
Construction = Literal["one_sided", "hedged"]
Side = Literal["lower", "upper"]
Floats = npt.NDArray[np.float64]
Bools = npt.NDArray[np.bool_]
Ints = npt.NDArray[np.int64]

BOUNDARY = 0.20
PASS_ALPHA = 0.0209
FUTILITY_ALPHA = 0.05
P_FULL = (0.55, 0.65, 0.75, 0.85)
P_PLACEBO = (0.15, 0.25, 0.35)
P_NULL = 1.0 / 7.0
N_MAX = (16, 33, 46, 60)
REPLICATES = 2000
SEED = 650
SIZING_CELLS = ((0.75, 0.25), (0.85, 0.25))
POWER_TARGETS = (0.80, 0.90)
CONSTRUCTIONS: tuple[Construction, ...] = ("one_sided", "hedged")
_TIE_EPS = 1e-9

_GRID: Floats = np.array(
    [
        cs_mod._MU_EPS + (1.0 - 2.0 * cs_mod._MU_EPS) * i / cs_mod._N_GRID
        for i in range(cs_mod._N_GRID + 1)
    ]
)


def stop_rule(*, ub_fp: float, lb_fp: float, lb_fn: float) -> Outcome:
    """The registered rule, as #649 states it. ``lb_fn`` is LB(mu_F) - UB(mu_N)."""
    if ub_fp < BOUNDARY:
        return "CUT_NO_LIFT"
    if lb_fp >= BOUNDARY and lb_fn >= BOUNDARY:
        return "A_PASSES_EARLY"
    return "UNRESOLVED_CONTINUE"


def paired_xs(first: Sequence[int], second: Sequence[int]) -> list[float]:
    """Pair the i-th draw of each stream as x = (a - b + 1) / 2."""
    return [(a - b + 1) / 2 for a, b in zip(first, second, strict=True)]


def _branch_log_wealths(
    xs: Sequence[float], mu: float, *, alpha: float, sides: int
) -> tuple[float, float]:
    """Log wealth of the plus and minus capital processes at ``mu`` in (0, 1), with the
    predictable plug-in lambda at log(sides/alpha), as in the engine."""
    mean_hat = cs_mod._MEAN_PRIOR
    var_hat = cs_mod._VAR_PRIOR
    log_pos = 0.0
    log_neg = 0.0
    numer = 2.0 * math.log(sides / alpha)
    for t, x in enumerate(xs, start=1):
        denom = max(var_hat, 1e-6) * float(t) * math.log(1.0 + float(t))
        target = math.sqrt(numer / denom)
        log_pos += math.log(1.0 + min(cs_mod._TRUNC_C / mu, target) * (x - mu))
        log_neg += math.log(1.0 - min(cs_mod._TRUNC_C / (1.0 - mu), target) * (x - mu))
        resid = x - mean_hat
        mean_hat = mean_hat + (x - mean_hat) / (t + 1)
        var_hat = max(var_hat + (resid * resid - var_hat) / (t + 1), 1e-6)
    return log_pos, log_neg


def one_sided_betting_bound(
    observations: Sequence[float],
    *,
    alpha: float = DEFAULT_ALPHA,
    side: Literal["lower", "upper"],
) -> float:
    """Terminal one-sided (1-alpha) anytime-valid bound on the mean of [0, 1] observations.

    A local copy of the engine function the #649 launcher adds to
    ``skill_harness.aggregation.confidence_sequence``; #649 owns it, and this script imports the
    engine's version once #649 merges. A lower bound uses only the plus capital process and an
    upper bound only the minus process, with the plug-in lambda at log(1/alpha), inverted at
    1/alpha. Empty input yields the vacuous bound: 0 for ``lower``, 1 for ``upper``.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")
    if side not in ("lower", "upper"):
        raise ValueError(f"side must be 'lower' or 'upper', got {side!r}")
    xs = [float(x) for x in observations]
    for i, x in enumerate(xs):
        if not 0.0 <= x <= 1.0 or math.isnan(x):
            raise ValueError(f"observation[{i}]={x!r} not in [0, 1]")
    if not xs:
        return 0.0 if side == "lower" else 1.0

    log_threshold = math.log(1.0 / alpha)

    def rejected(mu: float) -> bool:
        log_pos, log_neg = _branch_log_wealths(xs, mu, alpha=alpha, sides=1)
        return (log_pos if side == "lower" else log_neg) >= log_threshold

    grid = [float(m) for m in _GRID]
    if side == "upper":
        grid.reverse()
    first = next((i for i, m in enumerate(grid) if not rejected(m)), None)
    if first is None:
        return min(1.0, max(0.0, sum(xs) / len(xs)))
    if first == 0:
        return 0.0 if side == "lower" else 1.0
    outside, inside = grid[first - 1], grid[first]
    for _ in range(cs_mod._BISECT_ITERS):
        mid = 0.5 * (outside + inside)
        if rejected(mid):
            outside = mid
        else:
            inside = mid
    return float(inside)


def exact_bound(
    xs: Sequence[float], *, alpha: float, side: Side, construction: Construction
) -> float:
    """The bound on the mean scale, from the bound function itself."""
    if construction == "one_sided":
        return one_sided_betting_bound(xs, alpha=alpha, side=side)
    res = betting_confidence_sequence(xs, alpha=alpha)
    return res.lo if side == "lower" else res.hi


class WealthGrid:
    """Both capital processes at every grid mu, for R replicates at once."""

    def __init__(self, replicates: int, alpha: float, sides: int) -> None:
        self.log_threshold = math.log(1.0 / alpha)
        self._numer = 2.0 * math.log(sides / alpha)
        self._cap_plus = cs_mod._TRUNC_C / _GRID
        self._cap_minus = cs_mod._TRUNC_C / (1.0 - _GRID)
        self.t = 0
        self.log_pos: Floats = np.zeros((replicates, len(_GRID)))
        self.log_neg: Floats = np.zeros((replicates, len(_GRID)))
        self.mean_hat: Floats = np.full(replicates, cs_mod._MEAN_PRIOR)
        self.var_hat: Floats = np.full(replicates, cs_mod._VAR_PRIOR)

    def step(self, x: Floats) -> None:
        self.t += 1
        t = float(self.t)
        denom = np.maximum(self.var_hat, 1e-6) * t * math.log(1.0 + t)
        target = np.sqrt(self._numer / denom)[:, None]
        resid_mu = x[:, None] - _GRID
        self.log_pos += np.log(1.0 + np.minimum(self._cap_plus, target) * resid_mu)
        self.log_neg += np.log(1.0 - np.minimum(self._cap_minus, target) * resid_mu)
        resid = x - self.mean_hat
        self.mean_hat = self.mean_hat + (x - self.mean_hat) / (t + 1)
        var = self.var_hat + (resid * resid - self.var_hat) / (t + 1)
        self.var_hat = np.maximum(var, 1e-6)

    def hedged_log_wealth(self) -> Floats:
        a = math.log(cs_mod._THETA) + self.log_pos
        b = math.log(1.0 - cs_mod._THETA) + self.log_neg
        m = np.maximum(a, b)
        out = m + np.log(np.exp(a - m) + np.exp(b - m))
        return np.where(m >= cs_mod._LOG_WEALTH_CAP, cs_mod._LOG_WEALTH_CAP, out)


@dataclass(frozen=True)
class Bracket:
    """Per replicate, the exact bound lies in [lo, hi] unless ``unsure``."""

    lo: Floats
    hi: Floats
    unsure: Bools


def bracket(grid: WealthGrid, side: Side, construction: Construction) -> Bracket:
    """Scan the grid the way the bound function does and bracket its endpoint.

    A lower bound scans mu upward, an upper bound downward. The endpoint sits between the first
    surviving grid point and the rejected one before it, or at the vacuous edge when the first
    grid point survives.
    """
    if construction == "hedged":
        lw = grid.hedged_log_wealth()
    else:
        lw = grid.log_pos if side == "lower" else grid.log_neg
    step = 1 if side == "lower" else -1
    mus = _GRID[::step]
    survives = (lw < grid.log_threshold)[:, ::step]
    first = np.argmax(survives, axis=1)
    g_in = mus[first]
    g_out = mus[np.maximum(first - 1, 0)]
    vacuous = first == 0
    edge = 0.0 if side == "lower" else 1.0
    unsure = ~survives.any(axis=1) | (np.abs(lw - grid.log_threshold) < _TIE_EPS).any(axis=1)
    return Bracket(
        lo=np.where(vacuous, edge, g_out if side == "lower" else g_in),
        hi=np.where(vacuous, edge, g_in if side == "lower" else g_out),
        unsure=unsure,
    )


@dataclass(frozen=True)
class CellRun:
    """First stopping look (1-based; horizon + 1 when never stopped) and its outcome."""

    stop_at: Ints
    passed: Bools
    cut: Bools
    library_calls: int


def draw_streams(
    p_full: float,
    p_placebo: float,
    p_null: float,
    *,
    horizon: int,
    replicates: int,
    rng: np.random.Generator,
) -> tuple[Ints, Ints, Ints]:
    return (
        (rng.random((replicates, horizon)) < p_full).astype(np.int64),
        (rng.random((replicates, horizon)) < p_placebo).astype(np.int64),
        (rng.random((replicates, horizon)) < p_null).astype(np.int64),
    )


def simulate_cell(
    p_full: float,
    p_placebo: float,
    p_null: float,
    *,
    horizon: int,
    replicates: int,
    rng: np.random.Generator,
    construction: Construction = "one_sided",
    pass_alpha: float = PASS_ALPHA,
) -> CellRun:
    """Draw the three streams and run every replicate to its first stop or to ``horizon``."""
    return simulate_streams(
        *draw_streams(p_full, p_placebo, p_null, horizon=horizon, replicates=replicates, rng=rng),
        construction=construction,
        pass_alpha=pass_alpha,
    )


@dataclass(frozen=True)
class _Look:
    """One look's grid brackets, for the four bounds the rule reads."""

    ub_fp: Bracket
    lb_fp: Bracket
    lb_f: Bracket
    ub_n: Bracket


def simulate_streams(
    full: Ints,
    placebo: Ints,
    null: Ints,
    *,
    construction: Construction = "one_sided",
    pass_alpha: float = PASS_ALPHA,
) -> CellRun:
    """Apply the rule after every pair of three (replicates, horizon) 0/1 streams.

    ``pass_alpha`` differs from the registered 0.0209 only in the negative control, which
    loosens the pass test to show that the calibration check can fail.
    """
    replicates, horizon = full.shape
    sides = 1 if construction == "one_sided" else 2
    xs_fp = (full - placebo + 1) / 2.0
    xs_f = full.astype(np.float64)
    xs_n = null.astype(np.float64)
    fp_fut = WealthGrid(replicates, FUTILITY_ALPHA, sides)
    fp_pass = WealthGrid(replicates, pass_alpha, sides)
    f_pass = WealthGrid(replicates, pass_alpha / 2, sides)
    n_pass = WealthGrid(replicates, pass_alpha / 2, sides)
    stop_at = np.full(replicates, horizon + 1, dtype=np.int64)
    passed = np.zeros(replicates, dtype=np.bool_)
    cut = np.zeros(replicates, dtype=np.bool_)
    calls = 0
    for k in range(1, horizon + 1):
        fp_fut.step(xs_fp[:, k - 1])
        fp_pass.step(xs_fp[:, k - 1])
        f_pass.step(xs_f[:, k - 1])
        n_pass.step(xs_n[:, k - 1])
        look = _Look(
            ub_fp=bracket(fp_fut, "upper", construction),
            lb_fp=bracket(fp_pass, "lower", construction),
            lb_f=bracket(f_pass, "lower", construction),
            ub_n=bracket(n_pass, "upper", construction),
        )
        for r in np.flatnonzero(stop_at > horizon).tolist():
            prefixes = (xs_fp[r, :k].tolist(), xs_f[r, :k].tolist(), xs_n[r, :k].tolist())
            outcome, used = _decide(look, r, prefixes, construction, pass_alpha)
            calls += used
            if outcome != "UNRESOLVED_CONTINUE":
                stop_at[r] = k
                passed[r] = outcome == "A_PASSES_EARLY"
                cut[r] = outcome == "CUT_NO_LIFT"
    return CellRun(stop_at=stop_at, passed=passed, cut=cut, library_calls=calls)


def _decide(
    look: _Look,
    r: int,
    prefixes: tuple[list[float], list[float], list[float]],
    construction: Construction,
    pass_alpha: float,
) -> tuple[Outcome, int]:
    """The rule for replicate ``r``, from the grid where it settles and the bound otherwise."""
    xs_fp, xs_f, xs_n = prefixes
    calls = 0

    def exact(xs: list[float], alpha: float, side: Side) -> float:
        nonlocal calls
        calls += 1
        return exact_bound(xs, alpha=alpha, side=side, construction=construction)

    ub = look.ub_fp
    if ub.unsure[r] or not (2 * ub.hi[r] - 1 < BOUNDARY or 2 * ub.lo[r] - 1 >= BOUNDARY):
        cut_now = 2 * exact(xs_fp, FUTILITY_ALPHA, "upper") - 1 < BOUNDARY
    else:
        cut_now = bool(2 * ub.hi[r] - 1 < BOUNDARY)
    if cut_now:
        return "CUT_NO_LIFT", calls

    lb = look.lb_fp
    if lb.unsure[r] or not (2 * lb.lo[r] - 1 >= BOUNDARY or 2 * lb.hi[r] - 1 < BOUNDARY):
        fp_clears = 2 * exact(xs_fp, pass_alpha, "lower") - 1 >= BOUNDARY
    else:
        fp_clears = bool(2 * lb.lo[r] - 1 >= BOUNDARY)
    if not fp_clears:
        return "UNRESOLVED_CONTINUE", calls

    f, n = look.lb_f, look.ub_n
    sure_yes = f.lo[r] - n.hi[r] >= BOUNDARY
    sure_no = f.hi[r] - n.lo[r] < BOUNDARY
    if f.unsure[r] or n.unsure[r] or not (sure_yes or sure_no):
        half = pass_alpha / 2
        fn_clears = exact(xs_f, half, "lower") - exact(xs_n, half, "upper") >= BOUNDARY
    else:
        fn_clears = bool(sure_yes)
    return ("A_PASSES_EARLY" if fn_clears else "UNRESOLVED_CONTINUE"), calls


@dataclass(frozen=True)
class CapRow:
    construction: Construction
    p_full: float
    p_placebo: float
    p_null: float
    n_max: int
    replicates: int
    p_pass: float
    p_cut: float
    p_unresolved: float
    se_pass: float
    expected_pairs: float


def at_cap(
    run: CellRun,
    p_full: float,
    p_placebo: float,
    p_null: float,
    n_max: int,
    construction: Construction = "one_sided",
) -> CapRow:
    stopped = run.stop_at <= n_max
    reps = len(run.stop_at)
    p_pass = float(np.mean(stopped & run.passed))
    p_cut = float(np.mean(stopped & run.cut))
    return CapRow(
        construction=construction,
        p_full=p_full,
        p_placebo=p_placebo,
        p_null=p_null,
        n_max=n_max,
        replicates=reps,
        p_pass=p_pass,
        p_cut=p_cut,
        p_unresolved=1.0 - p_pass - p_cut,
        se_pass=math.sqrt(p_pass * (1.0 - p_pass) / reps),
        expected_pairs=float(np.mean(np.minimum(run.stop_at, n_max))),
    )


def smallest_n_reaching(run: CellRun, target: float) -> int | None:
    """Smallest cap, in pairs, whose pass probability is at least ``target``."""
    for n in range(1, int(run.stop_at.max(initial=1))):
        if np.mean((run.stop_at <= n) & run.passed) >= target:
            return n
    return None


def calibration_tolerance(replicates: int, alpha: float = PASS_ALPHA) -> float:
    """Three Monte Carlo standard errors at the nominal level."""
    return 3.0 * math.sqrt(alpha * (1.0 - alpha) / replicates)


def is_boundary(p_full: float, p_placebo: float) -> bool:
    return math.isclose(p_full - p_placebo, BOUNDARY, abs_tol=1e-9)


def cell_rng(seed: int, p_full: float, p_placebo: float) -> np.random.Generator:
    return np.random.default_rng([seed, round(p_full * 1000), round(p_placebo * 1000)])


_TSV_HEADER = (
    "construction\tp_full\tp_placebo\tp_null\tn_max\treplicates\tp_pass\tp_cut\tp_unresolved"
    "\tse_pass\texpected_pairs"
)


def _tsv_line(row: CapRow) -> str:
    return (
        f"{row.construction}\t{row.p_full:.2f}\t{row.p_placebo:.2f}\t{row.p_null:.6f}"
        f"\t{row.n_max}\t{row.replicates}\t{row.p_pass:.4f}\t{row.p_cut:.4f}"
        f"\t{row.p_unresolved:.4f}\t{row.se_pass:.4f}\t{row.expected_pairs:.2f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--replicates", type=int, default=REPLICATES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--horizon", type=int, default=max(N_MAX))
    args = ap.parse_args(argv)
    horizon = max(args.horizon, *N_MAX)
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[CapRow] = []
    runs: dict[tuple[Construction, float, float], CellRun] = {}
    for p_full in P_FULL:
        for p_placebo in P_PLACEBO:
            streams = draw_streams(
                p_full,
                p_placebo,
                P_NULL,
                horizon=horizon,
                replicates=args.replicates,
                rng=cell_rng(args.seed, p_full, p_placebo),
            )
            for construction in CONSTRUCTIONS:
                run = simulate_streams(*streams, construction=construction)
                runs[(construction, p_full, p_placebo)] = run
                rows.extend(at_cap(run, p_full, p_placebo, P_NULL, n, construction) for n in N_MAX)
                print(
                    f"cell ({p_full}, {p_placebo}) {construction} done, "
                    f"{run.library_calls} bound calls",
                    flush=True,
                )

    (args.out / "a_design_sim.tsv").write_text(
        "\n".join([_TSV_HEADER, *(_tsv_line(r) for r in rows)]) + "\n", encoding="utf-8"
    )
    summary = _summary(rows, runs, args.replicates, args.seed, horizon)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if _calibration_holds(rows) else 1


def _calibration_holds(rows: Sequence[CapRow]) -> bool:
    return all(
        r.p_pass <= PASS_ALPHA + calibration_tolerance(r.replicates)
        for r in rows
        if is_boundary(r.p_full, r.p_placebo)
    )


def _summary(
    rows: Sequence[CapRow],
    runs: dict[tuple[Construction, float, float], CellRun],
    replicates: int,
    seed: int,
    horizon: int,
) -> str:
    lines = [
        f"Replicates per cell: {replicates}. Seed: {seed}. p_N = 1/7. Pairs simulated to "
        f"{horizon}. Pass alpha {PASS_ALPHA} (F - N bounds at {PASS_ALPHA / 2} each), "
        f"futility alpha {FUTILITY_ALPHA}, margin {BOUNDARY}. `one_sided` is the registered "
        "rule; `hedged` is the same rule read from the two-sided hedged sequence's edges.",
        "",
        "## Boundary calibration (p_F - p_P = 0.20)",
        "",
        "| construction | p_F | p_P | n_max | P(pass) | MC SE at 0.0209 | "
        "limit (0.0209 + 3 SE) | holds |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        if is_boundary(r.p_full, r.p_placebo):
            se = math.sqrt(PASS_ALPHA * (1 - PASS_ALPHA) / r.replicates)
            limit = PASS_ALPHA + calibration_tolerance(r.replicates)
            lines.append(
                f"| {r.construction} | {r.p_full:.2f} | {r.p_placebo:.2f} | {r.n_max} | "
                f"{r.p_pass:.4f} | {se:.4f} | {limit:.4f} | "
                f"{'yes' if r.p_pass <= limit else 'NO'} |"
            )
    lines += [
        "",
        "## Smallest cap reaching the power target",
        "",
        "| construction | p_F | p_P | pairs for 80% pass | pairs for 90% pass | "
        "smallest grid n_max, 80% | smallest grid n_max, 90% |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for construction in CONSTRUCTIONS:
        for p_full, p_placebo in SIZING_CELLS:
            run = runs[(construction, p_full, p_placebo)]
            exact = [smallest_n_reaching(run, t) for t in POWER_TARGETS]
            grid = [
                next(
                    (
                        r.n_max
                        for r in rows
                        if (r.construction, r.p_full, r.p_placebo)
                        == (construction, p_full, p_placebo)
                        and r.p_pass >= t
                    ),
                    None,
                )
                for t in POWER_TARGETS
            ]
            fmt = [f">{horizon}" if n is None else str(n) for n in exact]
            gfmt = ["none" if n is None else str(n) for n in grid]
            lines.append(
                f"| {construction} | {p_full:.2f} | {p_placebo:.2f} | {fmt[0]} | {fmt[1]} | "
                f"{gfmt[0]} | {gfmt[1]} |"
            )
    lines += [
        "",
        "## Every cell",
        "",
        "| construction | p_F | p_P | n_max | P(pass) | P(CUT) | P(unresolved) | E[pairs] |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {r.construction} | {r.p_full:.2f} | {r.p_placebo:.2f} | {r.n_max} | "
        f"{r.p_pass:.4f} | {r.p_cut:.4f} | {r.p_unresolved:.4f} | {r.expected_pairs:.1f} |"
        for r in rows
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
