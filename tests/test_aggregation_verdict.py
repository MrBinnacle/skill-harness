"""Tests for aggregation/verdict.py — S67/S68 keep/cut verdict layer.

One falsifying test per rule (module docstring rules A1-A3, B1-B4) plus the
program's actual data points (P4.1 headroom case, the 26/26 screen ceilings) and
the CUT(harmful) deferral gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from skill_harness.aggregation.status import ClauseStatus

if TYPE_CHECKING:
    from skill_harness.semantics import RegisteredScope
from skill_harness.aggregation.verdict import (
    TRANSFORMATIVE_NULL_CEILING,
    CutSubReason,
    KeepCutVerdict,
    harmful_verdict_supported,
    paired_verdict,
    screen_verdict,
)

# ---------------------------------------------------------------------------
# Path A — screen_verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_p0", [-0.01, 1.01, 2.0, -1.0])
def test_A1_p0_out_of_range_raises(bad_p0: float) -> None:
    with pytest.raises(ValueError, match="pass-rate"):
        screen_verdict(bad_p0)


def test_A2_total_ceiling_is_cut_subsumed() -> None:
    """p0 = 1.0 — the 26/26 program ceilings. Model never fails without the skill."""
    r = screen_verdict(1.0)
    assert r.verdict == KeepCutVerdict.CUT
    assert r.cut_sub_reason == CutSubReason.SUBSUMED
    assert "ceiling" in r.rationale.lower()


def test_A2_headroom_is_cut_subsumed_not_keep() -> None:
    """P4.1: bare p0 = 0.8 (model skips the check 1 run in 5). The S67 correction:
    still CUT(subsumed), because 0.8 is far above the ~0.3 transformative bar — a
    marginal 0.8→1.0 lift cannot clear it. Guards against the 'one KEEP' over-claim."""
    r = screen_verdict(0.8)
    assert r.verdict == KeepCutVerdict.CUT, "0.8 must not read as KEEP"
    assert r.cut_sub_reason == CutSubReason.SUBSUMED
    assert "headroom" in r.rationale.lower()


def test_A2_just_above_ceiling_is_cut() -> None:
    r = screen_verdict(TRANSFORMATIVE_NULL_CEILING + 0.01)
    assert r.verdict == KeepCutVerdict.CUT
    assert r.cut_sub_reason == CutSubReason.SUBSUMED


def test_A3_at_ceiling_is_cant_tell_yet() -> None:
    """Boundary: p0 == 0.3 is NOT above the bar → still a candidate, not a cut."""
    r = screen_verdict(TRANSFORMATIVE_NULL_CEILING)
    assert r.verdict == KeepCutVerdict.CANT_TELL_YET
    assert r.cut_sub_reason is None


def test_A3_low_p0_is_cant_tell_yet() -> None:
    """Null fails often (p0 = 0.1) — the skill COULD be transformative, but no paired
    run has confirmed it. Must NOT jump straight to KEEP."""
    r = screen_verdict(0.1)
    assert r.verdict == KeepCutVerdict.CANT_TELL_YET
    assert r.cut_sub_reason is None


def test_A3_zero_p0_is_cant_tell_yet() -> None:
    r = screen_verdict(0.0)
    assert r.verdict == KeepCutVerdict.CANT_TELL_YET


# ---------------------------------------------------------------------------
# Path B — paired_verdict
# ---------------------------------------------------------------------------


def test_B1_passed_is_keep() -> None:
    r = paired_verdict(ClauseStatus.PASSED)
    assert r.verdict == KeepCutVerdict.KEEP
    assert r.cut_sub_reason is None


def test_B2_failed_is_cut_no_lift_not_subsumed() -> None:
    """A paired FAILED is distinct from a screen ceiling — the model FAILS without
    the skill here, so 'subsumed' would be wrong."""
    r = paired_verdict(ClauseStatus.FAILED)
    assert r.verdict == KeepCutVerdict.CUT
    assert r.cut_sub_reason == CutSubReason.NO_LIFT


def test_B3_unmeasured_is_cant_tell_yet() -> None:
    r = paired_verdict(ClauseStatus.UNMEASURED)
    assert r.verdict == KeepCutVerdict.CANT_TELL_YET


def test_B4_confounded_is_cant_tell_yet() -> None:
    r = paired_verdict(ClauseStatus.CONFOUNDED)
    assert r.verdict == KeepCutVerdict.CANT_TELL_YET


# ---------------------------------------------------------------------------
# CUT(harmful) deferral
# ---------------------------------------------------------------------------


def test_harmful_not_supported_in_v1() -> None:
    """Deferred by design (S64): no signed-delta CI exists, so 'worse' cannot be
    told from 'no effect' honestly. No mapping emits HARMFUL."""
    assert harmful_verdict_supported() is False


def test_no_mapping_emits_harmful() -> None:
    screen_results = [screen_verdict(p) for p in (0.0, 0.3, 0.5, 0.8, 1.0)]
    paired_results = [paired_verdict(s) for s in ClauseStatus]
    for r in (*screen_results, *paired_results):
        assert r.cut_sub_reason != CutSubReason.HARMFUL


# ---------------------------------------------------------------------------
# Program invariant: zero production-skill KEEPs to date (the one measured KEEP,
# 2026-07-27, is a declared synthetic positive control on the paired path —
# out of scope of this screen-ceiling invariant)
# ---------------------------------------------------------------------------


def test_program_to_date_has_zero_keeps() -> None:
    """Every production-skill screen in the program ceilinged (p0 >= 0.8: the
    26/26 at 1.0 and P4.1 at 0.8). None can produce a KEEP — the S67 headline.
    If this ever fails, a real KEEP has appeared and the ship-bar #4 decision
    re-opens."""
    program_p0s = [1.0] * 26 + [0.8]  # 26/26 ceilings + P4.1
    verdicts = [screen_verdict(p).verdict for p in program_p0s]
    assert KeepCutVerdict.KEEP not in verdicts
    assert all(v == KeepCutVerdict.CUT for v in verdicts)


# ---------------------------------------------------------------------------
# Scope tuple on verdicts (#51, PR-1; resolution record #36) — every verdict is
# scoped to a registered (skill x task family x estimand x delivery mechanism)
# tuple; verdicts without one are pre-registry observations and say so.
# ---------------------------------------------------------------------------


def _registered_scope() -> RegisteredScope:
    from skill_harness.semantics import DeliveryMechanism, Estimand, RegisteredScope

    return RegisteredScope(
        skill="example-skill",
        task_family="example-family",
        estimand=Estimand.TREATMENT_POLICY,
        delivery_mechanism=DeliveryMechanism.HOOK_NUDGED,
    )


def test_screen_verdict_carries_registered_scope() -> None:
    scope = _registered_scope()
    r = screen_verdict(1.0, scope=scope)
    assert r.scope is scope
    assert r.estimand_label == "treatment-policy"


def test_paired_verdict_carries_registered_scope() -> None:
    scope = _registered_scope()
    r = paired_verdict(ClauseStatus.PASSED, scope=scope)
    assert r.scope is scope
    assert r.estimand_label == "treatment-policy"


def test_unscoped_verdict_is_a_pre_registry_observation() -> None:
    """#41's honest-marker rule: a verdict with no registered scope (every
    historical Stage-0 screen) renders estimand n/a — never a retrofitted label."""
    from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL

    r = screen_verdict(1.0)
    assert r.scope is None
    assert r.estimand_label == PRE_REGISTRY_ESTIMAND_LABEL


def test_estimand_label_values_come_from_the_enum() -> None:
    """#51 AC (DC-4 surface): every estimand string a verdict can render is an
    Estimand enum value or the ratified pre-registry marker — nothing free-typed."""
    from skill_harness.semantics import (
        PRE_REGISTRY_ESTIMAND_LABEL,
        DeliveryMechanism,
        Estimand,
        RegisteredScope,
    )

    labels = {screen_verdict(1.0).estimand_label}
    for estimand in Estimand:
        scope = RegisteredScope(
            skill="example-skill",
            task_family="example-family",
            estimand=estimand,
            delivery_mechanism=DeliveryMechanism.MODEL_PULL,
        )
        labels.add(screen_verdict(1.0, scope=scope).estimand_label)
    allowed = {e.value for e in Estimand} | {PRE_REGISTRY_ESTIMAND_LABEL}
    assert labels <= allowed
