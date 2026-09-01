"""Empirical-Bayes Method-of-Moments hierarchical fit + BH-FDR fallback (A53).

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

Admission: a hierarchical fit is attempted only when the peeled latent variance
  is distinguishable from zero by a one-sided bootstrap test (see
  HETEROGENEITY_TEST_ALPHA). Otherwise it is refused as
  latent_variance_not_identified and BH-FDR runs instead.
Convergence failure (alpha_hat <= 0 or beta_hat <= 0, or the admission test
  refuses): fall back to BH-FDR at q=0.05.

Determinism: the admission bootstrap is seeded from a digest of the
observations themselves, so identical input yields an identical verdict on
every host and every run. PYTHONHASHSEED=0 already pinned by caller
environment.

scipy.stats.beta.sf is the probability evaluation primitive (mirror of
ablation/stopping.py pattern).
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from dataclasses import dataclass

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
BH_FDR_Q: float = 0.05


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
        "ebmom_hierarchical" | "bh_fdr_fallback" | "unpooled"
    aggregation_provenance:
        Method-specific dict for JSON serialisation (A53).
    posteriors:
        Per-clause posterior summaries.
    bh_fdr_passes:
        For bh_fdr_fallback only — set of clause_ids where p_adj < q.
        For other methods: None (decision delegated to status machine).
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
      3. BH-FDR fallback when EB-MoM fails to converge.

    Raises ValueError naming the clause when any clause has n <= 0 or w outside [0, n].

    The function is deterministic (no random sampling — EB-MoM is closed-form).
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
        # BH-FDR FALLBACK
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
        logger.warning(
            "EB-MoM convergence failure (%s): falling back to BH-FDR at q=%.2f.",
            fallback_reason,
            BH_FDR_Q,
        )
        # Compute unpooled p_exceeds for BH-FDR
        unpooled_posteriors = _build_unpooled_posteriors(clauses)
        p_exceeds_list = [cp.p_win_gt_threshold for cp in unpooled_posteriors]

        # BH-FDR: "passes" when the adjusted threshold is met.
        # We invert: p_value = 1 - p_exceeds (null: rate <= 0.60).
        p_values = [1.0 - p for p in p_exceeds_list]
        passing_indices = _bh_fdr(p_values, BH_FDR_Q)
        passing_clause_ids = frozenset(unpooled_posteriors[i].clause_id for i in passing_indices)

        return FitResult(
            aggregation_method="bh_fdr_fallback",
            aggregation_provenance={
                "q": BH_FDR_Q,
                "k_clauses": k,
                "fallback_reason": fallback_reason,
                "attempted": attempted,
            },
            posteriors=unpooled_posteriors,
            bh_fdr_passes=passing_clause_ids,
        )

    # -------------------------------------------------------------------
    # EB-MoM SUCCESS — build shrunken posteriors
    # -------------------------------------------------------------------
    posteriors = _build_shrunken_posteriors(clauses, alpha_hat, beta_hat)
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


def _draw_null_clause(
    clause: ClauseObservations,
    encoded_mean_0: float,
    rng: random.Random,
) -> ClauseObservations:
    """One clause resampled under H_0, preserving its n and its tie count.

    The null is CATEGORICAL over {0, 0.5, 1}, not binomial. A binomial null at
    the pooled mean would generate a tie-free world and compare tie-carrying
    data against it, reintroducing the misspecification sum_sq was added to
    remove.

    THE ESTIMAND HELD CONSTANT IS THE ENCODED CLAUSE MEAN, and that forces the
    decisive win probability to vary by clause. With tie fraction
    q_k = ties_k / n_k, a clause's encoded mean is

        E[X_k] = 0.5 q_k + (1 - q_k) p_k

    so a COMMON decisive rate p_k = p_0 produces DIFFERENT encoded means
    whenever tie fractions differ: at p_0 = 0.75 the encoded mean runs 0.70,
    0.65 and 0.60 for q = 0.20, 0.40 and 0.60. That is real between-clause
    variation, so such a draw is not a null for the hypothesis under test --
    it is a world with genuine heterogeneity in it. Inverting instead:

        p_0k = (mu_0 - 0.5 q_k) / (1 - q_k)

    gives every clause the same encoded mean mu_0 by construction. Tie counts
    stay fixed because how many trials tied is a property of the evidence
    collected, not of the hypothesis.
    """
    _wins, ties, _losses = _decompose(clause)
    decisive = clause.n - ties
    if decisive <= 0:
        # All ties: nothing to resample, and no decisive rate is identified.
        return ClauseObservations(
            clause_id=clause.clause_id, w=0.5 * ties, n=clause.n, sum_sq=0.25 * ties
        )

    tie_fraction = ties / clause.n
    p_0k = (encoded_mean_0 - 0.5 * tie_fraction) / (1.0 - tie_fraction)
    p_0k = min(max(p_0k, 0.0), 1.0)

    w = 0.5 * ties
    sum_sq = 0.25 * ties
    for _ in range(decisive):
        if rng.random() < p_0k:
            w += 1.0
            sum_sq += 1.0
    return ClauseObservations(clause_id=clause.clause_id, w=w, n=clause.n, sum_sq=sum_sq)


def _heterogeneity_test(
    clauses: list[ClauseObservations],
    latent_var_raw: float,
) -> _HeterogeneityTest:
    """Decide whether heterogeneity is identified well enough to fit.

    Tests H_0: tau^2 = 0 (one common rate; all observed spread is sampling
    noise) against H_1: tau^2 > 0, by parametric bootstrap under the null.

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

    # The null holds the ENCODED clause mean constant, because that is the
    # quantity whose between-clause variance the test is about. Pooled over
    # observations, not averaged over clauses.
    total_n = sum(cl.n for cl in clauses)
    encoded_mean_0 = sum(cl.w for cl in clauses) / total_n

    null_stats: list[float] = []
    for _ in range(HETEROGENEITY_BOOTSTRAP_B):
        null_clauses = [_draw_null_clause(cl, encoded_mean_0, rng) for cl in clauses]
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
        encoded_mean_0=encoded_mean_0,
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
) -> tuple[ClausePosterior, ...]:
    """Compute shrunken posterior Beta(alpha_hat + w_k, beta_hat + n_k - w_k) per clause."""
    results: list[ClausePosterior] = []
    for cl in clauses:
        alpha = alpha_hat + cl.w
        beta = beta_hat + (cl.n - cl.w)
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
                is_shrunken=True,
                w=cl.w,
                n=cl.n,
            )
        )
    return tuple(results)
