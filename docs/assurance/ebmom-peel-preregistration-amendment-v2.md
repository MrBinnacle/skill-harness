# Superseding pre-registration (v2): rows 5 and 6 become per-path false-claim rates against the generative truth, the refused path pools, and the admitted path is repaired before any seed is spent (#360, #405)

**Status:** FROZEN, 2026-09-05 (S414), on mechanism class 2. Section 4's condition was met at
R = 1000 in every regime and, under the S414 amendment, on 3,000 further burned-root worlds in
`low_heterogeneity` (section 0.7). No confirmatory root exists for it. Nothing in it may be cited
as confirmation.
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

**Measured.** The per-world dump (`rescore405_worlds.py`, started 2026-09-05T14:43Z) completed at
15:54Z across all five regimes. `clustered_bound.py` read it and printed the table below. Its
faithfulness control asserts that the per-world sums equal every cell of section 0.3 and refuses
to run otherwise; it did not refuse, so the per-world data and the per-path counts are the same
data.

Reading the columns. `G` is the decision-bearing worlds on the path, `g` the false-bearing worlds.
`bound99` is the world-block 99 percent lower bound of the 2026-09-05 ruling and `bound-verdict`
its call, marked `(vacuous)` where `p_none` exceeds 0.01 and the cell holds at least one false
decision, meaning the bound is 0 by construction and cannot reject at any rate. `exact_p` is the
all-decision exact binomial, valid only where every decision sits in its own world (`n == G`);
it is printed for reference and is not a kill. The columns right of the bar are section 2.1's
kill test: the selected false count over `G`, its exact p, its verdict, the interval `[kmin, kmax]`
that the counts permit any selection to reach, the count at which the cell rejects, and either
`fixed` (no selection changes the verdict) or `P(rej)`, the exact probability that a different
registered seed rejects the cell, computed as a Poisson-binomial tail over the per-world false
fractions.

One difference from the registered procedure, stated because it changes the realised numbers.
Section 2.1 selects a decision per world by a seeded draw over `clause_id`. This dump holds
per-world counts and not clause identities, so the script draws the selected decision's false
indicator as `Bernoulli(false_w / n_w)`. The two are equal in distribution, so every probability
column is exact; the realised `k` in a given cell is a different draw from the same law than the
harness will produce. The `[kmin, kmax]`, `rej>=`, `fixed` and `P(rej)` columns do not depend on
the draw at all.

