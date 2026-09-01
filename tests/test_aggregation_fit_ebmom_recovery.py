"""EB-MoM recovery against a known hyperprior (falsification plan item 2, #344).

Registered condition (docs/assurance/falsification-plan.md item 2): ``fit_skill``
computes per-clause rates ``w/n``, takes their population variance, and inverts
the Beta moment map in ``_ebmom`` with NO subtraction of mean binomial sampling
variance. The variance across observed rates therefore overstates true
heterogeneity: small-n clauses look more heterogeneous than they are
(under-shrinkage, overconfident decisions), and a genuinely homogeneous
population is fit as heterogeneous (over-shrinkage of strong clauses is the
opposite regime's risk).

PRE-REGISTRATION -- written before any simulation was run, per #344.

Generative model
----------------
For each regime: ``p_k ~ Beta(a*, b*)`` i.i.d. across K clauses,
``w_k ~ Binomial(n, p_k)``. Pure wins/losses; production ``w`` may carry ties
at half-weight but the moment map consumes only ``(w, n)`` and a tie-weighted
``w`` at the same true rate is less dispersed, so the binomial case is the
conservative (most-dispersed) reading of the same condition.

Parametrisation under test: mean ``mu* = a*/(a*+b*)`` and concentration
``c* = a*+b*``. The analytic prediction for the missing peel is
``E[var(rates)] ~= mu*(1-mu*) * (1/(c*+1) + 1/n)``, so the recovered
concentration deflates by roughly the factor ``n / (n + c* + 1)``.

Regimes (the ticket requires the first two; the third is a discriminant
control predicted to pass, and it is the surface the mutation receipt kills
against):

- ``small_n_bite``:       mu*=0.65, c*=20,  n=10,  K=200. Predicted deflation
  factor 10/31 ~= 0.32 -- a 68 percent concentration shortfall.
- ``low_heterogeneity``:  mu*=0.65, c*=100, n=25,  K=200. Predicted deflation
  25/126 ~= 0.20 -- an 80 percent shortfall in the over-shrinkage regime.
- ``benign_large_n``:     mu*=0.65, c*=10,  n=100, K=200. Predicted deflation
  100/111 ~= 0.90 -- a 10 percent shortfall, INSIDE tolerance; the detector
  must not fire here, or it is flagging the estimator rather than the defect.

Bounds, justified from both ends BEFORE observing the result
------------------------------------------------------------
``R = 50`` independent replicates per regime; assertions are on the mean over
replicates of each recovered quantity.

1. ``CONC_REL_TOL = 0.25``: the mean recovered concentration must sit within
   25 percent of ``c*``.
   From below (must not flag estimator noise): the relative sampling error of
   a population variance over K i.i.d. draws is about sqrt(2/K) = 10 percent
   at K=200; the concentration is a smooth function of (mean, variance), so a
   single replicate's relative error is of that order and the mean over R=50
   replicates has relative standard error about 1.4 percent. The tolerance is
   more than fifteen such standard errors, so a correct estimator essentially
   cannot trip it. MoM's own finite-K bias is O(1/K) and second-order here.
   From above (must catch the registered defect where theory says it bites):
   the predicted shortfalls in the two firing regimes are 68 and 80 percent,
   nearly three times the tolerance; the bound cannot miss them.
2. ``MEAN_ABS_TOL = 0.03``: the mean recovered ``mu`` must sit within 0.03 of
   ``mu*`` in every regime. The sample mean of K*R = 10000 clause rates has
   standard error sqrt(mu(1-mu)/(K*R*n)) < 0.002 in the worst regime; 0.03 is
   more than fifteen standard errors, and the missing peel does not bias the
   mean, so this doubles as a harness sanity check.
3. ``DECISION_FLIP_TOL = 0.02``: the fraction of clause decisions (tri-state:
   PASS at p>=0.95, FAIL at p<=0.05, else UNDECIDED, per the locked
   INVARIANTS.md section 1 thresholds) that differ between the fitted shrunken
   posterior and the oracle shrunken posterior built from the TRUE (a*, b*)
   must not exceed 2 percent in the benign regime.
   From below: with a correct fit the two posteriors differ only by estimator
   noise on 10000 clause decisions, and a 2 percent flip budget is far above
   the noise floor implied by bound 1's 1.4 percent parameter error (decisions
   flip only for clauses near a threshold; a <=25 percent-of-c parameter error
   moves p_win by well under the width of the undecided band for all but a
   thin boundary shell, measured conservatively as under 1 percent of draws).
   From above: 2 percent of decisions is one flipped verdict per fifty
   clauses, the materiality line at which the locked gate's output is no
   longer reproducible from the model it claims to implement.
   The flip rate in the two firing regimes is MEASURED AND REPORTED via the
   recovery assertions' failure messages (severity evidence for the findings
   document) rather than asserted, because the concentration assertions
   already fire there and stacking a second assertion on the same defect adds
   noise, not information.

Determinism: seeded ``numpy.random.default_rng`` per regime; no global RNG
state. PYTHONHASHSEED=0 is asserted by the tier-1 conftest.

Outcome protocol (registered): if a firing-regime assertion goes red on
current production code, the row lands as a STRICT xfail naming a findings
document, per the in-repo precedent ``tests/test_aggregation_calibration.py``,
and the repair is filed as its own ticket. The bound is not loosened.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.aggregation.fit import (
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    fit_skill,
)

SEED: int = 20260902
K_CLAUSES: int = 200
R_REPLICATES: int = 50
CONC_REL_TOL: float = 0.25
MEAN_ABS_TOL: float = 0.03
DECISION_FLIP_TOL: float = 0.02

PASS_P: float = 0.95
FAIL_P: float = 0.05


@dataclass(frozen=True)
class Regime:
    name: str
    mu_true: float
    conc_true: float
    n_trials: int
    predicted_deflation: float  # analytic n / (n + c* + 1), recorded for the report


REGIMES: dict[str, Regime] = {
    "small_n_bite": Regime("small_n_bite", 0.65, 20.0, 10, 10 / 31),
    "low_heterogeneity": Regime("low_heterogeneity", 0.65, 100.0, 25, 25 / 126),
    "benign_large_n": Regime("benign_large_n", 0.65, 10.0, 100, 100 / 111),
}


@dataclass(frozen=True)
class RegimeMeasurement:
    mean_mu_hat: float
    mean_conc_hat: float
    ebmom_replicates: int
    decision_flip_rate: float


def _decision(p_win: float) -> str:
    if p_win >= PASS_P:
        return "PASS"
    if p_win <= FAIL_P:
        return "FAIL"
    return "UNDECIDED"


def _measure_regime(regime: Regime) -> RegimeMeasurement:
    """Fit R replicates of hierarchical data drawn from the regime's truth."""
    rng = np.random.default_rng(SEED + regime.n_trials)
    a_true = regime.mu_true * regime.conc_true
    b_true = (1.0 - regime.mu_true) * regime.conc_true

    mu_hats: list[float] = []
    conc_hats: list[float] = []
    flips = 0
    decisions = 0
    ebmom_count = 0

    for _ in range(R_REPLICATES):
        p_k = rng.beta(a_true, b_true, size=K_CLAUSES)
        w_k = rng.binomial(regime.n_trials, p_k)
        clauses = [
            ClauseObservations(clause_id=f"c{i}", w=float(w), n=regime.n_trials)
            for i, w in enumerate(w_k)
        ]
        result = fit_skill(clauses)
        if result.aggregation_method != "ebmom_hierarchical":
            # A fallback replicate carries no recovered hyperprior; count and skip.
            continue
        ebmom_count += 1
        alpha_hat = float(result.aggregation_provenance["alpha_hat"])  # type: ignore[arg-type]
        beta_hat = float(result.aggregation_provenance["beta_hat"])  # type: ignore[arg-type]
        conc_hat = alpha_hat + beta_hat
        mu_hats.append(alpha_hat / conc_hat)
        conc_hats.append(conc_hat)

        for posterior, w in zip(result.posteriors, w_k, strict=True):
            oracle_p = float(
                beta_dist.sf(
                    WIN_RATE_THRESHOLD,
                    a_true + float(w),
                    b_true + (regime.n_trials - float(w)),
                )
            )
            decisions += 1
            if _decision(posterior.p_win_gt_threshold) != _decision(oracle_p):
                flips += 1

    if ebmom_count == 0:
        pytest.fail(
            f"EBMOM_PATH_NEVER_TAKEN: no replicate in regime {regime.name!r} reached"
            f" the hierarchical fit; the regime cannot measure recovery at all."
        )
    return RegimeMeasurement(
        mean_mu_hat=float(np.mean(mu_hats)),
        mean_conc_hat=float(np.mean(conc_hats)),
        ebmom_replicates=ebmom_count,
        decision_flip_rate=flips / decisions if decisions else 0.0,
    )


