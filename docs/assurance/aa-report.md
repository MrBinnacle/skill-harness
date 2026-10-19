# Assurance pass — aggregation A/A (negative-control) report (#163)

Parent: assurance-pass spec (#160). Sibling baseline: Phase 0 falsification
plan (#162). Sibling differential: #165 / `differential-report.md`.

This document records the **false-positive rate** of the two-arm posterior
difference gate (`two_arm_gate` in `src/skill_harness/aggregation/two_arm.py`)
under an offline A/A design: 500 seeded paired runs where both arms are drawn
from the **same** Bernoulli process, so any directional call is a false
positive by construction. The harness lives in
`tests/test_aggregation_aa.py`.

Hard constraint (work order): **if the rate falls outside binomial tolerance,
do not retune thresholds or aggregation math.** File a finding under
`docs/findings/` with severity `WRONG_NUMBER`, seed, and counts; mark the
assertion `@pytest.mark.xfail(strict=True, …)` pointing at that finding.

---

## Method

| Item | Value |
| --- | --- |
| Paired runs (N) | **500** |
| Master seed | `163_2026_08_09` (`numpy.random.default_rng`) |
| Null process | Identical arms, Bernoulli(`p=0.5`), no ties |
| Observation loop | Production sequential stopper: `BetaBinomialAccumulator.add` → `check_stop` / `next_check_at` (`N_MIN=8`, `N_INC=4`, `N_MAX=40`), mirroring `ablation/runner.py` |
| Gate | `two_arm_gate(..., delta=0.1, prob_threshold=0.95)` (DIF K7 constants used by the existing two-arm suite) |
| False positive | `outcome ∈ {treatment_better, treatment_worse}` |
| Network | Fully offline (`pytest-socket` autouse in the test module) |

### Why sequential, not fixed-n

Production never collects fixed-n samples: the runner drives sampling through
the Beta-Binomial sequential test. False-positive rates under repeated
posterior peeks are not the same as fixed-n rates, and stopped sums are biased
estimators of the underlying rate. This harness therefore generates each arm
**through** `check_stop()`, and records the `StoppingReason` distribution.

### Engine entry (`aggregate_skill`)

`aggregate_skill` (`engine.py`) is a pure DB orchestrator: it pools already-
written admissible verdicts and delegates interval/rate numerics to `fit_skill`
/ status. It does not own a two-arm significance threshold. The A/A estimand
for this ticket is the two-arm gate's directional false-positive rate under
identical arms. The sequential stopper and `two_arm_gate` both use the package's
standing Beta(1,1) posterior convention.

---

## Tolerance arithmetic

Registered significance threshold: `prob_threshold = 0.95`.

Nominal Type-I rate under a calibrated two-sided directional gate:

```text
α = 1 − prob_threshold = 0.05
```

Under the model `X ~ Binomial(N=500, α=0.05)`, the acceptance band is the
**central 95% probability mass** of that binomial (exact inverse CDF via
`scipy.stats.binom.ppf`):

```text
lo = binom.ppf(0.025, n=500, p=0.05) = 16
hi = binom.ppf(0.975, n=500, p=0.05) = 35
E[X] = 500 × 0.05 = 25
```

Assert `lo ≤ X ≤ hi`. This checks that the Monte-Carlo FPR sits near nominal;
it is not a claim that the Bayesian gate is a frequentist level-α test at every
`(n, δ)`.

---

## Measured results (seed `163_2026_08_09`)

| Quantity | Value |
| --- | --- |
| False-positive count `X` | **26** |
| False-positive rate `X/N` | **0.052** (5.2%) |
| Nominal α | 0.05 |
| Tolerance band on count | **[16, 35]** |
| Result | **INSIDE** tolerance |

### Outcome breakdown (500 pairs)

| `TwoArmOutcome` | Count |
| --- | --- |
| `null` | 474 |
| `treatment_better` | 12 |
| `treatment_worse` | 14 |
| **Directional (FP)** | **26** |

### `StoppingReason` distribution (1000 arms = 500 pairs × 2)

| `StoppingReason` | Count |
| --- | --- |
| `failed` | 517 |
| `underpowered_nmax` | 462 |
| `passed` | 21 |
| `budget_exhausted` | 0 |

Under Bernoulli(0.5) the pass rule `P(rate > 0.60) ≥ 0.95` is rarely reached
before `N_MAX`; most arms stop `failed` early or hit `underpowered_nmax`. That
is expected for a null-centered process and is recorded here so a future
re-run can detect drift in the stopper schedule itself.

---

## Findings

None. `X = 26 ∈ [16, 35]`. No `xfail` markers. No production thresholds or
aggregation math were changed.

If a future run disagrees:

1. Do **not** widen the band or retune `delta` / `prob_threshold` / stopper constants.  
2. File `docs/findings/` with severity `WRONG_NUMBER`, seed, `X`, band, and
   `StoppingReason` histogram.  
3. Mark the FPR assertion
   `@pytest.mark.xfail(strict=True, reason="finding: …")`.

---

## How to re-run

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_aa.py -q
```
