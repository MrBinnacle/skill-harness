"""Frontier assembly: the deliberation artifact of #56 (grid ratified on
#40, error semantics on #37, architecture on #42).

The operator chooses a design row from visible trade-offs -- attained
family-wise error rates and projected worst-case cost per row -- instead of
accepting a default. Assembly enumerates the FULL integer grid
``GRID_N_MIN``-``GRID_N_MAX`` (every row, never a shortlist: enumeration is
exact and $0, so excluding rows saves nothing and loses information, #40);
the 12-24 band is a presentation highlight only.

Costs enter the ``oc`` package HERE and only here (#42 convention 3), as
pre-computed registered knobs (``usd_per_pair`` / ``usd_per_trial``). The
live PRICE_PER_MTOK -> USD projection lives in
``skill_harness.oracles.calibration.cost_projection`` (``project_pair_usd``
/ ``project_trial_usd``), NOT here: ``oc`` imports nothing from the ablation
or subject packages (#42; drift row DC-8), and a hard-coded per-pair dollar
constant anywhere in ``src/skill_harness/`` is drift (DC-9). The hard cap
tests WORST-CASE FIXED-N projected cost pre-spend (#40(b)): curtailment
savings surface only in the expectation columns, never in the cap test.
Over-cap rows are displayed and marked infeasible -- the cap filters
ratifiable rows, never displayed rows (#40(d)).

Everything is a pure function of the registered knobs: no I/O, no
enumeration seeds, deterministic, testable without spend (#56).
"""

from __future__ import annotations

from dataclasses import dataclass

from skill_harness.oc.conventions import (
    BAND_N_HI,
    BAND_N_LO,
    CANDIDATE_FALSE_DIRECTION_TARGET,
    GRID_N_MAX,
    GRID_N_MIN,
)
from skill_harness.oc.gate1 import (
    Gate1AttainedErrors,
    Gate1Design,
    Gate1OC,
    gate1_attained_errors,
    gate1_oc,
)
from skill_harness.oc.gate2 import (
    Gate2Design,
    Gate2NullErrorBound,
    MMESpec,
    gate2_oc,
    gate2_worst_false_direction,
)