def _recovery_report(regime: Regime, m: RegimeMeasurement) -> str:
    return (
        f"regime={regime.name} truth(mu*={regime.mu_true}, c*={regime.conc_true},"
        f" n={regime.n_trials}) recovered(mean mu_hat={m.mean_mu_hat:.4f},"
        f" mean c_hat={m.mean_conc_hat:.2f}) predicted_deflation~="
        f"{regime.predicted_deflation:.2f} ebmom_replicates={m.ebmom_replicates}/"
        f"{R_REPLICATES} decision_flip_rate={m.decision_flip_rate:.4f}"
    )


@pytest.fixture(scope="module")
def measurements() -> dict[str, RegimeMeasurement]:
    return {name: _measure_regime(regime) for name, regime in REGIMES.items()}


@pytest.mark.parametrize("name", list(REGIMES))
def test_mean_recovery(name: str, measurements: dict[str, RegimeMeasurement]) -> None:
    """The recovered hyperprior mean sits within MEAN_ABS_TOL of truth, every regime."""
    regime, m = REGIMES[name], measurements[name]
    assert abs(m.mean_mu_hat - regime.mu_true) <= MEAN_ABS_TOL, (
        f"EBMOM_MEAN_RECOVERY_BIASED: |{m.mean_mu_hat:.4f} - {regime.mu_true}| >"
        f" {MEAN_ABS_TOL}. The moment map does not even recover the hyperprior"
        f" mean it was given. {_recovery_report(regime, m)}"
    )


