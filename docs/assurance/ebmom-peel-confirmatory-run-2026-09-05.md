# Confirmatory run stub: EB-MoM peel and heterogeneity gate (#360, #405)

This is the run stub that amendment section 9 requires. It exists so the root seed is committed
by digest BEFORE it is revealed, and so a third party can check that the seed used was the seed
committed. Each step below is appended in its own commit, in order. Nothing above a step is
edited when a later step lands.

## Step 1. Frozen implementation and harness

| item | value |
|---|---|
| branch | `agent/issue-360` |
| SHA | `4bd463310337c67c81b8b4e26a5878f3562ab6df`, pushed; `origin/agent/issue-360` agrees |
| amendment | `docs/assurance/ebmom-peel-preregistration-amendment.md` at that SHA |
| harness | `scripts/ebmom_acceptance_matrix.py`, sha256 `9986b0116d0cd6a6467efe4f0b59eef844169c2a14f048dec6d72457ceafa781` |
| estimator | `src/skill_harness/aggregation/fit.py`, sha256 `b0e0822ddd6466be983147bc01d5dd7806b127fc237e9584d58902c0dffcce07` |
| errors module | `src/skill_harness/aggregation/errors.py`, sha256 `2f8fee0d1b8dad1b5517fc98ff558b66273d11e41edd441b0502968d84f6a8b4` |
| Python / NumPy / SciPy | 3.13.1 / 2.5.2 / 1.18.0 |
| candidate under test | the branch as it stands: peel, admission test, BH-FDR fallback, plug-in concentration. No mechanism from #405 is built; the 2026-09-04 mechanism was withdrawn on 2026-09-05 (#405, `issuecomment-5548740369`) |

## Step 2. Who generated the root

The maintainer, in their own terminal, on 2026-09-05, after ruling "spend now" on #405 section
7.4. The session that built the gate did not see it. The session that wrote the 2026-09-05 ruling
received it only after step 1 was pushed, and holds it for step 4.

## Step 3. Commitment (this commit; the root is NOT in this file yet)

```
SHA256(root as 64 ASCII hex characters, UTF-8) = eb46d0ded40b42b22580f0fe107fa7ab3acf7c500d6ea2845800f13b6d256e97
SHA256(root as 32 raw bytes)                    = fcad9342c07d765d5d5fd337e408a4e96304e21a5e1d122a847724fef1f2727a
committed at                                    = 2026-09-05T02:48:18Z
```

Both encodings are given so the check does not depend on which one a verifier picks. The
harness consumes the root as the ASCII string (`derive_seed` joins it with `|` and hashes the
UTF-8 bytes), so the first line is the one that binds the run.

## Prediction, stated before the root is revealed

From the development record (S406 smoke at R = 40, S408 calibration and smoke B): the verdict
is REJECTED, with a positive wrong-PASS or wrong-FAIL excess over `main` in `low_heterogeneity`
(rows 5 and 6), `tie_heavy_null` (row 6) and `tie_heavy_signal` (row 5), at magnitudes near 25
times the R = 40 counts; row 1 calibrated on `tie_heavy_null`; row 3 inside the 10 percent bound
in every regime with nonzero latent variance. A NOT_REJECTED result would falsify the stability
of the R = 40 counts and would be reported as such.

## Step 5. The run (once)

| item | value |
|---|---|
| command | `PYTHONPATH=src PYTHONHASHSEED=0 python scripts/ebmom_acceptance_matrix.py --root-seed f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a --out docs/assurance/ebmom-peel-confirmatory-run-2026-09-05.json` |
| where | this worktree, branch `agent/issue-360`, tree = `4bd4633` plus the two stub commits `6d6835a` and `5fa03c5` (both touch `docs/assurance/` only; harness and estimator digests in step 1 unchanged) |
| started / finished | 2026-09-05T02:49:17Z / 2026-09-05T03:52Z, one process, 63 minutes |
| replicates | R = 1000 per regime, the registered value; `is_confirmatory: true` in the JSON |
| output | `ebmom-peel-confirmatory-run-2026-09-05.json`, 3,589 bytes, sha256 `124721b28d6d3619696fc49a40df2561d7edb8279cd8ac16bb4fc7f8ed8213c4` |
| stderr log | `ebmom-peel-confirmatory-run-2026-09-05.log`, 123025 bytes after the pre-commit hook normalised its line endings to LF, sha256 `5277c7595e9f8fe662d6da0a15cf2ee232c1e2e676ba751ddb8162351f6f7b1e` (1,295 fallback warnings and the R-check note; nothing else) |

