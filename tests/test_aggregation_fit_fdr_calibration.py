"""Null-world FDR calibration of the BH-FDR fallback (falsification plan item 1, #343).

Registered condition (docs/assurance/falsification-plan.md item 1): when EB-MoM
fails to converge, ``fit_skill`` builds ``p_values = [1.0 - p_exceeds]`` from the
Bayesian posterior mass ``P(rate > 0.60 | data)`` and hands the list to
Benjamini-Hochberg at ``q = BH_FDR_Q``. BH assumes valid null p-values --
super-uniform on [0, 1] under the null. If the transform is not that, the
realised false-discovery rate among declared passes can exceed the nominal q,
and a false PASS crosses the locked 0.95 gate and mints KEEP.

PRE-REGISTRATION -- written before any simulation was run, per #343.

Null hypothesis simulated
-------------------------
The composite null is ``rate <= WIN_RATE_THRESHOLD`` (0.60). The bound below is
written against the BOUNDARY case ``rate = 0.60`` exactly, which is the least
favourable point of the composite null for a one-sided exceedance statistic:
``P(rate > 0.60 | data)`` is stochastically largest there, so any interior null
rate produces a lower realised FDR. Clause outcomes are pure wins/losses
(``w ~ Binomial(n, 0.60)``); ties enter production ``w`` at half-weight but the
transform under test consumes only ``(w, n)``, and a tie-including ``w`` at the
same true rate is a strictly less dispersed statistic, again less favourable to
discovery than the binomial worst case.

Every simulated clause is null, so every declared pass is a false discovery
(V = R) and FDR = E[V / max(R, 1)] reduces to P(at least one declared pass).
The empirical FDR is the fraction of simulated skills whose ``bh_fdr_passes``
is non-empty.

Reaching the production branch
------------------------------
``_ebmom`` is monkeypatched to raise ``ConvergenceFailure`` so that every
simulated skill takes the real fallback branch inside the real ``fit_skill``:
the posterior construction, the ``1.0 - p`` inversion, and the ``_bh_fdr`` call
executed are the production lines in ``aggregation/fit.py``. Forcing the
trigger rather than engineering natural convergence failures avoids
conditioning the null distribution on the failure event; validity of the
p-value transform is an unconditional property of the transform.

Design sweep
------------
Item 3 (#345) showed that an argument conducted at a single design can conclude
agreement the sweep refutes. Three designs are measured:
``(K clauses, n trials)`` in ``(10, 10), (20, 50), (40, 25)`` -- small/discrete,
the documented-typical shape, and many-small-clauses.

The bound, justified from both ends BEFORE observing the result
---------------------------------------------------------------
``FDR_BOUND = 0.070`` per design, with ``N_SIMS = 1500`` per design.

From below (must not flag a calibrated procedure): under a true FDR at the
nominal q = 0.05, the Monte-Carlo standard error of the empirical proportion is
sqrt(0.05 * 0.95 / 1500) = 0.00563. The bound sits 3.5 standard errors above
q (0.05 + 3.5 * 0.00563 = 0.0697, rounded up to 0.070), so a genuinely
calibrated fallback trips it with probability ~2e-4 per design (~7e-4 across
the three-design family, normal approximation).

From above (must catch material miscalibration): the materiality line is a
DOUBLING of the promised guarantee, true FDR >= 2q = 0.10 -- at that point the
gate's stated false-discovery budget is off by 2x and a minted KEEP's receipt
overstates its own reliability materially. Against true FDR = 0.10 the test's
power is P(N(0.10, sqrt(0.10*0.90/1500)) > 0.070) ~ 0.9999 per design.

A bound that could not be justified from both ends would mean the detector is
not yet designed; a bound fitted to the observed measurement measures nothing.

Determinism: seeded ``numpy.random.default_rng(SEED)`` per test; no reliance on
global RNG state. PYTHONHASHSEED=0 is asserted by the tier-1 conftest.

Controls
--------
- ``test_harness_control_uniform_pvalues_calibrated``: genuine Uniform(0,1)
  p-values through the production ``_bh_fdr`` must stay under the same bound --
  the negative control proving the bound is not trivially trippable.
- ``test_harness_fires_on_anticonservative_input``: anti-conservative
  pseudo-p-values (U^2) through the production ``_bh_fdr`` must EXCEED the
  bound (pre-registered expectation >= 0.5) -- the fixture proving the detector
  goes red on the condition it registers (an input that is not a null p-value).
"""

from __future__ import annotations

import numpy as np
import pytest

from skill_harness.aggregation import fit as fit_module
from skill_harness.aggregation.errors import ConvergenceFailure
from skill_harness.aggregation.fit import (
    BH_FDR_Q,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    _bh_fdr,
    fit_skill,
)

SEED: int = 20260901
N_SIMS: int = 1500
FDR_BOUND: float = 0.070
NULL_RATE: float = WIN_RATE_THRESHOLD  # boundary case of the composite null rate <= 0.60