```
regime             column    path     row  false/dec   G    g   rate    bound99  p_none  exact_p   bound-verdict | opw k/G  opw_p    opw   [kmin,kmax] rej>=  seed-dep
benign_large_n     cand      admitted 5c    578/93023  1000  428  0.0062  0.0056  0.000   1.00e+00  pass             |   6/1000 1.00e+00  pass  [  0,428] rej>=68   P(rej)=0.000
benign_large_n     cand      admitted 6c    299/36424  1000  250  0.0082  0.0072  0.000   1.00e+00  pass             |   6/1000 1.00e+00  pass  [  0,250] rej>=68   P(rej)=0.000
benign_large_n     cand      refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand      refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_bpA  admitted 5c    578/93023  1000  428  0.0062  0.0056  0.000   1.00e+00  pass             |   5/1000 1.00e+00  pass  [  0,428] rej>=68   P(rej)=0.000
benign_large_n     cand_bpA  admitted 6c    299/36424  1000  250  0.0082  0.0071  0.000   1.00e+00  pass             |   7/1000 1.00e+00  pass  [  0,250] rej>=68   P(rej)=0.000
benign_large_n     cand_bpA  refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_bpA  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_bpB  admitted 5c    578/93023  1000  428  0.0062  0.0055  0.000   1.00e+00  pass             |   8/1000 1.00e+00  pass  [  0,428] rej>=68   P(rej)=0.000
benign_large_n     cand_bpB  admitted 6c    299/36424  1000  250  0.0082  0.0071  0.000   1.00e+00  pass             |  16/1000 1.00e+00  pass  [  0,250] rej>=68   P(rej)=0.000
benign_large_n     cand_bpB  refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_bpB  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_prod admitted 5c    578/93023  1000  428  0.0062  0.0056  0.000   1.00e+00  pass             |   5/1000 1.00e+00  pass  [  0,428] rej>=68   P(rej)=0.000
benign_large_n     cand_prod admitted 6c    299/36424  1000  250  0.0082  0.0070  0.000   1.00e+00  pass             |   9/1000 1.00e+00  pass  [  0,250] rej>=68   P(rej)=0.000
benign_large_n     cand_prod refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     cand_prod refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     main      admitted 5c    578/93040  1000  428  0.0062  0.0056  0.000   1.00e+00  pass             |   4/1000 1.00e+00  pass  [  0,428] rej>=68   P(rej)=0.000
benign_large_n     main      admitted 6c    333/37151  1000  273  0.0090  0.0077  0.000   1.00e+00  pass             |  14/1000 1.00e+00  pass  [  0,273] rej>=68   P(rej)=0.000
benign_large_n     main      refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     main      refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     oracle    admitted 5c    581/93091  1000  431  0.0062  0.0056  0.000   1.00e+00  pass             |   9/1000 1.00e+00  pass  [  0,431] rej>=68   P(rej)=0.000
benign_large_n     oracle    admitted 6c    232/35330  1000  212  0.0066  0.0056  0.000   1.00e+00  pass             |   6/1000 1.00e+00  pass  [  0,212] rej>=68   P(rej)=0.000
benign_large_n     oracle    refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
benign_large_n     oracle    refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
low_heterogeneity  cand      admitted 5c    831/24302   687  395  0.0342  0.0314  0.000   1.00e+00  pass             |  26/687  9.44e-01  pass  [  0,395] rej>=49   P(rej)=0.000
low_heterogeneity  cand      admitted 6c      3/4         4    3  0.7500  0.0000  0.050   4.81e-04  pass (vacuous)   |   3/4    4.81e-04  FAIL  [  3,  3] rej>=3    fixed
low_heterogeneity  cand      refused  5c    158/5923    313  128  0.0267  0.0224  0.000   1.00e+00  pass             |   8/313  9.89e-01  pass  [  0,128] rej>=26   P(rej)=0.000
low_heterogeneity  cand      refused  6c    347/744     283  212  0.4664  0.4265  0.000   2.68e-239  FAIL             | 143/283  5.21e-106  FAIL  [ 65,212] rej>=24   fixed
low_heterogeneity  cand_bpA  admitted 5c    831/24302   687  395  0.0342  0.0311  0.000   1.00e+00  pass             |  17/687  1.00e+00  pass  [  0,395] rej>=49   P(rej)=0.000
low_heterogeneity  cand_bpA  admitted 6c      3/4         4    3  0.7500  0.0000  0.050   4.81e-04  pass (vacuous)   |   3/4    4.81e-04  FAIL  [  3,  3] rej>=3    fixed
low_heterogeneity  cand_bpA  refused  5c    429/10852   313  192  0.0395  0.0338  0.000   1.00e+00  pass             |   8/313  9.89e-01  pass  [  0,192] rej>=26   P(rej)=0.000
low_heterogeneity  cand_bpA  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
low_heterogeneity  cand_bpB  admitted 5c    831/24302   687  395  0.0342  0.0309  0.000   1.00e+00  pass             |  23/687  9.85e-01  pass  [  0,395] rej>=49   P(rej)=0.000
low_heterogeneity  cand_bpB  admitted 6c      3/4         4    3  0.7500  0.0000  0.050   4.81e-04  pass (vacuous)   |   3/4    4.81e-04  FAIL  [  3,  3] rej>=3    fixed
low_heterogeneity  cand_bpB  refused  5c    773/16251   313  244  0.0476  0.0429  0.000   9.26e-01  pass             |  10/313  9.53e-01  pass  [  0,244] rej>=26   P(rej)=0.001
low_heterogeneity  cand_bpB  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
low_heterogeneity  cand_prod admitted 5c    831/24302   687  395  0.0342  0.0310  0.000   1.00e+00  pass             |  24/687  9.76e-01  pass  [  0,395] rej>=49   P(rej)=0.000
low_heterogeneity  cand_prod admitted 6c      3/4         4    3  0.7500  0.0000  0.050   4.81e-04  pass (vacuous)   |   3/4    4.81e-04  FAIL  [  3,  3] rej>=3    fixed
low_heterogeneity  cand_prod refused  5c      0/139      60    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/60   1.00e+00  pass  [  0,  0] rej>=8    fixed
low_heterogeneity  cand_prod refused  6c    347/744     283  212  0.4664  0.4256  0.000   2.68e-239  FAIL             | 133/283  1.97e-93  FAIL  [ 65,212] rej>=24   fixed
low_heterogeneity  main      admitted 5c    453/17353   687  294  0.0261  0.0231  0.000   1.00e+00  pass             |  15/687  1.00e+00  pass  [  0,294] rej>=49   P(rej)=0.000
low_heterogeneity  main      admitted 6c    203/504     340  176  0.4028  0.3519  0.000   2.16e-125  FAIL             | 137/340  2.93e-85  FAIL  [104,176] rej>=28   fixed
low_heterogeneity  main      refused  5c    192/6743    313  140  0.0285  0.0236  0.000   1.00e+00  pass             |   8/313  9.89e-01  pass  [  0,140] rej>=26   P(rej)=0.000
low_heterogeneity  main      refused  6c     27/84       75   27  0.3214  0.2118  0.000   3.37e-15  FAIL             |  23/75   1.11e-12  FAIL  [ 21, 27] rej>=10   fixed
low_heterogeneity  oracle    admitted 5c    987/28525   687  512  0.0346  0.0319  0.000   1.00e+00  pass             |  26/687  9.44e-01  pass  [  0,512] rej>=49   P(rej)=0.000
low_heterogeneity  oracle    admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
low_heterogeneity  oracle    refused  5c    423/11719   313  232  0.0361  0.0318  0.000   1.00e+00  pass             |  11/313  9.15e-01  pass  [  0,232] rej>=26   P(rej)=0.000
low_heterogeneity  oracle    refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
small_n_bite       cand      admitted 5c    608/13936   962  331  0.0436  0.0394  0.000   1.00e+00  pass             |  32/962  9.95e-01  pass  [  0,331] rej>=65   P(rej)=0.000
small_n_bite       cand      admitted 6c     22/369     229   22  0.0596  0.0329  0.000   2.28e-01  pass             |  11/229  5.97e-01  pass  [  9, 22] rej>=21   P(rej)=0.000
small_n_bite       cand      refused  5c     22/408      21   15  0.0539  0.0308  0.000   3.89e-01  pass             |   1/21   6.59e-01  pass  [  0, 15] rej>=5    P(rej)=0.003
small_n_bite       cand      refused  6c     25/129      21   17  0.1938  0.1240  0.000   5.65e-09  FAIL             |   6/21   4.42e-04  FAIL  [  0, 17] rej>=5    P(rej)=0.403
small_n_bite       cand_bpA  admitted 5c    608/13936   962  331  0.0436  0.0395  0.000   1.00e+00  pass             |  27/962  1.00e+00  pass  [  0,331] rej>=65   P(rej)=0.000
small_n_bite       cand_bpA  admitted 6c     22/369     229   22  0.0596  0.0327  0.000   2.28e-01  pass             |  16/229  1.13e-01  pass  [  9, 22] rej>=21   P(rej)=0.000
small_n_bite       cand_bpA  refused  5c      4/160      18    3  0.0250  0.0000  0.050   9.61e-01  pass (vacuous)   |   0/18   1.00e+00  pass  [  0,  3] rej>=5    fixed
small_n_bite       cand_bpA  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
small_n_bite       cand_bpB  admitted 5c    608/13936   962  331  0.0436  0.0394  0.000   1.00e+00  pass             |  25/962  1.00e+00  pass  [  0,331] rej>=65   P(rej)=0.000
small_n_bite       cand_bpB  admitted 6c     22/369     229   22  0.0596  0.0334  0.000   2.28e-01  pass             |  15/229  1.75e-01  pass  [  9, 22] rej>=21   P(rej)=0.000
small_n_bite       cand_bpB  refused  5c     18/220      17    3  0.0818  0.0000  0.050   2.86e-02  pass (vacuous)   |   0/17   1.00e+00  pass  [  0,  3] rej>=4    fixed
small_n_bite       cand_bpB  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
small_n_bite       cand_prod admitted 5c    608/13936   962  331  0.0436  0.0392  0.000   1.00e+00  pass             |  24/962  1.00e+00  pass  [  0,331] rej>=65   P(rej)=0.000
small_n_bite       cand_prod admitted 6c     22/369     229   22  0.0596  0.0345  0.000   2.28e-01  pass             |  14/229  2.58e-01  pass  [  9, 22] rej>=21   P(rej)=0.000
small_n_bite       cand_prod refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
small_n_bite       cand_prod refused  6c     25/129      21   17  0.1938  0.1293  0.000   5.65e-09  FAIL             |   5/21   3.24e-03  FAIL  [  0, 17] rej>=5    P(rej)=0.403
small_n_bite       main      admitted 5c   1328/26495   979  716  0.0501  0.0467  0.000   4.67e-01  pass             |  51/979  4.02e-01  pass  [  0,716] rej>=66   P(rej)=0.008
small_n_bite       main      admitted 6c    437/3510    952  347  0.1245  0.1111  0.000   2.30e-66  FAIL             | 117/952  1.12e-18  FAIL  [ 18,347] rej>=65   P(rej)=1.000
small_n_bite       main      refused  5c     22/408      21   15  0.0539  0.0312  0.000   3.89e-01  pass             |   1/21   6.59e-01  pass  [  0, 15] rej>=5    P(rej)=0.003
small_n_bite       main      refused  6c      2/26       17    2  0.0769  0.0000  0.135   3.76e-01  pass (vacuous)   |   2/17   2.08e-01  pass  [  1,  2] rej>=4    fixed
small_n_bite       oracle    admitted 5c    156/6445    979  147  0.0242  0.0199  0.000   1.00e+00  pass             |  28/979  1.00e+00  pass  [  0,147] rej>=66   P(rej)=0.000
small_n_bite       oracle    admitted 6c      4/80       79    4  0.0500  0.0000  0.018   5.72e-01  pass (vacuous)   |   4/79   5.62e-01  pass  [  4,  4] rej>=10   fixed
small_n_bite       oracle    refused  5c      1/89       20    1  0.0112  0.0000  0.368   9.90e-01  pass (vacuous)   |   0/20   1.00e+00  pass  [  0,  1] rej>=5    fixed
small_n_bite       oracle    refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand      admitted 5c      0/3075     39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     cand      admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand      refused  5c      0/8005    961    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/961  1.00e+00  pass  [  0,  0] rej>=65   fixed
tie_heavy_null     cand      refused  6c    251/251     219  219  1.0000  1.0000  0.000   0.00e+00  FAIL             | 219/219  1.19e-285  FAIL  [219,219] rej>=20   fixed
tie_heavy_null     cand_bpA  admitted 5c      0/3075     39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     cand_bpA  admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand_bpA  refused  5c      0/112337  961    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/961  1.00e+00  pass  [  0,  0] rej>=65   fixed
tie_heavy_null     cand_bpA  refused  6c      4/4         3    3  1.0000  0.0000  0.050   6.25e-06  pass (vacuous)   |   3/3    1.25e-04  FAIL  [  3,  3] rej>=2    fixed
tie_heavy_null     cand_bpB  admitted 5c      0/3075     39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     cand_bpB  admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand_bpB  refused  5c      0/120466  961    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/961  1.00e+00  pass  [  0,  0] rej>=65   fixed
tie_heavy_null     cand_bpB  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand_prod admitted 5c      0/3075     39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     cand_prod admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     cand_prod refused  5c      0/1         1    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/1    1.00e+00  pass  [  0,  0] rej>=None fixed
tie_heavy_null     cand_prod refused  6c    251/251     219  219  1.0000  1.0000  0.000   0.00e+00  FAIL             | 219/219  1.19e-285  FAIL  [219,219] rej>=20   fixed
tie_heavy_null     main      admitted 5c      0/500      39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     main      admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     main      refused  5c      0/8395    955    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/955  1.00e+00  pass  [  0,  0] rej>=65   fixed
tie_heavy_null     main      refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     oracle    admitted 5c      0/7800     39    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/39   1.00e+00  pass  [  0,  0] rej>=7    fixed
tie_heavy_null     oracle    admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_null     oracle    refused  5c      0/192200  961    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/961  1.00e+00  pass  [  0,  0] rej>=65   fixed
tie_heavy_null     oracle    refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand      admitted 5c    338/22722   999  222  0.0149  0.0125  0.000   1.00e+00  pass             |  11/999  1.00e+00  pass  [  0,222] rej>=68   P(rej)=0.000
tie_heavy_signal   cand      admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand      refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand      refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpA  admitted 5c    338/22722   999  222  0.0149  0.0126  0.000   1.00e+00  pass             |  15/999  1.00e+00  pass  [  0,222] rej>=68   P(rej)=0.000
tie_heavy_signal   cand_bpA  admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpA  refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpA  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpB  admitted 5c    338/22722   999  222  0.0149  0.0126  0.000   1.00e+00  pass             |   4/999  1.00e+00  pass  [  0,222] rej>=68   P(rej)=0.000
tie_heavy_signal   cand_bpB  admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpB  refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_bpB  refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_prod admitted 5c    338/22722   999  222  0.0149  0.0126  0.000   1.00e+00  pass             |  10/999  1.00e+00  pass  [  0,222] rej>=68   P(rej)=0.000
tie_heavy_signal   cand_prod admitted 6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_prod refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   cand_prod refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   main      admitted 5c    162/17345  1000  145  0.0093  0.0077  0.000   1.00e+00  pass             |  11/1000 1.00e+00  pass  [  0,145] rej>=68   P(rej)=0.000
tie_heavy_signal   main      admitted 6c      0/81       77    0  0.0000  0.0000  1.000   1.00e+00  pass             |   0/77   1.00e+00  pass  [  0,  0] rej>=10   fixed
tie_heavy_signal   main      refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   main      refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   oracle    admitted 5c   1293/57908  1000  722  0.0223  0.0209  0.000   1.00e+00  pass             |  26/1000 1.00e+00  pass  [  0,722] rej>=68   P(rej)=0.000
tie_heavy_signal   oracle    admitted 6c      2/181     170    2  0.0110  0.0000  0.135   9.99e-01  pass (vacuous)   |   2/170  9.98e-01  pass  [  1,  2] rej>=17   fixed
tie_heavy_signal   oracle    refused  5c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
tie_heavy_signal   oracle    refused  6c      0/0         0    0     -       -    1.000      -     n/t              |          n/t  
wrote rescore405-R1000-f95e4de5-worlds-bounds.json
```

