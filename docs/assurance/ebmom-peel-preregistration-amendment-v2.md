# Superseding pre-registration (v2): rows 5 and 6 become per-path false-claim rates against the generative truth, the refused path pools, and the admitted path is repaired before any seed is spent (#360, #405)

**Status:** DRAFT, 2026-09-05. NOT FROZEN. It freezes when section 4's condition is met and the
document is merged to `agent/issue-360` with the word DRAFT removed from this line, and not
before. No confirmatory root exists for it. Nothing in it may be cited as confirmation.
**Supersedes:** in `ebmom-peel-preregistration-amendment.md` (v1, at `13f0fbb`): section 5 rows
5 and 6 as kill rows, the kill criterion, and the refused-path decision procedure that v1 left
implicit (unpooled `Beta(1 + w, 1 + n - w)` under BH-FDR). Everything else in v1 stands by
reference: sections 1, 2, 3, 4, 6, 7, 8, 9 and 10, its regimes, its oracle definitions, its
generative models, `R = 1000`, `B = 999`, `HETEROGENEITY_TEST_ALPHA = 0.05`, and its recorded
REJECTED result of 2026-09-05, which stays in the record and is why this document exists (v1
section 7 item 5).
**Ruled on:** #405, comments of 2026-09-05 (the ruling, `issuecomment-5550928025`; its follow-up
and correction; and the S412 rulings posted the same day). The maintainer may overturn any item.
**Authored:** 2026-09-05, by the adjudication session that applied the pre-committed
form-selection rule and settled the kill test, after reading the per-path R = 1000 development
re-score on the burned root. It has seen every number in section 0 and has not seen, and by
construction cannot see, any confirmatory result under this document.

---

## How to treat this document

Same split as v1. **Frozen** items are the contract and do not move after a confirmatory result
lands. **Revisable** items are implementation proposals from a session that read the code and
did not build the gate; if a seam is wrong, say so with reasoning and change it. Items marked
**measured** are counts from the development re-score, re-runnable from the scripts named in
section 0. Items marked **ruled** are judgements, each with its *Revisit if*.

One thing is different from v1. This document is a bundle: five changes made together after a
failed run. Its only check is the fresh root under v1 section 9. Section 10 says so in the
appendix row that v1's appendix did not need.

---

## 0. Development evidence, preserved and quarantined

All of it is development evidence under v1 section 7 item 2. It informed every design choice
below and may not be cited as confirmation of anything.

### 0.1 Provenance

| item | value |
|---|---|
| generator, estimator, oracle, decision rule, score | this branch at `4bd4633` (unchanged through `13f0fbb`): `scripts/ebmom_acceptance_matrix.py`, `src/skill_harness/aggregation/fit.py`, `errors.py` |
| worlds | the confirmatory root `f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`, burned on 2026-09-05 when the v1 run REJECTED; its 5,000 worlds are development evidence from that moment |
| scripts | steering repository, `docs/research/ebmom-405-rescore-S411/`: `rescore405.py` (per-path tally, per-cell cluster count), `rescore405_worlds.py` (per-world dump), `clustered_bound.py` (both tests per cell), `world_diag.py`, `find_fail_worlds.py`, `proto_hu.py` (the admitted-path probe) |
| faithfulness control | `cand`'s vs-oracle excess over `main` reproduces the v1 confirmatory JSON in all five regimes: (-12,488, -3,028, +81), (+2,294, +160, -3,835), (0, -727, +17), (0, +251, -2,436), (+875, -2, -4,423); checked by comparing the two JSON files field by field, not by eye. The re-score is scoring the worlds and the fit that rejected |
| Python / NumPy / SciPy | 3.13.1 / 2.5.2 / 1.18.0 |

### 0.2 Columns

`oracle`: the decider that knows the true hyperprior, scored against the same truth; a scorer
self-check, never a candidate. `main`: `baseline_fit`. `cand`: the branch as v1's harness scores
it (unpooled refused path, raw threshold). `cand_prod`: the branch as production decides the
refused path (PASS gated on `bh_fdr_passes`). `cand_bpA`, `cand_bpB`: the two pooled fallbacks
of the 2026-09-05 ruling section 2. `cand_hu`: `cand_bpB` plus the admitted-path probe of
section 4. The path label is the candidate's admission verdict and is applied to every column,
so "the refused path" names one set of worlds for all of them.

