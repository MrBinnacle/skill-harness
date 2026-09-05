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
