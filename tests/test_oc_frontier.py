"""Frontier-assembly seam tests (#56; grid ratified on #40, architecture on
#42, error semantics on #37).

Seam (spec #49 testing decision 1): the ``oc`` public API — pure functions
from registered knobs to frontier rows/tables. Never internals. Row values
are pinned DIFFERENTIALLY against direct composition of the already-verified
public primitives (``gate1_oc``/``gate1_attained_errors``/``gate2_oc``/
``gate2_worst_false_direction``): the frontier must equal what an operator
would compute by hand from the primitives, column by column.

The Gate-2 design knobs deliberately match tests/test_oc_gate2.py's
(gamma=0.90, delta_min=0.2, q_min=0.7) so the exact-Fraction decision cache
for the expensive n=40 layer is shared within the test process (S155 env
note: keep the n=40 spend to one fill per suite).

The full-grid assembly test (#56 AC: every row n=6-40, never a shortlist) is
marked ``slow`` (~2 min of exact-Fraction cache fills; measured before this
file was written). CI runs it (`-m "not live"` keeps slow selected); local
iteration may deselect with `-m "not slow"`.
"""

from __future__ import annotations

import dataclasses

import pytest

from skill_harness.oc import (
    BAND_N_HI,
    BAND_N_LO,
    CANDIDATE_FALSE_DIRECTION_TARGET,
    Frontier,
    FrontierConfig,
    FrontierGate1Block,
    FrontierRow,
    Gate1AttainedErrors,
    Gate1Design,
    Gate1OC,
    Gate2Design,
    Gate2NullErrorBound,
    MMESpec,
    assemble_frontier,
    frontier_gate1_block,
    frontier_row,
    gate1_attained_errors,
    gate1_oc,
    gate2_oc,
    gate2_worst_false_direction,
    render_frontier_table,
)
from skill_harness.oracles.calibration.cost_projection import EVALUATION_HARD_CAP_USD

# ---------------------------------------------------------------------------
# Shared registered-knob fixtures (Gate-2 knobs match test_oc_gate2's _D16)
# ---------------------------------------------------------------------------

_G1 = Gate1Design(
    theta_lo=0.3,
    theta_hi=0.5,
    gamma_qualify=0.8,
    gamma_reject=0.9,
    n_initial=8,
)
_MME = MMESpec(delta_min=0.2, q_min=0.7)
_NULL_D = (0.2, 0.6, 1.0)
_ALT = ((0.5, 0.9), (0.8, 0.9), (0.6, 0.75))
_P0 = (0.05, 0.3, 0.5, 0.9)

_CFG = FrontierConfig(
    gate1=_G1,
    gamma=0.90,
    mme=_MME,
    power_floor=0.5,
    usd_per_pair=0.66,
    usd_per_trial=0.33,
    hard_cap_usd=EVALUATION_HARD_CAP_USD,
    null_d_grid=_NULL_D,
    alt_grid=_ALT,
    p0_grid=_P0,
)


def _design(n: int) -> Gate2Design:
    return Gate2Design(n_pairs=n, gamma=_CFG.gamma, mme=_CFG.mme)


def _expected_row(cfg: FrontierConfig, n: int) -> FrontierRow:
    """Recompose one row directly from the public primitives (the differential
    reference: same seams an operator would use by hand)."""
    design = Gate2Design(n_pairs=n, gamma=cfg.gamma, mme=cfg.mme)
    bound = gate2_worst_false_direction(design, cfg.null_d_grid)
    power_min = 2.0
    argmin = cfg.alt_grid[0]
    e_h1_max = 0.0
    for d, q in cfg.alt_grid:
        oc = gate2_oc(design, d, q)
        if oc.p_benefit < power_min:
            power_min = oc.p_benefit
            argmin = (d, q)
        e_h1_max = max(e_h1_max, oc.expected_n)
    e_null_max = max(gate2_oc(design, d, 0.5).expected_n for d in cfg.null_d_grid)
    worst = n * cfg.usd_per_pair
    meets_alpha = bound.certified_upper_bound <= cfg.alpha_candidate
    meets_power = power_min >= cfg.power_floor
    feasible = worst <= cfg.hard_cap_usd
    return FrontierRow(
        n_pairs=n,
        in_band=BAND_N_LO <= n <= BAND_N_HI,
        alpha_null=bound,
        power_h1_min=power_min,
        power_h1_argmin=argmin,
        expected_n_null_max=e_null_max,
        expected_n_h1_max=e_h1_max,
        worst_case_cost_usd=worst,
        meets_candidate_alpha=meets_alpha,
        meets_power_floor=meets_power,
        feasible=feasible,
        ratifiable=feasible and meets_power and meets_alpha,
    )


