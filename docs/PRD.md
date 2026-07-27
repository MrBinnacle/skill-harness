# Product Requirements Document

## Product Name

Skill Harness: Clause-Ablation Differential Testing for LLM Skills

Version: 1.1
Status: Ratified
Author: TBD

<!-- v1.1 changelog: 47 amendments applied (45 from Phase 3.5 audit + 2 from Appendix G).
     Rationale per amendment lives in the internal council findings log (not published).
     PRD stays spec; Council stays rationale. -->

> **Amendment note (2026-07-26).** This is the ratified v1.1 spec; two sections
> below predate the shipped v0.2 surface and are retained as the record rather
> than silently rewritten:
>
> - **§12** lists Compliance Proxy, Citation Density, and Hedge Index as
>   *Demoted from Tier 1 (NOT mechanical without further support)*. The
>   "further support" subsequently shipped: the A33 mechanical-validity gate
>   (offline, deterministic, bit-equal — see "Mechanical validity" below §12),
>   and the v0.2.0 registry
>   (`ablation/confound.py::get_default_tier1_scorers`) carries five Tier-1
>   scorers: `verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`,
>   `citation_presence_per_flag`.
> - **§18**'s "surface is locked — no new commands" records the v1.1 lock.
>   v0.2 extended the surface under its own pre-registered gate
>   (`docs/findings/v0.2-reaim-gate.md`): `skill audit` and the `screen` group
>   (`screen verdict`, `screen backfill`). See `CHANGELOG.md` 0.2.0 / 0.2.0a0.

---

# 1. Executive Summary

In plain terms: this tool measures whether a skill actually changes what an AI agent does. It
runs the same task with the skill present and with it removed, compares the two, and refuses
to invent a score when the evidence is too weak to support one. This document is the full
specification of how that measurement is kept honest.

Skill Harness is a deterministic evaluation framework for testing LLM skills (instruction files, prompt modules, behavioral overlays, and similar artifacts) using falsifiable contracts rather than output inspection.

Traditional software testing assumes:

* deterministic execution
* explicit output oracles
* stable function boundaries

Skills possess none of these properties.

The harness's novel and defensible claim is the *evidentiary discipline* — falsifiable directional contracts with write-time admissibility-gated, append-only provenance. This is the P4 signature (zero hits in the eval domain at the time of design). The estimator (Leave-One-Out clause ablation) is deliberately conservative: under-crediting contribution is a safe failure for an adversarial audit (false-negative on contribution, never false-positive on a PASS).

Skill Harness applies clause-level prompt-component ablation — as in Sclar et al. (arXiv:2310.11324, FormatSpread / component ablation), Longpre et al. (arXiv:2301.13688, FLAN component ablations) — to skill artifacts, with three disciplines: directional-only oracles, admissibility gating, and append-only provenance. Redundancy cancellation (JoPA, Chang et al. arXiv:2405.20404) is a documented v0.1 limitation; LOO under-credits contribution when clauses are jointly redundant, never over-credits.

The system evaluates whether a skill clause produces a measurable directional effect when present versus absent.

The harness never asks:

> "Is this output good?"

Instead it asks:

> "Does output A outperform output B on the single axis claimed by clause N?"

The resulting system produces empirical evidence for or against individual skill contracts and supports regression testing across skill revisions.

---

# 2. Problem Statement

Skills are increasingly used as reusable behavioral modules.

Unlike software:

* Skills do not have deterministic outputs.
* Skills rarely have ground-truth answers.
* Skills often make behavioral claims that are difficult to verify.
* Existing evaluation systems frequently rely on LLM self-grading.

Current evaluation methods hide uncertainty behind subjective judgments and aggregate confidence without validating the source of that confidence.

The result is a system that can report improvement while remaining unable to prove that any specific instruction contributed to that improvement.

Skill Harness exists to measure clause-level contribution.

---

# 3. Design Principles

## 3.1 Directional Evaluation

All evaluation is comparative.

Forbidden:

* quality scoring
* holistic grading
* "is this good?"

Required:

* A beats B on axis X

Reconciliation with §5 Tier 2: the Tier-2 LLM judge is admissible **only** in pairwise-preference mode for one named axis at a time. Judge prompts MUST present both candidates, MUST output one of `{A, B, tie}` for one axis, and MUST NOT emit a numeric score. G-Eval-style scalar templates (Liu et al. arXiv:2303.16634) are explicitly forbidden under §3.1.

---

## 3.2 Clause Isolation

Every skill is decomposed into atomic contracts.

A clause is tested through:

* Full skill
* Clause removed
* Null skill

Measurements are based on deltas between conditions.

---

## 3.3 Admissible Evidence Only

Evidence enters aggregation only if admissibility requirements are satisfied.

No component may self-certify its own reliability.

---

## 3.4 Falsifiability First

A clause is not considered tested until it has at least one falsifying case.

A clause without a possible failure mode is metadata, not a contract.

---

## 3.4a Falsifying Case Schema

Each clause declares the triple `(input_population_spec, expected_directional_pair, min_reproducibility)`. Until that schema is frozen (SHA-256 stored in `clauses.falsifying_case_schema_sha256`), the clause cannot transition to PASSED — regardless of posterior.

Formal gate: `PASSED ⇔ posterior_threshold_met ∧ ≥1 frozen_case_at_current_metric_version`.

---

## 3.5 Provenance Preservation

Every measurement must retain:

* source
* oracle
* version
* admissibility state

Historical evidence is append-only.