### 0.3 Per-path counts at R = 1000, `false / decisions (false-bearing worlds / decision-bearing worlds)`

`n/t` = no decisions of this kind on this path.

**`small_n_bite`** (979 of 1,000 admitted)

| column | admitted 5c | admitted 6c | refused 5c | refused 6c |
|---|---|---|---|---|
| `oracle` | 156 / 6,445 (147/979) | 4 / 80 (4/79) | 1 / 89 (1/20) | n/t |
| `main` | 1,328 / 26,495 (716/979) | **437 / 3,510 (347/952)** | 22 / 408 (15/21) | 2 / 26 (2/17) |
| `cand` | 608 / 13,936 (331/962) | 22 / 369 (22/229) | 22 / 408 (15/21) | **25 / 129 (17/21)** |
| `cand_prod` | same | same | n/t | **25 / 129 (17/21)** |
| `cand_bpA` | same | same | 4 / 160 (3/18) | n/t |
| `cand_bpB` | same | same | 18 / 220 (3/17) | n/t |

**`low_heterogeneity`** (687 of 1,000 admitted)

| column | admitted 5c | admitted 6c | refused 5c | refused 6c |
|---|---|---|---|---|
| `oracle` | 987 / 28,525 (512/687) | n/t | 423 / 11,719 (232/313) | n/t |
| `main` | 453 / 17,353 (294/687) | **203 / 504 (176/340)** | 192 / 6,743 (140/313) | 27 / 84 (27/75) |
| `cand` | 831 / 24,302 (395/687) | **3 / 4 (3/4)** | 158 / 5,923 (128/313) | **347 / 744 (212/283)** |
| `cand_prod` | same | **3 / 4 (3/4)** | 0 / 139 (0/60) | **347 / 744 (212/283)** |
| `cand_bpA` | same | **3 / 4 (3/4)** | 429 / 10,852 (192/313) | n/t |
| `cand_bpB` | same | **3 / 4 (3/4)** | 773 / 16,251 (244/313) | n/t |

**`benign_large_n`** (1,000 of 1,000 admitted; no refused path)

| column | admitted 5c | admitted 6c |
|---|---|---|
| `oracle` | 581 / 93,091 (431/1000) | 232 / 35,330 (212/1000) |
| `main` | 578 / 93,040 (428/1000) | 333 / 37,151 (273/1000) |
| all candidates | 578 / 93,023 (428/1000) | 299 / 36,424 (250/1000) |

**`tie_heavy_null`** (39 of 1,000 admitted; every clause truly 0.65, so every FAIL is false)

| column | admitted 5c | admitted 6c | refused 5c | refused 6c |
|---|---|---|---|---|
| `oracle` | 0 / 7,800 | n/t | 0 / 192,200 | n/t |
| `main` | 0 / 500 | n/t | 0 / 8,395 | n/t |
| `cand` | 0 / 3,075 | n/t | 0 / 8,005 | **251 / 251 (219/219)** |
| `cand_prod` | 0 / 3,075 | n/t | 0 / 1 | **251 / 251 (219/219)** |
| `cand_bpA` | 0 / 3,075 | n/t | 0 / 112,337 | **4 / 4 (3/3)** |
| `cand_bpB` | 0 / 3,075 | n/t | 0 / 120,466 | n/t |

**`tie_heavy_signal`** (1,000 of 1,000 admitted; no refused path)

| column | admitted 5c | admitted 6c |
|---|---|---|
| `oracle` | 1,293 / 57,908 (722/1000) | 2 / 181 (2/170) |
| `main` | 162 / 17,345 (145/1000) | 0 / 81 (0/77) |
| all candidates | 338 / 22,722 (222/999) | n/t |

The v1 kill cell here (+875 wrong PASS against the oracle) is a 1.5 percent false-PASS rate
against the truth, with the oracle itself at 2.2 percent.

### 0.4 The two tests, cell by cell

Appended when the per-world dump (`rescore405_worlds.py`, started 2026-09-05T14:43Z) completes:
the table printed by `clustered_bound.py`, giving for every cell the world-block 99 percent lower
bound of the 2026-09-05 ruling and the one-per-world exact binomial of section 2, with their
verdicts side by side. Every verdict that decides an item in this document is already fixed by
the counts in 0.3 (a cell whose false-bearing worlds are all selected still passes, or whose
selected decisions are all false still rejects), and section 3 says so cell by cell; the table
adds the bound column and the drawn counts.

