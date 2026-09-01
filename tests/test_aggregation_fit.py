"""Tests for aggregation/fit.py — EB-MoM hierarchical fit + BH-FDR fallback (A53).

Coverage:
- EB-MoM well-behaved case: K >= 10, valid alpha/beta, shrunken posteriors
- EB-MoM: hand-checked simple case [(5,10),(6,10),(7,10)] + extended to K=10
- Convergence failure: sample_var < 1e-6 → BH-FDR fallback
- Convergence failure: alpha_hat <= 0 → BH-FDR fallback
- Input precondition: a clause with n <= 0 is rejected on BOTH K paths (#231)
- Input precondition: a clause with w outside [0, n] is rejected on BOTH K paths (#232)
- UNPOOLED fallback: K < 10 → logged warning + unpooled posteriors
- Pass/fail thresholds correct in posteriors
- BH-FDR: correct clause IDs pass/fail after adjustment
- Determinism: same inputs → same output bytes
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skill_harness.aggregation.errors import ConvergenceFailure
from skill_harness.aggregation.fit import (
    HETEROGENEITY_TEST_ALPHA,
    K_MIN_FOR_EB,
    VAR_FLOOR,
    ClauseObservations,
    ClausePosterior,
    FitResult,
    _bh_fdr,
    _ebmom,
    fit_skill,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_clauses(wn_pairs: Sequence[tuple[float, int]]) -> list[ClauseObservations]:
    # Hypothesis generates fractional w here, which in production would imply
    # ties, and (w, n) alone does not determine sum_sq. For observations in
    # [0, 1] the feasible range is w^2/n <= sum_sq <= w, so the tie-free
    # extreme sum_sq = w is both valid and the MOST dispersed member of that
    # set -- the hardest case for the sampling-variance peel. These properties
    # assert only that the fit does not crash and returns valid Betas, so
    # picking the adversarial end of the feasible set is the right default.
    return [
        ClauseObservations.bernoulli(clause_id=f"c{i}", w=w, n=n)
        for i, (w, n) in enumerate(wn_pairs)
    ]


# ---------------------------------------------------------------------------
# _ebmom unit tests
# ---------------------------------------------------------------------------


class TestEbmom:
    def test_hand_checked_simple(self) -> None:
        """Hand-verify MoM for rates [0.5, 0.6, 0.7].

        sample_mean = 0.6, sample_var = (0.01 + 0.0 + 0.01) / 3 ≈ 0.006667
        common = 0.6 * 0.4 / 0.006667 - 1 ≈ 35.0
        alpha_hat ≈ 0.6 * 35 = 21.0
        beta_hat ≈ 0.4 * 35 = 14.0
        """
        m = 0.6
        v = (0.01 + 0.0 + 0.01) / 3  # population var of [0.5, 0.6, 0.7]
        alpha_hat, beta_hat = _ebmom(m, v)
        # Expected: common = 0.6*0.4/v - 1
        common = m * (1 - m) / v - 1
        expected_alpha = m * common
        expected_beta = (1 - m) * common
        assert abs(alpha_hat - expected_alpha) < 1e-8
        assert abs(beta_hat - expected_beta) < 1e-8
        assert alpha_hat > 0
        assert beta_hat > 0

    def test_low_variance_raises_convergence_failure(self) -> None:
        """sample_var < VAR_FLOOR → ConvergenceFailure(var_below_threshold)."""
        with pytest.raises(ConvergenceFailure) as exc_info:
            _ebmom(0.6, VAR_FLOOR / 2)
        assert exc_info.value.reason == "var_below_threshold"

    def test_zero_variance_raises_convergence_failure(self) -> None:
        """Exact zero variance → ConvergenceFailure."""
        with pytest.raises(ConvergenceFailure) as exc_info:
            _ebmom(0.5, 0.0)
        assert exc_info.value.reason == "var_below_threshold"

    def test_extreme_mean_alpha_le_zero(self) -> None:
        """sample_mean near 0 with large variance → alpha_hat <= 0."""
        # m very small, v large enough → common = m(1-m)/v - 1 < 0 → alpha=m*common<0
        # Need m*(1-m)/v < 1 → v > m*(1-m)
        m = 0.05
        v = 0.5  # >> m*(1-m)=0.0475, so common < 0
        with pytest.raises(ConvergenceFailure) as exc_info:
            _ebmom(m, v)
        assert exc_info.value.reason in ("alpha_le_zero", "beta_le_zero")

    def test_extreme_mean_beta_le_zero(self) -> None:
        """sample_mean near 1 with large variance → beta_hat <= 0."""
        m = 0.95
        v = 0.5  # >> m*(1-m)=0.0475
        with pytest.raises(ConvergenceFailure) as exc_info:
            _ebmom(m, v)
        assert exc_info.value.reason in ("alpha_le_zero", "beta_le_zero")

    def test_moderate_params_succeed(self) -> None:
        """Moderate mean/variance → valid alpha/beta > 0."""
        alpha, beta = _ebmom(0.65, 0.01)
        assert alpha > 0
        assert beta > 0


# ---------------------------------------------------------------------------
# fit_skill: observation-count precondition — must not depend on K (#231)
# ---------------------------------------------------------------------------


class TestFitSkillObservationCountPrecondition:
    """#231: the same payload must not get two answers depending on K.

    Adjudicated contract: raise a clear ValueError naming the bad clause on
    BOTH K paths. Before the fix, K < 10 accepted an n=0 clause as Beta(1,1)
    (RED: "DID NOT RAISE") while K >= 10 crashed in the EB prelude at
    ``rates = [cl.w / cl.n ...]`` (RED: ZeroDivisionError) — so the K >= 10
    parametrization below is the half that carried the crash and must not be
    filed under a K-specific section.
    """

    @pytest.mark.parametrize("k", [K_MIN_FOR_EB - 1, K_MIN_FOR_EB])
    def test_nonpositive_observation_count_rejected_before_method_selection(self, k: int) -> None:
        clauses = [
            ClauseObservations.bernoulli(clause_id=f"c{i}", w=3.0, n=10) for i in range(k - 1)
        ]
        clauses.append(ClauseObservations.bernoulli(clause_id="unmeasured", w=0.0, n=0))

        with pytest.raises(ValueError, match="unmeasured") as exc_info:
            fit_skill(clauses)
        # "naming the bad clause" — not "naming some clause".
        assert "c0" not in str(exc_info.value), str(exc_info.value)

    def test_precondition_is_documented_in_the_public_docstring(self) -> None:
        """The docstring is where a caller reads the contract (``help``/``__doc__``).

        #231 AC — undocumented is how the K-divergence survived: nothing said
        n >= 1 was required, so both behaviours looked defensible.
        """
        doc = fit_skill.__doc__ or ""
        assert "ValueError" in doc, doc
        assert any(phrase in doc for phrase in ("n <= 0", "n > 0", "n >= 1")), doc


# ---------------------------------------------------------------------------
# fit_skill: win-weight precondition — must not depend on K (#232)
# ---------------------------------------------------------------------------


class TestFitSkillWinWeightPrecondition:
    """#232: w is a win-weight sum over n observations, so w > n is not data.

    Unguarded it is silent on BOTH K paths, and differently silent, which is why
    this sits in its own K-neutral section (the #231 lesson):
      - K < 10: unpooled Beta(1 + w, 1 + n - w) takes a non-positive second
        parameter, so scipy answers nan for the interval and the pass
        probability while posterior_mean walks above 1.0;
      - K >= 10: the empirical rate w / n exceeds 1, so the hyperprior is fit to
        a mean outside the support and every clause's shrinkage moves with it.
    Neither raises, and a nan pass probability reads as "not passing" rather
    than as "inadmissible input" downstream.
    """

    @pytest.mark.parametrize("k", [K_MIN_FOR_EB - 1, K_MIN_FOR_EB])
    def test_wins_above_observations_rejected_before_method_selection(self, k: int) -> None:
        clauses = [
            ClauseObservations.bernoulli(clause_id=f"c{i}", w=3.0, n=10) for i in range(k - 1)
        ]
        clauses.append(ClauseObservations.bernoulli(clause_id="overcounted", w=11.0, n=10))

        with pytest.raises(ValueError, match="overcounted") as exc_info:
            fit_skill(clauses)
        message = str(exc_info.value)
        # "naming the bad clause" — not "naming some clause".
        assert "c0" not in message, message
        # Names the violated bound, so the caller is not sent looking at n.
        assert "w" in message, message

    def test_negative_win_weight_rejected(self) -> None:
        """The lower bound too: w sums weights in {0, 0.5, 1}, so w < 0 is not data.

        Left unguarded it is the same failure mode from the other side —
        Beta(1 + w, ...) takes a non-positive FIRST parameter.
        """
        with pytest.raises(ValueError, match="undercounted"):
            fit_skill([ClauseObservations.bernoulli(clause_id="undercounted", w=-1.0, n=10)])

    def test_every_observation_a_win_is_admissible(self) -> None:
        """w == n is the boundary that must NOT raise: every observation a win.

        Guards the fix against over-rejection (``w < n``) — a real skill that
        wins every comparison must still be fittable.
        """
        result = fit_skill([ClauseObservations.bernoulli(clause_id="perfect", w=10.0, n=10)])
        assert result.posteriors[0].w == 10.0
        assert result.posteriors[0].posterior_beta > 0.0

    def test_precondition_is_documented_in_the_public_docstring(self) -> None:
        """#232 mirrors #231 AC 2: the contract a caller reads must state it."""
        doc = fit_skill.__doc__ or ""
        assert "ValueError" in doc, doc
        assert "[0, n]" in doc, doc


# ---------------------------------------------------------------------------
# fit_skill: UNPOOLED path (K < 10)
# ---------------------------------------------------------------------------


class TestFitSkillUnpooled:
    def test_k_below_10_returns_unpooled(self, caplog: pytest.LogCaptureFixture) -> None:
        """K=3 → method='unpooled', provenance has reason='k_below_10'."""
        clauses = make_clauses([(5, 10), (6, 10), (7, 10)])
        import logging

        with caplog.at_level(logging.WARNING, logger="skill_harness.aggregation.fit"):
            result = fit_skill(clauses)
        assert result.aggregation_method == "unpooled"
        assert result.aggregation_provenance["reason"] == "k_below_10"
        assert result.aggregation_provenance["k_clauses"] == 3
        assert "EB hyperprior estimate unreliable" in caplog.text

    def test_unpooled_posteriors_are_not_shrunken(self) -> None:
        """K<10: all posteriors have is_shrunken=False."""
        clauses = make_clauses([(5, 10)] * 5)
        result = fit_skill(clauses)
        assert all(not p.is_shrunken for p in result.posteriors)

    def test_unpooled_posterior_formula(self) -> None:
        """K<10: Beta(1+w, 1+n-w) unpooled posterior."""
        # w=6, n=10 → alpha=7, beta=5 → mean=7/12
        clauses = make_clauses([(6.0, 10)])
        result = fit_skill(clauses)
        p = result.posteriors[0]
        expected_mean = 7.0 / 12.0
        assert abs(p.posterior_mean - expected_mean) < 1e-6

    def test_k_exactly_10_uses_ebmom_or_fallback(self) -> None:
        """K=10 attempts EB-MoM (not UNPOOLED)."""
        # Use rates with enough variance to converge. w <= n on every clause:
        # w > n is inadmissible (#232), so it cannot be the source of variance.
        clauses = make_clauses([(i + 1, 10) for i in range(10)])  # rates 0.1 .. 1.0
        result = fit_skill(clauses)
        # Should NOT be unpooled (K=10 >= K_MIN_FOR_EB=10)
        assert result.aggregation_method != "unpooled"


# ---------------------------------------------------------------------------
# fit_skill: EB-MoM hierarchical path (K >= 10)
# ---------------------------------------------------------------------------


class TestFitSkillEbmom:
    def _make_k10_clauses_with_variance(self) -> list[ClauseObservations]:
        """K=10 clauses with meaningful rate variance.

        Every clause satisfies w <= n: ``(3 + i, 10)`` over ``range(10)`` used to
        run to (11, 10) and (12, 10), i.e. rates 1.1 and 1.2. Those are not
        observations (#232) and the shrunken fit answered them with a negative
        Beta parameter, posterior_mean 1.025 and a nan credible interval, which
        every assertion in this class was green on.
        """
        # rates 0.3 .. 0.9, then padded to the K=10 EB floor at 0.8 — no rate
        # above 1.0, and no degenerate rate == 1.0.
        #
        # n=50 rather than n=10 (#360). The rate STRUCTURE is unchanged; only
        # the observation count per clause moved. At n=10 this spread is not
        # separable from binomial noise around a common rate: latent variance
        # 0.01956 against a null 95th percentile of 0.02067, so the
        # heterogeneity test correctly refuses it and the fit never reaches the
        # hierarchical path these tests exist to exercise. At n=50 the same
        # heterogeneity is identified with a wide margin (0.03661 vs 0.00355).
        # The refusal at n=10 is itself pinned by
        # test_marginal_heterogeneity_is_refused_not_fitted below, so this
        # change moves the INPUT that reaches the path under test rather than
        # erasing the behaviour change that made it necessary.
        pairs: list[tuple[float, int]] = [(15.0 + 5 * i, 50) for i in range(7)]
        pairs += [(40.0, 50)] * 3
        return make_clauses(pairs)

    def test_ebmom_method_returned(self) -> None:
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        assert result.aggregation_method == "ebmom_hierarchical"

    def test_marginal_heterogeneity_is_refused_not_fitted(self) -> None:
        """K=10, n=10, rates 0.3-0.9 is NOT identifiably heterogeneous (#360).

        This is the fixture these tests used before the heterogeneity gate
        landed, and it reached the hierarchical path. It no longer does, and
        that is the intended behaviour change rather than a regression: with
        ten clauses of ten trials, a 0.3-to-0.9 spread of observed rates is
        inside what binomial noise around a single common rate produces. The
        old code answered it with a hyperprior fitted to that noise.

        Pinned here so the change is asserted somewhere. Widening the fixture
        to n=50 to exercise the hierarchical path would otherwise delete the
        evidence that the gate does anything.
        """
        pairs: list[tuple[float, int]] = [(3.0 + i, 10) for i in range(7)]
        pairs += [(8.0, 10)] * 3
        result = fit_skill(make_clauses(pairs))

        assert result.aggregation_method == "bh_fdr_fallback"
        prov = result.aggregation_provenance
        assert prov["fallback_reason"] == "latent_variance_not_identified", (
            f"expected a refusal on identification grounds, got {prov['fallback_reason']!r}"
        )
        # The refusal must be auditable: a reader has to be able to see the
        # test that produced it, not just that something was refused.
        attempted = prov["attempted"]
        assert isinstance(attempted, dict)
        test = attempted["heterogeneity_test"]
        assert isinstance(test, dict)
        for field in ("statistic", "critical_value", "alpha", "bootstrap_b", "bootstrap_seed"):
            assert field in test, f"provenance is missing {field!r}"
        assert test["statistic"] <= test["critical_value"]
        assert test["alpha"] == HETEROGENEITY_TEST_ALPHA

    def test_admission_verdict_is_deterministic(self) -> None:
        """The bootstrap must not make fit_skill non-deterministic (#360).

        The seed is derived from the observations, so the same input gives the
        same critical value and the same verdict on every run. A wall-clock or
        global-RNG seed would make a published verdict irreproducible.
        """
        clauses = self._make_k10_clauses_with_variance()
        first = fit_skill(clauses)
        second = fit_skill(clauses)

        assert first.aggregation_method == second.aggregation_method
        t1 = first.aggregation_provenance["heterogeneity_test"]
        t2 = second.aggregation_provenance["heterogeneity_test"]
        assert isinstance(t1, dict) and isinstance(t2, dict)
        assert t1["critical_value"] == t2["critical_value"]
        assert t1["bootstrap_seed"] == t2["bootstrap_seed"]

    def test_provenance_fields_present(self) -> None:
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        prov = result.aggregation_provenance
        assert "alpha_hat" in prov
        assert "beta_hat" in prov
        assert "sample_mean" in prov
        assert "sample_var" in prov
        assert "k_clauses" in prov
        assert prov["k_clauses"] == 10

    def test_shrunken_posteriors(self) -> None:
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        assert all(p.is_shrunken for p in result.posteriors)

    def test_shrunken_alpha_beta_formula(self) -> None:
        """Shrunken posterior: alpha = alpha_hat + w, beta = beta_hat + (n-w)."""
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        prov = result.aggregation_provenance
        alpha_hat = float(prov["alpha_hat"])  # type: ignore[arg-type]
        beta_hat = float(prov["beta_hat"])  # type: ignore[arg-type]
        for i, p in enumerate(result.posteriors):
            w = clauses[i].w
            n = clauses[i].n
            expected_alpha = alpha_hat + w
            expected_beta = beta_hat + (n - w)
            assert abs(p.posterior_alpha - expected_alpha) < 1e-8
            assert abs(p.posterior_beta - expected_beta) < 1e-8

    def test_no_bh_fdr_passes(self) -> None:
        """EB-MoM result has bh_fdr_passes=None."""
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        assert result.bh_fdr_passes is None

    def test_posteriors_count_matches_clauses(self) -> None:
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        assert len(result.posteriors) == len(clauses)

    def test_posterior_clause_ids_match(self) -> None:
        clauses = self._make_k10_clauses_with_variance()
        result = fit_skill(clauses)
        input_ids = [c.clause_id for c in clauses]
        output_ids = [p.clause_id for p in result.posteriors]
        assert input_ids == output_ids

    def test_high_win_rate_high_p(self) -> None:
        """Clause with w/n=0.9 across K=10 clauses should have high p_exceeds."""
        # All clauses identical → no variance → would fall to BH-FDR
        # Mix rates so EB-MoM converges; one clause at high rate
        pairs: list[tuple[float, int]] = [(5.0, 10)] * 9 + [(9.0, 10)]
        clauses = make_clauses(pairs)
        result = fit_skill(clauses)
        # The high-rate clause should have p_win_gt_threshold > 0
        high_p = result.posteriors[-1]
        assert high_p.p_win_gt_threshold > 0


# ---------------------------------------------------------------------------
# fit_skill: BH-FDR fallback path
# ---------------------------------------------------------------------------


class TestFitSkillBhFdrFallback:
    def _make_degenerate_clauses(self) -> list[ClauseObservations]:
        """K=10 clauses all with identical rate → sample_var < VAR_FLOOR → fallback."""
        return make_clauses([(6, 10)] * 10)

    def test_fallback_method_returned(self) -> None:
        clauses = self._make_degenerate_clauses()
        result = fit_skill(clauses)
        assert result.aggregation_method == "bh_fdr_fallback"

    def test_fallback_provenance(self) -> None:
        clauses = self._make_degenerate_clauses()
        result = fit_skill(clauses)
        prov = result.aggregation_provenance
        assert prov["q"] == 0.05
        assert prov["k_clauses"] == 10
        assert "fallback_reason" in prov
        assert "attempted" in prov

    def test_fallback_posteriors_not_shrunken(self) -> None:
        """BH-FDR uses unpooled posteriors."""
        clauses = self._make_degenerate_clauses()
        result = fit_skill(clauses)
        assert all(not p.is_shrunken for p in result.posteriors)

    def test_bh_fdr_passes_not_none(self) -> None:
        clauses = self._make_degenerate_clauses()
        result = fit_skill(clauses)
        assert result.bh_fdr_passes is not None
        assert isinstance(result.bh_fdr_passes, frozenset)

    def test_bh_fdr_with_strong_winner(self) -> None:
        """Clause with very high p_exceeds should pass BH-FDR."""
        # Mix: 9 identical clauses (degenerate → fallback), 1 strong clause
        # But all-identical means K=10 with no variance → fallback
        # To force fallback while having one high-p clause:
        # use 9 at rate=0.6 (borderline) and 1 at rate=0.95
        # But then variance won't be zero... use all-identical to force fallback
        # then separately test BH logic
        clauses = make_clauses([(6, 10)] * 10)
        result = fit_skill(clauses)
        # w=6, n=10 → rate=0.6 → posterior Beta(7,5) → p = sf(0.6, 7, 5) ≈ 0.5
        # p_value for BH = 1 - 0.5 = 0.5 → likely doesn't pass BH-FDR at q=0.05
        # Result: none or few pass. Just check the type.
        assert isinstance(result.bh_fdr_passes, frozenset)


# ---------------------------------------------------------------------------
# T3: BH-FDR direct unit tests + fit-level test with obvious winner
# ---------------------------------------------------------------------------


class TestBhFdrDirect:
    def test_bh_fdr_known_input_known_output(self) -> None:
        """T3a: hand-computed _bh_fdr with known input → known output set.

        BH at q=0.05, k=4 clauses, p-values: [0.001, 0.01, 0.04, 0.5]
        Sorted ascending: [0.001, 0.01, 0.04, 0.5]
        BH thresholds (rank/k * q): [1/4*0.05, 2/4*0.05, 3/4*0.05, 4/4*0.05]
                                   = [0.0125,    0.025,    0.0375,   0.05]
        Comparisons:
          rank 1: p=0.001 <= 0.0125 → PASS (index 0)
          rank 2: p=0.01  <= 0.025  → PASS (index 1)
          rank 3: p=0.04  > 0.0375  → FAIL; but BH step-up: largest passing rank=2,
                                       so indices at ranks 1+2 pass = {0, 1}
          rank 4: p=0.5   > 0.05    → FAIL
        Expected: {0, 1}
        """
        p_values = [0.001, 0.01, 0.04, 0.5]
        result = _bh_fdr(p_values, q=0.05)
        assert isinstance(result, frozenset)
        assert result == frozenset({0, 1}), (
            f"Expected {{0, 1}} (indices of p=0.001 and p=0.01), got {result}"
        )

    def test_bh_fdr_all_pass_when_very_small(self) -> None:
        """T3a: all p-values tiny → all indices pass."""
        p_values = [0.0001, 0.0002, 0.0003]
        result = _bh_fdr(p_values, q=0.05)
        assert result == frozenset({0, 1, 2})

    def test_bh_fdr_none_pass_when_large(self) -> None:
        """T3a: all p-values large → empty set."""
        p_values = [0.5, 0.6, 0.7]
        result = _bh_fdr(p_values, q=0.05)
        assert result == frozenset()

    def test_bh_fdr_empty_input_returns_empty(self) -> None:
        """T3a: empty input → frozenset()."""
        result = _bh_fdr([], q=0.05)
        assert result == frozenset()

    def test_fit_fallback_with_obvious_winner_clause_in_bh_fdr_passes(self) -> None:
        """T3b: bimodal distribution → alpha_le_zero fallback fires AND winner in bh_fdr_passes.

        Strategy: 5 all-loss clauses (w=0, n=10) + 4 all-win clauses (w=10, n=10) + 1 winner.
        Bimodal distribution (mean=0.5, var=mean*(1-mean)) makes alpha_hat → 0 → fallback.
        The all-wins winner must appear in bh_fdr_passes (p ≈ 0 → survives BH correction).
        """
        # 5 pure-loss + 4 pure-win clauses → bimodal → alpha_hat = 0 → fallback
        clauses: list[ClauseObservations] = []
        for i in range(5):
            clauses.append(ClauseObservations.bernoulli(clause_id=f"loss-{i}", w=0.0, n=10))
        for i in range(4):
            clauses.append(ClauseObservations.bernoulli(clause_id=f"win-{i}", w=10.0, n=10))
        winner = ClauseObservations.bernoulli(clause_id="winner-clause", w=10.0, n=10)
        clauses.append(winner)
        assert len(clauses) == 10  # K=10 to satisfy EB eligibility gate

        result = fit_skill(clauses)

        # Verify fallback was triggered (alpha_le_zero from bimodal distribution)
        assert result.aggregation_method == "bh_fdr_fallback", (
            f"Expected bh_fdr_fallback, got {result.aggregation_method!r}"
        )
        assert result.bh_fdr_passes is not None

        # The obvious winner (p_value ≈ 0) must be in bh_fdr_passes
        assert "winner-clause" in result.bh_fdr_passes, (
            f"winner-clause (all-wins) not in bh_fdr_passes={result.bh_fdr_passes!r}. "
            "BH-FDR selection logic may be broken."
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestFitDeterminism:
    def test_same_input_same_output(self) -> None:
        """Running fit_skill twice on identical input returns identical posteriors."""
        clauses = make_clauses([(5 + i % 3, 10) for i in range(10)])
        r1 = fit_skill(clauses)
        r2 = fit_skill(clauses)
        assert r1.aggregation_method == r2.aggregation_method
        assert len(r1.posteriors) == len(r2.posteriors)
        for p1, p2 in zip(r1.posteriors, r2.posteriors):
            assert p1.posterior_mean == p2.posterior_mean
            assert p1.p_win_gt_threshold == p2.p_win_gt_threshold

    def test_credible_interval_in_bounds(self) -> None:
        """95% CI lo < mean < hi for all posteriors."""
        clauses = make_clauses([(5 + i % 4, 10) for i in range(10)])
        result = fit_skill(clauses)
        for p in result.posteriors:
            assert 0.0 <= p.credible_interval_lo <= p.posterior_mean
            assert p.posterior_mean <= p.credible_interval_hi <= 1.0


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@given(
    wn_pairs=st.lists(
        st.tuples(
            st.floats(min_value=0.0, max_value=10.0),
            st.integers(min_value=1, max_value=40),
        ),
        min_size=K_MIN_FOR_EB,
        max_size=50,
    )
)
@settings(max_examples=50, deadline=None)
def test_fit_skill_no_crash(wn_pairs: list[tuple[float, int]]) -> None:
    """fit_skill never raises for valid (w, n) inputs where 0 <= w <= n."""
    # Clip w <= n to satisfy constraint
    safe_pairs = [(min(w, float(n)), n) for w, n in wn_pairs]
    clauses = make_clauses(safe_pairs)
    result = fit_skill(clauses)
    assert result.aggregation_method in ("ebmom_hierarchical", "bh_fdr_fallback", "unpooled")
    assert len(result.posteriors) == len(clauses)


@given(
    wn_pairs=st.lists(
        st.tuples(
            st.floats(min_value=0.5, max_value=1.0),
            st.integers(min_value=1, max_value=40),
        ),
        min_size=K_MIN_FOR_EB,
        max_size=50,
    )
)
@settings(max_examples=30, deadline=None)
def test_posteriors_are_valid_betas(wn_pairs: list[tuple[float, int]]) -> None:
    """All posteriors have alpha > 0, beta > 0, 0 <= mean <= 1."""
    safe_pairs = [(min(w * n, float(n)), n) for w, n in wn_pairs]
    clauses = make_clauses(safe_pairs)
    result = fit_skill(clauses)
    for p in result.posteriors:
        assert p.posterior_alpha > 0
        assert p.posterior_beta > 0
        assert 0.0 <= p.posterior_mean <= 1.0
        assert 0.0 <= p.p_win_gt_threshold <= 1.0


# ---------------------------------------------------------------------------
# M1 · mut_84 · EB-MoM convergence guard: valid alpha_hat > 0 must not raise
#   Kills mutation: alpha_hat <= 0.0 → alpha_hat <= 1.0
#   At m=0.5, v = 0.25/(alpha_hat + 0.5). alpha_hat=beta_hat by symmetry.
# ---------------------------------------------------------------------------


def _var_for_alpha_hat(alpha_hat: float, m: float = 0.5) -> float:
    """Back-compute sample_var that produces given alpha_hat at given mean.

    From alpha_hat = m * (m*(1-m)/v - 1):
        v = m*(1-m) / (alpha_hat/m + 1)
    """
    return m * (1.0 - m) / (alpha_hat / m + 1.0)


@pytest.mark.parametrize(
    "alpha_hat_target, should_raise",
    [
        (-0.001, True),
        (0.0, True),
        (0.001, False),
        (0.5, False),
        (1.0, False),
        (1.5, False),
        (5.0, False),
    ],
)
def test_ebmom_convergence_guard_alpha_hat_boundary(
    alpha_hat_target: float, should_raise: bool
) -> None:
    """M1: alpha_hat <= 0 must raise; alpha_hat > 0 must not raise.

    Killing test: mutation alpha_hat<=0.0 → alpha_hat<=1.0 causes alpha_hat in
    (0, 1] to raise, failing the should_raise=False cases.
    """
    m = 0.5
    if alpha_hat_target <= 0.0:
        # var must be > VAR_FLOOR to reach the alpha_hat check.
        # At m=0.5, common=0 → alpha_hat=0 when v = m*(1-m) = 0.25.
        # For negative: v slightly > 0.25 → common < 0 → alpha_hat < 0.
        v = 0.25 / (alpha_hat_target / m + 1.0) if alpha_hat_target != 0.0 else 0.25 + 1e-9
        # Ensure v is well above VAR_FLOOR so we reach the alpha/beta check.
        assert v > VAR_FLOOR * 1000, f"v={v} too small; test design error"
    else:
        v = _var_for_alpha_hat(alpha_hat_target, m)
        assert v > VAR_FLOOR * 1000

    if should_raise:
        with pytest.raises(ConvergenceFailure):
            _ebmom(m, v)
    else:
        alpha_hat, beta_hat = _ebmom(m, v)
        assert alpha_hat > 0.0
        assert beta_hat > 0.0


# ---------------------------------------------------------------------------
# M2 · mut_6 · VAR_FLOOR = 1e-6 doubling boundary
#   Kills mutation: VAR_FLOOR = 1e-6 → VAR_FLOOR = 2e-6
# ---------------------------------------------------------------------------


class TestVarFloorBoundary:
    def test_var_above_var_floor_does_not_raise(self) -> None:
        """M2: var == 1.5e-6 > VAR_FLOOR=1e-6 → no ConvergenceFailure.

        Under mutation (VAR_FLOOR=2e-6), 1.5e-6 < 2e-6 → raises. Test goes RED.
        """
        # m=0.5, v=1.5e-6: common = 0.25/1.5e-6 - 1 ≈ 166666 → alpha_hat > 0
        alpha_hat, beta_hat = _ebmom(0.5, 1.5e-6)
        assert alpha_hat > 0.0
        assert beta_hat > 0.0

    def test_var_below_var_floor_raises(self) -> None:
        """M2: var == 0.5e-6 < VAR_FLOOR=1e-6 → ConvergenceFailure(var_below_threshold)."""
        with pytest.raises(ConvergenceFailure) as exc_info:
            _ebmom(0.5, 0.5e-6)
        assert exc_info.value.reason == "var_below_threshold"


# ---------------------------------------------------------------------------
# M3 · mut_69 · `if v < VAR_FLOOR` ↔ `v <= VAR_FLOOR` boundary
#   Kills mutation: v < VAR_FLOOR → v <= VAR_FLOOR
#   At v == VAR_FLOOR exactly, current code allows fit; mutation raises.
# ---------------------------------------------------------------------------


def test_var_exactly_at_floor_does_not_raise() -> None:
    """M3: var == VAR_FLOOR (1e-6) exactly → no ConvergenceFailure under current code.

    Under mutation (v <= VAR_FLOOR raises), this test goes RED.
    """
    # At m=0.5, v=1e-6: common = 0.25/1e-6 - 1 = 250000 - 1 = 249999 → alpha > 0
    alpha_hat, beta_hat = _ebmom(0.5, VAR_FLOOR)
    assert alpha_hat > 0.0
    assert beta_hat > 0.0


# ---------------------------------------------------------------------------
# M4 · mut_83 · `alpha_hat <= 0.0` ↔ `alpha_hat < 0.0` boundary
#   Kills mutation: alpha_hat <= 0.0 → alpha_hat < 0.0
#   alpha_hat == 0.0 exactly: current code raises; mutation does not.
# ---------------------------------------------------------------------------


def test_ebmom_alpha_hat_exactly_zero_raises_alpha_reason() -> None:
    """M4: alpha_hat==0.0 must raise ConvergenceFailure with reason 'alpha_le_zero'.

    At m=0.5, v=0.25: common=0 → alpha_hat=0.0, beta_hat=0.0.
    Current code (alpha_hat<=0.0): alpha guard fires first → reason='alpha_le_zero'.
    Mutation (alpha_hat<0.0): alpha guard skips alpha=0; beta guard fires → reason='beta_le_zero'.
    Test asserts reason=='alpha_le_zero' → goes RED under mutation.
    """
    m = 0.5
    v = 0.25  # common = 0.25/0.25 - 1 = 0 → alpha_hat = beta_hat = 0.0
    with pytest.raises(ConvergenceFailure) as exc_info:
        _ebmom(m, v)
    assert exc_info.value.reason == "alpha_le_zero", (
        f"Expected reason='alpha_le_zero' from alpha guard, got {exc_info.value.reason!r}"
    )


def test_ebmom_alpha_hat_negative_raises() -> None:
    """M4 companion: alpha_hat < 0.0 must also raise."""
    m = 0.5
    # v > 0.25 → common < 0 → alpha_hat < 0
    v = 0.25 / (1.0 + (-0.001) / m)  # engineered for alpha_hat ≈ -0.001
    with pytest.raises(ConvergenceFailure):
        _ebmom(m, v)


def test_ebmom_alpha_hat_small_positive_succeeds() -> None:
    """M4 companion: alpha_hat==0.001 > 0 must NOT raise."""
    m = 0.5
    v = _var_for_alpha_hat(0.001, m)
    alpha_hat, beta_hat = _ebmom(m, v)
    assert alpha_hat > 0.0
    assert beta_hat > 0.0


# ---------------------------------------------------------------------------
# M5 · mut_85 · RE-CLASSIFIED EQUIVALENT-IN-CURRENT-ARCHITECTURE
#   The beta_hat guard cannot be triggered independently of the alpha_hat guard
#   in `_ebmom`: MoM produces beta_hat <= 0 only when alpha_hat also fails the
#   sign check (both alpha_hat and beta_hat are proportional to the shared
#   `common` factor), and the alpha_hat guard fires first. A killer test would
#   require refactoring the guards into independent functions — deferred to
#   Phase 3.3-bis or v0.2 cleanup. No M5 test ships in this fix loop.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# M6 · mut_37 · BH-FDR `<= (rank/k)*q` ↔ `< (rank/k)*q` boundary
#   Kills mutation: <= → < loses the rejection at the exact threshold.
# ---------------------------------------------------------------------------


def test_bh_fdr_exact_threshold_included() -> None:
    """M6: p-value EXACTLY on BH threshold IS included (uses <= comparison).

    With k=1, rank=1, q=0.05: threshold = 1/1 * 0.05 = 0.05.
    p=0.05 <= 0.05 → True → passes under current code.
    Under mutation (p < 0.05): 0.05 < 0.05 → False → not included.
    """
    p_values = [0.05]
    result = _bh_fdr(p_values, q=0.05)
    assert result == frozenset({0}), (
        f"Expected frozenset({{0}}) — p=0.05 must be included at exact BH threshold. Got {result!r}"
    )


def test_bh_fdr_just_above_threshold_excluded() -> None:
    """M6 companion: p just above threshold is correctly excluded."""
    p_values = [0.05 + 1e-12]
    result = _bh_fdr(p_values, q=0.05)
    assert result == frozenset()


# ---------------------------------------------------------------------------
# M9 · mut_134 · `_bh_fdr` `if k == 0` ↔ `k == 1`
#   Kills mutation: single-element list that PASSES is returned early as empty.
# ---------------------------------------------------------------------------


def test_bh_fdr_single_passing_p_value() -> None:
    """M9: _bh_fdr([0.01], q=0.05) must return frozenset({0}).

    With k=1: threshold = 1/1 * 0.05 = 0.05. p=0.01 <= 0.05 → passes.
    Under mutation (if k == 1: return frozenset()), returns empty — RED.
    """
    result = _bh_fdr([0.01], q=0.05)
    assert result == frozenset({0}), (
        f"Single passing p-value must return frozenset({{0}}), got {result!r}"
    )


def test_bh_fdr_single_failing_p_value() -> None:
    """M9 companion: _bh_fdr([0.5], q=0.05) → frozenset() (doesn't pass threshold)."""
    result = _bh_fdr([0.5], q=0.05)
    assert result == frozenset()


# ---------------------------------------------------------------------------
# M10 · mut_57 · BH-FDR fallback fallback_reason field
#   Kills mutation: fallback_reason = exc.reason → fallback_reason = None
# ---------------------------------------------------------------------------


def _make_degenerate_clauses_k10() -> list[ClauseObservations]:
    """K=10 clauses all identical → sample_var=0 < VAR_FLOOR → BH-FDR fallback."""
    return make_clauses([(6, 10)] * 10)


def test_bh_fdr_fallback_reason_field() -> None:
    """M10: aggregation_provenance["fallback_reason"] must equal the ConvergenceFailure reason.

    Degenerate clauses (all identical) → var_between=0 → ConvergenceFailure(var_below_threshold).
    Mutation sets fallback_reason=None → assertion fails → RED.
    """
    clauses = _make_degenerate_clauses_k10()
    result = fit_skill(clauses)
    assert result.aggregation_method == "bh_fdr_fallback"
    prov = result.aggregation_provenance
    # The reason string moved with #360, and the move is correct. Ten identical
    # clauses have zero latent variance, so the admission test refuses them on
    # IDENTIFICATION grounds before the magnitude guard is ever consulted.
    # 'var_below_threshold' now names only the arithmetic-safety epsilon inside
    # _ebmom, which this input no longer reaches. The mutation this test kills
    # (fallback_reason set to None) is unaffected by which reason is expected.
    assert prov["fallback_reason"] == "latent_variance_not_identified", (
        f"Expected 'latent_variance_not_identified', got {prov['fallback_reason']!r}"
    )


# ---------------------------------------------------------------------------
# M11 · mut_58 · BH-FDR fallback `attempted` dict not None
#   Kills mutation: attempted = {...} → attempted = None
# ---------------------------------------------------------------------------


def test_bh_fdr_fallback_attempted_dict() -> None:
    """M11: aggregation_provenance["attempted"] must be a dict with the four expected keys.

    Mutation sets attempted=None → isinstance check fails → RED.

    After I1 fix: alpha_hat and beta_hat are None (not-computable) for the
    var_below_threshold path; sample_mean and sample_var remain float.
    """
    clauses = _make_degenerate_clauses_k10()
    result = fit_skill(clauses)
    assert result.aggregation_method == "bh_fdr_fallback"
    prov = result.aggregation_provenance
    attempted = prov["attempted"]
    assert isinstance(attempted, dict), f"Expected dict, got {type(attempted)!r}"
    for key in ("alpha_hat", "beta_hat", "sample_mean", "sample_var"):
        assert key in attempted, f"Key {key!r} missing from attempted dict"
    # alpha_hat/beta_hat are None for var_below_threshold (not-computable);
    # sample_mean and sample_var are always float.
    assert attempted["alpha_hat"] is None, (
        f"expected None for alpha_hat in var_below_threshold path, got {attempted['alpha_hat']!r}"
    )
    assert attempted["beta_hat"] is None, (
        f"expected None for beta_hat in var_below_threshold path, got {attempted['beta_hat']!r}"
    )
    assert isinstance(attempted["sample_mean"], float)
    assert isinstance(attempted["sample_var"], float)


# ---------------------------------------------------------------------------
# M12 · mut_8 · ClauseObservations frozen=True invariant
#   Kills mutation: @dataclass(frozen=True) → @dataclass(frozen=False)
# ---------------------------------------------------------------------------


def test_clause_observations_is_frozen() -> None:
    """M12: ClauseObservations must be a frozen dataclass.

    Under mutation (frozen=False), assignment succeeds → FrozenInstanceError not raised → RED.
    """
    obs = ClauseObservations.bernoulli(clause_id="c1", w=5.0, n=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.w = 99.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# M13 · mut_10 · ClausePosterior frozen=True invariant
# ---------------------------------------------------------------------------


def test_clause_posterior_is_frozen() -> None:
    """M13: ClausePosterior must be a frozen dataclass.

    Under mutation (frozen=False), assignment succeeds → FrozenInstanceError not raised → RED.
    """
    posterior = ClausePosterior(
        clause_id="c1",
        posterior_alpha=2.0,
        posterior_beta=3.0,
        posterior_mean=0.4,
        credible_interval_lo=0.1,
        credible_interval_hi=0.8,
        p_win_gt_threshold=0.3,
        is_shrunken=False,
        w=4.0,
        n=10,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        posterior.posterior_alpha = 99.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# M14 · mut_12 · FitResult frozen=True invariant
# ---------------------------------------------------------------------------


def test_fit_result_is_frozen() -> None:
    """M14: FitResult must be a frozen dataclass.

    Under mutation (frozen=False), assignment succeeds → FrozenInstanceError not raised → RED.
    """
    fit_result = FitResult(
        aggregation_method="unpooled",
        aggregation_provenance={"k_clauses": 1, "reason": "k_below_10"},
        posteriors=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        fit_result.aggregation_method = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# I1 · NaN-in-JSON fix — var_below_threshold path must NOT produce NaN
#   RED on current code: exc.alpha_hat/beta_hat are float("nan"), packing NaN
#   into attempted dict. GREEN after fix: None replaces NaN at the raise site.
# ---------------------------------------------------------------------------


def test_var_below_threshold_attempted_has_no_nan() -> None:
    """I1: ConvergenceFailure(var_below_threshold) must not carry NaN floats.

    10 clauses with identical (w=5, n=10) → sample_var = 0 < VAR_FLOOR → BH-FDR
    fallback via var_below_threshold. The attempted dict alpha_hat + beta_hat must
    be None (not-computable), not float('nan').

    RED on current code: alpha_hat=float('nan') / beta_hat=float('nan') → nan floats.
    GREEN after fix: alpha_hat=None / beta_hat=None.
    """
    import math

    clauses = make_clauses([(5, 10)] * 10)
    result = fit_skill(clauses)
    assert result.aggregation_method == "bh_fdr_fallback"
    prov = result.aggregation_provenance
    attempted = prov["attempted"]
    assert isinstance(attempted, dict)
    alpha_val = attempted["alpha_hat"]
    beta_val = attempted["beta_hat"]
    # After fix: None. Before fix: float("nan") → this assertion goes RED.
    assert alpha_val is None, (
        f"Expected None for alpha_hat, got {alpha_val!r} (NaN is RFC 8259 violation)"
    )
    assert beta_val is None, (
        f"Expected None for beta_hat, got {beta_val!r} (NaN is RFC 8259 violation)"
    )
    # sample_mean and sample_var are computable; must remain float (not None)
    assert isinstance(attempted["sample_mean"], float) and not math.isnan(attempted["sample_mean"])
    assert isinstance(attempted["sample_var"], float) and not math.isnan(attempted["sample_var"])
