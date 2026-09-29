"""Tests for #684: the registered Stage 1A rule at the observed baselines, 97 pairs at 1:1:1."""

from __future__ import annotations

import importlib.util
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


reg = _load("simulate_stage1a_regime")


def test_design_fields_are_written_out_for_the_observed_run() -> None:
    design = reg.Design(n_pairs=97)
    assert design.n_full == 97
    assert design.n_placebo == 97
    assert design.n_null == 97
    assert design.total_epochs == 291
    assert design.null_per_pair == 1.0


def test_the_null_rate_is_a_per_cell_input() -> None:
    design = reg.Design(n_pairs=20)
    easy = reg.run_cell(reg.Cell(0.95, 0.05, 0.0), design, replicates=100, seed=1)
    blocked = reg.run_cell(reg.Cell(0.95, 0.05, 1.0), design, replicates=100, seed=1)
    assert easy.per_look[-1].p_pass > 0.5
    assert blocked.per_look[-1].p_pass == 0.0


def test_every_look_up_to_the_cap_is_recorded() -> None:
    design = reg.Design(n_pairs=30)
    result = reg.run_cell(reg.Cell(0.85, 0.25, 0.30), design, replicates=200, seed=2)
    assert [row.look for row in result.per_look] == list(range(1, 31))
    for row in result.per_look:
        assert row.p_pass + row.p_cut + row.p_cant_tell_yet == pytest.approx(1.0)
        assert row.expected_pairs <= row.look
    passes = [row.p_pass for row in result.per_look]
    cuts = [row.p_cut for row in result.per_look]
    assert passes == sorted(passes)
    assert cuts == sorted(cuts)
    assert passes[-1] > passes[9]


def _engine_first_stop(full: list[int], placebo: list[int], null: list[int]) -> tuple[int, str]:
    """The registered rule from the engine's bound called at every look, with no grid shortcut."""
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound as bound

    sim = reg.a650
    half = sim.PASS_ALPHA / 2
    for k in range(1, len(full) + 1):
        xs_fp = sim.paired_xs(full[:k], placebo[:k])
        xs_f = [float(v) for v in full[:k]]
        xs_n = [float(v) for v in null[:k]]
        outcome = sim.stop_rule(
            ub_fp=2 * bound(xs_fp, alpha=sim.FUTILITY_ALPHA, side="upper") - 1,
            lb_fp=2 * bound(xs_fp, alpha=sim.PASS_ALPHA, side="lower") - 1,
            lb_fn=bound(xs_f, alpha=half, side="lower") - bound(xs_n, alpha=half, side="upper"),
        )
        if outcome != "UNRESOLVED_CONTINUE":
            return k, str(outcome)
    return len(full) + 1, "UNRESOLVED_CONTINUE"


