"""Tests for #685: lever adjudication of the registered Stage 1A rule.

Tests the four design levers (pairs, null allocation, F-N construction,
optional stopping) against the #684 baseline.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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


def test_null_allocation_uses_exactly_the_declared_observations() -> None:
    assert reg.null_draw_counts(97, 0.5).sum() == reg.Design(97, 0.5).n_null
    assert reg.null_draw_counts(97, 1.0).sum() == reg.Design(97, 1.0).n_null
    assert reg.null_draw_counts(97, 2.0).sum() == reg.Design(97, 2.0).n_null
    assert reg.null_draw_counts(4, 0.5).tolist() == [0, 1, 0, 1]
    assert reg.null_draw_counts(4, 2.0).tolist() == [2, 2, 2, 2]


def test_half_null_allocation_handles_a_cap_before_its_first_null_epoch() -> None:
    result = reg.run_cell(
        reg.Cell(0.55, 0.35, 0.35), reg.Design(n_pairs=1, null_per_pair=0.5), replicates=10, seed=11
    )
    assert [row.look for row in result.per_look] == [1]


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


def test_direct_terminal_bounds_equal_the_engine_bounds() -> None:
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    full = np.array([[1, 1, 0, 1], [0, 1, 1, 0]], dtype=np.int64)
    placebo = np.array([[0, 1, 0, 0], [1, 0, 0, 1]], dtype=np.int64)
    xs_fn = np.array([[1.0, 0.5, 0.0], [0.5, 1.0, 0.5]], dtype=np.float64)
    lb_fp, ub_fp, lb_fn = reg._terminal_bounds_direct(full, placebo, xs_fn, a650.PASS_ALPHA)

    for r in range(len(full)):
        xs_fp = ((full[r] - placebo[r] + 1) / 2.0).tolist()
        assert lb_fp[r] == pytest.approx(
            2 * one_sided_betting_bound(xs_fp, alpha=a650.PASS_ALPHA, side="lower") - 1,
            abs=1e-9,
        )
        assert ub_fp[r] == pytest.approx(
            2 * one_sided_betting_bound(xs_fp, alpha=a650.FUTILITY_ALPHA, side="upper") - 1,
            abs=1e-9,
        )
        assert lb_fn[r] == pytest.approx(
            2 * one_sided_betting_bound(xs_fn[r].tolist(), alpha=a650.PASS_ALPHA, side="lower") - 1,
            abs=1e-9,
        )


def _engine_stop_at(
    full: list[int],
    placebo: list[int],
    null_all: list[list[int]],
    design: Any,
) -> tuple[int, str]:
    """Apply the stated rule with the engine bound, without the grid shortcut."""
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

    null_draws = reg.null_draw_counts(len(full), design.null_per_pair)
    null_observations: list[float] = []
    direct_observations: list[float] = []
    half = a650.PASS_ALPHA / 2
    for k, (f, _p) in enumerate(zip(full, placebo, strict=True)):
        xs_fp = a650.paired_xs(full[: k + 1], placebo[: k + 1])
        for draw in range(null_draws[k]):
            null_observations.append(float(null_all[k][draw]))
        if null_draws[k]:
            mean_null = sum(null_all[k][: null_draws[k]]) / null_draws[k]
            direct_observations.append((f - mean_null + 1) / 2)
        if design.fn_construction == "direct":
            lb_fn = (
                2
                * one_sided_betting_bound(direct_observations, alpha=a650.PASS_ALPHA, side="lower")
                - 1
            )
        else:
            lb_fn = one_sided_betting_bound(full[: k + 1], alpha=half, side="lower") - (
                one_sided_betting_bound(null_observations, alpha=half, side="upper")
            )
        outcome = a650.stop_rule(
            ub_fp=2 * one_sided_betting_bound(xs_fp, alpha=a650.FUTILITY_ALPHA, side="upper") - 1,
            lb_fp=2 * one_sided_betting_bound(xs_fp, alpha=a650.PASS_ALPHA, side="lower") - 1,
            lb_fn=lb_fn,
        )
        if outcome != "UNRESOLVED_CONTINUE":
            return k + 1, str(outcome)
    return len(full) + 1, "UNRESOLVED_CONTINUE"


@pytest.mark.parametrize("null_per_pair", reg.NULL_PER_PAIR_LEVELS)
@pytest.mark.parametrize("fn_construction", reg.FN_CONSTRUCTIONS)
def test_every_decision_equals_the_engine_bound_for_each_stage1_design(
    null_per_pair: float, fn_construction: str
) -> None:
    cell = reg.Cell(0.85, 0.25, 0.30)
    design = reg.Design(n_pairs=30, null_per_pair=null_per_pair, fn_construction=fn_construction)
    replicates = 16
    rng = reg.cell_rng(685, cell)
    full = (rng.random((replicates, design.n_pairs)) < cell.p_full).astype(np.int64)
    placebo = (rng.random((replicates, design.n_pairs)) < cell.p_placebo).astype(np.int64)
    null_all = (rng.random((replicates, design.n_pairs, 2)) < cell.p_null).astype(np.int64)
    expected = [
        _engine_stop_at(full[r].tolist(), placebo[r].tolist(), null_all[r].tolist(), design)
        for r in range(replicates)
    ]

    result = reg.run_cell(cell, design, replicates=replicates, seed=685)

    for k, row in enumerate(result.per_look, start=1):
        assert row.p_pass == pytest.approx(
            sum(stop <= k and outcome == "A_PASSES_EARLY" for stop, outcome in expected)
            / replicates
        )
        assert row.p_cut == pytest.approx(
            sum(stop <= k and outcome == "CUT_NO_LIFT" for stop, outcome in expected) / replicates
        )


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "design",
    sorted(
        {design for _cell, design in reg.stage1_grid()},
        key=repr,
    ),
)
def test_calibration_holds_for_every_stage1_design_at_boundary(design: Any) -> None:
    cell = reg.Cell(0.55, 0.35, 0.35)
    result = reg.run_cell(cell, design, replicates=200, seed=685)
    assert reg.role(0.20) == "calibration"
    assert reg.calibration_holds(result)


# ---------------------------------------------------------------------------
# Negative control: calibration fails under loosened rule
# ---------------------------------------------------------------------------


def test_calibration_fails_when_pass_alpha_is_loosened() -> None:
    design = reg.Design(n_pairs=97)
    cell = reg.Cell(0.55, 0.35, 0.30)
    result = reg.run_cell(cell, design, replicates=600, seed=685, pass_alpha=0.6)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(600)
    assert result.per_look[-1].p_pass > limit


def test_calibration_fails_for_loosened_rule_under_non_baseline_design() -> None:
    """New negative control: loosened rule fails under a non-baseline design."""
    design = reg.Design(n_pairs=97, null_per_pair=0.5)
    cell = reg.Cell(0.55, 0.35, 0.30)
    result = reg.run_cell(cell, design, replicates=600, seed=685, pass_alpha=0.6)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(600)
    assert result.per_look[-1].p_pass > limit


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
        assert design.total_epochs in reg.EPOCH_BUDGETS
        assert design.null_per_pair in reg.NULL_PER_PAIR_LEVELS
        assert design.fn_construction in reg.FN_CONSTRUCTIONS
        assert 0.0 <= cell.d <= 0.5


def test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations() -> None:
    expected_pairs = {
        300: {0.5: 120, 1.0: 100, 2.0: 75},
        1200: {0.5: 480, 1.0: 400, 2.0: 300},
    }
    for epoch_budget in reg.EPOCH_BUDGETS:
        designs = {
            design for _cell, design in reg.stage1_grid() if design.total_epochs == epoch_budget
        }
        assert {design.null_per_pair for design in designs} == set(reg.NULL_PER_PAIR_LEVELS)
        assert {design.total_epochs for design in designs} == {epoch_budget}
        assert {
            design.null_per_pair: design.n_pairs
            for design in designs
            if design.fn_construction == "union"
        } == expected_pairs[epoch_budget]


def test_stage1_grid_includes_the_400_pair_baseline() -> None:
    grid = reg.stage1_grid()
    assert any(
        design.n_pairs == 400 and design.null_per_pair == 1.0 and design.fn_construction == "union"
        for _cell, design in grid
    )


# ---------------------------------------------------------------------------
# Price lines
# ---------------------------------------------------------------------------


def test_price_function() -> None:
    price = reg._price(291)
    assert "$" in price
    assert "0.083" in price or "24.15" in price


# ---------------------------------------------------------------------------
# Requirement 4: E[total epochs] and expected-spend price beside the cap price
# ---------------------------------------------------------------------------

_DESIGN_FIELDS = (
    "n_full",
    "n_placebo",
    "n_null",
    "total_epochs",
    "null_per_pair",
    "fn_construction",
    "stopping",
)


def _split_tsv(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.rstrip("\n").split("\n")
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def _parse_spend(cell: str) -> tuple[float, float]:
    lo_str, hi_str = cell.removeprefix("$").split("-$")
    return float(lo_str), float(hi_str)


def test_price_constants_are_the_registered_rates() -> None:
    """M5/M6: the list rates and the cap rate are the registered numbers."""
    assert reg._PRICE_LO == 0.083
    assert reg._PRICE_HI == 0.087
    assert reg._PRICE_CAP == 0.30


def test_cap_price_string_carries_the_cap_rate() -> None:
    """M6: the cap price is total_epochs * $0.30, not a shifted decimal."""
    price = reg._price(100)
    assert "(cap $30.00)" in price
    assert f"${100 * 0.083:.2f}" in price
    assert f"${100 * 0.087:.2f}" in price


def test_expected_spend_string_carries_both_list_rates() -> None:
    """M5: expected spend is E[total epochs] x $0.083 and x $0.087."""
    spend = reg._expected_spend(200.0)
    assert spend == f"${200.0 * 0.083:.2f}-${200.0 * 0.087:.2f}"
    assert spend == "$16.60-$17.40"


def test_every_per_look_row_carries_expected_epochs_and_expected_spend() -> None:
    design = reg.Design(n_pairs=20, null_per_pair=1.0)
    result = reg.run_cell(reg.Cell(0.85, 0.25, 0.30), design, replicates=200, seed=13)
    cols, rows = _split_tsv(reg.per_look_tsv([result]))
    for name in (*_DESIGN_FIELDS, "replicates", "se_pass", "expected_epochs", "expected_spend"):
        assert name in cols, f"per_look.tsv is missing the {name} column"
    i_price = len(cols) - 1
    i_pairs, i_epochs, i_spend = (
        cols.index(name) for name in ("expected_pairs", "expected_epochs", "expected_spend")
    )
    assert cols[i_price] == "price_range"
    for row in rows:
        assert len(row) == len(cols)
        expected_pairs = float(row[i_pairs])
        expected_epochs = float(row[i_epochs])
        assert expected_epochs == pytest.approx(3.0 * expected_pairs, abs=0.01)
        assert 0.0 < expected_epochs <= design.total_epochs
        lo, hi = _parse_spend(row[i_spend])
        assert lo == pytest.approx(expected_epochs * reg._PRICE_LO, abs=0.01)
        assert hi == pytest.approx(expected_epochs * reg._PRICE_HI, abs=0.01)
        assert "cap $" in row[i_price]
    cap_lo = design.total_epochs * reg._PRICE_LO
    assert _parse_spend(rows[0][i_spend])[0] < cap_lo


def test_expected_epochs_track_the_null_allocation_profile() -> None:
    cell = reg.Cell(0.85, 0.25, 0.30)
    for null_per_pair, epochs_per_pair in ((1.0, 3.0), (2.0, 4.0)):
        design = reg.Design(n_pairs=20, null_per_pair=null_per_pair)
        result = reg.run_cell(cell, design, replicates=150, seed=15)
        cols, rows = _split_tsv(reg.per_look_tsv([result]))
        i_pairs, i_epochs = cols.index("expected_pairs"), cols.index("expected_epochs")
        for row in rows:
            assert float(row[i_epochs]) == pytest.approx(
                epochs_per_pair * float(row[i_pairs]), abs=0.01
            )
    half = reg.Design(n_pairs=20, null_per_pair=0.5)
    result = reg.run_cell(cell, half, replicates=150, seed=15)
    cols, rows = _split_tsv(reg.per_look_tsv([result]))
    i_pairs, i_epochs = cols.index("expected_pairs"), cols.index("expected_epochs")
    for row in rows:
        expected_pairs = float(row[i_pairs])
        expected_epochs = float(row[i_epochs])
        assert 2.5 * expected_pairs - 0.5 <= expected_epochs <= 2.5 * expected_pairs + 1e-9


def test_every_terminal_row_carries_mc_se_expected_epochs_and_cap_price() -> None:
    design = reg.Design(n_pairs=20, null_per_pair=1.0)
    result = reg.run_cell(reg.Cell(0.55, 0.35, 0.35), design, replicates=400, seed=14)
    cols, rows = _split_tsv(reg.terminal_tsv([result]))
    for name in (*_DESIGN_FIELDS, "replicates", "se_share", "expected_epochs", "expected_spend"):
        assert name in cols, f"terminal_states.tsv is missing the {name} column"
    i_share, i_se = cols.index("share"), cols.index("se_share")
    i_spend, i_price = cols.index("expected_spend"), cols.index("price_range")
    i_epochs, i_reps = cols.index("expected_epochs"), cols.index("replicates")
    for row in rows:
        assert len(row) == len(cols)
        share, se, reps = float(row[i_share]), float(row[i_se]), int(row[i_reps])
        assert se == pytest.approx((share * (1.0 - share) / reps) ** 0.5, abs=1e-6)
        expected_epochs = float(row[i_epochs])
        assert expected_epochs == pytest.approx(result.per_look[-1].expected_epochs, abs=0.001)
        lo, hi = _parse_spend(row[i_spend])
        assert lo == pytest.approx(expected_epochs * reg._PRICE_LO, abs=0.01)
        assert hi == pytest.approx(expected_epochs * reg._PRICE_HI, abs=0.01)
        assert "cap $" in row[i_price]


def test_surface_rows_carry_expected_epochs_and_expected_spend_beside_the_cap_price() -> None:
    design = reg.Design(n_pairs=20)
    result = reg.run_cell(reg.Cell(0.85, 0.25, 0.30), design, replicates=150, seed=16)
    lines = reg._surface_lines([result])
    header = lines[0]
    assert "E[epochs]" in header
    assert "expected spend" in header
    assert header.rstrip("| ").endswith("price")
    header_cells = header.strip("| ").split(" | ")
    row = lines[2].strip("| ").split(" | ")
    assert len(row) == len(header_cells)
    epochs_index = header_cells.index("E[epochs]")
    assert float(row[epochs_index]) == pytest.approx(result.per_look[-1].expected_epochs, abs=0.05)
    spend_index = header_cells.index("expected spend")
    lo, hi = _parse_spend(row[spend_index].strip())
    expected_epochs = result.per_look[-1].expected_epochs
    assert lo == pytest.approx(expected_epochs * reg._PRICE_LO, abs=0.05)
    assert hi == pytest.approx(expected_epochs * reg._PRICE_HI, abs=0.05)