---

# 4. Core Evaluation Model

## 4.1 Skill

A skill is a user-authored instruction artifact.

Examples:

* Markdown instruction files
* Prompt modules
* Behavioral overlays
* Claude skills

---

## 4.2 Clause

An atomic directional contract.

Example:

> Require citations for factual claims.

Becomes:

Axis: `citation_support`
Comparator: `increase`

---

## 4.3 Conditions

Each test executes three conditions.

### Full

Complete skill.

### Ablated

Skill with exactly one clause removed.

### Null

No skill.

---

## 4.4 Measurement

The measurement unit is not an output.

The measurement unit is:

`Full beats Ablated`

or

`Full beats Null`

on a specific axis.

---

# 5. Oracle Model

## Tier 1: Mechanical

Deterministic counting procedures.

Examples:

* unsupported claim ratio
* hedge frequency
* citation density
* bullet ratio

Preferred whenever possible.

---

## Tier 2: Human-Calibrated Judge

Used only when no reliable mechanical metric exists.

Requirements:

* human-labeled calibration set
* tracked agreement score
* admissibility enforcement
* pairwise mode only — output one of `{A, B, tie}` for one named axis; numeric/scalar grading forbidden
* mandatory position swap — every verdict requires both `(A, B)` and `(B, A)` orderings; disagreement on swap → `position_swap_agreement = 0` → `admissibility_state = 'inadmissible'` (reason `position_disagreement`)
* length-controlled scoring — AlpacaEval-2 length-regression protocol (Dubois et al. arXiv:2404.04475) applied both at prompt-time (max_tokens=80 with "length should not influence" instruction) and observation-time; `length_regression_coefficient` stored separately from `length_controlled_agreement`; both raw and length-adjusted observations persisted at write time
* judge identity is bound to `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)`; the tool schema is part of the calibration scope, NOT swappable post-calibration
* judge invoked via tool_use with `strict: true`, `tool_choice` forced, schema `report_verdict({choice: enum[A,B,tie], rationale_brief})`. As-built defense layers, all required before a verdict can be written: (1) forced tool_use schema, (2) 8KB UTF-8 output truncation, (3) XML-delimited sandboxing of candidate outputs in the system prompt, (4) meta-token/injection regex short-circuit (cost-zero, before any API call), (5) mandatory position-swap (AB + BA calls, `oracles/tier2/judge.py`). Two v0.1 gaps, tracked for v0.2, not shipped: a null-baseline distributional check, and the `[untrusted model output]` UI prefix on `rationale_brief` — the field is persisted as audit-only data but is not currently rendered anywhere in the CLI/UI.

The judge is an instrument.
It is never the source of truth.

---

## Tier 3: Real-World Consequence

Terminal oracle.

Examples:

* issue closure rate
* contributor time-to-PR
* production incident reduction

Highest authority when available.

**v0.1 status: DEFERRED.** No published precedent attributes a real-world outcome to a single skill clause; whole-tool effects (Peng et al. arXiv:2302.06590; Cui et al. 4000+ devs) do not satisfy clause-level instrumentation. Lag time weeks-to-months; SNR effectively zero without a clause-instrumented RCT. `frozen_cases.oracle_source` CHECK constraint excludes `'real_world'` for v0.1. Re-evaluate post-v0.1 dogfooding.

---

# 6. Admissibility System

## Purpose

Prevent unvalidated judges from entering scoring.

---

## Rule

Tier-2 verdicts are inadmissible unless ALL of the following hold for the `(judge_id, axis)` pair:

* a calibrated record exists with `pairwise_agreement ≥ 0.7`
* `position_consistency ≥ 0.8`
* `length_controlled_agreement` recorded; Cohen's κ `≥ 0.40` (observed-marginal, chance-corrected) — hard-gates admissibility at pair-set size N ≥ 100 (see §13)
* calibration set size `≥ 50` pairs
* re-calibration cadence ≤ 90 days OR no model-version bump since

See §5 Tier 2 for the seven-layer adversarial defense stack required for any Tier-2 verdict to enter the admissibility pipeline.

---

## §6.1 Calibration input schema

Calibration inputs are strict JSONL with eight required fields: `pair_id, axis, prompt, response_a, response_b, human_preference, labeler_id, labeled_at`.

State enum (admissibility classes by pair-set size N):

* `rejected` (N < 50) — calibration refused; downstream verdicts inadmissible
* `conditional` (50 ≤ N < 100) — admissible with size-warning surfaced in reports
* `calibrated` (N ≥ 100) — admissible

Cohen's κ on the 3-class outcome (A/B/tie) uses observed marginals, NOT 1/3 uniform.

v0.1: no starter set ships; user-provided JSONL only. Operator-self-label admissibility is rejected (resolved 2026-06-06 by SME verdict on independence-collapse grounds; see Appendix E C2 resolution).

---

## §6.2 Length-control storage

Length control in v0.1 is calibration-time only, not verdict-write-time. `oracle_verdicts` stores a single `observation` column (`{0.0, 0.5, 1.0}`) — there are no `raw_observation` or `length_adjusted_observation` columns in the schema, and no per-verdict length correction is applied or stored (`JudgeVerdict.length_adjusted_observation` is hard-coded `None` on every path through `oracles/tier2/judge.py`).