def _regime_streams(horizon: int, per_rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(6841)
    rates = [(0.99, 0.01, 0.25), (0.55, 0.35, 0.35), (0.20, 0.60, 0.35), (0.95, 0.30, 0.40)]
    arms = [
        [(rng.random((per_rate, horizon)) < p).astype(np.int64) for p in rate] for rate in rates
    ]
    return tuple(np.concatenate([arm[i] for arm in arms]) for i in range(3))  # type: ignore[return-value]


def test_every_decision_equals_the_engine_bound_in_the_observed_regime() -> None:
    full, placebo, null = _regime_streams(horizon=30, per_rate=4)
    run = reg.a650.simulate_streams(full, placebo, null)
    seen = set()
    for r in range(full.shape[0]):
        stop, outcome = _engine_first_stop(full[r].tolist(), placebo[r].tolist(), null[r].tolist())
        seen.add(outcome)
        assert int(run.stop_at[r]) == stop, r
        assert bool(run.passed[r]) == (outcome == "A_PASSES_EARLY"), r
        assert bool(run.cut[r]) == (outcome == "CUT_NO_LIFT"), r
    assert {"A_PASSES_EARLY", "CUT_NO_LIFT", "UNRESOLVED_CONTINUE"} <= seen


def test_terminal_bounds_equal_the_engine_bounds() -> None:
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound as bound

    full, placebo, null = _regime_streams(horizon=40, per_rate=5)
    got = reg.terminal_bounds(full, placebo, null)
    half = reg.a650.PASS_ALPHA / 2
    for r in range(full.shape[0]):
        xs_fp = reg.a650.paired_xs(full[r].tolist(), placebo[r].tolist())
        xs_f = [float(v) for v in full[r]]
        xs_n = [float(v) for v in null[r]]
        lb_fp = 2 * bound(xs_fp, alpha=reg.a650.PASS_ALPHA, side="lower") - 1
        ub_fp = 2 * bound(xs_fp, alpha=reg.a650.FUTILITY_ALPHA, side="upper") - 1
        lb_fn = bound(xs_f, alpha=half, side="lower") - bound(xs_n, alpha=half, side="upper")
        assert got.lb_fp[r] == pytest.approx(lb_fp, abs=1e-9), r
        assert got.ub_fp[r] == pytest.approx(ub_fp, abs=1e-9), r
        assert got.lb_fn[r] == pytest.approx(lb_fn, abs=1e-9), r


@pytest.mark.parametrize(
    ("lb_fp", "lb_fn", "expected"),
    [
        (0.20, 0.10, "fp_passes_fn_fails"),
        (0.10, 0.20, "fn_passes_fp_fails"),
        (0.19, 0.19, "neither_passes"),
    ],
)
def test_joint_terminal_state(lb_fp: float, lb_fn: float, expected: str) -> None:
    assert reg.joint_state(lb_fp=lb_fp, lb_fn=lb_fn) == expected


def test_replicates_unresolved_at_the_cap_split_into_the_three_joint_states() -> None:
    design = reg.Design(n_pairs=40)
    result = reg.run_cell(reg.Cell(0.55, 0.35, 0.35), design, replicates=150, seed=3)
    unresolved = round(result.per_look[-1].p_cant_tell_yet * result.replicates)
    assert unresolved > 0
    assert sum(len(t.lb_fp) for t in result.terminal.values()) == unresolved
    for state, t in result.terminal.items():
        for lb_fp, lb_fn, ub_fp in zip(t.lb_fp, t.lb_fn, t.ub_fp, strict=True):
            assert reg.joint_state(lb_fp=lb_fp, lb_fn=lb_fn) == state
            assert ub_fp >= reg.a650.BOUNDARY


def _boundary_pass_rate(pass_alpha: float, replicates: int, p_null: float = 0.35) -> float:
    result = reg.run_cell(
        reg.Cell(0.55, 0.35, p_null),
        reg.Design(n_pairs=97),
        replicates=replicates,
        seed=reg.SEED,
        pass_alpha=pass_alpha,
    )
    return float(result.per_look[-1].p_pass)


def test_the_observed_regime_boundary_cell_passes_at_most_the_pass_alpha() -> None:
    replicates = 600
    assert reg.role(0.20) == "calibration"
    assert _boundary_pass_rate(reg.a650.PASS_ALPHA, replicates) <= reg.a650.PASS_ALPHA + (
        reg.a650.calibration_tolerance(replicates)
    )


def test_the_calibration_check_fails_in_this_regime_when_the_pass_test_is_loosened() -> None:
    # Off the diagonal (p_N = 0.30), so F - N sits above its margin and the loosened F - P test
    # is what over-passes. On the diagonal both conditions sit at their margin at once.
    replicates = 600
    assert _boundary_pass_rate(0.6, replicates, p_null=0.30) > reg.a650.PASS_ALPHA + (
        reg.a650.calibration_tolerance(replicates)
    )


def test_headline_is_the_smallest_grid_effect_reaching_the_target() -> None:
    curve = {0.20: 0.01, 0.25: 0.30, 0.30: 0.79, 0.35: 0.80, 0.40: 0.95}
    assert reg.smallest_d_reaching(curve, 0.8) == 0.35
    assert reg.smallest_d_reaching({0.20: 0.0, 0.40: 0.5}, 0.8) is None