Four findings from the table.

**1. The two tests disagree in five cells, and every disagreement runs one way.** The bound passes
by vacuity where the exact test rejects. No cell anywhere rejects under the bound and passes under
the exact test.

| regime | column | cell | count | `g` / `G` | bound | exact test |
|---|---|---|---|---|---|---|
| `low_heterogeneity` | `cand` | admitted 6c | 3 / 4 | 3 / 4 | pass (vacuous) | **FAIL**, `p = 4.8e-4` |
| `low_heterogeneity` | `cand_prod` | admitted 6c | 3 / 4 | 3 / 4 | pass (vacuous) | **FAIL**, `p = 4.8e-4` |
| `low_heterogeneity` | `cand_bpA` | admitted 6c | 3 / 4 | 3 / 4 | pass (vacuous) | **FAIL**, `p = 4.8e-4` |
| `low_heterogeneity` | `cand_bpB` | admitted 6c | 3 / 4 | 3 / 4 | pass (vacuous) | **FAIL**, `p = 4.8e-4` |
| `tie_heavy_null` | `cand_bpA` | refused 6c | 4 / 4 | 3 / 3 | pass (vacuous) | **FAIL**, `p = 1.25e-4` |

The first four rows are one cell, not four: the admitted path is shared by every candidate column,
so the same four worlds appear under each. It is the cell that lifts the park (section 4). The
fifth row is the cell that fails form A (section 3). Both cells reject under every possible
selection: `P(rej) = 1.0`. This is the measured form of the argument section 2.1 makes in prose —
the bound's blind spot is not a hypothetical, it is where both of this document's live decisions
were taken.

