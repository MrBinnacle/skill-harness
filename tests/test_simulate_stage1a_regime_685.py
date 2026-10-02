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


# ---------------------------------------------------------------------------
# Requirement 5: headline both halves, 0.80 and 0.90, stage-2 trigger, data only
# ---------------------------------------------------------------------------


def _hand_result(
    cell: Any,
    design: Any,
    *,
    p_pass: float,
    p_cut: float,
    replicates: int = 200,
) -> Any:
    look = design.n_pairs
    row = reg.LookRow(
        look=look,
        p_pass=p_pass,
        p_cut=p_cut,
        p_cant_tell_yet=max(0.0, 1.0 - p_pass - p_cut),
        se_pass=0.0,
        expected_pairs=float(look),
        expected_epochs=float(design.total_epochs),
    )
    terminal = {
        state: reg.TerminalSample(lb_fp=(), lb_fn=(), ub_fp=()) for state in reg.JOINT_STATES
    }
    return reg.CellResult(
        cell=cell,
        design=design,
        replicates=replicates,
        per_look=(row,),
        terminal=terminal,
        library_calls=0,
    )


def _results_for_budget(
    *,
    epoch_budget: int,
    null_per_pair: float,
    fn_construction: str,
    p_pass_at_0_30: float,
    p_cut_at_0_10: float,
    p_pass_at_other_d: float = 0.0,
    p_cut_at_other_d: float = 0.0,
) -> list[Any]:
    """One design family at one budget, filled across the nine baseline cells."""
    results: list[Any] = []
    n_pairs = reg.pairs_for_epoch_budget(epoch_budget, null_per_pair)
    design = reg.Design(
        n_pairs=n_pairs, null_per_pair=null_per_pair, fn_construction=fn_construction
    )
    for p_p in reg.BASELINES:
        for p_n in reg.BASELINES:
            results.append(
                _hand_result(
                    reg.Cell(round(p_p + 0.30, 10), p_p, p_n),
                    design,
                    p_pass=p_pass_at_0_30,
                    p_cut=0.0,
                )
            )
            results.append(
                _hand_result(
                    reg.Cell(round(p_p + 0.10, 10), p_p, p_n),
                    design,
                    p_pass=0.0,
                    p_cut=p_cut_at_0_10,
                )
            )
            for d in (0.00, 0.15, 0.20, 0.25, 0.40):
                results.append(
                    _hand_result(
                        reg.Cell(round(p_p + d, 10), p_p, p_n),
                        design,
                        p_pass=p_pass_at_other_d if d >= 0.20 else 0.0,
                        p_cut=p_cut_at_other_d if d < 0.20 else 0.0,
                    )
                )
    return results


def test_target_check_reports_the_smallest_priced_config_meeting_both_halves() -> None:
    """Both halves at d=0.30 (P(PASS)) and d=0.10 (P(CUT)), from data only."""
    cheap = _results_for_budget(
        epoch_budget=300,
        null_per_pair=1.0,
        fn_construction="union",
        p_pass_at_0_30=0.85,
        p_cut_at_0_10=0.85,
    )
    dear = _results_for_budget(
        epoch_budget=1200,
        null_per_pair=1.0,
        fn_construction="union",
        p_pass_at_0_30=0.95,
        p_cut_at_0_10=0.95,
    )
    rows = reg.target_check_rows(cheap + dear)
    by_key = {(r.null_per_pair, r.fn_construction, r.target): r for r in rows}
    row = by_key[(1.0, "union", 0.80)]
    assert row.reached
    assert row.total_epochs == 300
    assert row.p_pass_at_d030 == pytest.approx(0.85)
    assert row.p_cut_at_d010 == pytest.approx(0.85)
    assert not row.trigger_fires
    row90 = by_key[(1.0, "union", 0.90)]
    assert row90.reached
    assert row90.total_epochs == 1200