# ---------------------------------------------------------------------------
# Registered conventions (#40 band; #37 candidate target)
# ---------------------------------------------------------------------------


def test_band_constants_are_the_ratified_presentation_band() -> None:
    assert (BAND_N_LO, BAND_N_HI) == (12, 24)


def test_candidate_false_direction_target_is_carried_not_ratified() -> None:
    """#37 item 5 / #56 AC: 0.05 is carried as a registered CANDIDATE, the
    config consumes it as an overridable knob (finalized only at row-pick)."""
    assert CANDIDATE_FALSE_DIRECTION_TARGET == 0.05
    assert _CFG.alpha_candidate == CANDIDATE_FALSE_DIRECTION_TARGET
    override = dataclasses.replace(_CFG, alpha_candidate=0.03)
    assert override.alpha_candidate == 0.03


def test_evaluation_hard_cap_is_the_ratified_35() -> None:
    assert EVALUATION_HARD_CAP_USD == 35.0


# ---------------------------------------------------------------------------
# Config validation (registered knobs fail fast)
# ---------------------------------------------------------------------------


def test_config_rejects_gamma_at_or_below_half() -> None:
    with pytest.raises(ValueError, match="gamma"):
        dataclasses.replace(_CFG, gamma=0.5)


def test_config_rejects_out_of_range_targets() -> None:
    with pytest.raises(ValueError, match="power_floor"):
        dataclasses.replace(_CFG, power_floor=0.0)
    with pytest.raises(ValueError, match="alpha_candidate"):
        dataclasses.replace(_CFG, alpha_candidate=1.0)


def test_config_rejects_nonpositive_economics() -> None:
    with pytest.raises(ValueError, match="usd_per_pair"):
        dataclasses.replace(_CFG, usd_per_pair=0.0)
    with pytest.raises(ValueError, match="usd_per_trial"):
        dataclasses.replace(_CFG, usd_per_trial=-0.1)
    with pytest.raises(ValueError, match="hard_cap_usd"):
        dataclasses.replace(_CFG, hard_cap_usd=0.0)


def test_config_rejects_empty_grids() -> None:
    with pytest.raises(ValueError, match="null_d_grid"):
        dataclasses.replace(_CFG, null_d_grid=())
    with pytest.raises(ValueError, match="alt_grid"):
        dataclasses.replace(_CFG, alt_grid=())
    with pytest.raises(ValueError, match="p0_grid"):
        dataclasses.replace(_CFG, p0_grid=())


def test_config_rejects_alt_points_outside_h1() -> None:
    """#40: the power target is evaluated over H1 = {delta >= delta_min and
    q >= q_min}; a supplied alternative point outside the registered region is
    a misregistration, refused (never silently filtered)."""
    with pytest.raises(ValueError, match="H1"):
        dataclasses.replace(_CFG, alt_grid=((0.3, 0.8),))  # delta = 0.18 < 0.2
    with pytest.raises(ValueError, match="H1"):
        dataclasses.replace(_CFG, alt_grid=((0.5, 0.65),))  # q below q_min
    with pytest.raises(ValueError):
        dataclasses.replace(_CFG, alt_grid=((1.1, 0.9),))  # out of range


def test_config_rejects_out_of_range_grid_points() -> None:
    with pytest.raises(ValueError, match="null_d_grid"):
        dataclasses.replace(_CFG, null_d_grid=(0.5, 1.2))
    with pytest.raises(ValueError, match="p0_grid"):
        dataclasses.replace(_CFG, p0_grid=(-0.1,))


# ---------------------------------------------------------------------------
# Grid enforcement (#42: the grid bounds the FRONTIER layer, not the math)
# ---------------------------------------------------------------------------


def test_frontier_enforces_the_ratified_grid() -> None:
    """Gate2Design accepts any n >= 1 (the math layer is unbounded, #55);
    the frontier layer is where #40's grid is enforced (#42/#56)."""
    with pytest.raises(ValueError, match="grid"):
        frontier_row(_CFG, 5)
    with pytest.raises(ValueError, match="grid"):
        frontier_row(_CFG, 41)


# ---------------------------------------------------------------------------
# Row columns — differential against direct primitive composition
# ---------------------------------------------------------------------------


def test_row_n6_matches_direct_composition() -> None:
    assert frontier_row(_CFG, 6) == _expected_row(_CFG, 6)