**2. Every pass in the table is a pass the seed did not buy.** Of 120 rows, 75 are testable and 45
report no decisions of their kind. Of the 75, 31 verdicts are fixed by the counts and 44 could in
principle move with the seed. Quantified rather than left as a logical range: **the highest
rejection probability over seeds among all 74 passing-or-failing cells that passed is 0.0084**,
which is `main`'s admitted 5c cell in `small_n_bite` (1,328 false of 26,495, `G = 979`, rejecting
at 66 selected false, observed at 51). Every other passing cell is at or below 0.0032. No pass in
this table is a lucky draw.

One edge worth recording for the freeze evaluation: a cell with exactly one decision-bearing world
cannot reject at level 0.01 under any selection, because `P(Binomial(1, 0.05) >= 1) = 0.05`. One
cell here is that size (`tie_heavy_null`, `cand_prod`, refused 5c, `G = 1`) and its pass carries no
information. Section 5's rule that a cell with no decisions reports not testable rather than passed
should be read as covering this case in substance; the table reports `G` beside every verdict so a
reader can see it.

**3. One correction to what this section was expected to say.** The placeholder for 0.4 asserted
that every verdict deciding an item in this document is already fixed by the counts in 0.3. That is
true of both rejections above and of form B's refused 5c cell in `small_n_bite` (at most 3 of 17
selections can be false and the cell rejects at 4, so it passes under every draw). It is **not**
literally true of form B's refused 5c cell in `low_heterogeneity`: 773 false of 16,251 decisions
over 313 worlds, 244 of them false-bearing, rejecting at 26 selected false, observed at 10. A
selection reaching 26 exists. Its probability is **0.0007**. The form-selection conclusion is
therefore not fixed by the counts in the strict sense; it is stable at seven parts in ten thousand,
and section 3's branch does not change.