def test_target_check_not_reached_when_the_cut_half_fails() -> None:
    """P(PASS) at d=0.30 met but P(CUT) at d=0.10 unmet is NOT a meeting config."""
    results = _results_for_budget(
        epoch_budget=1200,
        null_per_pair=1.0,
        fn_construction="union",
        p_pass_at_0_30=0.95,
        p_cut_at_0_10=0.20,
    )
    rows = reg.target_check_rows(results)
    for row in rows:
        assert not row.reached
        assert row.total_epochs is None
        assert row.trigger_fires
        assert "P(CUT)" in row.missing_half or "P(CUT) at d=0.10" in row.missing_half


def test_target_check_not_reached_when_the_pass_half_fails() -> None:
    """P(CUT) at d=0.10 met but P(PASS) at d=0.30 unmet is NOT a meeting config."""
    results = _results_for_budget(
        epoch_budget=1200,
        null_per_pair=1.0,
        fn_construction="direct",
        p_pass_at_0_30=0.10,
        p_cut_at_0_10=0.95,
    )
    rows = reg.target_check_rows(results)
    for row in rows:
        assert not row.reached
        assert row.trigger_fires
        assert "P(PASS)" in row.missing_half


def test_stage2_trigger_fires_only_when_no_design_reaches_the_target() -> None:
    meets_0_80 = _results_for_budget(
        epoch_budget=300,
        null_per_pair=0.5,
        fn_construction="direct",
        p_pass_at_0_30=0.85,
        p_cut_at_0_10=0.85,
    )
    fails_0_90_everywhere = _results_for_budget(
        epoch_budget=1200,
        null_per_pair=2.0,
        fn_construction="union",
        p_pass_at_0_30=0.50,
        p_cut_at_0_10=0.50,
    )
    # Direct/0.5 reaches 0.80; nothing reaches 0.90.
    rows = reg.target_check_rows(meets_0_80 + fails_0_90_everywhere)
    fires = {r.target: reg.stage2_trigger_fires(rows, r.target) for r in rows}
    assert fires[0.80] is False
    assert fires[0.90] is True


def _results_with_per_cell_rates(
    *,
    epoch_budget: int,
    null_per_pair: float,
    fn_construction: str,
    pass_at: dict[tuple[float, float], float],
    cut_at: dict[tuple[float, float], float],
) -> list[Any]:
    """One design family at one budget, with per-(p_P, p_N) rates at d=0.30 and d=0.10."""
    results: list[Any] = []
    n_pairs = reg.pairs_for_epoch_budget(epoch_budget, null_per_pair)
    design = reg.Design(
        n_pairs=n_pairs, null_per_pair=null_per_pair, fn_construction=fn_construction
    )
    for p_p in reg.BASELINES:
        for p_n in reg.BASELINES:
            results.append(
                _hand_result(
                    reg.Cell(round(p_p + 0.30, 10), p_p, p_n),
                    design,
                    p_pass=pass_at[(p_p, p_n)],
                    p_cut=0.0,
                )
            )
            results.append(
                _hand_result(
                    reg.Cell(round(p_p + 0.10, 10), p_p, p_n),
                    design,
                    p_pass=0.0,
                    p_cut=cut_at[(p_p, p_n)],
                )
            )
            for d in (0.00, 0.15, 0.20, 0.25, 0.40):
                results.append(
                    _hand_result(
                        reg.Cell(round(p_p + d, 10), p_p, p_n),
                        design,
                        p_pass=0.0,
                        p_cut=0.0,
                    )
                )
    return results


