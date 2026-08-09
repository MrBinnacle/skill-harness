"""Mutation-killing tests for aggregation/ (#166).

Each test pins external behaviour that a surviving mutmut mutant flipped.
Standing rule: a kill is demonstrated by failing under the mutant and passing
on real code (verified via mutmut apply / mutmut run of the named mutant).
"""

from __future__ import annotations

import math

import pytest

from skill_harness.aggregation.two_arm import (
    TwoArmOutcome,
    _p_difference_exceeds,
    two_arm_gate,
)


class TestTwoArmBoundaryContracts:
    """Kill boundary / echo / label mutants in two_arm.py."""

    def test_single_trial_arm_is_valid(self) -> None:
        """n_trials >= 1 includes exactly 1 (kills n_trials < 2 / <= 1)."""
        result = two_arm_gate(1, 1, 0, 1, delta=0.0, prob_threshold=0.95)
        assert result.outcome in {
            TwoArmOutcome.TREATMENT_BETTER,
            TwoArmOutcome.TREATMENT_WORSE,
            TwoArmOutcome.NULL,
        }
        assert result.treatment_alpha == pytest.approx(2.0)
        assert result.treatment_beta == pytest.approx(1.0)

    def test_prob_threshold_one_is_valid(self) -> None:
        """prob_threshold may be exactly 1.0 (kills `<= 1.0` → `< 1.0`)."""
        result = two_arm_gate(4, 8, 4, 8, delta=0.1, prob_threshold=1.0)
        assert result.outcome is TwoArmOutcome.NULL
        assert result.prob_threshold == 1.0

    def test_result_echoes_delta_and_threshold(self) -> None:
        """Result carries the pre-registered constants (kills delta=None / threshold=None)."""
        result = two_arm_gate(5, 10, 3, 10, delta=0.15, prob_threshold=0.9)
        assert result.delta == 0.15
        assert result.prob_threshold == 0.9
        assert isinstance(result.delta, float)
        assert isinstance(result.prob_threshold, float)

    def test_invalid_treatment_trials_message_uses_treatment_label(self) -> None:
        with pytest.raises(ValueError, match=r"^treatment_trials must be >= 1"):
            two_arm_gate(0, 0, 1, 1, delta=0.1, prob_threshold=0.95)

    def test_invalid_control_trials_message_uses_control_label(self) -> None:
        with pytest.raises(ValueError, match=r"^control_trials must be >= 1"):
            two_arm_gate(1, 1, 0, 0, delta=0.1, prob_threshold=0.95)

    def test_gate_at_exact_threshold_is_directional(self) -> None:
        """`>= prob_threshold` includes equality (kills `>=` → `>`).

        Construct counts where the computed P lands extremely close to 1.0 and
        use threshold equal to the computed p so equality is the decision edge.
        """
        # Extreme separation → p_better essentially 1.0; threshold=1.0 forces
        # the equality branch: outcome is BETTER iff p_better >= 1.0.
        # With finite quadrature p may be slightly under 1; use the returned p.
        probe = two_arm_gate(40, 40, 0, 40, delta=0.0, prob_threshold=0.99)
        p = probe.p_treatment_better
        assert p >= 0.99
        # Re-run with threshold exactly equal to p (within float repr).
        at_eq = two_arm_gate(40, 40, 0, 40, delta=0.0, prob_threshold=p)
        assert at_eq.outcome is TwoArmOutcome.TREATMENT_BETTER
        # Symmetric reverse arm.
        probe_w = two_arm_gate(0, 40, 40, 40, delta=0.0, prob_threshold=0.99)
        pw = probe_w.p_treatment_worse
        at_eq_w = two_arm_gate(0, 40, 40, 40, delta=0.0, prob_threshold=pw)
        assert at_eq_w.outcome is TwoArmOutcome.TREATMENT_WORSE

    def test_null_rationale_states_power_floor_contract(self) -> None:
        """Rationale text is part of the operator-facing contract for NULL.

        Assert the concatenated clause as one string so adjacent-literal XX/case
        mutants cannot keep both halves matching independently.
        """
        result = two_arm_gate(4, 8, 4, 8, delta=0.1, prob_threshold=0.95)
        assert result.outcome is TwoArmOutcome.NULL
        assert (
            "No transformative effect resolved on this model/fixture; this is "
            "not evidence that no effect exists (registered power floor)."
        ) in result.rationale

    def test_difference_exceeds_integrates_to_unit_interval(self) -> None:
        """Quadrature upper bound is the unit interval support of Beta."""
        # P(X-Y > -1) for unit-supported betas is ~1; a wrong upper limit of 2
        # still works, but P(X-Y > 0) must stay a probability.
        p = _p_difference_exceeds(3.0, 3.0, 3.0, 3.0, 0.0)
        assert 0.0 <= p <= 1.0
        assert p == pytest.approx(0.5, abs=1e-6)
        # Clamp ceiling is 1.0: even pathological inputs must not exceed 1.
        p_hi = _p_difference_exceeds(50.0, 1.0, 1.0, 50.0, -0.5)
        assert p_hi <= 1.0 + 1e-15
        assert math.isfinite(p_hi)


