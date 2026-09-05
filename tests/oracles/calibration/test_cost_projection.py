"""Tests for cost_projection.py — A36 formula correctness, cache-reuse pct,
hard ceiling rejection, and SE/CI stat projections.

TDD RED phase: all tests should fail until cost_projection.py is created.
"""

from __future__ import annotations

import os

import pytest


# ------------------------------------------------------------------
# Verify PYTHONHASHSEED=0 discipline (A33 inherited by all tier-1/calibration tests)
# ------------------------------------------------------------------
def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0", (
        "PYTHONHASHSEED must be set to 0 for deterministic tests. Run with: PYTHONHASHSEED=0 pytest"
    )


# ------------------------------------------------------------------
# Import the module under test
# ------------------------------------------------------------------
from skill_harness.oracles.calibration.cost_projection import (  # noqa: E402
    DAILY_CAP_HARD_CEILING_USD,
    EVALUATION_HARD_CAP_USD,
    MODEL_PRICING_USD_PER_M,
    CostProjection,
    project_calibration_cost,
    project_pair_usd,
    project_pair_usd_cache_aware,
    project_trial_usd,
)

# ------------------------------------------------------------------
# MODEL_PRICING_USD_PER_M dict — only the three models we use
# ------------------------------------------------------------------


class TestModelPricingDict:
    """MODEL_PRICING_USD_PER_M contains exactly the 3 models we use."""

    def test_sonnet_4_6_present(self) -> None:
        assert "claude-sonnet-4-6" in MODEL_PRICING_USD_PER_M

    def test_opus_4_7_present(self) -> None:
        assert "claude-opus-4-7" in MODEL_PRICING_USD_PER_M

    def test_haiku_4_5_present(self) -> None:
        assert "claude-haiku-4-5" in MODEL_PRICING_USD_PER_M

    def test_no_stale_models(self) -> None:
        """Only the 3 models we actually use — no claude-3-* stale entries."""
        assert len(MODEL_PRICING_USD_PER_M) == 3

    def test_sonnet_4_6_input_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-sonnet-4-6"]["input"] == pytest.approx(3.0)

    def test_sonnet_4_6_output_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-sonnet-4-6"]["output"] == pytest.approx(15.0)

    def test_sonnet_4_6_cache_read_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-sonnet-4-6"]["cache_read"] == pytest.approx(0.30)

    def test_sonnet_4_6_cache_write_price(self) -> None:
        # 1.25x input rate for cache write
        assert MODEL_PRICING_USD_PER_M["claude-sonnet-4-6"]["cache_write"] == pytest.approx(3.75)

    def test_opus_4_7_input_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-opus-4-7"]["input"] == pytest.approx(5.0)

    def test_opus_4_7_output_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-opus-4-7"]["output"] == pytest.approx(25.0)

    def test_opus_4_7_cache_read_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-opus-4-7"]["cache_read"] == pytest.approx(0.50)

    def test_haiku_4_5_input_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-haiku-4-5"]["input"] == pytest.approx(1.0)

    def test_haiku_4_5_output_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-haiku-4-5"]["output"] == pytest.approx(5.0)

    def test_haiku_4_5_cache_read_price(self) -> None:
        assert MODEL_PRICING_USD_PER_M["claude-haiku-4-5"]["cache_read"] == pytest.approx(0.10)


class TestModelPricingSingleSourceOfTruth:
    """F3 regression: MODEL_PRICING_USD_PER_M must be derived from — never a
    second hand-maintained copy of — skill_harness.ablation.subject.PRICE_PER_MTOK.

    Before F3, the two tables were independent dicts with one overlapping
    entry (claude-sonnet-4-6) that merely happened to agree; nothing enforced
    that a price change applied to one would reach the other."""

    def test_every_judge_model_matches_canonical_table(self) -> None:
        from skill_harness.ablation.subject import PRICE_PER_MTOK

        for model, rates in MODEL_PRICING_USD_PER_M.items():
            assert rates == PRICE_PER_MTOK[model], (
                f"{model} pricing drifted from the canonical PRICE_PER_MTOK table"
            )