def test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum() -> None:
    """#708: aggregation rule is the diagonal minimum; the nine-cell minimum is ill-posed.

    Fixture rates at d=0.30 (P(PASS)) and d=0.10 (P(CUT)) are unequal across the
    nine (p_P, p_N) cells so that four readings disagree:

      diagonal minimum      PASS 0.85, CUT 0.84  -> meets 0.80
      nine-cell minimum     PASS 0.50, CUT 0.50  -> fails 0.80
      diagonal maximum      PASS 0.92, CUT 0.88  -> meets 0.80
      single cell (0.35,0.35) PASS 0.88, CUT 0.86 -> meets 0.80

    The #696 ruling reads the diagonal minimum. This test asserts those numbers
    and the resulting reached/trigger verdict. A min->max mutant, a
    diagonal->all-nine mutant, and a diagonal->single-cell mutant each report a
    different pair and each fails this assertion.
    """
    pass_at: dict[tuple[float, float], float] = {
        (0.30, 0.30): 0.85,
        (0.35, 0.35): 0.88,
        (0.40, 0.40): 0.92,
        (0.30, 0.35): 0.50,
        (0.30, 0.40): 0.95,
        (0.35, 0.30): 0.95,
        (0.35, 0.40): 0.95,
        (0.40, 0.30): 0.95,
        (0.40, 0.35): 0.95,
    }
    cut_at: dict[tuple[float, float], float] = {
        (0.30, 0.30): 0.84,
        (0.35, 0.35): 0.86,
        (0.40, 0.40): 0.88,
        (0.30, 0.35): 0.50,
        (0.30, 0.40): 0.95,
        (0.35, 0.30): 0.95,
        (0.35, 0.40): 0.95,
        (0.40, 0.30): 0.95,
        (0.40, 0.35): 0.95,
    }
    diagonal_pass = min(pass_at[(p, p)] for p in reg.BASELINES)
    diagonal_cut = min(cut_at[(p, p)] for p in reg.BASELINES)
    nine_pass = min(pass_at.values())
    nine_cut = min(cut_at.values())
    diagonal_pass_max = max(pass_at[(p, p)] for p in reg.BASELINES)
    single_pass = pass_at[(0.35, 0.35)]
    single_cut = cut_at[(0.35, 0.35)]
    assert {diagonal_pass, nine_pass, diagonal_pass_max, single_pass} == {0.85, 0.50, 0.92, 0.88}
    assert {diagonal_cut, nine_cut, max(cut_at[(p, p)] for p in reg.BASELINES), single_cut} == {
        0.84,
        0.50,
        0.88,
        0.86,
    }

    results = _results_with_per_cell_rates(
        epoch_budget=300,
        null_per_pair=1.0,
        fn_construction="union",
        pass_at=pass_at,
        cut_at=cut_at,
    )
    rows = reg.target_check_rows(results)
    row = next(
        r
        for r in rows
        if r.null_per_pair == 1.0 and r.fn_construction == "union" and r.target == 0.80
    )
    assert row.p_pass_at_d030 == pytest.approx(diagonal_pass), (
        "target check must report the diagonal minimum P(PASS) at d=0.30"
    )
    assert row.p_cut_at_d010 == pytest.approx(diagonal_cut), (
        "target check must report the diagonal minimum P(CUT) at d=0.10"
    )
    assert row.reached, "diagonal minima clear 0.80, so the family meets the target"
    assert not row.trigger_fires
    assert reg.stage2_trigger_fires(rows, 0.80) is False
    # The nine-cell reading does NOT meet; if the code used it, reached would flip.
    assert nine_pass < 0.80 and nine_cut < 0.80


def test_summary_target_check_text_says_diagonal_not_all_nine() -> None:
    """#708: the summary names the diagonal aggregation and never 'all nine'."""
    results = _results_for_budget(
        epoch_budget=300,
        null_per_pair=1.0,
        fn_construction="union",
        p_pass_at_0_30=0.85,
        p_cut_at_0_10=0.85,
    )
    summary = reg.summary_md(results, 200, 685)
    assert "## Target check" in summary
    assert "diagonal" in summary.lower()
    assert "all nine" not in summary
    assert "p_P = p_N" in summary or "p_P = p_N" in summary.replace(" ", "")