### 0.5 The four admitted-path FAIL worlds in `low_heterogeneity`, read directly

`find_fail_worlds.py` names them: worlds 255, 316, 600, 783. `world_diag.py` refits each:

| world | `latent_raw` (truth 0.00225) | fitted `c` (truth 100) | `p_boot` | FAIL clause | wins / 25 | true `theta` | plug-in `P(theta > 0.60)` | oracle |
|---|---|---|---|---|---|---|---|---|
| 255 | 0.00525 | 42.3 | 0.001 | c36 | 6 | 0.540 (true FAIL) | 0.0464 | UNDECIDED |
| 316 | 0.00484 | 45.7 | 0.001 | c33 | 5 | 0.646 (false) | 0.0369 | UNDECIDED |
| 600 | 0.00344 | 65.7 | 0.001 | c186 | 4 | 0.617 (false) | 0.0425 | UNDECIDED |
| 783 | 0.00463 | 49.6 | 0.001 | c13 | 6 | 0.628 (false) | 0.0361 | UNDECIDED |

One mechanism, four times: the latent variance overshoots by 1.5 to 2.3 times, the fitted
concentration comes out at half the truth or less, the posterior under-shrinks a clause that
drew 4 to 6 wins of 25 against a true mean above 0.60, and its tail lands a hair under 0.05. The
oracle at the true concentration abstains on all four. This is the concentration-uncertainty
class the 2026-09-05 ruling section 4 named as the first to be measured if the park lifted.

### 0.6 The admitted-path probe (`proto_hu.py`), measured

Normal-approximation hyperparameter uncertainty carried into the decision (section 4 states the
form). On the four worlds above: worlds 255 and 600 move to UNDECIDED (255 was the one true
FAIL); worlds 316 and 783 stay FAIL at `P = 0.0495` and `0.0432`. `low_heterogeneity` at
R = 40 on `SMOKE_NOT_CONFIRMATORY`: admitted 5c moves from 39 / 1,029 to 35 / 932, and the
wrong-PASS excess over `main` for the form-B column drops from +248 to +171. At R = 1000 on the
burned root (`proto-hu-lowhet-R1000.log`): admitted 5c moves from 831 / 24,302 (3.4 percent,
395 of 687 worlds) to 668 / 21,677 (3.1 percent, 364 worlds); the wrong-PASS excess over `main`
for the form-B candidate drops from +7,862 to +6,230 and its abstention rises from -8,595 to
-7,602; **admitted 6c moves from 3 of 4 to 2 of 2, both false, two worlds** (316 and 783), which
section 2.1 still rejects (`p = 0.0025`). The class narrows the tail and does not clear it.

---

## 1. What is superseded, stated plainly

| v1 item | v2 |
|---|---|
| Row 5, wrong PASS vs oracle, any positive excess over `main` kills | reported only (section 5 row 5) |
| Row 6, wrong FAIL vs oracle, any positive excess over `main` kills | reported only (section 5 row 6) |
| Kill criterion: any rise in wrong PASS or wrong FAIL against `main` in any regime | replaced by section 5 rows 5c and 6c per path, section 2's test |
| Refused path decided by unpooled `Beta(1 + w, 1 + n - w)`, PASS gated on BH-FDR in production and ungated in the harness | refused path pools (section 3, form B), decided by the locked rule, no BH-FDR; the harness scores what production runs |
| No admitted-path mechanism | the admitted path carries hyperparameter uncertainty into the decision (section 4); freeze is conditional on its development measurement |

The reasons are the 2026-09-05 ruling's section 1, unchanged: the comparator `main` breaks the
rule it stands in for (12.4 percent and 40 percent false among its FAILs at R = 1000); "wrong
against the oracle" is a regret, not an error rate; zero tolerance on a paired count has no
reference to sampling variability; and the promise the lane makes (INVARIANTS section 1) is
tested by none of the frozen rows. What v2 gives up is the per-cell guarantee that the candidate
is never more wrong than `main` at a boundary `main` abstains at; that guarantee was never a
property of the estimator.