def test_row_n16_matches_direct_composition() -> None:
    assert frontier_row(_CFG, 16) == _expected_row(_CFG, 16)


def test_row_n40_boundary_matches_direct_composition() -> None:
    """The grid-ceiling boundary row (the one deliberate n=40 exact-lattice
    spend of this module; knobs shared with test_oc_gate2's _D40 cache)."""
    row = frontier_row(_CFG, 40)
    assert row == _expected_row(_CFG, 40)
    # The certified bound can never sit below the evaluated grid max.
    assert row.alpha_null.certified_upper_bound >= row.alpha_null.grid_max - 1e-12


def test_row_argmin_is_first_grid_point_attaining_the_minimum() -> None:
    """Deterministic tie-break: alt_grid order, strict improvement only."""
    row = frontier_row(_CFG, 16)
    design = _design(16)
    powers = [gate2_oc(design, d, q).p_benefit for d, q in _CFG.alt_grid]
    first_min = _CFG.alt_grid[powers.index(min(powers))]
    assert row.power_h1_argmin == first_min


def test_row_cost_columns_are_pre_spend_worst_case() -> None:
    """#40(b): the cap column is worst-case FIXED-N spend — curtailment
    savings appear only in the expectation columns, never in the cap test."""
    row = frontier_row(_CFG, 16)
    assert row.worst_case_cost_usd == 16 * _CFG.usd_per_pair
    assert row.expected_n_h1_max <= 16.0
    assert row.expected_n_null_max <= 16.0


def test_over_cap_row_is_visible_but_infeasible() -> None:
    """#40(d)/#56 AC: the cap filters RATIFIABLE rows, never displayed rows —
    an over-cap row still assembles, carrying feasible=False."""
    tight = dataclasses.replace(_CFG, hard_cap_usd=10.0)
    over = frontier_row(tight, 16)  # 16 x 0.66 = 10.56 > 10
    under = frontier_row(tight, 15)  # 15 x 0.66 = 9.90 <= 10
    assert over.feasible is False and over.ratifiable is False
    assert under.feasible is True
    # Feasibility is the only column the cap changes.
    baseline = frontier_row(_CFG, 16)
    assert over.alpha_null == baseline.alpha_null
    assert over.power_h1_min == baseline.power_h1_min


def test_ratifiable_is_the_registered_conjunction() -> None:
    """#37 item 7: only rows meeting the registered targets are presented as
    ratifiable — cap feasibility AND the power floor AND the candidate
    false-direction target (certified bound, not the grid max)."""
    for n in (6, 16):
        row = frontier_row(_CFG, n)
        assert row.ratifiable == (
            row.feasible and row.meets_power_floor and row.meets_candidate_alpha
        )
        assert row.meets_candidate_alpha == (
            row.alpha_null.certified_upper_bound <= _CFG.alpha_candidate
        )
        assert row.meets_power_floor == (row.power_h1_min >= _CFG.power_floor)


def test_rows_are_pure_functions_of_the_config() -> None:
    """#56 AC: deterministic, testable without spend — same registered knobs,
    identical row (dataclass equality, exact floats)."""
    assert frontier_row(_CFG, 16) == frontier_row(_CFG, 16)


# ---------------------------------------------------------------------------
# Gate-1 config-level block (#37 item 7: both gates' attained errors +
# the P(UNRESOLVED)-vs-true-p0 profile)
# ---------------------------------------------------------------------------


def test_gate1_block_matches_direct_composition() -> None:
    block = frontier_gate1_block(_CFG)
    assert block.attained == gate1_attained_errors(_G1)
    assert block.profile == tuple(gate1_oc(_G1, p0) for p0 in _P0)
    assert block.worst_case_cost_usd == _G1.n_ceiling * _CFG.usd_per_trial


# ---------------------------------------------------------------------------
# Renderer (data in -> ASCII table out; no I/O, no enumeration)
# ---------------------------------------------------------------------------


def _hand_row(
    n: int,
    *,
    in_band: bool,
    feasible: bool,
    ratifiable: bool,
) -> FrontierRow:
    return FrontierRow(
        n_pairs=n,
        in_band=in_band,
        alpha_null=Gate2NullErrorBound(grid_max=0.0123, certified_upper_bound=0.0234),
        power_h1_min=0.8123,
        power_h1_argmin=(0.6, 0.75),
        expected_n_null_max=float(n) * 0.7,
        expected_n_h1_max=float(n) * 0.8,
        worst_case_cost_usd=n * 0.66,
        meets_candidate_alpha=True,
        meets_power_floor=True,
        feasible=feasible,
        ratifiable=ratifiable,
    )


