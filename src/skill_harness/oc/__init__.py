"""Pure-math operating-characteristic engine (#42 architecture; #54 + #55).

``skill_harness.oc`` answers, from registered knobs alone: does this skill
qualify at Gate 1, what does the paired Gate-2 comparison decide, at what
ATTAINED (not nominal) error rates, and at what point can a run stop
spending because the decision is mathematically settled? No I/O, no
database, no simulation - exact enumeration throughout.

Architecture (ratified on #42): this package imports NOTHING from the
ablation or subject packages - the engine is estimand-agnostic and its
consumers import it, never the reverse (drift-check row DC-8). The legacy
``ablation/sizing.py`` + ``stopping.py`` modules stay untouched as the
legacy rule's characterized artifacts; parallel machinery is the ratified
answer, not a refactor (the scalar half-update state is provably
insufficient for the four-outcome gate - counterexample in #42's record).

Grid conventions are ``oc``'s own registered constants (#40 provenance in
:mod:`skill_harness.oc.conventions`; drift-check row DC-7).

Gate-1 machinery landed with #54; the Gate-2 four-outcome (x_f, x_n) lattice
machinery, dual-MME registration, and frequentist cross-checks landed with
#55; frontier assembly landed with #56 - costs never enter below the
frontier-assembly layer (#42 convention 3), and they enter it as registered
knobs projected live by ``oracles.calibration.cost_projection``, keeping
this package import-clean (drift rows DC-8/DC-9).
"""

from __future__ import annotations

from skill_harness.oc.conventions import (
    BAND_N_HI,
    BAND_N_LO,
    CANDIDATE_FALSE_DIRECTION_TARGET,
    GRID_N_MAX,
    GRID_N_MIN,
)
from skill_harness.oc.crosschecks import mcnemar_midp, newcombe_interval, tango_interval
from skill_harness.oc.exact import beta_binomial_pmf, beta_cdf, dirichlet_delta_tail
from skill_harness.oc.frontier import (
    Frontier,
    FrontierConfig,
    FrontierGate1Block,
    FrontierRow,
    assemble_frontier,
    frontier_gate1_block,
    frontier_row,
    render_frontier_table,
)
from skill_harness.oc.gate1 import (
    Gate1AttainedErrors,
    Gate1Decision,
    Gate1Design,
    Gate1OC,
    gate1_attained_errors,
    gate1_decide,
    gate1_extension_pp,
    gate1_oc,
)
from skill_harness.oc.gate2 import (
    Gate2Decision,
    Gate2Design,
    Gate2NullErrorBound,
    Gate2OC,
    Gate2RegionProbs,
    MMESpec,
    gate2_decide,
    gate2_oc,
    gate2_region_probs,
    gate2_worst_false_direction,
)

__all__ = [
    "BAND_N_HI",
    "BAND_N_LO",
    "CANDIDATE_FALSE_DIRECTION_TARGET",
    "GRID_N_MAX",
    "GRID_N_MIN",
    "Frontier",
    "FrontierConfig",
    "FrontierGate1Block",
    "FrontierRow",
    "Gate1AttainedErrors",
    "Gate1Decision",
    "Gate1Design",
    "Gate1OC",
    "Gate2Decision",
    "Gate2Design",
    "Gate2NullErrorBound",
    "Gate2OC",
    "Gate2RegionProbs",
    "MMESpec",
    "assemble_frontier",
    "beta_binomial_pmf",
    "beta_cdf",
    "dirichlet_delta_tail",
    "frontier_gate1_block",
    "frontier_row",
    "gate1_attained_errors",
    "gate1_decide",
    "gate1_extension_pp",
    "gate1_oc",
    "gate2_decide",
    "gate2_oc",
    "gate2_region_probs",
    "gate2_worst_false_direction",
    "mcnemar_midp",
    "newcombe_interval",
    "render_frontier_table",
    "tango_interval",
]
