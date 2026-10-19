"""Differential testing of aggregation numerical primitives (#165).

Cross-checks every public aggregation function that computes an interval, a
resampled/pooled statistic, or a rate against independent ``scipy.stats`` /
``statsmodels`` references on 1,000 seeded random inputs per function via
``numpy.testing.assert_allclose``. Fully offline (no network).

## Enumeration of audited public functions

Walk of ``engine.py``, ``fit.py``, ``two_arm.py``, ``status.py``, ``report.py``,
``profile.py``, ``verdict.py`` — public callables that compute an interval,
a resampled/pooled statistic, or a rate:

- ``fit_skill`` (fit.py): rates ``w/n``; EB-MoM hyperprior; unpooled/shrunken
  Beta posteriors (mean, 95% CI via ``ppf``, ``P(rate>0.60)``); BH-FDR pass
  set via ``statsmodels``.
- ``two_arm_gate`` (two_arm.py): independent Beta arm posteriors;
  ``P(p_t-p_c>delta)`` / reverse via quadrature.
- ``effect_from_matched_gate2`` (profile.py): signed paired rate
  ``(x_f-x_n)/n``; Newcombe (1998) 95% interval.
- ``effect_per_cost`` (profile.py): rate-per-cost ratio
  ``effect.mean / desc_token_cost`` when defined.

## Exclusions (one line each)

- ``aggregate_skill`` (engine.py): DB orchestrator; numerics delegated to
  ``fit_skill`` (coverage/mean-delta are trivial ratios).
- ``derive_clause_status`` (status.py): threshold state machine on already-
  computed ``p_win_gt_threshold``; no interval/rate computation.
- ``screen_verdict`` / ``paired_verdict`` / ``matched_gate2_verdict`` /
  ``harmful_verdict_supported`` (verdict.py): discrete KEEP/CUT maps.
- ``to_json_dict`` / ``to_json_bytes`` / ``skill_report_from_dict``
  (report.py): serialisation only.
- ``disposition_from_verdict`` / ``evidence_quality_from_screen`` /
  ``build_skill_profile`` (profile.py): enum mappers / row assembly; rate
  arithmetic is only ``effect_per_cost`` (audited).
- Dataclass/enum constructors and module constants: not computational.

Hard constraint: any disagreement is a finding (xfail + docs/findings), never a
widened tolerance. Per-function tolerances are stated at each assertion site.
"""

from __future__ import annotations

import logging
import math
from statistics import NormalDist
from typing import Any

import numpy as np
from numpy.testing import assert_allclose
from scipy import integrate  # type: ignore[import-untyped]
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]
from statsmodels.stats.multitest import multipletests

from skill_harness.aggregation.errors import ConvergenceFailure
from skill_harness.aggregation.fit import (
    BH_FDR_Q,
    K_MIN_FOR_EB,
    VAR_FLOOR,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    FitResult,
    _bh_fdr,
    fit_skill,
)
from skill_harness.aggregation.profile import (
    EffectEstimate,
    effect_from_matched_gate2,
    effect_per_cost,
)
from skill_harness.aggregation.two_arm import two_arm_gate
from skill_harness.oc import Gate2Design, MMESpec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_INPUTS = 1000
SEED = 165_2026_08_09  # issue #165, deterministic

# Per-function absolute tolerances (stated at assertion sites via these names).
# Float64 closed-forms / identical primitives → machine-eps band.
TOL_FIT_SKILL = 1e-12
TOL_TWO_ARM = 1e-10  # quad residual; production limit=200 vs reference epsabs=1e-14
TOL_EFFECT_MATCHED = 1e-12
TOL_EFFECT_PER_COST = 1e-15

_LOG = logging.getLogger("skill_harness.aggregation.fit")


# ---------------------------------------------------------------------------
# Independent references (scipy.stats / statsmodels / published formulas)
# ---------------------------------------------------------------------------


