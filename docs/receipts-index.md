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

### [`docs/findings/class-hypothesis-preregistration.md`](findings/class-hypothesis-preregistration.md)

- **Claims:** `value_class` has three permitted values and `TRANSFORMATIVE_LIFT`
  has zero members anywhere in the registry, so the `CUT`-withholding branch in
  `verdict.py` is untestable in principle rather than merely unreached. Measured
  at zero spend on 2026-09-20: the extractor's corpus resolves to 82 entries via
  `--dry-scope`, not the 71 three surfaces state; `value_class_registry.py` holds
  12 entries, 9 `trap-discipline` and 3 `calibration`, not 11; only 4 of the 12
  resolve in that corpus, of which exactly one is `trap-discipline` and the
  registry marks it retired (`sqlite-tie-break-red-test-trap`). Of the remaining
  eight, seven sit in a dated backup directory and nowhere live, one of those
  seven also sits in plugin `_quarantine/` so the two sets overlap rather than
  partition, and the eighth (`closure-mode-at-boundaries`) is not absent but
  renamed: `skills#286` renamed the card to `closure-mode`, which is live and
  published, while `value_class_registry.py:52` still keys the old string. The
  registry therefore holds at least one stale key, filed as `#601` as a defect
  in the instrument. The corpus-wide extraction `#104` contemplates is
  therefore refused as an instrument for this hypothesis, because the skills it
  would pay for are not the missing ones. Class as assigned is close to collinear
  with liveness, so classification coverage rather than extraction coverage is
  the binding constraint. Registered as the next observation, at zero cost:
  ablate the `value_class` branch across every verdict already on disk and count
  how many change, publishing either outcome.
- **Refuses to claim:** That the class hypothesis is false, or that it has been
  tested. Refusing an instrument does not discharge a hypothesis, and the shipped
  branches remain depended upon and unexamined. That any test of the hypothesis
  is registered here: the first draft registered a between-class versus
  within-class contrast on mechanical measurability, two independent non-Anthropic
  reviewers converged that this measures registry coverage rather than null
  interpretation, and it is withdrawn with nothing put in its place. That the
  6-skill sample's within-class spread (6.4x, Fisher two-sided p = 0.041) supports
  anything: two of six rows carry a class and both are the same class, so it is
  quarantined as anecdote. That the registry's labels are correct, since only
  their count and reachability were measured. That `verdict.py` should stop
  branching on `value_class`, which belongs to `#104`. That no literature lets
  intervention type condition a null's interpretation, a prior sweep's claim this
  document declines to rely on. That the refusal is permanent: it should be
  re-derived if classification coverage puts live members in both arms.

### [`docs/findings/gitpull-hazard-entry-is-not-a-prompt-lever.md`](findings/gitpull-hazard-entry-is-not-a-prompt-lever.md)

- **Claims:** `#419` item 2's two criteria — force the hazard action, and do
  not name the strategy — are not jointly satisfiable at the prompt layer.
  Every prompt-level route to hazard entry works by naming the action, and the
  card's `description` begins with a use-before instruction naming that action,
  so a prompt carrying the token hands the treated arm the card's own retrieval
  cue; buying entry in the prompt therefore moves contamination from the
  untreated arm to the treated arm rather than removing it, into a place
  `check_d4_prompt_leak` does not look, since that check reads the prompt and
  the fixture files a prompt names and does not model treatment-side retrieval.
  Candidate v3a is selected as the task version that ships, because it is the
  only one that moves the lever out of the prompt and into the environment.
  Four things measured at $0: the digest-pinned sandbox image runs git 2.39.5
  and hedges its suggestion, so the wording quoted in the drafting pass is the
  host's git 2.55.0 and not the sandbox's; the rejection line states the
  competing action plainly as `(fetch first)`; `check_d4_prompt_leak` reports
  the new prompt clean prompt-only against three candidate rule strings,
  identically to v2; and the card's `description` is byte-identical across its
  `git-pull-rebase-trap` to `pull-rebase` rename, so this ticket's Revisit-if
  has not fired.
- **Refuses to claim:** That v3a enters the trap — its entry rate is
  unmeasured, measuring it is item 3, which is spend, and zero is a live
  outcome; any hazard rate, lift, or verdict for the card; that the untreated
  arm's two-hop signpost through the fixture's commit messages was neutralised;
  that the force-push failure mode was removed; that the per-pair token basis
  is still the measured 539,011 under a shorter prompt; and any reordering of
  `#419` item 3 against `#420`, which is stated as a fork and deliberately not
  taken.

### [`docs/findings/gitpull-v3a-null-qualification-screen.md`](findings/gitpull-v3a-null-qualification-screen.md)

- **Claims:** The `#419` item 3 Null qualification screen on task v3a ran on
  2026-09-21 under a dated $5.00 authorisation with every count from 0 to 8
  pre-registered (Amendment 1) before the run. On `claude-sonnet-5` direct,
  k = 8, run `joXzHFBKEBvqXPHstc8kt3`: 0 of 8 Null epochs entered the hazard
  on the pattern of record, 0 undecided, 8 of 8 passed the oracle, $0.81 spent
  (Amendment 2). The push-divergence fixture worked in every epoch, the push
  was rejected with git's own hint naming the pull, and the subject fetched
  and merged by hand each time. Per the pre-registered table the candidate
  fails for this subject: v3a is retired as a task version for Sonnet 5, no
  floor is registered, and RAT-0001's frontmatter stays empty with a dated
  line. A second screen on `claude-opus-5` under a $16.00 authorisation
  (Amendment 3, run `EMMSk62u6Gu7AT4ey43kkZ`) returned 0 of 8 entered (2
  parser-undecided, 0 after the required hand-read), 8 of 8 passed, $2.25.
  Opus 5 read the fixture's `RELEASING.md`, merged with `--no-ff`, verified
  the ledger SHAs and said in its summaries that it declined to rebase because
  that file forbids rewriting. So the lever is the in-repo policy signpost the
  S414 pass recorded as moved rather than removed, on both subjects, and the
  family moves to `#611` item 6 (scenario search, first axis the signpost)
  before any further screen. Total spend for item 3: $3.06.
