# Assurance pass — aggregation coverage calibration report (#164)

Parent: assurance-pass spec (#160). Sibling baseline: Phase 0 falsification
plan (#162). Sibling A/A: #163 / `aa-report.md`. Sibling differential: #165 /
`differential-report.md`.

This document records **frequentist coverage** of the aggregation pipeline's
95% credible intervals under an offline planted-effect design: 500 seeded
replications at each of three planted clause win-rates (null / small / large),
with observations collected through the production sequential stopper. The
harness lives in `tests/test_aggregation_calibration.py`.

Hard constraint (work order): **if coverage falls outside binomial tolerance,
do not retune thresholds or aggregation math.** File a finding under
`docs/findings/` with severity `WRONG_NUMBER`, seed, and counts; mark the
failing grid point `@pytest.mark.xfail(strict=True, …)` pointing at that
finding.

---

## Method

| Item | Value |
| --- | --- |
| Replications per grid point (N) | **500** |
| Master seed | `164_2026_08_09` (`numpy.random.default_rng`; child seed = master + grid index) |
| Planted-effect grid | `null` p=**0.50**, `small` p=**0.65**, `large` p=**0.85** (Bernoulli, no ties) |
| Observation loop | Production sequential stopper: `BetaBinomialAccumulator.add` → `check_stop` / `next_check_at` (`N_MIN=8`, `N_INC=4`, `N_MAX=40`), mirroring `ablation/runner.py` |
| Interval | `fit_skill` unpooled Beta(1+w, 1+n−w) equal-tailed 95% CI (`credible_interval_lo/hi`) — the interval `engine.aggregate_skill` surfaces |
| Coverage event | `lo ≤ planted_p ≤ hi` |
| Two-arm side-channel | `two_arm_gate(planted, control@0.5, delta=0.1, prob_threshold=0.95)` per replication (pipeline exercise; not the coverage estimand) |
| Network | Fully offline (`pytest-socket` autouse in the test module) |

### Why sequential, not fixed-n

Production never collects fixed-n samples: the runner drives sampling through
the Beta-Binomial sequential test. Interval coverage computed over fixed-n
replications does not transfer to data collected under sequential stopping —
stopped sums are biased estimators of the underlying rate. This harness
therefore generates each planted arm **through** `check_stop()`, and records
the `StoppingReason` distribution per grid point.

### Engine entry (`aggregate_skill`)

`aggregate_skill` (`engine.py`) is a pure DB orchestrator: it pools already-
written admissible verdicts and delegates interval numerics to `fit_skill`.
The coverage estimand for this ticket is therefore the `fit_skill` 95% CI
under sequential collection. `two_arm_gate` is exercised as a side-channel on
the same draws (directional posterior mass, not a CI).

---

## Tolerance arithmetic

Nominal coverage under a calibrated 95% interval:

```text
π = 0.95
```

Under the model `X ~ Binomial(N=500, π=0.95)`, the acceptance band is the
**central 95% probability mass** of that binomial (exact inverse CDF via
`scipy.stats.binom.ppf`):

```text
lo = binom.ppf(0.025, n=500, p=0.95) = 465
hi = binom.ppf(0.975, n=500, p=0.95) = 484
E[X] = 500 × 0.95 = 475
```

Assert `lo ≤ X ≤ hi` **per grid point**.

---

## Coverage table (seed `164_2026_08_09` + grid index)

| Grid | Planted `p` | Seed | Coverage count `X` | Rate `X/N` | Band | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `null` | 0.50 | `16420260809` | **470** | 0.940 | [465, 484] | **INSIDE** |
| `small` | 0.65 | `16420260810` | **441** | 0.882 | [465, 484] | **BELOW** (finding) |
| `large` | 0.85 | `16420260811` | **491** | 0.982 | [465, 484] | **ABOVE** (finding) |

---

## `StoppingReason` distribution per grid point (planted arm only, N=500)

### `null` (p=0.50)

| `StoppingReason` | Count |
| --- | --- |
| `underpowered_nmax` | 252 |
| `failed` | 240 |
| `passed` | 8 |
| `budget_exhausted` | 0 |

Mean stopped `n` (planted arm): **29.24**

### `small` (p=0.65)

| `StoppingReason` | Count |
| --- | --- |
| `underpowered_nmax` | 327 |
| `passed` | 139 |
| `failed` | 34 |
| `budget_exhausted` | 0 |

Mean stopped `n` (planted arm): **32.95**

### `large` (p=0.85)

| `StoppingReason` | Count |
| --- | --- |
| `passed` | 491 |
| `underpowered_nmax` | 9 |
| `failed` | 0 |
| `budget_exhausted` | 0 |

Mean stopped `n` (planted arm): **15.33**

Under Bernoulli(0.85) the pass rule `P(rate > 0.60) ≥ 0.95` fires early on
almost every replication — optional stopping is most aggressive on the large
grid point, which is also where coverage overshoots the upper band.

---

## Two-arm side-channel (`two_arm_gate` outcomes, 500 pairs each)

Control arm always Bernoulli(0.50). Not a coverage estimand; recorded so a
future re-run can detect drift in the two-arm gate under the same seeds.

| Grid | `null` | `treatment_better` | `treatment_worse` |
| --- | --- | --- | --- |
| `null` (p_t=0.50) | 486 | 7 | 7 |
| `small` (p_t=0.65) | 395 | 105 | 0 |
| `large` (p_t=0.85) | 170 | 330 | 0 |

---

## Findings

See `docs/findings/aggregation-ci-coverage-under-sequential-stop.md`
(severity `WRONG_NUMBER`).

- `small` and `large` are `@pytest.mark.xfail(strict=True)` with a pointer to
  that finding.
- `null` remains a hard assert (inside band at this seed).
- **No production thresholds or aggregation math were changed.**

If a future run disagrees:

1. Do **not** widen the band or retune `fit_skill` / stopper constants.  
2. Update the finding with the new seed, `X`, band, and `StoppingReason`
   histogram.  
3. Adjust xfail markers only to match measured misses (strict xfail).

---

## How to re-run

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_calibration.py -q
```