# ---------------------------------------------------------------------------
# status.py — BH-FDR conjunction + equality boundary
# ---------------------------------------------------------------------------


class TestStatusFdrConjunction:
    def test_bh_fdr_false_with_low_p_is_not_fdr_failed(self) -> None:
        """FDR_CORRECTION_FAILED requires BOTH p>=threshold AND bh_fdr_pass=False.

        Kills `and` → `or`: low p with bh_fdr_pass=False must not take the FDR
        branch (falls through to underpowered/failed instead).
        """
        from skill_harness.aggregation.status import (
            ClauseStatus,
            ClauseStatusInput,
            UnmeasuredSubReason,
            derive_clause_status,
        )

        inp = ClauseStatusInput(
            axis="verbosity",
            admissible_verdict_count=40,
            total_verdict_count=40,
            confounded_verdict_count=0,
            n_verdicts=40,
            p_win_gt_threshold=0.50,
            current_frozen_case_count=1,
            any_stale_frozen_case=False,
            run_state=None,
            bh_fdr_pass=False,
        )
        status, sub = derive_clause_status(inp)
        assert sub != UnmeasuredSubReason.FDR_CORRECTION_FAILED
        assert status in {ClauseStatus.UNMEASURED, ClauseStatus.FAILED, ClauseStatus.PASSED}

    def test_bh_fdr_failed_at_exact_pass_threshold(self) -> None:
        """p == PASS_PROB_THRESHOLD with bh_fdr_pass=False → FDR_CORRECTION_FAILED.

        Kills `>=` → `>` on the FDR branch.
        """
        from skill_harness.aggregation.status import (
            PASS_PROB_THRESHOLD,
            ClauseStatus,
            ClauseStatusInput,
            UnmeasuredSubReason,
            derive_clause_status,
        )

        inp = ClauseStatusInput(
            axis="verbosity",
            admissible_verdict_count=40,
            total_verdict_count=40,
            confounded_verdict_count=0,
            n_verdicts=40,
            p_win_gt_threshold=PASS_PROB_THRESHOLD,
            current_frozen_case_count=1,
            any_stale_frozen_case=False,
            run_state=None,
            bh_fdr_pass=False,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.FDR_CORRECTION_FAILED


# ---------------------------------------------------------------------------
# errors.py — ConvergenceFailure attribute + message contract
# ---------------------------------------------------------------------------


class TestConvergenceFailureContract:
    def test_attributes_echo_constructor_args(self) -> None:
        from skill_harness.aggregation.errors import ConvergenceFailure

        exc = ConvergenceFailure(
            reason="alpha_le_zero",
            alpha_hat=-0.5,
            beta_hat=2.0,
            sample_mean=0.1,
            sample_var=0.05,
        )
        assert exc.reason == "alpha_le_zero"
        assert exc.alpha_hat == -0.5
        assert exc.beta_hat == 2.0
        assert exc.sample_mean == 0.1
        assert exc.sample_var == 0.05

    def test_none_hyperparams_render_as_none_token(self) -> None:
        from skill_harness.aggregation.errors import ConvergenceFailure

        exc = ConvergenceFailure(
            reason="var_below_threshold",
            alpha_hat=None,
            beta_hat=None,
            sample_mean=0.5,
            sample_var=1e-9,
        )
        msg = str(exc)
        assert "alpha_hat=None" in msg
        assert "beta_hat=None" in msg
        assert "XXNoneXX" not in msg
        assert "alpha_hat=none" not in msg
        assert "beta_hat=NONE" not in msg


# ---------------------------------------------------------------------------
# report.py — full structural round-trip (kills field-None / key-case mutants)
# ---------------------------------------------------------------------------


class TestReportStructuralRoundTrip:
    def test_round_trip_preserves_every_field(self) -> None:
        from skill_harness.aggregation.report import (
            REPORT_SCHEMA_VERSION,
            ClauseReport,
            ContributionSummary,
            SkillReport,
            VectorSummary,
            skill_report_from_dict,
            to_json_dict,
        )

        clause = ClauseReport(
            clause_id="c-mut",
            status="PASSED",
            sub_reason=None,
            posterior_mean=0.8125,
            credible_interval_95=(0.61, 0.93),
            p_win_gt_threshold=0.971,
            frozen_case_count_at_current_metric_version=2,
            metric_id_per_axis={"verbosity": "metric_v1"},
            metric_version_per_axis={"verbosity": "1.0.0"},
            ablation_operator_hash="deadbeef",
            run_ids_aggregated=("run-a", "run-b"),
            n_verdicts=16,
            w_observation_sum=13.0,
            subject_model="claude-sonnet-4-6",
            user_message_sha256="b" * 64,
            is_prior_only=False,
        )
        report = SkillReport(
            report_schema_version=REPORT_SCHEMA_VERSION,
            skill_id="skill-mut",
            generated_at_utc="2026-08-09T00:00:00.000Z",
            harness_version="0.2.2",
            aggregation_method="ebmom_hierarchical",
            aggregation_provenance={
                "alpha_hat": 4.0,
                "beta_hat": 2.0,
                "sample_mean": 0.7,
                "sample_var": 0.02,
                "k_clauses": 3,
                "family_size_used": 3,
            },
            clauses=(clause,),
            vector=VectorSummary(
                passed=1,
                failed=0,
                confounded=0,
                unmeasured=0,
                unmeasured_breakdown={},
                coverage=1.0,
                coverage_warnings=["note"],
            ),
            coverage=1.0,
            contribution=ContributionSummary(
                full_vs_null_delta=0.125,
                label="single-clause LOO; lower-bound under redundancy",
            ),
        )
        restored = skill_report_from_dict(to_json_dict(report))
        assert restored == report
        assert restored.clauses[0].is_prior_only is False
        assert restored.vector.coverage_warnings == ["note"]
        assert restored.contribution.label == ("single-clause LOO; lower-bound under redundancy")
        assert restored.vector.failed == 0
        assert restored.generated_at_utc == "2026-08-09T00:00:00.000Z"
        assert restored.clauses[0].frozen_case_count_at_current_metric_version == 2


# ---------------------------------------------------------------------------
# profile.py — row field fidelity
# ---------------------------------------------------------------------------


class TestProfileRowFidelity:
    def test_build_skill_profile_echoes_input_fields(self) -> None:
        from skill_harness.aggregation.profile import (
            EffectEstimate,
            SkillProfileInput,
            build_skill_profile,
        )
        from skill_harness.aggregation.verdict import KeepCutVerdict

        effect = EffectEstimate(mean=0.25, ci_lo=0.1, ci_hi=0.4, is_prior_only=False)
        inp = SkillProfileInput(
            skill="s1",
            verdict=KeepCutVerdict.KEEP,
            cut_sub_reason=None,
            has_screen=True,
            n_trials=20,
            is_disable_model_invocation=False,
            desc_token_cost=100,
            fired_token_cost=50,
            fired_usd=0.01,
            estimand="matched_gate2",
            effect=effect,
        )
        rows = build_skill_profile([inp])
        assert len(rows) == 1
        row = rows[0]
        assert row.skill == "s1"
        assert row.verdict == KeepCutVerdict.KEEP.value
        assert row.fired_usd == 0.01
        assert row.desc_token_cost == 100
        assert row.effect is not None
        assert row.effect.mean == pytest.approx(0.25)
        assert row.effect_per_cost == pytest.approx(0.25 / 100)

    def test_effect_from_matched_gate2_rejects_empty_and_mismatched(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.oc import Gate2Design, MMESpec

        design = Gate2Design(n_pairs=4, gamma=0.95, mme=MMESpec(delta_min=0.1, q_min=0.7))
        with pytest.raises(ValueError, match="at least one pair"):
            effect_from_matched_gate2(design, both_pass=0, full_only=0, null_only=0, both_fail=0)
        with pytest.raises(ValueError, match="design.n_pairs=4"):
            effect_from_matched_gate2(design, both_pass=1, full_only=0, null_only=0, both_fail=0)


# ---------------------------------------------------------------------------
# verdict.py — scope + rationale contracts
# ---------------------------------------------------------------------------


def _scope() -> object:
    from skill_harness.semantics import (
        DeliveryMechanism,
        Estimand,
        RegisteredScope,
    )

    return RegisteredScope(
        skill="s1",
        task_family="tf",
        estimand=Estimand.TREATMENT_POLICY,
        delivery_mechanism=DeliveryMechanism.MODEL_PULL,
    )


class TestVerdictContracts:
    def test_matched_gate2_harm_keeps_scope_and_rationale(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.aggregation.verdict import (
            CutSubReason,
            KeepCutVerdict,
            matched_gate2_verdict,
        )
        from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec

        design = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
        effect = effect_from_matched_gate2(
            design, both_pass=4, full_only=0, null_only=8, both_fail=4
        )
        assert effect.decision is Gate2Decision.HARM
        scope = _scope()
        result = matched_gate2_verdict(effect, scope=scope)  # type: ignore[arg-type]
        assert result.verdict is KeepCutVerdict.CUT
        assert result.cut_sub_reason is CutSubReason.HARMFUL
        assert result.scope is scope
        assert result.rationale is not None
        assert "CUT (harmful)" in result.rationale
        assert "First-class harm" in result.rationale

    def test_matched_gate2_equivalent_keeps_scope(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.aggregation.verdict import (
            CutSubReason,
            KeepCutVerdict,
            ValueClass,
            matched_gate2_verdict,
        )
        from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec

        design = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
        effect = effect_from_matched_gate2(
            design, both_pass=6, full_only=2, null_only=2, both_fail=6
        )
        assert effect.decision is Gate2Decision.EQUIVALENT
        scope = _scope()
        result = matched_gate2_verdict(
            effect,
            scope=scope,  # type: ignore[arg-type]
            value_class=ValueClass.TRANSFORMATIVE_LIFT,
        )
        assert result.verdict is KeepCutVerdict.CUT
        assert result.cut_sub_reason is CutSubReason.NO_LIFT
        assert result.scope is scope

    def test_matched_gate2_unresolved_keeps_scope(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.aggregation.verdict import (
            KeepCutVerdict,
            matched_gate2_verdict,
        )
        from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec

        design = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
        effect = effect_from_matched_gate2(
            design, both_pass=5, full_only=5, null_only=1, both_fail=5
        )
        assert effect.decision is Gate2Decision.UNRESOLVED
        scope = _scope()
        result = matched_gate2_verdict(effect, scope=scope)  # type: ignore[arg-type]
        assert result.verdict is KeepCutVerdict.CANT_TELL_YET
        assert result.scope is scope
        assert "CAN'T-TELL-YET" in (result.rationale or "")


# ---------------------------------------------------------------------------
# fit.py — ClauseFit field fidelity + ConvergenceFailure kwargs
# ---------------------------------------------------------------------------


class TestFitFieldFidelity:
    def test_unpooled_fit_preserves_w_and_n(self) -> None:
        from skill_harness.aggregation.fit import ClauseObservations, fit_skill

        clauses = [
            ClauseObservations(clause_id="a", w=3.0, n=8),
            ClauseObservations(clause_id="b", w=5.0, n=8),
        ]
        result = fit_skill(clauses)
        by_id = {c.clause_id: c for c in result.posteriors}
        assert by_id["a"].w == 3.0
        assert by_id["a"].n == 8
        assert by_id["b"].w == 5.0
        assert by_id["b"].n == 8
        assert by_id["a"].w is not None
        assert by_id["b"].n is not None

    def test_ebmom_raises_preserve_alpha_beta_on_failure(self) -> None:
        """Direct unit path: _ebmom ConvergenceFailure carries both hats."""
        from skill_harness.aggregation.errors import ConvergenceFailure
        from skill_harness.aggregation.fit import _ebmom

        with pytest.raises(ConvergenceFailure) as ei:
            _ebmom(0.01, 0.2)
        exc = ei.value
        assert exc.reason == "alpha_le_zero"
        assert exc.alpha_hat is not None
        assert exc.beta_hat is not None
        assert exc.sample_mean == pytest.approx(0.01)
        assert exc.sample_var == pytest.approx(0.2)

    def test_unpooled_is_shrunken_false_not_none(self) -> None:
        from skill_harness.aggregation.fit import ClauseObservations, fit_skill

        result = fit_skill([ClauseObservations(clause_id="a", w=1.0, n=2)])
        assert result.posteriors[0].is_shrunken is False

    def test_shrunken_fit_preserves_w_and_n(self) -> None:
        """K>=K_MIN_FOR_EB EB path must echo per-clause w/n (kills w=None / n=None)."""
        from skill_harness.aggregation.fit import ClauseObservations, fit_skill

        # Spread means so EB-MoM converges (avoid var floor / alpha<=0).
        clauses = [ClauseObservations(clause_id=f"c{i}", w=float(i), n=20) for i in range(10)]
        result = fit_skill(clauses)
        assert result.aggregation_method == "ebmom_hierarchical"
        by_id = {c.clause_id: c for c in result.posteriors}
        assert by_id["c0"].w == 0.0 and by_id["c0"].w is not None
        assert by_id["c0"].n == 20 and by_id["c0"].n is not None
        assert by_id["c9"].w == 9.0
        assert by_id["c9"].n == 20
        assert by_id["c0"].is_shrunken is True


class TestErrorMessageContracts:
    def test_precondition_error_message_embeds_code(self) -> None:
        from skill_harness.aggregation.errors import PreconditionError

        exc = PreconditionError("no_clauses", None)
        assert "PreconditionError" in str(exc)
        assert "no_clauses" in str(exc)
        assert exc.code == "no_clauses"

    def test_malformed_run_config_preserves_run_id_and_message(self) -> None:
        from skill_harness.aggregation.errors import MalformedRunConfig

        exc = MalformedRunConfig("missing family_size", "run-42")
        assert exc.run_id == "run-42"
        assert exc.run_id is not None
        assert "run-42" in str(exc)
        assert "missing family_size" in str(exc)

    def test_convergence_failure_message_formats_numeric_hats(self) -> None:
        from skill_harness.aggregation.errors import ConvergenceFailure

        exc = ConvergenceFailure(
            reason="alpha_le_zero",
            alpha_hat=-1.25,
            beta_hat=3.5,
            sample_mean=0.2,
            sample_var=0.1,
        )
        msg = str(exc)
        assert "alpha_hat=-1.2500" in msg
        assert "beta_hat=3.5000" in msg


class TestProfileKillers:
    def test_effect_per_cost_at_unit_cost(self) -> None:
        """desc_token_cost == 1 is valid (kills <= 0 → <= 1)."""
        from skill_harness.aggregation.profile import EffectEstimate, effect_per_cost

        effect = EffectEstimate(mean=0.5, ci_lo=0.1, ci_hi=0.9, is_prior_only=False)
        assert effect_per_cost(effect, 1) == pytest.approx(0.5)
        assert effect_per_cost(effect, 0) is None

    def test_negative_pair_count_message(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.oc import Gate2Design, MMESpec

        design = Gate2Design(n_pairs=4, gamma=0.95, mme=MMESpec(delta_min=0.1, q_min=0.7))
        with pytest.raises(ValueError, match=r"all four paired-outcome counts must be >= 0"):
            effect_from_matched_gate2(design, both_pass=-1, full_only=0, null_only=0, both_fail=0)
        with pytest.raises(ValueError, match=r"^the 2x2 table must contain at least one pair$"):
            effect_from_matched_gate2(design, both_pass=0, full_only=0, null_only=0, both_fail=0)

    def test_profile_sorts_by_skill_and_echoes_disposition(self) -> None:
        from skill_harness.aggregation.profile import (
            EffectEstimate,
            SkillProfileInput,
            build_skill_profile,
        )
        from skill_harness.aggregation.verdict import CutSubReason, KeepCutVerdict

        effect = EffectEstimate(mean=0.2, ci_lo=0.0, ci_hi=0.4, is_prior_only=False)
        inputs = [
            SkillProfileInput(
                skill="z-last",
                verdict=KeepCutVerdict.CUT,
                cut_sub_reason=CutSubReason.NO_LIFT,
                has_screen=True,
                n_trials=20,
                is_disable_model_invocation=False,
                desc_token_cost=10,
                fired_token_cost=7,
                fired_usd=0.02,
                estimand="matched_gate2",
                effect=effect,
            ),
            SkillProfileInput(
                skill="a-first",
                verdict=KeepCutVerdict.KEEP,
                cut_sub_reason=None,
                has_screen=True,
                n_trials=20,
                is_disable_model_invocation=False,
                desc_token_cost=10,
                fired_token_cost=3,
                fired_usd=0.01,
                estimand="matched_gate2",
                effect=effect,
            ),
        ]
        rows = build_skill_profile(inputs)
        assert [r.skill for r in rows] == ["a-first", "z-last"]
        assert rows[0].disposition == "ADMITTED"
        assert rows[0].disposition is not None
        assert rows[0].fired_token_cost == 3
        assert rows[0].fired_token_cost is not None
        assert rows[0].cut_sub_reason is None
        assert rows[1].cut_sub_reason == CutSubReason.NO_LIFT.value
        assert rows[1].fired_token_cost == 7
        assert rows[0].evidence_quality in {"measured_high", "MEASURED_HIGH"}

    def test_disable_model_invocation_is_unmeasurable(self) -> None:
        from skill_harness.aggregation.profile import SkillProfileInput, build_skill_profile
        from skill_harness.aggregation.verdict import KeepCutVerdict

        rows = build_skill_profile(
            [
                SkillProfileInput(
                    skill="dm",
                    verdict=KeepCutVerdict.CANT_TELL_YET,
                    cut_sub_reason=None,
                    has_screen=True,
                    n_trials=20,
                    is_disable_model_invocation=True,
                    desc_token_cost=1,
                    fired_token_cost=0,
                    fired_usd=0.0,
                    estimand=None,
                    effect=None,
                )
            ]
        )
        assert rows[0].evidence_quality in {"unmeasurable", "UNMEASURABLE"}


class TestReportKillers:
    def test_round_trip_with_sub_reason_and_prior_only_true(self) -> None:
        """Kills sub_reason=None always and is_prior_only default/key mutants."""
        from skill_harness.aggregation.report import (
            REPORT_SCHEMA_VERSION,
            ClauseReport,
            ContributionSummary,
            SkillReport,
            VectorSummary,
            skill_report_from_dict,
            to_json_bytes,
            to_json_dict,
        )

        clause = ClauseReport(
            clause_id="c-prior",
            status="UNMEASURED",
            sub_reason="no_data",
            posterior_mean=0.5,
            credible_interval_95=(0.025, 0.975),
            p_win_gt_threshold=0.4,
            frozen_case_count_at_current_metric_version=0,
            metric_id_per_axis={},
            metric_version_per_axis={},
            ablation_operator_hash="deadbeef",
            run_ids_aggregated=("run-a",),
            n_verdicts=0,
            w_observation_sum=0.0,
            subject_model=None,
            user_message_sha256=None,
            is_prior_only=True,
        )
        report = SkillReport(
            report_schema_version=REPORT_SCHEMA_VERSION,
            skill_id="skill-prior",
            generated_at_utc="2026-08-09T00:00:00.000Z",
            harness_version="0.2.2",
            aggregation_method="unpooled",
            aggregation_provenance={"k_clauses": 1},
            clauses=(clause,),
            vector=VectorSummary(
                passed=0,
                failed=0,
                confounded=0,
                unmeasured=1,
                unmeasured_breakdown={"no_data": 1},
                coverage=0.0,
                coverage_warnings=[],
            ),
            coverage=0.0,
            contribution=ContributionSummary(
                full_vs_null_delta=None,
                label="single-clause LOO; lower-bound under redundancy",
            ),
        )
        d = to_json_dict(report)
        assert d["clauses"][0]["is_prior_only"] is True
        assert "is_prior_only" in d["clauses"][0]
        assert d["clauses"][0]["sub_reason"] == "no_data"
        restored = skill_report_from_dict(d)
        assert restored.clauses[0].is_prior_only is True
        assert restored.clauses[0].sub_reason == "no_data"
        # Missing-key default: drop is_prior_only → False.
        d2 = to_json_dict(report)
        del d2["clauses"][0]["is_prior_only"]
        restored_default = skill_report_from_dict(d2)
        assert restored_default.clauses[0].is_prior_only is False
        raw = to_json_bytes(report)
        assert raw.endswith(b"\n")
        assert b"is_prior_only" in raw
        # Missing coverage_warnings defaults to [].
        d3 = to_json_dict(report)
        del d3["vector"]["coverage_warnings"]
        restored_cw = skill_report_from_dict(d3)
        assert restored_cw.vector.coverage_warnings == []


class TestVerdictScopeAndRationale:
    def test_screen_subsumed_keeps_scope_and_rationale_text(self) -> None:
        from skill_harness.aggregation.verdict import (
            CutSubReason,
            KeepCutVerdict,
            ValueClass,
            screen_verdict,
        )

        scope = _scope()
        # High null ceiling → CUT subsumed when transformative-lift.
        result = screen_verdict(
            p0=0.95,
            scope=scope,  # type: ignore[arg-type]
            value_class=ValueClass.TRANSFORMATIVE_LIFT,
        )
        assert result.verdict is KeepCutVerdict.CUT
        assert result.cut_sub_reason is CutSubReason.SUBSUMED
        assert result.scope is scope
        assert result.rationale is not None
        assert "CUT" in result.rationale or "subsumed" in result.rationale.lower()

    def test_screen_unclassified_wrong_instrument_rationale(self) -> None:
        from skill_harness.aggregation.verdict import KeepCutVerdict, screen_verdict

        scope = _scope()
        result = screen_verdict(p0=0.95, scope=scope, value_class=None)  # type: ignore[arg-type]
        assert result.verdict is KeepCutVerdict.CANT_TELL_YET
        assert result.scope is scope
        assert result.rationale is not None
        assert "no value class yet" in result.rationale
        assert "subsumed CUT is withheld" in result.rationale

    def test_screen_below_ceiling_keeps_scope(self) -> None:
        from skill_harness.aggregation.verdict import KeepCutVerdict, screen_verdict

        scope = _scope()
        result = screen_verdict(p0=0.1, scope=scope)  # type: ignore[arg-type]
        assert result.verdict is KeepCutVerdict.CANT_TELL_YET
        assert result.scope is scope
        assert result.rationale is not None
        assert "CAN'T-TELL-YET" in result.rationale

    def test_paired_keep_and_cut_rationale_and_scope(self) -> None:
        from skill_harness.aggregation.status import ClauseStatus
        from skill_harness.aggregation.verdict import (
            CutSubReason,
            KeepCutVerdict,
            paired_verdict,
        )

        scope = _scope()
        keep = paired_verdict(ClauseStatus.PASSED, scope=scope)  # type: ignore[arg-type]
        assert keep.verdict is KeepCutVerdict.KEEP
        assert keep.scope is scope
        assert keep.rationale is not None
        assert "KEEP" in keep.rationale
        assert "transformative bar" in keep.rationale

        cut = paired_verdict(ClauseStatus.FAILED, scope=scope)  # type: ignore[arg-type]
        assert cut.verdict is KeepCutVerdict.CUT
        assert cut.cut_sub_reason is CutSubReason.NO_LIFT
        assert cut.scope is scope
        assert cut.rationale is not None
        assert "CUT (no lift)" in cut.rationale
        assert "Not 'subsumed'" in cut.rationale

        unm = paired_verdict(ClauseStatus.UNMEASURED, scope=scope)  # type: ignore[arg-type]
        assert unm.verdict is KeepCutVerdict.CANT_TELL_YET
        assert unm.scope is scope
        assert unm.rationale is not None

        conf = paired_verdict(ClauseStatus.CONFOUNDED, scope=scope)  # type: ignore[arg-type]
        assert conf.verdict is KeepCutVerdict.CANT_TELL_YET
        assert conf.scope is scope

    def test_matched_gate2_benefit_keeps_scope_and_rationale(self) -> None:
        from skill_harness.aggregation.profile import effect_from_matched_gate2
        from skill_harness.aggregation.verdict import KeepCutVerdict, matched_gate2_verdict
        from skill_harness.oc import Gate2Decision, Gate2Design, MMESpec

        design = Gate2Design(n_pairs=16, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
        effect = effect_from_matched_gate2(
            design, both_pass=2, full_only=10, null_only=0, both_fail=4
        )
        assert effect.decision is Gate2Decision.BENEFIT
        scope = _scope()
        result = matched_gate2_verdict(effect, scope=scope)  # type: ignore[arg-type]
        assert result.verdict is KeepCutVerdict.KEEP
        assert result.scope is scope
        assert result.rationale is not None
        assert "KEEP" in result.rationale
        assert "signed delta=" in result.rationale
        assert "95% CI" in result.rationale
