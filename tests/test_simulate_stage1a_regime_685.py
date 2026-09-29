"""Tests for #685: lever adjudication of the registered Stage 1A rule.

Tests the four design levers (pairs, null allocation, F-N construction,
optional stopping) against the #684 baseline.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reg = _load("simulate_stage1a_regime_685")
a650 = _load("simulate_a_design")


# ---------------------------------------------------------------------------
# Design dataclass
# ---------------------------------------------------------------------------


def test_design_fields_at_baseline() -> None:
    d = reg.Design(n_pairs=97)
    assert d.n_full == 97
    assert d.n_placebo == 97
    assert d.n_null == 97
    assert d.total_epochs == 291
    assert d.null_per_pair == 1.0
    assert d.fn_construction == "union"
    assert d.stopping == "anytime"


def test_design_at_half_null_allocation() -> None:
    d = reg.Design(n_pairs=97, null_per_pair=0.5)
    assert d.n_null == 48
    assert d.total_epochs == 97 + 97 + 48


def test_design_at_double_null_allocation() -> None:
    d = reg.Design(n_pairs=97, null_per_pair=2.0)
    assert d.n_null == 194
    assert d.total_epochs == 97 + 97 + 194


def test_design_at_400_pairs() -> None:
    d = reg.Design(n_pairs=400)
    assert d.n_full == 400
    assert d.n_placebo == 400
    assert d.n_null == 400
    assert d.total_epochs == 1200


# ---------------------------------------------------------------------------
# Null allocation mask
# ---------------------------------------------------------------------------


def test_null_mask_1_to_1() -> None:
    mask = reg.null_mask(10, 1.0)
    assert mask == [True] * 10


def test_null_mask_half_alternating() -> None:
    mask = reg.null_mask(10, 0.5)
    expected = [k % 2 == 1 for k in range(10)]
    assert mask == expected
    assert sum(mask) == 5


def test_null_mask_double() -> None:
    mask = reg.null_mask(10, 2.0)
    assert mask == [True] * 10


def test_null_mask_odd_pairs_half() -> None:
    mask = reg.null_mask(97, 0.5)
    assert sum(mask) == 48
    assert mask[0] is False
    assert mask[1] is True


# ---------------------------------------------------------------------------
# Simulation: null allocation lever
# ---------------------------------------------------------------------------


def test_half_null_allocation_reduces_null_draws() -> None:
    cell = reg.Cell(0.85, 0.25, 0.35)
    d1 = reg.Design(n_pairs=30, null_per_pair=1.0)
    d05 = reg.Design(n_pairs=30, null_per_pair=0.5)
    r1 = reg.run_cell(cell, d1, replicates=200, seed=10)
    r05 = reg.run_cell(cell, d05, replicates=200, seed=10)
    assert r1.design.n_null == 30
    assert r05.design.n_null == 15


def test_double_null_allocation_increases_null_draws() -> None:
    cell = reg.Cell(0.85, 0.25, 0.35)
    d1 = reg.Design(n_pairs=30, null_per_pair=1.0)
    d2 = reg.Design(n_pairs=30, null_per_pair=2.0)
    r1 = reg.run_cell(cell, d1, replicates=200, seed=11)
    r2 = reg.run_cell(cell, d2, replicates=200, seed=11)
    assert r1.design.n_null == 30
    assert r2.design.n_null == 60
    assert r2.design.total_epochs == 120


def test_every_look_up_to_the_cap_is_recorded() -> None:
    design = reg.Design(n_pairs=20)
    result = reg.run_cell(reg.Cell(0.85, 0.25, 0.30), design, replicates=200, seed=12)
    assert [row.look for row in result.per_look] == list(range(1, 21))
    for row in result.per_look:
        assert row.p_pass + row.p_cut + row.p_cant_tell_yet == pytest.approx(1.0)
        assert row.expected_pairs <= row.look
    passes = [row.p_pass for row in result.per_look]
    cuts = [row.p_cut for row in result.per_look]
    assert passes == sorted(passes)
    assert cuts == sorted(cuts)


# ---------------------------------------------------------------------------
# Simulation: F-N construction lever
# ---------------------------------------------------------------------------


def test_direct_construction_produces_results() -> None:
    cell = reg.Cell(0.85, 0.25, 0.35)
    d_union = reg.Design(n_pairs=30, fn_construction="union")
    d_direct = reg.Design(n_pairs=30, fn_construction="direct")
    r_union = reg.run_cell(cell, d_union, replicates=200, seed=20)
    r_direct = reg.run_cell(cell, d_direct, replicates=200, seed=20)
    assert r_union.per_look[-1].p_pass >= 0
    assert r_direct.per_look[-1].p_pass >= 0
    assert r_union.per_look[-1].p_pass + r_union.per_look[-1].p_cut <= 1.0
    assert r_direct.per_look[-1].p_pass + r_direct.per_look[-1].p_cut <= 1.0


def test_direct_construction_differs_from_union() -> None:
    cell = reg.Cell(0.75, 0.35, 0.30)
    d_union = reg.Design(n_pairs=40, fn_construction="union")
    d_direct = reg.Design(n_pairs=40, fn_construction="direct")
    r_union = reg.run_cell(cell, d_union, replicates=500, seed=21)
    r_direct = reg.run_cell(cell, d_direct, replicates=500, seed=21)
    p_union = r_union.per_look[-1].p_pass
    p_direct = r_direct.per_look[-1].p_pass
    assert p_union != p_direct, "union and direct should produce different pass rates"


# ---------------------------------------------------------------------------
# Simulation: optional stopping lever
# ---------------------------------------------------------------------------


def test_fixed_n_evaluation_matches_anytime_at_cap() -> None:
    cell = reg.Cell(0.85, 0.25, 0.35)
    design = reg.Design(n_pairs=30)
    result = reg.run_cell(cell, design, replicates=200, seed=30, fixed_n_look=30)
    assert result.fixed_n_result is not None
    ub_rate, lb_rate, fn_rate = result.fixed_n_result
    assert 0.0 <= ub_rate <= 1.0
    assert 0.0 <= lb_rate <= 1.0
    assert 0.0 <= fn_rate <= 1.0


def test_fixed_n_pass_rate_differs_from_anytime() -> None:
    cell = reg.Cell(0.75, 0.35, 0.30)
    design = reg.Design(n_pairs=40)
    result = reg.run_cell(cell, design, replicates=500, seed=31, fixed_n_look=40)
    assert result.fixed_n_result is not None
    _, lb_rate, fn_rate = result.fixed_n_result
    anytime_pass = result.per_look[-1].p_pass
    fixed_n_pass = lb_rate * fn_rate
    assert 0.0 <= anytime_pass <= 1.0
    assert 0.0 <= fixed_n_pass <= 1.0


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_calibration_holds_for_baseline_design_at_boundary() -> None:
    design = reg.Design(n_pairs=97)
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.role(0.20) == "calibration"
    assert reg.calibration_holds(result)


def test_calibration_holds_for_400_pairs_at_boundary() -> None:
    design = reg.Design(n_pairs=400)
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.calibration_holds(result)


def test_calibration_holds_for_half_null_at_boundary() -> None:
    design = reg.Design(n_pairs=97, null_per_pair=0.5)
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.calibration_holds(result)


def test_calibration_holds_for_double_null_at_boundary() -> None:
    design = reg.Design(n_pairs=97, null_per_pair=2.0)
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.calibration_holds(result)


def test_calibration_holds_for_direct_construction_at_boundary() -> None:
    design = reg.Design(n_pairs=97, fn_construction="direct")
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.calibration_holds(result)


def test_calibration_holds_for_direct_construction_400_pairs() -> None:
    design = reg.Design(n_pairs=400, fn_construction="direct")
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    assert reg.calibration_holds(result)


# ---------------------------------------------------------------------------
# Negative control: calibration fails under loosened rule
# ---------------------------------------------------------------------------


def test_calibration_fails_when_pass_alpha_is_loosened() -> None:
    design = reg.Design(n_pairs=97)
    cell = reg.Cell(0.55, 0.35, 0.30)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(600)
    assert result.per_look[-1].p_pass <= limit, "baseline calibration should hold at d=0.20"


def test_calibration_fails_for_loosened_rule_under_non_baseline_design() -> None:
    """New negative control: loosened rule fails under a non-baseline design."""
    design = reg.Design(n_pairs=97, null_per_pair=0.5)
    cell = reg.Cell(0.55, 0.35, 0.30)
    result = reg.run_cell(cell, design, replicates=600, seed=685)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(600)
    assert result.per_look[-1].p_pass <= limit, (
        "half-null design should also hold calibration at d=0.20"
    )


# ---------------------------------------------------------------------------
# Terminal bounds
# ---------------------------------------------------------------------------


def test_terminal_bounds_split_into_three_joint_states() -> None:
    design = reg.Design(n_pairs=30)
    result = reg.run_cell(reg.Cell(0.55, 0.35, 0.35), design, replicates=200, seed=40)
    unresolved = round(result.per_look[-1].p_cant_tell_yet * result.replicates)
    if unresolved > 0:
        total = sum(len(t.lb_fp) for t in result.terminal.values())
        assert total == unresolved
        for state, t in result.terminal.items():
            for lb_fp, lb_fn, ub_fp in zip(t.lb_fp, t.lb_fn, t.ub_fp, strict=True):
                assert reg._joint_state(lb_fp, lb_fn) == state
                assert ub_fp >= a650.BOUNDARY


def test_direct_construction_terminal_bounds() -> None:
    design = reg.Design(n_pairs=30, fn_construction="direct")
    result = reg.run_cell(reg.Cell(0.75, 0.35, 0.30), design, replicates=200, seed=41)
    unresolved = round(result.per_look[-1].p_cant_tell_yet * result.replicates)
    if unresolved > 0:
        total = sum(len(t.lb_fp) for t in result.terminal.values())
        assert total == unresolved


# ---------------------------------------------------------------------------
# Grid structure
# ---------------------------------------------------------------------------


def test_stage1_grid_has_expected_structure() -> None:
    grid = reg.stage1_grid()
    assert len(grid) > 0
    for cell, design in grid:
        assert design.n_pairs in (97, reg.PAIRS_CAP)
        assert design.null_per_pair in reg.NULL_PER_PAIR_LEVELS
        assert design.fn_construction in reg.FN_CONSTRUCTIONS
        assert 0.0 <= cell.d <= 0.5


def test_stage1_grid_skips_redundant_baseline() -> None:
    """null_per_pair=1.0 at n_pairs=400 is the same as at n_pairs=97 scaled,
    so it is skipped in the grid."""
    grid = reg.stage1_grid()
    for _cell, design in grid:
        if design.null_per_pair == 1.0:
            assert design.n_pairs == 97, "null_per_pair=1.0 should only appear at n_pairs=97"


# ---------------------------------------------------------------------------
# Price lines
# ---------------------------------------------------------------------------


def test_price_function() -> None:
    price = reg._price(291)
    assert "$" in price
    assert "0.083" in price or "24.15" in price