# ------------------------------------------------------------------
# CostProjection Pydantic model fields
# ------------------------------------------------------------------


class TestCostProjectionModel:
    """CostProjection is a frozen Pydantic model with the required fields."""

    def _make_projection(self) -> CostProjection:
        return project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=1000,
            tool_schema_tokens=500,
            candidate_output_avg_tokens=290,
        )

    def test_has_n_calls(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "n_calls")

    def test_has_t_in_cached(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "t_in_cached")

    def test_has_t_in_uncached(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "t_in_uncached")

    def test_has_t_in_cache_read(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "t_in_cache_read")

    def test_has_t_out(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "t_out")

    def test_has_usd(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "usd")

    def test_has_cache_reuse_pct(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "cache_reuse_pct")

    def test_has_est_se_pairwise_agreement(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "est_se_pairwise_agreement")

    def test_has_est_ci_95_width(self) -> None:
        p = self._make_projection()
        assert hasattr(p, "est_ci_95_width")

    def test_is_frozen(self) -> None:
        """CostProjection is immutable (frozen Pydantic model)."""
        p = self._make_projection()
        with pytest.raises(Exception):
            p.n_calls = 999


# ------------------------------------------------------------------
# A36 formula correctness — N=50, Sonnet 4.6
# ------------------------------------------------------------------


class TestA36FormulaCorrectnessN50Sonnet:
    """Verify the A36 cost formula against the dispatch brief numbers.

    Dispatch brief says: ~$0.31 on claude-sonnet-4-6 at N=50 pairs with cache.
    Parameters (brief-specified example):
      system_prompt_tokens=1500 (from "1.5K cached prefix")
      tool_schema_tokens=0  (included in system_prompt_tokens in the brief example)
      candidate_output_avg_tokens=290  (580 tokens per pair / 2 responses)
    N_calls = 50 x 2 = 100
    """

    def _proj(self) -> CostProjection:
        # Use parameters matching brief's "1.5K cached prefix x 99 reads + 580 uncached tail x 100"
        # system+tool combined = 1500 tokens, candidate_output = 290 avg per side
        return project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=1500,
            tool_schema_tokens=0,
            candidate_output_avg_tokens=290,
        )

    def test_n_calls(self) -> None:
        # N_calls = N_pairs x 2 per A6 position swap
        assert self._proj().n_calls == 100

    def test_cache_reuse_pct_near_71(self) -> None:
        # Brief says "cache reuse: 71% on input"
        p = self._proj()
        assert 65.0 <= p.cache_reuse_pct <= 78.0, f"cache_reuse_pct={p.cache_reuse_pct}"

    def test_usd_in_range_sonnet_cached(self) -> None:
        # Brief says ~$0.31 with cache on sonnet-4-6 at N=50
        p = self._proj()
        assert 0.20 <= p.usd <= 0.50, f"usd={p.usd:.4f} outside [0.20, 0.50]"

    def test_usd_much_less_than_uncached_cost(self) -> None:
        """Cached cost is significantly less than uncached cost at N=50."""
        cached = self._proj()
        # Uncached would be: N_calls x (system+tool+candidates) x $3/M input + output cost
        n_calls = 100
        total_input_tok = n_calls * (1500 + 290 * 2)
        uncached_usd = (total_input_tok / 1_000_000) * 3.0 + (n_calls * 50 / 1_000_000) * 15.0
        # Cached should be noticeably less expensive
        assert cached.usd < uncached_usd * 0.85, (
            f"cached={cached.usd:.4f} not significantly less than uncached={uncached_usd:.4f}"
        )

    def test_t_out_positive(self) -> None:
        assert self._proj().t_out > 0

    def test_t_in_cache_read_positive(self) -> None:
        # 99 cache reads (all calls after the first)
        assert self._proj().t_in_cache_read > 0


# ------------------------------------------------------------------
# A36 formula: detailed token accounting
# ------------------------------------------------------------------