# Observed on first run (2026-08-31, seed 20260902): the two predicted-firing
# regimes went red at relative errors 0.690 and 0.806 with decision flip rates
# 0.1186 and 0.0816. Strict xfail per the registered outcome protocol; the
# bound is NOT loosened. The repair un-marks these in the same change it lands.
_FIRING_REGIMES: frozenset[str] = frozenset({"small_n_bite", "low_heterogeneity"})


def _concentration_params() -> list[object]:
    params: list[object] = []
    for name in REGIMES:
        marks = []
        if name in _FIRING_REGIMES:
            marks.append(
                pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "finding: docs/findings/ebmom-missing-sampling-variance-peel.md "
                        f"(regime {name!r}; severity WRONG_NUMBER; no binomial "
                        "sampling-variance peel before the moment inversion)"
                    ),
                )
            )
        params.append(pytest.param(name, marks=marks))
    return params


@pytest.mark.parametrize("name", _concentration_params())
def test_concentration_recovery(name: str, measurements: dict[str, RegimeMeasurement]) -> None:
    """The recovered concentration sits within CONC_REL_TOL of truth.

    This is the assertion the missing sampling-variance peel violates where it
    bites (see the module docstring's regime predictions).
    """
    regime, m = REGIMES[name], measurements[name]
    rel_err = abs(m.mean_conc_hat - regime.conc_true) / regime.conc_true
    assert rel_err <= CONC_REL_TOL, (
        f"EBMOM_CONCENTRATION_NOT_RECOVERED: relative error {rel_err:.3f} >"
        f" {CONC_REL_TOL} against the known hyperprior. The moment inversion"
        f" treats sampling noise in w/n as true heterogeneity (no binomial"
        f" variance peel), so shrinkage strength is wrong and the locked"
        f" 0.95/0.05 decisions are computed from a hyperprior the data did not"
        f" imply. {_recovery_report(regime, m)}"
    )


def test_decision_flips_benign_regime(measurements: dict[str, RegimeMeasurement]) -> None:
    """In the benign regime, fitted-vs-oracle decision flips stay within budget."""
    regime, m = REGIMES["benign_large_n"], measurements["benign_large_n"]
    assert m.decision_flip_rate <= DECISION_FLIP_TOL, (
        f"EBMOM_DECISIONS_NOT_REPRODUCIBLE: decision flip rate"
        f" {m.decision_flip_rate:.4f} > {DECISION_FLIP_TOL} in the regime where"
        f" concentration recovery is within tolerance; the fitted posterior"
        f" moves clauses across the locked PASS/FAIL thresholds relative to the"
        f" true-hyperprior posterior. {_recovery_report(regime, m)}"
    )