- **Refuses to claim:** Any verdict on the `pull-rebase` card; any hazard
  rate or floor for either subject; that no task in this family can elicit
  the pull, which is what the signpost-free variant will measure; that the
  maintainer's report of the trap firing on Opus 5 in ordinary work is false,
  since only this fixture and agent version were measured; that v3c would do
  better, which is expected false and is why it is not run; and any change to
  a registered RAT-0001 field.

### [`docs/findings/twin-v4-stage1-null-screen.md`](findings/twin-v4-stage1-null-screen.md)

- **Claims:** The `#620` v4 twin Null screen (Stage 1) ran on 2026-09-22 under
  a dated $12.00 authorisation (board gate `twin-stage1`), run
  `UEfX5wJp2nGfCnn5k3NeRH`, on `claude-sonnet-5`, 8 epochs per world, $1.76
  spent. The free identifiability gate passed 9 of 9 first. Of 16 epochs, 1 is
  void because the agent never started. Of the 15 valid epochs, the first
  integration action was a merge in 5 (3 of 8 in world A, 2 of 7 in world B),
  and all 15 ended in the correct world state. Each of the 7 refused epochs
  recovered, and none was a silent violation. The adopted headroom gate on
  Null(A) correctness fails at 8 of 8, while the first-action shift has room.
- **Refuses to claim:** Any verdict on the `pull-rebase` card, since no card
  arm ran; which clause of the adopted rule governs when recovery saturates
  the final outcome, which is recorded as open; that p_N is estimated beyond
  15 epochs on one subject and agent version; and any authorisation for
  Stage 2.

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

### [`docs/assurance/ebmom-peel-confirmatory-run-2026-09-05.md`](assurance/ebmom-peel-confirmatory-run-2026-09-05.md)

