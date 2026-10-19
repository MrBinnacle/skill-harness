"""#684: operating characteristics of the registered Stage 1A rule in the regime that was run.

No model calls, no network, no spend.

Stage 1A ran 97 Full/Placebo pairs with one Null draw per pair (1:1:1) and observed baselines
near 0.35 for both Placebo and Null. The #650 simulator (``simulate_a_design.py``) holds the Null
rate at 1/7 and caps the run at 60 pairs, so it cannot describe that run. This sibling reuses the
#650 construction, stopping rule and exactness machinery unchanged and makes the Null rate and
the cap per-cell inputs. The pass alpha stays registered at 0.0209.

Grid: p_P and p_N each in {0.30, 0.35, 0.40} (nine cells), d = p_F - p_P in {0.20, 0.25, 0.30,
0.35, 0.40}. Every look from 1 to 97 is recorded, so any smaller cap can be read off. For the
replicates still open at the cap, the terminal bounds are recorded by joint state: which of the
two PASS conditions holds. The terminal bounds come from the engine's ``one_sided_betting_bound``,
vectorised over replicates (``terminal_bounds``); a test checks them against the engine to 1e-9.

Usage:
  python scripts/screens/419/simulate_stage1a_regime.py --out DIR [--replicates 10000]
         [--seed 684] [--workers N]
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

import simulate_a_design as a650  # the sibling #650 simulator, reused unchanged

from skill_harness.aggregation import confidence_sequence as cs_mod
from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

N_PAIRS = 97
BASELINES = (0.30, 0.35, 0.40)
EFFECTS = (0.20, 0.25, 0.30, 0.35, 0.40)
POWER_TARGET = 0.80
REPLICATES = 10_000
SEED = 684

JointState = Literal["fp_passes_fn_fails", "fn_passes_fp_fails", "neither_passes"]
JOINT_STATES: tuple[JointState, ...] = (
    "fp_passes_fn_fails",
    "fn_passes_fp_fails",
    "neither_passes",
)


@dataclass(frozen=True)
class Design:
    """One draw per arm per look: Full and Placebo paired by launch index, one Null per pair."""

    n_pairs: int

    @property
    def n_full(self) -> int:
        return self.n_pairs

    @property
    def n_placebo(self) -> int:
        return self.n_pairs

    @property
    def n_null(self) -> int:
        return self.n_pairs

    @property
    def total_epochs(self) -> int:
        return self.n_full + self.n_placebo + self.n_null

    @property
    def null_per_pair(self) -> float:
        return self.n_null / self.n_pairs


@dataclass(frozen=True)
class Cell:
    """True success rates of the three arms."""

    p_full: float
    p_placebo: float
    p_null: float

    @property
    def d(self) -> float:
        return round(self.p_full - self.p_placebo, 10)


@dataclass(frozen=True)
class LookRow:
    """Outcome probabilities if the cap were ``look`` pairs."""

    look: int
    p_pass: float
    p_cut: float
    p_cant_tell_yet: float
    se_pass: float
    expected_pairs: float


@dataclass(frozen=True)
class TerminalSample:
    """Terminal bounds, at the cap, of the replicates in one joint state.

    ``lb_fp`` and ``ub_fp`` are on the difference scale d = 2x - 1; ``lb_fn`` is
    LB(mu_F) - UB(mu_N) with each bound one-sided at the registered pass alpha / 2.
    """

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


def cell_rng(seed: int, cell: Cell) -> np.random.Generator:
    """One generator per cell, keyed on all three rates so cells never share draws."""
    return np.random.default_rng(
        [seed, round(cell.p_full * 1000), round(cell.p_placebo * 1000), round(cell.p_null * 1000)]
    )


def per_look_rows(run: a650.CellRun, n_pairs: int) -> tuple[LookRow, ...]:
    """Every cap from 1 to ``n_pairs``, read from one run's first stopping looks."""
    reps = len(run.stop_at)
    rows = []
    for k in range(1, n_pairs + 1):
        stopped = run.stop_at <= k
        p_pass = float(np.mean(stopped & run.passed))
        p_cut = float(np.mean(stopped & run.cut))
        rows.append(
            LookRow(
                look=k,
                p_pass=p_pass,
                p_cut=p_cut,
                p_cant_tell_yet=1.0 - p_pass - p_cut,
                se_pass=math.sqrt(p_pass * (1.0 - p_pass) / reps),
                expected_pairs=float(np.mean(np.minimum(run.stop_at, k))),
            )
        )
    return tuple(rows)