**4. A weakness in one piece of section 3's supporting evidence, reported rather than argued.**
Section 3 cites three cells where the unpooled fallback's FAIL promise breaks: 251 of 251 in
`tie_heavy_null`, 347 of 744 in `low_heterogeneity`, 25 of 129 in `small_n_bite`. As counts all
three are exactly as stated. Under the registered kill test the first two reject under every
selection, and **the third rejects with probability 0.40** — a coin flip, because its 25 false
FAILs sit in 17 of 21 worlds and the test keeps one decision per world. This is the cost section
2.2 names under "what it discards", now with a number on it. It does not touch the form choice:
form A is failed by a cell that rejects with probability 1, and form B mints no refused-path FAIL
in `small_n_bite` at all. It does mean the `small_n_bite` refused 6c cell should not be offered as
independent confirmation of the pooling policy, and section 3's other two cells carry that claim
unaided.

`clustered_bound.py` writes `rescore405-R1000-f95e4de5-worlds-bounds.json` beside the dump, holding
every column above per cell.

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

### 0.6 The admitted-path mechanism classes, measured

**Class 1, normal-approximation hyperparameter uncertainty (`proto_hu.py`).** Carried into the decision (section 4 states the
form). On the four worlds above: worlds 255 and 600 move to UNDECIDED (255 was the one true
FAIL); worlds 316 and 783 stay FAIL at `P = 0.0495` and `0.0432`. `low_heterogeneity` at
R = 40 on `SMOKE_NOT_CONFIRMATORY`: admitted 5c moves from 39 / 1,029 to 35 / 932, and the
wrong-PASS excess over `main` for the form-B column drops from +248 to +171. At R = 1000 on the
burned root (`proto-hu-lowhet-R1000.log`): admitted 5c moves from 831 / 24,302 (3.4 percent,
395 of 687 worlds) to 668 / 21,677 (3.1 percent, 364 worlds); the wrong-PASS excess over `main`
for the form-B candidate drops from +7,862 to +6,230 and its abstention rises from -8,595 to
-7,602; **admitted 6c moves from 3 of 4 to 2 of 2, both false, two worlds** (316 and 783), which
section 2.1 still rejects (`p = 0.0025`). The class narrows the tail and does not clear it.

