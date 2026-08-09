# Finding: aggregation 95% CI coverage under sequential stopping

**Severity:** `WRONG_NUMBER`  
**Ticket:** #164 (coverage calibration by simulation)  
**Status:** open — detection landed; production math **not** changed  
**Harness:** `tests/test_aggregation_calibration.py`  
**Report:** `docs/assurance/calibration-report.md`  
**Master seed:** `164_2026_08_09` (`numpy.random.default_rng`; per-point seed = master + grid index)

---

## Summary

Under the production sequential stopper (`BetaBinomialAccumulator` /
`check_stop`, `N_MIN=8`, `N_INC=4`, `N_MAX=40`) the unpooled Beta(1+w, 1+n−w)
equal-tailed 95% credible interval produced by `fit_skill` (K=1 path; the same
interval `engine.aggregate_skill` surfaces) does **not** attain nominal
frequentist coverage at every planted clause win-rate on the registered grid.

| Grid label | Planted `p` | Seed | Coverage count `X` / 500 | Rate | Band `[465, 484]` | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `null` | 0.50 | `16420260809` | **470** | 0.940 | inside | OK |
| `small` | 0.65 | `16420260810` | **441** | 0.882 | **below** | **MISS** |
| `large` | 0.85 | `16420260811` | **491** | 0.982 | **above** | **MISS** |

Tolerance arithmetic (central 95% mass of `Binomial(N=500, π=0.95)`):

```text
lo = binom.ppf(0.025, n=500, p=0.95) = 465
hi = binom.ppf(0.975, n=500, p=0.95) = 484
E[X] = 475
```

---

## Why this is a finding, not a retune

Standing rule (assurance-pass / #164): **coverage misses are findings, never a
reason to adjust locked aggregation math** (Beta prior, equal-tailed `ppf`
interval, stopper thresholds in `docs/INVARIANTS.md` §1, `N_MIN`/`N_INC`/`N_MAX`).

Optional stopping is known to bias stopped sums as estimators of the underlying
rate; equal-tailed Bayesian credible intervals are not exact frequentist CIs at
every `(n, p)` even under fixed-n. The calibration harness makes the joint
failure mode measurable and pins it with seeds.

---

## Detection wiring

- `tests/test_aggregation_calibration.py::test_coverage_within_binomial_tolerance_per_grid_point`
  — parametrized over the grid.
- Grid points `small` and `large` are marked
  `@pytest.mark.xfail(strict=True, reason="finding: … this file …")`.
- Grid point `null` remains a hard assert (currently inside band).
- No production module under `src/skill_harness/aggregation/` is modified by the
  landing of this finding.

---

## Reproduction

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_calibration.py -q
```

Expected: `null` passes; `small` and `large` xfail (strict). If an xfail
unexpectedly passes, pytest fails strict-xfail — re-measure and update this
finding before touching thresholds.