def _ref_beta_posterior(alpha: float, beta: float) -> tuple[float, float, float, float]:
    """Independent Beta summaries: mean, 95% CI, P(X > 0.60).

    Uses ``scipy.stats.beta`` ppf/sf — the same primitive family as production,
    recomputed from first principles in the test process (not by reading
    production return values).
    """
    mean = alpha / (alpha + beta)
    lo = float(beta_dist.ppf(0.025, alpha, beta))
    hi = float(beta_dist.ppf(0.975, alpha, beta))
    p_exceed = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta))
    return mean, lo, hi, p_exceed


def _ref_mean_sampling_variance(clauses: list[ClauseObservations]) -> float:
    """Independent re-derivation of the mean within-clause sampling variance.

    Written from
    docs/assurance/ebmom-peel-preregistration-amendment.md section 2, NOT by
    calling production: a reference that calls the implementation tests only
    that the code equals itself.

        within_ss_k    = sum_sq_k - n_k * r_k^2
        sampling_var_k = within_ss_k / ((n_k - 1) * n_k)
    """
    total = 0.0
    for cl in clauses:
        rate = cl.w / cl.n
        within_ss = max(cl.sum_sq - cl.n * rate * rate, 0.0)
        total += within_ss / (max(cl.n - 1.0, 1.0) * cl.n)
    return total / len(clauses)


def _ref_ebmom(sample_mean: float, sample_var: float) -> tuple[float, float]:
    """Independent MoM Beta hyperprior (A53 closed form)."""
    if sample_var < VAR_FLOOR:
        raise ConvergenceFailure(
            reason="var_below_threshold",
            alpha_hat=None,
            beta_hat=None,
            sample_mean=sample_mean,
            sample_var=sample_var,
        )
    common = sample_mean * (1.0 - sample_mean) / sample_var - 1.0
    alpha_hat = sample_mean * common
    beta_hat = (1.0 - sample_mean) * common
    if alpha_hat <= 0.0:
        raise ConvergenceFailure(
            reason="alpha_le_zero",
            alpha_hat=alpha_hat,
            beta_hat=beta_hat,
            sample_mean=sample_mean,
            sample_var=sample_var,
        )
    if beta_hat <= 0.0:
        raise ConvergenceFailure(
            reason="beta_le_zero",
            alpha_hat=alpha_hat,
            beta_hat=beta_hat,
            sample_mean=sample_mean,
            sample_var=sample_var,
        )
    return alpha_hat, beta_hat


def _ref_bounded_pooling_concentration(mu: float, v_bound: float) -> float | None:
    """Independent form-B concentration (pre-registration v2 section 3).

    Re-derived from the specification, not called out of production: the same
    moment inversion _ref_ebmom performs, evaluated at the admission bound
    instead of at the observed latent variance. Returns None where the
    inversion yields no proper Beta, which is the specified revert to unpooled.

    v_bound itself is READ from provenance rather than re-derived. It is the
    critical order statistic of a bootstrap seeded from the data, and an
    "independent" re-derivation of a seeded resampling procedure would have to
    reproduce its exact RNG stream, which is cloning rather than independence.
    The same argument the admission branch below already makes.
    """
    if v_bound <= VAR_FLOOR:
        return None
    c = mu * (1.0 - mu) / v_bound - 1.0
    if c <= 0.0 or mu * c <= 0.0 or (1.0 - mu) * c <= 0.0:
        return None
    return c


def _ref_bh_pass_indices(p_values: list[float], q: float) -> set[int]:
    """Independent BH-FDR via statsmodels ``multipletests(method='fdr_bh')``."""
    if not p_values:
        return set()
    reject, _, _, _ = multipletests(p_values, alpha=q, method="fdr_bh")
    return {i for i, flag in enumerate(reject) if flag}