What ships in v0.1: (a) a prompt-side instruction to the judge that response length should not influence its choice (`oracles/tier2/judge.py::_build_prompt`); (b) a calibration-time length-controlled agreement check — `calibrate()` fits an OLS length-regression coefficient (`β₁`, `oracles/calibration/length_regression.py`) over the calibration pair set, derives `length_controlled_agreement`, and gates the `(judge_id, axis)` calibration state on it whenever a value is computed (`_THRESHOLD_LENGTH_CONTROLLED = 0.65` in `oracles/calibration/command.py::determine_state`). This is a judge-level admissibility gate, not a per-verdict correction.

Per-verdict, write-time length adjustment (the schema in the previous revision of this section) is not implemented; tracked for v0.2.

---

## Storage

Admissibility is recorded at write time.
It is never recomputed.

---

## States

### Admissible

May enter aggregation.

### Inadmissible

Stored for audit only.
Cannot affect results.

---

## Principle

No admissible evidence ⇒ no claim.

---

# 7. Clause Extraction

## Goal

Convert prose instructions into atomic directional contracts.

---

## Output Schema

Each clause contains:

* clause text
* axis
* comparator
* oracle tier
* vacuity flag

---

## Vacuity Detection

A clause has one of three vacuity states (`clauses.vacuity_flag` enum):

* `not_vacuous` — has an observable delta and a constructible falsifying case
* `mechanical_vacuous` — claimed axis is not in `metric_library`; deterministic, auto-excluded from testing
* `semantic_vacuous_pending_review` — extractor judged the clause has no measurable axis or no constructible falsifying case (LLM judgment); stored as `UNMEASURED` with reason, NOT silently excluded

The extractor is itself a Tier-2 judge. v0.1 uses uncalibrated extraction with the `semantic_vacuous_pending_review` sentinel; `(extractor_id, skill_genre)` calibration is deferred to v0.2 (D4).

---

# 8. Coverage Law

A clause is untested until at least one falsifying case exists.

Coverage is measured by:

`tested_clauses / total_clauses`

where:

`tested_clause = clause with ≥1 falsifying case`

In v0.1, `total_clauses` is the authored clause set including all vacuity_flag values. v0.2 will additionally report `(tested / (total − mechanical_vacuous))` per Council D3, gated on extractor-calibration audit (D4).

≥15% extractor-flagged vacuity rate on a representative skill triggers D3 ship in v0.1.x.

---

# 9. Frozen Regression Suite

## Purpose

Capture failures permanently.

Every adversarial input that defeats a skill becomes a regression case.
The suite only grows.

---

## Oracle Provenance

Every frozen case stores:

* oracle source
* attribution
* timestamp
* metric provenance

---

## Oracle Sources

### Human

Requires:

* `labeled_by`
* `labeled_at`

### Mechanical

Requires:

* metric version

### Real World

Requires source attribution.

---

# 10. Metric Provenance

Mechanical oracles are versioned artifacts.

A frozen case must record:

* metric identity
* metric version
* implementation hash

Purpose:
Allow re-audit when metrics change.

---

# 11. Interaction Confounds

## Problem

Clauses interact.

Example:
`verbosity ↔ structure`

Removing one clause may unintentionally alter another axis.

---

## Detection

During ablation, every axis in `metric_library_v1` is monitored — not only clause-claimed axes.

Threshold: `delta > k · σ_axis(Null)`, with defaults `k = 2.0` and `N_null ≥ 30` for variance estimation. Below the N_null floor, confound detection is disabled for that axis and affected verdicts are reported as `UNMEASURED(underpowered)`. Uncalibrated Tier-2 axes are excluded from σ(Null) estimation.

`confound_events.delta_kind` enum:

* `observed_unclaimed_delta` — movement on a non-claimed axis; audit-only, never aggregated
* `confound_flagged` — movement on a claimed-but-other-clause axis; verdict outcome becomes `FLAGGED_CONFOUNDED`

Storage is threshold-triggered event-row only (no dense per-sample × axis matrix). All-axes deltas are computed in-memory per condition-cell at orchestration time.

---

## Result

The clause outcome becomes:

`FLAGGED_CONFOUNDED`

instead of pass or fail.

---

## Principle

A contaminated delta must never be reported as clean evidence.

---

# 12. Mechanical Metric Library (Initial)

*(v1.1 position — see the Amendment note at the top of this file: the demotions
below were later satisfied by the A33 mechanical-validity gate, and v0.2 ships
five Tier-1 scorers.)*

## Demoted from Tier 1 (NOT mechanical without further support)

* **Assertion Density** (`factual_claims / sentences`) — requires NLI / claim extraction
* **Unsupported Claim Ratio** — requires claim extraction + evidence-attribution
* **Compliance Proxy** — requires directive classifier (heuristic, fragile)
* **Citation Density** (regex) — false-positives on markdown code blocks
* **Hedge Index** — depends on a corpus-bound, context-blind wordlist

## Tier 1 admissible honest heuristics (deterministic, network-blocked)

* `assertion_density := declarative_sentences / total_sentences` (regex on punctuation + leading-verb)
* `unsupported_claim_ratio := sentences_lacking_inline_citation_marker / declarative_sentences` (regex for `[N]`, `[Author Year]`, URL, `(source: …)`)
* `verbosity := tokens / instruction_units`
* `structure_score` — derived from `header_ratio`, `bullet_ratio`, `section_balance`

---

## §12.1 Mechanical validity audit gate