---

## 2. Rows 5c and 6c: definition, test, and what is reported beside them

**FROZEN.**

| # | quantity | kill test |
|---|---|---|
| 5c | false-PASS rate among PASS decisions: `#{PASS and true theta_k <= 0.60} / #{PASS}` | section 2.1, null `p = 0.05` (the complement of the locked `PASS_P = 0.95`), level `0.01` |
| 6c | false-FAIL rate among FAIL decisions: `#{FAIL and true theta_k > 0.60} / #{FAIL}` | the same, null `p = 0.05` (the locked `FAIL_P`) |

Per regime and per path (admitted, refused). Each cell is its own kill. A cell with zero
decisions of its kind reports not testable, never passed. Truth is the true encoded clause mean
the generator returns (`ebmom_acceptance_matrix.py`, `draw_world`'s second return) and the v1
harness discards.

### 2.1 The kill test: exact binomial over one decision per world

1. Take the worlds on the path with at least one decision of the row's kind. Their number is
   `G`, the cell's cluster count.
2. From each such world select one decision of that kind by a seeded draw: seed = first 8 bytes,
   big-endian, of SHA-256 over `<root>|<regime>|<world>|<row>` (`5c` or `6c`), feeding
   `random.Random`, choosing uniformly among that world's decisions of that kind sorted by
   `clause_id` (Python `str` order). The selection is fixed by the root before any decision
   exists.
3. Count the selected decisions that are false. Exact binomial, one-sided greater, null
   `p = 0.05`, level `0.01`. Rejection fails the row.

**Why this and not the world-block bootstrap the ruling registered.** Worlds are independent by
construction (one seed each, derived from the root). One decision per world gives `G`
independent Bernoulli outcomes. Under the per-claim reading of the promise, every PASS is made
at `P(theta > 0.60) >= 0.95` and every FAIL at `<= 0.05`, so under calibration each selected
decision is false with probability at most 0.05, and their sum is stochastically dominated by
`Binomial(G, 0.05)`. The test has size at most 0.01 at every `G` from 1 upward, with no
asymptotics, no resampling and no minimum-cluster number. The world-block percentile bound the
ruling registered is 0 by construction whenever four or fewer worlds carry a false decision,
whatever the rate, because a resample of `R` worlds then omits every false-bearing world more
than 1 percent of the time; the S412 ruling on #405 carries the measured table. The bound is
kept as a reported diagnostic (2.2) and demoted from the kill.

**What the null is.** The per-claim promise, not an average. A lane that is overconfident on one claim
and underconfident on the next, averaging 5 percent, does not keep the promise
INVARIANTS section 1 makes, and this test says so. *Revisit if:* the promise is re-read as an
average rate, in which case the null changes and the dominance argument must be replaced.

**What it discards.** All decisions but one per world. In the refused-path 5c cell of
`low_heterogeneity` under form B that is 16,251 decisions reduced to 313 trials. The discarded
decisions share their world's mean error with the kept one; where the cell is sparse nothing is
lost, and where it is dense the power is still ample (a fallback wrong on two thirds of its
worlds rejects at any `G` above a dozen).

### 2.2 Reported beside the kill, per cell

- `false / decisions`, `G`, and `g` (false-bearing worlds), as the re-score prints them.
- The world-block 99 percent lower bound as the 2026-09-05 ruling defined it (resample the
  regime's `R` worlds with replacement, `B = 999`, the 10th order statistic; a resample with no
  decisions on the path counts as 0 and is counted). Where it and 2.1 disagree the disagreement
  is reported.
- Rows 5, 6 and 7 against the oracle for the candidate and `main` with the paired excess,
  exactly as v1, so every number stays comparable with the REJECTED run.
- Rows 5c and 6c for the oracle itself: a harness self-check. The decider that knows the true
  hyperprior must pass both rows on every testable cell, or the regime's generative model or its
  oracle is mis-specified. At R = 1000 it passes every testable cell in the four landed regimes
  (section 0.3).
- A reliability table per regime: fitted `P(theta > 0.60)` binned in tenths with the empirical
  frequency of `theta > 0.60` in each bin, candidate and `main`. Diagnostic.

### 2.3 The harness scores the refused path as production decides it

**FROZEN, and it binds the build.** v1's harness scored the refused path by the raw threshold on
unpooled posteriors; production gated PASS on `bh_fdr_passes` (`engine.py:355-363`, `status.py`
B1). Under v2 the refused path is section 3's pooled posterior decided by the locked rule, in
production and in the harness alike, and a fixture feeds one refused world through `fit_skill`
plus `engine`/`status` and through the harness and asserts identical clause statuses. A harness
that scores a procedure production does not run is not a confirmatory harness.

---

## 3. The refused path pools, and the form is B

**Ruled (policy) and measured (form).** Policy from the 2026-09-05 ruling section 2: on a refused
fit the lane fits a hierarchical posterior that shares strength across clauses, decided by the
locked rule; the refusal stays typed and visible in provenance. The unpooled fallback's FAIL
promise breaks wherever it fires: 251 of 251 false in `tie_heavy_null`, 347 of 744 in
`low_heterogeneity`, 25 of 129 in `small_n_bite` (section 0.3), and `main`'s breaks the same way.

**The pre-committed rule** (posted 2026-09-05T09:35:53Z, before the deciding regime landed at
09:38:28Z): freeze the form that passes both per-path rows in every regime at R = 1000 on the
burned root; if both do, the one with fewer added abstentions (row 7); if neither, reopen with
two named diagnostics. It was committed against "the clustered bound"; section 2 replaced the
test, so the rule is applied here under BOTH tests and the branch under each is stated.

**Applied.** Form A fails one cell: refused-path 6c in `tie_heavy_null`, 4 FAILs from 3 worlds,
all false, one selected per world, 3 of 3 false, `p = 1.25e-4` under section 2.1 (the world-block
bound passes it by vacuity, `g = 3`). Form B mints no FAIL on any refused path in any regime and
its refused-path 5c cells sit at 4.76 percent (`low_heterogeneity`, 773 / 16,251), 8.2 percent
by count but 3 false-bearing worlds of 17 (`small_n_bite`, 18 / 220; at most 3 of 17 selected
decisions can be false, and `P(Binomial(17, 0.05) >= 3) = 0.050`, so the cell passes under every
possible draw), and 0 elsewhere. Under the world-block bound both forms pass every cell and the tie-break
selects the fewer added abstentions, which is B (-114,646 against A's -106,521 in
`tie_heavy_null`; -8,595 against -7,031 in `low_heterogeneity`). **Under either test the rule
lands on form B.** The third branch does not fire and its two diagnostics are not owed.

**Form B, frozen:**

```
on refusal:  v_bound = the admission test's critical order statistic (the (1 - alpha) quantile of
             the null bootstrap distribution of latent_raw, already in provenance)
             c_bound = mu (1 - mu) / v_bound - 1
             non-positive c_bound -> unpooled Beta(1 + w, 1 + n - w), typed and counted
             decide each clause by the locked rule on Beta(mu c_bound + w, (1 - mu) c_bound + n - w)
```

The estimator is continuous across the admission boundary: an admitted fit at the boundary and
a refused fit at the boundary shrink identically. Full pooling (`c -> infinity`) is excluded by
arithmetic (it PASSes every clause at the grand mean in `low_heterogeneity`, where 15 percent of
clauses are truly at or below 0.60). Form A's R = 1000 numbers stand beside B's in section 0.3.

**BH-FDR on the pooled path: retired, as a design choice.** It was a multiplicity brake on
unpooled posteriors. On a hierarchical posterior it is a different multiplicity story bolted onto
one path; what bounds correlated false PASSes now is the per-path 5c kill.

*Revisit if:* the confirmatory run fails a refused-path cell under form B, which reopens the form
with the two diagnostics the ruling named (a bootstrap-percentile upper bound against the Wald
bound on the refused worlds; the distribution of `latent_raw`, `v_bound`, `c_bound` and the
revert count on that path).

---

## 4. The admitted path: the park is lifted, and freeze waits on the repair

**Ruled.** The 2026-09-05 ruling parked every admitted-path mechanism on one condition: the
admitted path passes 5c and 6c, per path, in every regime at R = 1000. It does not. Admitted 6c
in `low_heterogeneity` is 3 false of 4, one decision per world, `p = 4.8e-4` under section 2.1.
The world-block bound passed it by vacuity, which is the reason section 2 replaced the bound and
not a reason to keep the park. The mechanism is read directly in section 0.5: concentration
overshoot on admitted fits, the class the ruling named.

**What is built, revisable in form, frozen in kind.** The admitted-path decision integrates over
the sampling uncertainty of the fitted hyperprior rather than plugging in `(alpha_hat, beta_hat)`.
The first class measured (section 0.6, `proto_hu.py`):

```
mu_s ~ N(mu_hat, total_var / K)
v_s  ~ N(latent_raw, (sqrt(2 / (K - 1)) total_var)^2), truncated below at the admission
       critical order statistic (the fit was admitted, so v > crit)
c_s  = mu_s (1 - mu_s) / v_s - 1, non-positive draws dropped and counted
P_k  = mean over S = 200 seeded draws of P(theta > 0.60 | Beta(mu_s c_s + w_k, (1 - mu_s) c_s + n_k - w_k))
```

decided by the locked rule on `P_k`; seeds from SHA-256 over `<canonical clause encoding>|hu`
under v1 section 3's frozen derivation so the decision stays deterministic. Measured on the four
worlds it clears two of four and leaves two false FAILs at 0.0495 and 0.0432: the normal
approximation understates the tail an admitted fit is selected from (the winner's curse the
2026-09-05 panel named against the "least shrinkage" derivation applies here too). The second
class to measure if the first does not clear the row: the admission-conditioned parametric
bootstrap of `(mu_hat, latent_raw)` under the fitted hyperprior (draw `K` clause means from
`Beta(alpha_hat, beta_hat)`, draw `w_k`, recompute the moments, keep draws above `crit`), which
replaces the normal by the finite-sample distribution the model itself implies. The third, if
neither clears it: a hierarchical posterior over `(mu, c)` with a stated weak prior. Each is
measured at R = 40 then R = 1000 on the burned root, in that order, and the first that meets the
condition below is frozen; the others' numbers are reported beside it.

**Freeze condition, FROZEN, and what it is.** This document freezes only when the candidate as
built passes rows 5c and 6c under section 2.1 on every testable cell of every registered regime
on the burned root, and the oracle self-check passes every testable cell. A candidate that fails
a cell on the burned root is predicted to fail the fresh root and does not get one. That is the
lesson of v1's run, applied before the seed rather than after.

It is a seed-conservation rule and a selection-control rule, not a validity claim. Trying
mechanism classes in sequence on the burned worlds until one passes is selection on those
worlds, and a pass so obtained is biased toward passing. Cross-family review named this and
the control is adopted: **the mechanism class is selected on worlds 0 to 499 of each regime and
the freeze condition is evaluated on worlds 500 to 999**, the halves fixed here before any class
beyond the first has been run (the four admitted FAIL worlds of section 0.5 split two and two:
255 and 316 select, 600 and 783 evaluate). The fresh root then tests the selected build once,
which is the only test of it that carries no selection. A rejection on the fresh root in a cell
that passed the evaluation half falsifies the stability of the R = 1000 counts and is reported
as such, never re-run.

*Revisit if:* no class clears admitted 6c in `low_heterogeneity` at R = 1000, in which case the
question is whether the FAIL promise on that path is reachable at `n = 25` by any estimator, and
it goes back to #405 as a design question with the three measurements attached.

---

## 5. Acceptance matrix, v2

**FROZEN once this document freezes.** Every quantity reported for every registered regime and,
for rows 5c to 7, per path. A run that reports a subset is not a confirmatory run.
Replication `R = 1000` per regime; identical synthetic worlds for `main` and the candidate.

| # | quantity | bound |
|---|---|---|
| 1 | false admission under homogeneity (`tie_heavy_null`) | v1 row 1, unchanged |
| 2 | admission rate by regime | reported (v1) |
| 3 | relative bias of `latent_raw` over all replicates | v1 row 3, unchanged |
| 4 | fallback rate and reason distribution; plus the pooled-path revert count (non-positive `c_bound`) | reported |
| 5c | false-PASS rate among PASS decisions, per path | **kill**: section 2.1 rejects at level 0.01 against 0.05 |
| 6c | false-FAIL rate among FAIL decisions, per path | **kill**: section 2.1 rejects at level 0.01 against 0.05 |
| 5c*, 6c* | the same rows for the oracle | harness self-check; a failure voids the regime's result and is reported as a harness defect, not a candidate verdict |
| 5, 6 | wrong PASS, wrong FAIL vs oracle, candidate and `main`, paired excess | reported, never a kill |
| 7 | added abstention, per path | reported as an evidence-coverage cost |
| 8 | world-block 99 percent lower bound per cell, `G`, `g` | reported diagnostic beside 5c and 6c |
| 9 | reliability table per regime | reported diagnostic |
| 10 | production-faithfulness fixture: one refused world through `fit_skill` + `engine`/`status` and through the harness, identical statuses | must pass; a failure voids the run |

**Kill criterion.** Any rejection in any 5c or 6c cell, on either path, in any registered regime,
rejects the candidate. Rollback state is `main`. `agent/issue-360` stays unmerged as the
development artifact.

**What the criterion's level is, stated so it is not misread.** Each cell is a test of size at
most 0.01. The criterion is a union over up to 20 testable cells (five regimes, two paths, two
rows), so a candidate that keeps the promise in every cell is rejected somewhere with probability
up to about 0.18. That is a property v1's criterion had too (any positive excess in any regime)
and it is kept deliberately: the rows exist so that any cell can convict, and a correction that
divides the level across cells would return the sparse tail to the blind spot section 2.1 was
chosen to remove. The claim the criterion supports is "no cell showed the promise broken", not
"this procedure has level 0.01".

**What a sparse cell can and cannot say.** A rejection in a cell of two to four claims is valid:
a calibrated lane that makes two FAIL claims is killed only when both are wrong, at most 1 in
400. A pass in such a cell is weak evidence, because a lane that happens to make one claim, or
none, passes too. The build is therefore held to the oracle's behaviour on that side (section
4's freeze condition), and a sparse pass on the fresh root is reported as a pass with its `G`,
never as a demonstration.

---

## 6. Prediction for the confirmatory run, to be completed at freeze

Stated now for the parts the burned root already determines; the admitted-path cells depend on
section 4's outcome and are written at freeze, before the root is generated.

- Refused path, form B: 5c passes in every regime (point estimates 4.76 percent and below, 313
  and 21 refused worlds); 6c not testable in every regime (form B mints no refused-path FAIL).
- `main`: fails 6c on the admitted path in `small_n_bite` and `low_heterogeneity` (12.4 and 40
  percent false), passes 5c everywhere. Reported, not a verdict on `main`.
- `oracle`: passes every testable cell.
- Rows 5, 6, 7 vs oracle: under form B the candidate's wrong-PASS excess over `main` in
  `low_heterogeneity` is +7,862 on the burned root before any admitted-path mechanism and
  +6,230 under the first class measured; whichever class freezes, its R = 1000 figure on the
  burned root is the prediction, and its abstention excess moves the other way. Both are
  reported costs, not kills. Under v1 this regime's +2,294 was a kill; under v2 the same
  regime's refused path makes 773 PASS claims where the unpooled fallback made 158, at a false
  rate under the oracle's, and the number that grows is a coverage figure.
- **A property of the FAIL cells, stated so nobody is surprised by it:** on the admitted path in
  `low_heterogeneity` the oracle makes no FAIL claim in 687 worlds and the candidate makes two
  to four. A cell that small is a valid test under section 2.1 (two claims, both false,
  `p = 0.0025`) and its outcome on a fresh root is dominated by how many FAIL claims happen to
  be made. The freeze condition therefore asks the mechanism to match the oracle's behaviour on
  that side, which is to abstain, rather than to be lucky.
- A NOT_REJECTED result is the prediction if and only if section 4's condition was met on the
  burned root; a REJECTED result in any cell that passed on the burned root falsifies the
  stability of the R = 1000 counts and is reported as such.

---

## 7. Mutation receipt, required before the run

Three mutants, each killed by a named assertion, obligation A or B per v1 section 6:

1. Pooling removed on the refused path (revert to unpooled): killed by the `tie_heavy_null`
   refused 6c assertion (251 of 251 false at R = 1000; any R above 40 suffices).
2. Per-path split removed (rows pooled): killed by an assertion that the refused-path cell in
   `low_heterogeneity` is reported separately with its own `G`, and that a pooled-only tally
   cannot produce it.
3. One-per-world selection replaced by all decisions: killed by an assertion on a fixture world
   with two correlated false decisions, where the all-decision test rejects and the registered
   test does not.

A fourth, if section 4 freezes a mechanism: the mechanism removed (plug-in restored), killed by
the admitted 6c cell in `low_heterogeneity` on the burned root.

---

## 8. Confirmatory protocol, receipt identity, seed commitment

v1 sections 7, 8 and 9 stand unchanged and are not restated. The fresh root is generated by the
maintainer after this document is frozen and the build has landed; its digest is committed by a
session that neither built nor ruled, before the root is revealed; the harness runs once. The
receipt carries both identities of v1 section 8, plus this document's SHA.

---

## 9. Decision status

- **Frozen at freeze:** section 2 (rows, test, reported set, production-faithful scoring);
  section 3's policy and form B; section 4's freeze condition; section 5; the kill criterion;
  section 7's mutants; v1's frozen items by reference.
- **Ruled, overturnable by the maintainer:** the kill test's replacement (section 2.1; the S412
  ruling on #405 carries the measured reason); the demotion of the vs-`main` comparison (the
  2026-09-05 ruling section 1 states what restoring it would cost: the comparator must first be
  shown to keep the promise in that cell).