# ---------------------------------------------------------------------------
# Registered configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontierConfig:
    """Every registered knob the frontier depends on -- nothing else enters.

    Fields
    ------
    gate1 : Gate1Design
        The registered Gate-1 screen design; its attained zone-edge pair and
        P(UNRESOLVED)-vs-true-p0 profile are config-level facts (#37 item 5/7).
    gamma : float
        Gate-2 posterior certification mass; in (0.5, 1) (#37 "gamma-only").
    mme : MMESpec
        The registered dual MME (delta_min AND q_min, #40).
    power_floor : float
        Registered power target over H1; in (0, 1). Its VALUE is a
        ratification-time pick (#40 defers the numeric choice), so it is a
        required knob with no default.
    usd_per_pair : float
        Projected worst-case dollars per Gate-2 pair, > 0 -- computed live
        via ``cost_projection.project_pair_usd`` (never a hard-coded
        constant, DC-9).
    usd_per_trial : float
        Projected dollars per Gate-1 screen trial, >= 0 (display only: the
        hard cap tests the Gate-2 pair spend, matching #40's own worst-case
        arithmetic).
    hard_cap_usd : float
        The registered per-evaluation hard cap, > 0 (pass
        ``cost_projection.EVALUATION_HARD_CAP_USD`` -- the #40-ratified $35).
    null_d_grid : tuple[float, ...]
        Nuisance-d evaluation points for the null false-direction bound
        (d = 1 is always added by :func:`gate2_worst_false_direction`).
    alt_grid : tuple[tuple[float, float], ...]
        Registered alternative (d, q) points; every point must lie in
        H1 = {(d, q): d(2q-1) >= delta_min and q >= q_min} -- a point outside
        the registered region is a misregistration and is refused, never
        silently filtered.
    p0_grid : tuple[float, ...]
        True-p0 points for the Gate-1 profile (#37 item 7).
    alpha_candidate : float
        The candidate worst-case false-direction target; in (0, 1). Defaults
        to the registered CANDIDATE 0.05 (#37 item 5) -- carried, finalized
        only at row-pick, never ratified here (#56).
    """

    gate1: Gate1Design
    gamma: float
    mme: MMESpec
    power_floor: float
    usd_per_pair: float
    usd_per_trial: float
    hard_cap_usd: float
    null_d_grid: tuple[float, ...]
    alt_grid: tuple[tuple[float, float], ...]
    p0_grid: tuple[float, ...]
    alpha_candidate: float = CANDIDATE_FALSE_DIRECTION_TARGET

    def __post_init__(self) -> None:
        if not 0.5 < self.gamma < 1.0:
            raise ValueError(
                "gamma must lie in (0.5, 1) - the three Gate-2 region masses "
                f"sum to 1, so gamma <= 0.5 admits double-fire; got {self.gamma}"
            )
        if not 0.0 < self.power_floor < 1.0:
            raise ValueError(f"power_floor must lie strictly inside (0, 1); got {self.power_floor}")
        if not 0.0 < self.alpha_candidate < 1.0:
            raise ValueError(
                f"alpha_candidate must lie strictly inside (0, 1); got {self.alpha_candidate}"
            )
        if self.usd_per_pair <= 0.0:
            raise ValueError(f"usd_per_pair must be > 0; got {self.usd_per_pair}")
        if self.usd_per_trial < 0.0:
            raise ValueError(f"usd_per_trial must be >= 0; got {self.usd_per_trial}")
        if self.hard_cap_usd <= 0.0:
            raise ValueError(f"hard_cap_usd must be > 0; got {self.hard_cap_usd}")
        for name, grid in (("null_d_grid", self.null_d_grid), ("p0_grid", self.p0_grid)):
            if not grid:
                raise ValueError(f"{name} must be nonempty")
            for v in grid:
                if not 0.0 <= v <= 1.0:
                    raise ValueError(f"every {name} point must lie in [0, 1]; got {v}")
        if not self.alt_grid:
            raise ValueError("alt_grid must be nonempty")
        offenders = [(d, q) for d, q in self.alt_grid if not self.mme.in_h1(d, q)]
        if offenders:
            raise ValueError(
                "every alt_grid point must lie in the registered H1 = "
                "{(d, q): d(2q-1) >= delta_min and q >= q_min} (#40) - a "
                "point outside the region is a misregistration, refused "
                f"rather than silently filtered; offending points: {offenders}"
            )


# ---------------------------------------------------------------------------
# Result vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontierRow:
    """One grid row: everything a #40 row-pick states, attained not nominal.

    ``alpha_null`` is the #37 item-5 Gate-2 registration (worst-case
    false-direction at the null, as the grid-max/certified-bound PAIR -- this
    layer never conflates a grid max with a supremum). The conformance flags
    use the CERTIFIED upper bound: a pass certifies the supremum meets the
    target, which a grid-max pass cannot.
    """

    n_pairs: int
    in_band: bool
    alpha_null: Gate2NullErrorBound
    power_h1_min: float
    power_h1_argmin: tuple[float, float]
    expected_n_null_max: float
    expected_n_h1_max: float
    worst_case_cost_usd: float
    meets_candidate_alpha: bool
    meets_power_floor: bool
    feasible: bool
    ratifiable: bool


@dataclass(frozen=True)
class FrontierGate1Block:
    """Config-level Gate-1 facts (#37 item 7): the attained zone-edge pair,
    the P(UNRESOLVED)-vs-true-p0 profile, and the worst-case screen cost
    (n_ceiling x usd_per_trial -- display only; the hard cap tests the
    Gate-2 pair spend per #40's own worst-case arithmetic)."""

    attained: Gate1AttainedErrors
    profile: tuple[Gate1OC, ...]
    worst_case_cost_usd: float


