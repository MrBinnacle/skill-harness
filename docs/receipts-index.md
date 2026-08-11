# Measurement receipts index

One page for every measurement receipt this project has produced. Each entry
states **what it claims** and **what it refuses to claim**. A missing number
is a typed refusal, never an invented score.

Completeness is CI-gated: `tests/test_receipts_index.py` fails if any file in
the named receipt directories is absent from this page.

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
  Full-vs-Null first; differentiation is UNMEASURED + admissibility + pin
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

---

## Ratifications

Forward-looking `RAT-*.md` records bind pre-spend ablation launches (see
[`docs/ratifications/README.md`](ratifications/README.md)). **None are on disk
yet** — the completeness glob is `docs/ratifications/RAT-*.md`, so the first
ratification file must gain an entry here in the same change.

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

### [`docs/sers/receipts/reclass-git-pull-rebase-trap.json`](sers/receipts/reclass-git-pull-rebase-trap.json)

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
