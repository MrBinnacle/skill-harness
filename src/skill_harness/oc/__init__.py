"""Pure-math operating-characteristic engine (#42 architecture, #54 opener).

``skill_harness.oc`` answers, from registered knobs alone: does this skill
qualify at Gate 1, at what ATTAINED (not nominal) error rates, and at what
point can a run stop spending because the decision is mathematically
settled? No I/O, no database, no simulation - exact enumeration throughout.

Architecture (ratified on #42): this package imports NOTHING from the
ablation or subject packages - the engine is estimand-agnostic and its
consumers import it, never the reverse (drift-check row DC-8). The legacy
``ablation/sizing.py`` + ``stopping.py`` modules stay untouched as the
legacy rule's characterized artifacts; parallel machinery is the ratified
answer, not a refactor (the scalar half-update state is provably
insufficient for the four-outcome gate - counterexample in #42's record).

Grid conventions are ``oc``'s own registered constants (#40 provenance in
:mod:`skill_harness.oc.conventions`; drift-check row DC-7).

This package is the Gate-1 opener (#54). The Gate-2 four-outcome lattice DP
(#55) and frontier assembly with live cost projection (#56) land next; costs
never enter below the frontier-assembly layer (#42 convention 3).
"""

from __future__ import annotations

from skill_harness.oc.conventions import GRID_N_MAX, GRID_N_MIN
from skill_harness.oc.exact import beta_binomial_pmf, beta_cdf
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

__all__ = [
    "GRID_N_MAX",
    "GRID_N_MIN",
    "Gate1AttainedErrors",
    "Gate1Decision",
    "Gate1Design",
    "Gate1OC",
    "beta_binomial_pmf",
    "beta_cdf",
    "gate1_attained_errors",
    "gate1_decide",
    "gate1_extension_pp",
    "gate1_oc",
]