@dataclass(frozen=True)
class Frontier:
    """The assembled deliberation artifact: config + Gate-1 block + one row
    per grid n. ``rows`` always covers the full ratified grid in order."""

    config: FrontierConfig
    gate1: FrontierGate1Block
    rows: tuple[FrontierRow, ...]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def frontier_row(config: FrontierConfig, n_pairs: int) -> FrontierRow:
    """Assemble one frontier row at the given pair count.

    The ratified grid is enforced HERE: the math layer deliberately accepts
    any n >= 1 (#55), and the frontier layer is where #40's grid bounds
    enumeration (#42).

    :param config: The registered frontier configuration.
    :param n_pairs: Grid row, GRID_N_MIN <= n_pairs <= GRID_N_MAX.
    :returns: The assembled row.
    :raises ValueError: If n_pairs is outside the ratified grid.
    """
    if not GRID_N_MIN <= n_pairs <= GRID_N_MAX:
        raise ValueError(
            f"n_pairs={n_pairs} lies outside the ratified frontier grid "
            f"{GRID_N_MIN}-{GRID_N_MAX} (#40; the frontier layer enforces "
            "the grid, the math layer stays unbounded per #42)"
        )
    design = Gate2Design(n_pairs=n_pairs, gamma=config.gamma, mme=config.mme)
    bound = gate2_worst_false_direction(design, config.null_d_grid)

    power_min = 2.0  # above any probability; first grid point always improves
    argmin = config.alt_grid[0]
    expected_h1_max = 0.0
    for d, q in config.alt_grid:
        oc = gate2_oc(design, d, q)
        if oc.p_benefit < power_min:  # strict: ties keep the earliest point
            power_min = oc.p_benefit
            argmin = (d, q)
        expected_h1_max = max(expected_h1_max, oc.expected_n)
    expected_null_max = max(gate2_oc(design, d, 0.5).expected_n for d in config.null_d_grid)

    worst_case = n_pairs * config.usd_per_pair
    meets_alpha = bound.certified_upper_bound <= config.alpha_candidate
    meets_power = power_min >= config.power_floor
    feasible = worst_case <= config.hard_cap_usd
    return FrontierRow(
        n_pairs=n_pairs,
        in_band=BAND_N_LO <= n_pairs <= BAND_N_HI,
        alpha_null=bound,
        power_h1_min=power_min,
        power_h1_argmin=argmin,
        expected_n_null_max=expected_null_max,
        expected_n_h1_max=expected_h1_max,
        worst_case_cost_usd=worst_case,
        meets_candidate_alpha=meets_alpha,
        meets_power_floor=meets_power,
        feasible=feasible,
        ratifiable=feasible and meets_power and meets_alpha,
    )


def frontier_gate1_block(config: FrontierConfig) -> FrontierGate1Block:
    """Assemble the config-level Gate-1 block (#37 item 7).

    :param config: The registered frontier configuration.
    :returns: Attained pair + p0 profile + worst-case screen cost.
    """
    return FrontierGate1Block(
        attained=gate1_attained_errors(config.gate1),
        profile=tuple(gate1_oc(config.gate1, p0) for p0 in config.p0_grid),
        worst_case_cost_usd=config.gate1.n_ceiling * config.usd_per_trial,
    )


def assemble_frontier(config: FrontierConfig) -> Frontier:
    """Assemble the full frontier: EVERY integer grid row (#56 AC-1).

    Deliberately unparameterized over the grid -- there is no way to ask this
    function for a shortlist. The full assembly costs minutes of exact
    enumeration at the top rows (#40 anticipates the wall-time and prescribes
    logged even-n thinning as the only admissible relief, revisit-if).

    :param config: The registered frontier configuration.
    :returns: The assembled deliberation artifact.
    """
    return Frontier(
        config=config,
        gate1=frontier_gate1_block(config),
        rows=tuple(frontier_row(config, n) for n in range(GRID_N_MIN, GRID_N_MAX + 1)),
    )


