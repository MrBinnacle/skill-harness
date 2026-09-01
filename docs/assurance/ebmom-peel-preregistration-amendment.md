# Amended pre-registration: EB-MoM sampling-variance peel and heterogeneity admission (#360)

**Status:** FROZEN on authoring. No confirmatory simulation has been run against it.
**Amends:** the pre-registration in the module docstring of
`tests/test_aggregation_fit_ebmom_recovery.py` (falsification plan item 2, #344).
**Supersedes:** that registration's acceptance statistic only. Its regimes, its generative
model, and its recorded result stand as evidence.
**Depends on:** #368 (tie-encoding estimand). See section 4.
**Authored:** 2026-08-31, by the session that produced the development evidence in section 0.

---

## How to treat this document

You are not being given orders. You are reading a frozen acceptance contract plus a set of
implementation proposals, and the two carry different authority on purpose.

The session that wrote this **had already seen development results** on seed `20260902`: four
estimator families measured, the mean-concentration bar failed by all four. It has **not** seen
the confirmatory evidence, and by construction cannot — section 7 requires seeds this session
does not choose.

That asymmetry runs in both directions, so the split is:

- **The acceptance contract (sections 1, 3-level, 5, 7, and the kill criterion) is frozen and
  non-negotiable.** Not on the strength of its own correctness, but because a contract that can be
  revised after the confirmatory numbers arrive is not a contract. Its whole function is to be
  fixed before the evidence exists. If you believe a threshold is wrong, **say so before
  running the confirmatory simulation and get an amendment**; do not adjust it afterwards, and
  do not adjust it because a result landed on the wrong side.
- **The implementation seams (sections 2-mechanism, 3-procedure, 4, 6) are proposals from a
  session that could read the code but had not built the final gate.** You are inside the tree.
  If a seam is wrong, wrong-shaped, or already solved, surface the disagreement with reasoning
  and change it.

New evidence licenses a revisit request on a labelled-revisable item. It does not license
moving a threshold, dropping a reported quantity, or reclassifying a regime.

---

## 0. Development evidence, preserved and quarantined

The following are **development evidence**. They are disclosed, they may inform design, and
they may not be cited as confirmation of any repaired estimator.

| item | value |
|---|---|
| development seed | `20260902` |
| regimes | `small_n_bite` (mu\*=0.65, c\*=20, n=10), `low_heterogeneity` (0.65, 100, 25), `benign_large_n` (0.65, 10, 100), all K=200, R=50 |
| original result on `main` (unpeeled) | mean c_hat 6.19 (rel err 0.690) and 19.41 (0.806); decision flips 0.1186 and 0.0816 |
| candidate peel, mean c_hat | 30.14 (0.507) and 163.67 (0.637) |
| candidate peel, median c_hat | 22.44 (0.12) and 91.07 (0.09) |
| four estimator families, mean c_hat | per-clause peel 30.14 / 163.67; pooled peel 33.60 / 170.53; ANOVA rho 28.60 / 144.51; marginal-likelihood EB 29.91 / 1.5e16 |
| finite-K bias, 4000 replicates | `/K` peel biased low by -1.31e-4 and -5.8e-5 against a predicted `-(V_p+S)/K` of -1.62e-4 and -5.6e-5; `/(K-1)` biased by +3.1e-5 and -2e-6 |
| clipping | `max(v,0)` fires on 2.3 percent of `low_heterogeneity` replicates and moves the retained mean up by about 8e-6 |

**The original registration is not rewritten, and that is deliberate.** Its text stands unedited, including its
"from below" derivation, which is correct for the unpeeled estimator it was written against and
incorrect for any peeled one. That is the finding, and erasing it would erase the finding.

---

## 1. The mean-of-`c_hat` acceptance statistic is superseded

**FROZEN — non-negotiable.**

The original bar asserted that the mean over replicates of the recovered concentration sits
within `CONC_REL_TOL = 0.25` of truth. That statistic is withdrawn as an acceptance criterion.

**Why, stated mechanically.** Concentration is recovered as

```
c_hat = mu(1-mu) / v_latent - 1
```

a **reciprocal** of the latent variance. The peel is what makes this unstable: it removes most
of `v_latent`'s magnitude and none of its sampling error. In `low_heterogeneity` the raw rate
variance is about 0.0113 and the latent component about 0.00225, so a relative error of
`sqrt(2/K)` = 10 percent on the raw variance becomes roughly 50 percent on the peeled one. As
`v_latent` approaches zero the reciprocal diverges, and the arithmetic mean of a divergent
right tail is dominated by the replicates nearest the boundary. Those are precisely the
replicates where the data carry the least information about heterogeneity, so the statistic
weights the least informative draws the most.

This is not specific to method-of-moments. Full marginal-likelihood EB is **worse**: at the
homogeneous boundary the likelihood is maximised as `c -> infinity`, and one development
replicate in fifty diverged to 1.5e16. Any estimator of a concentration parameter inherits the
instability, because the instability is in the parametrisation, not the fitting method.

**The replacement is NOT the median.** Substituting a robust location statistic would move
the reported number off the tail while leaving the tail in production. The tail is not a
reporting nuisance; it is fits that should never have been admitted (section 3). Reporting the
median would let a defect ship behind a well-behaved summary, which is the failure mode this
repository exists to refuse.

**What replaces it:** the acceptance matrix in section 5, which asserts on the latent variance
where the estimator is unbiased, on admission behaviour, and on decision outcomes — never on a
reciprocal.

---

## 2. Estimator definition

**Mechanism revisable. The three properties below are frozen.**

```
total_var   = sum_k (r_k - r_bar)^2 / (K - 1)          # unbiased, NOT /K
sampling_var= mean_k [ r_k (1 - r_k) / (n_k - 1) ]      # see section 4 on ties
latent_raw  = total_var - sampling_var                  # may be negative; RETAINED as-is
```

Frozen properties:

1. **Finite-K correction.** Total variance uses `K-1`. The `/K` population form has expectation
   `(K-1)/K` times the true total variance, so subtracting the full sampling term under-peels
   by `-(V_p + S)/K`. Measured at 4000 replicates, this matches the closed form to within Monte
   Carlo error and it invalidates any claim that the `/K` candidate is unbiased.
2. **`latent_raw` is retained unclipped** and is the quantity every bias and coverage assertion
   in section 5 reads. Clipping before analysis induces a positive bias in the retained
   estimate, because it maps the entire negative tail onto a single boundary point.
3. **Clipping happens only after the admission decision**, and only to keep downstream
   arithmetic total. A fit that is admitted (section 3) has `latent_raw > 0` by construction, so
   in the admitted path the clip is a no-op; it exists for the refused path's provenance, not
   for the estimate.

*Revisit if:* reading the code shows a cheaper algebraically identical form, or shows that
`ClauseObservations` cannot supply what `sampling_var` needs (which is section 4's question, and
the answer changes the mechanism, not the three properties).

---

## 3. Admission by a heterogeneity test, replacing `VAR_FLOOR`

**Procedure revisable. Level and provenance frozen.**

`VAR_FLOOR = 1e-6` no longer controls admission. It was calibrated as an absolute magnitude
against the raw variance and is the wrong *kind* of quantity: a development replicate with
`latent = 5e-4` clears it and returns `c_hat = 454`. The question is not whether the latent
variance is large. It is whether it is **distinguishable from zero given its own sampling
error**.

### The test

```
H_0 : tau^2 = 0     (one common rate; all observed spread is sampling noise)
H_1 : tau^2 > 0
```

Parametric bootstrap under the null:

1. Fit the common rate `mu_0 = sum_k w_k / sum_k n_k` (pooled, not the mean of rates).
2. For `b = 1..B`: for each clause `k`, regenerate an observation vector under the null model at
   `mu_0`, **preserving that clause's own `n_k`**. Unequal `n_k` is the normal case and the
   null must reproduce it.
3. Compute `latent_raw` for each bootstrap sample by the section 2 formula, unchanged.
4. Critical value `c_alpha` = the `(1 - alpha)` quantile of the `B` null values.
5. **Admit the hierarchical fit iff `latent_raw > c_alpha`.** Otherwise raise
   `ConvergenceFailure` and take the existing BH-FDR fallback path.

`B = 999` proposed. The bootstrap replaces a normal approximation deliberately: at a boundary
null the sampling distribution of a variance component is skewed and partly atomic at zero, and
a normal quantile is wrong in exactly the regime that matters.

**Determinism must be preserved.** `fit_skill` currently documents itself as deterministic,
and a bootstrap introduces sampling. The bootstrap seed **must** be derived from the
observations themselves — a digest over the canonical sorted `(clause_id, w, n)` tuples — so the
same input yields the same admission verdict on every host and every run. Check
`docs/INVARIANTS.md` for a determinism clause before building; if one exists, this design must
satisfy it rather than amend it.

### The level, derived rather than inherited

**`alpha` is NOT `BH_FDR_Q = 0.05` by analogy.** They govern different quantities: `BH_FDR_Q`
controls false discoveries among clause verdicts; `alpha` controls whether a hyperprior gets
invented at all. Sharing a number would be a coincidence, not a reason.

The two errors are asymmetric **in kind**:

- A **false admission** fits a hyperprior to noise and emits shrunken posteriors derived from a
  model the data did not imply. The receipt looks normal. The reader cannot tell.
- A **false refusal** emits a typed refusal and routes to BH-FDR. The reader sees it and can act
  on it.

Where one error is silent and the other is visible, the silent one should be the rarer, which
argues for a small `alpha`. But the argument is not unconditional, and the condition is
buildable: **requiring the test statistic, critical value, level, `B`, and bootstrap identity in
the fallback and success provenance converts the silent error into an audited one.** Once the
admission rate is itself a reported quantity (section 5), a false admission is visible in
aggregate, and the asymmetry that justified an extreme `alpha` weakens.

Against that sits power. At the registered `low_heterogeneity` regime the development signal
ratio is about 2.0, so under a normal approximation one-sided power is roughly:

| alpha | z | approximate power at signal ratio 2.0 |
|---|---|---|
| 0.10 | 1.282 | 0.76 |
| 0.05 | 1.645 | 0.64 |
| 0.01 | 2.326 | 0.37 |

(Indicative only. The bootstrap null is skewed at the boundary, so the confirmatory run measures
these rather than assuming them.)

**Proposed: `HETEROGENEITY_TEST_ALPHA = 0.05`, one-sided.** Reasoning: `alpha = 0.01` refuses
roughly two thirds of a regime the instrument was built to measure, which is an instrument that
mostly declines to measure; `alpha = 0.10` buys 12 points of power for double the invented-fit
rate. 0.05 sits where the audited-provenance requirement makes the residual false-admission rate
observable rather than hidden.

**This is a risk-tolerance call and it is the maintainer's, not the implementer's.** It is
proposed with its derivation and its cost table so it can be overridden on values grounds. It is
frozen once set, before the confirmatory run.

Rename the control to say what it does: `HETEROGENEITY_TEST_ALPHA`. Keep a separate tiny epsilon
for arithmetic safety only (division guards), and do not let it carry admission meaning.

Fallback provenance **must** record `fallback_reason = "latent_variance_not_identified"` plus
the observed statistic, `c_alpha`, `alpha`, `B`, and the bootstrap seed identity.

*Revisit if:* the bootstrap cost is prohibitive at production K (measure it), or a null model
other than the pooled-rate one is the right null once section 4 resolves.

---

## 4. Dependency on #368: `(w, n)` does not identify the sampling variance

**FROZEN — non-negotiable that the dependency exists. The route is revisable.**

`sampling_var` uses `r(1-r)/(n-1)`, which is the correct unbiased estimator of `p(1-p)/n`
**for Bernoulli observations**. Production observations are not Bernoulli: `engine.py:291` sets
`w = sum(clause_axis_observations[k])` over values in `{0, 0.5, 1}`, so ties enter at half
weight.

Verified: `(w=1, n=2)` is produced by both

| observations | w | n | r | true within-clause sum of squares |
|---|---|---|---|---|
| one win, one loss | 1.0 | 2 | 0.50 | 0.5000 |
| two ties | 1.0 | 2 | 0.50 | 0.0000 |

and the peel reads `0.2500` for both. **The within-clause variance is not a function of
`(w, n)`.** Any peel computed from `(w, n)` alone is guessing on tie-carrying data, and guessing
in the direction that matters: a tie-heavy clause has less within-clause variance than the
formula assumes, so it is over-peeled and its latent contribution understated.

Two admissible routes. Exactly one must be chosen before the gate is built:

- **(a) Migrate the fit to the ratified discordant-table estimand (#368).** Discordant wins and
  losses are Bernoulli, so the section 2 formula applies unchanged and no new field is needed.
  Cleaner, and it is the estimand of record.
- **(b) Carry sufficient statistics.** Extend `ClauseObservations` with the tie count, or with
  the sum of squared observations, so within-clause variance is identified. Additive, but it
  widens a frozen dataclass and every producer of it.

Route (a) is recommended on the strength of the existing ruling. The choice is the maintainer's
because it decides what the production claim is about, not merely how it is computed.

**No confirmatory run may use tie-free synthetic data as evidence that production is
correct.** The development regimes draw `w_k ~ Binomial(n, p_k)` and are tie-free, so they
cannot detect this defect at all. The confirmatory matrix must include at least one
tie-carrying regime.

---

## 5. Acceptance matrix

**FROZEN — non-negotiable.** Every quantity below is reported for every registered regime. A run
that reports a subset is not a confirmatory run.

| # | quantity | assertion |
|---|---|---|
| 1 | **False admission under homogeneity** — admission rate when `tau^2 = 0` exactly | within Monte Carlo error of `alpha`; this is the test's own calibration and its failure invalidates everything below |
| 2 | **Admission rate by regime** | reported, not bounded. A regime near the identification boundary is *expected* to admit a minority of replicates; that is a power result, not a defect |
| 3 | **Bias of `latent_raw`** against the true variance component, unclipped | relative bias within a bound registered before the run |
| 4 | **Interval coverage** of the recovered variance component | nominal coverage within binomial tolerance |
| 5 | **Fallback rate** and its reason distribution | reported; `latent_variance_not_identified` separated from `alpha_le_zero` and `beta_le_zero` |
| 6 | **Wrong PASS rate** — fitted says PASS, oracle does not | must not rise against `main` in any registered regime |
| 7 | **Wrong FAIL rate** — fitted says FAIL, oracle does not | must not rise against `main` in any registered regime |
| 8 | **Added abstention** — fitted says UNDECIDED, oracle decides | reported as an evidence-coverage cost, not netted against 6 or 7 |

**The three decision outcomes stay separate and are never summed into a single flip rate.**
The development flip rate of 0.1436 in `low_heterogeneity` mixes wrong directional verdicts with
honest abstentions and cannot distinguish a repair that makes the instrument more careful from
one that makes it more wrong. That conflation is why the number was uninterpretable when this
session reported it.

---

## 6. The differential reference

**Mechanism revisable. Independence is frozen.**

`tests/test_aggregation_differential.py::test_1000_seeded_inputs_match_reference` passes on
`main` and fails under the candidate peel. This was measured both ways; it is caused by the
change, not pre-existing.

The reference must therefore move. Frozen constraints on how:

1. **Independent re-derivation.** The reference implements the amended estimator and admission
   rule **from this specification**, not by calling production. It must not import or invoke the
   production peel, the admission helper, `_ebmom`, or `fit_skill`. A reference that calls the
   implementation tests that the code equals itself.
2. **Mutation receipt required.** Ship a receipt proving the re-derived reference *can* reject a
   wrong implementation: mutate production, show the differential test goes red, and attribute
   the kill **to the differential assertion by name**. A mutation that fails to compile, or that
   reddens a different suite, is not a kill — record which assertion failed, not the exit code.

*Revisit if:* the existing reference is already independent by construction, in which case say so
with the file evidence and only its expectations move.

---

## 7. Confirmatory protocol

**FROZEN — non-negotiable.**

1. This amendment is frozen when merged. Sections 1, 3-level, 5, and the kill criterion do not
   change afterwards.
2. The gate is built to this specification. Building may use seed `20260902` freely; anything it
   produces is development evidence and is labelled as such.
3. **The confirmatory run uses fresh seeds chosen by someone other than the session that wrote
   this amendment or built the gate.** The maintainer named Hans as a source for those seeds.
   The seeds are recorded in the confirmatory receipt before the run.
4. The confirmatory run reports the full section 5 matrix. One run, reported whichever way it
   lands.
5. A confirmatory run that fails does not license a second run at new seeds. It licenses a new
   amendment, openly superseding this one, and the failed result stays in the record.

---

## Kill criterion

**Any rise in the wrong PASS rate or the wrong FAIL rate, in any registered regime, against
`main`, rejects the combined change.**

A rise in abstention does not reject it and is reported separately as an evidence-coverage cost.

Rollback state is `main`. `agent/issue-360` stays unmerged and is the development artifact.

---

## Decision status

- **Non-negotiable:** section 1 (statistic superseded, median rejected); section 2's three
  frozen properties; section 3's level once set, and the provenance requirement; section 4's
  dependency on #368 and the tie-carrying regime requirement; section 5 in full; section 6's
  independence constraint; section 7; the kill criterion.
- **Revisable with new evidence:** the estimator's algebraic form (section 2 mechanism).
  *Revisit if:* the code shows an identical cheaper form, or `ClauseObservations` cannot supply
  the inputs.
- **Revisable with new evidence:** the bootstrap procedure and `B` (section 3).
  *Revisit if:* measured production cost is prohibitive, or a different null is correct after
  section 4 resolves.
- **Revisable with new evidence:** the #368 route, (a) or (b) (section 4).
  *Revisit if:* the discordant migration turns out to change what is being claimed rather than
  how it is computed.
- **Revisable with new evidence:** how the differential reference moves (section 6).
  *Revisit if:* it is already independent, with file evidence.
- **Maintainer's call, proposed not decided:** `HETEROGENEITY_TEST_ALPHA = 0.05`. Risk tolerance,
  with the power cost tabled in section 3.

---

## Blast-radius correction (method finding, applies beyond this ticket)

The blast-radius measurement on #360 used a GitNexus call-graph index. It found `_ebmom`'s
production callers correctly and reported `fit_skill` and `aggregate_skill`, depth 1 and 2. It
named `tests/test_aggregation_fit.py` and the recovery test as the pinning test surface.

It **missed** `tests/test_aggregation_differential.py`, which pins the same behaviour through
`fit_skill` rather than through `_ebmom`. A grep for `_ebmom` agreed with the index and missed it
for the same reason: the dependency is on the **nearest public API**, not on the changed symbol.

**A blast-radius check needs two sweeps, not one: call-graph impact from the changed symbol,
and the direct test surface of the nearest public API above it.** A call-graph index answers
"what calls this function" and cannot answer "what asserts on this behaviour."

Recorded here rather than only on the ticket, because it is a method defect and the next
instrument-repair session will otherwise repeat it.
