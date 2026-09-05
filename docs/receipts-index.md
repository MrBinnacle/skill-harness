# Measurement receipts index

One page for every measurement receipt this project has produced. Each entry
states **what it claims** and **what it refuses to claim**. A missing number
is a typed refusal, never an invented score.

Completeness is CI-gated: `tests/test_receipts_index.py` fails if any file in
the named receipt directories is absent from this page.

A rendered view of the SERS instances below is published at
[mrbinnacle.github.io/skill-harness](https://mrbinnacle.github.io/skill-harness/).
It is generated from `docs/sers/receipts/` by `python -m skill_harness.sitegen`
and covers that section only. This page stays the citable surface for every kind.

| Kind | Directory / surface |
| --- | --- |
| Case studies | [`docs/case-studies/`](case-studies/) |
| Findings | [`docs/findings/`](findings/) |
| Observation records | [`docs/observations/`](observations/) |
| Assurance reports | [`docs/assurance/`](assurance/) |
| Ratifications | [`docs/ratifications/`](ratifications/) |
| SERS instances | [`docs/sers/receipts/`](sers/receipts/) |
| Cost-beside-evidence join | `skill audit --extraction` (CLI surface) |

---

## Case studies

### [`docs/case-studies/double-ceiling-structurally-unmeasured.md`](case-studies/double-ceiling-structurally-unmeasured.md)

- **Claims:** On two deliberately hardened FTS5 tasks, Null passed 14/14 epochs
  (screens 3/3 + 3/3, paired k=8 Null 8/8); paired discordance \(\hat d = 0.00\)
  with Jeffreys 95% CI \([0.00, 0.26]\); pre-stated GO/NO-GO returned **NO-GO**;
  spend ≈$6.17; Full-vs-Null is structurally unmeasured at \(d \lesssim 0.5\)
  inside \(N_{\max}=40\).
- **Refuses to claim:** That the subject skill has no benefit in general; a
  keep/cut on transformative lift from this apparatus shakedown; that any
  published skill benchmark with an unreported Null ceiling is measuring help.

### [`docs/case-studies/ai-slop-sentinel-under-ablation.md`](case-studies/ai-slop-sentinel-under-ablation.md)

- **Claims:** Three independent pre-spend catches blocked a contaminated
  cross-vendor `ai-slop-sentinel` run before any subject model was called; the
  dogfood path returned all clauses **UNMEASURED** (no Tier-1 scorer / no
  calibrated Tier-2 judge) at $0.00 subject spend.
- **Refuses to claim:** A cross-vendor contribution metric for the skill; that
  UNMEASURED means the skill is worthless; that the aborted experiment's
  prediction was confirmed or falsified.

### [`docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md`](case-studies/displaced-enforcement-skill-ablation-blind-spot.md)

- **Claims:** Full-vs-Null skill-text ablation does not exercise hook-layer
  enforcement; a flat or null ablation result is not evidence that a
  displaced-enforcement discipline does nothing.
- **Refuses to claim:** A measured keep/cut for any specific hook-backed skill;
  that every null ablation is a blind-spot artefact; a magnitude for hook vs
  text contribution.

---

## Findings

### [`docs/findings/gitpull-cost-basis-unregisterable.md`](findings/gitpull-cost-basis-unregisterable.md)

- **Claims:** The rebuilt `gitpull` cost basis `#420` asks for cannot be
  registered at the design's own `n`. Computed through `project_pair_usd`, the
  measured run gives $1.10765200 per pair (input 539,011, output 2,963), so
  n = 32 costs $35.444864 and its rounded-up cap $35.45 breaches the $35.00
  ceiling DC-12 enforces; since DC-12 also fails a cap below the record's own
  worst case, the valid interval `[worst_case, 35.00]` is empty at n = 32. The
  control reproduces `RAT-0001` §6 exactly ($0.72974200 at the registered
  tokens), so the disagreement is in the tokens and not the arithmetic. The
  cache-aware alternative has no projector: `project_pair_usd` carries no cache
  term by design, `project_calibration_cost` models a judge prefix rather than
  a Gate-2 pair, and DC-9 bans hand arithmetic. The original projection was
  conservative in dollars and wrong in tokens at once — roughly sevenfold
  over-priced, 1.524 under-counted — so the cap held for a reason unrelated to
  the basis being sound.
- **Refuses to claim:** Any choice among the three paths that would make a
  record registerable (reduce `n` to 31, raise the $35 ceiling, build a
  cache-aware pair projector) — the fork is stated and deliberately not taken;
  that 98.6 percent cache-read share generalises beyond the single run that
  measured it; that n = 31 preserves power over the registered H1 region (no
  power recomputation was run); any change to `RAT-0001`'s registered fields;
  and any figure for a task family other than `gitpull` at this prompt and
  fixture.

### [`docs/findings/confound-status-silent-understatement.md`](findings/confound-status-silent-understatement.md)

- **Claims:** CONFOUNDED was unreachable: the runner wrote confounded
  verdicts as `inadmissible`, the admissible VIEW excluded them on state
  alone, and the engine's `all_confounded_flag` joined confound events
  against admissible rows only, so it was always false; measured on the
  detector fixture (status UNMEASURED/inadmissible, `vector.confounded=0`).
  Primary-confounded rows verifiably never enter aggregation. RESOLVED by
  #366: the engine reads the `inadmissibility_reason` the runner already
  persists, which `docs/INVARIANTS.md` #3 forces by forbidding read-time
  recomputation of evidence admissibility.
- **Refuses to claim:** That any historical report understated a confound
  (no production re-scan was run); that the admissible VIEW's
  `affected_clause_id` filtering question is settled (it was not touched);
  that a clause mixing confounded and otherwise-inadmissible verdicts is
  wholly confounded — it reads CONFOUNDED, and the split stays available in
  `confounded_verdict_count`.

### [`docs/findings/halfupdate-tie-sensitivity.md`](findings/halfupdate-tie-sensitivity.md)

- **Claims:** Under half-update (Tie=0.5, n+=1) the posterior converges to
  Beta(1+w+t/2, 1+l+t/2); measured at w=8, l=0, t=16: P(rate>0.60)=0.726
  (INCONCLUSIVE) where a drop-ties recompute gives 0.990 (PASSED), with
  posterior-mean shifts up to 0.178. The estimand was RULED on #368
  (2026-08-31): the discordant table is the estimand of record, half-update
  stays as the interim heuristic, and the measured sensitivity is recorded in
  `docs/INVARIANTS.md` §8.
- **Refuses to claim:** That the error is monotone dilution toward 0.5 — a
  sweep found 80,011 grid points where half-update RAISES P(rate>0.60); that
  the PASS-gate zero holds beyond the swept grid (w, l <= 60, t <= 80); that
  any minted production verdict flipped (no re-scan was run); that the
  0.60/0.95/0.05 thresholds transfer to the conditional parameter unexamined.

### [`docs/findings/d4-prompt-leak-into-null-arm.md`](findings/d4-prompt-leak-into-null-arm.md)

- **Claims:** A fourth leak direction, D4 — the task prompt states or points at
  the rule the skill supplies, so the Null arm is coached. Audited over all
  eight screen fixtures: 4 LEAK (`gitpull`, `appendonly`, `bayes`, `judgegate`),
  4 CLEAN (`tiebreak`, `dependabot`, `docx`, `microrun` root). Causation shown
  by A/B on `gitpull` holding fixture bytes, oracle, epochs and provider fixed
  and varying only the prompt: `p0` 1.000 (3/3) signposted against 0.000 (0/3)
  de-leaked. Second, independent ground for voiding the same rows: all four
  backfilled screens carry pin `2f76c933...` (2026-07-10) where the same
  `HarnessPin.capture(...)` arguments now produce `706cbaea...`.
- **Refuses to claim:** That the `git-pull-rebase-trap` skill arm's 1.000 (3/3)
  against 0.000 (0/3) is a verdict of record — it is unpaired, so it yields no
  discordant table, carries no registered estimand, ran on
  `openrouter/anthropic/claude-sonnet-4.5` rather than the pinned subject, and
  is n=3 per arm (Fisher one-sided p ~ 0.05); that any minted production verdict
  changed (no re-scan was run); that no pin-currency check exists anywhere in
  the repository — the supporting grep covers `src/` only and was not run
  against `tests/`; that the 4 CLEAN fixtures are free of D1/D2/D3, which this
  audit did not re-judge.

### [`docs/findings/pi-c-detector-blind-to-description-channel.md`](findings/pi-c-detector-blind-to-description-channel.md)

- **Claims:** Paired k=8 on `git-pull-rebase-trap`, one pin both arms
  (`5324feef...`), de-leaked prompt: discordant epochs x=6 of 8, d-hat 0.75,
  Jeffreys 95% interval [0.408, 0.944], GO at the pre-stated x >= 5; Null arm
  0/8. The write-time gate refused the pair with `ZeroInvocationError`: zero
  Skill tool calls across the Full arm under detector `v1-skill-tool-call`. The
  trajectories show no Skill call and no `SKILL.md` read in either arm, and a
  Full arm that merged in 6 of 8 epochs where every Null epoch rebased. The
  mounted skill acted through its frontmatter description in the skill listing,
  a channel the detector does not observe. The refusal is correct under the #46
  contract; the contract does not cover the channel.
- **Refuses to claim:** That `git-pull-rebase-trap` is KEEP (no admissible
  store row, no direction field in the registered micro-run template, no sized
  run); that the subject is the registered direct-Anthropic one (the run used
  OpenRouter, declared before launch, same route and pin in both arms); that
  6/8 is the skill's ceiling (two epochs rebased with the description present);
  that a description-only effect is detectable from a transcript.

### [`docs/findings/paired-ingest-nan-score-silent-tie.md`](findings/paired-ingest-nan-score-silent-tie.md)

- **Claims:** A NaN `score_value` flowed through `_score_to_float` and
  `_observation` scored it 0.5, recording a missing measurement as a tie;
  reproduced deterministically (a beneficial pair with one NaN epoch wrote
  observations [0.5, 1.0, 1.0]). RESOLVED by #363 at commit `210ac93`:
  `ParsedSample.score_value` carries `allow_inf_nan=False` and
  `_score_to_float` raises on a non-finite value.
- **Refuses to claim:** That any production `.eval` log has carried a NaN
  score (no historical re-scan was run); that any minted verdict was diluted
  in practice; that the repair reaches a caller which constructs neither
  `ParsedSample` nor calls `_score_to_float`.

### [`docs/findings/paired-ingest-boundary-undetectables.md`](findings/paired-ingest-boundary-undetectables.md)

- **Claims:** The arm-swap surface of `write_paired_evidence` is fully
  refused (role/condition check, contamination check, dead-treated-arm
  check — the third refuting the detector's own pre-registered
  invisibility prediction); a within-set epoch permutation in one arm is
  structurally invisible, pinned by a characterisation test, with damage
  bounded by within-arm score variance.
- **Refuses to claim:** That the permutation risk is repairable at the
  ingest boundary (it needs out-of-band pairing evidence from the log
  producer); that fabricated invocation traces are in scope.

### [`docs/findings/ebmom-missing-sampling-variance-peel.md`](findings/ebmom-missing-sampling-variance-peel.md)

- **Claims:** EB-MoM inverts the Beta moment map with no binomial
  sampling-variance peel, so recovered concentration deflates by ~`n/(n+c+1)`;
  measured against known hyperpriors (K=200, R=50, seed 20260902): relative
  error 0.690 at (mu*=0.65, c*=20, n=10) and 0.806 at (c*=100, n=25), with
  decision flip rates 0.1186 and 0.0816 against the locked 0.95/0.05
  thresholds; the benign regime (c*=10, n=100) recovers inside the
  pre-registered 0.25 tolerance.
- **Refuses to claim:** That any historical KEEP/CUT verdict flipped (no
  production run was re-scored here); a corrected estimator (that is repair
  ticket #360); flip rates at designs other than the three measured.

### [`docs/findings/why-naive-skill-benchmarks-mislead.md`](findings/why-naive-skill-benchmarks-mislead.md)

- **Claims:** On a 60-trial 4-arm config ablation, run-to-run output-token CV
  ≈17.6% RMS; k≈3 with/without designs cannot resolve small effects; standing
  config tax ≈+17.8k prefix tokens vs blank; deterministic pass/fail banks
  price cost not knowledge-layer benefit; task–skill matching samples on the
  dependent variable — each claim graded MEASURED / MECHANISM / DIRECTIONAL /
  EXPLORATORY.
- **Refuses to claim:** A keep/cut on any production skill; that every published
  skill benchmark is invalid; a single universal minimum sample size for all
  task classes.

### [`docs/findings/v0.2-preregistration.md`](findings/v0.2-preregistration.md)

- **Claims:** Locked pre-data Full-vs-Null plan (contrast, oracle, pin,
  stopping rule, budget); noise micro-run returned pre-stated **NO-GO** with
  \(\hat d = 0.00\), Jeffreys 95% CI \([0.00, 0.26]\); instrument detects
  transformative skills only under the locked constants.
- **Refuses to claim:** A sized benefit measurement under this registration
  until the task-sourcing condition is met; a portfolio-wide keep/cut sweep
  without declared multiplicity treatment; that Null means “no skills at all”
  (Null is stock agent minus the one skill under test).

### [`docs/findings/v0.2-reaim-gate.md`](findings/v0.2-reaim-gate.md)

- **Claims:** Entry-gate discipline for v0.2: unit inversion to skill-level
  Full-vs-Null first; differentiation is UNMEASURED + evidence admissibility + pin
  gating, not merely paired lift (field already has paired runners).
- **Refuses to claim:** That the 2026-07-08 lock was prior-art-complete (dated
  correction records the sweep ran after); that v0.2 re-implements an existing
  harness as its differentiator.

### [`docs/findings/aggregation-ci-coverage-under-sequential-stop.md`](findings/aggregation-ci-coverage-under-sequential-stop.md)

- **Claims:** Under the production sequential stopper, the unpooled Beta 95%
  credible interval missed nominal frequentist coverage on the registered grid
  (`small` under-coverage X=441/500; `large` over-coverage X=491/500); severity
  `WRONG_NUMBER`; closed by #187 anytime-valid confidence sequence leading the
  public report surface.
- **Refuses to claim:** That thresholds or aggregation math should be retuned to
  hide the miss; that the legacy posterior interval is a frequentist 95% CI
  under sequential stopping; that the two misses are equal operator damage.

### [`docs/findings/store-bricking-deadlock.md`](findings/store-bricking-deadlock.md)

- **Claims:** Two independent instances of one deadlock shape, both reproduced
  deterministically (#168): a comment-only edit to a shipped migration changed
  its recorded SHA-256, `apply_pending` then refused to open every existing
  evidence store, and the `schema_migrations` row that would clear the refusal
  is append-only — with **no re-stamp path anywhere in `src/`**, asserted as an
  absence test. The same shape recurs between `subject/ingest.py`'s self-hash
  and append-only `metric_versions`. Severity `CORRUPTION`. **Instance 6a is
  fixed (#169)**: a semantic digest separates commentary from schema, and a
  comment-only mismatch is cleared by an appended restamp record. The absence
  test above **stays green** — the repair adds no mutating path against the
  ledger — and the `strict=True` xfail that guarded the fix is now a plain
  regression test under the same name. **Instance 6b is fixed (#209)** by an
  AST-shape identity digest in which comments and formatting are not
  identity-bearing but **docstrings are**, since a docstring is reachable at
  runtime and can hold a threshold or rubric. The finding is **fully
  discharged**; both instances keep their raw-byte tamper digest and clear a
  commentary-only drift by appending a compensating record.
- **Refuses to claim:** Any rate, frequency or probability of the deadlock
  occurring in the field — this is an existence proof on a constructed store,
  not a measurement of incidence. That `ORACLE_METRIC_VERSION` bumping is a
  repair (it mints a **new metric identity**, so evidence before and after is
  no longer the same measurement). That read-only survival was mitigation: the
  escape hatch sets `PRAGMA query_only = ON`, so a store bricked by a real
  schema change is readable and permanently unwritable. That the reproduction
  was seeded or searched — it is deterministic, and **no seed is recorded
  because none was used.** That 6a's normalisation generalised to 6b: SQL
  comments cannot carry behaviour, Python docstrings can, so 6b needed a
  different discriminator rather than the same one. That a store **already
  bricked before** upgrading is healed — it is not; only stores opened cleanly
  once after the upgrade are, and the remainder keep the restore-the-bytes
  remedy. That either digest is stable across arbitrary Python versions — 3.13
  moved the AST shape for PEP 695 generics (PEP 696 added `default_value`), which
  is why the algorithm is **versioned** and its cross-version agreement is
  asserted over a frozen corpus rather than assumed. That the AST digest is
  independently correct — the frozen golden values are recorded from a measured
  run, so they evidence **agreement across cells**, not correctness; the
  behavioural tests carry that.

---

## Observation records

### [`docs/observations/OBS-0001-fts5-notes-search-v1.md`](observations/OBS-0001-fts5-notes-search-v1.md)

- **Claims:** Stage-0 Null screen 2026-07-09 on `fts5-notes-search-v1`: 3/3
  passes; ceiling → task rejected for hardening; disposition_of_record CUT of
  `sqlite-expert` stands as dated history.
- **Refuses to claim:** A skill verdict in the observation body; compliance
  (`pi_c: not-instrumented`); a registered estimand; Gate-1 classification
  (`classification: DEFERRED`).

### [`docs/observations/OBS-0002-fts5-notes-search-v2.md`](observations/OBS-0002-fts5-notes-search-v2.md)

- **Claims:** Stage-0 Null 3/3 on `fts5-notes-search-v2` (2026-07-09) plus the
  8/8 Stage-1 Null arm that enters the 26/26 aggregate; counts are
  ledger-canonical.
- **Refuses to claim:** A skill verdict in the observation body; compliance or
  estimand; Gate-1 classification (`DEFERRED`).

### [`docs/observations/OBS-0003-sqlite-tie-break-red-test-trap.md`](observations/OBS-0003-sqlite-tie-break-red-test-trap.md)

- **Claims:** Stage-0 Null 3/3 on `sqlite-tie-break-red-test-trap` (2026-07-10);
  part of the registered 26/26 Null aggregate.
- **Refuses to claim:** A skill verdict in the observation body; compliance or
  estimand; Gate-1 classification (`DEFERRED`).

### [`docs/observations/OBS-0004-bayesian-eval-discipline.md`](observations/OBS-0004-bayesian-eval-discipline.md)

- **Claims:** Stage-0 Null 3/3 on `bayesian-eval-discipline` (2026-07-10); part
  of the registered 26/26 Null aggregate.
- **Refuses to claim:** A skill verdict in the observation body; compliance or
  estimand; Gate-1 classification (`DEFERRED`).

### [`docs/observations/OBS-0005-append-only-evidence-design.md`](observations/OBS-0005-append-only-evidence-design.md)

- **Claims:** Stage-0 Null 3/3 on `append-only-evidence-design` (2026-07-10);
  part of the registered 26/26 Null aggregate.
- **Refuses to claim:** A skill verdict in the observation body; compliance or
  estimand; Gate-1 classification (`DEFERRED`).

### [`docs/observations/OBS-0006-llm-judge-calibration.md`](observations/OBS-0006-llm-judge-calibration.md)

- **Claims:** Stage-0 Null 3/3 on `llm-judge-calibration` (2026-07-10); part of
  the registered 26/26 Null aggregate.
- **Refuses to claim:** A skill verdict in the observation body; compliance or
  estimand; Gate-1 classification (`DEFERRED`).

---

## Assurance reports

### [`docs/assurance/ebmom-gate-mutation-receipt.md`](assurance/ebmom-gate-mutation-receipt.md)

- **Claims:** Seven mutants against the #360 peel and heterogeneity gate, each
  run in its own git worktree at a fixed commit with production never mutated in
  place, each case recording and asserting both worktree HEADs, the
  `module.__file__` actually imported, clean and mutant source digests, that the
  digests differ, that the clean baseline passed first with nonzero collection,
  that the mutant imports, the named failing assertion, and that the production
  tree is byte-unchanged afterwards. Re-run 2026-09-02 after the null was amended
  on the heterogeneity-target ruling: six killed by named assertions, one
  survivor preserved rather than folded into a score. M-B4 is now the superseded
  ties-fixed draw and is killed by the deterministic tie-split fixture that pins
  the ruling; the first campaign's M-B4 result is retained as the record of how
  the contract inconsistency was found. On the first campaign's first run the
  generator returned INVALID_BASELINE for all four method-selection cases
  because their clean baseline was already red from a renamed provenance field,
  which is the baseline check preventing four kills being recorded against an
  already-failing test. Records that a tie-blind peel survives the differential
  suite by construction, since that suite's inputs are tie-free where the two
  formulas are algebraically identical, and that the registered acceptance
  regimes cannot distinguish the amended null from a ties-fixed one, which is
  why the fixture exists.
- **Refuses to claim:** Any mutation score, and that the mutant set is
  exhaustive; that the candidate passes the acceptance matrix, since no
  confirmatory run has been performed and the development smoke, with row 1 now
  calibrated at 0 of 40, still returns REJECTED on the kill criterion in three
  regimes; that the smoke numbers quoted for the survivor are results, since they
  were produced at R=20 under a throwaway root seed solely to show the mutant is
  detectable; that obligation B is fully covered by seven hand-chosen mutants.

### [`docs/assurance/ebmom-peel-preregistration-amendment.md`](assurance/ebmom-peel-preregistration-amendment.md)

- **Claims:** The mean-of-`c_hat` acceptance statistic registered for falsification
  plan item 2 (#344) is superseded, because concentration is a reciprocal of the
  latent variance and the peel removes that variance's magnitude without removing
  its sampling error, so the mean is dominated by the replicates carrying least
  information. Records the development evidence that produced the amendment (seed
  20260902; four estimator families; the measured finite-K bias of the `/K` peel
  matching its closed form). Freezes a replacement acceptance matrix that reports
  false admission under homogeneity, admission rate, latent-variance bias and
  coverage, fallback rate, and wrong-PASS, wrong-FAIL and added-abstention
  separately. Replaces the fixed `VAR_FLOOR` with a one-sided parametric-bootstrap
  test of `latent_variance > 0` at a proposed level of 0.05 with its power cost
  tabled. States that `(w, n)` does not identify within-clause variance when ties
  are present, verified on a worked pair, which makes #360 depend on #368. Amended
  2026-09-02 by supersession on the heterogeneity-target ruling: the null redraws
  ties from one pooled categorical because the lane's target is the encoded clause
  mean; row 1 re-measured at 0 of 40 on the registered null world, calibrated; the
  superseded ties-fixed text is retained and marked. Records, in section 0, that the
  same development smoke fires the frozen kill criterion in three regimes and that
  two of those were already present at `7d50b4a` and unreported.
- **Refuses to claim:** That the repaired estimator passes anything — no
  confirmatory simulation has been run against this amendment, and the development
  smoke predicts a REJECTED one; that the heterogeneity target is settled beyond the
  lane's current decision rule, since the ruling expires when the lane migrates to
  the discordant representation; that the test level is anything but the
  maintainer's ruling of 2026-08-31;
  that the development results on seed 20260902 confirm any repair, since they are
  quarantined as development evidence by section 0; that the original registration
  was wrong, as its derivation is correct for the unpeeled estimator it was written
  against; that tie-free synthetic regimes can detect the tie-identification
  defect; that the bootstrap's power figures hold, since they are normal
  approximations pending measurement.

### [`docs/assurance/dependency-audit.md`](assurance/dependency-audit.md)

- **Claims:** The command CI runs (`python -m pip_audit --local`, pip-audit 2.10.1,
  no `continue-on-error:`) exited 1 on a deliberately vulnerable installed pin —
  `jinja2` 2.11.3, four published advisories — and exited 0 on the dependency set
  this repo pins today, so the scanner step is fail-able rather than merely green.
- **Refuses to claim:** That GitHub Actions was observed honouring that exit
  status; that the demonstration environment reproduces the CI runner's resolution
  (25 of its 86 distributions are unpinned by `requirements-ci.txt`); that a clean
  run means the dependency set is free of vulnerabilities rather than free of
  advisories published to pip-audit's service on the run date; that the advisory
  IDs or fix versions are stable; anything about this repository's own source.

### [`docs/assurance/workflows-audit.md`](assurance/workflows-audit.md)

- **Claims:** All six GitHub Actions workflow files present at issue #172 were
  reviewed for exact commit-SHA action pins, explicit least-privilege permissions,
  and `pull_request_target`; no violations were found, no existing job was renamed,
  and neither new check was added to the required-check set.
- **Refuses to claim:** That shell-installed dependencies are GitHub Actions or
  therefore covered by action SHA pinning; that repository branch protection was
  inspected or changed; that a passing configuration audit proves action behavior.

### [`docs/assurance/falsification-plan.md`](assurance/falsification-plan.md)

- **Claims:** Phase 0 baseline (#162): suite green (1800 passed / 8 skipped at
  authoring), release gate and drift-check green; ranked list of exactly ten
  wrong-number failure modes with one named detection each.
- **Refuses to claim:** That later phases may invent new failure modes without
  revisiting this plan; that style/lint are in scope; any production code or
  test change in the landing of this document.

### [`docs/assurance/aa-report.md`](assurance/aa-report.md)

- **Claims:** Offline A/A (#163): 500 seeded paired runs, identical Bernoulli(0.5)
  arms through the production sequential stopper; two-arm gate false-positive
  count X=26 (rate 0.052) inside binomial band [16, 35] at seed
  `163_2026_08_09`.
- **Refuses to claim:** That the Bayesian gate is a frequentist level-α test at
  every \((n, \delta)\); license to retune thresholds if a future seed misses
  (file `WRONG_NUMBER` instead).

### [`docs/assurance/calibration-report.md`](assurance/calibration-report.md)

- **Claims:** Coverage calibration (#164) method and grid (500 reps × three
  planted rates through the sequential stopper) for the unpooled Beta 95%
  interval `fit_skill` / `aggregate_skill` surfaces; points to the findings
  record when coverage misses.
- **Refuses to claim:** License to retune aggregation math on a miss; that
  fixed-n coverage transfers to sequentially stopped data.

### [`docs/assurance/differential-report.md`](assurance/differential-report.md)

- **Claims:** Differential cross-check (#165): audited aggregation surfaces
  agreed with independent scipy/statsmodels references within pre-stated atol
  on 1,000 seeded inputs per function; max observed error recorded; no
  findings opened.
- **Refuses to claim:** License to widen atol/rtol to make a check pass; that
  unlisted functions were audited.

### [`docs/assurance/mutation-report.md`](assurance/mutation-report.md)

- **Claims:** Container-side mutmut 3.7.0 scores and survivor justifications for
  aggregation, ablation, extractor, and audit modules under scoped test
  selection (`scripts/run_mutation.py`).
- **Refuses to claim:** Host/Windows mutation coverage; that Monte Carlo
  assurance harnesses (#163/#164) were inside the mutmut selection; a cosmic-ray
  run (fallback named, not required).

### [`docs/assurance/fuzz-report.md`](assurance/fuzz-report.md)

- **Claims:** Container-side atheris 3.1.0 fuzz of the SKILL.md parser and
  extractor JSON ingestion models (#170); ≥1h total wall (30m+30m); executions,
  libFuzzer edge/feature/live-corpus counters, and crash count recorded; findings
  triaged by severity; every figure re-derivable from `fuzz/artifacts/*.json`.
- **Refuses to claim:** Host/Windows fuzz coverage; that expected refusals
  (`MalformedSkillError`, pydantic `ValidationError`) are crashes; production
  fixes for non-trivial findings (findings first); coverage-guided search over
  the JSON validation core (`pydantic_core` is a compiled extension atheris
  cannot instrument — that target's execution count is throughput, not reach);
  that the corpus file count is the corpus size.

### [`docs/assurance/coverage-floors.md`](assurance/coverage-floors.md)

- **Claims:** Per-module **branch** coverage (coverage.py 7.15.2, `--cov-branch`)
  for `src/skill_harness/aggregation/` and `src/skill_harness/ablation/` under
  the ordinary CI test selection (#171), paired in every row with that module's
  #166 mutation score; a stated attention rule reading both instruments, which
  flags **7 of 20 modules** where branch coverage alone flags 3; the four modules
  where the instruments disagree and mutation is the one under the floor
  (`aggregation/engine.py` 90.0/67.9, `aggregation/verdict.py` 91.2/71.5,
  `ablation/subject.py` 90.6/62.4, `ablation/render.py` 83.3/65.9); that
  `aggregation/confidence_sequence.py` has the worst branch coverage (17
  uncovered arcs of 54) and **no #166 mutation score at all**, and that its
  uncovered arcs were read and are input-validation guards; 2,210 branches
  measured, 1,909 covered.
- **Refuses to claim:** That coverage is evidence of correctness — a branch is
  counted when a test steps on it, whether or not anything asserted on the
  result; that a module reporting 0 branches carries any information, which is
  why those five rows print `n/a` rather than the arithmetically-true 100%; that
  a healthy branch percentage is evidence for a module whose mutation score is
  below the floor; that coverage substitutes for mutation on a module mutation
  never measured; that 80% is a gate rather than a place to look; host coverage
  for the two symlink tests Windows refuses without Developer Mode. **Carries a
  dated retraction:** an earlier draft attributed the `confidence_sequence.py`
  gap to the excluded calibration lane from name similarity, without opening the
  `missing_branches` data that refutes it.

### [`docs/ASSURANCE.md`](ASSURANCE.md)

The assurance close-out (#174). Indexed by hand: it sits at the docs root, so
`tests/test_receipts_index.py` — which gates `docs/assurance/` — does not force
this entry.

- **Claims:** The figures above, re-quoted from the checked-in reports with each
  source named (#163 through #172), the residual risks the pass leaves standing,
  and four PROPOSED, NOT CONFIGURED drift-contract candidates that are absent
  from `scripts/drift_check.py`; that the requested #173 independent
  re-derivation report does not exist in this worktree and is recorded missing
  rather than reconstructed.
- **Refuses to claim:** That the recorded runs establish absence of defects; that
  a closed issue substitutes for the missing #173 numerical receipt; that the
  candidate contract rows are configured or ratified; that the pass covers
  vacuity-flag recall, which it leaves UNMEASURED by the assurance report set;
  that it covers records outside `docs/assurance/`, unmutated modules, or the
  platforms and cores the fuzz and coverage lanes did not reach.

### [`docs/assurance/release-gate-red-206.md`](assurance/release-gate-red-206.md)

The deterministic falsification receipt for the `0.3.0` assurance release gate
(#206).

- **Claims:** A release gate run over a seeded tree that declares `0.3.0` exits
  1 with exactly two failures — assurance issue #169 open, and no successful
  `assurance.yml` run on record — while checks G1 through G6 pass on that tree;
  the recorded transcript is compared line-for-line against the gate's live
  output by `tests/test_release_gate_206.py`.
- **Refuses to claim:** That the local HTTP stand-in for the GitHub API is a
  live GitHub result; that any real assurance lane run has finished green; that
  the 0.2.x patch line is in scope for the assurance checks; that the gate is
  tamper-proof rather than blocked-by-default.

### [`docs/assurance/issue-174-bottom-line-receipt.md`](assurance/issue-174-bottom-line-receipt.md)

- **Claims:** The Phase 7 close-out's bottom-line paragraph is published verbatim
  as a comment on issue #174, at comment id `5496638740`, posted 2026-09-01, with
  the paragraph digesting to `sha256:5d270dbd`. Before #354 the issue had zero
  comments and the assertion that checks this skipped in CI for want of a
  credential, so the close-out claimed a published finding that was not
  published. A credential-free check now enforces the claim against this receipt.
- **Refuses to claim:** That the bottom line was published on the close-out date
  — it was posted sixteen days after issue #174 was closed, and the comment says
  so; that the original comment ever existed (the timeline carries no
  `commented` event, and GitHub emits none for a deletion, so both readings
  survive); that the remote comment is currently intact, which only the
  credentialed check sees and which does not run in CI; that any figure inside
  the paragraph is correct — those carry their own receipts listed on this page.

### [`docs/assurance/confounded-status-mutation-receipt.md`](assurance/confounded-status-mutation-receipt.md)

The mutation receipt for the #366 CONFOUNDED repair, generated by
`scripts/mutation_receipt.py --select 366` into
[`confounded-status-mutation-receipt.json`](assurance/confounded-status-mutation-receipt.json).

- **Claims:** Three named mutants of `src/skill_harness/aggregation/engine.py`
  were each run in its own git worktree under Python 3.13.1 against the file at
  `sha256:c64986c3`, and all three were KILLED by named test nodes: dropping the
  read of the persisted `inadmissibility_reason`, inverting the survivor gate so
  CONFOUNDED fires only when admissible work survived, and counting every
  inadmissible verdict except `scorer_error` as confounded. The third SURVIVED on
  the first campaign, which measured a fixture monoculture — every fixture
  discarded for confound, so an engine ignoring the reason looked identical to
  one reading it — and it is killed here by the test written from that survival.
  Each case asserted a clean baseline passing first with nonzero collection, the
  imported `module.__file__` resolving inside its own worktree, differing source
  digests, a mutant that imports, and a byte-unchanged production tree.
- **Refuses to claim:** A mutation score — three hand-chosen mutants cannot
  support one; adequacy of the aggregation suite as a whole; that any historical
  report understated a confound (no production re-scan was run); that the
  admissible VIEW's `affected_clause_id` question is settled (untouched); that
  M-C3 discriminates any reason beyond `confounded` from `underpowered`.

### [`docs/assurance/nan-score-refusal-mutation-receipt.md`](assurance/nan-score-refusal-mutation-receipt.md)

The mutation receipt for the #363 non-finite score refusal, generated by
`scripts/mutation_receipt.py` into
[`nan-score-refusal-mutation-receipt.json`](assurance/nan-score-refusal-mutation-receipt.json).

- **Claims:** Three named mutants of `src/skill_harness/subject/ingest.py` were
  each run in its own git worktree under Python 3.13.1 (first at commit
  `210ac93`; regenerated 2026-09-01 at `ae9ab3c` after #387 rewrote the module
  and aligned exposure config_json with the #388 delivery reader; same three
  kills), and
  all three were KILLED by named test nodes: removing `allow_inf_nan=False`
  from `ParsedSample.score_value` (killed by the item 8 paired detector and by
  the model-layer unit test), disabling the `math.isfinite` guard in
  `_score_to_float`, and narrowing that guard to NaN so an infinity passes. Each
  case asserted its clean baseline passed first with nonzero collection, that
  the imported `module.__file__` resolved inside its own worktree, that the
  source digests differed, that the mutant imported, and that the production
  tree was byte-unchanged afterwards.
- **Refuses to claim:** A mutation score — three hand-chosen mutants cannot
  support one; adequacy of the test suite as a whole; that a non-finite score
  has ever appeared in a production `.eval` log (no historical re-scan was run);
  that a third write path to `oracle_verdicts.observation`, if one exists, is
  covered.

### [`docs/assurance/exposure-refusal-mutation-receipt.md`](assurance/exposure-refusal-mutation-receipt.md)

The mutation receipt for the two #387 refusal predicates at paired ingest (the
#384 ruling: treatment = exposure, invocation = stratifier), generated by
`scripts/mutation_receipt.py --select 387` into
[`exposure-refusal-mutation-receipt.json`](assurance/exposure-refusal-mutation-receipt.json).

- **Claims:** Two named mutants of `src/skill_harness/subject/ingest.py` were
  each run in its own git worktree at commit `fb3b91b` under Python 3.13.1
  against the file at `sha256:1eaefbae`, and both were KILLED by named test
  nodes: emptying the set behind predicate (a) so an unexposed Full-arm epoch
  writes, and emptying the channel-(c) half of predicate (b) so an exposed
  Null-arm epoch writes while the #46 invocation half stays. Each case asserted
  its clean baseline passed first with two tests collected, that the imported
  `module.__file__` resolved inside its own worktree, that the source digests
  differed, that the mutant imported, and that the production tree was
  byte-unchanged afterwards.
- **Refuses to claim:** A mutation score — two hand-chosen mutants cannot
  support one; adequacy of the ingest suite as a whole; anything about the v2
  exposure detector itself (`detect_skill_exposure`), which the parse-level
  tests pin and this receipt does not; that the #46 invocation half of
  predicate (b) is re-attested here (its 0/22 fixture is pinned separately).

### [`docs/assurance/paired-gate2-mutation-receipt.md`](assurance/paired-gate2-mutation-receipt.md)

The mutation receipt for the #389 ratification binding and count-mismatch
refusal at the paired-lane Gate-2 read surface, generated by
`scripts/mutation_receipt.py --select 389` into
[`paired-gate2-mutation-receipt.json`](assurance/paired-gate2-mutation-receipt.json).

- **Claims:** Two named mutants of `src/skill_harness/cli/paired_gate2.py`
  were each run in its own git worktree at commit `be86b77` under Python
  3.13.15 against the file at `sha256:8abfb41b`, and both were KILLED by named
  test nodes: forcing `record.status != "RATIFIED"` to false so a DRAFT record
  is accepted (killed by `test_draft_record_refused`), and forcing
  `total_pairs != design.n_pairs` to false so k=8 pairs are read against an
  n=32 design (killed by `test_pilot_k8_vs_design_n32`). Each case asserted
  its clean baseline passed first with one test collected, that the imported
  `module.__file__` resolved inside its own worktree, that the source digests
  differed, that the mutant imported, and that the production tree was
  byte-unchanged afterwards. Regenerated 2026-09-03 for #421 after `be86b77`
  added the `#403`-amendment hazard refusal to the same module; the two `#389`
  anchors were still present and both kills held. The hazard refusal itself is
  pinned by `TestHazardNotRecorded`, `TestHazardNotMet` and
  `TestHazardPositivePath` and is not a mutant in this receipt.
- **Refuses to claim:** A mutation score — two hand-chosen mutants cannot
  support one; adequacy of the paired Gate-2 test suite as a whole; that the
  ratification-record field-mismatch path is covered here (covered by
  `TestMissingDesignFields` and `TestSkillIdMismatch` in
  `test_cli_paired_gate2.py`); that every CLI output format is tested here
  (formatting is pinned by the tests in `test_cli_paired_gate2.py`).

---

## Ratifications

Forward-looking `RAT-*.md` records bind pre-spend ablation launches (see
[`docs/ratifications/README.md`](ratifications/README.md)). The completeness glob is
`docs/ratifications/RAT-*.md`; every record gains an entry here in the same change.

### [`docs/ratifications/RAT-0001-git-pull-rebase-trap.md`](ratifications/RAT-0001-git-pull-rebase-trap.md)

- **Claims:** DRAFT, unsigned. The Gate-2 row-pick for one sized paired run of
  `git-pull-rebase-trap`, copied field for field from Amendment 4 of the v0.2
  pre-registration (commit `9264b04`): `gamma = 0.90`, `delta_min = 0.20`,
  `q_min = 0.70`, `n = 32`, `alpha[cert] = 0.0161`, power `0.826` at the binding
  H1 point; worst-case cost $23.351744 from `project_pair_usd` at `claude-sonnet-5`
  list price on the 2026-09-01 calibrated tokens per pair, `hard_cap_usd = 23.36`
  rounded up to the cent; self-certified with the verbatim disclosure line and
  the 21-day expiry arithmetic (expires 2026-09-22). The only act left in it is
  the operator's signature, and that act is a spend authorization of up to
  $23.36, stated in one sentence in section 9.
- **Refuses to claim:** That any spend is authorized while the status line reads
  DRAFT (the gate refuses it by construction, mutant M-R1); that the row is the
  cheapest conforming one (that is `gamma = 0.85, n = 26` at $18.97, recorded and
  not chosen); that the pre-spend token re-measurement will hold (if tokens per
  pair re-measure above about 470k the row breaches the cap and the run does not
  launch); that the SME branch was deliberated (it was not; the #45 clock never
  started).

---

## SERS instances

Machine-readable receipts under [`docs/sers/receipts/`](sers/receipts/).
Verdict and sub-reason strings use the
[`sers.schema.json`](sers/sers.schema.json) vocabulary
(`KEEP` | `CUT` | `CANT_TELL_YET`; `cut_sub_reason`; `unmeasured_sub_reason`).

### [`docs/sers/receipts/double-ceiling-nogo-2026-07-09.json`](sers/receipts/double-ceiling-nogo-2026-07-09.json)

- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=underpowered`; Null 14/14 ceiling path; discordance 0;
  `go_nogo=NO_GO`; evidence_admissibility admissible; not a fabricated no-benefit
  CUT.
- **Refuses to claim:** `KEEP` or `CUT`; measured `p_win` (refusal
  `underpowered`); standing/fired token triple (not_instrumented); that this is
  a production-skill benefit measurement.

### [`docs/sers/receipts/reclass-append-only-evidence-design.json`](sers/receipts/reclass-append-only-evidence-design.json)

- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=null`; `value_class=calibration`;
  `wrong_instrument=true`; Null p0=1.00 above transformative bar but lift
  instrument cannot see calibration value; pre-guard CUT(subsumed) withheld.
- **Refuses to claim:** `CUT` with `cut_sub_reason=subsumed`; a transformative
  lift measurement; standing/fired token costs (not_instrumented).

### [`docs/sers/receipts/superseded/reclass-git-pull-rebase-trap.json`](sers/receipts/superseded/reclass-git-pull-rebase-trap.json)

- **Superseded 2026-09-01** by `gitpull-paired-k8-2026-09-01.json`, itself
  superseded 2026-09-02 by
  [`gitpull-paired-k8-2026-09-01-detector-v2.json`](sers/receipts/superseded/gitpull-paired-k8-2026-09-01-detector-v2.json).
  The site publishes one receipt per skill and refuses to choose between two,
  so the older receipt moved out of the published directory and stays in the
  tree unedited. Its `p0=1.00` screen row is D4-voided: the prompt it ran on
  named the skill's rule (`docs/findings/d4-prompt-leak-into-null-arm.md`).

- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=null`; `value_class=trap-discipline`;
  `wrong_instrument=true`; Null p0=1.00 means the trap did not fire in-screen,
  not that the model is unaided; CUT withheld.
- **Refuses to claim:** `CUT` with `cut_sub_reason=subsumed`; that the trap is
  unnecessary in production; standing/fired token costs (not_instrumented).

### [`docs/sers/receipts/synthetic-control-keep-2026-07-27.json`](sers/receipts/synthetic-control-keep-2026-07-27.json)

- **Claims:** `verdict=KEEP`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=null`; `declared_synthetic_control=true`; Full 8/8 vs
  Null 0/8; `p_win=0.99`; first store-backed KEEP — instrument-label validation.
- **Refuses to claim:** A production-skill KEEP; that any real library skill has
  cleared the full keep lane; standing cost as part of the KEEP claim
  (not_instrumented).

### [`docs/sers/receipts/superseded/gitpull-paired-k8-2026-09-01-detector-v2.json`](sers/receipts/superseded/gitpull-paired-k8-2026-09-01-detector-v2.json)

- **Superseded 2026-09-03** by
  [`gitpull-paired-n32-2026-09-03-sized.json`](sers/receipts/gitpull-paired-n32-2026-09-03-sized.json).
  The site publishes one receipt per skill; the file moved out of the
  published directory unedited and stays the GO datum the sized run was
  sized on.
- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=underpowered`; `value_class=trap-discipline`;
  `wrong_instrument=false`; `sers_version=1.2.0` with a `delivery` block;
  evidence admissibility **admissible** — the same 2026-09-01 pair re-ingested
  under detector v2 (#387) as run `0cc7fce87e70`, 8 samples per arm, one pin
  (`5324feef...`) across both arms. `delivery.channel=description_only`:
  description exposure 8/8 in the Full arm and 0/8 in the Null arm, Skill tool
  invocations 0/8 (\(\hat\pi_c = 0.00\), 95% CI \([0.000, 0.369]\)). Paired
  cells full_only=6, null_only=0, both_pass=0, both_fail=2. Measurements carried
  forward unchanged from the superseded receipt: `null_pass_rate` 0/8,
  `discordance_rate` 6/8 with the Jeffreys interval in `detail`, `go_nogo=GO`.
  Supersedes `superseded/gitpull-paired-k8-2026-09-01.json`, whose
  `inadmissible` status was an instrument defect and not a property of the
  evidence.
- **Refuses to claim:** `KEEP` — k=8 is a Stage-1 micro-run and a GO datum for
  the sized run, which is why the sub-reason is `underpowered`; a win direction
  (withheld per the registered micro-run template); a Gate-2 verdict — the #389
  paired-lane read binds to a RATIFIED design record and `docs/ratifications/`
  holds none, so no read was performed against this run; the registered
  direct-Anthropic subject (ran on OpenRouter); standing or fired token costs
  (not_instrumented / not_applicable, the body never loaded).

### [`docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json`](sers/receipts/gitpull-paired-n32-2026-09-03-sized.json)

- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=null`; `value_class=trap-discipline`;
  `wrong_instrument=false`; `sers_version=1.2.0`; evidence admissibility
  **admissible** under the 0.4.1 oracle metric identity — run `0700d089…`,
  n=32 both arms. Lattice `both_pass=32, full_only=0, null_only=0,
  both_fail=0`; signed delta 0.000, 95% CI [-0.107, 0.107]; `pi_c` 24/32 =
  0.75, 95% CI [0.566, 0.885]. `delivery.channel=body_and_description`;
  exposure 32/32; `go_nogo=NOT_APPLICABLE` (RAT-0001 registers no GO/NO-GO
  gate).
- **Refuses to claim:** `KEEP` or `CUT`; that the trap was avoided — 0 of 32
  Null epochs and 0 of 32 Full epochs ran the hazard action, so the run
  carries no information about the trap-discipline estimand under the #403
  ruling of 2026-09-03; standing, fired, or aux token costs
  (not_instrumented).

### [`docs/sers/receipts/superseded/gitpull-paired-k8-2026-09-01.json`](sers/receipts/superseded/gitpull-paired-k8-2026-09-01.json)

- **Superseded 2026-09-02** by
  [`gitpull-paired-k8-2026-09-01-detector-v2.json`](sers/receipts/superseded/gitpull-paired-k8-2026-09-01-detector-v2.json).
  It recorded the same measurements as **inadmissible** because detector v1
  observed only Skill tool calls and could not see the description channel the
  effect arrived through. The #384 ruling made exposure the treatment and pi_c a
  stratifier; the pair then ingested without refusal. The file moved out of the
  published directory unedited.

- **Claims:** `verdict=CANT_TELL_YET`, `cut_sub_reason=null`,
  `unmeasured_sub_reason=inadmissible`; `value_class=trap-discipline`;
  `wrong_instrument=true`; `sers_version=1.1.0` with a live-minted
  `subject_identity`; `null_pass_rate` 0/8, `discordance_rate` 6/8 with the
  Jeffreys interval in `detail`, `go_nogo=GO`; evidence admissibility
  `inadmissible` on `ZeroInvocationError` (zero detected invocations, detector
  v1). Source prose: the description-channel finding above. Supersedes
  `superseded/reclass-git-pull-rebase-trap.json` (2026-07-20), whose screen row
  is D4-voided.
- **Refuses to claim:** `KEEP`; a win direction (withheld per the registered
  micro-run template); the registered direct-Anthropic subject (ran on
  OpenRouter); standing or fired token costs (not_instrumented /
  not_applicable, the body never loaded).

---

## Cost-beside-evidence join surface (`skill audit --extraction`)

Not a file under `docs/` — the offline CLI join of mechanical cost (from
`skill audit`) with zero-power clause evidence (from `skill init --out`
JSONL). Implementation: `src/skill_harness/extractor/clause_evidence.py`;
tests: `tests/test_clause_evidence_audit.py`.

- **Claims:** When `--extraction` points at a single matching
  `ExtractionResult` row (same `source_sha256`), prints per-clause vacuity /
  scoreability evidence beside the audit’s standing/fired/aux cost figures;
  named refusal reasons when the join cannot run
  (`no_extraction`, `no_matching_extraction`, `ambiguous_duplicate_rows`,
  `legacy_extraction_missing_instrument_identity`,
  `unreadable_extraction_file`).
- **Refuses to claim:** Instantiated coverage against the evidence database
  (`Instantiated coverage: REFUSED` — audit does not open a DB); a keep/cut
  verdict; stable choice among duplicate extraction rows for one sha;
  aggregation-layer `UnmeasuredSubReason` vocabulary (extractor-layer names
  only).