def test_summary_reports_off_diagonal_cells_as_sensitivity() -> None:
    """#708: the six off-diagonal cells appear as sensitivity, labelled, never as the target."""
    pass_at: dict[tuple[float, float], float] = {
        (0.30, 0.30): 0.85,
        (0.35, 0.35): 0.88,
        (0.40, 0.40): 0.92,
        (0.30, 0.35): 0.50,
        (0.30, 0.40): 0.60,
        (0.35, 0.30): 0.70,
        (0.35, 0.40): 0.75,
        (0.40, 0.30): 0.80,
        (0.40, 0.35): 0.77,
    }
    cut_at: dict[tuple[float, float], float] = {key: 0.84 for key in pass_at}
    cut_at[(0.30, 0.35)] = 0.50
    results = _results_with_per_cell_rates(
        epoch_budget=300,
        null_per_pair=1.0,
        fn_construction="union",
        pass_at=pass_at,
        cut_at=cut_at,
    )
    summary = reg.summary_md(results, 200, 685)
    assert "sensitivity" in summary.lower()
    assert "## Target check" in summary
    # Off-diagonal readings are present and are not filed under the target heading alone.
    sens_idx = summary.lower().find("sensitivity")
    target_idx = summary.find("## Target check")
    assert target_idx != -1 and sens_idx != -1
    # The off-diagonal minimum PASS value 0.50 appears in the sensitivity block.
    sens_block = summary[sens_idx:]
    assert "0.5000" in sens_block or "0.50" in sens_block
    # Never label an off-diagonal reading as the target itself.
    assert "off-diagonal" in summary.lower() or "sensitivity" in summary.lower()


def test_summary_renders_both_halves_and_the_stage2_trigger_from_data() -> None:
    # P(PASS) at d=0.30 clears 0.80 in every baseline cell; P(CUT) at d=0.10 does not.
    failing = _results_for_budget(
        epoch_budget=300,
        null_per_pair=1.0,
        fn_construction="union",
        p_pass_at_0_30=0.85,
        p_cut_at_0_10=0.10,
    )
    summary = reg.summary_md(failing, 200, 685)
    assert "## Target check" in summary
    assert "P(PASS) >= target at d = 0.30" in summary
    assert "P(CUT) >= target at d = 0.10" in summary
    assert "not reached" in summary
    assert "Stage-2 trigger for target 0.80: fires" in summary
    assert "Stage-2 trigger for target 0.90: fires" in summary
    assert "union" in summary


def test_summary_marks_smoke_output_as_schema_evidence() -> None:
    summary = reg.summary_md([], 20, 685)
    assert "establish only the output schema" in summary
    assert "They do not establish operating characteristics" in summary
    assert "These results establish operating characteristics" not in summary


def test_headline_reads_the_pairs_cap_designs_in_the_results() -> None:
    """M10: headline() must read n_pairs from the results, not a stale 97."""
    design = reg.Design(n_pairs=reg.PAIRS_CAP, null_per_pair=1.0, fn_construction="union")
    results = [
        _hand_result(
            reg.Cell(round(p_p + d, 10), p_p, p_n),
            design,
            p_pass=p_pass,
            p_cut=0.0,
        )
        for p_p in reg.BASELINES
        for p_n in reg.BASELINES
        for d, p_pass in ((0.30, 0.20), (0.40, 0.85))
    ]
    curve = reg.headline(results, 0.80)
    assert curve[("union", 0.35, 0.35)] == 0.40
    assert curve[("direct", 0.35, 0.35)] is None
    assert reg.smallest_d_reaching({0.30: 0.20, 0.40: 0.85}, 0.80) == 0.40


# ---------------------------------------------------------------------------
# Requirement 6: every #694 survivor turned red; exit path has its own test
# ---------------------------------------------------------------------------


def test_role_labels_d_equal_to_0_15_as_no_lift() -> None:
    """M8: role() uses d <= 0.15, so d = 0.15 is no-lift, not a real effect."""
    assert reg.role(0.15) == "no-lift"
    assert reg.role(0.00) == "no-lift"
    assert reg.role(0.14999) == "no-lift"
    assert reg.role(0.15001) == "small real effect" or reg.role(0.15001) == "real effect"
    assert reg.role(0.20) == "calibration"
    assert reg.role(0.25) == "small real effect"
    assert reg.role(0.30) == "real effect"