Every Tier-1 metric must pass an offline-only, network-blocked, deterministic-output test before its `tier = 1` row inserts into `metric_versions`. Implementation primitive: `pytest-socket` + bit-equality assertion + `PYTHONHASHSEED=0` discipline; test modules carry `pytestmark = pytest.mark.disable_socket`. `metric_versions.mechanical_validity_test_passed = 1` flips only on tests-pass AND zero socket attempts. Failures auto-downgrade the metric to Tier 2.

§12.1's outcome is `mechanical_validity_test_passed` only; the `audited` flip is the separate operator act defined in §15.1.

---

## Unsupported

Rhythm metrics.

Sentence-length variance is not considered a valid structure proxy.

Status: Unaudited.
No frozen cases may be minted from it.

---

# 13. Calibration System

## Calibration Unit

`(judge_id, axis)`

---

## Calibration Inputs

Human-labeled frozen pair set.

---

## Outputs

**Calibration metric (primary, for pairwise mode):** position-swap-symmetric pairwise-preference agreement vs human labels.

**Thresholds:**

* pairwise-preference agreement `≥ 0.7`
* position-consistency `≥ 0.8`
* Cohen's κ `≥ 0.40` (observed-marginal calculation, not 1/3-uniform) — as-built this IS a fixed hard-gate threshold, enforced only at pair-set size N ≥ 100: `oracles/calibration/command.py::determine_state()` returns `rejected` (`cohen_kappa_below_threshold`) when κ falls below it, alongside the pairwise-agreement, position-consistency, and length-controlled-agreement checks. Below N = 100 (`conditional` tier), κ is computed and stored but not gated.
* minimum calibration set size = 50 pairs per `(judge_id, axis)`

**Re-calibration cadence:** every 90 days OR at the next model version bump (whichever first).

Calibration is axis-specific. No cross-axis inheritance allowed (load-bearing invariant — see CLAUDE.md Oracle tiering).

---

# 14. Aggregation Model

## Inputs

Only verdicts satisfying:

* admissible
* non-confounded

---

## Observation Encoding

Win = 1
Tie = 0.5
Loss = 0

---

## Posterior

`Beta(1,1)` prior

Posterior:
`Beta(1+w, 1+n−w)`

---

## Reporting

For every clause:

* posterior mean
* credible interval
* pass probability

---

## §14.1 Sampling rule

**Sampling rule (default):**

