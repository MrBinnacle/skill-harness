"""Task frontier — honest task supply for the matched-pair estimator (spec #89).

The instrument can estimate a skill's matched-pair effect, but an effect
estimated on the same tasks whose difficulty was tuned on that data is
optimistically biased (the winner's curse). This module is the supply side, and
it is honest by construction: the data used to pick a task family's difficulty
can never reach the number that scores the skill.

Three phases, walled off at the SEMANTIC LINEAGE level:

    calibration   null-only probes SELECT a difficulty rung; permanently
                  excluded from confirmation and from the effect
    confirmation  FRESH null-only lineages test whether the locked rung clears
                  the eligibility gate; failure holds the family at UNRESOLVED
    matched       a SECOND fresh set of matched instances — the only data that
                  enters the benefit/harm rule, via ``oc/gate2``

The isolation is a PHYSICAL partition (one append-only table per phase,
migration 0700) plus a write-time phase stamp taken from the frozen manifest
and never recomputed at read — the same shape as the existing screen-store
firewall. This removes the row-leakage bug class; it is defense in depth, not a
proof that no analyst can ever misuse the data.

The public surface is deliberately small:

    load_manifest(data)                 -> TaskFamilyManifest   the freeze
    admit(conn, manifest, observation)  -> Admission            the write gate
    matched_evidence(conn, manifest)    -> StoredObservation[]  the estimator feed
    audit_observation(conn, obs_id)     -> StoredObservation?   the audit read

Spec #89 names four calls, and the fourth is ``calibration_rung`` — the selected
rung exposed as a DECISION. It is NOT built (it needs the rung selection of a
later ticket). ``audit_observation`` is not a substitute for it: it is the by-id
audit read this tracer needs to show that a record comes back under the phase it
was admitted to.

What the surface does guarantee: no call returns calibration or confirmation
observations in BULK, and none takes a phase as an argument. ``audit_observation``
does return a walled-off row when handed its id — but the interface never hands
out the ids or the lineages of a walled-off phase, so it cannot be turned into a
way to walk that evidence. This removes the row-leakage bug class; it is defense
in depth, not a proof that a determined caller with ids from elsewhere cannot
read those rows. ``tests/task_frontier/test_tracer.py`` pins the exported surface
so a bulk convenience accessor cannot quietly reopen the leak path.

The firewall is a load-bearing invariant — see docs/INVARIANTS.md #7.

Prior art (spec #89): split-sample / selective inference (Cox 1975;
Fithian-Sun-Taylor 2014; Berk et al. 2013); confirmatory-vs-exploratory phase
separation (Nosek et al. 2018); rephrased-sample contamination motivating
semantic lineages over seeds (Yang et al. 2023); reusable holdout / adaptive
data analysis for the confirmation-attempt budget (Dwork et al. 2015).
"""

from __future__ import annotations

from skill_harness.task_frontier.admission import (
    Admission,
    Observation,
    StoredObservation,
    admit,
    audit_observation,
    matched_evidence,
)
from skill_harness.task_frontier.manifest import (
    Arm,
    FrozenHashes,
    Phase,
    TaskFamilyManifest,
    load_manifest,
)

__all__ = [
    "Admission",
    "Arm",
    "FrozenHashes",
    "Observation",
    "Phase",
    "StoredObservation",
    "TaskFamilyManifest",
    "admit",
    "audit_observation",
    "load_manifest",
    "matched_evidence",
]