- **Claims:** The pre-registered confirmatory run of the v1 EB-MoM peel amendment (#360, #405):
  branch/harness/estimator identity by SHA at `4bd4633`; a root seed generated by the maintainer
  outside the building session and committed by SHA-256 before disclosure; a prediction of
  REJECTED stated before the reveal; one execution at the registered R = 1000 per regime
  (`is_confirmatory: true`); the disclosed root verified against the commitment; and the full
  section-5 matrix reported for every regime. Result: REJECTED
  (`kill_criterion_triggered: true`), with four positive-excess kill cells — `low_heterogeneity`
  row 5 (+2,294) and row 6 (+160), `tie_heavy_null` row 6 (+251), `tie_heavy_signal` row 5
  (+875) — plus row 1 calibrated (39/1,000 admissions, p = 0.127) and row 3 inside tolerance
  everywhere nonzero. Scores its own prediction: direction and cell set held in all four kill
  cells; the stated multiplier ("near 25x the R = 40 counts") held in two and missed in two,
  recorded as missed rather than smoothed over. States the contract consequence: a failed
  confirmatory run does not license a second run at new seeds, only a superseding amendment
  (which `ebmom-peel-preregistration-amendment-v2.md` is); rollback state is `main`,
  `agent/issue-360` stays unmerged.
- **Refuses to claim:** That this result is re-runnable or appealable at a fresh seed — the
  contract it invokes forbids that; that the missed multiplier readings indicate the underlying
  mechanism is wrong, only that the R = 40 magnitude gloss was; a resolution to the four open
  design questions the REJECTED result raises (how rows 5/6 are scored, the fallback policy on
  refusal, whether `low_heterogeneity` discriminates estimators, which mechanism class to measure
  first) — it names them as going to reserved-tier cross-family review, not as decided here.

### [`docs/assurance/ebmom-peel-confirmatory-run-2026-09-05-step4-reveal.md`](assurance/ebmom-peel-confirmatory-run-2026-09-05-step4-reveal.md)

- **Claims:** The root seed `f95e4de5…` was disclosed only after its SHA-256 commitment had
  already landed and been pushed as commit `6d6835a` in
  `ebmom-peel-confirmatory-run-2026-09-05.md` step 3; the disclosed root reproduces that
  commitment under the stated `hashlib.sha256` check; and the harness runs once, next, from the
  worktree at `4bd4633` plus the reveal commits, with the harness and estimator digests unchanged
  from step 1.
- **Refuses to claim:** Any run result — steps 5 and 6 (the run's output, its manifest hash, and
  the verification of the published root against the commitment) are explicitly deferred to "the
  commit that lands the JSON," which is `ebmom-peel-confirmatory-run-2026-09-05.md`, not this
  file; independent re-verification of the harness or estimator digests beyond restating that
  they are unchanged.

### [`docs/assurance/ebmom-peel-confirmatory-run-v2-2026-09-13.md`](assurance/ebmom-peel-confirmatory-run-v2-2026-09-13.md)

- **Claims:** The pre-registered confirmatory run of the v2 EB-MoM amendment (#360, #405):
  branch, harness, estimator and errors-module identity by SHA-256 at `681824d`, re-measured
  unchanged at the run commit; no file under `src/` and no change to the acceptance harness since
  `#444` was accepted at `d2d31a7`; a root seed generated by the maintainer outside the building
  session and committed in both encodings before disclosure; a prediction of NOT_REJECTED taken
  from v2 section 6, which was written at the 2026-09-05 freeze before this root existed; one
  execution at the registered R = 1000 per regime over every registered regime
  (`is_confirmatory: true`); the disclosed root matching the JSON's `root_seed` byte for byte; and
  the full section-5 matrix reported for every regime, both paths and the pooled column. Result:
  NOT_REJECTED (`kill_criterion_triggered: false`, `rejecting_cells: []`), with the oracle
  self-check passing on all 13 testable oracle cells, `latent_raw` relative bias inside the 0.1
  tolerance wherever it is defined, and `tie_heavy_null` calibrated at 57 of 1,000 admitted,
  exact binomial p = 0.309 at level 0.01. Thirteen candidate cells were testable and none
  rejected; the seven not testable are listed in the JSON's `not_testable_cells`. Names the
  nearest cell to a kill rather than the verdict alone: `small_n_bite`, admitted path, row 6c, 21
  false FAIL claims in 241, rate 0.087, p = 0.029 against the frozen level of 0.01, which would
  have rejected at 0.05, while the comparator column `cand_bpB` in that same cell is 31 of 350 at
  p = 0.0028 and does reject. Records that the one cell section 6 excluded in advance, the
  admitted-path 6c cell in `low_heterogeneity`, came out `G = 1`, two FAIL decisions and zero
  false, the outcome section 6 gave probability 0.34. Discharges v2 section 5's condition for
  holding `agent/issue-360` unmerged, and states that no threshold, regime, oracle, row or level
  moved in response to the result.
- **Refuses to claim:** That a NOT_REJECTED result shows the mechanism works. It establishes only
  that on one fresh committed root of 1,000 worlds per regime the candidate kept the per-claim
  promise of section 2 in every testable cell at level 0.01. It is not a level-0.01 procedure,
  since section 5 states the criterion as a union over up to 20 cells with true level up to about
  0.18; it does not demonstrate the admitted-path FAIL side in `low_heterogeneity`, where `G = 1`
  is a sparse pass reported with its `G`; it does not resolve the maintainer's section 9 fork,
  whether that sparse cell is a confirmatory kill or a mechanism gate, which a pass leaves exactly
  where it was; it does not retire the v1 REJECTED result of 2026-09-05, which stays in the record
  beside it; and it does not stand if a third-party recomputation of the two step 3 digests
  against the step 4 root fails, or if a re-run of the step 5 command at the step 1 SHA produces a
  JSON whose `regimes` differ in any cell, either of which voids the step. The hand review of the
  branch's own diff is still owed before merge.

### [`docs/assurance/ebmom-peel-confirmatory-run-v2-2026-09-13-step4-reveal.md`](assurance/ebmom-peel-confirmatory-run-v2-2026-09-13-step4-reveal.md)

- **Claims:** The root seed `d77c7cd1…` was disclosed only after its SHA-256 commitment had
  already landed as commit `122185f` on `agent/issue-360` and been pushed; both encodings recorded
  at step 3, the 64 ASCII hex characters and the 32 raw bytes, were recomputed at reveal time and
  both matched; the root is 64 characters; and the harness runs once, next, from the worktree at
  `681824d` with the reveal commits on top, which touch `docs/assurance/` only, so the harness and
  estimator digests recorded in step 1 are unchanged. Gives the exact command and records that no
  `--replicates`, `--regime` or `--world-range` argument is passed, so the harness's own defaults
  of R = 1000 and every registered regime decide completeness rather than a restated argument.
- **Refuses to claim:** Any run result. Steps 5 and 6, the run's output, its manifest hash, and
  the verification of the published root against the commitment, are deferred to the commit that
  lands the JSON, which is `ebmom-peel-confirmatory-run-v2-2026-09-13.md`, not this file.
  Independent re-verification of the harness or estimator digests beyond restating that they are
  unchanged.

### [`docs/assurance/ebmom-peel-preregistration-amendment-v2.md`](assurance/ebmom-peel-preregistration-amendment-v2.md)

- **Claims:** FROZEN 2026-09-05 (S414) on mechanism class 2, superseding v1's rows 5/6 kill
  criterion (any positive wrong-PASS/wrong-FAIL excess against `main`) with a per-path,
  per-regime exact-binomial-over-one-selected-decision-per-world test (rows 5c/6c), because
  `main` itself breaks the promise it stood in for, "wrong against the oracle" is a regret rather
  than an error rate, and the registered world-block bootstrap bound is 0 by construction — hence
  vacuous — whenever four or fewer worlds carry a false decision. Development re-score at
  R = 1000 on the burned confirmatory root, across five regimes, both paths and six candidate
  columns, measures every disagreement between the exact test and the vacuous bound (five cells,
  always the bound passing by vacuity where the exact test fails) and the seed-dependence of
  every verdict (highest rejection probability among passing cells: 0.0084). Rules the refused
  path pools through a hierarchical "form B" posterior chosen by a pre-committed rule under both
  candidate tests, retiring BH-FDR; rules the admitted path must integrate hyperparameter
  uncertainty rather than plug in point estimates, because plug-in and class 1 (normal
  approximation) both leave `low_heterogeneity` admitted 6c false at 3 of 4 (one decision per
  world, p = 4.8e-4). Measures mechanism class 2 (admission-conditioned parametric bootstrap)
  rejecting in no cell across three burned-root world ranges, including the S414 extension of
  3,000 further never-generated burned-root worlds, whose exact test passes with power (6
  decision-bearing worlds of 4,000, 2 false, p = 0.033, rejects at 3) — the ground on which the
  freeze executes. Names the four admitted-path FAIL worlds directly (255, 316, 600, 783) and
  reads a shared mechanism: latent-variance overshoot, understated fitted concentration,
  posterior under-shrinkage of a clause near the 0.60 boundary.
- **Refuses to claim:** That anything in it is confirmation of anything — "no confirmatory root
  exists for it," and every R = 1000 / burned-root number is development evidence, quarantined
  under v1 section 7 item 2; that the mechanism-gate alternative (a pre-registered abstention
  floor on the sparse admitted-path cell) is wrong — it is recorded as "the live alternative" the
  maintainer still owns, declined twice but not foreclosed; that the kill criterion has overall
  level 0.01 as a procedure — stated explicitly as a union over up to 20 cells with true level up
  to about 0.18; that the `small_n_bite` refused-6c cell is independent confirmation of the
  pooling policy, since its rejection probability over seeds is 0.40; that the admitted-path
  mechanism's form is final — section 4 marks it "revisable in form, frozen in kind," and the
  third mechanism class was never run.

### [`docs/assurance/ebmom-v2-form-b-mutation-receipt.md`](assurance/ebmom-v2-form-b-mutation-receipt.md)

- **Claims:** Mutant 1 of v2 section 7 — pooling removed on the refused path, reverting to the
  unpooled posterior the pre-registration retired — is KILLED at `d39440d` by
  `tests/test_aggregation_fit_bounded_pooling.py::test_mutant_1_tie_heavy_null_refused_false_fail_rate`,
  measured by `scripts/mutation_receipt.py` in its own git worktree at a fixed commit with
  production never mutated in place, recording both worktree HEADs, the `module.__file__`
  actually imported, clean and mutant source digests, that the digests differ, that the mutant
  compiles, that the clean baseline passed first with nonzero collection, and that the
  production tree was byte-unchanged afterwards. The selection carries three node ids so the
  receipt shows which assertion moved and which did not: only the kill assertion failed, while
  the positive control (the retired unpooled fallback REJECTING the same registered test on the
  same worlds) and the refusal guard (all 41 replicates refused) stayed green under the mutant,
  which excludes both an empty-cell kill and a kill through the wrong mechanism. The regime
  makes every FAIL false by construction: `tie_heavy_null` is homogeneous at a true encoded mean
  of 0.65 against a 0.60 threshold.
- **Refuses to claim:** Any mutation score, or that one mutant is a campaign — mutants 2, 3 and
  4 of section 7 are not measured here and belong to #443, #443 and #442, with #444 collecting
  all four; that form B passes the acceptance matrix, since no confirmatory run has been
  performed and v2 section 5 keeps the branch unmerged until one is; that its numbers are
  results rather than a detectability demonstration, since they are R = 41 under the throwaway
  root `SMOKE_NOT_CONFIRMATORY` rather than the R = 1000 figures section 7 cites; anything
  whatever about the admitted path or about the fresh root, which does not yet exist.

### [`docs/assurance/ebmom-class2-reproduction-R40-SMOKE_NO.md`](assurance/ebmom-class2-reproduction-R40-SMOKE_NO.md)

- **Claims:** The built `fit_skill`, scored through `scripts/ebmom_form_b_reproduction.py
  --column cand_pb` at R = 40 on the throwaway root `SMOKE_NOT_CONFIRMATORY`, reproduces 15 of
  the 20 per-path cells of the `cand_pb` column of `proto-pb-all-R40-SMOKE_NO.json` (five
  regimes, both paths, rows 5c and 6c, compared on false count, decision count, `G` and `g`),
  and reproduces ALL 20 when the same production code is driven with the prototype's own draw
  seed. Every refused-path cell agrees in every regime, `tie_heavy_null` refusing all 40
  replicates, so the admitted-path mechanism left the refused path untouched. The five that
  differ under production's own seed are all admitted-path, in `small_n_bite` (6c decision count
  9 against 8) and `tie_heavy_signal` (5c count 7 against 6, of 864 against 854), and the
  diagnostic run isolates the seed as the whole of the difference: the prototype seeds from
  `<root>|<regime>|<world>|pb`, which `fit_skill` cannot compute, so the frozen derivation gives
  it `<canonical clause encoding>|pb` and a different stream.
- **Refuses to claim:** That the built candidate reproduces `cand_pb` under its own seed — it
  does not, in two regimes, and #442's acceptance criterion asking for that is recorded NOT MET
  as written rather than reinterpreted; anything about R = 1000 or R = 4000, which the harness
  ticket owns and where a one-decision difference may or may not persist; that any cell passes
  or fails the v2 section 5 kill rows, which need a confirmatory run that has not been performed;
  that any number here is confirmatory, the root being a development smoke.

### [`docs/assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.md`](assurance/ebmom-form-b-reproduction-R40-SMOKE_NO.md)

- **Claims:** The twin of `ebmom-form-b-reproduction-R40-SMOKE_NO.json`, recording that receipt
  as FROZEN at `#458` rather than regenerated. The receipt itself is a dated record of the state
  at `d39440d`: production reproduced the prototype's `cand_bpB` column (form B on refusal,
  plug-in on the admitted path) at R = 40 on `low_heterogeneity` and `tie_heavy_null`, on the
  throwaway root `SMOKE_NOT_CONFIRMATORY`, with `total_differences` 0. Three measurements taken
  2026-09-08 support the freeze: the receipt's `expected_file`
  (`proto-pb-all-R40-SMOKE_NO.json`) is not in the repository; that dump embeds a wall-clock
  `seconds` field per regime (`proto_pb.py:238`), so its pinned `expected_sha256` is
  unreproducible - two regenerations differ from the pin and from each other, and are identical
  once `seconds` is dropped; and the receipt's own command line, run against production on this
  branch, exits 1 with exactly three differing cells, all in
  `low_heterogeneity.row5c_false_pass_admitted`, with `tie_heavy_null` agreeing entirely. The
  twin also records that the reference directory repaired under `#458` regenerates a `cand_bpB`
  column matching the receipt's recorded `built` block on 32 of 32 compared fields.
