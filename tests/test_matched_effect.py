"""Matched Gate-2 → EffectEstimate wiring (#85).

Pins the dormant-hook connection: four paired-outcome counts + a registered
Gate-2 design yield a populated EffectEstimate (signed delta + interval +
benefit/harm/equivalent/unresolved decision). Harm is first-class. The
Stage-0 screen path stays effect-free. two_arm_gate stays DIF-confined.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from skill_harness.aggregation.profile import (
    EffectEstimate,
    SkillProfileInput,
    SkillProfileRow,
    build_skill_profile,
    effect_from_matched_gate2,
)
from skill_harness.aggregation.verdict import (
    CutSubReason,
    KeepCutVerdict,
    harmful_verdict_supported,
    matched_gate2_verdict,
)
from skill_harness.oc import (
    Gate2Decision,
    Gate2Design,
    MMESpec,
    gate2_decide,
    gate2_region_probs,
)

TOL = 1e-12

# Canonical knobs shared with tests/test_oc_gate2.py (_D16).
_D16 = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))


# Hand-checkable 2x2 tables (sum to n_pairs=16). Decisions match the Gate-2
# reference table in test_oc_gate2.py.
_CASES: dict[str, tuple[int, int, int, int, Gate2Decision]] = {
    # both_pass, full_only, null_only, both_fail, expected decision
    "clear_benefit": (4, 8, 0, 4, Gate2Decision.BENEFIT),
    "clear_harm": (4, 0, 8, 4, Gate2Decision.HARM),
    "equivalent": (6, 2, 2, 6, Gate2Decision.EQUIVALENT),
    "unresolved": (5, 5, 1, 5, Gate2Decision.UNRESOLVED),
}


def _effect(
    both_pass: int,
    full_only: int,
    null_only: int,
    both_fail: int,
    *,
    design: Gate2Design = _D16,
) -> EffectEstimate:
    return effect_from_matched_gate2(
        design,
        both_pass=both_pass,
        full_only=full_only,
        null_only=null_only,
        both_fail=both_fail,
    )


class TestEffectFromMatchedGate2:
    """AC1: signed delta + interval + decision matching Gate-2 region masses."""

    @pytest.mark.parametrize("label", list(_CASES))
    def test_decision_matches_gate2_and_masses_sum_to_one(self, label: str) -> None:
        bp, xf, xn, bf, want = _CASES[label]
        probs = gate2_region_probs(_D16, xf, xn)
        assert probs.p_benefit + probs.p_harm + probs.p_equivalent == pytest.approx(1.0, abs=TOL)
        assert gate2_decide(_D16, xf, xn) is want

        eff = _effect(bp, xf, xn, bf)
        assert isinstance(eff, EffectEstimate)
        assert eff.decision is want
        assert eff.is_prior_only is False

        n = bp + xf + xn + bf
        assert n == _D16.n_pairs
        # Signed MLE delta = (full-only - null-only) / n.
        assert eff.mean == pytest.approx((xf - xn) / n, abs=TOL)
        assert -1.0 <= eff.ci_lo <= eff.mean <= eff.ci_hi <= 1.0 or (eff.ci_lo <= eff.ci_hi)
        # Interval must be a real bracket (not a point collapsed to a bare estimate).
        assert eff.ci_lo < eff.ci_hi or (xf == xn == 0)

    def test_clear_benefit_has_positive_signed_delta(self) -> None:
        bp, xf, xn, bf, _ = _CASES["clear_benefit"]
        eff = _effect(bp, xf, xn, bf)
        assert eff.mean > 0.0
        assert eff.decision is Gate2Decision.BENEFIT

    def test_clear_harm_has_negative_signed_delta(self) -> None:
        bp, xf, xn, bf, _ = _CASES["clear_harm"]
        eff = _effect(bp, xf, xn, bf)
        assert eff.mean < 0.0
        assert eff.decision is Gate2Decision.HARM
        # Entire equal-tailed bracket on the harm side for this lattice point.
        assert eff.ci_hi < 0.0


class TestHarmIsFirstClass:
    """AC2: clear harm → HARM decision; never folded into no-lift; support gate opens."""

    def test_clear_harm_decision_and_support_gate(self) -> None:
        bp, xf, xn, bf, _ = _CASES["clear_harm"]
        eff = _effect(bp, xf, xn, bf)
        assert eff.decision is Gate2Decision.HARM
        assert harmful_verdict_supported(eff) is True
        # No-arg form stays False (Stage-0 / bare-point path still unsupported).
        assert harmful_verdict_supported() is False

    def test_harm_verdict_is_never_no_lift(self) -> None:
        bp, xf, xn, bf, _ = _CASES["clear_harm"]
        eff = _effect(bp, xf, xn, bf)
        result = matched_gate2_verdict(eff)
        assert result.verdict is KeepCutVerdict.CUT
        # Harm is emitted as HARMFUL — never folded into NO_LIFT.
        assert result.cut_sub_reason is CutSubReason.HARMFUL
        assert result.cut_sub_reason.value == "harmful"

    def test_benefit_is_keep(self) -> None:
        bp, xf, xn, bf, _ = _CASES["clear_benefit"]
        result = matched_gate2_verdict(_effect(bp, xf, xn, bf))
        assert result.verdict is KeepCutVerdict.KEEP
        assert result.cut_sub_reason is None

    def test_equivalent_is_cut_no_lift_not_harmful(self) -> None:
        bp, xf, xn, bf, _ = _CASES["equivalent"]
        result = matched_gate2_verdict(_effect(bp, xf, xn, bf))
        assert result.verdict is KeepCutVerdict.CUT
        assert result.cut_sub_reason is CutSubReason.NO_LIFT

    def test_unresolved_is_cant_tell_yet(self) -> None:
        bp, xf, xn, bf, _ = _CASES["unresolved"]
        result = matched_gate2_verdict(_effect(bp, xf, xn, bf))
        assert result.verdict is KeepCutVerdict.CANT_TELL_YET
        assert result.cut_sub_reason is None


class TestProfilePopulatesEffectOnMatchedPath:
    """AC3: matched-pair result populates EffectEstimate; screen path stays None."""

    def test_matched_input_carries_populated_effect(self) -> None:
        bp, xf, xn, bf, want = _CASES["clear_benefit"]
        eff = _effect(bp, xf, xn, bf)
        (row,) = build_skill_profile(
            [
                SkillProfileInput(
                    skill="paired-skill",
                    verdict=KeepCutVerdict.KEEP,
                    cut_sub_reason=None,
                    has_screen=True,
                    n_trials=16,
                    is_disable_model_invocation=False,
                    desc_token_cost=100,
                    fired_token_cost=None,
                    fired_usd=None,
                    effect=eff,
                )
            ]
        )
        assert row.effect is not None
        assert row.effect.decision is want
        assert row.effect.mean == pytest.approx(eff.mean, abs=TOL)
        assert row.effect_per_cost == pytest.approx(eff.mean / 100, abs=TOL)

    def test_screen_path_stays_effect_free(self) -> None:
        (row,) = build_skill_profile(
            [
                SkillProfileInput(
                    skill="screen-only",
                    verdict=KeepCutVerdict.CUT,
                    cut_sub_reason=None,
                    has_screen=True,
                    n_trials=10,
                    is_disable_model_invocation=False,
                    desc_token_cost=50,
                    fired_token_cost=None,
                    fired_usd=None,
                )
            ]
        )
        assert row.effect is None
        assert row.effect_per_cost is None

    def test_anti_fusion_field_set_unchanged(self) -> None:
        """Extend the anti-fusion pin: matched population must not add fused fields."""
        expected = {
            "skill",
            "verdict",
            "cut_sub_reason",
            "estimand",
            "disposition",
            "evidence_quality",
            "desc_token_cost",
            "fired_token_cost",
            "fired_usd",
            "effect",
            "effect_per_cost",
        }
        assert {f.name for f in dataclasses.fields(SkillProfileRow)} == expected


class TestMatchedPathIsGate2NotTwoArm:
    """AC4: matched path routes through Gate-2; two_arm_gate stays DIF-confined."""

    def test_mapping_source_does_not_call_two_arm(self) -> None:
        src = inspect.getsource(effect_from_matched_gate2)
        assert "two_arm_gate" not in src.split("never")[0]  # body, not the ban docstring
        # Body must route through gate2_decide.
        body = src.split('"""', 2)[-1]
        assert "two_arm_gate(" not in body
        assert "gate2_decide" in body

    def test_mapping_module_does_not_import_two_arm(self) -> None:
        import skill_harness.aggregation.profile as profile_mod

        src = inspect.getsource(profile_mod)
        import_lines = [
            line for line in src.splitlines() if line.lstrip().startswith(("import ", "from "))
        ]
        assert not any("two_arm" in line for line in import_lines)
        assert any("skill_harness.oc" in line for line in import_lines)

    def test_no_default_delta_or_prob_threshold_on_mapping(self) -> None:
        sig = inspect.signature(effect_from_matched_gate2)
        for name in ("delta", "prob_threshold"):
            assert name not in sig.parameters
        # Design carries the pre-registered knobs; caller must supply it.
        params = sig.parameters
        assert "design" in params
        assert params["design"].default is inspect.Parameter.empty
