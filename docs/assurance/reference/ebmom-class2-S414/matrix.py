"""Acceptance-matrix harness for the EB-MoM peel and heterogeneity gate (#360).

Runs the frozen acceptance matrix in
``docs/assurance/ebmom-peel-preregistration-amendment.md`` section 5.

The harness derives EVERY regime seed and replicate seed from a single root
seed supplied on the command line. It refuses to invent one. That is the whole
control: the session that wrote the specification and built this file does not
choose the confirmatory worlds, so it cannot have tuned anything to them.

    python scripts/ebmom_acceptance_matrix.py --root-seed <64 hex chars>

Baseline and candidate are evaluated on the SAME generated worlds, world for
world, so rows 5 and 6 are paired differences on identical inputs rather than
two independent samples.

ASCII only, per the repository's cp1252 console constraint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field

from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]
from scipy.stats import binomtest

from skill_harness.aggregation.fit import (
    HETEROGENEITY_TEST_ALPHA,
    VAR_FLOOR,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    fit_skill,
)
from skill_harness.aggregation.fit import _decompose as decompose

# --- frozen protocol constants (amendment sections 4, 5, 7) -----------------

R_REPLICATES = 1000
PASS_P = 0.95
FAIL_P = 0.05
BIAS_TOL = 0.10  # absolute relative bias bound, nonzero-variance regimes
CALIBRATION_TEST_LEVEL = 0.01  # exact binomial test level for row 1


@dataclass(frozen=True)
class Regime:
    """One registered synthetic world.

    tie_rate = 0 means a tie-free (Bernoulli) regime, where the hyperprior is
    Beta(a_true, b_true) on the clause rate directly.

    tie_rate > 0 means the encoded observation is 0.5 with that probability and
    otherwise decisive at p_k ~ Beta(a_true, b_true). The encoded clause mean is
    then tie_rate/2 + (1 - tie_rate) * p_k, whose variance is
    (1 - tie_rate)^2 * Var(p_k).
    """

    name: str
    a_true: float
    b_true: float
    n_trials: int
    k_clauses: int
    tie_rate: float = 0.0
    homogeneous_p: float | None = None  # set for the null regime

    @property
    def encoded_mean(self) -> float:
        if self.homogeneous_p is not None:
            return self.tie_rate * 0.5 + (1.0 - self.tie_rate) * self.homogeneous_p
        p_mean = self.a_true / (self.a_true + self.b_true)
        return self.tie_rate * 0.5 + (1.0 - self.tie_rate) * p_mean

    @property
    def true_latent_variance(self) -> float:
        """Between-clause variance of the ENCODED clause mean."""
        if self.homogeneous_p is not None:
            return 0.0
        c = self.a_true + self.b_true
        var_p = (self.a_true * self.b_true) / (c * c * (c + 1.0))
        return (1.0 - self.tie_rate) ** 2 * var_p

    def pseudo_true_moment_matched_beta(self) -> tuple[float, float] | None:
        """The Beta target of the MOMENT MAP. NOT the true latent distribution.

        For a tie regime the latent distribution is a scaled Beta,
        theta_k = 0.5 t + (1 - t) p_k with p_k ~ Beta(a_true, b_true), which is
        not itself Beta. This moment-matched Beta is what an EB-MoM estimator
        converges to, so it is the right target for an estimator-recovery
        comparison. It is the WRONG object to call the oracle, and decision
        truth does not use it -- see oracle_decisions.
        """
        if self.true_latent_variance <= 0.0:
            return None
        mean = self.encoded_mean
        var = self.true_latent_variance
        c = mean * (1.0 - mean) / var - 1.0
        return mean * c, (1.0 - mean) * c

    @property
    def decisive_threshold(self) -> float:
        """The decisive-rate threshold equivalent to WIN_RATE_THRESHOLD.

        theta = 0.5 t + (1 - t) p exceeds the encoded threshold exactly when
        p exceeds (threshold - 0.5 t) / (1 - t). At t = 0.40 and a 0.60
        threshold that is 2/3.
        """
        if self.tie_rate <= 0.0:
            return WIN_RATE_THRESHOLD
        return (WIN_RATE_THRESHOLD - 0.5 * self.tie_rate) / (1.0 - self.tie_rate)


REGIMES: tuple[Regime, ...] = (
    # Tie-free, carried over from the original registration.
    Regime("small_n_bite", 0.65 * 20, 0.35 * 20, n_trials=10, k_clauses=200),
    Regime("low_heterogeneity", 0.65 * 100, 0.35 * 100, n_trials=25, k_clauses=200),
    Regime("benign_large_n", 0.65 * 10, 0.35 * 10, n_trials=100, k_clauses=200),
    # Tie-carrying, registered in amendment section 4.
    Regime(
        "tie_heavy_null",
        a_true=1.0,
        b_true=1.0,
        n_trials=25,
        k_clauses=200,
        tie_rate=0.40,
        homogeneous_p=0.75,
    ),
    Regime(
        "tie_heavy_signal",
        a_true=15.0,
        b_true=5.0,
        n_trials=25,
        k_clauses=200,
        tie_rate=0.40,
    ),
)


# --- seed derivation --------------------------------------------------------


def derive_seed(root_seed: str, *parts: object) -> int:
    """Derive a stream seed from the root and a label path.

    Every seed the harness uses comes through here, so the whole run is a pure
    function of the root seed the maintainer supplies.
    """
    material = "|".join([root_seed, *(str(p) for p in parts)])
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")


# --- world generation -------------------------------------------------------


def draw_world(regime: Regime, seed: int) -> tuple[list[ClauseObservations], list[float]]:
    """Generate one replicate. Returns (clauses, true encoded clause means)."""
    rng = random.Random(seed)  # noqa: S311  -- simulation, not a security primitive
    clauses: list[ClauseObservations] = []
    truths: list[float] = []

    for i in range(regime.k_clauses):
        if regime.homogeneous_p is not None:
            p_decisive = regime.homogeneous_p
        else:
            p_decisive = rng.betavariate(regime.a_true, regime.b_true)
        truths.append(regime.tie_rate * 0.5 + (1.0 - regime.tie_rate) * p_decisive)

        w = 0.0
        sum_sq = 0.0
        for _ in range(regime.n_trials):
            if regime.tie_rate > 0.0 and rng.random() < regime.tie_rate:
                obs = 0.5
            elif rng.random() < p_decisive:
                obs = 1.0
            else:
                obs = 0.0
            w += obs
            sum_sq += obs * obs
        clauses.append(ClauseObservations(clause_id=f"c{i}", w=w, n=regime.n_trials, sum_sq=sum_sq))
    return clauses, truths


# --- the baseline estimator, as `main` behaves ------------------------------


def baseline_fit(clauses: list[ClauseObservations]) -> tuple[str, float | None, float | None]:
    """Re-derivation of the estimator on `main`: no peel, /K variance, VAR_FLOOR.

    Written here rather than imported so the comparison survives the candidate
    replacing production. Returns (method, alpha_hat, beta_hat).
    """
    k = len(clauses)
    rates = [cl.w / cl.n for cl in clauses]
    mean = sum(rates) / k
    var = sum((r - mean) ** 2 for r in rates) / k  # population, unpeeled

    if var < VAR_FLOOR:
        return "bh_fdr_fallback", None, None
    common = mean * (1.0 - mean) / var - 1.0
    alpha_hat = mean * common
    beta_hat = (1.0 - mean) * common
    if alpha_hat <= 0.0 or beta_hat <= 0.0:
        return "bh_fdr_fallback", None, None
    return "ebmom_hierarchical", alpha_hat, beta_hat


# --- decisions --------------------------------------------------------------


def decision(p_win: float) -> str:
    if p_win >= PASS_P:
        return "PASS"
    if p_win <= FAIL_P:
        return "FAIL"
    return "UNDECIDED"


def oracle_decisions(regime: Regime, clauses: list[ClauseObservations]) -> list[str]:
    """Decision truth under the EXACT generative model (amendment section 4).

    For a tie regime this is the exact tie-model posterior, not a
    moment-matched approximation. A tie carries no information about p_k when
    the tie probability is fixed independently of it, so ties do not update
    p_k and the posterior is

        p_k | W, L  ~  Beta(a_true + W, b_true + L)

    and the encoded threshold maps to regime.decisive_threshold on p_k.
    """
    if regime.tie_rate > 0.0 and regime.homogeneous_p is None:
        out: list[str] = []
        for cl in clauses:
            wins, _ties, losses = decompose(cl)
            p_exceed = float(
                beta_dist.sf(
                    regime.decisive_threshold,
                    regime.a_true + wins,
                    regime.b_true + losses,
                )
            )
            out.append(decision(p_exceed))
        return out

    prior = regime.pseudo_true_moment_matched_beta()
    if prior is None:
        # Degenerate oracle: every clause's true encoded mean is exactly
        # regime.encoded_mean, so P(rate > threshold) is 0 or 1.
        verdict = "PASS" if regime.encoded_mean > WIN_RATE_THRESHOLD else "FAIL"
        return [verdict] * len(clauses)
    a0, b0 = prior
    return [
        decision(float(beta_dist.sf(WIN_RATE_THRESHOLD, a0 + cl.w, b0 + (cl.n - cl.w))))
        for cl in clauses
    ]


def fitted_decisions(
    clauses: list[ClauseObservations], alpha_hat: float | None, beta_hat: float | None
) -> list[str]:
    """Decisions from the shrunken posterior, or unpooled when no fit was made."""
    a0, b0 = (alpha_hat, beta_hat) if alpha_hat is not None and beta_hat is not None else (1.0, 1.0)
    return [
        decision(float(beta_dist.sf(WIN_RATE_THRESHOLD, a0 + cl.w, b0 + (cl.n - cl.w))))
        for cl in clauses
    ]


# --- the matrix -------------------------------------------------------------


@dataclass
class RegimeResult:
    name: str
    true_latent_variance: float
    admitted: int = 0
    replicates: int = 0
    latent_estimates: list[float] = field(default_factory=list)
    fallback_reasons: dict[str, int] = field(default_factory=dict)
    wrong_pass_candidate: int = 0
    wrong_fail_candidate: int = 0
    added_abstention_candidate: int = 0
    wrong_pass_baseline: int = 0
    wrong_fail_baseline: int = 0
    added_abstention_baseline: int = 0

    def relative_bias(self) -> float | None:
        if self.true_latent_variance <= 0.0 or not self.latent_estimates:
            return None
        mean_est = sum(self.latent_estimates) / len(self.latent_estimates)
        return (mean_est - self.true_latent_variance) / self.true_latent_variance


def score(truth_decisions: list[str], fit_decisions: list[str]) -> tuple[int, int, int]:
    """Return (wrong_pass, wrong_fail, added_abstention)."""
    wrong_pass = wrong_fail = abstained = 0
    for oracle, fitted in zip(truth_decisions, fit_decisions, strict=True):
        if fitted == oracle:
            continue
        if fitted == "PASS":
            wrong_pass += 1
        elif fitted == "FAIL":
            wrong_fail += 1
        else:
            abstained += 1
    return wrong_pass, wrong_fail, abstained


def run_regime(regime: Regime, root_seed: str, replicates: int) -> RegimeResult:
    result = RegimeResult(regime.name, regime.true_latent_variance)

    for r in range(replicates):
        clauses, _truths = draw_world(regime, derive_seed(root_seed, regime.name, r))
        result.replicates += 1

        candidate = fit_skill(clauses)
        prov = candidate.aggregation_provenance
        # Row 3 reads latent_raw across ALL replicates, admitted or refused.
        # On the refused path the test record is nested under "attempted";
        # reading only the top level would collect admitted fits only, and
        # admission selects the positive tail, which manufactures bias.
        test = prov.get("heterogeneity_test")
        if not isinstance(test, dict):
            attempted = prov.get("attempted")
            if isinstance(attempted, dict):
                test = attempted.get("heterogeneity_test")
        if not isinstance(test, dict):
            raise AssertionError(
                f"no heterogeneity_test in provenance for method "
                f"{candidate.aggregation_method!r}; row 3 would silently "
                f"condition on admission"
            )
        result.latent_estimates.append(float(test["statistic"]))
        if candidate.aggregation_method == "ebmom_hierarchical":
            result.admitted += 1
            cand_a = float(prov["alpha_hat"])  # type: ignore[arg-type]
            cand_b = float(prov["beta_hat"])  # type: ignore[arg-type]
        else:
            cand_a = cand_b = None  # type: ignore[assignment]
            reason = str(prov.get("fallback_reason", "unknown"))
            result.fallback_reasons[reason] = result.fallback_reasons.get(reason, 0) + 1

        base_method, base_a, base_b = baseline_fit(clauses)
        del base_method

        oracle = oracle_decisions(regime, clauses)
        wp, wf, ab = score(oracle, fitted_decisions(clauses, cand_a, cand_b))
        result.wrong_pass_candidate += wp
        result.wrong_fail_candidate += wf
        result.added_abstention_candidate += ab

        wp, wf, ab = score(oracle, fitted_decisions(clauses, base_a, base_b))
        result.wrong_pass_baseline += wp
        result.wrong_fail_baseline += wf
        result.added_abstention_baseline += ab

    return result


def calibration_verdict(result: RegimeResult) -> dict[str, object] | None:
    """Row 1: exact binomial test of admission rate against alpha."""
    if result.true_latent_variance > 0.0:
        return None
    test = binomtest(result.admitted, result.replicates, HETEROGENEITY_TEST_ALPHA)
    p_value = float(test.pvalue)
    return {
        "admitted": result.admitted,
        "replicates": result.replicates,
        "expected_rate": HETEROGENEITY_TEST_ALPHA,
        "p_value": p_value,
        "test_level": CALIBRATION_TEST_LEVEL,
        # Failure to reject is the pass condition.
        "calibrated": p_value >= CALIBRATION_TEST_LEVEL,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root-seed",
        required=True,
        help="Root seed supplied by the maintainer. Every regime and replicate "
        "seed is derived from it. The harness never invents one.",
    )
    parser.add_argument("--replicates", type=int, default=R_REPLICATES)
    parser.add_argument("--out", default="-", help="JSON output path, or - for stdout")
    args = parser.parse_args(argv)

    if args.replicates != R_REPLICATES:
        print(
            f"NOTE: replicates={args.replicates} is not the registered R={R_REPLICATES}. "
            "This run is a smoke test and is NOT a confirmatory run.",
            file=sys.stderr,
        )

    regime_rows: list[dict[str, object]] = []
    report: dict[str, object] = {
        "root_seed": args.root_seed,
        "replicates": args.replicates,
        "registered_replicates": R_REPLICATES,
        "is_confirmatory": args.replicates == R_REPLICATES,
        "alpha": HETEROGENEITY_TEST_ALPHA,
        "bias_tolerance": BIAS_TOL,
    }

    killed = False
    for regime in REGIMES:
        result = run_regime(regime, args.root_seed, args.replicates)
        bias = result.relative_bias()
        excess_pass = result.wrong_pass_candidate - result.wrong_pass_baseline
        excess_fail = result.wrong_fail_candidate - result.wrong_fail_baseline
        if excess_pass > 0 or excess_fail > 0:
            killed = True

        row: dict[str, object] = {
            "regime": result.name,
            "true_latent_variance": result.true_latent_variance,
            "admission_rate": result.admitted / result.replicates,
            "calibration": calibration_verdict(result),
            "relative_bias_latent_raw": bias,
            "bias_within_tolerance": None if bias is None else abs(bias) <= BIAS_TOL,
            "fallback_reasons": result.fallback_reasons,
            "wrong_pass": {
                "candidate": result.wrong_pass_candidate,
                "baseline": result.wrong_pass_baseline,
                "excess": excess_pass,
            },
            "wrong_fail": {
                "candidate": result.wrong_fail_candidate,
                "baseline": result.wrong_fail_baseline,
                "excess": excess_fail,
            },
            "added_abstention": {
                "candidate": result.added_abstention_candidate,
                "baseline": result.added_abstention_baseline,
                "excess": result.added_abstention_candidate - result.added_abstention_baseline,
            },
        }
        regime_rows.append(row)

    report["regimes"] = regime_rows
    report["kill_criterion_triggered"] = killed
    report["verdict"] = "REJECTED" if killed else "NOT_REJECTED"

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out == "-":
        print(payload)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
    # The harness reports; it does not gate CI. Exit 0 either way so a kill is
    # read from the verdict field rather than inferred from an exit code.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