# (K clauses, n trials per clause). K >= K_MIN_FOR_EB so the K-gate is not taken.
DESIGNS: tuple[tuple[int, int], ...] = ((10, 10), (20, 50), (40, 25))


def _force_convergence_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route every fit_skill call through the production BH-FDR fallback branch."""

    def _raise(sample_mean: float, sample_var: float) -> tuple[float, float]:
        raise ConvergenceFailure(
            reason="alpha_le_zero",
            alpha_hat=-1.0,
            beta_hat=1.0,
            sample_mean=sample_mean,
            sample_var=sample_var,
        )

    monkeypatch.setattr(fit_module, "_ebmom", _raise)


def _empirical_null_fdr(k_clauses: int, n_trials: int, rng: np.random.Generator) -> float:
    """Fraction of null-world skills where the production fallback declares >= 1 pass."""
    skills_with_false_discovery = 0
    for _ in range(N_SIMS):
        wins = rng.binomial(n_trials, NULL_RATE, size=k_clauses)
        clauses = [
            ClauseObservations.bernoulli(clause_id=f"c{i}", w=float(w), n=n_trials)
            for i, w in enumerate(wins)
        ]
        result = fit_skill(clauses)
        assert result.aggregation_method == "bh_fdr_fallback", (
            f"simulation must take the fallback branch, got {result.aggregation_method!r}"
        )
        if result.bh_fdr_passes:
            skills_with_false_discovery += 1
    return skills_with_false_discovery / N_SIMS


@pytest.mark.parametrize(("k_clauses", "n_trials"), DESIGNS)
def test_null_world_fdr_within_nominal_q(
    k_clauses: int, n_trials: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Realised null-world FDR of the production fallback stays within the bound.

    The null, the boundary-case choice, N_SIMS, and FDR_BOUND (justified from
    both ends) are pre-registered in the module docstring.
    """
    _force_convergence_failure(monkeypatch)
    rng = np.random.default_rng(SEED + k_clauses)  # distinct, fixed stream per design
    fdr = _empirical_null_fdr(k_clauses, n_trials, rng)
    assert fdr <= FDR_BOUND, (
        f"NULL_WORLD_FDR_EXCEEDS_NOMINAL: realised FDR {fdr:.4f} > bound {FDR_BOUND}"
        f" (nominal q={BH_FDR_Q}) at design K={k_clauses}, n={n_trials}."
        f" The quantity fit_skill feeds to _bh_fdr (1 - posterior mass) is not"
        f" behaving as a valid null p-value: false PASSes cross the locked 0.95"
        f" gate more often than the q it promises."
    )


def _any_pass_rate(p_matrix: np.ndarray) -> float:
    """Fraction of rows where the production _bh_fdr declares >= 1 pass at BH_FDR_Q."""
    hits = 0
    for row in p_matrix:
        if _bh_fdr([float(p) for p in row], BH_FDR_Q):
            hits += 1
    return hits / len(p_matrix)


def test_harness_control_uniform_pvalues_calibrated() -> None:
    """Negative control: genuine Uniform(0,1) p-values stay under the same bound.

    Proves the metric-plus-bound machinery does not flag a calibrated input.
    Pre-registered: same FDR_BOUND, same N_SIMS, k=20.
    """
    rng = np.random.default_rng(SEED)
    p_matrix = rng.uniform(size=(N_SIMS, 20))
    rate = _any_pass_rate(p_matrix)
    assert rate <= FDR_BOUND, (
        f"HARNESS_CONTROL_MISCALIBRATED: uniform p-values yield any-pass rate"
        f" {rate:.4f} > bound {FDR_BOUND}; the harness or bound is wrong and the"
        f" detector's verdicts cannot be trusted either way."
    )


def test_harness_fires_on_anticonservative_input() -> None:
    """Red-on-condition fixture: a non-p-value input must trip the detector's bound.

    U^2 for U ~ Uniform(0,1) is anti-conservative (mass piles toward 0).
    Pre-registered expectation: any-pass rate >= 0.5 at k=20 -- far beyond
    FDR_BOUND -- because P(min of 20 U <= sqrt(q/k)) alone exceeds 0.6.
    """
    rng = np.random.default_rng(SEED)
    p_matrix = rng.uniform(size=(N_SIMS, 20)) ** 2
    rate = _any_pass_rate(p_matrix)
    assert rate > FDR_BOUND, (
        f"DETECTOR_BLIND_TO_NON_PVALUE: anti-conservative input yields any-pass"
        f" rate {rate:.4f} <= bound {FDR_BOUND}; the detector cannot see the"
        f" condition it registers."
    )
    assert rate >= 0.5, (
        f"DETECTOR_SENSITIVITY_BELOW_REGISTRATION: any-pass rate {rate:.4f} < 0.5"
        f" against U^2 input; pre-registered sensitivity floor not met."
    )