## Step 6. Publication and verification of the root

```
root                         = f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a
SHA256(root ascii)           = eb46d0ded40b42b22580f0fe107fa7ab3acf7c500d6ea2845800f13b6d256e97
step-3 commitment (6d6835a)  = eb46d0ded40b42b22580f0fe107fa7ab3acf7c500d6ea2845800f13b6d256e97
match                        = yes
root_seed field in the JSON  = the same string
```

## Result: REJECTED

`kill_criterion_triggered: true`. Section 5 matrix, full, as the contract requires; every row
is reported including the ones that did not move.

| regime | admission rate | row 1 (calibration) | row 3 (rel. bias of `latent_raw`) | row 4 (fallback) | row 5 wrong PASS cand / `main` / excess | row 6 wrong FAIL cand / `main` / excess | row 7 abstention cand / `main` / excess |
|---|---|---|---|---|---|---|---|
| `small_n_bite` | 0.979 | n/a | -0.0147, in tolerance | 21 not identified | 7,881 / 20,369 / **-12,488** | 428 / 3,456 / **-3,028** | 81 / 0 / +81 |
| `low_heterogeneity` | 0.687 | n/a | -0.0175, in tolerance | 313 not identified | 2,294 / 0 / **+2,294** | 748 / 588 / **+160** | 12,313 / 16,148 / -3,835 |
| `benign_large_n` | 1.000 | n/a | +0.0001, in tolerance | none | 0 / 0 / 0 | 1,094 / 1,821 / **-727** | 68 / 51 / +17 |
| `tie_heavy_null` | 0.039 | 39 / 1000 admitted, exact binomial p = 0.127 against 0.05, **calibrated** | n/a (true variance 0) | 961 not identified | 0 / 0 / 0 | 251 / 0 / **+251** | 188,669 / 191,105 / -2,436 |
| `tie_heavy_signal` | 1.000 | n/a | +0.0001, in tolerance | none | 877 / 2 / **+875** | 0 / 2 / -2 | 36,244 / 40,667 / -4,423 |

Kill cells, all positive: `low_heterogeneity` row 5 (+2,294) and row 6 (+160), `tie_heavy_null`
row 6 (+251), `tie_heavy_signal` row 5 (+875). The frozen kill criterion is any positive excess in
any registered regime, so any one of the four rejects.

## The prediction, scored

Stated in step 3 before the root existed: REJECTED, positive excess in exactly those four cells,
row 1 calibrated, row 3 inside 10 percent everywhere. **Every part held.** The stated magnitude,
"near 25 times the R = 40 counts", was right in two cells (row 5 `low_heterogeneity` 21x, row 6
`tie_heavy_null` 21x) and wrong in two (row 6 `low_heterogeneity` 8x, row 5 `tie_heavy_signal`
51x). The direction and the cell set were the prediction; the multiplier was a gloss, and it is
recorded as missed where it missed.

What the run adds beyond the development record: row 1 is calibrated at R = 1000 (39 admissions
against an expectation of 50, p = 0.127), which the R = 40 smoke (0 of 40) could not establish;
row 3 is inside tolerance in every nonzero regime at the registered R; and the candidate's
improvements over `main` where it improves are large and now measured at scale (`small_n_bite`
-12,488 wrong PASSes, `benign_large_n` -727 wrong FAILs).

## What the contract says follows

Section 7 item 5, frozen: "A confirmatory run that fails does not license a second run at new
seeds. It licenses a new amendment, openly superseding this one, and the failed result stays in
the record." This file is that record. Rollback state is `main`; `agent/issue-360` stays unmerged.
The four questions the superseding amendment carries are stated on #405 in the 2026-09-05
ruling, section 7.3: how rows 5 and 6 are scored, the fallback policy on refusal, whether
`low_heterogeneity` as registered discriminates estimators, and which open mechanism class is
measured first. Each is a design ruling above #405 and goes to the reserved tier with
cross-family review before it is written.