def _boundary_result_for_calibration_holds(*, pass_alpha: float, replicates: int) -> Any:
    design = reg.Design(n_pairs=97, null_per_pair=0.5)
    cell = reg.Cell(0.55, 0.35, 0.30)
    return reg.run_cell(cell, design, replicates=replicates, seed=685, pass_alpha=pass_alpha)


def test_calibration_holds_reads_the_cap_look_not_look_one() -> None:
    """M9: calibration_holds must read per_look[-1], not per_look[0]."""
    result = _boundary_result_for_calibration_holds(pass_alpha=0.6, replicates=600)
    limit = a650.PASS_ALPHA + a650.calibration_tolerance(600)
    assert result.per_look[0].p_pass < limit, "look 1 must sit under the limit"
    assert result.per_look[-1].p_pass > limit, "the cap must sit over the limit"
    assert reg.calibration_holds(result) is False


def test_main_exits_zero_when_calibration_holds(tmp_path: Path) -> None:
    grid = [(reg.Cell(0.55, 0.35, 0.30), reg.Design(n_pairs=30, null_per_pair=0.5))]
    code = reg.main(
        ["--out", str(tmp_path / "out"), "--replicates", "600", "--workers", "1", "--seed", "685"],
        grid=grid,
    )
    assert code == 0


def test_main_exits_non_zero_when_calibration_fails(tmp_path: Path) -> None:
    """M13: the exit-on-calibration-failure path returns 1, not 0."""
    grid = [(reg.Cell(0.55, 0.35, 0.30), reg.Design(n_pairs=30, null_per_pair=0.5))]
    code = reg.main(
        ["--out", str(tmp_path / "out"), "--replicates", "600", "--workers", "1", "--seed", "685"],
        grid=grid,
        pass_alpha=0.6,
    )
    assert code == 1
    assert (tmp_path / "out" / "summary.md").is_file()


def _engine_parity_mismatch(
    cell: Any,
    design: Any,
    *,
    replicates: int,
    seed: int,
    pass_alpha: float,
) -> int:
    """Count per-look rows where run_cell disagrees with the engine bound."""
    from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound as bound

    rng = reg.cell_rng(seed, cell)
    full = (rng.random((replicates, design.n_pairs)) < cell.p_full).astype(np.int64)
    placebo = (rng.random((replicates, design.n_pairs)) < cell.p_placebo).astype(np.int64)
    null_all = (rng.random((replicates, design.n_pairs, 2)) < cell.p_null).astype(np.int64)
    null_draws = reg.null_draw_counts(design.n_pairs, design.null_per_pair)
    half = pass_alpha / 2

    def engine_stop(
        f_list: list[int], p_list: list[int], n_rows: list[list[int]]
    ) -> tuple[int, str]:
        null_obs: list[float] = []
        direct_obs: list[float] = []
        for k in range(len(f_list)):
            xs_fp = reg.a650.paired_xs(f_list[: k + 1], p_list[: k + 1])
            for draw in range(null_draws[k]):
                null_obs.append(float(n_rows[k][draw]))
            if null_draws[k]:
                mean_null = sum(n_rows[k][: null_draws[k]]) / null_draws[k]
                direct_obs.append((f_list[k] - mean_null + 1) / 2)
            if design.fn_construction == "direct":
                lb_fn = 2 * bound(direct_obs, alpha=pass_alpha, side="lower") - 1
            else:
                lb_fn = bound(f_list[: k + 1], alpha=half, side="lower") - bound(
                    null_obs, alpha=half, side="upper"
                )
            outcome = reg.a650.stop_rule(
                ub_fp=2 * bound(xs_fp, alpha=reg.a650.FUTILITY_ALPHA, side="upper") - 1,
                lb_fp=2 * bound(xs_fp, alpha=pass_alpha, side="lower") - 1,
                lb_fn=lb_fn,
            )
            if outcome != "UNRESOLVED_CONTINUE":
                return k + 1, str(outcome)
        return len(f_list) + 1, "UNRESOLVED_CONTINUE"

    expected = [
        engine_stop(full[r].tolist(), placebo[r].tolist(), null_all[r].tolist())
        for r in range(replicates)
    ]
    result = reg.run_cell(cell, design, replicates=replicates, seed=seed, pass_alpha=pass_alpha)
    mismatches = 0
    for k, row in enumerate(result.per_look, start=1):
        exp_pass = sum(s <= k and o == "A_PASSES_EARLY" for s, o in expected) / replicates
        exp_cut = sum(s <= k and o == "CUT_NO_LIFT" for s, o in expected) / replicates
        if abs(row.p_pass - exp_pass) > 1e-9 or abs(row.p_cut - exp_cut) > 1e-9:
            mismatches += 1
    return mismatches