**Class 2, the admission-conditioned parametric bootstrap (`proto_pb.py`), measured.** Section 4
names it as the class to measure if the first does not clear the row. It does not, so it was.
Draw K clause means from the fitted `Beta(alpha_hat, beta_hat)`, generate a synthetic world under
them preserving each clause's `n_k` and the pooled tie fraction the data carry, recompute the
moments `fit_skill` computes, keep the draw when the recomputed peel exceeds the admission critical
order statistic, and average the clause tail probability over `S = 200` kept draws. This replaces
class 1's normal approximation with the finite-sample distribution the fitted model itself implies.
Both classes centre their draws at the fitted values, so **neither corrects the winner's-curse bias
in the point estimate**; class 2 captures the shape of the sampling distribution, and that is the
whole of what it adds.

On the four worlds of section 0.5: 255, 316 and 600 move to UNDECIDED and 783 stays FAIL at
`P = 0.0429`. Class 1 cleared 255 and 600 only. World 255's clause is a true fail, so clearing it
is an abstention cost rather than a repair.

At R = 1000 on the burned root, admitted path, against the form-B plug-in column:

| regime | row | `cand_bpB` | class 1 | class 2 |
|---|---|---|---|---|
| `small_n_bite` | 5c | 608 / 13,936 | not run | 579 / 13,446 |
| | 6c | 22 / 369 (229 worlds) | not run | 16 / 267 (164 worlds) |
| `low_heterogeneity` | 5c | 831 / 24,302 (395/687) | 668 / 21,677 (364/687) | 666 / 21,607 (360/687) |
| | 6c | **3 / 4 (4 worlds)** | **2 / 2 (2 worlds)** | **1 / 1 (1 world)** |
| `benign_large_n` | 5c | 578 / 93,023 | not run | 578 / 93,028 |
| | 6c | 299 / 36,424 | not run | 293 / 36,330 |
| `tie_heavy_null` | 5c | 0 / 3,075 | not run | 0 / 1,762 |
| `tie_heavy_signal` | 5c | 338 / 22,722 (222/999) | not run | 338 / 23,009 (231/999) |

In `low_heterogeneity` class 2 removes 1,622 of the form-B candidate's wrong-PASS excess over
`main` (+7,862 to +6,240) and adds 1,073 abstentions; class 1 removed 1,632 and added 993. The two
classes differ on almost nothing except the row that decides.

**Class 2 rejects in no cell, in any regime, on any of the three world ranges, under either test.**
Two controls stated before the run both passed: the `cand_bpB` column computed inside the class-2
run reproduces this document's section 0.3 cells exactly, by a different code path; and every
refused-path cell is identical between `cand_bpB` and `cand_pb`, as their shared form B requires.

**The split-half score, and the reason this document is still a draft.** Section 4 selects on
worlds 0 to 499 and evaluates the freeze on 500 to 999. For `low_heterogeneity` admitted 6c:

| range | `cand_bpB` | class 2 | verdict on class 2 |
|---|---|---|---|
| selection, 0-499 | 1 / 2 in 2 worlds | 0 / 0 | not testable |
| evaluation, 500-999 | 2 / 2 in 2 worlds, rejects at `p = 0.0025` | 1 / 1 in 1 world | passes at `p = 0.050` |
| all 1,000 | 3 / 4 in 4 worlds, rejects at `p = 4.8e-4` | 1 / 1 in 1 world | passes at `p = 0.050` |

Section 4's freeze condition is met as written. It is met by a cell that **cannot reject at level
0.01 under any selection**, because with one decision-bearing world the largest attainable
statistic is one false selection and `P(Binomial(1, 0.05) >= 1) = 0.05`. `clustered_bound.py`
reports the rejecting count per cell, and for this cell it reports that no such count exists.

That is the vacuity section 2.1 removed from the world-block bound, reappearing through the
replacement test's power floor rather than the bound's zero atom. It is far narrower — one
decision-bearing world, against the bound's four-or-fewer false-bearing worlds at any rate — and it
is where the candidate now sits. Two readings sharpen it: on the selection half the cell is empty,
so the split-half control had nothing to control on this row; and a candidate that abstained on
that row entirely would pass the same way, which is why section 5 already holds the build to the
oracle's behaviour rather than to a sparse pass, and why the abstention columns above are the ones
that separate the two.

**This document therefore does not freeze on class 2 here.** Whether a `G = 1` cell satisfies
section 4's condition is a question about what the condition was for, and it belongs with the fork
section 9 already hands the maintainer between a confirmatory kill and a mechanism gate — a gate
matched to the oracle's abstention is precisely the instrument a one-world cell defeats and a gate
does not. Full measurements: the steering repository's `RESULTS-S413-class2.md`, and the reading
pre-registered before the run landed in `prereg-S413-class2-reading.md`.

### 0.7 The S414 extension: class 2 on worlds 1,000 to 3,999, and the freeze

The S414 ruling (section 4) evaluated the condition once more, on 3,000 burned-root worlds in
`low_heterogeneity` that were never generated for any class, under the same exact test, with the
rule committed before the run started and the pre-registered reading saying class 2 would more
likely fail it than pass it.

**Rule 1, reproducibility: passed.** All 1,000 committed per-world rows reproduce in the
extension's prefix, four columns, zero differences.

**Rule 2, the exact test on worlds 1,000 to 3,999: passed with power.** `false / decisions (G / g)`:

| column | admitted 5c | admitted 6c | refused 5c |
|---|---|---|---|
| class 2 | 2,164 / 67,607 (2,138 / 1,206), pass | **1 / 5 (5 / 1), `p = 0.226`, rejects at 3, pass** | 2,291 / 44,948 (859 / 643), pass |
| plug-in | 2,780 / 76,900, pass | **4 / 12 (12 / 4), `p = 0.0022`, FAIL under every selection** | same cell by construction |
| `main` | pass | 500 / 1,497, FAIL | pass; refused 6c 58 / 182 FAIL |
| `oracle` | pass | 0 / 0 | pass |

Four of class 2's five residual FAIL claims are true. The pre-registered scenarios put the false
fraction at 0.5 to 1.0 from the prior columns; the measured fraction is 0.2 on the new worlds and
0.33 over all 4,000 (2 of 6). The plug-in on the same worlds is the 0.33 the scenarios were built
from, and it fails. The removed abstention rule (at most one false) would also have passed and was
not the swing vote. Pooled: 6 decision-bearing worlds in 4,000, 2 false, `p = 0.033`, rejects at 3.

**The freeze executes.** Measurement of record: the steering repository's
`RESULTS-S414-extension.md`, `proto-pb-low_heterogeneity-R4000-f95e4de5.json`,
`clustered-bound-pb-R4000-f95e4de5-w1000-4000.log` and the full-range log beside it.

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

