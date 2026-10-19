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

| item | value |
|---|---|
| command | `PYTHONPATH=src PYTHONHASHSEED=0 python scripts/ebmom_acceptance_matrix.py --root-seed d77c7cd1f9daab006397b20330988074bc24b34c98ffa2827eebfc7195f7500f --out docs/assurance/ebmom-peel-confirmatory-run-v2-2026-09-13.json` |
| where | the S446 scratchpad worktree, local branch `agent/issue-360-stub` at `a6f40f9`, which is `origin/agent/issue-360` at `681824d` plus the three stub commits of steps 1 to 4, all under `docs/assurance/`; step 1's harness, estimator and errors digests re-measured unchanged at this commit (harness sha256 `84ee23c6a71a2ec18215486e9578f1dbfda0d64cf1afbf2220c39f5fad72105c`) |
| launched | OS-detached by S446 at 2026-09-13T16:23:35Z (process creation time, Windows PID 46788); the launching session closed with the run at 2,443 s of CPU and no JSON written |
| finished | 2026-09-13T18:03Z, one process, about 100 minutes wall clock; per-regime wall times from the log: `small_n_bite` 698 s, `low_heterogeneity` 1,095 s, `benign_large_n` 1,872 s, `tie_heavy_null` 1,134 s, `tie_heavy_signal` 1,173 s |
| replicates | R = 1000 per regime, the registered value; `registered_replicates: 1000`, `replicates: 1000`, `is_confirmatory: true` in the JSON |
| root in the JSON | `root_seed` equals the root revealed at step 4, byte for byte |
| output | `ebmom-peel-confirmatory-run-v2-2026-09-13.json`, 105,037 bytes, sha256 `3cd7437f5addd3e1e7b2a18c68e7870fa0a4b799fad7eacd2f07a98756601eaa` |
| stderr log | `ebmom-peel-confirmatory-run-v2-2026-09-13.log`, 180,155 bytes after its line endings were normalised to LF as v1's were, sha256 `9abd815ce3597991a95a7b5bf46e9253fbd918a68add2b5bd4587148c5443748`; 1,241 `Admission refused (latent_variance_not_identified)` lines and the five per-regime admission lines, nothing else |
| network | none; the harness at this SHA imports no HTTP client, no SDK and no credential, as this step's commitment stated, and the run cost no money |
| read by | S447, which did not build v2 and did not rule on it, and which read the root only from the step 4 file after the stub commits were on disk |

## Step 6. Disposition

### Result: NOT_REJECTED

`verdict: NOT_REJECTED`, `kill_criterion_triggered: false`, `rejecting_cells: []`, `rollback_state: main` not invoked. The oracle self-check passed on all 13 testable oracle cells (`failing_cells: []`), so no regime's result is voided. Relative bias of `latent_raw` is within the 0.1 tolerance in every regime where it is defined. `tie_heavy_null` calibrates: 57 of 1000 admitted against an expected 0.05, exact binomial p = 0.309 at level 0.01.

Section 6 predicted NOT_REJECTED and it landed. The one cell section 6 excluded in advance, the admitted-path 6c cell in `low_heterogeneity`, came out `G = 1`, two FAIL decisions, zero false, which section 6 gave probability 0.34. Under section 5 that is a sparse pass reported with its `G`, never a demonstration.

### The kill rows, candidate column `cand_pb`, every regime and both paths, plus pooled

Rate is false claims over decisions of that kind; p is the exact one-sided binomial against 0.05; a cell rejects at p < 0.01. "not testable" means no decision of that kind on that path.

