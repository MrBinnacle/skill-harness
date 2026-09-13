"""Null-world FDR calibration of the retired BH-FDR transform (falsification item 1, #343).

Registered condition (docs/assurance/falsification-plan.md item 1): when EB-MoM
failed to converge, ``fit_skill`` built ``p_values = [1.0 - p_exceeds]`` from the
Bayesian posterior mass ``P(rate > 0.60 | data)`` and handed the list to
Benjamini-Hochberg at ``q = BH_FDR_Q``. BH assumes valid null p-values --
super-uniform on [0, 1] under the null. If the transform is not that, the
realised false-discovery rate among declared passes can exceed the nominal q.

The past tense is load-bearing. ``fit_skill`` stopped making that call on
2026-09-05; see the section below and item 1 of the plan.

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

Reaching the transform
----------------------
Until 2026-09-05 this section read "Reaching the production branch", and
``_ebmom`` was monkeypatched to raise ``ConvergenceFailure`` so every simulated
skill took the real fallback branch inside the real ``fit_skill``.

Pre-registration v2 section 3 (FROZEN 2026-09-05) retired BH-FDR on that
branch: a refused fit now pools at the admission bound and publishes no FDR
selection, so forcing the failure reaches bounded pooling and ``bh_fdr_passes``
is None. The old harness would have measured a realised FDR of zero on every
design and passed for the wrong reason -- a detector satisfied by the absence
of the thing it watches.

The transform is therefore driven directly: ``_build_unpooled_posteriors``,
their ``P(rate > 0.60)``, the ``1.0 - p`` inversion and ``_bh_fdr``, all
production functions in ``aggregation/fit.py``. Forcing the trigger rather than
engineering natural convergence failures avoided conditioning the null
distribution on the failure event; validity of the p-value transform is an
unconditional property of the transform, which is why the measurement survives
the loss of the caller.

What was LOST, stated plainly: the registered condition no longer ends in a
false PASS, because no production path consumes ``_bh_fdr``. The damage clause
of falsification-plan item 1 is therefore no longer live, and the row records
that. What is retained is the measurement that would have to be re-read before
any caller is added back.

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

from skill_harness.aggregation.fit import (
    BH_FDR_Q,
    WIN_RATE_THRESHOLD,
    ClauseObservations,
    _bh_fdr,
    _build_unpooled_posteriors,
)

SEED: int = 20260901
N_SIMS: int = 1500
FDR_BOUND: float = 0.070
NULL_RATE: float = WIN_RATE_THRESHOLD  # boundary case of the composite null rate <= 0.60

# (K clauses, n trials per clause). K >= K_MIN_FOR_EB so the K-gate is not taken.
DESIGNS: tuple[tuple[int, int], ...] = ((10, 10), (20, 50), (40, 25))


def _null_world_transform_pvalues(
    k_clauses: int, n_trials: int, rng: np.random.Generator
) -> list[list[float]]:
    """One p-vector per simulated null-world skill, through the real transform.

    The transform is the production one, line for line: the unpooled posteriors
    _build_unpooled_posteriors returns, their P(rate > 0.60), and the 1 - p
    inversion. What is no longer available is a production CALLER for it.
    Pre-registration v2 section 3 (FROZEN 2026-09-05) retired BH-FDR on the
    refused path, so fit_skill pools at the admission bound and publishes no
    FDR selection; forcing a ConvergenceFailure now reaches bounded pooling,
    not this transform.

    That is a real weakening of this detector and it is recorded rather than
    hidden. Under #341 the honest states for a registered row are "the detector
    exists and fires" or "REGISTERED WITHOUT DETECTOR, with the reason". This
    row keeps the first state for the transform and loses the claim that the
    transform is on a production path: the condition it registers can no longer
    reach a KEEP, because nothing downstream consumes the result. The row in
    docs/assurance/falsification-plan.md says so.
    """
    vectors: list[list[float]] = []
    for _ in range(N_SIMS):
        wins = rng.binomial(n_trials, NULL_RATE, size=k_clauses)
        clauses = [
            ClauseObservations.bernoulli(clause_id=f"c{i}", w=float(w), n=n_trials)
            for i, w in enumerate(wins)
        ]
        posteriors = _build_unpooled_posteriors(clauses)
        vectors.append([1.0 - post.p_win_gt_threshold for post in posteriors])
    return vectors


def _empirical_null_fdr(k_clauses: int, n_trials: int, rng: np.random.Generator) -> float:
    """Fraction of null-world skills where the transform declares >= 1 pass."""
    vectors = _null_world_transform_pvalues(k_clauses, n_trials, rng)
    return sum(1 for p_values in vectors if _bh_fdr(p_values, BH_FDR_Q)) / len(vectors)


@pytest.mark.parametrize(("k_clauses", "n_trials"), DESIGNS)
def test_null_world_fdr_within_nominal_q(k_clauses: int, n_trials: int) -> None:
    """Realised null-world FDR of the transform stays within the bound.

    The null, the boundary-case choice, N_SIMS, and FDR_BOUND (justified from
    both ends) are pre-registered in the module docstring and are unchanged.
    What changed is where the transform is reached from: v2 section 3 retired
    its production caller, so the posteriors and the inversion are driven
    directly rather than through a forced ConvergenceFailure inside fit_skill.
    """
    rng = np.random.default_rng(SEED + k_clauses)  # distinct, fixed stream per design
    fdr = _empirical_null_fdr(k_clauses, n_trials, rng)
    assert fdr <= FDR_BOUND, (
        f"NULL_WORLD_FDR_EXCEEDS_NOMINAL: realised FDR {fdr:.4f} > bound {FDR_BOUND}"
        f" (nominal q={BH_FDR_Q}) at design K={k_clauses}, n={n_trials}."
        f" The quantity fed to _bh_fdr (1 - posterior mass) is not behaving as a"
        f" valid null p-value. No production path consumes it since v2 section 3,"
        f" so this no longer implies a false PASS; it does mean the transform must"
        f" not be given a caller again in this state."
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
