"""Empirical-Bayes Method-of-Moments hierarchical fit + bounded-pooling refusal (A53).

Two-level model:
  Level 1 (per-clause): posterior Beta(1 + w_k, 1 + n_k - w_k) where w_k is
           the win-weight sum (Win=1, Tie=0.5, Loss=0).
  Level 2 (hyperprior): Beta(alpha_hat_skill, beta_hat_skill) fit via MoM over
           per-clause empirical rates (w_k / n_k).

Shrunken posterior per clause: Beta(alpha_hat + w_k, beta_hat + n_k - w_k).

Pass rule (LOCKED — see docs/INVARIANTS.md #1): clause PASSES when
  P(rate > 0.60) >= 0.95 on the shrunken posterior.

K < 10: EB hyperprior estimate is noisy (BDA3 §5) — fall back to UNPOOLED.
The hyperprior is fit to the LATENT variance: the across-clause variance of
observed rates carries within-clause sampling noise as well as true
heterogeneity, and the noise is peeled off before the moment map is inverted.
Without the peel the recovered concentration deflates by roughly n/(n+c+1).

ADMITTED PATH, mechanism class 2 (pre-registration v2 section 4, FROZEN
  2026-09-05): the probability the pass rule is applied to is NOT the plug-in
  sf(0.60) of that posterior. It is the same tail probability averaged over
  S = 200 draws of the hyperparameters from the finite-sample distribution the
  fitted model implies, conditioned on the event that admitted the fit:

      theta_j ~ Beta(alpha_hat, beta_hat), K of them
      one synthetic world under them, preserving each clause's n_k and the
        pooled tie fraction
      (mu_s, latent_s) = the moments fit_skill computes on that world
      keep the draw when latent_s > heterogeneity_test.critical_order_statistic
      c_s = mu_s (1 - mu_s) / latent_s - 1, non-positive dropped and counted
      P_k = mean_s P(theta > 0.60 | Beta(mu_s c_s + w_k,
                                         (1 - mu_s) c_s + n_k - w_k))

  The plug-in spends the uncertainty in (alpha_hat, beta_hat) as if it were
  zero. v2 section 0.5 reads the cost off four worlds where the fitted
  concentration lands at half the truth or less and a clause with 4 to 6 wins
  of 25 against a true mean above 0.60 is under-shrunk into a FAIL whose tail
  sits a hair under 0.05. Draw-budget exhaustion and the plug-in fallback are
  typed and counted in provenance under `admitted_bootstrap`; nothing about a
  short or empty average is silent.

Admission: a hierarchical fit is attempted only when the peeled latent variance
  is distinguishable from zero by a one-sided bootstrap test (see
  HETEROGENEITY_TEST_ALPHA). Otherwise it is refused as
  latent_variance_not_identified.

REFUSAL, form B (pre-registration v2 section 3, FROZEN 2026-09-05):
  A refused fit still pools. It does not fall back to the unpooled per-clause
  posterior under BH-FDR: that fallback broke its own FAIL promise wherever it
  fired, 251 of 251 false decisions in the registered tie_heavy_null regime at
  R = 1000. The concentration is instead bounded by the admission test's own
  critical order statistic, which provenance already carries:

      v_bound = heterogeneity_test.critical_order_statistic
      c_bound = mu (1 - mu) / v_bound - 1
      posterior_k = Beta(mu c_bound + w_k, (1 - mu) c_bound + n_k - w_k)

  and every clause is decided by the same locked rule the admitted path uses.
  A non-positive c_bound reverts to the unpooled Beta(1 + w, 1 + n - w); the
  revert is typed and counted in provenance. Because v_bound is the boundary
  the admission test measured the observed statistic against, the estimator is
  continuous across that boundary: a fit admitted at the boundary and a fit
  refused at the boundary shrink identically.

  BH-FDR is RETIRED on this path by the same section, as a design choice. It
  was a multiplicity brake on unpooled posteriors; on a pooled posterior it is
  a different multiplicity story bolted onto one path. What bounds correlated
  false PASSes now is the per-path false-PASS kill of v2 section 2.

Convergence failure (alpha_hat <= 0 or beta_hat <= 0, or the admission test
  refuses): the bounded-pooling refusal above.

Determinism: the admission bootstrap AND the admitted path's
admission-conditioned bootstrap are each seeded from a digest of the
observations themselves, under distinct labels so the two streams differ, so
identical input yields an identical verdict on every host and every run.
PYTHONHASHSEED=0 already pinned by caller environment.

scipy.stats.beta.sf is the probability evaluation primitive (mirror of
ablation/stopping.py pattern).
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.aggregation.errors import ConvergenceFailure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locked constants (pass rule — see docs/INVARIANTS.md #1)
# ---------------------------------------------------------------------------

WIN_RATE_THRESHOLD: float = 0.60

# BDA3 §5 — K floor for EB hyperprior reliability.
K_MIN_FOR_EB: int = 10

# Arithmetic-safety epsilon ONLY. This is NOT the admission rule: it guards the
# division in the moment inversion against a latent variance of exactly zero.
# Admission is decided by the heterogeneity test below, never by this magnitude.
VAR_FLOOR: float = 1e-6

# Level of the one-sided heterogeneity test that admits a hierarchical fit.
# Ruled by the maintainer 2026-08-31 against its power cost, NOT inherited from
# BH_FDR_Q: that controls false discoveries among clause verdicts, this controls
# whether a hyperprior is fitted at all. See
# docs/assurance/ebmom-peel-preregistration-amendment.md section 3.
HETEROGENEITY_TEST_ALPHA: float = 0.05

# Bootstrap replicates for the admission test. A bootstrap rather than a normal
# quantile because the null sits on the boundary of the parameter space, where
# the sampling distribution of a variance component is skewed and partly atomic
# at zero, which is exactly the regime the test operates in.
HETEROGENEITY_BOOTSTRAP_B: int = 999

# BH-FDR significance level (A9).
#
# RETIRED FROM THE DECISION PATH, pre-registration v2 section 3 (FROZEN
# 2026-09-05). `fit_skill` no longer calls `_bh_fdr`: a refused fit pools under
# form B and every clause is decided by the locked rule. The constant and the
# `_bh_fdr` helper are retained ONLY as the subject of the registered detector
# for falsification-plan item 1, which measures the calibration of the
# `1 - posterior mass` transform. Neither has a production caller. Do not add
# one without superseding v2 section 3.
BH_FDR_Q: float = 0.05

# Bounded-pooling form. "B" is the form the pre-committed selection rule landed
# on under both tests (v2 section 3): v_bound is the admission test's critical
# order statistic, which makes the estimator continuous across the admission
# boundary. Recorded in provenance so a receipt names the form it ran.
BOUNDED_POOLING_FORM: str = "B"

# ---------------------------------------------------------------------------
# Mechanism class 2 on the ADMITTED path: the admission-conditioned parametric
# bootstrap (pre-registration v2 section 4, FROZEN 2026-09-05).
#
# An admitted fit no longer decides each clause on the plug-in posterior
# Beta(alpha_hat + w_k, beta_hat + n_k - w_k). The plug-in treats the fitted
# hyperprior as if it were known, and v2 section 0.5 reads the cost off four
# worlds: the latent variance overshoots by 1.5 to 2.3 times, the fitted
# concentration lands at half the truth or less, and a clause that drew 4 to 6
# wins of 25 against a true mean above 0.60 is under-shrunk into a FAIL whose
# tail sits a hair under 0.05. The decision quantity becomes the clause tail
# probability averaged over draws of the hyperparameters from the finite-sample
# distribution the fitted model itself implies, CONDITIONED on the event that
# admitted the fit.
#
# The draws are conditioned rather than merely truncated because admission is
# what selected this fit: the sampling distribution of (mu, latent) given
# admission is the one the decision is exposed to, and it is not the
# unconditional one. Class 1 (`proto_hu.py`) approximated it with a truncated
# normal and left two of the four worlds failing; class 2 replaces the
# approximation with the model's own draws.
#
# What this does NOT do, stated because it bounds what a pass here means: the
# draws are centred at the fitted values, so the mechanism captures the SHAPE of
# the sampling distribution and corrects no winner's-curse bias in the point
# estimate.
ADMITTED_BOOTSTRAP_DRAWS: int = 200

# Candidate draws per block, and the ceiling on blocks. Admission conditioning
# can reject most of a block, so the budget is bounded rather than a while-loop:
# a fit whose admission event is severe must terminate and SAY it terminated
# early, which is what the `exhausted` and `fell_back_to_plugin` counters in
# provenance are for.
ADMITTED_BOOTSTRAP_BLOCK: int = 400
ADMITTED_BOOTSTRAP_MAX_BLOCKS: int = 40

# The label that separates this stream from the admission bootstrap's. Both
# derive from the same canonical clause encoding under the frozen v1 section 3
# procedure; without a distinct label the two would share a seed and the
# mechanism would resample the stream the admission test already consumed.
ADMITTED_BOOTSTRAP_LABEL: str = "pb"


# ---------------------------------------------------------------------------
# Per-clause input/output shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClauseObservations:
    """Aggregated observations for one clause.

    w      = sum of observations (Win=1, Tie=0.5, Loss=0).
    n      = total observation count (integer).
    sum_sq = sum of SQUARED observations.

    sum_sq is the sufficient statistic that identifies within-clause variance.
    (w, n) alone does not: (w=1, n=2) is produced both by one win and one loss,
    whose within-clause sum of squares is 0.5, and by two ties, whose sum of
    squares is 0.0. A peel computed from (w, n) guesses on tie-carrying data
    and over-peels tie-heavy clauses. See
    docs/assurance/ebmom-peel-preregistration-amendment.md section 4.

    For tie-free observations sum_sq == w, because 0^2 = 0 and 1^2 = 1.
    """

    clause_id: str
    w: float
    n: int
    sum_sq: float

    @classmethod
    def bernoulli(cls, clause_id: str, w: float, n: int) -> ClauseObservations:
        """Build from tie-free observations, where sum_sq == w.

        Squaring leaves 0 and 1 unchanged, so a clause with no ties has
        sum_sq == w exactly. This constructor exists so a caller must SAY it
        has tie-free data rather than getting that assumption from a default.
        Production data can contain ties and must not use it; see
        aggregation/engine.py, which computes sum_sq from the observations.
        """
        return cls(clause_id=clause_id, w=w, n=n, sum_sq=w)


@dataclass(frozen=True)
class ClausePosterior:
    """Per-clause posterior summary."""

    clause_id: str
    # Posterior parameters
    posterior_alpha: float
    posterior_beta: float
    # Point summaries
    posterior_mean: float
    credible_interval_lo: float
    credible_interval_hi: float
    p_win_gt_threshold: float
    # Whether the shrunken (hierarchical) or unpooled posterior was used
    is_shrunken: bool
    # Raw observations
    w: float
    n: int


@dataclass(frozen=True)
class FitResult:
    """Outcome of a skill-level EB-MoM fit.

    aggregation_method:
        "ebmom_hierarchical" | "bounded_pooling_refused" | "unpooled"

        "bounded_pooling_refused" replaced "bh_fdr_fallback" when v2 section 3
        retired BH-FDR on the refused path. The name states what ran: the
        admission test refused, and the fit pooled at the bound instead. A
        receipt that still said "bh_fdr_fallback" would name a procedure the
        run did not perform.
    aggregation_provenance:
        Method-specific dict for JSON serialisation (A53).
    posteriors:
        Per-clause posterior summaries.
    bh_fdr_passes:
        ALWAYS None since v2 section 3 retired BH-FDR. No method sets it. The
        field is retained so a reader of an older receipt still has the shape
        to compare against, and so the status machine's `bh_fdr_pass` input
        keeps a declared source; consumers must treat None as "no FDR gate
        applies", which is now every case.
    """

    aggregation_method: str
    aggregation_provenance: dict[str, object]
    posteriors: tuple[ClausePosterior, ...]
    bh_fdr_passes: frozenset[str] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _unpooled_posterior(clause: ClauseObservations) -> tuple[float, float]:
    """Return (alpha, beta) for the unpooled Beta(1+w, 1+n-w) posterior."""
    return 1.0 + clause.w, 1.0 + (clause.n - clause.w)


def _posterior_stats(alpha: float, beta: float) -> tuple[float, float, float, float]:
    """Return (mean, lo_95, hi_95, p_exceeds) for a Beta(alpha, beta)."""
    mean = alpha / (alpha + beta)
    lo = float(beta_dist.ppf(0.025, alpha, beta))
    hi = float(beta_dist.ppf(0.975, alpha, beta))
    p = float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha, beta))
    return mean, lo, hi, p


def _build_unpooled_posteriors(
    clauses: list[ClauseObservations],
) -> tuple[ClausePosterior, ...]:
    results: list[ClausePosterior] = []
    for cl in clauses:
        alpha, beta = _unpooled_posterior(cl)
        mean, lo, hi, p = _posterior_stats(alpha, beta)
        results.append(
            ClausePosterior(
                clause_id=cl.clause_id,
                posterior_alpha=alpha,
                posterior_beta=beta,
                posterior_mean=mean,
                credible_interval_lo=lo,
                credible_interval_hi=hi,
                p_win_gt_threshold=p,
                is_shrunken=False,
                w=cl.w,
                n=cl.n,
            )
        )
    return tuple(results)


def _bh_fdr(p_values: list[float], q: float) -> frozenset[int]:
    """Benjamini-Hochberg FDR correction.

    Returns the set of indices (into p_values) that pass at q level.

    NO PRODUCTION CALLER since pre-registration v2 section 3 (FROZEN
    2026-09-05) retired BH-FDR on the refused path. It is retained as the
    subject of the registered detector for falsification-plan item 1, which
    measures whether `1 - posterior mass` behaves as a valid null p-value.
    That question is still worth an answer, and the answer is what would have
    to change before any caller is added back.
    """
    k = len(p_values)
    if k == 0:
        return frozenset()
    # BH: sort by p-value ascending; compare p_(i) <= i/k * q
    indexed = sorted(range(k), key=lambda i: p_values[i])
    passed: set[int] = set()
    for rank, idx in enumerate(indexed, start=1):
        if p_values[idx] <= (rank / k) * q:
            passed.add(idx)
    # All indices at or below the largest passing rank also pass (standard BH)
    if not passed:
        return frozenset()
    largest_rank = max(rank for rank, idx in enumerate(indexed, start=1) if idx in passed)
    return frozenset(indexed[:largest_rank])


def _bounded_pooling_concentration(mu: float, v_bound: float) -> float | None:
    """Form-B concentration from the admission bound, or None to revert.

    c_bound = mu (1 - mu) / v_bound - 1, the moment inversion evaluated at the
    admission test's critical order statistic rather than at the observed
    latent variance. Returns None when the inversion does not yield a proper
    Beta, in which case the caller reverts to the unpooled posterior and counts
    the revert.

    Three ways it returns None, all of them arithmetic rather than statistical:

      v_bound <= VAR_FLOOR   the division is unstable, the same guard _ebmom
                             applies to the observed variance. VAR_FLOOR is an
                             epsilon, never an admission rule.
      c_bound <= 0           the bound exceeds the maximum variance a Beta with
                             mean mu can carry, so no Beta matches the moments.
      mu c <= 0 or           a degenerate mean (0 or 1) leaves one Beta
      (1 - mu) c <= 0        parameter at zero, which is not a distribution.

    Matches `bounded_c` in the vendored reference `rescore405.py`, which
    produced v2 section 0's cand_bpB numbers, guard for guard.
    """
    if v_bound <= VAR_FLOOR:
        return None
    c = mu * (1.0 - mu) / v_bound - 1.0
    if c <= 0.0 or mu * c <= 0.0 or (1.0 - mu) * c <= 0.0:
        return None
    return c


def _admitted_bootstrap_seed(clauses: list[ClauseObservations]) -> int:
    """Seed for the admission-conditioned bootstrap, from the data and a label.

    Same frozen derivation as `_bootstrap_seed` (v1 section 3): the canonical
    clause encoding, SHA-256, first eight bytes big-endian. The label
    ADMITTED_BOOTSTRAP_LABEL is appended under the frozen field separator so
    this stream and the admission test's are distinct functions of the same
    data. `fit_skill` promises determinism and this mechanism samples, so the
    seed must be a function of the input and nothing else.

    The label cannot collide with a clause field: the canonical encoding always
    ends with a `float.hex()` value, which never ends in the label's bytes.
    """
    material = _canonical_input_bytes(clauses) + (
        _SEED_FIELD_SEP + ADMITTED_BOOTSTRAP_LABEL
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _bootstrap_moments(
    w: np.ndarray[Any, np.dtype[np.float64]],
    sum_sq: np.ndarray[Any, np.dtype[np.float64]],
    n: np.ndarray[Any, np.dtype[np.float64]],
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], np.ndarray[Any, np.dtype[np.float64]]]:
    """Recompute (sample_mean, latent_var_raw) as `fit_skill` does, over draws.

    Row-for-row the arithmetic of `fit_skill` plus `_mean_sampling_variance`,
    vectorised over synthetic worlds:

        rates          = w / n
        sample_var     = sum((r - mean)^2) / (k - 1)      UNBIASED, /(k-1)
        sampling_var_k = (sum_sq_k - n_k r_k^2) / ((n_k - 1) n_k)
        latent_raw     = sample_var - mean_k(sampling_var_k)   UNCLIPPED

    The peel is retained unclipped here for the same reason `fit_skill` retains
    it unclipped: the admission comparison below reads it as-is, and clipping
    the negative tail onto zero would bias the retained value upward.

    TWO GUARDS the reference `proto_pb.py::_moments` does not carry, both taken
    from `_mean_sampling_variance` because production must survive data the
    registered regimes do not contain:

      max(within_ss, 0)   float error can push an exactly-zero within-clause sum
                          of squares slightly negative; a genuine negative is
                          impossible, since sum_sq >= n r^2 for every real sample
                          by Cauchy-Schwarz, with equality when the clause's
                          observations are all identical.
      max(n - 1, 1)       a clause with n = 1 carries no within-clause
                          information and would divide by zero. within_ss is 0 by
                          construction there, so the clause contributes nothing
                          rather than a nan. Reached in production and by the
                          property tests; not reached by any registered regime,
                          whose n is 10, 25 or 100.

    Neither guard can change a reproduction of the prototype: on the registered
    regimes both are no-ops, which the four-decimal reproduction in
    tests/test_aggregation_fit_admitted_bootstrap.py measures rather than
    assumes.
    """
    r = w / n
    mu = r.mean(axis=1)
    sample_var = r.var(axis=1, ddof=1)
    within_ss = np.maximum(sum_sq - n * r * r, 0.0)
    sampling_var = (within_ss / (np.maximum(n - 1.0, 1.0) * n)).mean(axis=1)
    return mu, sample_var - sampling_var


def _draw_bootstrap_worlds(
    rng: np.random.Generator,
    thetas: np.ndarray[Any, np.dtype[np.float64]],
    n: np.ndarray[Any, np.dtype[np.float64]],
    tie: float,
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], np.ndarray[Any, np.dtype[np.float64]]]:
    """One synthetic world per row of `thetas`, in the {0, 0.5, 1} alphabet.

    Returns (w, sum_sq) so the caller can recompute the peel from the same
    sufficient statistics production reads. The observation model is the one the
    lane operates on: each trial is a tie with probability `tie`, else a
    decisive win with probability p_k.

    The fitted hyperprior is over the ENCODED clause mean
    theta_k = 0.5 t + (1 - t) p_k, so a drawn theta_k is inverted per clause,

        p_k = (theta_k - 0.5 t) / (1 - t)

    at the pooled tie fraction the observed data carry. That is
    `_draw_null_clause`'s model generalised from one pooled mean to one mean per
    clause. On tie-free data (`tie == 0`) it reduces exactly to the binomial
    draw, and sum_sq == w there because 0^2 = 0 and 1^2 = 1.
    """
    counts = n.astype(int)
    if tie <= 0.0:
        wins = rng.binomial(counts, np.clip(thetas, 0.0, 1.0))
        return wins.astype(float), wins.astype(float)
    ties = rng.binomial(counts, tie)
    decisive = counts - ties
    p_decisive = np.clip((thetas - 0.5 * tie) / (1.0 - tie), 0.0, 1.0)
    wins = rng.binomial(decisive, p_decisive)
    return wins + 0.5 * ties, wins + 0.25 * ties


def _plugin_tail_probabilities(
    clauses: list[ClauseObservations],
    alpha_hat: float,
    beta_hat: float,
) -> list[float]:
    """P(rate > threshold) on the plug-in shrunken posterior, per clause."""
    return [
        float(beta_dist.sf(WIN_RATE_THRESHOLD, alpha_hat + cl.w, beta_hat + (cl.n - cl.w)))
        for cl in clauses
    ]


def _admission_conditioned_probs(
    clauses: list[ClauseObservations],
    alpha_hat: float,
    beta_hat: float,
    critical_order_statistic: float,
    seed: int,
) -> tuple[list[float], dict[str, object]]:
    """Clause tail probabilities under the admission-conditioned bootstrap.

    Specification: pre-registration v2 section 4 (FROZEN 2026-09-05). Reference
    implementation: `pb_probs` in
    docs/assurance/reference/ebmom-class2-S414/proto_pb.py, which produced every
    number v2 sections 0.3 to 0.7 record. This is the same procedure inside
    production.

    Per block of ADMITTED_BOOTSTRAP_BLOCK candidate draws:

        theta_j     ~ Beta(alpha_hat, beta_hat), K of them
        one synthetic world under those means, preserving every clause's n_k and
          the pooled tie fraction the observed data carry
        (mu_s, latent_s) = the moments fit_skill computes on that world
        KEEP the draw when latent_s > critical_order_statistic
        c_s = mu_s (1 - mu_s) / latent_s - 1, non-positive dropped and counted

    stopping once ADMITTED_BOOTSTRAP_DRAWS draws are kept or the block budget is
    spent. The returned probability per clause is

        P_k = mean_s P(theta > WIN_RATE_THRESHOLD |
                       Beta(mu_s c_s + w_k, (1 - mu_s) c_s + n_k - w_k))

    on the OBSERVED (w_k, n_k). The caller decides by the locked rule on P_k.

    Returns (probabilities, diagnostics). The diagnostics are counts, not a
    summary: `drawn`, `kept`, `below_crit`, `nonpositive_c`, `exhausted`,
    `fell_back_to_plugin` and `used`, all of which reach provenance. A run that
    kept nothing has nothing to average and returns the PLUG-IN probabilities
    with `fell_back_to_plugin` true, rather than inventing a decision; a run
    that kept some but fewer than S averages what it kept and says so through
    `exhausted`. Both are typed outcomes and neither is silent.
    """
    k = len(clauses)
    n_vec = np.array([cl.n for cl in clauses], dtype=float)
    w_obs = np.array([cl.w for cl in clauses], dtype=float)
    n_block = np.broadcast_to(n_vec, (ADMITTED_BOOTSTRAP_BLOCK, k))
    tie = _pooled_null(clauses).tie

    rng = np.random.default_rng(seed)
    kept_mu: list[np.ndarray[Any, np.dtype[np.float64]]] = []
    kept_c: list[np.ndarray[Any, np.dtype[np.float64]]] = []
    n_kept = 0
    n_drawn = 0
    n_below_crit = 0
    n_nonpositive_c = 0
    for _ in range(ADMITTED_BOOTSTRAP_MAX_BLOCKS):
        if n_kept >= ADMITTED_BOOTSTRAP_DRAWS:
            break
        thetas = rng.beta(alpha_hat, beta_hat, size=(ADMITTED_BOOTSTRAP_BLOCK, k))
        w_s, sq_s = _draw_bootstrap_worlds(rng, thetas, n_block, tie)
        mu_s, latent_s = _bootstrap_moments(w_s, sq_s, n_block)
        n_drawn += ADMITTED_BOOTSTRAP_BLOCK
        admitted = latent_s > critical_order_statistic
        n_below_crit += int((~admitted).sum())
        mu_s, latent_s = mu_s[admitted], latent_s[admitted]
        # A kept draw has latent_s > critical_order_statistic, and that boundary
        # is a bootstrap order statistic which is positive in every observed
        # case but is not positive BY CONSTRUCTION. If it were not, a kept draw
        # could carry latent_s == 0 and the inversion would return an infinity
        # that passes `c_s > 0` and turns the clause probability into a nan. The
        # errstate and the isfinite term below exclude that, and neither can
        # alter a reproduction: the draws they drop are exactly the draws that
        # would otherwise put a nan into the average.
        with np.errstate(divide="ignore", invalid="ignore"):
            c_s = mu_s * (1.0 - mu_s) / latent_s - 1.0
        proper = (c_s > 0.0) & np.isfinite(c_s) & (mu_s > 0.0) & (mu_s < 1.0)
        n_nonpositive_c += int((~proper).sum())
        mu_s, c_s = mu_s[proper], c_s[proper]
        if mu_s.size:
            kept_mu.append(mu_s)
            kept_c.append(c_s)
            n_kept += int(mu_s.size)

    diagnostics: dict[str, object] = {
        "mechanism": "admission_conditioned_parametric_bootstrap",
        "spec": "docs/assurance/ebmom-peel-preregistration-amendment-v2.md section 4",
        "s_target": ADMITTED_BOOTSTRAP_DRAWS,
        "block": ADMITTED_BOOTSTRAP_BLOCK,
        "max_blocks": ADMITTED_BOOTSTRAP_MAX_BLOCKS,
        "seed": seed,
        "drawn": n_drawn,
        "kept": n_kept,
        "below_crit": n_below_crit,
        "nonpositive_c": n_nonpositive_c,
        "exhausted": n_kept < ADMITTED_BOOTSTRAP_DRAWS,
    }
    if n_kept == 0:
        # No admissible draw inside the budget. The mechanism has nothing to
        # average over, so the decision falls back to the plug-in posterior and
        # the fallback is COUNTED. Inventing a decision from an empty average is
        # the failure this branch exists to make impossible.
        logger.warning(
            "Admission-conditioned bootstrap kept 0 of %d draws (crit=%.3e): "
            "falling back to the plug-in posterior, counted in provenance.",
            n_drawn,
            critical_order_statistic,
        )
        diagnostics["fell_back_to_plugin"] = True
        diagnostics["used"] = 0
        return _plugin_tail_probabilities(clauses, alpha_hat, beta_hat), diagnostics
    diagnostics["fell_back_to_plugin"] = False

    mus = np.concatenate(kept_mu)[:ADMITTED_BOOTSTRAP_DRAWS]
    cs = np.concatenate(kept_c)[:ADMITTED_BOOTSTRAP_DRAWS]
    diagnostics["used"] = int(mus.size)
    alphas = mus[:, None] * cs[:, None] + w_obs[None, :]
    betas = (1.0 - mus[:, None]) * cs[:, None] + (n_vec - w_obs)[None, :]
    probs = beta_dist.sf(WIN_RATE_THRESHOLD, alphas, betas).mean(axis=0)
    return [float(p) for p in probs], diagnostics


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fit_skill(
    clauses: list[ClauseObservations],
) -> FitResult:
    """Fit skill-level aggregation and return per-clause posteriors.

    Selects method in priority order:
      1. UNPOOLED when K < K_MIN_FOR_EB (10).
      2. EB-MoM hierarchical when convergence succeeds.
      3. Bounded-pooling refusal (form B) when the admission test refuses or
         EB-MoM fails to converge.

    Raises ValueError naming the clause when any clause has n <= 0 or w outside [0, n].

    The function is DETERMINISTIC but no longer sampling-free. EB-MoM itself is
    closed-form; the admission test and, on the admitted path, the
    admission-conditioned bootstrap both resample. Both streams are seeded from
    the canonical clause encoding under the frozen v1 section 3 derivation, so
    the same clauses give the same verdict on every host and every run.
    """
    for clause in clauses:
        if clause.n <= 0:
            raise ValueError(f"Clause {clause.clause_id!r} must have n > 0")
        if not 0.0 <= clause.w <= clause.n:
            raise ValueError(
                f"Clause {clause.clause_id!r} must have w in [0, n={clause.n}]; got {clause.w!r}"
            )

    k = len(clauses)

    # -------------------------------------------------------------------
    # UNPOOLED: K < 10 (BDA3 §5 — EB estimate too noisy)
    # -------------------------------------------------------------------
    if k < K_MIN_FOR_EB:
        logger.warning(
            "K=%d < %d: EB hyperprior estimate unreliable. Reporting UNPOOLED posteriors per A53.",
            k,
            K_MIN_FOR_EB,
        )
        posteriors = _build_unpooled_posteriors(clauses)
        return FitResult(
            aggregation_method="unpooled",
            aggregation_provenance={"k_clauses": k, "reason": "k_below_10"},
            posteriors=posteriors,
        )

    # -------------------------------------------------------------------
    # EB-MoM — attempt hierarchical fit
    # -------------------------------------------------------------------
    rates = [cl.w / cl.n for cl in clauses]
    sample_mean = sum(rates) / k
    # UNBIASED total variance: /(k-1), not /k. The population form has
    # expectation (k-1)/k of the true total variance, so subtracting the full
    # sampling term under-peels by -(V_latent + V_sampling)/k.
    sample_var = sum((r - sample_mean) ** 2 for r in rates) / (k - 1)

    # The across-clause variance of observed rates is true heterogeneity PLUS
    # within-clause sampling noise. Peel the noise before inverting the moment
    # map; feeding the raw variance to _ebmom attributes sampling noise to the
    # hyperprior and deflates the recovered concentration by ~n/(n+c+1).
    sampling_var = _mean_sampling_variance(clauses)
    # RETAINED UNCLIPPED. latent_var_raw may be negative, and the admission test
    # and every bias assertion read it as-is: clipping first would map the whole
    # negative tail onto zero and induce a positive bias in the retained value.
    latent_var_raw = sample_var - sampling_var

    test = _heterogeneity_test(clauses, latent_var_raw)
    heterogeneity_test = {
        "statistic": test.statistic,
        "p_boot": test.p_boot,
        "critical_order_statistic": test.critical_order_statistic,
        "exceed_count": test.exceed_count,
        "null_encoded_mean": test.encoded_mean_0,
        "null_tie_fraction": test.tie_fraction_0,
        "alpha": HETEROGENEITY_TEST_ALPHA,
        "bootstrap_b": HETEROGENEITY_BOOTSTRAP_B,
        "bootstrap_seed": _bootstrap_seed(clauses),
        "admitted": test.admitted,
    }

    try:
        if not test.admitted:
            raise ConvergenceFailure(
                reason="latent_variance_not_identified",
                alpha_hat=None,
                beta_hat=None,
                sample_mean=sample_mean,
                sample_var=latent_var_raw,
            )
        # Clip ONLY here, after admission. An admitted fit has
        # latent_var_raw > critical_value >= 0 in every realistic case, so this
        # is a no-op on the admitted path; it exists to keep the arithmetic
        # total, never to repair the estimate.
        alpha_hat, beta_hat = _ebmom(sample_mean, max(latent_var_raw, 0.0))
    except ConvergenceFailure as exc:
        # -------------------------------------------------------------------
        # BOUNDED-POOLING REFUSAL, form B (v2 section 3)
        # -------------------------------------------------------------------
        fallback_reason = exc.reason
        attempted = {
            "alpha_hat": exc.alpha_hat,
            "beta_hat": exc.beta_hat,
            "sample_mean": exc.sample_mean,
            # exc.sample_var is the PEELED variance the inversion actually saw.
            # The raw and sampling terms are carried beside it so a reader can
            # tell a homogeneous population from a noisy one.
            "sample_var": exc.sample_var,
            "sample_var_raw": sample_var,
            "sampling_var": sampling_var,
            "latent_var_raw": latent_var_raw,
            "heterogeneity_test": heterogeneity_test,
        }
        # v_bound is the boundary the admission test just measured the observed
        # statistic against. Reusing it, rather than a separately estimated
        # upper bound, is what makes the estimator continuous at the admission
        # boundary: at the boundary the refused concentration below and the
        # admitted _ebmom concentration are the same number.
        mu = sample_mean
        v_bound = float(heterogeneity_test["critical_order_statistic"])
        c_bound = _bounded_pooling_concentration(mu, v_bound)
        reverted = c_bound is None

        if c_bound is None:
            logger.warning(
                "Admission refused (%s): bounded pooling reverted to UNPOOLED "
                "(mu=%.6f, v_bound=%.3e yields no proper Beta).",
                fallback_reason,
                mu,
                v_bound,
            )
            posteriors = _build_unpooled_posteriors(clauses)
        else:
            logger.warning(
                "Admission refused (%s): pooling at the admission bound "
                "(form %s, mu=%.6f, v_bound=%.3e, c_bound=%.6f).",
                fallback_reason,
                BOUNDED_POOLING_FORM,
                mu,
                v_bound,
                c_bound,
            )
            posteriors = _build_shrunken_posteriors(clauses, mu * c_bound, (1.0 - mu) * c_bound)

        return FitResult(
            aggregation_method="bounded_pooling_refused",
            aggregation_provenance={
                "k_clauses": k,
                "fallback_reason": fallback_reason,
                "attempted": attempted,
                "bounded_pooling": {
                    "form": BOUNDED_POOLING_FORM,
                    "mu": mu,
                    "v_bound": v_bound,
                    "c_bound": c_bound,
                    "reverted_to_unpooled": reverted,
                    # A COUNT, not only a flag: one fit contributes 0 or 1, and
                    # a harness summing the column over worlds gets the revert
                    # count v2 section 3 requires without re-deriving it from a
                    # boolean.
                    "unpooled_revert_count": 1 if reverted else 0,
                    "spec": ("docs/assurance/ebmom-peel-preregistration-amendment-v2.md section 3"),
                },
            },
            posteriors=posteriors,
        )

    # -------------------------------------------------------------------
    # EB-MoM SUCCESS — build shrunken posteriors
    # -------------------------------------------------------------------
    #
    # The hyperprior is fitted, not known. Deciding on the plug-in posterior
    # spends the uncertainty in (alpha_hat, beta_hat) as if it were zero, and v2
    # section 0.5 measures what that costs on the admitted path. The tail
    # probability each clause is decided on is therefore averaged over draws of
    # the hyperparameters from the finite-sample distribution the fitted model
    # implies, conditioned on the admission event that selected this fit.
    tail_probabilities, bootstrap_diagnostics = _admission_conditioned_probs(
        clauses,
        alpha_hat,
        beta_hat,
        float(heterogeneity_test["critical_order_statistic"]),
        _admitted_bootstrap_seed(clauses),
    )
    posteriors = _build_shrunken_posteriors(
        clauses, alpha_hat, beta_hat, tail_probabilities=tail_probabilities
    )
    return FitResult(
        aggregation_method="ebmom_hierarchical",
        aggregation_provenance={
            "alpha_hat": alpha_hat,
            "beta_hat": beta_hat,
            "sample_mean": sample_mean,
            "sample_var": sample_var,
            "sampling_var": sampling_var,
            "latent_var_raw": latent_var_raw,
            "heterogeneity_test": heterogeneity_test,
            "k_clauses": k,
            "admitted_bootstrap": bootstrap_diagnostics,
        },
        posteriors=posteriors,
    )


def _mean_sampling_variance(clauses: list[ClauseObservations]) -> float:
    """Mean per-clause sampling variance of the observed rate w/n.

    Computed from the sufficient statistic sum_sq, so it is exact under ties:

        within_ss_k    = sum_sq_k - n_k * r_k^2
        sampling_var_k = within_ss_k / ((n_k - 1) * n_k)

    within_ss_k is the within-clause sum of squares. Dividing by (n_k - 1)
    gives the unbiased per-observation variance, and dividing again by n_k
    gives the variance of the clause MEAN, which is the quantity the
    across-clause variance in fit_skill carries.

    Reduces exactly to the Bernoulli form when no ties are present: with
    observations in {0, 1}, sum_sq == w, so within_ss = n r - n r^2 and
    sampling_var = r(1-r)/(n-1). Generalising therefore costs nothing on
    tie-free data and cannot silently change a tie-free result.

    n_k == 1 carries no within-clause information, so the (n_k - 1) factor is
    clamped at 1. within_ss is then 0 by construction for a single
    observation, so such a clause contributes nothing rather than a guess.

    Returns the mean over clauses, matching the across-clause variance in
    fit_skill that it is subtracted from.
    """
    total = 0.0
    for clause in clauses:
        rate = clause.w / clause.n
        within_ss = clause.sum_sq - clause.n * rate * rate
        # Floating-point error can push an exactly-zero within_ss slightly
        # negative; a genuine negative is impossible for a sum of squares.
        total += max(within_ss, 0.0) / (max(clause.n - 1.0, 1.0) * clause.n)
    return total / len(clauses)


@dataclass(frozen=True)
class _HeterogeneityTest:
    """Outcome of the admission test, recorded verbatim in provenance."""

    statistic: float
    p_boot: float
    critical_order_statistic: float
    exceed_count: int
    encoded_mean_0: float
    tie_fraction_0: float
    admitted: bool


# Seed-derivation procedure, FROZEN. Every element below is part of the
# contract, because changing any of them silently changes admission verdicts on
# unchanged data:
#   sort order   -- ascending by clause_id, Python str comparison (code points)
#   field order  -- clause_id, w, n, sum_sq
#   number form  -- float.hex() for w and sum_sq (exact, round-trippable, and
#                   locale- and repr-independent); str() for the integer n
#   separators   -- "|" between fields, ";" between clauses
#   encoding     -- UTF-8
#   digest       -- SHA-256 over those bytes
#   seed         -- the first 8 bytes of the digest, big-endian, unsigned
#   generator    -- random.Random (Mersenne Twister), seeded with that integer
# Python object hashes are NOT used: they are salted per process and would make
# the verdict vary run to run, which is the exact failure this guards against.
_SEED_FIELD_SEP = "|"
_SEED_CLAUSE_SEP = ";"


def _canonical_input_bytes(clauses: list[ClauseObservations]) -> bytes:
    """Serialise the clause set to the frozen canonical byte form."""
    parts = []
    for cl in sorted(clauses, key=lambda c: c.clause_id):
        parts.append(
            _SEED_FIELD_SEP.join(
                (cl.clause_id, float(cl.w).hex(), str(int(cl.n)), float(cl.sum_sq).hex())
            )
        )
    return _SEED_CLAUSE_SEP.join(parts).encode("utf-8")


def _bootstrap_seed(clauses: list[ClauseObservations]) -> int:
    """Derive the bootstrap seed from the observations themselves.

    fit_skill is documented as deterministic and the admission test resamples,
    so the seed MUST be a function of the input: the same clauses give the same
    verdict on every host and every run. A wall-clock or global-RNG seed would
    make a published verdict irreproducible.

    The seed covers all four fields including sum_sq. (clause_id, w, n) stopped
    being the complete input when route (b) added sum_sq: two clause sets
    differing only in tie composition are different data and must not share a
    bootstrap stream.
    """
    digest = hashlib.sha256(_canonical_input_bytes(clauses)).digest()
    return int.from_bytes(digest[:8], "big")


def _decompose(clause: ClauseObservations) -> tuple[int, int, int]:
    """Recover (wins, ties, losses) exactly from (w, n, sum_sq).

    Observations take values in {0, 0.5, 1}, so

        w      = wins + 0.5 * ties
        sum_sq = wins + 0.25 * ties

    which inverts exactly:

        ties = 4 * (w - sum_sq)
        wins = 2 * sum_sq - w
        losses = n - wins - ties

    This is an identity, not an estimate, and it is why sum_sq is a genuine
    sufficient statistic for this outcome alphabet rather than a summary of
    it. Counts are rounded because they arrive through float arithmetic.
    """
    ties = round(4.0 * (clause.w - clause.sum_sq))
    wins = round(2.0 * clause.sum_sq - clause.w)
    losses = clause.n - wins - ties
    return max(wins, 0), max(ties, 0), max(losses, 0)


@dataclass(frozen=True)
class _PooledNull:
    """The one categorical distribution over {0, 0.5, 1} every clause draws from under H_0.

    Pooled over OBSERVATIONS, not averaged over clauses: tie = sum_k ties_k / N,
    win = sum_k wins_k / N, loss = 1 - tie - win. The encoded mean of a draw is
    0.5 * tie + win, which equals sum_k w_k / sum_k n_k by identity.
    """

    tie: float
    win: float
    encoded_mean: float


def _pooled_null(clauses: list[ClauseObservations]) -> _PooledNull:
    total_n = sum(cl.n for cl in clauses)
    wins = 0
    ties = 0
    for cl in clauses:
        w_k, t_k, _l_k = _decompose(cl)
        wins += w_k
        ties += t_k
    tie = ties / total_n
    win = wins / total_n
    return _PooledNull(tie=tie, win=win, encoded_mean=0.5 * tie + win)


def _draw_null_clause(
    clause: ClauseObservations,
    null: _PooledNull,
    rng: random.Random,
) -> ClauseObservations:
    """One clause resampled under H_0, preserving its n.

    H_0 is ONE categorical distribution over {0, 0.5, 1} shared by every clause
    (amendment section 3 as amended 2026-09-02 on the heterogeneity-target
    ruling, #360). Every observation is redrawn, ties included, because the
    lane's heterogeneity target is the ENCODED clause mean

        theta_k = 0.5 * t_k + (1 - t_k) * p_k

    and a clause's tie propensity t_k is a component of theta_k: part of the
    hypothesis under test, not an ancillary statistic to condition on. The
    superseded null held each clause's realised tie count fixed and so
    reproduced none of the tie-sampling variation the data carry; it admitted
    16 of 40 replicates of the registered homogeneous tie regime where alpha
    predicts 2.

    The null is categorical, not binomial: a binomial null at the pooled mean
    would regenerate a tie-free world and compare tie-carrying data against
    it. Every null clause has encoded mean null.encoded_mean by identity, with
    no per-clause inversion and no clamp. On tie-free data (null.tie == 0) the
    draw is the binomial null at the pooled rate and consumes the RNG stream
    exactly as the previous implementation did, so tie-free verdicts are
    unchanged.
    """
    # Ties are REDRAWN at the pooled tie fraction. Fixing ties_b at the
    # clause's observed tie count is the superseded null; the tie-split
    # fixture in tests/test_aggregation_fit.py refuses under that mutant.
    ties_b = 0 if null.tie == 0.0 else sum(1 for _ in range(clause.n) if rng.random() < null.tie)
    decisive = clause.n - ties_b
    p_decisive = null.win / (1.0 - null.tie) if null.tie < 1.0 else 0.0
    wins_b = sum(1 for _ in range(decisive) if rng.random() < p_decisive)
    return ClauseObservations(
        clause_id=clause.clause_id,
        w=wins_b + 0.5 * ties_b,
        n=clause.n,
        sum_sq=wins_b + 0.25 * ties_b,
    )


def _heterogeneity_test(
    clauses: list[ClauseObservations],
    latent_var_raw: float,
) -> _HeterogeneityTest:
    """Decide whether heterogeneity is identified well enough to fit.

    Tests H_0: tau^2 = 0 (one common encoded clause mean; all observed spread
    is sampling noise) against H_1: tau^2 > 0, by parametric bootstrap under
    the null.

    This REPLACES the old fixed VAR_FLOOR as the admission rule. A magnitude
    floor asks whether the latent variance is large; the question that decides
    whether a hyperprior is identified is whether it is distinguishable from
    zero given its own sampling error. A replicate with latent_var = 5e-4
    clears a 1e-6 floor and returns a concentration of 454 fitted to noise.

    Returns the full test outcome. The caller admits the fit when
    ``admitted`` is true and records the whole record in provenance, so the
    decision is reproducible and auditable: a false admission is otherwise
    invisible in the receipt, while a false refusal is visible by
    construction. Provenance makes the decision reproducible and auditable; it
    does not make an individual false admission retrospectively identifiable,
    and the weaker claim is the one being made.

    Specification: docs/assurance/ebmom-peel-preregistration-amendment.md
    section 3.
    """
    # S311 is suppressed below: this is a statistical bootstrap, not a security
    # primitive. A reproducible PRNG seeded from the data is exactly what is
    # wanted here; a cryptographic source would make the verdict irreproducible.
    rng = random.Random(_bootstrap_seed(clauses))  # noqa: S311

    # The null is one pooled categorical distribution, so every null clause
    # carries the same ENCODED mean, the quantity whose between-clause
    # variance the test is about. Pooled over observations, not averaged
    # over clauses.
    null = _pooled_null(clauses)

    null_stats: list[float] = []
    for _ in range(HETEROGENEITY_BOOTSTRAP_B):
        null_clauses = [_draw_null_clause(cl, null, rng) for cl in clauses]
        null_rates = [c.w / c.n for c in null_clauses]
        null_mean = sum(null_rates) / len(null_rates)
        null_total = sum((r - null_mean) ** 2 for r in null_rates) / (len(null_rates) - 1)
        null_stats.append(null_total - _mean_sampling_variance(null_clauses))

    # Finite-bootstrap p-value with the +1 correction, NOT an interpolated
    # percentile. At finite B the achievable levels are discrete, and
    # (1 + count) / (B + 1) is the form that keeps the test valid there; a
    # library-interpolated 95th percentile sits between order statistics and
    # can admit at a true level above alpha.
    exceed = sum(1 for stat in null_stats if stat >= latent_var_raw)
    p_boot = (1.0 + exceed) / (HETEROGENEITY_BOOTSTRAP_B + 1.0)

    # The order statistic the decision turns on, recorded so a reader can see
    # the boundary the observed statistic was measured against.
    null_stats.sort()
    index = math.ceil((1.0 - HETEROGENEITY_TEST_ALPHA) * len(null_stats)) - 1
    critical_order_statistic = null_stats[min(max(index, 0), len(null_stats) - 1)]

    return _HeterogeneityTest(
        statistic=latent_var_raw,
        p_boot=p_boot,
        critical_order_statistic=critical_order_statistic,
        exceed_count=exceed,
        encoded_mean_0=null.encoded_mean,
        tie_fraction_0=null.tie,
        admitted=p_boot <= HETEROGENEITY_TEST_ALPHA,
    )


def _ebmom(sample_mean: float, sample_var: float) -> tuple[float, float]:
    """Compute (alpha_hat, beta_hat) via Method-of-Moments.

    Closed-form per A53:
        m = sample_mean
        v = sample_var
        alpha_hat = m * (m*(1-m)/v - 1)
        beta_hat  = (1-m) * (m*(1-m)/v - 1)

    This is the pure moment inversion and knows nothing about sampling noise.
    fit_skill passes the PEELED (latent) variance, so every guard below reads
    against latent heterogeneity rather than raw dispersion: a population
    whose observed spread is entirely binomial noise peels to zero and lands
    on var_below_threshold, which routes it to the BH-FDR fallback as the
    degenerate case it is.

    Raises ConvergenceFailure when:
      - sample_var < VAR_FLOOR  (degenerate; division unstable)
      - alpha_hat <= 0
      - beta_hat <= 0
    """
    m = sample_mean
    v = sample_var

    if v < VAR_FLOOR:
        raise ConvergenceFailure(
            reason="var_below_threshold",
            alpha_hat=None,
            beta_hat=None,
            sample_mean=m,
            sample_var=v,
        )

    common = m * (1.0 - m) / v - 1.0
    alpha_hat = m * common
    beta_hat = (1.0 - m) * common

    if alpha_hat <= 0.0:
        raise ConvergenceFailure(
            reason="alpha_le_zero",
            alpha_hat=alpha_hat,
            beta_hat=beta_hat,
            sample_mean=m,
            sample_var=v,
        )
    if beta_hat <= 0.0:
        raise ConvergenceFailure(
            reason="beta_le_zero",
            alpha_hat=alpha_hat,
            beta_hat=beta_hat,
            sample_mean=m,
            sample_var=v,
        )

    return alpha_hat, beta_hat


def _build_shrunken_posteriors(
    clauses: list[ClauseObservations],
    alpha_hat: float,
    beta_hat: float,
    tail_probabilities: list[float] | None = None,
) -> tuple[ClausePosterior, ...]:
    """Compute shrunken posterior Beta(alpha_hat + w_k, beta_hat + n_k - w_k) per clause.

    `tail_probabilities`, when given, REPLACES `p_win_gt_threshold` with a tail
    probability computed elsewhere, one per clause in clause order. The admitted
    path passes the admission-conditioned bootstrap's P_k there (v2 section 4).

    What that means for a reader of the result, stated because it is a real
    inconsistency and not an oversight: on that path

        p_win_gt_threshold != sf(WIN_RATE_THRESHOLD, posterior_alpha, posterior_beta)

    by construction. P_k is the tail of a MIXTURE over S hyperparameter draws and
    no single Beta carries it. The reported (posterior_alpha, posterior_beta) are
    the plug-in posterior the mechanism integrates around -- retained rather than
    replaced by an invented single Beta, because a moment-matched stand-in would
    be a distribution the run never used. Provenance names the mechanism and
    carries its draw counts, and
    `tests/test_aggregation_fit_admitted_bootstrap.py` pins the divergence so it
    cannot be quietly closed by a later change to either side.
    """
    if tail_probabilities is not None and len(tail_probabilities) != len(clauses):
        raise ValueError(
            f"tail_probabilities has {len(tail_probabilities)} entries for {len(clauses)} clauses"
        )
    results: list[ClausePosterior] = []
    for index, cl in enumerate(clauses):
        alpha = alpha_hat + cl.w
        beta = beta_hat + (cl.n - cl.w)
        mean, lo, hi, p = _posterior_stats(alpha, beta)
        if tail_probabilities is not None:
            p = tail_probabilities[index]
        results.append(
            ClausePosterior(
                clause_id=cl.clause_id,
                posterior_alpha=alpha,
                posterior_beta=beta,
                posterior_mean=mean,
                credible_interval_lo=lo,
                credible_interval_hi=hi,
                p_win_gt_threshold=p,
                is_shrunken=True,
                w=cl.w,
                n=cl.n,
            )
        )
    return tuple(results)