def _hand_frontier() -> Frontier:
    gate1 = FrontierGate1Block(
        attained=Gate1AttainedErrors(p_qualify_at_theta_hi=0.031, p_reject_at_theta_lo=0.042),
        profile=(
            Gate1OC(
                true_p0=0.3,
                p_qualifies=0.5,
                p_rejected=0.2,
                p_unresolved=0.3,
                expected_n=7.5,
                curtailed=True,
            ),
        ),
        worst_case_cost_usd=2.64,
    )
    rows = (
        _hand_row(11, in_band=False, feasible=True, ratifiable=True),
        _hand_row(12, in_band=True, feasible=True, ratifiable=True),
        _hand_row(40, in_band=False, feasible=False, ratifiable=False),
    )
    return Frontier(config=_CFG, gate1=gate1, rows=rows)


def _row_line(table: str, n: int) -> str:
    for line in table.splitlines():
        tokens = line.split()
        if tokens and tokens[0] == str(n):
            return line
    raise AssertionError(f"no table line for n={n}:\n{table}")


def test_render_is_pure_ascii() -> None:
    assert render_frontier_table(_hand_frontier()).isascii()


def test_render_marks_band_rows_as_presentation_highlight_only() -> None:
    table = render_frontier_table(_hand_frontier())
    assert _row_line(table, 12).split()[1] == "*"
    assert _row_line(table, 11).split()[1] == "-"
    assert "presentation highlight" in table


def test_render_marks_over_cap_rows_visible_but_infeasible() -> None:
    """#56 AC wording: over-cap rows RENDER visible-but-infeasible — the row
    line is present and carries the INFEASIBLE mark."""
    table = render_frontier_table(_hand_frontier())
    line40 = _row_line(table, 40)
    assert "INFEASIBLE" in line40
    assert "INFEASIBLE" not in _row_line(table, 12)
    assert "RATIFIABLE" in _row_line(table, 12)


def test_render_states_the_cap_and_candidate_semantics() -> None:
    """The table states its own honesty clauses: worst-case fixed-N pre-spend
    cap, expectation-only curtailment savings, candidate target finalized at
    row-pick."""
    table = render_frontier_table(_hand_frontier())
    assert "worst-case fixed-N" in table
    assert "pre-spend" in table
    assert "expectation" in table
    assert "finalized at row-pick" in table
    assert "$35.00" in table  # the config's cap, printed


def test_render_prints_gate1_attained_pair() -> None:
    table = render_frontier_table(_hand_frontier())
    assert "Gate-1" in table
    assert "0.031" in table and "0.042" in table


# ---------------------------------------------------------------------------
# Full-grid assembly (#56 AC-1: every row n=6-40, never a shortlist).
# ~2 min of exact-Fraction decision-cache fills (measured): slow-marked; CI
# runs it, local iteration may deselect.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_full_grid_assembly_every_row_no_shortlist() -> None:
    cfg = dataclasses.replace(_CFG, usd_per_pair=1.0, usd_per_trial=0.5)
    frontier = assemble_frontier(cfg)

    # AC-1: the full integer grid, every row, in order.
    assert tuple(row.n_pairs for row in frontier.rows) == tuple(range(6, 41))
    # Band flags are exactly the 12-24 presentation band.
    assert [row.n_pairs for row in frontier.rows if row.in_band] == list(range(12, 25))
    # AC-3: at $1/pair the $35 cap splits the grid at n=35; over-cap rows are
    # PRESENT and marked infeasible, never dropped.
    assert [row.n_pairs for row in frontier.rows if not row.feasible] == [36, 37, 38, 39, 40]
    for row in frontier.rows:
        assert row.worst_case_cost_usd == row.n_pairs * 1.0
        assert row.alpha_null.certified_upper_bound >= row.alpha_null.grid_max - 1e-12
        assert 0.0 <= row.power_h1_min <= 1.0
    # Spot rows equal the public per-row function (pure recomposition).
    assert frontier.rows[0] == frontier_row(cfg, 6)
    assert frontier.rows[17] == frontier_row(cfg, 23)
    assert frontier.rows[-1] == frontier_row(cfg, 40)
    # Config-level Gate-1 block equals its public builder.
    assert frontier.gate1 == frontier_gate1_block(cfg)

    # Rendering: all 35 rows present, the 5 over-cap rows marked, ASCII only.
    table = render_frontier_table(frontier)
    assert table.isascii()
    for n in range(6, 41):
        assert _row_line(table, n)
    assert table.count("INFEASIBLE") == 5
