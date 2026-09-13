# Amended pre-registration: EB-MoM sampling-variance peel and heterogeneity admission (#360)

**Status:** FROZEN on authoring. No confirmatory simulation has been run against it.
**BLOCKED (2026-09-01) on the clause disagreement: RESOLVED 2026-09-02** by the heterogeneity-target
ruling (encoded mean; section 3's tie treatment superseded; row 1 re-measured calibrated at 0 of 40).
**A confirmatory root seed is STILL not to be spent, on this session's recommendation rather than by
contract:** the same R=40 development smoke fires the frozen kill criterion in three registered
regimes (wrong-PASS excess +109 in `low_heterogeneity` and +17 in `tie_heavy_signal`; wrong-FAIL
excess +12 in `tie_heavy_null`), and the two tie-free instances were already present at `7d50b4a`
and unreported. A confirmatory run now is predicted to REJECT. The contract permits it (one run,
reported whichever way it lands, then a superseding amendment); spending the seed on a predicted
rejection is the maintainer's call. Section 0 carries the numbers.
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
| development smoke through the harness at `7d50b4a`, before the null amendment (2026-09-02, R=40, root `SMOKE_NOT_CONFIRMATORY`) | verdict REJECTED. Row 1 `tie_heavy_null` 16/40. Kill criterion excess over `main`: `low_heterogeneity` wrong PASS +109, wrong FAIL +19; `tie_heavy_signal` wrong PASS +17; `tie_heavy_null` wrong FAIL +6. Abstention excess: `small_n_bite` +1, `low_heterogeneity` -194, `tie_heavy_null` -3054, `tie_heavy_signal` -164. Row 3 bias 0.0249 / 0.0012 / 0.0143 / 0.0201 (all inside 10 percent). **These rows existed on the smoke the 2026-09-01 comment reported row 1 from, and were not reported.** |
| development smoke through the harness after the null amendment (2026-09-02, R=40, same root) | verdict REJECTED. Row 1 `tie_heavy_null` **0/40, calibrated** (exact binomial p = 0.27). Kill criterion excess unchanged on the tie-free regimes (`low_heterogeneity` +109 / +19; `benign_large_n` 0 / -35; `small_n_bite` -567 / -122); `tie_heavy_signal` wrong PASS +17; `tie_heavy_null` wrong FAIL **+12** (was +6: the amended null refuses the null world, so those clauses take the unpooled path, which abstains where `main`'s over-shrunk fit happened to PASS them correctly). Abstention excess on `tie_heavy_null` -14 (was -3054). Row 3 bias unchanged. |
| mechanism of the tie-free kills, read from the numbers | the wrong-PASS excess in `low_heterogeneity` is the section 1 reciprocal instability reaching the decisions: an admitted fit with an overshooting `c_hat` (hundreds against a truth of 100) shrinks every clause to 0.65 with a posterior narrow enough to clear `P(rate > 0.60) >= 0.95`, where the oracle at `c = 100` abstains. The admission test refuses the fits nearest the boundary; it does not bound the variance of `c_hat` among the admitted ones. A repair is a change to the estimator (section 2 mechanism, revisable), not to any threshold, and it is development work under section 7 item 2 |


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
sampling_var= mean_k [ (sum_sq_k - n_k r_k^2) / ((n_k - 1) n_k) ]   # section 4
latent_raw  = total_var - sampling_var                  # may be negative; RETAINED as-is
```

Frozen properties:

1. **Finite-K correction.** Total variance uses `K-1`. The `/K` population form has expectation
   `(K-1)/K` times the true total variance, so subtracting the full sampling term under-peels
   by `-(V_p + S)/K`. Measured at 4000 replicates, this matches the closed form to within Monte
   Carlo error and it invalidates any claim that the `/K` candidate is unbiased.
2. **`latent_raw` is retained unclipped** and is the quantity the section 5 bias row reads. Clipping before analysis induces a positive bias in the retained
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

The null is **CATEGORICAL over `{0, 0.5, 1}`, not binomial.** A binomial null at the pooled
encoded mean would regenerate a tie-free world and compare tie-carrying data against it, which
reintroduces exactly the misspecification `sum_sq` was added to remove.

**AMENDED 2026-09-02, on the heterogeneity-target ruling recorded on #360 that day.** The text
from "Ties are held fixed per clause" through "must not be described as if it did" is
**SUPERSEDED** and kept unedited as the record; the replacement follows it under "The null as
amended". Steps 4 and 5, the decision rule, `B`, the level, the seed derivation and the provenance
requirement are unchanged. The ruling: the lane's heterogeneity target is the **encoded clause
mean** `theta_k = 0.5 t_k + (1 - t_k) p_k`, because the lane decides each clause on the encoded
rate (INVARIANTS section 1) and operates on `{0, 0.5, 1}` observations under route (b) (section 4).
Under that target the tie count is not ancillary, so a null that holds it fixed conditions on part
of the hypothesis. It holds while both premises hold; the Revisit-if in the decision-status list
says when it expires.

---- SUPERSEDED TEXT BEGINS ----

Ties are held **fixed per clause**. How many trials tied is a property of the evidence
collected, not of the hypothesis under test; `H_0` is a statement about one shared *decisive*
win probability.

1. Decompose each clause exactly (section 4) into `wins_k`, `ties_k`, `losses_k`.
2. Fit the pooled encoded mean `mu_0 = sum_k w_k / sum_k n_k`. This is the quantity the null
   holds constant; see the note below step 3. A clause with no decisive trial is returned
   unchanged, since no decisive rate is identified for it.
3. For `b = 1..B`: for each clause `k`, keep `ties_k` ties and redraw its `n_k - ties_k`
   decisive trials as Bernoulli(`p_0k`). Each clause keeps its own `n_k`; unequal `n_k` is the
   normal case and the null must reproduce it.

**THE NULL HOLDS THE ENCODED CLAUSE MEAN CONSTANT. That is the heterogeneity target, and it forces the
decisive rate to vary by clause.** With tie fraction `q_k = ties_k / n_k`,

```
E[X_k] = 0.5 q_k + (1 - q_k) p_k
```

so a COMMON decisive rate produces DIFFERENT encoded means whenever tie fractions differ.
Measured: at `p_0 = 0.75` the encoded mean runs 0.70, 0.65 and 0.60 for `q` = 0.20, 0.40 and
0.60. A draw like that is not a null for the hypothesis under test; it is a world carrying real
between-clause variation, and it would inflate the null distribution. The null therefore inverts
per clause:

```
p_0k = (mu_0 - 0.5 q_k) / (1 - q_k),   clamped to [0, 1]
W_k  ~ Binomial(n_k - ties_k, p_0k)
```

which gives every clause the encoded mean `mu_0` by construction. `mu_0` is pooled over
observations, `sum_k w_k / sum_k n_k`.

**One null, and it is this one:** tie counts fixed per clause AND the encoded clause mean held
constant. An implementation that instead drew all three outcomes from a single pooled
categorical distribution would not hold tie counts fixed, and must not be described as if it
did.

---- SUPERSEDED TEXT ENDS ----

#### The null as amended (2026-09-02)

`H_0` is one categorical distribution over `{0, 0.5, 1}` shared by every clause.

1. Decompose each clause exactly (section 4) into `wins_k`, `ties_k`, `losses_k`.
2. Pool over observations, not over clauses: `t_0 = sum_k ties_k / N`, `win_0 = sum_k wins_k / N`,
   `loss_0 = 1 - t_0 - win_0`, with `N = sum_k n_k`.
3. For `b = 1..B`: for each clause `k`, redraw **all** `n_k` observations i.i.d. from
   `{0.5: t_0, 1: win_0, 0: loss_0}`. Each clause keeps its own `n_k`.

Every null clause has encoded mean `0.5 t_0 + win_0 = mu_0` by identity, with no per-clause
inversion and no clamp. Ties are redrawn because tie propensity is a component of `theta_k`; the
superseded null fixed them and so reproduced none of the tie-sampling variation the data carry,
which is the whole of the 16 of 40. On tie-free data (`t_0 = 0`) the draw is the binomial null at
the pooled rate and consumes the RNG stream exactly as the superseded implementation did, so
tie-free admission verdicts are unchanged. Provenance keeps `null_encoded_mean` and adds
`null_tie_fraction` (`t_0`); the frozen provenance list gains that field and loses nothing.

**Why pooled rather than a per-clause plug-in of `q_k`.** A per-clause plug-in with the superseded
inversion clamps `p_0k` at boundary tie fractions; a clamped clause no longer has encoded mean
`mu_0`, so the null world carries heterogeneity of its own and the test goes conservative exactly
where `theta`-heterogeneity driven by tie propensity is real. Chosen before the row-1
re-measurement, which checks it and does not pick it.

**A limitation, measured.** `H_0: Var(theta) = 0` is composite; worlds with common `theta` and
clause-varying `(t_k, p_k)` are inside it and the pooled null draws only its i.i.d. member. The
statistic's null expectation is zero under every member; the null variance can differ because
`Var(X) = theta - 0.25 t - theta^2` varies with `t`. Measured on `iso_theta` below.

**`tie_heavy_null` is a null world under both readings.** In the registered regime every clause has
`theta_k = 0.65` exactly and the population latent variance of `theta` is 0. The `6.0e-04` the
open-question section attributed to "conditional heterogeneity" is sampling variation of the tie
count, and only a null that conditions on realised tie counts can see it. The regime does not
move, and its label was never wrong.

**What the registered matrix cannot see.** `tie_heavy_null` is homogeneous under both readings and
`tie_heavy_signal` has a common tie rate, so the confirmatory matrix cannot distinguish the amended
null from a decisive-rate null. The ruling is pinned by a deterministic fixture in
`tests/test_aggregation_fit.py::TestFitSkillEbmom::test_tie_propensity_heterogeneity_is_admitted`:
ten clauses `(wins, ties, losses) = (60, 20, 20)` and ten `(28, 60, 12)`, decisive rates 0.75 and
0.70, encoded 0.70 and 0.58. The amended null admits it (`p_boot = 0.001`); the ties-fixed null
refuses it (`p_boot = 0.335`). Mutant M-B4 in the mutation receipt is now that ties-fixed draw.

**Development demonstration behind the ruling** (`scripts/ebmom_null_demo_7d50b4a.py`, pinned to
commit `7d50b4a`, root seed `SMOKE_NOT_CONFIRMATORY`, throwaway; not row 1):

| world | true `Var(theta)` | null | admitted, R=40 | admitted, R=200 |
|---|---|---|---|---|
| `tie_heavy_null` | 0 (both readings) | ties fixed, encoded mean common (superseded) | 16/40 | 79/200 |
| `tie_heavy_null` | 0 (both readings) | ties fixed, decisive rate common | 0/40 | 7/200 |
| `tie_heavy_null` | 0 (both readings) | pooled categorical, ties redrawn (amended) | 0/40 | 5/200 |
| `tie_split` | 0.0025 encoded; 0 decisive | ties fixed, encoded mean common (superseded) | 40/40 | 200/200 |
| `tie_split` | 0.0025 encoded; 0 decisive | ties fixed, decisive rate common | 2/40 | 9/200 |
| `tie_split` | 0.0025 encoded; 0 decisive | pooled categorical, ties redrawn (amended) | 40/40 | 199/200 |

`tie_split`: common decisive rate 0.75, tie propensity 0.20 for even clauses and 0.60 for odd,
`n = 25`, `K = 200`; encoded means 0.70 and 0.60. Through the amended production code at `R = 200`
(no monkeypatch): `tie_heavy_null` admitted 4/200 (0.020, exact binomial p = 0.05 against 0.05); `iso_theta` (encoded mean 0.65 for every clause, `(t, p) = (0.20, 0.6875)` for even clauses and `(0.60, 0.875)` for odd, so `Var(theta) = 0` with `Var(t) > 0`) admitted 13/200 (0.065, p = 0.33); `tie_split` admitted 199/200. The composite-hypothesis member outside the null's i.i.d. world is calibrated within Monte Carlo error at this size.

**Cross-family challenge review.** The ruling was reviewed before posting by two non-Anthropic
models prompted to refute it in both directions. Both accepted the amended null as the right shape
given the encoded target and neither could construct a case for the superseded null standing. Both
held that the choice of target is a judgement rather than a derivation, and the ruling on #360 is
written that way and names the alternative: hold `BLOCKED` and build route (a) first. Receipt: the
operator's steering repository, `docs/audit/t1-360-heterogeneity-target-S394/`.

4. Compute `latent_raw` for each bootstrap sample by the section 2 formula, unchanged.
5. **Decision rule, FROZEN at `B = 999`:**

```
p_boot = (1 + count_b( T_b >= T_observed )) / (B + 1)
admit  iff  p_boot <= 0.05
```

**Not a library-interpolated 95th percentile.** At finite `B` the achievable levels are
discrete; the `(1 + count) / (B + 1)` form is the one that keeps the test valid there, whereas
an interpolated quantile sits between order statistics and can admit at a true level above
`alpha`. The bootstrap replaces a normal approximation deliberately: at a boundary null the
sampling distribution of a variance component is skewed and partly atomic at zero, and a normal
quantile is wrong in exactly the regime that matters.

Record `p_boot`, the critical order statistic, the exceedance count, `q_0`, the pooled tie
fraction `t_0` (added 2026-09-02, additive), `B`, the level, and the bootstrap identity.

**Determinism must be preserved.** `docs/INVARIANTS.md` carries no general determinism clause,
but `fit_skill`'s own docstring makes the promise directly, and a bootstrap introduces sampling.

**The seed-derivation procedure is FROZEN in full.** Every element is part of the contract,
because changing any one of them silently changes admission verdicts on unchanged data:

| element | frozen value |
|---|---|
| sort order | ascending by `clause_id`, Python `str` comparison (code points) |
| field order | `clause_id`, `w`, `n`, `sum_sq` |
| number form | `float.hex()` for `w` and `sum_sq`; `str(int(...))` for `n` |
| separators | `\|` between fields, `;` between clauses |
| encoding | UTF-8 |
| digest | SHA-256 over those bytes |
| seed | first 8 bytes of the digest, big-endian, unsigned |
| generator | `random.Random` (Mersenne Twister), seeded with that integer |

`float.hex()` rather than `repr`: it is exact, round-trippable, and independent of repr
formatting. **Python object hashes are NOT used** — they are salted per process, so a verdict
would vary run to run, which is the exact failure this guards against.

The digest covers **all four fields including `sum_sq`**. `(clause_id, w, n)` stopped being the
complete input when route (b) landed: two clause sets differing only in tie composition are
different data and must not share a bootstrap stream. Pinned by
`test_seed_covers_sum_sq_not_just_w_and_n`.

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
buildable: **requiring the test statistic, `p_boot`, the critical order statistic, the level,
`B`, and the bootstrap identity in both the fallback and success provenance converts the silent
error into an audited one.** Once the admission rate is itself a reported quantity (section 5),
a false admission is visible in aggregate, and the asymmetry that justified an extreme `alpha`
weakens. **The claim being made is the weaker one:** provenance makes a decision reproducible
and auditable, not retrospectively identifiable as a false admission. That weaker claim is
sufficient for this argument.

Against that sits power. At the registered `low_heterogeneity` regime the development signal
ratio is about 2.0, so under a normal approximation one-sided power is roughly:

| alpha | z | approximate power at signal ratio 2.0 |
|---|---|---|
| 0.10 | 1.282 | 0.76 |
| 0.05 | 1.645 | 0.64 |
| 0.01 | 2.326 | 0.37 |

(Indicative only. The bootstrap null is skewed at the boundary, so the confirmatory run measures
these rather than assuming them.)

**SET: `HETEROGENEITY_TEST_ALPHA = 0.05`, one-sided.** Reasoning: `alpha = 0.01` refuses
roughly two thirds of a regime the instrument was built to measure, which is an instrument that
mostly declines to measure; `alpha = 0.10` buys 12 points of power for double the invented-fit
rate. 0.05 sits where the audited-provenance requirement makes the residual false-admission rate
observable rather than hidden.

This was a risk-tolerance call and it was the maintainer's, not the implementer's. It was
proposed with the derivation and cost table above and **ruled by the maintainer on 2026-08-31**,
before any confirmatory run. It is now frozen: it does not move because a confirmatory result
lands on the wrong side of it.

Rename the control to say what it does: `HETEROGENEITY_TEST_ALPHA`. Keep a separate tiny epsilon
for arithmetic safety only (division guards), and do not let it carry admission meaning.

**The guarantee is PER FIT INVOCATION, and the provenance says so:**

```
HETEROGENEITY_TEST_ALPHA = 0.05 controls one fit invocation.
It does not establish a fleet-wide or repeated-use false-admission budget.
```

Per-cell alpha does not control false qualification across many cells or repeated uses. That is
a known open defect in the wider qualification design; it does not block this change, but a
reader must not read a per-fit level as a program-level one.
*Revisit if:* hierarchical admission is applied across many skills, models, or repeated
evaluations, which needs a program-level alpha-spending rule this amendment does not provide.

Fallback provenance **must** record `fallback_reason = "latent_variance_not_identified"` plus
the observed statistic, `p_boot`, the critical order statistic, the exceedance count, `q_0`,
`alpha`, `B`, and the bootstrap seed identity.

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

**ROUTE (b) IS CHOSEN, because route (a) is not available.** Measured 2026-08-31: #368 is still
`OPEN`, and the discordant machinery that exists (`oc/crosschecks.py`, `oc/exact.py`,
`oc/gate2.py`) serves the paired Gate-2 lane, not the clause-level aggregation lane that
`fit_skill` occupies. There is no discordant table for `fit_skill` to consume, so route (a)
cannot be built today; it is blocked on #368's migration rather than rejected on merit.

This is a checkable fact about the tree, not a values call, which is why the implementing
session settled it.

**CORRECTED after maintainer review: #368 does not by itself supersede `sum_sq`.** The two
tickets repair different decision lanes, and merging their concepts must not merge their
authority:

```
#368 supersedes scalar half-update for production matched-efficacy decisions.
It does NOT by itself supersede sum_sq in the diagnostic clause-aggregation lane.
sum_sq becomes redundant only if fit_skill is migrated to a sufficient
discordant representation, or removed from that lane.
```

Matched Full/Null efficacy decisions belong to the four-cell discordant-table path and Gate 2.
Hierarchical clause aggregation is a distinct surface and must not silently become the
production efficacy authority. So while `fit_skill` continues to operate on clause-level
`{0, 0.5, 1}` observations, `sum_sq` remains necessary after #368 lands, not redundant.

Route (b) as built:

```
sum_sq_k = sum_i o_{k,i}^2                       # carried on ClauseObservations
within_ss_k     = sum_sq_k - n_k * r_k^2         # exact within-clause sum of squares
sampling_var_k  = within_ss_k / ((n_k - 1) * n_k)
```

**`sum_sq` is a genuine sufficient statistic for this outcome alphabet, not a summary of it.**
For observations in `{0, 0.5, 1}`, `w = wins + 0.5 ties` and `sum_sq = wins + 0.25 ties`, which
inverts exactly:

```
ties   = 4 * (w - sum_sq)
wins   = 2 * sum_sq - w
losses = n - wins - ties
```

Verified on worked cases including `(wins=3, ties=4, losses=2)` and the all-tie corner
`(0, 9, 0)`. This identity is what makes the categorical null in section 3 constructible: the
null can hold each clause's tie count fixed because that count is recoverable, not estimated.

This is exact under ties and **reduces to the Bernoulli form when there are none**: with
`o in {0,1}`, `sum_sq = sum(o) = w`, so `sampling_var = (n r - n r^2)/((n-1) n) = r(1-r)/(n-1)`,
which is the section 2 formula unchanged. The generalisation therefore costs nothing on tie-free
data and cannot silently change the Bernoulli result.

`sum_sq` is **required, not optional-with-fallback**. An optional field that silently falls back
to the Bernoulli formula would compute a wrong peel on tie-carrying data while reporting
success, which is the class of defect this amendment exists to remove.

**No confirmatory run may use tie-free synthetic data as evidence that production is
correct.** The development regimes draw `w_k ~ Binomial(n, p_k)` and are tie-free, so they
cannot detect this defect at all.

### Registered tie-carrying regimes

**FROZEN — two regimes, registered before the freeze rather than added at run time.**

One tie regime is not enough. A null regime tests whether the test is *calibrated* when ties
are present; a signal regime tests whether the *peel* is right when ties are present. Either
one alone leaves a hole: a calibrated test that cannot recover a known variance is useless, and
an accurate peel that over-admits under homogeneity mints invented fits.

Both encode a mean of 0.65, matching the tie-free regimes, so the tie dimension is the only
thing that varies.

#### `tie_heavy_null` — calibration under ties

```
tie probability          t   = 0.40
decisive win probability q   = 0.75, IDENTICAL for every clause
n = 25, K = 200
encoded mean   = 0.4*0.5 + 0.6*0.75 = 0.65
latent variance = 0   (exactly; there is no between-clause variation)
```

What it tests: the admission rate under an exactly homogeneous, tie-carrying world must match
`alpha`. This is the row that catches a null model that regenerates a tie-free world, which
would make the observed tie-carrying spread look like heterogeneity and over-admit.

#### `tie_heavy_signal` — the peel under ties

```
tie probability t = 0.40
decisive p_k ~ Beta(15, 5)      (mean 0.75, variance 0.75*0.25/21)
n = 25, K = 200
encoded mean = 0.2 + 0.6*0.75 = 0.65
true encoded latent variance
  = 0.60^2 * [0.75 * 0.25 / 21]
  = 0.36 * 0.008928571...
  = 0.0032142857
```

The encoded observation is `o = 0.5` with probability `t`, else decisive at `p_k`, so the
clause's expected observation is `0.2 + 0.6 p_k` and the between-clause variance of that
expectation is `0.6^2 Var(p_k)`. Derived above rather than simulated, and it is the target the
bias row in section 5 measures against.

What it tests: the peel must recover `0.0032142857` within the registered bias bound on
tie-carrying data. A peel computed from `(w, n)` alone over-peels tie-heavy clauses and will
understate it.

**No confirmatory run may substitute one of these for the other.** A run reporting the
section 5 matrix on the three tie-free regimes plus only `tie_heavy_signal` is not a
confirmatory run, and neither is one that reports only `tie_heavy_null`.

#### The oracle for a tie regime, registered

Rows 5 to 7 compare fitted decisions against an oracle built from the TRUE hyperprior. For the
tie-free regimes that hyperprior is `Beta(a*, b*)` directly. For a tie regime the encoded mean
is `0.2 + 0.6 p_k`, a scaled Beta, which is not itself Beta, so the oracle needs a stated
choice rather than an implied one.

**FROZEN: the oracle hyperprior for a tie regime is the Beta with mean and variance matched to
the true encoded-mean distribution.** Moment matching is the standard construction and it keeps
the oracle in the same family as the quantity under test. For `tie_heavy_signal`:

```
mean = 0.65, variance = 0.0032142857
c    = mean(1-mean)/variance - 1 = 69.777778
a    = 45.355556,  b = 24.422222
```

For `tie_heavy_null` the true latent variance is 0, so the encoded mean is exactly 0.65 for
every clause and the oracle is the degenerate distribution at 0.65. Its `P(rate > 0.60) = 1`,
so every clause's oracle decision is PASS. Rows 5 to 7 remain well defined there; row 3 does
not, and is reported only for regimes with nonzero true latent variance, as section 5 states.

Registered here because it is a degree of freedom in the acceptance matrix, and an unstated one
would let the harness author choose the oracle after seeing which choice passes.

---

## 5. Acceptance matrix

**FROZEN — non-negotiable.** Every quantity below is reported for every registered regime. A run
that reports a subset is not a confirmatory run.

**Replication: `R = 1000` per registered regime.** Registered regimes are `small_n_bite`,
`low_heterogeneity`, `benign_large_n`, `tie_heavy_null`, `tie_heavy_signal`.

**Identical synthetic worlds.** `main` and the candidate are evaluated on the SAME generated
data, world for world. The comparison rows below are paired differences on identical inputs,
not two independent samples, so an apparent difference cannot be sampling noise between runs.

| # | quantity | frozen bound |
|---|---|---|
| 1 | **False admission under homogeneity** — admission rate where the true latent variance is 0 (`tie_heavy_null`, and any tie-free null world generated for this row) | exact binomial test of the observed admission count against `p = 0.05`, at test level `0.01`; failure to reject is the pass condition |
| 2 | **Admission rate by regime** | reported, not bounded. A regime near the identification boundary is *expected* to admit a minority of replicates; that is a power result, not a defect |
| 3 | **Relative bias of `latent_raw`**, unclipped, over **ALL replicates including refused ones**, against the regime's true latent variance | absolute relative bias **no greater than 10 percent** in every regime whose true latent variance is nonzero. Conditioning on admission would select the positive tail and manufacture bias, so the harness asserts it collected one estimate per replicate |
| 4 | **Fallback rate** and its reason distribution | reported; `latent_variance_not_identified` separated from `alpha_le_zero` and `beta_le_zero` |
| 5 | **Wrong PASS count (CLAUSE STATUS)** — fitted clause status is PASS, oracle is not | **any positive excess over `main` on the identical worlds kills the candidate** |
| 6 | **Wrong FAIL count (CLAUSE STATUS)** — fitted clause status is FAIL, oracle is not | **any positive excess over `main` on the identical worlds kills the candidate** |
| 7 | **Added abstention** — fitted says UNDECIDED, oracle decides | reported as an evidence-coverage cost, not netted against 5 or 6 |

**The `interval coverage` row from the first draft is REMOVED, not deferred.** It named a
property of an interval that production does not compute: `fit_skill` returns per-clause
posterior credible intervals, and no interval is produced for the latent variance or the
hyperprior, so there was nothing for a coverage row to measure. Row 3 measures the estimator's
accuracy directly instead. Restoring a coverage row requires first building the interval it
would be about, and that is not in this change.

**Rows 5 to 7 are CLAUSE-STATUS errors, not production benefit or harm verdicts.** This change
lives in the diagnostic clause-aggregation lane. A wrong clause status is not a wrong efficacy
verdict, and nothing in this matrix licenses a claim about matched Full/Null efficacy, which
Gate 2 and the discordant-table path decide.

**The three decision outcomes stay separate and are never summed into a single flip rate.**
The development flip rate of 0.1436 in `low_heterogeneity` mixes wrong directional verdicts with
honest abstentions and cannot distinguish a repair that makes the instrument more careful from
one that makes it more wrong. That conflation is why the number was uninterpretable when this
session reported it. Rows 5 and 6 are counts of wrong claims; row 7 counts honest refusals to
claim. A rise in row 7 is a cost to report. A rise in row 5 or 6 is a kill.

---

## 6. The differential reference

**Mechanism revisable. Independence is frozen.**

`tests/test_aggregation_differential.py::test_1000_seeded_inputs_match_reference` passes on
`main` and fails under the candidate peel. This was measured both ways; it is caused by the
change, not pre-existing.

The reference must therefore move, and it carries **two distinct obligations that are separately
owed**:

- **Obligation A — the numerics of the selected method.** The reference re-derives the amended
  estimator **from this specification**, not by calling production. It must not import or invoke
  the production peel, the admission helper, `_ebmom`, or `fit_skill`. A reference that calls the
  implementation tests only that the code equals itself.
- **Obligation B — the method selection itself.** The reference **may branch on the method
  production selected**, because independently re-deriving a seeded bootstrap would mean
  reproducing its exact RNG stream, which is cloning rather than independence. But branching on
  the selection is NOT accepting it. **The reference may not treat production's method choice as
  correct merely because production made it.** A wrong method choice must be killed by
  independent admission tests, not by the differential comparison, which cannot see it.

Discharging obligation B: `tests/test_aggregation_fit.py::test_marginal_heterogeneity_is_refused_not_fitted`
(a known-unidentified input must be refused), `::test_admission_verdict_is_deterministic`,
`::test_seed_covers_sum_sq_not_just_w_and_n`, `::test_canonical_encoding_is_order_independent`,
plus acceptance-matrix rows 1 and 2, which bound the selection's error rate rather than any
single verdict.

**Mutation receipt required, and it must name the obligation each kill belongs to.** Ship a
receipt proving the suite *can* reject a wrong implementation: mutate production, show the gate
goes red, and attribute the kill **to a named assertion**, recording whether that assertion
serves A or B. A mutation that fails to compile, or that reddens a different suite than the one
whose job the behaviour is, is not a kill — record which assertion failed, never the exit code
alone. **A receipt that kills only obligation-A mutants leaves the method-selection surface
unmeasured and does not discharge this section.**

*Revisit if:* the existing reference is already independent by construction, in which case say so
with the file evidence and only its expectations move.

---

## 7. Confirmatory protocol

**FROZEN — non-negotiable.**

1. This amendment is frozen when merged. Sections 1, 3-level, 5, and the kill criterion do not
   change afterwards.
2. The gate is built to this specification. Building may use seed `20260902` freely; anything it
   produces is development evidence and is labelled as such.
3. **The confirmatory run uses a root seed chosen by someone other than the session that wrote
   this amendment or built the gate**, and every regime and replicate seed is derived from that
   root by the harness. The commitment and reveal sequence is section 9; the identity the
   receipt must carry is section 8.
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
- **Settled on a checkable fact:** the #368 route is **(b)**, sufficient statistics, because
  route (a)'s discordant table does not exist in the aggregation lane and #368 is open
  (section 4). *Revisit if:* #368's migration lands, at which point route (a) supersedes and
  `sum_sq` becomes redundant rather than wrong.
- **Revisable with new evidence:** how the differential reference moves (section 6).
  *Revisit if:* it is already independent, with file evidence.
- **Ruled by the maintainer 2026-08-31, now frozen:** `HETEROGENEITY_TEST_ALPHA = 0.05`, on the
  derivation and power cost tabled in section 3. It does not move on a confirmatory result.
- **Non-negotiable:** the `tie_heavy_null` and `tie_heavy_signal` regimes and their generative
  models (section 4). They are the only registered surfaces on which the tie defect can fire,
  and neither substitutes for the other.
- **Ruled by the maintainer 2026-09-01, now frozen:** the finite-bootstrap decision rule
  `p_boot = (1 + count)/(B + 1)`, `admit iff p_boot <= 0.05`; the full seed-derivation procedure;
  `R = 1000`; the 10 percent bias bound; the exact-binomial calibration rule at level 0.01;
  identical synthetic worlds for `main` and candidate; and removal of the interval-coverage row.
- **Ruled 2026-09-02, by the adjudication session the maintainer's close scheduled; overturnable
  by the maintainer:** the heterogeneity target is the encoded clause mean, for as long as the lane
  decides on the encoded rate under route (b). Section 3's null amended by supersession to the
  pooled categorical. *Revisit if:* `fit_skill` migrates to the discordant representation, at
  which point the target becomes the decisive rate by construction and this item expires; or the
  section 1 decision rule stops being a threshold on the encoded rate; or a tracked ruling names
  this lane's target explicitly.


---

## OPEN, AND IT BLOCKS THE CONFIRMATORY RUN: two frozen clauses disagree

**RULED 2026-09-02.** The heterogeneity target is the **encoded mean**; the losing clause is section
3's tie treatment, amended above by supersession; section 4's regime stands. The ruling, its scope,
the crux question for the maintainer, and the fork it leaves open (repair now on the current
encoding, or hold `BLOCKED` and build route (a) first) are recorded on #360 in the comment of
2026-09-02. Step 3 of the sequence below was then run: row 1 on `tie_heavy_null` admitted **0 of 40** (exact binomial p = 0.27 against 0.05; calibrated). The two clauses now agree. The same smoke fires the kill criterion in three regimes, and re-running it at `7d50b4a` shows the two tie-free instances were already present before the null was amended and were not reported; see the development evidence in section 0 and the ticket comment of 2026-09-02. The text below is kept
unedited as the record of the question as it stood.


**Found by the registered `tie_heavy_null` regime on a development smoke, before any
confirmatory run. Not fixed here, because fixing it means choosing a heterogeneity target,
and that is
adjudication.**

Measured, root seed `SMOKE_NOT_CONFIRMATORY`, R=40:

| homogeneous world | admission rate | acceptance row 1 |
|---|---|---|
| tie-free, common rate 0.65 | 0.025 (1/40) | calibrated |
| `tie_heavy_null` as registered | **0.400 (16/40)** | **FAILS**, exact binomial p = 3.0e-11 |

The defect is tie-specific and it is not Monte Carlo noise.

### Mechanism

`tie_heavy_null` is registered as a **common decisive win probability** `q = 0.75` with a tie
probability of 0.40. Tie counts are therefore random. Conditional on a clause's REALISED tie
fraction `q_k`, its expected observation is

```
E[X_k | q_k] = 0.5 q_k + (1 - q_k) * 0.75 = 0.75 - 0.25 q_k
```

which VARIES with `q_k`. With `n = 25` and `t = 0.40`, `sd(q_k) = 0.098`, so the conditional
means carry variance `0.25^2 * 0.0096 = 6.0e-04`. The regime is homogeneous **marginally** and
heterogeneous **conditionally on the realised tie counts**.

Section 3's null holds tie counts FIXED and gives every clause the same ENCODED mean. So the
null reproduces no conditional variation, while the data carry `6.0e-04` of it. The observed
statistic therefore exceeds the null quantile far more often than `alpha`, and the gate
over-admits by roughly eightfold.

### The inconsistency, stated plainly

Two frozen clauses describe different hypotheses:

- **Section 4** registers `tie_heavy_null` with a common **decisive** rate.
- **Section 3** specifies a null holding the common **encoded** mean.

Those are not the same null, and the 40 percent is exactly that disagreement. Each clause is
defensible on its own terms:

- If the heterogeneity target is the **decisive** rate, tie counts are an ancillary
  nuisance, the regime is right, and the null must hold the decisive rate common.
- If the heterogeneity target is the **encoded** mean, the null is right, and the regime
  does not generate a null world at all: it generates conditionally heterogeneous data.

Note that the second reading makes the `tie_heavy_null` label wrong rather than the code wrong.

### Why this session is not deciding it

Choosing between them decides **what the hierarchical lane measures heterogeneity IN**, which is
a specification question, not an implementation one. It also interacts with the lane-authority
correction above: the diagnostic clause-aggregation lane consumes encoded `{0, 0.5, 1}`
observations, while the production efficacy lane consumes discordant counts.

Tuning either clause after seeing a 40 percent admission rate is exactly the move this
amendment exists to prevent. **No threshold, regime, or kill criterion has been changed in
response to this measurement.**

### What must happen before a confirmatory root seed is spent

1. The maintainer rules on the heterogeneity target: the decisive rate, or the encoded mean.
2. Whichever clause loses is amended openly, superseding this text rather than overwriting it.
3. Row 1 is re-measured on a development smoke to confirm the two clauses now agree.
4. Only then is the root seed generated and the single confirmatory run performed.

Running the confirmatory matrix now would burn the seed on a contract that contradicts itself,
and its row-1 failure would be uninterpretable: it could not distinguish a mis-calibrated gate
from a mis-specified regime.

---

## 8. Receipt identity: semantic and execution

**FROZEN.** Neither identity alone supports independent replay, so the confirmatory receipt
carries both.

**Measurement (semantic) identity** — what was measured:

```
amendment SHA
estimator definition (section 2)
alpha / B / R
registered regimes and their generative parameters
oracle definitions (section 4)
acceptance matrix and kill criterion (section 5)
```

**Execution identity** — what actually ran:

```
final branch SHA
Python / NumPy / SciPy versions
harness digest and verifier digest
confirmatory root seed
per-regime and per-replicate seed derivation
raw-output manifest hash
the exact command line
```

A receipt missing either half is not replayable, and a claim resting on it is not checkable.
Explicit no-change outcomes are recorded rather than omitted: a row that did not move is
evidence, and its absence is indistinguishable from a row that was never run.

---

## 9. Seed commitment and reveal

**FROZEN.** The root seed is committed before it is revealed, so it cannot be replaced after
anyone has seen a result. This follows the precedent already used in this programme for a
private pre-registration committed by digest before disclosure.

1. Freeze and push the implementation and harness SHA.
2. The maintainer generates a 256-bit root seed. The implementing session does not see it.
3. `SHA256(root)` is committed or publicly timestamped in the run stub, before the root is
   disclosed.
4. The root is revealed only after that commitment exists.
5. The harness runs ONCE.
6. The root is published and verified against the prior commitment.

Step 3 is what makes the run falsifiable by a third party: without it, "we used seed X" is an
assertion, and with it, it is a check anyone can perform.

---

## 10. Appendix: researcher degrees of freedom

**Every choice made while developing this change, recorded because hiding them would be the
defect.** The smoke runs below are legitimate development evidence; concealing them, not
performing them, would be the problem.

| degree of freedom | what was done |
|---|---|
| estimator families tried | four: per-clause peel, pooled peel, ANOVA intraclass-correlation, full marginal-likelihood EB |
| development seed | `20260902`, used for all four family comparisons and the finite-K bias study |
| variance denominator | `/K` and `/(K-1)` compared over 4000 replicates against the closed-form bias |
| clipping | investigated; `max(v,0)` measured firing on 2.3 percent of `low_heterogeneity` replicates, moving the retained mean by about 8e-6 |
| smoke runs | R=3 and R=20, root seed `SMOKE_NOT_CONFIRMATORY`, throwaway. Used to prove the harness executes and that mutant M-A3 is detectable |
| fixtures | the EB-path fixture was widened from n=10 to n=50; the original n=10 case was retained as an explicit refusal test rather than deleted |
| mutants | six, listed in the mutation receipt, five killed and one survivor preserved |
| tooling failure | one clean-restoration attempt failed silently through a `/tmp` path the interpreter could not see, so a "clean" comparison row was actually the mutant. Caught because both rows printed identically; the affected numbers were re-measured after a surgical revert |
| amendments | this document has been amended four times before any confirmatory run: the initial supersession of the mean statistic, the maintainer's ratification pass, the workspace-review pass that corrected the null, the oracle, and the #368 scope, and the 2026-09-02 supersession of the null's tie treatment on the heterogeneity-target ruling |
| code changed after seeing smoke output | yes, and named: the admission-conditioned bias collection in the harness, the encoded-mean null, and the exact tie oracle. All three were corrections to defects the smoke runs and review exposed, not tuning toward a passing result. None of them moved a registered threshold, regime, or the kill criterion |
| amendment of the null after the ruling | 2026-09-02: the ties-fixed tie treatment superseded by the pooled categorical, on the heterogeneity-target ruling. The form (pooled, not per-clause plug-in) was stated before row 1 was re-measured. Row 1 was then re-measured once at R=40 under `SMOKE_NOT_CONFIRMATORY`; the result is reported whichever way it landed, above |
| demonstration behind the ruling | `scripts/ebmom_null_demo_7d50b4a.py`, R=40 and R=200, root seed `SMOKE_NOT_CONFIRMATORY`, on two worlds (the registered null, and a common-`p` split-`t` world the registered matrix does not contain). Run to exhibit the mechanism; the target was ruled on the cited facts, not on this table |
| cross-family challenge review of the ruling | two non-Anthropic reviewers, both-directions brief, before the ruling was posted; one PARTLY SOUND, one UNSOUND, converging that the target choice is a judgement. The ruling was rewritten to say so and to name the alternative. Receipt in the operator's steering repository, `docs/audit/t1-360-heterogeneity-target-S394/` |

**No registered regime, threshold, oracle definition or kill criterion has been changed in
response to a smoke result.** The changes listed in the last row are repairs to the apparatus.
The contract they are measured against is unchanged.

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