- **A fork the maintainer owns, named by cross-family review:** whether the sparse admitted-path
  FAIL cell (`low_heterogeneity`, two to four claims in 687 worlds) is a confirmatory kill under
  section 2.1, as written here, or a **mechanism gate** (a pre-registered abstention requirement
  on that side, matched to the oracle, with the exact test kept for cells whose verdict is not
  dominated by how many claims happen to be made). One seat argued the second; the other argued
  a floor of any kind re-blinds the tail. This document takes the first because the promise is
  per claim and a valid rejection is a rejection; the second is recorded as the live
  alternative, and choosing it changes section 5's row 6c on that path only.
- **Not level 0.01 as a procedure:** the kill is a union over cells (section 5), by design.
- **Selected by measurement under a pre-committed rule:** form B (section 3), the same branch
  under both tests.
- **Revisable:** the form of the admitted-path mechanism (section 4), by the sequence stated
  there; the reliability table's binning; `S = 200`.
- **Open until freeze:** section 0.4 (both tests, every cell), 0.6 at R = 1000, `tie_heavy_signal`
  in 0.3, and section 6's admitted-path lines.

---

## 10. Appendix: researcher degrees of freedom

| degree of freedom | what was done |
|---|---|
| this bundle | five changes after a failed run: rows re-scored against truth, per path; the kill test replaced twice (exact-binomial-over-clauses to world-block bootstrap after the first panel, then to one-per-world exact after the S412 literature sweep and the vacuity table); the refused path pooled; the admitted path repaired. Its only check is the fresh root. |
| the kill test changed after the data were seen | yes. The reason is structural (the bound is 0 at four or fewer false-bearing worlds on any data) and was found by asking what a minimum-cluster number would rest on. The form-selection rule was applied under both tests and lands on B under each. The cell whose verdict the change flips is named (admitted 6c, `low_heterogeneity`) and it flips toward rejection. |
| worlds re-used | the burned confirmatory root, 5,000 worlds, seen in full before every choice here. Development evidence by v1 section 7 item 5; never a fresh root. |
| predictions | the 2026-09-05 ruling section 5 predicted `cand` fails refused 6c in `tie_heavy_null`, `low_heterogeneity` and `small_n_bite` and passes admitted 5c in all five: held in the four landed regimes. It did not predict the admitted 6c cell. Its R = 40 P4 missed (recorded there). |
| the admitted-path probe | one class run before this document was drafted, on four named worlds and at R = 40; reported whichever way it landed (two of four cleared). |
| withdrawn figures | two per-path rates derived by subtraction reached #405 and were corrected the same day; the script has no pooled-only counter left. |
| cross-family review | the 2026-09-05 ruling: two seats, both changed it. This document and the S412 rulings: two seats before posting, both PARTLY SOUND overall; they added the forking-path admission, the split-half freeze control, the family-wise statement and the sparse-cell reading, and named the mechanism-gate fork. Receipt: steering repository `docs/audit/t1-s412-sh405/`. |

No registered regime, oracle, generative model, admission level or `B` has moved.