* `N_min = 8` per condition pair (above STAT-F3's analytic floor of 5)
* `N_inc = 4` (batch size between stop checks)
* `N_max = 40`
* Stop when `P(rate > 0.60) ≥ 0.95` (PASS) OR `P(rate > 0.60) ≤ 0.05` (FAIL); else add `N_inc`
* No batches past N_max. Reaching N_max without stop → hard stop → clause status `UNMEASURED(underpowered_nmax)`
* `stopping_reason ∈ {passed, failed, underpowered_nmax, budget_exhausted}` recorded on `runs.config_json`
* Variance budgeting: per-clause posterior-width stop rule + global token budget; greedy allocation by `1/posterior_width`

---

## §14.2 Multiplicity / pooling

For K clauses per skill, posterior estimates are pooled via hyperprior `Beta(α_skill, β_skill)`. This shrinks weak signals toward the skill mean and is self-immunizing against family-wise false positives.

**v0.1 fit method:** Empirical-Bayes Method-of-Moments (`scipy.stats`, closed-form, deterministic, no MCMC). Per-clause posterior stays `Beta(1+w, 1+n−w)` (PRD §14 Pass Rule locked); hyperprior `Beta(α̂_skill, β̂_skill)` fit via MoM over per-clause `(w_k, n_k)`.

**Convergence failure:** `α̂ ≤ 0 ∨ β̂ ≤ 0 ∨ var_between < 1e-6` → BH-FDR fallback (Benjamini-Hochberg 1995, q = 0.05) over per-clause `p_exceeds` from unpooled posterior.

**K < 10:** EB hyperprior estimate is noisy (BDA3 §5). Default to UNPOOLED reporting with `aggregation_method = unpooled (K<10)` logged warning; hierarchical fit only triggers at K ≥ 10.

**Determinism:** `PYTHONHASHSEED=0` environment discipline. PyMC MCMC NUTS hyperprior fit deferred to v0.2 (D21).

---

## §14.3 Tie encoding (provisional)

Tie encoding is provisionally **half-update**: each observation with `observation = 0.5` is treated as two updates (half-win + half-loss). Same posterior mean as 0.5 encoding, slightly different variance, Bayesian semantics honest (pseudo-Bernoulli). Tie count is derived by filtering `oracle_verdicts.observation = 0.5` — there is no separate stored `tie_count` column (`0001_initial.sql`). The operator can still switch to drop-ties at report time without re-sampling, by re-deriving that filter over already-persisted `observation` values.

**Open (C1):** flip to drop-ties preserves Beta-Binomial conjugacy exactly. Data-blocked until first `(judge_id, axis)` calibration event lands.

---

## Pass Rule

Clause passes when:

`P(win_rate > threshold) ≥ confidence_requirement`

Default:

* `threshold = 0.60`
* `confidence_requirement = 0.95`

---

# 15. Clause Status Model

A clause may be:

### PASSED

Evidence exceeds threshold.

### FAILED

Evidence falls below threshold.

### CONFOUNDED

Interaction contamination detected.

### UNMEASURED

One of the following sub-reasons applies; reported as `UNMEASURED(<sub_reason>)`:

* `no_data` — no verdicts written for this clause
* `inadmissible` — verdicts written, all inadmissible (tokens were spent; this is NOT silent skipping)
* `underpowered` — verdicts admissible but N below sampling-rule stop conditions, or σ(Null) below floor for confound detection
* `falsifying_case_missing` — clause has no frozen falsifying case (per §3.4 / §7a)
* `falsifying_case_stale` — clause's only frozen cases are at non-current metric_versions (see definition of "current" below)
* `budget_exhausted` — sampling halted because `--max-usd` or `--daily-cap` was hit before stop conditions

---

## §15.1 Current metric_version

"Current" metric_version for a metric is derived (no stored pointer):

```sql
SELECT version, implementation_hash FROM metric_versions
 WHERE metric_id = ?
   AND audited = 1
   AND mechanical_validity_test_passed = 1
 ORDER BY registered_at DESC
 LIMIT 1
```

The `audited + validity_passed` filter is load-bearing, and its two flags are distinct: `mechanical_validity_test_passed` records the outcome of §12.1's mechanical-validity audit gate, while `audited` records the separate operator act defined below. A metric_version missing either flag must NOT be considered current.

**The audited flip (normative).** `audited = 1` on a metric_versions row attests: a deliberate operator act (`audit-metric`) registered this metric implementation, hash-pinned against the shipped module at execution time. It is an operator-attested, hash-pinned registration — NOT a claim of independent construct-validity review. The act requires a non-empty operator-typed attestation string (`--attest "<text>"`), echoed in its dry-run and execute output; it defaults to dry-run and writes only on `--execute`. No act flips audited on an existing row (append-only); a store whose row was minted unaudited requires re-ingest into a store audited first. Attester identity lives in the operator's commit trail, not the DB (`registered_at` already captures when). The schema layer cannot prevent a hand-crafted INSERT from forging `audited = 1` — the semantic is act-enforced only.

**Auto-flip rule:** a clause whose only frozen cases are at non-current metric_versions transitions to `UNMEASURED(falsifying_case_stale)`. Stale cases remain in `frozen_cases` (audit trail) but do NOT count toward the §19 #7 PASSED gate. **No re-freeze command** — the operator re-runs `freeze` with a new verdict collected under the current metric_version (append-only; no stamp-renewal-without-evidence path).

---

# 16. Skill-Level Reporting

Skills are reported as vectors.
Never as a scalar score.

---

## Required Output

* Passed Clauses
* Failed Clauses
* Confounded Clauses
* Unmeasured Clauses
* Coverage
* Full-vs-Null Contribution

---

## §16.1 Wire format

Reports are emitted in two formats via `--format=rich|json` (default `rich` for operator terminal use).

**JSON output** ships with mandatory top-level `report_schema_version` (semver). v0.1 lifetime is `1.x` additive-only: additions = minor bump; removals/renames/type-changes = major bump (breaks `diff skill` consumers).

**Wire-format version by command (independent schemas):**
- `run evaluate-skill` report: `"1.2.0"` — initial `"1.0.0"`, bumped to `"1.1.0"` for A55 comparability axes (`subject_model`, `user_message_sha256`), bumped to `"1.2.0"` for `coverage_warnings` field on `vector` (M3 pre-tag fix).
- `diff skill` report: `"1.0.0"` — independent schema; additive bumps track only diff-report-specific field changes.

**Required top-level keys:**
`report_schema_version, skill_id, generated_at_utc, harness_version, aggregation_method ∈ {ebmom_hierarchical, bh_fdr_fallback, unpooled}, aggregation_provenance, clauses[], vector (Passed/Failed/Confounded/Unmeasured/Coverage/Contribution), coverage, contribution`.

**Per-clause fields:**
`clause_id, status, sub_reason (when UNMEASURED), posterior_mean, credible_interval_95, p_win_gt_threshold, frozen_case_count_at_current_metric_version, metric_id_per_axis, metric_version_per_axis, ablation_operator_hash, run_ids_aggregated`.

**Byte-stable for identical evidence:** JSON output is sorted-keys, no internal timestamps inside the payload (single `generated_at_utc` at top level only).

**Pipeline discipline:** `--format=json` writes ONLY to stdout; warnings (UNMEASURED count, A50 LOO-honesty caveat, incomplete-run warn) go to stderr.

**Rejected for v0.1:** `--format=csv|md` (CSV is lossy on credible intervals + provenance; deferred).

**`aggregation_provenance` required sub-keys (when `aggregation_method = ebmom_hierarchical`):** `alpha_hat, beta_hat, sample_mean, sample_var, K_clauses, pythonhashseed`.

**`aggregation_provenance` required sub-keys (when `aggregation_method = bh_fdr_fallback`):** `fallback_reason ∈ {var_below_threshold, alpha_hat_nonpositive, beta_hat_nonpositive, unknown}`, `attempted = {alpha_hat, beta_hat, sample_mean, sample_var}` (the EB-MoM attempt that failed), `q_value` (BH-FDR q parameter, default 0.05), `pythonhashseed`.

**`aggregation_provenance` required sub-keys (when `aggregation_method = unpooled`):** `K_clauses, k_min_for_eb` (= 10), `pythonhashseed`.

---

## Example

```
Passed: 7
Failed: 1
Confounded: 2
Unmeasured: 3
Coverage: 81%
Skill Contribution: +22%
```

---

# 17. System Architecture

## Deterministic Layer

Python runner.

Responsibilities:

* orchestration
* sampling
* scoring
* storage
* aggregation

---

## Stochastic Layer

Model workers.

Roles:

* subject
* injector
* calibrated judge

Models generate content only.
They never own control flow.

---

## Persistence

SQLite. **Append-only evidence model.** Every evidence table carries `BEFORE UPDATE` and `BEFORE DELETE` triggers raising `RAISE(ABORT, 'append_only_violation: <table>')`. Application-layer contract alone is insufficient — bypassable via any SQLite REPL.

**Two-database partition:**

* `evidence.db` — all append-only domain state (skills, clauses, metric_versions, judges, calibration_events, samples, oracle_verdicts, confound_events, frozen_cases, runs)
* `runtime.db` — all mutable operational state (run_progress, current_calibration, cost_ledger, run_budget, skill_imports_staging, schema_migrations)

Cross-DB FKs enforced at application layer; never via SQL.

**Cost ledger:** `runtime.cost_ledger` records per-call token + USD spend; `runtime.run_budget` records per-run cap. Three-layer cost cap: (a) `run ablation` / `run evaluate-skill` / `calibrate` default to dry-run; `--execute` required; (b) per-run `--max-usd <X>` (default $5); (c) per-day rolling `--daily-cap <X>` (default $20).

**Schema migration discipline:** numbered SQL files in `src/skill_harness/storage/migrations_sql/{evidence,runtime}/` (shipped as package data). Each application records `(migration_id, file_sha256)` in append-only `schema_migrations`. On startup, file-SHA mismatch against recorded SHA aborts with `MigrationTamperedError`.

Per-track migration number ranges:

* Track A — `0001-0099` (storage primitives)
* Track B — `0100-0199` (extractor)
* Track C — `0200-0299` (oracle / calibration)
* Track D — `0300-0399` (ablation runner)
* Track E — `0400-0499` (aggregation / status)

`discover()` raises `BootstrapError` on duplicate version numbers.

**Track E migrations:**

* `0400_freeze_provenance.sql` — extends `frozen_cases` with `verdict_id` FK, `run_id` FK, `axis`, unique-index on `(clause_id, axis, failing_input_sha256)`, and BEFORE INSERT trigger refusing rows whose joined `runs.completed_at IS NULL`
* `0401_stale_frozen_view.sql` — creates `current_metric_versions` VIEW and `frozen_cases_with_currency` VIEW (per §15.1 "current metric_version" derivation)

**Durability asymmetry:** `evidence.db` opens with `PRAGMA synchronous = FULL` (audit-trail invariant). `runtime.db` opens with `PRAGMA synchronous = NORMAL` (in-flight state, tolerant of replay-on-restart).

**Single-writer mechanism (v0.1):** SQLite `BEGIN IMMEDIATE` + 5-second `busy_timeout`. No in-process `queue.Queue` or writer thread. Application discipline: writes from a single thread per DB connection. Subprocess workers deferred to v0.2 (D11).

**Dual-DB write ordering:** writes spanning both DBs use `storage/dual_write.py::write_<op>_with_<companion>`. Sequence: `BEGIN IMMEDIATE` on evidence → INSERT evidence → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT runtime → COMMIT runtime. On runtime COMMIT failure, log structured `dual_write_partial` event; the gap is reconciler-eligible (do NOT auto-insert phantom runtime row). **`ATTACH DATABASE` is forbidden in production code paths** (defeats A22 FULL/NORMAL split); read-only ATTACH allowed in future `skill audit` (D7).

**Cost re-derivable from evidence:** per-call token + USD cost columns written onto evidence rows inside the evidence transaction. `cost_ledger` becomes a projection; reconciler back-fills runs whose sums disagree (cost written from actual response `usage`, never from projection).

**Aggregation surface:** the canonical read-side for aggregation is the SQL VIEW `admissible_verdicts` (migration `0003_admissible_verdicts_view.sql`), which selects from `oracle_verdicts` where `admissibility_state = 'admissible'` AND no matching row in `confound_events` with `delta_kind = 'confound_flagged'` for the same `(run_id, primary_clause_id)`. `aggregate_skill()` (`aggregation/engine.py`) reads observation values ONLY from this VIEW — never from raw `oracle_verdicts` — so inadmissible/confounded data structurally cannot enter computed statistics.

Raw `SELECT … FROM oracle_verdicts` is enforced (pre-commit hook `ban-raw-oracle-verdicts` + CI job `structural-bans`, see `.pre-commit-config.yaml` / `.github/workflows/ci.yml`) against a documented allowlist, not a bare "audit/-only" ban — none of the allowed call sites read `observation` from the raw table to feed aggregation; they are single-row/metadata reads the VIEW is not shaped to answer:

* `audit/` — cross-reference/inspection (`audit_all_verdicts()` etc.), the module's designed purpose (A29).
* `aggregation/engine.py` — admissibility-state counts and confound-membership checks for exclusion-rate reporting (bookkeeping about which rows the VIEW dropped, not the dropped rows' values).
* `ablation/runner.py` — resume-state rebuild: reloading a SPECIFIC already-persisted verdict by `(run_id, clause_id, sample_index)` to avoid re-recording it.
* `cli/main.py` — single-verdict operator commands (freeze eligibility check, verdict lookup by id).
* `storage/repositories/evidence/frozen_cases.py` — single-row provenance copy (`metric_id`/`metric_version`/sample refs) by `verdict_id` at freeze time.

A new production reference outside this list fails the hook; `tests/test_structural_bans.py` mirrors the same allowlist so a violation also surfaces in the ordinary test run.

**Repository surface:** per-table modules under `storage/repositories/evidence/` and `storage/repositories/runtime/`. Functional API only — no classes (closes subclass-override escape hatches; closes per-instance-state hazard). Pydantic write-models with `model_config = ConfigDict(strict=True, extra='forbid', frozen=True)`. Evidence repos export only `insert_*` / `get_*` / `select_*` / `list_*` — no `update_*` / `delete_*` / `set_*` / `patch_*` / `modify_*` / `remove_*`. AST-walker test (`tests/test_evidence_repo_surface.py`) is the falsifying-case enforcement: regex scan rejects matching function names.

---

# 17a. Threat Model (informal)

**Trust partition.** `evidence.db` is append-only, audited, load-bearing. `runtime.db` is mutable by design. Compromise of `runtime.db` (`current_calibration` rewrite is the load-bearing target) affects only FUTURE verdicts because past verdicts have already snapshotted `admissibility_state` at write time (§6) and `oracle_verdicts` is append-only. Symmetry between the two DBs is NOT a design goal.

**Filesystem substitution boundary.** Append-only triggers + SHA-256 migration ledger defend against in-process unauthorized writes (developer error, SQL-injection-style mutation, library bug). They do NOT defend against an attacker who replaces the entire `evidence.db` file at the filesystem layer — the SHA ledger checks file contents against an SHA recorded inside the same DB, so a whole-DB substitution supplies both the data and the baseline. v0.1 assumes filesystem integrity (local-trust). File-replacement detection deferred to v0.2 (D6 `db_identity`).

**PRAGMA scope.** Connections MUST go through `skill_harness.storage.migrations.open_db()`. Direct `sqlite3.connect()` bypasses connection-scoped pragmas including `foreign_keys = ON`.

**Structural enforcement:** pre-commit hook `ban-raw-sqlite-connect` (`.pre-commit-config.yaml`, `language: pygrep`) plus CI job `structural-bans` (`.github/workflows/ci.yml`) scan `src/` and `tests/` for `sqlite3\.connect\(`, excluding `storage/migrations.py` (the module that defines `open_db()` and is the only legitimate caller); `tests/test_structural_bans.py` mirrors the same check so a violation also shows up in the ordinary `pytest -m "not live"` run. Upgrades the documented PRAGMA-scope discipline from PR-review to mechanism.

---

# 18. CLI

*(v1.1 surface — see the Amendment note at the top of this file: v0.2 added
`skill audit` and the `screen` group under its own pre-registered gate.)*

## `skill init`

Import and extract clauses.

---

## `skill clauses`

Inspect clause inventory.

---

## `run ablation`

Execute single-clause ablation.

**Cost discipline (applies to `run ablation`, `calibrate`):**

* default behaviour is **dry-run**. Prints projected calls, tokens (cached / uncached split), USD on the chosen model, and cache reuse %.
* `--execute` required to make API calls.
* `--max-usd <X>` per-run hard ceiling (default $5).
* `--daily-cap <X>` per-day rolling ceiling over the trailing 24h (default $20).
* `--max-usd` and `--daily-cap` errors name the offending flag distinctly.

The dry-run / `--execute` / `--max-usd` / `--daily-cap` doctrine in §18 applies to `calibrate` in addition to `run ablation`. Note: `calibrate` projection uses a distinct formula from ablation (no per-pair cache; only system+schema prefix cacheable). Dry-run output includes `est_SE_pairwise_agreement` and `est_CI_95_width`.

**Resume / progress / inspection (flags only; no new commands — §18 surface is locked):**

* `--resume <run_id>` with resume-preview
* Bare re-run against an incomplete prior run WARNS + names the resumable `run_id` (no silent fresh-start / double-spend)
* `rich.progress` per-clause + live dual-cap footer
* `--show-rendered <clause_id>` prints verbatim Full / Ablated_k / Null + `ablation_operator_version`

---

## `run evaluate-skill`

Aggregate completed ablation runs into a skill report. **Read-side only — no LLM API calls, no `--max-usd`, no `--execute` flag, no `ANTHROPIC_API_KEY` required.**

Discovers all `runs` rows for the given `skill_id` with `run_kind='ablation'` and `completed_at IS NOT NULL`. Preflight: incomplete prior runs → refuse-to-start exit 1. No completed runs → exit 1 with operator-readable message. Aggregation uses the `admissible_verdicts` VIEW.

May optionally mint a `runs.run_kind='evaluate_skill'` envelope as audit-trail metadata (run_ids aggregated + EB-MoM hyperprior parameters + `aggregation_method`) so the report is reproducible — NOT a sampling run.

---

## `diff skill`

`diff skill <skill_id_a> <skill_id_b>` — compare skill revisions (revisions = distinct `skill_id` rows; `clause_id` does NOT persist across revisions).

**Clause comparability key:** `(axis, clause_text_sha256)`. Exact match first; unaligned clauses → `ADDED` / `REMOVED`.

**`metric_drift` guard:** per-clause status delta is `metric_drift` whenever ANY of `(metric_id, metric_version)`, `ablation_operator_hash`, `subject_model`, `user_message_sha256` diverge between A's verdict and B's verdict — the two posteriors are NOT commensurable when the measurement changed.

**Status delta enum:** `regressed | improved | unchanged | new | removed | metric_drift`.

**Exit codes:** default exit `0` if diff ran (semantic success is not the default signal); `--exit-on-divergence` flips exit to `2` when any clause status differs A↔B; exit `1` on hard error.

---

## `freeze`

`freeze <verdict_id>` — promote a freezable verdict into the regression suite.

**v0.1 eligibility** (branches on `verdict.comparison`):

* Ablation path (`full_vs_ablated`, unchanged — A56): `observation ∈ {0.0, 0.5}` (FAILING side).
* Paired path (`full_vs_null` — A′, S86 frozen-case design council): `observation = 1.0` (winning epoch) AND the verdict's metric is registered as binary (`PAIRED_FREEZE_BINARY_METRIC_IDS`); the Null-arm sample (`sample_b`) is stored as the falsifying case. Paired ties (`0.5`) and losses (`0.0`) refuse: without per-arm scores a `0.5` cannot be distinguished from a both-PASS tie, and freezing either would store a passing Null sample as a falsifying case. Under a binary metric, `observation = 1.0` entails the Null sample failed the outcome oracle absolutely; graded metrics refuse explicitly (freeze-time re-verification of absolute Null failure is pre-registered as the follow-on — it requires per-arm scores persisted, v0.2 D22 lane).

Both paths: `admissibility_state = 'admissible'` AND `oracle_source = 'mechanical'` (Tier-1 only; Tier-2 freezing deferred to v0.2 D22).

**Normative (A′):** a paired frozen case is the Null half of the winning evidence re-encoded, **not** independent falsification — on the paired path, any threshold-clearing run deterministically contains freezable evidence, so the §3.4 frozen-case gate does no independent inferential work there; anti-vacuity is discharged upstream by the Stage-0 Null screen (`p0 < 1`) and write-time admissibility, and a paired-path PASSED/KEEP must never be read as independently falsified.

**Idempotent:** duplicate freeze of same `(clause_id, axis, failing_input_sha256)` raises UNIQUE → exit 0 with `"already frozen"` stderr (not silent no-op).

**Dry-run default** (consistent with `skill init`, `run ablation`, `calibrate`).

**Discoverability:** Track D ablation report adds a `verdict_id` column for operator lookup.

---

## `audit-metric`

`audit-metric <metric_id>` — register an audited `metric_versions` row for a subject Tier-1 metric (the §15.1 audited flip; pre-register-before-ingest).

**Semantics:** normative definition in §15.1 "The audited flip". The row written is the exact shape ingest would write except `audited = 1`: `version = ORACLE_METRIC_VERSION`, `implementation_hash` computed live by ingest's own hash function (imported, never duplicated — the pin must keep binding to the oracle module), `tier = 1`, `mechanical_validity_test_passed = 1`.

**Requires** a non-empty `--attest "<text>"` operator attestation (echoed in output, not stored — attester identity lives in the commit trail).

**Refuses (exit 1):** metric not in `PAIRED_FREEZE_BINARY_METRIC_IDS`; an existing unaudited row at the same `(metric_id, version)` (append-only — recovery is audit-metric against a fresh store, then re-ingest); an existing audited row whose hash no longer matches the live module (implementation drift).

**Idempotent:** re-run after success exits 0 with `"already audited"` only when the existing audited row's hash matches the live module.

**Dry-run default** (consistent with `skill init`, `run ablation`, `freeze`, `calibrate`); prints the full would-be row including the live hash. Ingest's side of the contract: when its existence guard finds a pre-registered `(metric_id, version)` row, it recomputes the live hash and refuses fail-closed on mismatch (drift check; remedy = bump `ORACLE_METRIC_VERSION` or run the matching code).

---

## `calibrate`

`calibrate <judge_id> <axis> <pair_set.jsonl>` — register a calibrated `(judge_id, axis)` record from a JSONL pairwise calibration set.

**Dry-run default** (consistent with `skill init`, `run ablation`, `freeze`). `--execute` required to write calibration record.

**Cost discipline:** `--max-usd` and `--daily-cap` apply. Projection uses a distinct formula from ablation (no per-pair cache; only system+schema prefix cacheable). Dry-run output includes `est_SE_pairwise_agreement` and `est_CI_95_width`.

**Minimum calibration set:** 50 pairs per `(judge_id, axis)` (A7). Admission gate: `pairwise_agreement >= 0.7`.

---

## §18.1 Exit codes

**Exit code convention (uniform across `run ablation`, `run evaluate-skill`, `diff skill`, `freeze`):**

* `0` = operation completed; every clause reached a verdict
* `1` = precondition fail (no completed ablation, incomplete prior run, aggregation error, validation refused for freeze, hard error for diff)
* `2` = operation completed but ≥1 UNMEASURED clause (for `evaluate-skill` / `ablation`); `--exit-on-divergence` flag flipped to 2 (for `diff`)
* Sub-reason discrimination lives in `report.sub_reason` field + stderr human-readable message (NOT in distinct exit codes — `UNMEASURED(underpowered)` vs `UNMEASURED(falsifying_case_stale)` both exit 2).

---

# 19. Success Criteria

The system succeeds if it can:

1. Detect clause regressions caused by skill edits.
2. Distinguish failed clauses from unmeasured clauses.
3. Reject uncalibrated judges automatically.
4. Preserve oracle and metric provenance.
5. Surface confounded measurements instead of silently aggregating them.
6. Produce reproducible clause-level evidence across skill versions.
7. Refuse to report any clause as `PASSED` without a non-stale frozen falsifying case at the current metric_version (per §3.4 / §7a and §15.1).

---

# 20. Core Invariant

A clause that cannot be falsified is not a contract.
It is metadata.

The harness exists to measure contracts, not intentions.