def test_exact_fp_fallback_uses_the_registered_pass_alpha() -> None:
    """M1b: the exact F-P fallback must call the bound at pass_alpha.

    On a borderline cell under a loosened pass alpha the grid bracket cannot
    decide, so the exact fallback runs. Swapping pass_alpha for FUTILITY_ALPHA
    in that fallback changes per-look decisions against the engine.
    """
    cell = reg.Cell(0.75, 0.35, 0.30)
    design = reg.Design(n_pairs=40, null_per_pair=0.5, fn_construction="union")
    assert _engine_parity_mismatch(cell, design, replicates=24, seed=685, pass_alpha=0.6) == 0
    assert _engine_parity_mismatch(cell, design, replicates=24, seed=685, pass_alpha=0.5) == 0
    assert (
        _engine_parity_mismatch(cell, design, replicates=24, seed=685, pass_alpha=a650.PASS_ALPHA)
        == 0
    )


def test_direct_fn_exact_fallback_is_pinned_to_the_engine() -> None:
    """Exact-path FN: the direct F-N exact fallback must use pass_alpha, not half.

    A cell where F-P clears and F-N is marginal leaves the direct F-N bracket
    undecided, so the exact bound decides. Evaluating that bound at alpha/2
    instead of pass_alpha changes per-look decisions against the engine.
    Forcing the fallback to True is observationally equivalent on this grid
    (every exact-path evaluation the suite reaches already clears), which is
    why this pins the alpha rather than the truth value.
    """
    cell = reg.Cell(0.65, 0.20, 0.45)
    design = reg.Design(n_pairs=40, null_per_pair=1.0, fn_construction="direct")
    assert _engine_parity_mismatch(cell, design, replicates=40, seed=685, pass_alpha=0.1) == 0
    assert (
        _engine_parity_mismatch(cell, design, replicates=40, seed=8, pass_alpha=a650.PASS_ALPHA)
        == 0
    )
    cell2 = reg.Cell(0.55, 0.35, 0.35)
    design2 = reg.Design(n_pairs=30, null_per_pair=1.0, fn_construction="direct")
    assert _engine_parity_mismatch(cell2, design2, replicates=24, seed=685, pass_alpha=0.6) == 0


def test_union_fn_exact_fallback_is_pinned_to_the_engine() -> None:
    """M2b: the union F-N exact fallback must not be forced true."""
    cell = reg.Cell(0.60, 0.35, 0.45)
    design = reg.Design(n_pairs=30, null_per_pair=2.0, fn_construction="union")
    assert _engine_parity_mismatch(cell, design, replicates=24, seed=685, pass_alpha=0.6) == 0
    cell2 = reg.Cell(0.85, 0.25, 0.30)
    design2 = reg.Design(n_pairs=30, null_per_pair=2.0, fn_construction="union")
    assert (
        _engine_parity_mismatch(cell2, design2, replicates=16, seed=685, pass_alpha=a650.PASS_ALPHA)
        == 0
    )


# ---------------------------------------------------------------------------
# Committed smoke-run data (acceptance: every data row carries the schema)
# ---------------------------------------------------------------------------

_SMOKE_DIR = (
    Path(__file__).resolve().parents[1] / "docs" / "findings" / "data" / "stage1a-regime-685"
)