def role(d: float) -> str:
    """What an effect row on the grid is for."""
    if math.isclose(d, a650.BOUNDARY, abs_tol=1e-9):
        return "calibration"
    if math.isclose(d, 0.25, abs_tol=1e-9):
        return "small real effect"
    return "real effect"


def smallest_d_reaching(curve: dict[float, float], target: float) -> float | None:
    """Smallest grid effect whose P(PASS) at the cap is at least ``target``."""
    return next((d for d in sorted(curve) if curve[d] >= target), None)


def run_cell(
    cell: Cell,
    design: Design,
    *,
    replicates: int,
    seed: int,
    pass_alpha: float = a650.PASS_ALPHA,
) -> CellResult:
    """Draw one stream per arm, one draw per look, and apply the registered rule to the cap.

    ``pass_alpha`` differs from the registered 0.0209 only in the negative control.
    """
    streams = a650.draw_streams(
        cell.p_full,
        cell.p_placebo,
        cell.p_null,
        horizon=design.n_pairs,
        replicates=replicates,
        rng=cell_rng(seed, cell),
    )
    run = a650.simulate_streams(*streams, pass_alpha=pass_alpha)
    unresolved = run.stop_at > design.n_pairs
    return CellResult(
        cell=cell,
        design=design,
        replicates=replicates,
        per_look=per_look_rows(run, design.n_pairs),
        terminal=tally_terminal(*(arm[unresolved] for arm in streams)),
        library_calls=run.library_calls,
    )


def joint_state(*, lb_fp: float, lb_fn: float) -> JointState:
    """Which of the two PASS conditions holds at the cap, for a replicate the rule left open."""
    fp = lb_fp >= a650.BOUNDARY
    fn = lb_fn >= a650.BOUNDARY
    if fp and fn:
        raise ValueError("both PASS conditions hold: the rule would have passed this replicate")
    if fp:
        return "fp_passes_fn_fails"
    if fn:
        return "fn_passes_fp_fails"
    return "neither_passes"


@dataclass(frozen=True)
class TerminalBounds:
    """The three quantities the rule reads, per replicate, after its last pair."""

    lb_fp: a650.Floats
    ub_fp: a650.Floats
    lb_fn: a650.Floats


def terminal_bounds(full: a650.Ints, placebo: a650.Ints, null: a650.Ints) -> TerminalBounds:
    """The engine's one-sided bounds on the full (replicates, pairs) streams, vectorised."""
    xs_fp = (full - placebo + 1) / 2.0
    half = a650.PASS_ALPHA / 2
    return TerminalBounds(
        lb_fp=2 * _bound(xs_fp, a650.PASS_ALPHA, "lower") - 1,
        ub_fp=2 * _bound(xs_fp, a650.FUTILITY_ALPHA, "upper") - 1,
        lb_fn=_bound(full.astype(np.float64), half, "lower")
        - _bound(null.astype(np.float64), half, "upper"),
    )


def tally_terminal(
    full: a650.Ints, placebo: a650.Ints, null: a650.Ints
) -> dict[JointState, TerminalSample]:
    """Split replicates the rule left open at the cap by which PASS condition holds."""
    tb = terminal_bounds(full, placebo, null)
    if bool(np.any(tb.ub_fp < a650.BOUNDARY)):
        raise RuntimeError("an open replicate has UB(F - P) < 0.20: the rule would have cut it")
    states = [
        joint_state(lb_fp=float(f), lb_fn=float(n)) for f, n in zip(tb.lb_fp, tb.lb_fn, strict=True)
    ]
    out: dict[JointState, TerminalSample] = {}
    for state in JOINT_STATES:
        idx = [i for i, s in enumerate(states) if s == state]
        out[state] = TerminalSample(
            lb_fp=tuple(float(tb.lb_fp[i]) for i in idx),
            lb_fn=tuple(float(tb.lb_fn[i]) for i in idx),
            ub_fp=tuple(float(tb.ub_fp[i]) for i in idx),
        )
    return out