| regime | 5c admitted | 5c pooled | 5c refused | 6c admitted | 6c pooled | 6c refused |
|---|---|---|---|---|---|---|
| `small_n_bite` (adm 0.988) | 565/13,317 = 0.0424, p 0.999 | 580/13,463 = 0.0431, p 0.999 | 15/146 = 0.103, p 0.37 | **21/241 = 0.0871, p 0.029** | 21/241 = 0.0871, p 0.029 | not testable |
| `low_heterogeneity` (adm 0.717) | 685/22,083 = 0.0310, p 0.998 | 1,505/37,769 = 0.0399, p 0.991 | 820/15,686 = 0.0523, p 0.55 | 0/2 = 0, G = 1, p 1 | 0/2, p 1 | not testable |
| `benign_large_n` (adm 1.000) | 604/92,776 = 0.0065, p 1 | same | not testable | 284/36,523 = 0.0078, p 1 | same | not testable |
| `tie_heavy_null` (adm 0.057) | 0/2,398 = 0, p 1 | 0/121,545, p 1 | 0/119,147, p 1 | not testable | not testable | not testable |
| `tie_heavy_signal` (adm 0.997) | 361/23,701 = 0.0152, p 1 | 388/24,063 = 0.0161, p 1 | 27/362 = 0.0746, p 1 | 0/2 = 0, G = 2, p 1 | same | not testable |

Seven cells are not testable, all listed in the JSON's `not_testable_cells`: four refused-path 6c cells, both `benign_large_n` refused cells, and the `tie_heavy_null` admitted 6c cell. Thirteen candidate cells were testable and none rejected.

**The nearest cell to a kill is stated so it is not lost.** `small_n_bite`, admitted path, row 6c: 21 false FAIL claims in 241, rate 0.087, p = 0.029 against the 0.01 level. It passes the criterion as written and would have rejected at level 0.05. The same cell for the comparator column `cand_bpB`, reported beside the candidate and not under test, is 31 of 350 at p = 0.0028, which rejects. Nothing moves in response: the candidate column was named before the root existed, the level was frozen at 0.01, and this paragraph exists so a reader sees the margin rather than the verdict alone.

### Reported beside the kill, never a kill

Wrong PASS, wrong FAIL and abstention against the oracle, candidate over `main`, negative meaning fewer: `small_n_bite` -13,570 / -3,216 / +79; `low_heterogeneity` +6,718 / -591 / -6,663; `benign_large_n` 0 / -889 / +11; `tie_heavy_null` 0 / 0 / -112,573; `tie_heavy_signal` +887 / -1 / -5,549. `main` itself rejects on 6c in `small_n_bite` (413/3,457, p about 1e-17) and on all three 6c paths in `low_heterogeneity` (p about 1e-66 and smaller), which is the defect v1 and v2 were written to remove; the candidate's 6c rates in those regimes are 0.087 and 0. Fallback reasons are all `latent_variance_not_identified`: 12, 283, 0, 943, 3 worlds per regime in the order above. The reliability tables are in the JSON under each regime's `reliability`.

### What this result establishes, and what it does not

It establishes that on one fresh committed root of 1,000 worlds per regime, the candidate kept the per-claim promise of section 2 in every testable cell at level 0.01, and that the R = 1000 counts measured on the burned root were stable enough to predict this. It does not establish a level-0.01 procedure (section 5 says so), it does not demonstrate the admitted-path FAIL side in `low_heterogeneity` (`G = 1`), and it leaves the maintainer's fork in section 9 exactly where it was: whether that sparse cell is a confirmatory kill or a mechanism gate is unchanged by a pass.

### Disposition

The candidate is not rejected. v2 section 5's condition for holding `agent/issue-360` unmerged, that step 5 has not reported, is discharged by this step. The next action is a merge pull request from `agent/issue-360` to `main`, opened after this step lands, with this file and the JSON as its evidence and a hand review of the branch's own diff still owed before merge. No threshold, regime, oracle, row or level moves. The v1 REJECTED result of 2026-09-05 stays in the record beside this one.

*Revisit if:* a third-party recomputation of the two step 3 digests against the step 4 root fails, or a re-run of the step 5 command at the step 1 SHA produces a JSON whose `regimes` differ in any cell; either voids this step.