**Ruled S414, and it is an amendment to the condition above, made after class 2's result was
seen.** A cell at `G = 1` on worlds 500 to 999 decides the freeze in neither direction: the exact
test at `G = 1` cannot reach level 0.01 (a severity failure, not the bound's vacuity), so a pass
there is not the abstention-rather-than-luck this condition asks for, and a false claim there is
not a rejection. For that row the condition is then evaluated once more, on worlds 1,000 to 3,999
of the burned root in that regime: the same derivation (`derive_seed(root, regime, index)`), never
generated for any class, outside both halves, carrying no selection, and not the fresh root of
section 8. Rule: worlds 0 to 999 of the extension dump must reproduce the committed dump row for
row, or the extension is void; the class freezes if and only if the exact test rejects no cell of
that regime on worlds 1,000 to 3,999. A `G <= 1` cell on the extension passes, and there is no
second extension. The kill test does not change and no claim-count gate is added: the first draft
of the ruling carried one and cross-family review identified it as the section 9 gate under a new
name. The trigger and the test use disjoint worlds with independent seeds, so for a calibrated
candidate the extension withholds the freeze with probability at most 0.01 and can grant nothing
the letter withholds. Ruling, arithmetic and receipt: steering repository,
`docs/research/ebmom-405-rescore-S411/prereg-S414-freeze-ruling-extension.md`,
`docs/audit/t1-s414-sh437/`. *Revisit if:* the maintainer rules a `G = 1` cell satisfies the
condition as first written, which withdraws the extension.

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

Stated now for the parts the burned root already determines; the admitted-path cells were written
at freeze (S414), before the root is generated.

- **Admitted path, class 2, 5c:** passes in every regime. Burned-root point estimates 4.3 percent
  (`small_n_bite`, 579 / 13,446), 3.1 percent (`low_heterogeneity`, 666 / 21,607 at R = 1000 and
  2,830 / 89,214 over 4,000 worlds), 0.6 percent (`benign_large_n`), 0 (`tie_heavy_null`), 1.5
  percent (`tie_heavy_signal`). Rejection probability over seeds under 0.01 in every cell.
- **Admitted path, class 2, 6c, every regime but one:** passes. `small_n_bite` 16 / 267 across 164
  worlds; `benign_large_n` 293 / 36,330 across 247 worlds; the tie regimes mint no admitted FAIL.
- **Admitted path, class 2, 6c in `low_heterogeneity`: a distribution, not a verdict.** At the
  pooled burned-root rate (1.5 decision-bearing worlds per 1,000, false fraction 0.33) a fresh
  root of 1,000 worlds has `G = 0` with probability 0.22 (not testable), `G = 1` with 0.34 (a
  pass the test cannot fail), `G >= 2` with 0.44; the exact test rejects the cell with probability
  **0.07** at the measured figures, 0.16 at the rate's 95 percent upper bound. A rejection there
  is the sparse-cell outcome section 5 describes: it kills under the criterion as written, and it
  does not falsify the stability of the R = 1000 counts.
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
- A NOT_REJECTED result is the prediction, section 4's condition having been met on the burned
  root; a REJECTED result in any cell that passed on the burned root with a rejection probability
  over seeds under 0.01 falsifies the stability of the R = 1000 counts and is reported as such.
  The one cell that carries its own distribution above is excluded from that reading.

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
- **Closed since drafting:** section 0.4, both tests on every cell, from the completed per-world
  dump. It reports five cells where the tests disagree, all of them the bound passing by vacuity
  where the exact test rejects, and it puts a number on the seed-dependence of every verdict.
  Section 0.6, mechanism class 2 at R = 1000 on the burned root, scored on all three world ranges.
- **Ruled S414, overturnable by the maintainer:** a `G = 1` cell decides the freeze in neither
  direction, and the condition is evaluated once more on 3,000 never-generated burned-root worlds
  under the same exact test (section 4, the S414 paragraph). The mechanism-gate alternative in the
  fork above is declined a second time, on the ground that any claim-count threshold is set after
  the count is known; the kill test stays.
- **Frozen, S414:** mechanism class 2 (section 4's second class, `proto_pb.py`'s form, `S = 200`),
  on the extension result in section 0.7. Class 3 does not run. Section 6's admitted-path lines
  are written. Section 7's fourth mutant is owed by the build. The build's acceptance includes
  reproducing `proto-pb-all-R1000-f95e4de5.json`'s per-path cells at R = 1000 on the burned root,
  so that what the fresh root tests is the mechanism that was measured.

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
| cross-family review | the 2026-09-05 ruling: two seats, both changed it. This document and the S412 rulings: two seats before posting, both PARTLY SOUND overall; they added the forking-path admission, the split-half freeze control, the family-wise statement and the sparse-cell reading, and named the mechanism-gate fork. Receipt: steering repository `docs/audit/t1-s412-sh405/`. The S414 freeze ruling: two seats (PARTLY SOUND, UNSOUND); they removed a claim-count rule the first draft carried, relabelled the fresh-root risk table as scenario analysis, and forced the error-rate statement to be written; receipt `docs/audit/t1-s414-sh437/`. |
| the freeze condition evaluated on more worlds after a `G = 1` result | yes, S414. Section 4's condition was written for R = 1000 and the split halves; after class 2 landed at `G = 1` on the evaluation half, the condition was extended once to worlds 1,000 to 3,999 of the burned root, under the same test, with the rule committed before the worlds existed and the reading pre-registered as more likely to fail class 2 than to pass it. Strict direction only. The mechanism-gate alternative was declined twice. |

No registered regime, oracle, generative model, admission level or `B` has moved.
