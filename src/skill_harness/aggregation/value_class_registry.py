"""Per-skill ``value_class`` registration — the portfolio classification source (#77).

The screen instrument (``screen_verdict``) measures TRANSFORMATIVE LIFT only. Its
``p0 above the bar → CUT(subsumed)`` mapping is a category error for any skill whose
value is NOT transformative lift (a trap that guards one wrong action, or a
calibration skill that makes a measurement sound). The #76 guard withholds the CUT
for such skills — but only if it KNOWS the skill's class. #76 shipped the guard with
store rows unclassified (every screen → CAN'T-TELL-YET, honest but undiscriminating).

This module is the registration source #76's guard consumes: a static map from the
skill's ``skill_name`` (the exact string the screen store keys on, == the published
skill-card name) to its ``ValueClass``. The CLI seams look each screened skill up here
and pass the class into ``screen_verdict`` — so a registered non-transformative skill
renders CAN'T-TELL-YET *on purpose* (registered wrong-instrument), not by the accident
of being unclassified. That makes the four false CUTs (OBS-0003..0006) structurally
impossible to reintroduce (US-3/US-16).

Why a static map and not a scope/DB field (#41): the four target records are
pre-registry historical screens with ``scope = None``; #41 bans retrofitting any label
onto them. ``value_class`` is therefore an independent registration keyed by skill
name, exactly as ``ValueClass``'s docstring requires.

The empty transformative-lift class TRIPS the signed S2-kill criterion (the F6
sign-off, S166): ship the classification + CAN'T-TELL-YET/field surface, do NOT
build the S3 board apparatus for zero customers.

A skill_name absent from this map resolves to ``None`` (unclassified) → the guard's
honest default (CAN'T-TELL-YET, never a false CUT). The map is measured by
``tests/test_value_class_registry.py`` against a pinned list of
``(skill_name, value_class, retired_on)`` triples (#422).
"""

from __future__ import annotations

from skill_harness.aggregation.verdict import ValueClass

# ---------------------------------------------------------------------------
# The registry — keyed by the store/card ``skill_name`` (verbatim).
# ---------------------------------------------------------------------------

SKILL_VALUE_CLASS: dict[str, ValueClass] = {
    # --- calibration: make a measurement/evaluation trustworthy ---------------
    "bayesian-eval-discipline": ValueClass.CALIBRATION,
    "llm-judge-calibration": ValueClass.CALIBRATION,
    "append-only-evidence-design": ValueClass.CALIBRATION,
    # --- trap-discipline: guard against one specific wrong action -------------
    "git-pull-rebase-trap": ValueClass.TRAP_DISCIPLINE,
    "sqlite-tie-break-red-test-trap": ValueClass.TRAP_DISCIPLINE,  # retired 2026-07-10; RETIRED.md
    "github-pages-deploy-verification": ValueClass.TRAP_DISCIPLINE,
    "subagent-research-reliability": ValueClass.TRAP_DISCIPLINE,
    "downstream-instruction-framing": ValueClass.TRAP_DISCIPLINE,
    "closure-mode-at-boundaries": ValueClass.TRAP_DISCIPLINE,
    "skill-necessity-gate": ValueClass.TRAP_DISCIPLINE,  # retired 2026-08-31; RETIRED.md
    "parallel-review-disposition-schema": ValueClass.TRAP_DISCIPLINE,
    "mock-masked-stub-trap": ValueClass.TRAP_DISCIPLINE,
    # --- transformative-lift: intentionally empty (S2-kill fires) -------------
}
"""The portfolio classification. transformative-lift is deliberately empty:
no current skill is one the transformative-lift screen can validly CUT. Adjust a
single entry to reclassify a skill — the operator owns the value call; this is the
recorded default."""


def value_class_for(skill_name: str) -> ValueClass | None:
    """Return the registered ``ValueClass`` for a skill, or ``None`` if unclassified.

    ``None`` is the honest default the #76 guard treats as "not transformative-lift"
    → CAN'T-TELL-YET (wrong instrument), never a false CUT. Pass the result straight
    into ``screen_verdict(p0, value_class=value_class_for(name))``.
    """
    return SKILL_VALUE_CLASS.get(skill_name)