class TestA36TokenAccounting:
    """Verify individual token-count fields in the projection formula."""

    def _proj(
        self,
        n_pairs: int = 10,
        system_prompt_tokens: int = 1000,
        tool_schema_tokens: int = 200,
        candidate_output_avg_tokens: int = 150,
    ) -> CostProjection:
        return project_calibration_cost(
            n_pairs=n_pairs,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=system_prompt_tokens,
            tool_schema_tokens=tool_schema_tokens,
            candidate_output_avg_tokens=candidate_output_avg_tokens,
        )

    def test_n_calls_equals_n_pairs_times_2(self) -> None:
        for n in (1, 10, 50, 100):
            p = project_calibration_cost(
                n_pairs=n,
                model_id="claude-sonnet-4-6",
                system_prompt_tokens=500,
                tool_schema_tokens=100,
                candidate_output_avg_tokens=100,
            )
            assert p.n_calls == n * 2

    def test_t_out_equals_n_calls_times_50(self) -> None:
        """T_out = N_calls x 50 tokens estimate per A36."""
        p = self._proj(n_pairs=10)
        expected_t_out = 20 * 50  # 10 pairs x 2 calls x 50 tokens
        assert p.t_out == expected_t_out

    def test_t_in_cache_read_formula(self) -> None:
        """T_in_cache_read = (N_calls - 1) x (system_prompt_tokens + tool_schema_tokens)."""
        n_pairs = 10
        sp_tok = 1000
        ts_tok = 200
        p = project_calibration_cost(
            n_pairs=n_pairs,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=sp_tok,
            tool_schema_tokens=ts_tok,
            candidate_output_avg_tokens=150,
        )
        expected_cache_read = (n_pairs * 2 - 1) * (sp_tok + ts_tok)
        assert p.t_in_cache_read == expected_cache_read

    def test_t_in_uncached_is_first_call_tokens(self) -> None:
        """t_in_uncached = system_prompt_tokens + tool_schema_tokens + pair_unique_tokens
        for the first call (the only uncached portion).
        """
        sp_tok = 1000
        ts_tok = 200
        cand_avg = 150
        p = project_calibration_cost(
            n_pairs=10,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=sp_tok,
            tool_schema_tokens=ts_tok,
            candidate_output_avg_tokens=cand_avg,
        )
        # t_in_uncached = first call's full input tokens
        # pair_unique_tokens = candidate_output_avg_tokens * 2 (one per side)
        pair_tok = cand_avg * 2
        expected_uncached = sp_tok + ts_tok + pair_tok
        assert p.t_in_uncached == expected_uncached


# ------------------------------------------------------------------
# SE / CI stat projections (bayesian-eval-discipline)
# ------------------------------------------------------------------


class TestSECIProjections:
    """est_SE_pairwise_agreement and est_CI_95_width from bayesian-eval-discipline.

    Formula:
        est_se = sqrt(0.7 * 0.3 / N_pairs)
        est_ci_95_width = 2 * 1.96 * est_se
    """

    def test_se_at_n50(self) -> None:
        import math

        p = project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=500,
            tool_schema_tokens=100,
            candidate_output_avg_tokens=100,
        )
        expected_se = math.sqrt(0.7 * 0.3 / 50)
        assert p.est_se_pairwise_agreement == pytest.approx(expected_se, rel=1e-6)

    def test_ci_width_at_n50(self) -> None:
        import math

        p = project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=500,
            tool_schema_tokens=100,
            candidate_output_avg_tokens=100,
        )
        expected_se = math.sqrt(0.7 * 0.3 / 50)
        expected_ci = 2 * 1.96 * expected_se
        assert p.est_ci_95_width == pytest.approx(expected_ci, rel=1e-6)

    def test_se_at_n100_half_n50(self) -> None:
        """SE at N=100 should be smaller than SE at N=50."""
        p50 = project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=500,
            tool_schema_tokens=100,
            candidate_output_avg_tokens=100,
        )
        p100 = project_calibration_cost(
            n_pairs=100,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=500,
            tool_schema_tokens=100,
            candidate_output_avg_tokens=100,
        )
        assert p100.est_se_pairwise_agreement < p50.est_se_pairwise_agreement

    def test_se_matches_brief_example(self) -> None:
        """Brief dry-run output: est_SE_pairwise_agreement: 0.065 at N=50."""
        p = project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=1500,
            tool_schema_tokens=0,
            candidate_output_avg_tokens=290,
        )
        assert p.est_se_pairwise_agreement == pytest.approx(0.065, abs=0.002)

    def test_ci_matches_formula(self) -> None:
        """est_CI_95_width = 2 * 1.96 * est_se (bayesian-eval-discipline formula).

        Note: the dispatch brief's dry-run example shows 0.127 which is 1.96*SE
        (one-sided half-width). The authoritative formula in bayesian-eval-discipline
        and the dispatch text says 2 * 1.96 * est_se (full two-sided width = ~0.254).
        We verify the full two-sided formula.
        """
        import math

        p = project_calibration_cost(
            n_pairs=50,
            model_id="claude-sonnet-4-6",
            system_prompt_tokens=1500,
            tool_schema_tokens=0,
            candidate_output_avg_tokens=290,
        )
        expected_se = math.sqrt(0.7 * 0.3 / 50)
        expected_ci = 2 * 1.96 * expected_se
        assert p.est_ci_95_width == pytest.approx(expected_ci, rel=1e-6)