def _bound(xs: a650.Floats, alpha: float, side: a650.Side) -> a650.Floats:
    """``one_sided_betting_bound`` for every row of ``xs`` at once.

    The grid gives the engine's bracket; 64 vectorised bisection steps inside it repeat the
    engine's own bisection. A row whose bracket the grid cannot settle is sent to the engine.
    """
    replicates, n = xs.shape
    grid = a650.WealthGrid(replicates, alpha, 1)
    for k in range(n):
        grid.step(xs[:, k])
    br = a650.bracket(grid, side, "one_sided")
    edge = 0.0 if side == "lower" else 1.0
    vacuous = (br.lo == edge) & (br.hi == edge)
    idle = vacuous | br.unsure  # rows answered without bisection; keep their mu interior
    outside = np.where(idle, 0.5, br.lo if side == "lower" else br.hi)
    inside = np.where(idle, 0.5, br.hi if side == "lower" else br.lo)
    targets = _plug_in_targets(xs, alpha)
    threshold = math.log(1.0 / alpha)
    for _ in range(cs_mod._BISECT_ITERS):
        mid = 0.5 * (outside + inside)
        rejected = _branch_log_wealth(xs, targets, mid, side) >= threshold
        outside = np.where(rejected, mid, outside)
        inside = np.where(rejected, inside, mid)
    out = np.where(vacuous, edge, inside)
    for r in np.flatnonzero(br.unsure).tolist():
        out[r] = one_sided_betting_bound(xs[r].tolist(), alpha=alpha, side=side)
    return out


def _plug_in_targets(xs: a650.Floats, alpha: float) -> a650.Floats:
    """The predictable plug-in lambda target at each step, which does not depend on mu."""
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
    """Log wealth of the plus (lower) or minus (upper) capital process at a per-row mu."""
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


QUANTILES = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
_DESIGN_HEADER = "n_full\tn_placebo\tn_null\ttotal_epochs\tnull_per_pair"
_CELL_HEADER = "p_full\tp_placebo\tp_null\td\trole"
_NOT_REACHED = "not reached on this grid"


def grid_cells() -> list[Cell]:
    return [
        Cell(round(p_p + d, 10), p_p, p_n)
        for p_p in BASELINES
        for p_n in BASELINES
        for d in EFFECTS
    ]


def _run(job: tuple[Cell, int, int, int]) -> CellResult:
    cell, n_pairs, replicates, seed = job
    result = run_cell(cell, Design(n_pairs=n_pairs), replicates=replicates, seed=seed)
    print(f"{cell} done, {result.library_calls} bound calls", flush=True)
    return result


def _design_cols(design: Design) -> str:
    return (
        f"{design.n_full}\t{design.n_placebo}\t{design.n_null}\t{design.total_epochs}"
        f"\t{design.null_per_pair:.2f}"
    )


def _cell_cols(cell: Cell) -> str:
    return (
        f"{cell.p_full:.2f}\t{cell.p_placebo:.2f}\t{cell.p_null:.2f}\t{cell.d:.2f}\t{role(cell.d)}"
    )


def per_look_tsv(results: Sequence[CellResult]) -> str:
    lines = [
        f"{_DESIGN_HEADER}\t{_CELL_HEADER}\treplicates\tlook\tp_pass\tp_cut"
        "\tp_cant_tell_yet\tse_pass\texpected_pairs"
    ]
    for res in results:
        lines += [
            f"{_design_cols(res.design)}\t{_cell_cols(res.cell)}\t{res.replicates}\t{row.look}"
            f"\t{row.p_pass:.5f}\t{row.p_cut:.5f}\t{row.p_cant_tell_yet:.5f}\t{row.se_pass:.5f}"
            f"\t{row.expected_pairs:.3f}"
            for row in res.per_look
        ]
    return "\n".join(lines) + "\n"


def _quantiles(values: Sequence[float]) -> list[str]:
    if not values:
        return ["NA" for _ in QUANTILES]
    return [f"{float(q):.4f}" for q in np.quantile(np.asarray(values), QUANTILES)]


def terminal_tsv(results: Sequence[CellResult]) -> str:
    qnames = [f"q{round(q * 100):02d}" for q in QUANTILES]
    stat_cols = "\t".join(f"{name}_{q}" for name in ("lb_fp", "lb_fn", "ub_fp") for q in qnames)
    lines = [
        f"{_DESIGN_HEADER}\t{_CELL_HEADER}\treplicates\tjoint_state\tcount\tshare\t{stat_cols}"
    ]
    for res in results:
        for state in JOINT_STATES:
            t = res.terminal[state]
            stats = [*_quantiles(t.lb_fp), *_quantiles(t.lb_fn), *_quantiles(t.ub_fp)]
            lines.append(
                f"{_design_cols(res.design)}\t{_cell_cols(res.cell)}\t{res.replicates}\t{state}"
                f"\t{len(t.lb_fp)}\t{len(t.lb_fp) / res.replicates:.5f}\t" + "\t".join(stats)
            )
    return "\n".join(lines) + "\n"


