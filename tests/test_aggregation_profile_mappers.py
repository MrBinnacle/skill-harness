"""Pure mapper tests for the per-skill evaluation profile (RED first).

Covers the two axis mappers and their boundaries:
  - disposition_from_verdict: all four inputs incl. None (never screened).
  - evidence_quality_from_screen: all four ordinal outputs incl. the
    disable-model-invocation -> UNMEASURABLE and n_trials < N_MIN -> MEASURED_LOW
    boundaries.
"""

from __future__ import annotations

import pytest

from skill_harness.aggregation.profile import (
    EffectEstimate,
    EvidenceQuality,
    RankingDisposition,
    disposition_from_verdict,
    effect_per_cost,
    evidence_quality_from_screen,
)
from skill_harness.aggregation.status import N_MIN
from skill_harness.aggregation.verdict import KeepCutVerdict


class TestDispositionFromVerdict:
    def test_keep_is_admitted(self) -> None:
        assert disposition_from_verdict(KeepCutVerdict.KEEP) == RankingDisposition.ADMITTED

    def test_cut_is_excluded(self) -> None:
        assert disposition_from_verdict(KeepCutVerdict.CUT) == RankingDisposition.EXCLUDED

    def test_cant_tell_yet_is_not_yet_rankable(self) -> None:
        # Author-flagged deviation from the originating spec: a CAN'T-TELL-YET skill
        # is "a sourced candidate, not a verdict yet" (verdict.py) — it is NOT
        # admitted to ranking as if measured.
        assert (
            disposition_from_verdict(KeepCutVerdict.CANT_TELL_YET)
            == RankingDisposition.NOT_YET_RANKABLE
        )

    def test_none_never_screened_is_not_yet_rankable(self) -> None:
        assert disposition_from_verdict(None) == RankingDisposition.NOT_YET_RANKABLE


class TestEvidenceQualityFromScreen:
    def test_disable_model_invocation_is_unmeasurable(self) -> None:
        # A skill the model never auto-invokes cannot be Null-arm screened.
        # UNMEASURABLE wins even if a screen and trials are present.
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=99, is_disable_model_invocation=True
            )
            == EvidenceQuality.UNMEASURABLE
        )

    def test_no_screen_is_unmeasured(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=False, n_trials=0, is_disable_model_invocation=False
            )
            == EvidenceQuality.UNMEASURED
        )

    def test_below_n_min_is_measured_low(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN - 1, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_LOW
        )

    def test_at_n_min_is_measured_high(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_HIGH
        )

    def test_above_n_min_is_measured_high(self) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=N_MIN + 50, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_HIGH
        )

    @pytest.mark.parametrize("n_trials", [0, 1, 7])
    def test_has_screen_but_underpowered_is_measured_low(self, n_trials: int) -> None:
        assert (
            evidence_quality_from_screen(
                has_screen=True, n_trials=n_trials, is_disable_model_invocation=False
            )
            == EvidenceQuality.MEASURED_LOW
        )


class TestEffectPerCost:
    """The effect-per-cost display aid is defined ONLY where its inputs exist."""

    def test_held_none_effect_returns_none(self) -> None:
        # The current program state: no measured effect -> no eff/cost, ever.
        assert effect_per_cost(None, 100) is None

    def test_none_cost_returns_none(self) -> None:
        eff = EffectEstimate(mean=0.4, ci_lo=0.1, ci_hi=0.7, is_prior_only=False)
        assert effect_per_cost(eff, None) is None

    def test_zero_cost_returns_none(self) -> None:
        eff = EffectEstimate(mean=0.4, ci_lo=0.1, ci_hi=0.7, is_prior_only=False)
        assert effect_per_cost(eff, 0) is None

    def test_populated_effect_and_positive_cost_divides(self) -> None:
        # Executable spec for the paired path: eff/cost = mean / desc_token_cost.
        eff = EffectEstimate(mean=0.5, ci_lo=0.2, ci_hi=0.8, is_prior_only=False)
        assert effect_per_cost(eff, 200) == 0.5 / 200


class TestEstimandPassThrough:
    """#51: the profile row carries the verdict's estimand scope label verbatim
    (a qualifier on the verdict axis, sourced enum-side); None (no verdict at
    all) stays None so the renderer can show an em-dash."""

    def test_estimand_label_passes_through_to_row(self) -> None:
        from skill_harness.aggregation.profile import SkillProfileInput, build_skill_profile
        from skill_harness.semantics import PRE_REGISTRY_ESTIMAND_LABEL

        (row,) = build_skill_profile(
            [
                SkillProfileInput(
                    skill="alpha-skill",
                    verdict=KeepCutVerdict.CUT,
                    cut_sub_reason=None,
                    has_screen=True,
                    n_trials=10,
                    is_disable_model_invocation=False,
                    desc_token_cost=None,
                    fired_token_cost=None,
                    fired_usd=None,
                    estimand=PRE_REGISTRY_ESTIMAND_LABEL,
                )
            ]
        )
        assert row.estimand == PRE_REGISTRY_ESTIMAND_LABEL

    def test_estimand_defaults_to_none_when_unsourced(self) -> None:
        from skill_harness.aggregation.profile import SkillProfileInput, build_skill_profile

        (row,) = build_skill_profile(
            [
                SkillProfileInput(
                    skill="beta-skill",
                    verdict=None,
                    cut_sub_reason=None,
                    has_screen=False,
                    n_trials=0,
                    is_disable_model_invocation=False,
                    desc_token_cost=None,
                    fired_token_cost=None,
                    fired_usd=None,
                )
            ]
        )
        assert row.estimand is None
