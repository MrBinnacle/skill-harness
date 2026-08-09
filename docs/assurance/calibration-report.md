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
  that finding — **legacy posterior interval only**.
- `null` remains a hard assert (inside band at this seed).
- **Locked stopper constants and the posterior decision rule were not changed.**
- **#187 fix:** production report surface adds an anytime-valid predictable-plugin
  betting confidence sequence (`predictable_plugin_betting_cs_v1`) beside the
  posterior interval. Only the CS may carry a frequentist coverage claim.
  Finding status: **closed**.

If a future *legacy posterior* run disagrees:

1. Do **not** widen the band or retune `fit_skill` / stopper constants.  
2. Update the finding with the new seed, `X`, band, and `StoppingReason`
   histogram.  
3. Adjust xfail markers only to match measured misses (strict xfail) on the
   legacy characterization — never on the production CS.

---

## #187 anytime-valid confidence sequence (production interval)

| Item | Value |
| --- | --- |
| Method id | `predictable_plugin_betting_cs_v1` |
| Construction | Waudby-Smith & Ramdas hedged capital + predictable plug-in λ (JRSS-B 2024 / arXiv:2010.09686) |
| Module | `src/skill_harness/aggregation/confidence_sequence.py` |
| Harness | `tests/test_aggregation_cs_calibration.py` (`pytest -m calibration`) |
| Master seed | `187_2026_08_09` (child seed = master + flat grid index) |
| Grid | p ∈ {0.05, 0.25, 0.50, 0.58, 0.60, 0.62, 0.65, 0.75, 0.85, 0.95} × tie rates {0%, 20%, 50%} |
| Contract | coverage count ≥ 465 / 500 (binom lower edge); **overcoverage is not a failure** |
| Width metrics | median width and 90th-percentile width recorded per cell (never used to reject valid overcoverage) |
| Incomparable pools | `interval_status=UNMEASURED_INCOMPARABLE_POOL`, sequence field null |

### Coverage + width table (seed `187_2026_08_09`, N=500)

Estimand is the observation mean under the DGP
`X = 0.5` w.p. `tie_rate`, else `Bern(p)`, i.e.
`mu = tie_rate * 0.5 + (1 - tie_rate) * p`. Lower coverage tolerance = 465.
Overcoverage is not a failure. Wall clock for one full dense grid on linux
py3.13 ≈ **199 s** (~6.6 s/cell); determinism recompute doubles that. Slowest
cell ≈ 7 s. Windows budget at 2× ≈ 14 min — inside the dedicated calibration
job's 40-minute timeout.

| label | p | tie | X | rate | med_w | p90_w | mean_n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| p0.05_tie00 | 0.05 | 0.00 | 498 | 0.996 | 0.540 | 0.635 | 8.0 |
| p0.25_tie00 | 0.25 | 0.00 | 495 | 0.990 | 0.662 | 0.763 | 10.4 |
| p0.50_tie00 | 0.50 | 0.00 | 499 | 0.998 | 0.475 | 0.732 | 28.6 |
| p0.58_tie00 | 0.58 | 0.00 | 499 | 0.998 | 0.455 | 0.647 | 33.6 |
| p0.60_tie00 | 0.60 | 0.00 | 500 | 1.000 | 0.452 | 0.543 | 34.8 |
| p0.62_tie00 | 0.62 | 0.00 | 499 | 0.998 | 0.449 | 0.540 | 34.7 |
| p0.65_tie00 | 0.65 | 0.00 | 499 | 0.998 | 0.448 | 0.540 | 33.2 |
| p0.75_tie00 | 0.75 | 0.00 | 499 | 0.998 | 0.466 | 0.540 | 24.5 |
| p0.85_tie00 | 0.85 | 0.00 | 499 | 0.998 | 0.510 | 0.540 | 14.8 |
| p0.95_tie00 | 0.95 | 0.00 | 500 | 1.000 | 0.540 | 0.540 | 9.8 |
| p0.05_tie20 | 0.05 | 0.20 | 499 | 0.998 | 0.607 | 0.669 | 8.4 |
| p0.25_tie20 | 0.25 | 0.20 | 499 | 0.998 | 0.635 | 0.703 | 12.6 |
| p0.50_tie20 | 0.50 | 0.20 | 498 | 0.996 | 0.423 | 0.634 | 32.2 |
| p0.58_tie20 | 0.58 | 0.20 | 499 | 0.998 | 0.404 | 0.540 | 35.8 |
| p0.60_tie20 | 0.60 | 0.20 | 500 | 1.000 | 0.406 | 0.511 | 35.8 |
| p0.62_tie20 | 0.62 | 0.20 | 500 | 1.000 | 0.402 | 0.503 | 36.4 |
| p0.65_tie20 | 0.65 | 0.20 | 500 | 1.000 | 0.396 | 0.490 | 35.7 |
| p0.75_tie20 | 0.75 | 0.20 | 499 | 0.998 | 0.395 | 0.508 | 31.7 |
| p0.85_tie20 | 0.85 | 0.20 | 498 | 0.996 | 0.443 | 0.540 | 22.5 |
| p0.95_tie20 | 0.95 | 0.20 | 499 | 0.998 | 0.503 | 0.574 | 13.3 |
| p0.05_tie50 | 0.05 | 0.50 | 499 | 0.998 | 0.599 | 0.668 | 10.7 |
| p0.25_tie50 | 0.25 | 0.50 | 499 | 0.998 | 0.481 | 0.650 | 17.9 |
| p0.50_tie50 | 0.50 | 0.50 | 499 | 0.998 | 0.340 | 0.527 | 33.1 |
| p0.58_tie50 | 0.58 | 0.50 | 498 | 0.996 | 0.326 | 0.409 | 36.8 |
| p0.60_tie50 | 0.60 | 0.50 | 499 | 0.998 | 0.321 | 0.414 | 36.9 |
| p0.62_tie50 | 0.62 | 0.50 | 496 | 0.992 | 0.322 | 0.375 | 38.0 |
| p0.65_tie50 | 0.65 | 0.50 | 500 | 1.000 | 0.317 | 0.362 | 38.7 |
| p0.75_tie50 | 0.75 | 0.50 | 500 | 1.000 | 0.307 | 0.349 | 39.0 |
| p0.85_tie50 | 0.85 | 0.50 | 500 | 1.000 | 0.294 | 0.352 | 37.5 |
| p0.95_tie50 | 0.95 | 0.50 | 498 | 0.996 | 0.282 | 0.444 | 32.7 |

Lowest coverage count on the grid: **495** (p=0.25, tie=0%) — still above 465.
`StoppingReason` values observed: `passed`, `failed`, `underpowered_nmax`
(`budget_exhausted` is set by the runner on external budget abort, not by
`check_stop`, so it does not appear in this pure-stopper harness).

Poison-direction control: `miscalibrated_nonpredictable_cs` (non-predictable λ)
is demonstrated RED (below lower tolerance) at p=0.65, proving the harness can
catch an invalid sequence.

---

## How to re-run

```bash
# Legacy posterior characterization (#164 pins)
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_calibration.py -q

# Production CS dense grid (#187)
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_cs_calibration.py -q -m calibration
```