# ---------------------------------------------------------------------------
# Rendering (pure string; the table an operator opens, #56)
# ---------------------------------------------------------------------------


def render_frontier_table(frontier: Frontier) -> str:
    """Render the frontier as a pure-ASCII table (data in, text out; no I/O).

    Presentation semantics pinned by #56's acceptance criteria: the 12-24
    band is a highlight mark only; over-cap rows render visible with an
    INFEASIBLE mark, never dropped; the candidate false-direction target is
    labelled candidate (finalized at row-pick); the cap/expectation honesty
    clauses are printed on the table itself.

    :param frontier: An assembled frontier.
    :returns: The rendered table.
    """
    cfg = frontier.config
    lines = [
        f"Gate-2 decision frontier -- full integer grid n = {GRID_N_MIN}-{GRID_N_MAX} "
        f"(#40; the {BAND_N_LO}-{BAND_N_HI} band '*' is a presentation highlight, "
        "never a grid bound)",
        f"knobs: gamma={cfg.gamma:.3f}  delta_min={cfg.mme.delta_min:.2f}  "
        f"q_min={cfg.mme.q_min:.2f}  power_floor={cfg.power_floor:.3f}  "
        f"usd/pair={cfg.usd_per_pair:.4f}  hard cap=${cfg.hard_cap_usd:.2f}",
        f"candidate false-direction target {cfg.alpha_candidate:.3f} -- candidate only, "
        "finalized at row-pick (#37/#56)",
        "",
        f"{'n':>4} {'band':>4}  {'alpha[grid]':>11} {'alpha[cert]':>11}  "
        f"{'power(H1)':>9}  {'E[N]null':>8} {'E[N]H1':>8}  {'worst$':>8}  "
        f"{'feasibility':<11}  ratifiable",
    ]
    for row in frontier.rows:
        lines.append(
            f"{row.n_pairs:>4} {'*' if row.in_band else '-':>4}  "
            f"{row.alpha_null.grid_max:>11.4f} "
            f"{row.alpha_null.certified_upper_bound:>11.4f}  "
            f"{row.power_h1_min:>9.4f}  "
            f"{row.expected_n_null_max:>8.2f} {row.expected_n_h1_max:>8.2f}  "
            f"{row.worst_case_cost_usd:>8.2f}  "
            f"{'ok' if row.feasible else 'INFEASIBLE':<11}  "
            f"{'RATIFIABLE' if row.ratifiable else '-'}"
        )
    g1 = frontier.gate1
    lines += [
        "",
        "Gate-1 (config-level, #37 item 7):",
        "  attained zone-edge pair: "
        f"P(QUALIFIES | p0=theta_hi)={g1.attained.p_qualify_at_theta_hi:.3f}  "
        f"P(REJECTED | p0=theta_lo)={g1.attained.p_reject_at_theta_lo:.3f}",
        f"  worst-case screen cost: ${g1.worst_case_cost_usd:.2f} "
        "(display only -- the hard cap tests the Gate-2 pair spend, #40)",
        "  P(UNRESOLVED)-vs-true-p0 profile:",
    ]
    for point in g1.profile:
        lines.append(
            f"    p0={point.true_p0:.2f}  P(Q)={point.p_qualifies:.3f}  "
            f"P(R)={point.p_rejected:.3f}  P(U)={point.p_unresolved:.3f}  "
            f"E[N]={point.expected_n:.2f}"
        )
    lines += [
        "",
        "cap: worst-case fixed-N pre-spend projection against the registered hard cap "
        "(#40(b)); curtailment savings appear in the expectation columns only. "
        "Over-cap rows are shown and marked infeasible, never hidden (#40(d)).",
    ]
    return "\n".join(lines)