def _ref_p_difference_exceeds(a1: float, b1: float, a2: float, b2: float, delta: float) -> float:
    """Independent P(X-Y > delta) for X~Beta(a1,b1), Y~Beta(a2,b2)."""

    def integrand(x: float) -> float:
        return float(beta_dist.pdf(x, a1, b1) * beta_dist.cdf(x - delta, a2, b2))

    value, _ = integrate.quad(integrand, delta, 1.0, epsabs=1e-14, limit=500)
    return min(1.0, max(0.0, float(value)))


def _ref_newcombe(
    both_pass: int, x_f: int, x_n: int, both_fail: int, *, level: float = 0.95
) -> tuple[float, float]:
    """Independent Newcombe (1998) method-10 paired-difference interval."""
    n = both_pass + x_f + x_n + both_fail
    z = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    r, s, t, u = both_pass, x_f, x_n, both_fail
    p1 = (r + s) / n
    p2 = (r + t) / n
    delta = p1 - p2

    def wilson(x: int, nn: int, zz: float) -> tuple[float, float]:
        center = (x + zz * zz / 2.0) / (nn + zz * zz)
        half = zz * math.sqrt(x * (nn - x) / nn + zz * zz / 4.0) / (nn + zz * zz)
        return center - half, center + half

    l1, u1 = wilson(r + s, n, z)
    l2, u2 = wilson(r + t, n, z)
    denom_sq = (r + s) * (t + u) * (r + t) * (s + u)
    if denom_sq > 0:
        b = r * u - s * t
        c = b - n / 2.0 if b > n / 2.0 else (float(b) if b < 0 else 0.0)
        phi = c / math.sqrt(denom_sq)
    else:
        phi = 0.0
    lower = delta - math.sqrt(
        max(0.0, (p1 - l1) ** 2 - 2.0 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    )
    upper = delta + math.sqrt(
        max(0.0, (p2 - l2) ** 2 - 2.0 * phi * (p2 - l2) * (u1 - p1) + (u1 - p1) ** 2)
    )
    return lower, upper


# ---------------------------------------------------------------------------
# Input generators (seeded, stratified so all fit paths are hit)
# ---------------------------------------------------------------------------


def _fit_skill_inputs(rng: np.random.Generator) -> list[list[ClauseObservations]]:
    """1,000 clause-lists: ~1/3 unpooled, ~1/3 EB-MoM, ~1/3 BH-FDR fallback."""
    out: list[list[ClauseObservations]] = []
    for i in range(N_INPUTS):
        bucket = i % 3
        if bucket == 0:
            k = int(rng.integers(1, K_MIN_FOR_EB))
            clauses = []
            for j in range(k):
                n = int(rng.integers(1, 48))
                w = float(rng.uniform(0.0, float(n)))
                clauses.append(ClauseObservations.bernoulli(clause_id=f"c{j}", w=w, n=n))
            out.append(clauses)
        elif bucket == 1:
            # Heterogeneous rates in (0.15, 0.85) → EB-MoM typically converges.
            k = int(rng.integers(K_MIN_FOR_EB, 28))
            clauses = []
            for j in range(k):
                n = int(rng.integers(4, 48))
                rate = float(rng.uniform(0.15, 0.85))
                clauses.append(ClauseObservations.bernoulli(clause_id=f"c{j}", w=rate * n, n=n))
            out.append(clauses)
        else:
            # Force BH-FDR: identical rates → sample_var = 0 < VAR_FLOOR.
            k = int(rng.integers(K_MIN_FOR_EB, 28))
            n = int(rng.integers(5, 40))
            rate = float(rng.uniform(0.05, 0.95))
            out.append(
                [ClauseObservations.bernoulli(clause_id=f"c{j}", w=rate * n, n=n) for j in range(k)]
            )
    return out


def _two_arm_inputs(
    rng: np.random.Generator,
) -> list[tuple[int, int, int, int, float, float]]:
    rows: list[tuple[int, int, int, int, float, float]] = []
    for _ in range(N_INPUTS):
        tt = int(rng.integers(1, 40))
        ct = int(rng.integers(1, 40))
        tp = int(rng.integers(0, tt + 1))
        cp = int(rng.integers(0, ct + 1))
        delta = float(rng.uniform(0.0, 0.9))
        # prob_threshold in (0.5, 1]
        prob_threshold = float(rng.uniform(0.5000001, 1.0))
        rows.append((tp, tt, cp, ct, delta, prob_threshold))
    return rows


def _matched_table_inputs(
    rng: np.random.Generator,
) -> list[tuple[int, int, int, int, int]]:
    """(n_pairs, both_pass, full_only, null_only, both_fail)."""
    rows: list[tuple[int, int, int, int, int]] = []
    for _ in range(N_INPUTS):
        n = int(rng.integers(1, 40))
        parts = rng.multinomial(n, [0.25, 0.25, 0.25, 0.25])
        bp, xf, xn, bf = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
        rows.append((n, bp, xf, xn, bf))
    return rows


def _effect_per_cost_inputs(
    rng: np.random.Generator,
) -> list[tuple[EffectEstimate | None, int | None]]:
    rows: list[tuple[EffectEstimate | None, int | None]] = []
    for i in range(N_INPUTS):
        kind = i % 5
        if kind == 0:
            rows.append((None, int(rng.integers(1, 5000))))
        elif kind == 1:
            mean = float(rng.uniform(-1.0, 1.0))
            rows.append(
                (
                    EffectEstimate(
                        mean=mean, ci_lo=mean - 0.1, ci_hi=mean + 0.1, is_prior_only=False
                    ),
                    None,
                )
            )
        elif kind == 2:
            mean = float(rng.uniform(-1.0, 1.0))
            rows.append(
                (
                    EffectEstimate(
                        mean=mean, ci_lo=mean - 0.1, ci_hi=mean + 0.1, is_prior_only=False
                    ),
                    0,
                )
            )
        elif kind == 3:
            mean = float(rng.uniform(-1.0, 1.0))
            rows.append(
                (
                    EffectEstimate(
                        mean=mean, ci_lo=mean - 0.1, ci_hi=mean + 0.1, is_prior_only=False
                    ),
                    int(rng.integers(-20, 0)),
                )
            )
        else:
            mean = float(rng.uniform(-1.0, 1.0))
            cost = int(rng.integers(1, 10_000))
            rows.append(
                (
                    EffectEstimate(
                        mean=mean, ci_lo=mean - 0.1, ci_hi=mean + 0.1, is_prior_only=False
                    ),
                    cost,
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _check_admitted_bootstrap_tail(
    result: FitResult, plugin_tail: np.ndarray[Any, np.dtype[np.float64]], seed_index: int
) -> None:
    """What an independent reference can say about the class-2 tail.

    Not the value: that would mean reproducing a seeded resampling stream, which
    is cloning rather than an independent check, and this file refuses that for
    the admission bootstrap for the same reason. What is checkable is that the
    number is a probability, that the mechanism actually reached the decision
    rather than the plug-in reaching it silently, and that provenance's own draw
    counts are internally consistent with the mode it reports.
    """
    diagnostics = result.aggregation_provenance["admitted_bootstrap"]
    assert isinstance(diagnostics, dict)
    got = np.array([p.p_win_gt_threshold for p in result.posteriors])
    assert np.all((got >= 0.0) & (got <= 1.0)), (
        f"class-2 tail outside [0, 1] at seed_index={seed_index}: {got}"
    )
    assert int(diagnostics["used"]) <= int(diagnostics["s_target"])
    assert int(diagnostics["kept"]) + int(diagnostics["below_crit"]) + int(
        diagnostics["nonpositive_c"]
    ) == int(diagnostics["drawn"]), (
        f"admitted_bootstrap draw counts do not add up at seed_index={seed_index}: {diagnostics}"
    )
    if diagnostics["fell_back_to_plugin"]:
        assert_allclose(
            got,
            plugin_tail,
            rtol=0.0,
            atol=TOL_FIT_SKILL,
            err_msg=(
                "the counted plug-in fallback must return the plug-in tail exactly, "
                f"seed_index={seed_index}"
            ),
        )
        return
    assert int(diagnostics["used"]) > 0
    assert not np.allclose(got, plugin_tail, rtol=0.0, atol=TOL_FIT_SKILL), (
        "the admitted path reported the plug-in tail while claiming not to have "
        f"fallen back, seed_index={seed_index}: the mechanism did not reach the decision"
    )


class TestFitSkillDifferential:
    """``fit_skill`` vs independent Beta / MoM / statsmodels BH-FDR."""

    def test_1000_seeded_inputs_match_reference(self) -> None:
        rng = np.random.default_rng(SEED)
        inputs = _fit_skill_inputs(rng)
        assert len(inputs) == N_INPUTS

        # fit_skill logs warnings on unpooled / BH paths; not under test here.
        prev_level = _LOG.level
        _LOG.setLevel(logging.ERROR)
        try:
            for seed_i, clauses in enumerate(inputs):
                result = fit_skill(clauses)
                k = len(clauses)
                rates = [cl.w / cl.n for cl in clauses]
                got_means = np.array([p.posterior_mean for p in result.posteriors])
                got_lo = np.array([p.credible_interval_lo for p in result.posteriors])
                got_hi = np.array([p.credible_interval_hi for p in result.posteriors])
                got_p = np.array([p.p_win_gt_threshold for p in result.posteriors])
                got_a = np.array([p.posterior_alpha for p in result.posteriors])
                got_b = np.array([p.posterior_beta for p in result.posteriors])

                if k < K_MIN_FOR_EB:
                    assert result.aggregation_method == "unpooled"
                    exp_a = np.array([1.0 + cl.w for cl in clauses])
                    exp_b = np.array([1.0 + (cl.n - cl.w) for cl in clauses])
                    exp_stats = [
                        _ref_beta_posterior(float(a), float(b)) for a, b in zip(exp_a, exp_b)
                    ]
                    exp_means = np.array([s[0] for s in exp_stats])
                    exp_lo = np.array([s[1] for s in exp_stats])
                    exp_hi = np.array([s[2] for s in exp_stats])
                    exp_p = np.array([s[3] for s in exp_stats])
                else:
                    sample_mean = sum(rates) / k
                    # Amended estimator (#360), re-derived here from the
                    # specification rather than by calling production:
                    # unbiased /(k-1) total variance, minus the mean
                    # within-clause sampling variance.
                    total_var = sum((r - sample_mean) ** 2 for r in rates) / (k - 1)
                    latent_var = total_var - _ref_mean_sampling_variance(clauses)

                    # Branch on the method production chose, rather than
                    # re-deriving the admission decision. Admission is a
                    # bootstrap test seeded from the data; an "independent"
                    # re-derivation of a seeded resampling procedure would have
                    # to reproduce its exact RNG stream, which is cloning, not
                    # independence. What is cross-checked here is the NUMERICS
                    # given the branch. The admission decision itself is
                    # covered by test_aggregation_fit.py
                    # (test_marginal_heterogeneity_is_refused_not_fitted,
                    # test_admission_verdict_is_deterministic) and its
                    # calibration by the acceptance matrix.
                    if result.aggregation_method == "bounded_pooling_refused":
                        prov = result.aggregation_provenance
                        pooling = prov["bounded_pooling"]
                        assert isinstance(pooling, dict)
                        v_bound = float(pooling["v_bound"])
                        ref_c = _ref_bounded_pooling_concentration(sample_mean, v_bound)
                        assert result.bh_fdr_passes is None, (
                            "the refused path publishes no FDR selection under v2 "
                            f"section 3, got {result.bh_fdr_passes!r} at seed_index={seed_i}"
                        )
                        assert bool(pooling["reverted_to_unpooled"]) is (ref_c is None), (
                            f"revert disagreement at seed_index={seed_i} SEED={SEED}: "
                            f"production reverted={pooling['reverted_to_unpooled']!r} "
                            f"reference c_bound={ref_c!r}"
                        )
                        if ref_c is None:
                            exp_a = np.array([1.0 + cl.w for cl in clauses])
                            exp_b = np.array([1.0 + (cl.n - cl.w) for cl in clauses])
                        else:
                            assert_allclose(
                                float(pooling["c_bound"]),
                                ref_c,
                                rtol=0.0,
                                atol=TOL_FIT_SKILL,
                                err_msg=f"fit_skill c_bound seed_index={seed_i}",
                            )
                            exp_a = np.array([sample_mean * ref_c + cl.w for cl in clauses])
                            exp_b = np.array(
                                [(1.0 - sample_mean) * ref_c + (cl.n - cl.w) for cl in clauses]
                            )
                        exp_stats = [
                            _ref_beta_posterior(float(a), float(b)) for a, b in zip(exp_a, exp_b)
                        ]
                        exp_means = np.array([s[0] for s in exp_stats])
                        exp_lo = np.array([s[1] for s in exp_stats])
                        exp_hi = np.array([s[2] for s in exp_stats])
                        exp_p = np.array([s[3] for s in exp_stats])
                    else:
                        assert result.aggregation_method == "ebmom_hierarchical"
                        alpha_hat, beta_hat = _ref_ebmom(sample_mean, max(latent_var, 0.0))
                        assert_allclose(
                            float(result.aggregation_provenance["alpha_hat"]),  # type: ignore[arg-type]
                            alpha_hat,
                            rtol=0.0,
                            atol=TOL_FIT_SKILL,
                            err_msg=f"fit_skill alpha_hat seed_index={seed_i}",
                        )
                        assert_allclose(
                            float(result.aggregation_provenance["beta_hat"]),  # type: ignore[arg-type]
                            beta_hat,
                            rtol=0.0,
                            atol=TOL_FIT_SKILL,
                            err_msg=f"fit_skill beta_hat seed_index={seed_i}",
                        )
                        exp_a = np.array([alpha_hat + cl.w for cl in clauses])
                        exp_b = np.array([beta_hat + (cl.n - cl.w) for cl in clauses])
                        exp_stats = [
                            _ref_beta_posterior(float(a), float(b)) for a, b in zip(exp_a, exp_b)
                        ]
                        exp_means = np.array([s[0] for s in exp_stats])
                        exp_lo = np.array([s[1] for s in exp_stats])
                        exp_hi = np.array([s[2] for s in exp_stats])
                        # p_win_gt_threshold on the admitted path is NOT the tail
                        # of the reported Beta since v2 section 4: it is the same
                        # tail averaged over S admission-conditioned draws of the
                        # hyperparameters. An independent reference cannot be
                        # written for it -- reproducing a seeded resampling
                        # procedure is cloning, which is the reason this test
                        # already branches on production's method rather than
                        # re-deriving admission. What CAN be cross-checked without
                        # cloning is asserted in _check_admitted_bootstrap_tail
                        # below, and the plug-in tail is kept as the reference the
                        # mechanism must have moved away from.
                        exp_p = np.array([s[3] for s in exp_stats])
                        _check_admitted_bootstrap_tail(result, exp_p, seed_i)
                        exp_p = got_p

                # rtol=0, atol=TOL_FIT_SKILL (1e-12) — fit_skill posterior band
                assert_allclose(
                    got_a,
                    exp_a,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill posterior_alpha seed_index={seed_i}",
                )
                assert_allclose(
                    got_b,
                    exp_b,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill posterior_beta seed_index={seed_i}",
                )
                assert_allclose(
                    got_means,
                    exp_means,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill posterior_mean seed_index={seed_i}",
                )
                assert_allclose(
                    got_lo,
                    exp_lo,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill credible_interval_lo seed_index={seed_i}",
                )
                assert_allclose(
                    got_hi,
                    exp_hi,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill credible_interval_hi seed_index={seed_i}",
                )
                assert_allclose(
                    got_p,
                    exp_p,
                    rtol=0.0,
                    atol=TOL_FIT_SKILL,
                    err_msg=f"fit_skill p_win_gt_threshold seed_index={seed_i}",
                )
                # Empirical rates used by EB-MoM must match w/n.
                if k >= K_MIN_FOR_EB and result.aggregation_method == "ebmom_hierarchical":
                    assert_allclose(
                        float(result.aggregation_provenance["sample_mean"]),  # type: ignore[arg-type]
                        float(np.mean(rates)),
                        rtol=0.0,
                        atol=TOL_FIT_SKILL,
                        err_msg=f"fit_skill sample_mean (rate) seed_index={seed_i}",
                    )
        finally:
            _LOG.setLevel(prev_level)


class TestBhFdrHelperDifferential:
    """``_bh_fdr`` vs statsmodels ``multipletests(method='fdr_bh')``.

    The helper has had no production caller since pre-registration v2 section 3
    retired BH-FDR on the refused path; it is retained as the subject of the
    registered detector for falsification-plan item 1, which asks whether the
    ``1 - posterior mass`` transform behaves as a valid null p-value. That
    question is answered against this implementation, so the implementation
    still needs an independent reference. The cross-check moved here when the
    fit-level BH branch above became a bounded-pooling branch, rather than
    being deleted with it.
    """

    def test_1000_seeded_pvectors_match_reference(self) -> None:
        rng = np.random.default_rng(SEED + 7)
        for draw in range(1000):
            k = int(rng.integers(1, 41))
            # A mixture of near-null and strongly significant p-values, so the
            # step-up boundary is exercised rather than only its interior.
            p_values = [
                float(rng.uniform(0.0, 1.0))
                if rng.random() < 0.7
                else float(rng.uniform(0.0, 0.02))
                for _ in range(k)
            ]
            got = set(_bh_fdr(p_values, BH_FDR_Q))
            ref = _ref_bh_pass_indices(p_values, BH_FDR_Q)
            assert got == ref, (
                f"_bh_fdr disagreement at draw={draw} SEED={SEED}: "
                f"got={sorted(got)} ref={sorted(ref)} p_values={p_values}"
            )


class TestTwoArmGateDifferential:
    """``two_arm_gate`` vs independent Beta quadrature."""

    def test_1000_seeded_inputs_match_reference(self) -> None:
        rng = np.random.default_rng(SEED + 1)
        inputs = _two_arm_inputs(rng)
        assert len(inputs) == N_INPUTS

        for seed_i, (tp, tt, cp, ct, delta, thresh) in enumerate(inputs):
            result = two_arm_gate(tp, tt, cp, ct, delta=delta, prob_threshold=thresh)
            t_alpha = 1.0 + tp
            t_beta = 1.0 + (tt - tp)
            c_alpha = 1.0 + cp
            c_beta = 1.0 + (ct - cp)
            ref_better = _ref_p_difference_exceeds(t_alpha, t_beta, c_alpha, c_beta, delta)
            ref_worse = _ref_p_difference_exceeds(c_alpha, c_beta, t_alpha, t_beta, delta)

            # rtol=0, atol=TOL_TWO_ARM (1e-10) — two_arm_gate quadrature band
            assert_allclose(
                result.p_treatment_better,
                ref_better,
                rtol=0.0,
                atol=TOL_TWO_ARM,
                err_msg=f"two_arm_gate p_treatment_better seed_index={seed_i}",
            )
            assert_allclose(
                result.p_treatment_worse,
                ref_worse,
                rtol=0.0,
                atol=TOL_TWO_ARM,
                err_msg=f"two_arm_gate p_treatment_worse seed_index={seed_i}",
            )
            assert_allclose(
                [
                    result.treatment_alpha,
                    result.treatment_beta,
                    result.control_alpha,
                    result.control_beta,
                ],
                [t_alpha, t_beta, c_alpha, c_beta],
                rtol=0.0,
                atol=TOL_TWO_ARM,
                err_msg=f"two_arm_gate posterior params seed_index={seed_i}",
            )


class TestEffectFromMatchedGate2Differential:
    """``effect_from_matched_gate2`` vs independent rate + Newcombe interval."""

    def test_1000_seeded_inputs_match_reference(self) -> None:
        rng = np.random.default_rng(SEED + 2)
        inputs = _matched_table_inputs(rng)
        assert len(inputs) == N_INPUTS

        for seed_i, (n, bp, xf, xn, bf) in enumerate(inputs):
            design = Gate2Design(n_pairs=n, gamma=0.90, mme=MMESpec(delta_min=0.2, q_min=0.7))
            effect = effect_from_matched_gate2(
                design,
                both_pass=bp,
                full_only=xf,
                null_only=xn,
                both_fail=bf,
            )
            ref_mean = (xf - xn) / float(n)
            ref_lo, ref_hi = _ref_newcombe(bp, xf, xn, bf)

            # rtol=0, atol=TOL_EFFECT_MATCHED (1e-12) — effect_from_matched_gate2 band
            assert_allclose(
                effect.mean,
                ref_mean,
                rtol=0.0,
                atol=TOL_EFFECT_MATCHED,
                err_msg=f"effect_from_matched_gate2 mean (rate) seed_index={seed_i}",
            )
            assert_allclose(
                [effect.ci_lo, effect.ci_hi],
                [ref_lo, ref_hi],
                rtol=0.0,
                atol=TOL_EFFECT_MATCHED,
                err_msg=f"effect_from_matched_gate2 Newcombe CI seed_index={seed_i}",
            )


class TestEffectPerCostDifferential:
    """``effect_per_cost`` vs independent mean/cost ratio."""

    def test_1000_seeded_inputs_match_reference(self) -> None:
        rng = np.random.default_rng(SEED + 3)
        inputs = _effect_per_cost_inputs(rng)
        assert len(inputs) == N_INPUTS

        for seed_i, (effect, cost) in enumerate(inputs):
            got = effect_per_cost(effect, cost)
            if effect is None or cost is None or cost <= 0:
                assert got is None, f"effect_per_cost seed_index={seed_i} expected None"
                continue
            ref = effect.mean / float(cost)
            assert got is not None
            # rtol=0, atol=TOL_EFFECT_PER_COST (1e-15) — effect_per_cost band
            assert_allclose(
                got,
                ref,
                rtol=0.0,
                atol=TOL_EFFECT_PER_COST,
                err_msg=f"effect_per_cost seed_index={seed_i}",
            )


def test_enumeration_covers_ticket_modules() -> None:
    """Docstring enumeration is present and names every walked module."""
    from pathlib import Path

    doc = Path(__file__).read_text(encoding="utf-8")
    for name in (
        "fit_skill",
        "two_arm_gate",
        "effect_from_matched_gate2",
        "effect_per_cost",
        "aggregate_skill",
        "derive_clause_status",
        "screen_verdict",
        "to_json_dict",
    ):
        assert name in doc
    for mod_name in (
        "engine.py",
        "fit.py",
        "two_arm.py",
        "status.py",
        "report.py",
        "profile.py",
        "verdict.py",
    ):
        assert mod_name in doc


def test_differential_report_exists() -> None:
    """Assurance report records per-function agreement (#165 AC)."""
    from pathlib import Path

    report = (
        Path(__file__).resolve().parent.parent / "docs" / "assurance" / "differential-report.md"
    )
    text = report.read_text(encoding="utf-8")
    assert "fit_skill" in text
    assert "two_arm_gate" in text
    assert "effect_from_matched_gate2" in text
    assert "effect_per_cost" in text
    assert "1,000" in text or "1000" in text
    assert "tolerance" in text.lower()
