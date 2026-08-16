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
Convergence failure (alpha_hat <= 0 or beta_hat <= 0 or sample_var < 1e-6):
  fall back to BH-FDR at q=0.05.

Determinism: no random sampling (EB-MoM is closed-form). PYTHONHASHSEED=0
already pinned by caller environment.

scipy.stats.beta.sf is the probability evaluation primitive (mirror of
ablation/stopping.py pattern).
"""

from __future__ import annotations

import logging
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

# Minimum sample variance to attempt EB-MoM (below this → degenerate).
VAR_FLOOR: float = 1e-6

# BH-FDR significance level (A9).
BH_FDR_Q: float = 0.05


# ---------------------------------------------------------------------------
# Per-clause input/output shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClauseObservations:
    """Aggregated observations for one clause.

    w  = sum of observations (Win=1, Tie=0.5, Loss=0).
    n  = total observation count (integer).
    """

    clause_id: str
    w: float
    n: int


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

    Raises ValueError naming the clause when any clause has n <= 0.

    The function is deterministic (no random sampling — EB-MoM is closed-form).
    """
    for clause in clauses:
        if clause.n <= 0:
            raise ValueError(f"Clause {clause.clause_id!r} must have n > 0")

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
    sample_var = sum((r - sample_mean) ** 2 for r in rates) / k  # population var

    try:
        alpha_hat, beta_hat = _ebmom(sample_mean, sample_var)
    except ConvergenceFailure as exc:
        # -------------------------------------------------------------------
        # BH-FDR FALLBACK
        # -------------------------------------------------------------------
        fallback_reason = exc.reason
        attempted = {
            "alpha_hat": exc.alpha_hat,
            "beta_hat": exc.beta_hat,
            "sample_mean": exc.sample_mean,
            "sample_var": exc.sample_var,
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
            "k_clauses": k,
        },
        posteriors=posteriors,
    )


def _ebmom(sample_mean: float, sample_var: float) -> tuple[float, float]:
    """Compute (alpha_hat, beta_hat) via Method-of-Moments.

    Closed-form per A53:
        m = sample_mean
        v = sample_var
        alpha_hat = m * (m*(1-m)/v - 1)
        beta_hat  = (1-m) * (m*(1-m)/v - 1)

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
