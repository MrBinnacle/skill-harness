"""Registered grid conventions for the ``skill_harness.oc`` package.

These are ``oc``'s OWN registered constants — the single place the OC
enumeration grid is declared. Guarded by drift-check row DC-7 (constants,
doc quotes, and the provenance sentence below).
"""

from __future__ import annotations

from typing import Final

# Provenance: ratified decision #40 fixes the full integer grid n = 6-40;
# deliberately NOT imported from the legacy stopping-rule constants - the
# ceiling is fixed by ratified decision, not by the legacy rule (#42
# convention 2). An import would let a legacy-path change silently move a
# ratified convention and hold this engine hostage to legacy retirement.
# Revisit-if: the legacy path survives permanently AND the two values are
# required to co-move - then swap to an import.
GRID_N_MIN: Final[int] = 6
GRID_N_MAX: Final[int] = 40

# The 12-24-pair band (#40, prototype P4) is a presentation highlight on the
# frontier report, never a grid bound: enumeration is exact and $0, so
# excluding rows saves nothing and loses information.
BAND_N_LO: Final[int] = 12
BAND_N_HI: Final[int] = 24

# Provenance: #37 item 5 carries the candidate worst-case false-direction
# target 0.05, finalized ONLY at row-pick - the frontier consumes it as an
# overridable knob and never ratifies it (#56 acceptance criterion). A
# ratified value would be a dated amendment to this comment, never a silent
# constant change.
CANDIDATE_FALSE_DIRECTION_TARGET: Final[float] = 0.05