# ------------------------------------------------------------------
# Hard ceiling rejection
# ------------------------------------------------------------------


class TestDailyCapHardCeiling:
    """DAILY_CAP_HARD_CEILING_USD = 100.0 is a named constant."""

    def test_hard_ceiling_value(self) -> None:
        assert pytest.approx(100.0) == DAILY_CAP_HARD_CEILING_USD


# ------------------------------------------------------------------
# #56 / #40: evaluation cap + live per-pair / per-trial projections
# ------------------------------------------------------------------


class TestEvaluationHardCap:
    """#40 (operator-picked values decision): $35 per skill-task evaluation,
    registered as a named constant next to the daily ceiling (drift row DC-10
    pins both against the doc quotes)."""

    def test_cap_value(self) -> None:
        assert EVALUATION_HARD_CAP_USD == 35.0

    def test_cap_sits_under_the_daily_ceiling(self) -> None:
        assert EVALUATION_HARD_CAP_USD < DAILY_CAP_HARD_CEILING_USD


class TestPairAndTrialProjections:
    """#40(c): the frontier's cost column is PRICE_PER_MTOK x calibrated
    tokens — never a hard-coded per-pair dollar constant (drift row DC-9).
    These projections are deliberately worst-case: full input rate, no cache
    discount (a hard cap that assumes savings is not hard, #40(b))."""

    def test_pair_literal_sonnet(self) -> None:
        # 200k in x $3/M + 4k out x $15/M = 0.60 + 0.06
        usd = project_pair_usd(
            "claude-sonnet-4-6",
            input_tokens_per_pair=200_000,
            output_tokens_per_pair=4_000,
        )
        assert usd == pytest.approx(0.66)

    def test_pair_literal_haiku(self) -> None:
        # 200k in x $1/M + 4k out x $5/M = 0.20 + 0.02
        usd = project_pair_usd(
            "claude-haiku-4-5",
            input_tokens_per_pair=200_000,
            output_tokens_per_pair=4_000,
        )
        assert usd == pytest.approx(0.22)

    def test_trial_literal_sonnet(self) -> None:
        # 100k in x $3/M + 2k out x $15/M = 0.30 + 0.03
        usd = project_trial_usd(
            "claude-sonnet-4-6",
            input_tokens_per_trial=100_000,
            output_tokens_per_trial=2_000,
        )
        assert usd == pytest.approx(0.33)

    def test_rates_flow_from_the_canonical_table(self) -> None:
        """Mirror of the F3 single-source-of-truth regression: the projection
        must reproduce arithmetic done directly against PRICE_PER_MTOK."""
        from skill_harness.ablation.subject import PRICE_PER_MTOK

        for model in ("claude-sonnet-4-6", "claude-opus-4-7", "gpt-5.4"):
            rates = PRICE_PER_MTOK[model]
            expected = 123_456 * rates["input"] / 1e6 + 7_890 * rates["output"] / 1e6
            usd = project_pair_usd(
                model, input_tokens_per_pair=123_456, output_tokens_per_pair=7_890
            )
            assert usd == pytest.approx(expected)

    def test_unknown_model_raises_not_defaults(self) -> None:
        """A cap projection must never silently price the wrong model."""
        with pytest.raises(KeyError):
            project_pair_usd(
                "claude-nonexistent", input_tokens_per_pair=1000, output_tokens_per_pair=100
            )

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValueError):
            project_pair_usd(
                "claude-sonnet-4-6", input_tokens_per_pair=-1, output_tokens_per_pair=100
            )
        with pytest.raises(ValueError):
            project_trial_usd(
                "claude-sonnet-4-6", input_tokens_per_trial=100, output_tokens_per_trial=-1
            )

    def test_pair_literal_sonnet_5(self) -> None:
        # 486212.75 in x $2/M + 54777.625 out x $10/M = 0.9724255 + 0.54777625
        usd = project_pair_usd(
            "claude-sonnet-5",
            input_tokens_per_pair=486212.75,
            output_tokens_per_pair=54777.625,
        )
        assert usd == pytest.approx(1.52020175)

    def test_trial_literal_sonnet_5(self) -> None:
        # 249623.25 in x $2/M + 29456 out x $10/M = 0.4992465 + 0.29456
        usd = project_trial_usd(
            "claude-sonnet-5",
            input_tokens_per_trial=249623.25,
            output_tokens_per_trial=29456,
        )
        assert usd == pytest.approx(0.7938065)


