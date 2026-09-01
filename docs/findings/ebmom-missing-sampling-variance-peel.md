# EB-MoM treats binomial sampling noise as true heterogeneity

**Status:** OPEN. **Severity:** WRONG_NUMBER (decisions move, not only parameters).
**Found by:** `tests/test_aggregation_fit_ebmom_recovery.py` (falsification plan item 2, #344),
first run 2026-08-31, seed 20260902.
**Registered in advance:** the bounds and the regime predictions were written into the test's
docstring before the first simulation ran.

## What happened

`fit_skill` (`src/skill_harness/aggregation/fit.py`) estimates the Beta hyperprior by the
method of moments: it computes per-clause rates `w/n`, takes their population variance, and
inverts the Beta moment map in `_ebmom(sample_mean, sample_var)`. No term subtracts the mean
binomial sampling variance from the across-clause variance.

## The mechanism

Each observed rate `w/n` is the true clause rate plus binomial noise of variance roughly
`p(1-p)/n`. The across-clause variance of observed rates is therefore approximately

```
E[var(rates)] ~= mu(1-mu) * ( 1/(c+1) + 1/n )
```

where `c = alpha + beta` is the true hyperprior concentration. `_ebmom` attributes the whole
quantity to the first term, so the recovered concentration deflates by roughly the factor
`n / (n + c + 1)`. A deflated concentration means a weaker prior, which means under-shrinkage:
every clause's posterior sits closer to its own noisy rate than the model it claims to
implement says it should.

## Measured consequence (K=200 clauses, R=50 replicates per regime)

| regime | truth (mu*, c*, n) | mean recovered c | relative error | decision flip rate vs true-hyperprior posterior |
|---|---|---|---|---|
| small_n_bite | 0.65, 20, 10 | 6.19 | 0.690 | **0.1186** |
| low_heterogeneity | 0.65, 100, 25 | 19.41 | 0.806 | **0.0816** |
| benign_large_n | 0.65, 10, 100 | (in tolerance) | <= 0.25 | 0.0000-0.02 (within budget) |

The analytic deflation factors (0.32 and 0.20) predict recovered concentrations of about 6.8
and 20; the measurements landed at 6.19 and 19.41. The mechanism above is therefore not a
conjecture about the red: the measured bias matches its closed form.

The decision flip rate is the operative number: in the small-n regime, 11.9 percent of
clause verdicts under the locked `P(rate > 0.60) >= 0.95` / `<= 0.05` thresholds
(docs/INVARIANTS.md section 1) differ from the verdicts the true hyperprior implies. Those
flips are minted into PASS/FAIL outcomes and travel into KEEP/CUT dispositions. Who pays: a
skill measured with many small-n clauses gets overconfident verdicts in both directions;
readers of the published receipts inherit the overstatement.

## What a fix has to change

Subtract the mean binomial sampling variance before inverting the moment map (the standard
method-of-moments correction for the beta-binomial hierarchy):

```
v_latent = sample_var - mean( r_k (1 - r_k) / n_k )   # or the pooled equivalent
```

clamped below at zero (a negative peeled variance is the homogeneous case and should route to
the existing degenerate/fallback handling, not produce a negative concentration). The
`ConvergenceFailure` conditions and the `VAR_FLOOR` check need re-deriving against the peeled
variance, and `test_aggregation_fit.py`'s algebraic identities pin the CURRENT (unpeeled) map,
so they move with the fix. The recovery test's two xfail rows then flip to green and the
strict marker forces their un-marking in the same change.

## Uncertainty

The measured flip rates are point estimates at one seed; their scale (8-12 percent, versus a
2 percent materiality budget) is far outside plausible Monte-Carlo noise for 500,000 scored
decisions per regime. The benign regime shows the estimator is not globally broken: at n=100
with modest heterogeneity the deflation is inside tolerance and decisions reproduce.

## Next action

Repair ticket: filed as the fix's own ticket (see the issue referencing this document).
The detector stays strict-xfail on the two firing regimes until the peel lands.