def calibration_holds(res: CellResult) -> bool:
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(res.replicates)
    return res.per_look[-1].p_pass <= limit


def headline(results: Sequence[CellResult]) -> dict[tuple[float, float], float | None]:
    """Per (p_P, p_N), the smallest grid d whose P(PASS) at the cap reaches the target."""
    out: dict[tuple[float, float], float | None] = {}
    for p_p in BASELINES:
        for p_n in BASELINES:
            curve = {
                r.cell.d: r.per_look[-1].p_pass
                for r in results
                if (r.cell.p_placebo, r.cell.p_null) == (p_p, p_n)
            }
            out[(p_p, p_n)] = smallest_d_reaching(curve, POWER_TARGET)
    return out


def _mid(values: Sequence[float]) -> str:
    if not values:
        return "-"
    q10, q50, q90 = np.quantile(np.asarray(values), (0.10, 0.50, 0.90))
    return f"{q50:.3f} [{q10:.3f}, {q90:.3f}]"


def _surface_lines(results: Sequence[CellResult]) -> list[str]:
    lines = [
        "| p_P | p_N | d | role | p_F | P(PASS) | SE | P(CUT) | P(CANT_TELL_YET) | E[pairs] "
        "| calibration holds |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        c, row = res.cell, res.per_look[-1]
        holds = ("yes" if calibration_holds(res) else "NO") if role(c.d) == "calibration" else ""
        lines.append(
            f"| {c.p_placebo:.2f} | {c.p_null:.2f} | {c.d:.2f} | {role(c.d)} | {c.p_full:.2f} | "
            f"{row.p_pass:.4f} | {row.se_pass:.4f} | {row.p_cut:.4f} | "
            f"{row.p_cant_tell_yet:.4f} | {row.expected_pairs:.1f} | {holds} |"
        )
    return lines


def _terminal_lines(results: Sequence[CellResult]) -> list[str]:
    lines = [
        "| p_P | p_N | d | joint state | count | share | LB(F-P) | LB(mu_F) - UB(mu_N) | UB(F-P) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        c = res.cell
        for state in JOINT_STATES:
            t = res.terminal[state]
            n = len(t.lb_fp)
            lines.append(
                f"| {c.p_placebo:.2f} | {c.p_null:.2f} | {c.d:.2f} | {state} | {n} | "
                f"{n / res.replicates:.4f} | {_mid(t.lb_fp)} | {_mid(t.lb_fn)} | "
                f"{_mid(t.ub_fp)} |"
            )
    return lines


def summary_md(results: Sequence[CellResult], replicates: int, seed: int) -> str:
    design = results[0].design
    se_nominal = math.sqrt(a650.PASS_ALPHA * (1 - a650.PASS_ALPHA) / replicates)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(replicates)
    lines = [
        f"Design: n_full = {design.n_full}, n_placebo = {design.n_placebo}, "
        f"n_null = {design.n_null}, total_epochs = {design.total_epochs}, "
        f"null_per_pair = {design.null_per_pair:.2f}. Replicates per cell: {replicates}. "
        f"Seed: {seed}. MC SE of P(PASS) at the nominal 0.0209: {se_nominal:.5f}; "
        f"calibration limit 0.0209 + 3 SE = {limit:.5f}.",
        "",
        "## Surface at the cap",
        "",
        *_surface_lines(results),
        "",
        "## Headline: smallest d with P(PASS) >= 0.80 by 97 pairs",
        "",
        "| p_P | p_N | smallest d |",
        "| --- | --- | --- |",
    ]
    for (p_p, p_n), d in headline(results).items():
        shown = _NOT_REACHED if d is None else f"{d:.2f}"
        lines.append(f"| {p_p:.2f} | {p_n:.2f} | {shown} |")
    lines += [
        "",
        "## Joint terminal state of replicates open at the cap",
        "",
        "Each bound is median [10th, 90th percentile]. LB(F-P) and UB(F-P) are on the d scale.",
        "",
        *_terminal_lines(results),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--replicates", type=int, default=REPLICATES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [(cell, N_PAIRS, args.replicates, args.seed) for cell in grid_cells()]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_run, jobs))
    (args.out / "per_look.tsv").write_text(per_look_tsv(results), encoding="utf-8")
    (args.out / "terminal_states.tsv").write_text(terminal_tsv(results), encoding="utf-8")
    summary = summary_md(results, args.replicates, args.seed)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    calibration = [r for r in results if role(r.cell.d) == "calibration"]
    return 0 if all(calibration_holds(r) for r in calibration) else 1


if __name__ == "__main__":
    sys.exit(main())
