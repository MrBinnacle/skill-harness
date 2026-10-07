"""Tests for #650: the ledger-level simulation of the #621 A-world design."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sim = _load("simulate_a_design")


def _library_first_stop(
    full: list[int], placebo: list[int], null: list[int], construction: str
) -> tuple[int, str]:
    """The rule applied by calling the bound functions at every look, with no grid shortcut."""
    half = sim.PASS_ALPHA / 2

    def bound(xs: list[float], alpha: float, side: str) -> float:
        return float(sim.exact_bound(xs, alpha=alpha, side=side, construction=construction))

    for k in range(1, len(full) + 1):
        xs_fp = sim.paired_xs(full[:k], placebo[:k])
        xs_f = [float(v) for v in full[:k]]
        xs_n = [float(v) for v in null[:k]]
        outcome = sim.stop_rule(
            ub_fp=2 * bound(xs_fp, sim.FUTILITY_ALPHA, "upper") - 1,
            lb_fp=2 * bound(xs_fp, sim.PASS_ALPHA, "lower") - 1,
            lb_fn=bound(xs_f, half, "lower") - bound(xs_n, half, "upper"),
        )
        if outcome != "UNRESOLVED_CONTINUE":
            return k, str(outcome)
    return len(full) + 1, "UNRESOLVED_CONTINUE"


@pytest.mark.parametrize("construction", ["one_sided", "hedged"])
def test_every_decision_equals_the_bound_called_at_every_look(construction: str) -> None:
    rng = np.random.default_rng(6501)
    horizon = 22
    rates = [(0.95, 0.05, 0.05), (0.55, 0.35, 0.15), (0.3, 0.6, 0.15), (0.85, 0.25, 0.15)]
    streams = [
        np.stack([(rng.random(horizon) < p).astype(np.int64) for _ in range(8)])
        for rate in rates
        for p in rate
    ]
    full = np.concatenate(streams[0::3])
    placebo = np.concatenate(streams[1::3])
    null = np.concatenate(streams[2::3])
    run = sim.simulate_streams(full, placebo, null, construction=construction)
    seen = set()
    for r in range(full.shape[0]):
        stop, outcome = _library_first_stop(
            full[r].tolist(), placebo[r].tolist(), null[r].tolist(), construction
        )
        seen.add(outcome)
        assert int(run.stop_at[r]) == stop, r
        assert bool(run.passed[r]) == (outcome == "A_PASSES_EARLY"), r
        assert bool(run.cut[r]) == (outcome == "CUT_NO_LIFT"), r
    assert {"A_PASSES_EARLY", "CUT_NO_LIFT"} <= seen


@pytest.mark.parametrize("alpha", [0.0209, 0.05])
def test_grid_wealth_equals_the_engine_wealth(alpha: float) -> None:
    from skill_harness.aggregation.confidence_sequence import _hedged_log_wealth

    rng = np.random.default_rng(6502)
    xs = rng.choice([0.0, 0.5, 1.0], size=(6, 30))
    hedged = sim.WealthGrid(xs.shape[0], alpha, 2)
    single = sim.WealthGrid(xs.shape[0], alpha, 1)
    for k in range(xs.shape[1]):
        hedged.step(xs[:, k])
        single.step(xs[:, k])
    ours = hedged.hedged_log_wealth()
    for r in range(xs.shape[0]):
        row = xs[r].tolist()
        theirs = [_hedged_log_wealth(row, float(mu), alpha=alpha) for mu in sim._GRID]
        assert ours[r] == pytest.approx(theirs, rel=0, abs=1e-10)
        branches = [
            sim._branch_log_wealths(row, float(mu), alpha=alpha, sides=1) for mu in sim._GRID
        ]
        assert single.log_pos[r] == pytest.approx([b[0] for b in branches], rel=0, abs=1e-10)
        assert single.log_neg[r] == pytest.approx([b[1] for b in branches], rel=0, abs=1e-10)


def test_local_branch_wealth_at_two_sides_is_the_engine_hedged_wealth() -> None:
    from skill_harness.aggregation.confidence_sequence import _THETA, _hedged_log_wealth

    xs = [1.0, 0.5, 1.0, 0.0, 1.0, 1.0, 0.5, 1.0]
    for mu in (0.2, 0.5, 0.7):
        lp, ln = sim._branch_log_wealths(xs, mu, alpha=0.05, sides=2)
        mixed = math.log(_THETA * math.exp(lp) + (1 - _THETA) * math.exp(ln))
        assert mixed == pytest.approx(_hedged_log_wealth(xs, mu, alpha=0.05), abs=1e-12)


def test_one_sided_bound_is_tighter_than_the_hedged_edge() -> None:
    xs = [1.0] * 12 + [0.5] * 4 + [0.0] * 2
    hedged = sim.betting_confidence_sequence(xs, alpha=0.0209)
    lower = sim.one_sided_betting_bound(xs, alpha=0.0209, side="lower")
    upper = sim.one_sided_betting_bound(xs, alpha=0.0209, side="upper")
    assert hedged.lo < lower < upper < hedged.hi
    assert sim.one_sided_betting_bound([], side="lower") == 0.0
    assert sim.one_sided_betting_bound([], side="upper") == 1.0


def _boundary_pass_rate(pass_alpha: float, replicates: int) -> float:
    run = sim.simulate_cell(
        0.55,
        0.35,
        sim.P_NULL,
        horizon=33,
        replicates=replicates,
        rng=sim.cell_rng(sim.SEED, 0.55, 0.35),
        pass_alpha=pass_alpha,
    )
    return float(sim.at_cap(run, 0.55, 0.35, sim.P_NULL, 33).p_pass)


def test_boundary_pass_rate_is_at_most_the_ledger_alpha() -> None:
    replicates = 1000
    assert sim.is_boundary(0.55, 0.35)
    p_pass = _boundary_pass_rate(sim.PASS_ALPHA, replicates)
    assert p_pass <= sim.PASS_ALPHA + sim.calibration_tolerance(replicates)


def test_calibration_check_fails_when_the_pass_test_is_loosened() -> None:
    replicates = 1000
    p_pass = _boundary_pass_rate(0.6, replicates)
    assert p_pass > sim.PASS_ALPHA + sim.calibration_tolerance(replicates)


def test_a_large_effect_passes_most_of_the_time() -> None:
    run = sim.simulate_cell(
        0.95, 0.05, sim.P_NULL, horizon=33, replicates=200, rng=np.random.default_rng(1)
    )
    assert sim.at_cap(run, 0.95, 0.05, sim.P_NULL, 33).p_pass > 0.8


def test_caps_are_read_from_one_run() -> None:
    run = sim.simulate_cell(
        0.85, 0.25, sim.P_NULL, horizon=60, replicates=200, rng=np.random.default_rng(2)
    )
    rows = [sim.at_cap(run, 0.85, 0.25, sim.P_NULL, n) for n in sim.N_MAX]
    for row in rows:
        assert row.p_pass + row.p_cut + row.p_unresolved == pytest.approx(1.0)
        assert row.expected_pairs <= row.n_max
    passes = [row.p_pass for row in rows]
    assert passes == sorted(passes)
    n80 = sim.smallest_n_reaching(run, 0.8)
    if n80 is not None:
        assert sim.at_cap(run, 0.85, 0.25, sim.P_NULL, n80).p_pass >= 0.8
        assert sim.at_cap(run, 0.85, 0.25, sim.P_NULL, n80 - 1).p_pass < 0.8


@pytest.mark.parametrize(
    ("ub_fp", "lb_fp", "lb_fn", "expected"),
    [
        (0.19, 0.25, 0.25, "CUT_NO_LIFT"),
        (0.50, 0.20, 0.20, "A_PASSES_EARLY"),
        (0.50, 0.20, 0.19, "UNRESOLVED_CONTINUE"),
        (0.50, 0.19, 0.30, "UNRESOLVED_CONTINUE"),
    ],
)
def test_stop_rule(ub_fp: float, lb_fp: float, lb_fn: float, expected: str) -> None:
    assert sim.stop_rule(ub_fp=ub_fp, lb_fp=lb_fp, lb_fn=lb_fn) == expected
