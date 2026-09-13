# Confirmatory run stub, v2: EB-MoM per-path false-claim rates (#360, #405)

This is the run stub that v1 section 9 requires and v2 section 8 carries forward unchanged. It
exists so the root seed is committed by digest BEFORE it is revealed, and so a third party can
check that the seed used was the seed committed. Each step below is appended in its own commit,
in order. Nothing above a step is edited when a later step lands.

This run is under **v2**, `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`. The v1 run
of 2026-09-05 returned REJECTED, that result stays in the record, and v2 exists because of it. The
root spent on 2026-09-05 is spent. v2's status line states the position this stub answers:

> No confirmatory root exists for it. Nothing in it may be cited as confirmation.

## Step 1. Frozen implementation and harness

| item | value |
|---|---|
| branch | `agent/issue-360` |
| SHA | `681824dbf079679602dcf529bd8bf4f0a1b8868b`, pushed; `origin/agent/issue-360` agrees |
| amendment | `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`, sha256 `8bb6a4c9030c13fe77a138699a824f7784166ebb6d7a2e2fec699e59f08a1176` |
| harness | `scripts/ebmom_acceptance_matrix.py`, sha256 `84ee23c6a71a2ec18215486e9578f1dbfda0d64cf1afbf2220c39f5fad72105c` |
| estimator | `src/skill_harness/aggregation/fit.py`, sha256 `51884574aa8ee18438426a58287af9d18720a41a1b788c1ff9a168cbd51da866` |
| errors module | `src/skill_harness/aggregation/errors.py`, sha256 `2f8fee0d1b8dad1b5517fc98ff558b66273d11e41edd441b0502968d84f6a8b4` |
| Python / NumPy / SciPy | 3.13.1 / 2.5.2 / 1.18.0 |
| candidate under test | the branch as it stands: the peel, the admission test, form B pooling on the refused path, and mechanism class 2 on the admitted path |

### The estimator and the harness are unchanged since the accepted hand-off

`#444`, "v2 build 5 of 5", was accepted on 2026-09-06 at head `d2d31a779f2e131bc97aea2ffd179f536c51fe9a`, with its four criteria discharged there. The branch has moved eight commits since. Measured at this commitment:

```text
git diff --stat d2d31a7 origin/agent/issue-360 -- src/ scripts/
 scripts/ebmom_form_b_reproduction.py | 14 ++++++++++++--
 1 file changed, 12 insertions(+), 2 deletions(-)
```

**No file under `src/` changed, and the acceptance harness did not change.** The one script that moved is a reproduction script, not the harness under test. The eight commits are the `#458` frozen-reference repair, the `#452` and `#453` apparatus fixes, the receipts index, and the CI attribution and coverage-core work of `#519` and `#506`. So the implementation whose acceptance was discharged at `d2d31a7` is the implementation this root will test.

### All five v2 builds and every named blocker are closed

| item | state at this commitment |
|---|---|
| `#440` v2 build 1 of 5 | CLOSED completed |
| `#441` v2 build 2 of 5, form B | CLOSED completed |
| `#442` v2 build 3 of 5, class 2 on the admitted path | CLOSED completed |
| `#443` v2 build 4 of 5, per-path rows | CLOSED completed |
| `#444` v2 build 5 of 5, receipts and hand-off | CLOSED completed |
| `#458` frozen class-2 reference repair | CLOSED completed, landed at `5acbad6` |
| `#452` canonical evidence integrity | CLOSED completed |
| `#453` population integrity | CLOSED completed |
| `#447`, `#448` the three waived gate failures | CLOSED completed |

`#452` and `#453` are recorded because `#444`'s acceptance named them as open apparatus defects at the time it closed, and the six-layer gating property it states is monotonic: a downstream-valid result cannot compensate for an upstream-invalid evidence or population state. Both are repaired at this head.

### The branch has CI for the first time

`0e93309` (`#519`) put `faulthandler_timeout` on this branch and `681824d` (`#506`) put `COVERAGE_CORE=sysmon` on it. Run `34764117821` took all four Test cells green between 12m40s and 20m00s against a 25-minute budget that had previously killed every one of them. Before that this branch could not be gated at all.

## Step 2. Who generated the root

The maintainer, in their own terminal, on 2026-09-13, using a `System.Security.Cryptography.RandomNumberGenerator` fill of 32 bytes rendered as 64 lowercase hex characters. The root was written to a file on the maintainer's machine and never printed to the session.

**The session committing this stub did not see the root and did not build or rule on this work.** v2 section 8 requires the digest to be committed by a session that neither built nor ruled. This session (S446) performed board triage and body folds across three repositories; it wrote no part of v2, no part of the implementation, and neither the S411 nor the S414 ruling. It will read the root only after this commit is pushed.

## Step 3. Commitment (this commit; the root is NOT in this file yet)

```text
SHA256(root as 64 ASCII hex characters, UTF-8) = 5a37629960f9d90bb7eed52dab47ee34f7a74ac6de8916ad2995b362125dc0da
SHA256(root as 32 raw bytes)                    = 4ac62ed4782b9d9d0e3ed28c65c40b3e8b00e1989bb6e9eb66b81c00ce4ad29f
committed at                                    = 2026-09-13T16:19:32Z
```

Both encodings are given so the check does not depend on which one a verifier picks. The harness consumes the root as the ASCII string, since `derive_seed` joins it with `|` and hashes the UTF-8 bytes, so the first line is the one that binds the run.

A verifier checks this by taking the root revealed at step 4 and recomputing both lines.

## Prediction, stated before the root is revealed

**v2 section 6 already carries the prediction, and it was written at freeze on 2026-09-05 (S414), before this root existed.** It is not restated here in full and it is not amended. This stub records only which outcome section 6 nominates, so a reader of this file alone knows what was predicted.

**The predicted result is NOT_REJECTED**, section 4's condition having been met on the burned root.

Section 6 excludes exactly one cell from that reading, and the exclusion was registered in advance. The admitted-path class-2 cell 6c in `low_heterogeneity` carries its own distribution rather than a verdict: at the pooled burned-root rate a fresh root of 1,000 worlds gives `G = 0` with probability 0.22, `G = 1` with 0.34, and `G >= 2` with 0.44, and the exact test rejects that cell with probability **0.07** at the measured figures, or 0.16 at the rate's 95 percent upper bound. A rejection there kills under the criterion as written and does **not** falsify the stability of the R = 1000 counts.

A REJECTED result in any other cell that passed on the burned root with a rejection probability over seeds under 0.01 falsifies that stability, and is reported as such.

The result is reported whichever way it lands. Section 5's kill criterion is unchanged and no threshold, regime, oracle or row moves in response to what this run returns.

## Step 4. Reveal

Landed. See `ebmom-peel-confirmatory-run-v2-2026-09-13-step4-reveal.md`. Both digest encodings
recorded in step 3 were recomputed against the revealed root and both matched.

## Step 5. The run (once)

To be appended in its own commit. The receipt carries both identities of v1 section 8 plus v2's SHA.

The run makes no network call and costs no money. `scripts/ebmom_acceptance_matrix.py` at the SHA above imports `argparse`, `hashlib`, `json`, `random`, `sys`, `time`, `scipy.stats` and `skill_harness.aggregation.fit`. There is no HTTP client, no SDK and no credential. `#360`'s note of 2026-09-06 says the run would become a spend authorisation if it needed paid API calls. Measured at this commitment, it does not, so no spend authorisation is sought.

## Step 6. Disposition

To be appended. v2 section 5 keeps `agent/issue-360` unmerged until step 5 reports. No merge pull request is opened before then.
