"""Tests for the classify-the-11 registry + the four-record flip regression (#77).

These lock three things:
  1. The portfolio classification is complete and pins the S2-kill condition
     (0 transformative-lift → the signed kill fires; see F6-signoff-S166).
  2. The four historical false CUTs (OBS-0003..0006) re-render CAN'T-TELL-YET
     (wrong instrument), NEVER CUT, once their registered class flows through the
     guard — the standing regression against re-introducing the day-one falsehood.
  3. ``value_class_for`` is the honest default for an unregistered skill (None).

External-behaviour only — no store, no private logs (the guard is a pure function
of p0 + value_class; the registry is a pure map).
"""

from __future__ import annotations

import pytest

from skill_harness.aggregation.value_class_registry import (
    SKILL_VALUE_CLASS,
    value_class_for,
)
from skill_harness.aggregation.verdict import (
    KeepCutVerdict,
    ValueClass,
    screen_verdict,
)

# The eleven-skill portfolio (US-16: all classified BEFORE the board renders).
_EXPECTED_SKILLS = frozenset(
    {
        "git-pull-rebase-trap",
        "sqlite-tie-break-red-test-trap",
        "github-pages-deploy-verification",
        "subagent-research-reliability",
        "downstream-instruction-framing",
        "closure-mode-at-boundaries",
        "skill-necessity-gate",
        "parallel-review-disposition-schema",
        "bayesian-eval-discipline",
        "llm-judge-calibration",
        "append-only-evidence-design",
    }
)

# The four historical Stage-0 records the guard exists to un-false-CUT.
_OBS_0003_0006 = (
    "sqlite-tie-break-red-test-trap",  # OBS-0003
    "bayesian-eval-discipline",  # OBS-0004
    "append-only-evidence-design",  # OBS-0005
    "llm-judge-calibration",  # OBS-0006
)


# ---------------------------------------------------------------------------
# Registry completeness + the S2-kill condition
# ---------------------------------------------------------------------------


def test_all_eleven_skills_classified() -> None:
    """US-16: every portfolio skill carries a registered value_class, no extras."""
    assert set(SKILL_VALUE_CLASS) == set(_EXPECTED_SKILLS)
    assert len(SKILL_VALUE_CLASS) == 11


def test_s2_kill_condition_transformative_lift_class_is_empty() -> None:
    """The machine-checkable form of the signed S2-kill trigger (F6-signoff-S166):
    NO skill is transformative-lift → the harness has zero current customers for its
    one measurement path → ship field/CAN'T-TELL-YET only, do NOT build the S3 board.
    If a future transformative-lift KEEP is registered here, this test flips and the
    kill calculus is revisited (F6 Revisit-if) — that is the intended trip-wire."""
    assert ValueClass.TRANSFORMATIVE_LIFT not in SKILL_VALUE_CLASS.values()


def test_f8a_third_class_named_and_populated() -> None:
    """F8a: the canonical third partition is named from the real distribution and is
    non-empty (3 calibration skills). The two point-trap disciplines are the balance."""
    assert ValueClass.CALIBRATION.value == "calibration"
    counts = {vc: sum(1 for v in SKILL_VALUE_CLASS.values() if v is vc) for vc in ValueClass}
    assert counts[ValueClass.CALIBRATION] == 3
    assert counts[ValueClass.TRAP_DISCIPLINE] == 8
    assert counts[ValueClass.TRANSFORMATIVE_LIFT] == 0


def test_value_class_for_unregistered_is_none() -> None:
    """The honest default: an unknown skill_name → None → the guard's not-transformative
    path (CAN'T-TELL-YET), never a false CUT."""
    assert value_class_for("some-unregistered-skill") is None
    assert value_class_for("git-pull-rebase-trap") is ValueClass.TRAP_DISCIPLINE
    assert value_class_for("llm-judge-calibration") is ValueClass.CALIBRATION


# ---------------------------------------------------------------------------
# The four-record flip regression — the standing guard against the false CUT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_name", _OBS_0003_0006)
def test_obs_records_ceiling_flips_to_cant_tell_not_cut(skill_name: str) -> None:
    """THE flip regression (US-3): each of OBS-0003..0006 ceilings at p0 = 1.00 on its
    Null screen. Routed through its REGISTERED value_class, the guard must render
    CAN'T-TELL-YET (wrong instrument), never CUT(subsumed). Reintroducing the false CUT
    (dropping the class, or mapping any of these to transformative-lift) fails here."""
    vc = value_class_for(skill_name)
    assert vc is not None, f"{skill_name} must be registered"
    assert vc is not ValueClass.TRANSFORMATIVE_LIFT

    v = screen_verdict(1.0, value_class=vc)
    # CANT_TELL_YET (not CUT) with no subsumed sub-reason == the false CUT withheld.
    assert v.verdict is KeepCutVerdict.CANT_TELL_YET
    assert v.cut_sub_reason is None
    assert v.wrong_instrument is True
    assert "wrong instrument" in v.rationale.lower()


def test_calibration_ceiling_is_wrong_instrument_like_trap() -> None:
    """The new CALIBRATION class behaves at the guard exactly like trap-discipline:
    a screen ceiling is a wrong-instrument CAN'T-TELL-YET, not a subsumed CUT."""
    v = screen_verdict(1.0, value_class=ValueClass.CALIBRATION)
    assert v.verdict is KeepCutVerdict.CANT_TELL_YET
    assert v.wrong_instrument is True