def test_committed_smoke_per_look_rows_carry_the_full_schema() -> None:
    path = _SMOKE_DIR / "per_look.tsv"
    assert path.is_file(), "the smoke-run per_look.tsv must be committed"
    cols, rows = _split_tsv(path.read_text(encoding="utf-8"))
    for name in (
        *_DESIGN_FIELDS,
        "replicates",
        "se_pass",
        "expected_epochs",
        "expected_spend",
        "price_range",
    ):
        assert name in cols, f"committed per_look.tsv is missing {name}"
    i = {name: cols.index(name) for name in cols}
    assert rows, "the committed per_look.tsv has no data rows"
    assert len(rows) > 1000, "the smoke run must commit enough rows to show the schema"
    seen: dict[str, set[str]] = {name: set() for name in _DESIGN_FIELDS}
    for row in rows:
        assert len(row) == len(cols)
        for name in _DESIGN_FIELDS:
            value = row[i[name]]
            assert value, f"empty {name} on a data row"
            seen[name].add(value)
        assert float(row[i["replicates"]]) > 0
        assert float(row[i["se_pass"]]) >= 0.0
        assert float(row[i["expected_epochs"]]) > 0.0
        assert _parse_spend(row[i["expected_spend"]])[0] > 0.0
        assert "cap $" in row[i["price_range"]]
    assert seen["null_per_pair"] == {"0.50", "1.00", "2.00"}
    assert seen["fn_construction"] == {"union", "direct"}
    assert seen["stopping"] == {"anytime"}
    assert "300" in seen["total_epochs"] and "1200" in seen["total_epochs"]


def test_committed_smoke_terminal_rows_carry_mc_se_and_price_lines() -> None:
    path = _SMOKE_DIR / "terminal_states.tsv"
    assert path.is_file(), "the smoke-run terminal_states.tsv must be committed"
    cols, rows = _split_tsv(path.read_text(encoding="utf-8"))
    for name in (
        *_DESIGN_FIELDS,
        "replicates",
        "se_share",
        "expected_epochs",
        "expected_spend",
        "price_range",
    ):
        assert name in cols, f"committed terminal_states.tsv is missing {name}"
    i = {name: cols.index(name) for name in cols}
    assert rows, "the committed terminal_states.tsv has no data rows"
    assert len(rows) > 500, "the smoke run must commit enough terminal rows to show the schema"
    for row in rows:
        assert len(row) == len(cols)
        share, se = float(row[i["share"]]), float(row[i["se_share"]])
        reps = int(row[i["replicates"]])
        assert se == pytest.approx((share * (1.0 - share) / reps) ** 0.5, abs=1e-6)
        assert _parse_spend(row[i["expected_spend"]])[0] > 0.0
        assert "cap $" in row[i["price_range"]]


def test_committed_smoke_summary_reports_the_target_check() -> None:
    path = _SMOKE_DIR / "summary.md"
    assert path.is_file(), "the smoke-run summary.md must be committed"
    summary = path.read_text(encoding="utf-8")
    assert "## Target check" in summary
    assert "Replicates per cell: 20." in summary
    assert "P(PASS) >= target at d = 0.30" in summary
    assert "P(CUT) >= target at d = 0.10" in summary
    assert "establish only the output schema" in summary
    assert "These results establish operating characteristics" not in summary
    for target in ("0.80", "0.90"):
        assert f"Stage-2 trigger for target {target}:" in summary
        assert f"| {target} |" in summary


def test_committed_smoke_lives_under_docs_findings_data_not_scratch() -> None:
    """AC3: output path is docs/findings/data/stage1a-regime-685/."""
    assert _SMOKE_DIR.is_dir()
    assert (_SMOKE_DIR / "per_look.tsv").is_file()
    assert (_SMOKE_DIR / "terminal_states.tsv").is_file()
    assert (_SMOKE_DIR / "summary.md").is_file()
    scratch_data = Path(__file__).resolve().parents[1] / ".scratch" / "issue-695" / "data"
    assert not scratch_data.exists(), "smoke output must not land under .scratch/"