# ------------------------------------------------------------------
# #436: cache-aware pair projector — reduction control + class pricing
# ------------------------------------------------------------------


class TestCacheAwarePairProjector:
    """#436: project_pair_usd_cache_aware prices each token class from
    PRICE_PER_MTOK and reproduces project_pair_usd at share zero (the
    reduction control — #40(c) worst-case discipline is a special case)."""

    def test_reduction_control_at_share_zero_sonnet(self) -> None:
        """At cache_read_share=0.0 with cache_read=0 and cache_write=0,
        the cache-aware projector reproduces project_pair_usd exactly —
        all input tokens priced at full input rate, no cache discount."""
        worst_case = project_pair_usd(
            "claude-sonnet-4-6",
            input_tokens_per_pair=200_000,
            output_tokens_per_pair=4_000,
        )
        cache_aware = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=200_000,
            cache_read_tokens=0,
            cache_write_tokens=0,
            output_tokens=4_000,
            cache_read_share=0.0,
        )
        assert cache_aware == pytest.approx(worst_case)

    def test_reduction_control_at_share_zero_haiku(self) -> None:
        """Reduction control on a second model — haiku 4.5."""
        worst_case = project_pair_usd(
            "claude-haiku-4-5",
            input_tokens_per_pair=100_000,
            output_tokens_per_pair=2_000,
        )
        cache_aware = project_pair_usd_cache_aware(
            "claude-haiku-4-5",
            input_tokens=100_000,
            cache_read_tokens=0,
            cache_write_tokens=0,
            output_tokens=2_000,
            cache_read_share=0.0,
        )
        assert cache_aware == pytest.approx(worst_case)

    def test_cache_read_tokens_priced_at_cache_read_rate(self) -> None:
        """Cache-read tokens use the cache_read rate, not the input rate.
        Sonnet 4.6: input=$3/M, cache_read=$0.30/M.
        100k input + 100k cache_read + 0 cache_write + 4k output:
        = 100k*3/M + 100k*0.30/M + 4k*15/M = 0.30 + 0.03 + 0.06 = 0.39"""
        usd = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=100_000,
            cache_read_tokens=100_000,
            cache_write_tokens=0,
            output_tokens=4_000,
            cache_read_share=0.5,
        )
        assert usd == pytest.approx(0.39)

    def test_cache_write_tokens_priced_at_cache_write_rate(self) -> None:
        """Cache-write tokens use the cache_write rate.
        Sonnet 4.6: cache_write=$3.75/M.
        0 input + 0 cache_read + 50k cache_write + 2k output:
        = 50k*3.75/M + 2k*15/M = 0.1875 + 0.03 = 0.2175"""
        usd = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=50_000,
            output_tokens=2_000,
            cache_read_share=0.0,
        )
        assert usd == pytest.approx(0.2175)

    def test_all_four_classes_combined(self) -> None:
        """All four token classes priced independently from PRICE_PER_MTOK.
        Sonnet 4.6: input=$3, output=$15, cache_write=$3.75, cache_read=$0.30 per MTok.
        10k*3/M + 20k*0.30/M + 5k*3.75/M + 3k*15/M
        = 0.03 + 0.006 + 0.01875 + 0.045 = 0.09975"""
        usd = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=10_000,
            cache_read_tokens=20_000,
            cache_write_tokens=5_000,
            output_tokens=3_000,
            cache_read_share=2 / 3,
        )
        assert usd == pytest.approx(0.09975)

    def test_unknown_model_raises_not_defaults(self) -> None:
        """A cache-aware projection must never silently price the wrong model."""
        with pytest.raises(KeyError):
            project_pair_usd_cache_aware(
                "claude-nonexistent",
                input_tokens=1000,
                cache_read_tokens=0,
                cache_write_tokens=0,
                output_tokens=100,
                cache_read_share=0.0,
            )

    def test_negative_tokens_rejected(self) -> None:
        """Negative token counts in any class are rejected."""
        with pytest.raises(ValueError):
            project_pair_usd_cache_aware(
                "claude-sonnet-4-6",
                input_tokens=-1,
                cache_read_tokens=0,
                cache_write_tokens=0,
                output_tokens=100,
                cache_read_share=0.0,
            )
        with pytest.raises(ValueError):
            project_pair_usd_cache_aware(
                "claude-sonnet-4-6",
                input_tokens=0,
                cache_read_tokens=-1,
                cache_write_tokens=0,
                output_tokens=100,
                cache_read_share=0.0,
            )
        with pytest.raises(ValueError):
            project_pair_usd_cache_aware(
                "claude-sonnet-4-6",
                input_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=-1,
                output_tokens=100,
                cache_read_share=0.0,
            )
        with pytest.raises(ValueError):
            project_pair_usd_cache_aware(
                "claude-sonnet-4-6",
                input_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                output_tokens=-1,
                cache_read_share=0.0,
            )

    def test_cache_read_share_is_metadata(self) -> None:
        """The cache_read_share argument is a declared input, not used in the
        cost calculation — different shares with the same token split produce
        the same USD (the share is recorded alongside, not applied to price)."""
        usd_a = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=100_000,
            cache_read_tokens=50_000,
            cache_write_tokens=10_000,
            output_tokens=2_000,
            cache_read_share=0.3,
        )
        usd_b = project_pair_usd_cache_aware(
            "claude-sonnet-4-6",
            input_tokens=100_000,
            cache_read_tokens=50_000,
            cache_write_tokens=10_000,
            output_tokens=2_000,
            cache_read_share=0.9,
        )
        assert usd_a == pytest.approx(usd_b)

    def test_sonnet_5_all_cache_classes(self) -> None:
        """Sonnet 5 pricing: input=$2, output=$10, cache_write=$2.50, cache_read=$0.20.
        486212.75*2/M + 1000*0.20/M + 500*2.50/M + 54777.625*10/M
        = 0.9724255 + 0.0002 + 0.00125 + 0.54777625 = 1.52165175"""
        usd = project_pair_usd_cache_aware(
            "claude-sonnet-5",
            input_tokens=486_212.75,
            cache_read_tokens=1_000,
            cache_write_tokens=500,
            output_tokens=54_777.625,
            cache_read_share=0.002,
        )
        assert usd == pytest.approx(1.52165175)
