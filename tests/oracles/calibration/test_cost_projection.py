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
    MODEL_PRICING_USD_PER_M,
    CostProjection,
    project_calibration_cost,
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
            p.n_calls = 999  # type: ignore[misc]


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