- **Refuses to claim:** Anything about production at or after `60a6548` - the receipt does not
  assert current reproduction and must not be read as asserting it; that the three differing
  cells are a regression, the differences being confined to the admitted path `#442`
  deliberately changed while the refused path form B governs still agrees; that the receipt
  could be regenerated into a current claim without new measurement machinery; anything
  confirmatory, `is_confirmatory` being false and the root a development smoke; anything about
  R = 1000 or R = 4000, which this receipt never measured; a keep/cut verdict or any result
  about the estimator.

### [`docs/assurance/ebmom-v2-class2-mutation-receipt.md`](assurance/ebmom-v2-class2-mutation-receipt.md)

- **Claims:** Mutant 4 of v2 section 7 - the admission-conditioned parametric bootstrap removed
  from the admitted path and the plug-in posterior restored - is KILLED at `60a6548` by
  `tests/test_aggregation_fit_admitted_bootstrap.py::test_mutant_4_low_heterogeneity_admitted_false_fail_rate`,
  measured by `scripts/mutation_receipt.py` in its own git worktree at a fixed commit with
  production never mutated in place, recording both worktree HEADs, the `module.__file__`
  actually imported, clean and mutant source digests, that the digests differ, that the mutant
  compiles, that the clean baseline passed first with nonzero collection, and that the production
  tree was byte-unchanged afterwards. The selection carries three node ids so the receipt shows
  which assertion moved and which did not: only the kill assertion failed, while the positive
  control (the plug-in posterior REJECTING the same registered test on the same four fits, three
  false of four, exact binomial p = 4.8e-4) and the admission guard (all four worlds reaching
  `ebmom_hierarchical`) stayed green under the mutant, which excludes both an empty-cell kill and
  a kill through the wrong mechanism. The mutation leaves the bootstrap running and discards its
  result, so nothing but the decision path can account for the kill.
- **Refuses to claim:** Any mutation score, or that one mutant is a campaign - mutants 1, 2 and 3
  of section 7 are measured elsewhere (#441, #443) with #444 collecting all four; that the
  admitted 6c cell's MEMBERSHIP was re-derived, since the four worlds come from v2 section 0.5's
  `find_fail_worlds.py` scan and this receipt re-derives only the decisions on them, the control
  being what makes the borrowed membership falsifiable; that the mechanism is calibrated, the cell
  being four decisions where v2 section 5 rates a pass as weak evidence; that the mechanism passes
  the acceptance matrix, since no confirmatory run has been performed and v2 section 5 keeps the
  branch unmerged until one is; anything about the fresh root, which does not yet exist.

### [`docs/assurance/ebmom-v2-section-7-mutation-receipts.md`](assurance/ebmom-v2-section-7-mutation-receipts.md)

- **Claims:** That the four mutants registered in v2 section 7 have four mutation receipts in
  `docs/assurance/`, and names for each one the mutant, its id, the receipt, the file it targets,
  the verdict and the assertion that killed it. Every row was checked against the receipts and
  against the tree when written: all four verdicts are KILLED, and all four killing assertions
  exist under the names given. It is an index over receipts, so its authority is entirely
  borrowed - each receipt is the evidence for its own row.
- **Refuses to claim:** Any digest, deliberately - each receipt pins the files it measured in its
  own `target_digests`, and `tests/test_mutation_receipt.py` holds that pin honest against both
  the live tree and the receipt's own prose, so a digest copied into an index would be guarded by
  neither and could go stale in silence while both tests stayed green. That four is a mutation
  score or a campaign result. That the other mutation receipts in the same directory are section 7
  mutants - they are not, and a reader counting files there will get a larger number. That the
  EB-MoM gate receipt's one SURVIVED case is a failure, it being a preserved finding. That the
  mechanism passes the acceptance matrix, since no confirmatory run has been performed and v2
  section 5 keeps the branch unmerged until one is. Anything about the fresh root, which does not
  yet exist and is the maintainer's to generate. That the index is self-policing: no test checks
  it is complete against section 7, so a mutant added or removed there leaves this page wrong and
  silent.

### [`docs/assurance/ebmom-v2-per-path-split-mutation-receipt.md`](assurance/ebmom-v2-per-path-split-mutation-receipt.md)

- **Claims:** Mutant 2 of v2 section 7 - the per-path split removed, so every decision is
  tallied on one lane and the refused-path cell cannot be reported at all - is KILLED at
  `9a81e83` by
  `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G`,
  measured by `scripts/mutation_receipt.py` in its own git worktree at a fixed commit with
  production never mutated in place, recording both worktree HEADs, the `module.__file__`
  actually imported, clean and mutant source digests, that the digests differ, that the mutant
  compiles, that the clean baseline passed first with nonzero collection, and that the production
  tree was byte-unchanged afterwards. The selection carries three node ids so the receipt shows
  which assertion moved and which did not: only the kill assertion failed, while the positive
  control (the POOLED cell unchanged, because pooling loses the path and never the decisions) and
  the guard (the two fixture worlds re-derived from `fit_skill` reaching different paths) stayed
  green under the mutant, which excludes both an emptied fixture and a kill through the wrong
  mechanism. The receipt records that the FIRST control was wrong - it died beside the kill and
  the generator reported two killing assertions - and what replaced it.
- **Refuses to claim:** Any mutation score, or that one mutant is a campaign - mutants 1, 3 and 4
  of section 7 are measured elsewhere with #444 collecting all four; anything about any cell's
  rate, verdict or kill status, this being a receipt about the report's structure and not about
  the candidate; that the candidate passes the acceptance matrix, since no confirmatory run has
  been performed and v2 section 5 keeps the branch unmerged until one is; anything about the
  fresh root, which does not yet exist.

### [`docs/assurance/ebmom-v2-one-per-world-mutation-receipt.md`](assurance/ebmom-v2-one-per-world-mutation-receipt.md)

- **Claims:** Mutant 3 of v2 section 7 - the one-decision-per-world selection replaced by all
  decisions, restoring the test that treats clause decisions as independent - is KILLED at
  `16da76b` by
  `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_3_two_correlated_false_decisions_do_not_reject`,
  measured by `scripts/mutation_receipt.py` in its own git worktree at a fixed commit with
  production never mutated in place, recording both worktree HEADs, the `module.__file__`
  actually imported, clean and mutant source digests, that the digests differ, that the mutant
  compiles, that the clean baseline passed first with nonzero collection, and that the production
  tree was byte-unchanged afterwards. The selection carries three node ids so the receipt shows
  which assertion moved and which did not: only the kill assertion failed, while the positive
  control (the retired all-decision test REJECTING the same fixture, two false of two, exact
  binomial p = 0.0025) and the guard (the fixture being one world carrying two decisions) stayed
  green under the mutant, which excludes both an inert fixture and a kill through the wrong
  mechanism.
- **Refuses to claim:** Any mutation score, or that one mutant is a campaign - mutants 1, 2 and 4
  of section 7 are measured elsewhere with #444 collecting all four; anything about any
  registered regime's cells, the fixture being synthetic and two decisions wide; that the
  selection has the right POWER, only the right level, section 2.1 stating separately what is
  discarded and why the remaining power is judged sufficient; that the candidate passes the
  acceptance matrix, since no confirmatory run has been performed and v2 section 5 keeps the
  branch unmerged until one is.

### [`docs/assurance/ebmom-v2-reproduction-R1000-f95e4de5.md`](assurance/ebmom-v2-reproduction-R1000-f95e4de5.md)

- **Claims:** Parts (a), (b) and (c) of the S417 amendment against
  `proto-pb-all-R1000-f95e4de5.json` (SHA-256 recorded), all five registered regimes at R = 1000
  on the burned root, 9,428.5 s. (a) PORT IDENTITY HOLDS: under the injected prototype seed
  production reproduces the dump with ZERO differing cells in every regime, all four columns,
  both paths, both rows, the pooled rows and the vs-oracle excesses. (b) Under the production
  seed 39 cells differ, every one of them `cand_pb`, driven by 2,836 near-cut flips in 740,800
  admitted clause decisions with a largest absolute tail movement of 0.0381; `cand_bpB`, `oracle`
  and `main` agree cell for cell, which is what the S417 ruling predicts of columns that do not
  draw the admitted-path stream. (c) v2 section 4's freeze condition on worlds 500 to 999 under
  the production seed rejects NO candidate cell in any regime and the oracle self-check passes
  every one of the 11 testable cells. Reported beside each cell: false over decisions, `G`, `g`,
  the selected-false count, the rejecting count, the p-value, the world-block bound and the
  reliability table. `main` independently reproduces v2 section 6's written prediction to the
  decimal (admitted 6c 40.3 percent false in `low_heterogeneity`, 12.4 percent in
  `small_n_bite`). Receipt identity, both halves of v1 section 8 plus the v2 SHA:
  `ebmom-v2-reproduction-identity-f95e4de5.json`.
- **Refuses to claim:** That the candidate reproduces `cand_pb` under its OWN seed - it does not,
  and the S417 amendment is why that is reported rather than treated as a defect; any
  confirmatory result or verdict on the candidate, the root being burned development evidence
  seen in full before every choice v2 records, with the fresh root not yet generated and v2
  section 5 keeping the branch unmerged; the consequence of part (c), which v2 section 4 owns and
  which nothing triggered; that the `low_heterogeneity` admitted 6c cell is evidence of anything,
  since at `G = 1` no selection could have rejected it and the harness prints that rather than
  leaving it to be inferred; any verdict on `main`.

### [`docs/assurance/ebmom-v2-reproduction-R4000-low_heterogeneity-f95e4de5.md`](assurance/ebmom-v2-reproduction-R4000-low_heterogeneity-f95e4de5.md)

- **Claims:** The same three parts against `proto-pb-low_heterogeneity-R4000-f95e4de5.json`
  (SHA-256 recorded), `low_heterogeneity` at R = 4000 on the burned root, 5,718.3 s. (a) PORT
  IDENTITY HOLDS: zero differing cells under the injected prototype seed, all four columns. (b)
  Eleven `cand_pb` cells differ under the production seed, with every one of the 2,458 flips in
  565,000 admitted clause decisions sitting within 0.0038 of a decision cut and no clause moving
  by more than 0.0379; the flips are close to symmetric at the PASS cut (1,299 UNDECIDED to PASS,
  1,157 PASS to UNDECIDED, 2 FAIL to UNDECIDED). (c) The S414 extension of the freeze condition,
  worlds 1,000 to 3,999 under the production seed, rejects no cell: the admitted 6c cell is 1
  false of 7 selected across 7 decision-bearing worlds, `p = 0.302`, with a rejecting count of 3,
  so it passes WITH POWER - a replication of the S414 result (`1 / 5`, `p = 0.226`) on a second
  stream. The oracle self-check passes both testable cells.
- **Refuses to claim:** That the candidate reproduces `cand_pb` under its own seed; any
  confirmatory result; the consequence of part (c), which belongs to v2 section 4; that the
  admitted 6c cell is safe - over the full 4,000 worlds it is 2 false of 8 selected against a
  rejecting count of 3, one selection from rejecting, which the receipt states rather than
  buries, and v2 section 5 rates a pass in a cell that small as weak evidence; any verdict on
  `main`, whose two 6c cells fail decisively on the same worlds.

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
  measured, 1,909 covered. Later rows are appended with their own measurement
  date rather than re-totalled into that census: `matched_bridge.py` (2026-08-16,
  #246), `binding.py` (2026-08-17, #263), and `ablation/arms.py` (2026-09-21,
  #554) each carry a row under the same attention rule and a dated paragraph in
  the report; the three later rows are unmeasured by #166 and stay flagged on
  the mutation arm of the rule.
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

### [`docs/assurance/release-gate-red-563.md`](assurance/release-gate-red-563.md)

The deterministic falsification receipt for the real-tree release-gate control
(#563), the counterpart to the seeded-tree receipt above.

- **Claims:** Two seeded mutations each drove `python scripts/release_gate.py`
  on the real repository tree, with no `--root`, to exit 1 with the gate's
  stdout recorded verbatim. One set a README status banner to `v0.2.9` against a
  tree declaring `0.3.0`, naming one G3 lockstep failure and reddening two
  tests. The other short-circuited `main` off the tree's version, naming three
  failures and reddening three tests including the request-set assertion; a
  third mutation, `gate_workflows_sha_pinned` neutered so its glob matches no
  file, left both release-gate modules green and is recorded as a measured
  limit rather than as a pass.
- **Refuses to claim:** That the transcripts were re-derived by a live run;
  they are a dated record, and the checked-in control asserts only that the
  receipt still names its command, its seeded mutation and its exit code; that
  the surviving mutant is a defect in the control rather than a property of the
  verdict-reading seam; that the enumerated survivors are the complete set of
  mutations this seam cannot see; that a green real-tree run establishes the
  gate asked every question it declares, rather than that it reported no
  failure.

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

### [`docs/assurance/pi-adapter-refusal-mutation-receipt.md`](assurance/pi-adapter-refusal-mutation-receipt.md)

The mutation receipt for the Pi subject adapter's own three refusal
predicates (roster symmetry, parser identity, mid-epoch identity), generated
by `scripts/mutation_receipt.py --select pi-` into
[`pi-adapter-refusal-mutation-receipt.json`](assurance/pi-adapter-refusal-mutation-receipt.json).

- **Claims:** three named mutants of `subject/pi/launcher.py` and
  `subject/pi/parser.py`, each run in its own git worktree, all KILLED by
  named nodes in `tests/test_subject_pi.py`: emptying the cross-arm baseline
  check, skipping the declared-vs-live parser identity comparison, and
  dropping the second-`model_change` count guard against a discriminating
  fixture whose repeated change carries the SAME subject (only the count
  guard can fire).
- **Refuses to claim:** a mutation score; anything about the DRIVER'S wiring
  of these helpers (that is the driver-wiring receipt, below); anything
  about the scientific refusal predicates downstream, which the #387
  exposure receipt attests.

### [`docs/assurance/pi-driver-wiring-mutation-receipt.md`](assurance/pi-driver-wiring-mutation-receipt.md)

The mutation receipt for the Pi paired lane's production driver
(`subject/pi/runner.py`): the four receiptable cases from the scratch
session's five hand mutations, converted to the #341 standard because
transcript-only mutation claims are not checkable by a reader. Generated by
`scripts/mutation_receipt.py --select mr-` into
[`pi-driver-wiring-mutation-receipt.json`](assurance/pi-driver-wiring-mutation-receipt.json).

- **Claims:** four named mutants, all KILLED by named nodes in
  `tests/test_subject_pi_runner.py`: the driver stops COMPARING the declared
  parser identity (M-R1 — the mutant reaches spend and fails with DID NOT
  RAISE; a first-generation mutant that crashed with NameError instead was
  caught and corrected 2026-09-09, documented in the receipt), the
  nonzero-returncode refusal no longer fires (M-R2), the version probe stops
  wrapping the container prefix (M-R4), and the driver stops passing its
  `container=` to the probe with the helper intact (M-R5). M-R4/M-R5 pair on
  purpose: mechanism AND wiring, each shown to matter. The scratch session's
  M-R3 (delete the gate call) is subsumed by M-R1 against the same killing
  tests and is not a separate obligation. **Rename note (2026-09-14, #536):**
  the ids `M-R1` and `M-R2` in this entry are the receipt's original ids and
  are kept here because the receipt is a record; in `scripts/mutation_receipt.py`
  they are now `M-R6` and `M-R7`, because `M-R1`/`M-R2` collided with the
  `389-` pair in `paired-gate2-mutation-receipt`, which keeps them.
- **Refuses to claim:** a mutation score; that the helpers' predicates are
  themselves correct (the adapter receipt's obligation, disjoint from this
  one); anything about the containerized execution path, which is
  implemented and unwired-tested but has never run a live epoch.

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

### [`docs/assurance/pi-adapter-refusal-mutation-receipt.md`](assurance/pi-adapter-refusal-mutation-receipt.md)

The mutation receipt for the three apparatus refusal predicates the Pi subject
adapter owns, generated by `scripts/mutation_receipt.py --select pi-` into
[`pi-adapter-refusal-mutation-receipt.json`](assurance/pi-adapter-refusal-mutation-receipt.json).

- **Claims:** Three named mutants of `src/skill_harness/subject/pi/launcher.py`
  and `src/skill_harness/subject/pi/parser.py` were each run in its own git
  worktree, pinned by content digest rather than by commit, and all three were
  KILLED by named test nodes: emptying the cross-arm baseline check in
  `verify_pair_symmetry`, skipping the declared-vs-live comparison in
  `verify_parser_identity`, and dropping the second-`model_change` count guard
  in `_verify_identity`.
- **Refuses to claim:** A mutation score (three hand-chosen cases cannot support
  one, and the receipt states this); that the predicates fire on the production
  path (a mutant proves the FUNCTION refuses, not that a caller invokes it —
  that property is established separately by the production-path tests in
  `tests/test_subject_pi_runner.py`); coverage of any adapter refusal outside
  the three named obligations; and any scientific claim whatsoever, since these
  are apparatus checks upstream of the scientific refusal predicates attested by
  the #387 receipt.

### [`docs/assurance/hazard-entry-segmentation-mutation-receipt.md`](assurance/hazard-entry-segmentation-mutation-receipt.md)

The mutation receipt for the #438 hazard-entry counting repair, generated by
`scripts/mutation_receipt.py --select 438` into
[`hazard-entry-segmentation-mutation-receipt.json`](assurance/hazard-entry-segmentation-mutation-receipt.json).

- **Claims:** Three named mutants of `src/skill_harness/subject/paired_launch.py`
  were each run in its own git worktree at commit `57aed6b` under Python 3.13.1
  against the file at
  `sha256:6b04484e151e017c0b000f3326df7309a9eb93025a14b25294db1477fd41bd3a`, and
  all three were KILLED by named test nodes: returning the whole command string
  as one segment, so a chained command is matched as a blob again (killed by
  `TestSimpleCommands::test_splits_a_chain_on_every_unquoted_operator` and four
  cases in `TestHazardCommandCases`); returning `AVOIDED` for a string that
  cannot be segmented at all, so a heredoc reads as the trap avoided (killed by
  the two whole-string `test_case` rows); and returning `AVOIDED` when a single
  SEGMENT cannot be read while the whole-string refusal keeps working (killed by
  the `echo foo\` row alone). Each case asserted its clean baseline passed first
  with a nonzero collection, that the imported `module.__file__` resolved inside
  its own worktree, that the source digests differed, that the mutant imported,
  and that the production tree was byte-unchanged afterwards. The third mutant
  is the finding: when the campaign was first written the per-segment refusal
  had no detector at all and that mutant would have SURVIVED, so the killing
  case was added in response.
- **Refuses to claim:** A mutation score - three hand-chosen mutants cannot
  support one; adequacy of the paired-launch test suite as a whole; that the
  hazard pattern registered for the `git-pull-rebase-trap` family is correct
  (the pattern lives in RAT-0001 Amendment 5 and in the test module, not in
  production code, so no mutant here can reach it; its evidence is the
  eight-log measurement in that amendment); that the private pilot logs were
  read during this campaign (`TestPilotLogsUnderThePatternOfRecord` skips where
  they are absent and is named as no mutant's killing test); anything about a
  strategy established in repository config, which this instrument does not
  read by construction.

### [`docs/assurance/path-c-tie-encoding-mutation-receipt.md`](assurance/path-c-tie-encoding-mutation-receipt.md)

The mutation receipt for the #368 Path C migration, which routes tie-bearing
ablation clause decisions through the Gate-2 discordant machinery under the
estimand ruled 2026-08-31 (`docs/INVARIANTS.md` §8). Generated by
`scripts/mutation_receipt.py --select 368-` into
[`path-c-tie-encoding-mutation-receipt.json`](assurance/path-c-tie-encoding-mutation-receipt.json).

- **Claims:** Four named mutants were each run in its own git worktree at
  commit `24c1cdc` under Python 3.13.1, against
  `src/skill_harness/ablation/stopping.py` at `sha256:fc85702b` and
  `src/skill_harness/ablation/path_c.py` at `sha256:4af1162c`, and all four
  were KILLED by named test nodes: restoring the half-update posterior
  `Beta(1+w, 1+n-w)` (killed by `test_stopping_decision_agreement` on both
  win-heavy fixtures and by `test_production_accumulator_no_longer_dilutes`);
  pointing the N_MIN evidence gate at the total comparison count instead of
  the discordant count (killed by
  `test_ties_cannot_buy_a_clause_past_the_evidence_bar`); sizing the Gate-2
  design by the discordant count so the tie cell is discarded and the
  effect-size floor disappears (killed by
  `test_ties_reach_the_decision_rather_than_being_discarded` and
  `test_tie_heavy_win_is_held_below_the_effect_floor`); and accepting a
  ratification record that omits a Gate-2 threshold instead of refusing it
  (killed by `test_missing_threshold_refuses_rather_than_defaulting`). Each
  case asserted its clean baseline passed first with nonzero collection, that
  the imported `module.__file__` resolved inside its own worktree, that the
  source digests differed, that the mutant imported, and that the production
  tree was byte-unchanged afterwards.
- **Refuses to claim:** A mutation score — four hand-chosen mutants cannot
  support one; adequacy of the ablation test suite as a whole; that the
  migration is correct, as distinct from the four named defects being
  detected; **any operating-characteristic claim** — the lane applies the
  registered fixed-N decision rule to a sequentially-stopped realised table,
  and the registered design's error rates do not transfer to it; and **any
  empirical claim about a real skill**, since no paid measurement was run and
  whether a shipped verdict changes is #419's and #420's question.

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
