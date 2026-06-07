# Phase 3.5 — PRD v1.1 Amendment Audit + Patch Plan

Pre-stages the doc-lock work. Enumerates every queued amendment, anchors each
to a specific PRD section, drafts verbatim patches where possible.

**Sources read (verbatim):**
- `PRD.md` (706 lines, v1.0)
- `docs/COUNCIL_FINDINGS.md` (638 lines) — main table + Appendices B, C, D, E, F
- `docs/dispatch/phase-3-3-mutation-testing-fix-brief.md` (CF-Phase-3-3-1)
- `CLAUDE.md` load-bearing invariants block (used as cross-check)

**Count reconciliation:**
- Original v1.1 table (2026-06-03 + the 4 SECURITY/RELIABILITY rows backfilled into it): 20
- Pre-Track-A impl council (Appendix C, 2026-06-04): +6 → 26
- Pre-Track-C council (Appendix D, 2026-06-05): +8 → 34
- Pre-Track-D council (Appendix E, 2026-06-06): replaces the D2 §1 edit (no net add) → 34
- Pre-Track-E council (Appendix F, 2026-06-06): +10 → **44 council-queued**
- CF-Phase-3-3-1 (Phase 3.3 fix brief): +1 candidate (NOT council-adopted) → **45 candidates if adopted**

## Total: 45 amendment candidates (44 council-queued + 1 Phase-3.3-surfaced)

> Audit notes overlapping rows: the original 2026-06-03 table queued §17 edits at
> the same time as the Pre-Track-A impl council (Appendix C) added six more §17
> rows. Both sets land in §17, so sequencing matters — handled in §17 below.
> The Pre-Track-D council (Appendix E) explicitly *replaces* the D2 §1 edit
> wording in the original table; that's not an additional row but a re-write of
> an existing row.

---

## Amendments by PRD section (sequenced)

### §1 — Executive Summary

- **[A-§1-1]** · Drop "manufactured primitives"; reframe positioning. · driver: **A39/A50 lineage via EVR-6 (Appendix E)**; supersedes the D2 / EVAL-F1 original
  - Current PRD text excerpt (lines 25-31):
    > "Skill Harness introduces four manufactured primitives that replace those assumptions:
    >
    > 1. Oracle → Directional Pairing
    > 2. Isolation → Clause Ablation
    > 3. Determinism → Variance Budgeting
    > 4. Trust → Admissible Oracles"
  - Proposed (shape, per Appendix E EVR-6 verbatim): replace the "four manufactured primitives" block with a positioning statement that the harness's novel and defensible claim is "the *evidentiary discipline* — falsifiable directional contracts with write-time admissibility-gated, append-only provenance" (the P4 signature, zero hits in the eval domain per landscape §1) — NOT the estimator. LOO is honestly the *conservative* estimator inside that discipline; under-crediting contribution is a safe failure for an adversarial audit (false-negative on contribution, never false-positive on a PASS).
  - Add prior-art citations (D2/EVAL-F1 original intent retained): Sclar et al. arXiv:2310.11324 (FormatSpread / component ablation), Longpre et al. arXiv:2301.13688 (FLAN), Chang et al. arXiv:2405.20404 (JoPA — for the LOO honesty caveat).
  - Sequencing note: Pre-Track-D Appendix E explicitly *replaces* the original D2 row. Apply this single amendment; do NOT also apply the D2 "drop manufactured primitives" row from the original table as a separate edit (it would either no-op or double-edit).

### §3.1 — Directional Evaluation

- **[A-§3.1-1]** · Add pairwise-only reconciliation clause. · driver: **A5 / EVAL-F5**
  - Current PRD text excerpt (lines 70-80):
    > "All evaluation is comparative.
    >
    > Forbidden:
    > * quality scoring
    > * holistic grading
    > * \"is this good?\"
    >
    > Required:
    > * A beats B on axis X"
  - Proposed (verbatim insertion after the "Required" bullet block, per A5):
    > "Reconciliation with §5 Tier 2: the Tier-2 LLM judge is admissible **only** in pairwise-preference mode for one named axis at a time. Judge prompts MUST present both candidates, MUST output one of `{A, B, tie}` for one axis, and MUST NOT emit a numeric score. G-Eval-style scalar templates (Liu et al. arXiv:2303.16634) are explicitly forbidden under §3.1."
  - Sequencing note: apply BEFORE A-§5T2-* edits so the §5 Tier 2 sub-rule reads naturally as a downstream consequence of §3.1.

### §3.4 / new §7a — Falsifying Case Schema

- **[A-§3.4-1 / A-§7a-1]** · Falsifying Case Schema spec. · driver: **A15 / TEST-ARCH-F1**
  - Current PRD text excerpt (lines 107-110, §3.4):
    > "A clause is not considered tested until it has at least one falsifying case.
    >
    > A clause without a possible failure mode is metadata, not a contract."
  - Proposed (insert new sub-section after §3.4, before §3.5, titled "§3.4a Falsifying Case Schema" OR add full §7a per A15's original framing): each clause declares the triple `(input_population_spec, expected_directional_pair, min_reproducibility)`. Until that schema is frozen (SHA-256 stored in `clauses.falsifying_case_schema_sha256`), the clause cannot transition to PASSED — regardless of posterior. Formal gate: `PASSED ⇔ posterior_threshold_met ∧ ≥1 frozen_case_at_current_metric_version`.
  - Sequencing note: A57 strengthens this gate further (see A-§19#7-1 below). Apply this base text first, then A57's "non-stale" qualifier.

### §5 Tier 2 — Human-Calibrated Judge

- **[A-§5T2-1]** · Position-swap mandatory; pairwise-only mode. · driver: **A5 + A6 / EVAL-F5, EVAL-F7, EVAL-F2**
  - Current PRD text excerpt (lines 207-219):
    > "## Tier 2: Human-Calibrated Judge
    >
    > Used only when no reliable mechanical metric exists.
    >
    > Requirements:
    > * human-labeled calibration set
    > * tracked agreement score
    > * admissibility enforcement
    >
    > The judge is an instrument.
    > It is never the source of truth."
  - Proposed (extend the Requirements bullet list, verbatim insertions):
    > "* pairwise mode only — output one of `{A, B, tie}` for one named axis; numeric/scalar grading forbidden
    > * mandatory position swap — every verdict requires both `(A, B)` and `(B, A)` orderings; disagreement on swap → `position_swap_agreement = 0` → `admissibility_state = 'inadmissible'` (reason `position_disagreement`)
    > * length-controlled scoring — AlpacaEval-2 length-regression protocol (Dubois et al. arXiv:2404.04475) applied both at prompt-time (max_tokens=80 with "length should not influence" instruction) and observation-time; `length_regression_coefficient` stored separately from `length_controlled_agreement`; both raw and length-adjusted observations persisted at write time"

- **[A-§5T2-2]** · Judge identity is `sha256(model_id || system_prompt_sha256 || tool_schema_sha256)`. · driver: **A31 / Appendix D Q1**
  - Current PRD text excerpt: §5 Tier 2 currently does not name `judge_id` shape.
  - Proposed (verbatim insertion in §5 Tier 2 Requirements):
    > "* judge identity is bound to `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)`; the tool schema is part of the calibration scope, NOT swappable post-calibration"

- **[A-§5T2-3]** · Adversarial injection defense layers. · driver: **A38 / Appendix D Q8**
  - Current PRD text excerpt: §5 Tier 2 currently does not address rationale untrust.
  - Proposed (verbatim insertion in §5 Tier 2 Requirements):
    > "* judge invoked via tool_use with `strict: true`, `tool_choice` forced, schema `report_verdict({choice: enum[A,B,tie], rationale_brief})`; rationale field is audit-only, displayed in UI with `[untrusted model output]` prefix; defense layers (tool_use schema + 8KB output truncation + XML-delimited sandboxing + meta-token regex short-circuit + position-swap + null-baseline distributional check + rationale UI prefix) all required before a verdict can be written"

  - Sequencing note: A-§5T2-1 → A-§5T2-2 → A-§5T2-3. Treat as one cohesive rewrite of §5 Tier 2 Requirements; otherwise the bullet list becomes a mess of inserted pieces.

### §5 Tier 3 — Real-World Consequence

- **[A-§5T3-1]** · Mark DEFERRED to v0.2. · driver: **D1 / EVAL-F3**
  - Current PRD text excerpt (lines 222-232):
    > "## Tier 3: Real-World Consequence
    >
    > Terminal oracle.
    >
    > Examples:
    > * issue closure rate
    > * contributor time-to-PR
    > * production incident reduction
    >
    > Highest authority when available."
  - Proposed (verbatim insertion after "Highest authority when available."):
    > "**v0.1 status: DEFERRED.** No published precedent attributes a real-world outcome to a single skill clause; whole-tool effects (Peng et al. arXiv:2302.06590; Cui et al. 4000+ devs) do not satisfy clause-level instrumentation. Lag time weeks-to-months; SNR effectively zero without a clause-instrumented RCT. `frozen_cases.oracle_source` CHECK constraint excludes `'real_world'` for v0.1. Re-evaluate post-v0.1 dogfooding."

### §6 — Admissibility System

- **[A-§6-1]** · Admissibility includes position-consistency + length-control gates. · driver: **A6 + A7 / EVAL-F2, EVAL-F7, STAT-F5**
  - Current PRD text excerpt (lines 246-252):
    > "Tier-2 verdicts are inadmissible unless:
    >
    > `(judge_id, axis)`
    >
    > has a calibrated record."
  - Proposed (extend the Rule block):
    > "Tier-2 verdicts are inadmissible unless ALL of the following hold for the `(judge_id, axis)` pair:
    > * a calibrated record exists with `pairwise_agreement ≥ 0.7`
    > * `position_consistency ≥ 0.8`
    > * `length_controlled_agreement` recorded; Cohen's κ stored as secondary chance-corrected reporting
    > * calibration set size `≥ 50` pairs
    > * re-calibration cadence ≤ 90 days OR no model-version bump since"

- **[A-§6-2]** · Calibration JSONL schema + three-tier admissibility states. · driver: **A34 / Appendix D Q4**
  - Current PRD text excerpt: §6/§7 currently do not name the calibration input schema.
  - Proposed (insert new sub-section "§6.1 Calibration input schema"):
    > "Calibration inputs are strict JSONL with eight required fields: `pair_id, axis, prompt, response_a, response_b, human_preference, labeler_id, labeled_at`.
    >
    > State enum (admissibility classes by pair-set size N):
    > * `rejected` (N < 50) — calibration refused; downstream verdicts inadmissible
    > * `conditional` (50 ≤ N < 100) — admissible with size-warning surfaced in reports
    > * `calibrated` (N ≥ 100) — admissible
    >
    > Cohen's κ on the 3-class outcome (A/B/tie) uses observed marginals, NOT 1/3 uniform.
    >
    > v0.1: no starter set ships; user-provided JSONL only. Operator-self-label admissibility is rejected (resolved 2026-06-06 by SME verdict on independence-collapse grounds; see Appendix E C2 resolution)."

- **[A-§6-3]** · Length-control storage details. · driver: **A35 / Appendix D Q5**
  - Current PRD text excerpt: implicit in §6; not spelled out.
  - Proposed (verbatim insertion in §6, after §6.1):
    > "Length-control storage: `oracle_verdicts` persists both `raw_observation` and `length_adjusted_observation`; the regression coefficient is stored at calibration time in `calibration_events.length_regression_coefficient`. Correction is applied at verdict-write time, never at read time."

- **[A-§6-4]** · Adversarial injection defense (cross-ref to §5 Tier 2). · driver: **A38**
  - Sequencing note: this is covered structurally inside §5 Tier 2 by A-§5T2-3. Optionally add a one-line cross-reference in §6: "See §5 Tier 2 for the seven-layer adversarial defense stack required for any Tier-2 verdict to enter the admissibility pipeline." Treat as low-priority cross-link, not a separate amendment.

### §7 — Clause Extraction

- **[A-§7-1]** · Vacuity split mechanical/semantic; extractor calibration deferred to v0.2. · driver: **A16 + D4 / TEST-ARCH-F2**
  - Current PRD text excerpt (lines 300-308):
    > "## Vacuity Detection
    >
    > A clause is vacuous if:
    >
    > * no observable delta can be defined
    > * no falsifying case can be constructed
    > * no measurable axis exists
    >
    > Vacuous clauses are excluded from testing."
  - Proposed (verbatim replacement of the bullet list):
    > "A clause has one of three vacuity states (`clauses.vacuity_flag` enum):
    >
    > * `not_vacuous` — has an observable delta and a constructible falsifying case
    > * `mechanical_vacuous` — claimed axis is not in `metric_library`; deterministic, auto-excluded from testing
    > * `semantic_vacuous_pending_review` — extractor judged the clause has no measurable axis or no constructible falsifying case (LLM judgment); stored as `UNMEASURED` with reason, NOT silently excluded
    >
    > The extractor is itself a Tier-2 judge. v0.1 uses uncalibrated extraction with the `semantic_vacuous_pending_review` sentinel; `(extractor_id, skill_genre)` calibration is deferred to v0.2 (D4)."

### §11 — Interaction Confounds

- **[A-§11-1]** · Watch ALL metric_library axes; threshold = `k·σ(Null)`; `observed_unclaimed_delta`. · driver: **A11 + A47 / TEST-ARCH-F3, EVAL-F6, STAT-2, REL-3**
  - Current PRD text excerpt (lines 397-405):
    > "## Detection
    >
    > During ablation:
    > all clause metrics are monitored.
    >
    > If removal of clause N causes a different clause axis to move beyond threshold:
    > confound event is recorded."
  - Proposed (verbatim replacement):
    > "During ablation, every axis in `metric_library_v1` is monitored — not only clause-claimed axes.
    >
    > Threshold: `delta > k · σ_axis(Null)`, with defaults `k = 2.0` and `N_null ≥ 30` for variance estimation. Below the N_null floor, confound detection is disabled for that axis and affected verdicts are reported as `UNMEASURED(underpowered)`. Uncalibrated Tier-2 axes are excluded from σ(Null) estimation.
    >
    > `confound_events.delta_kind` enum:
    > * `observed_unclaimed_delta` — movement on a non-claimed axis; audit-only, never aggregated
    > * `confound_flagged` — movement on a claimed-but-other-clause axis; verdict outcome becomes `FLAGGED_CONFOUNDED`
    >
    > Storage is threshold-triggered event-row only (no dense per-sample × axis matrix). All-axes deltas are computed in-memory per condition-cell at orchestration time."

### §12 — Mechanical Metric Library

- **[A-§12-1]** · Demote Assertion Density, Unsupported Claim Ratio, Compliance Proxy, Citation Density, raw Hedge Index. · driver: **A14 / COST-F5, EVAL-F4**
  - Current PRD text excerpt (lines 425-465, §12 "Supported" list): the six metrics Assertion Density, Unsupported Claim Ratio, Hedge Index, Compliance Proxy, Verbosity, Structure Score are listed without admissibility qualification.
  - Proposed (split §12 "Supported" into honest two-track structure):
    > "### Demoted from Tier 1 (NOT mechanical without further support)
    > * **Assertion Density** (`factual_claims / sentences`) — requires NLI / claim extraction
    > * **Unsupported Claim Ratio** — requires claim extraction + evidence-attribution
    > * **Compliance Proxy** — requires directive classifier (heuristic, fragile)
    > * **Citation Density** (regex) — false-positives on markdown code blocks
    > * **Hedge Index** — depends on a corpus-bound, context-blind wordlist
    >
    > ### Tier 1 admissible honest heuristics (deterministic, network-blocked)
    > * `assertion_density := declarative_sentences / total_sentences` (regex on punctuation + leading-verb)
    > * `unsupported_claim_ratio := sentences_lacking_inline_citation_marker / declarative_sentences` (regex for `[N]`, `[Author Year]`, URL, `(source: …)`)
    > * `verbosity := tokens / instruction_units`
    > * `structure_score` — derived from `header_ratio`, `bullet_ratio`, `section_balance`"

- **[A-§12-2]** · Tier-1 mechanical validity audit primitive. · driver: **A14 + A33 / COST-F5, Appendix D Q3**
  - Proposed (verbatim insertion at end of §12, new sub-section "§12.1 Mechanical validity audit gate"):
    > "Every Tier-1 metric must pass an offline-only, network-blocked, deterministic-output test before its `tier = 1` row inserts into `metric_versions`. Implementation primitive: `pytest-socket` + bit-equality assertion + `PYTHONHASHSEED=0` discipline; test modules carry `pytestmark = pytest.mark.disable_socket`. `metric_versions.mechanical_validity_test_passed = 1` flips only on tests-pass AND zero socket attempts. Failures auto-downgrade the metric to Tier 2."

  - Sequencing note: §12 currently has the "Unsupported / Rhythm metrics" block (lines 467-474). Preserve that block verbatim — it's the load-bearing "no frozen cases may be minted from sentence-length variance" guard. Apply A-§12-1 then A-§12-2 as additions; do not collapse with the unaudited block.

### §13 — Calibration System

- **[A-§13-1]** · Name metric + thresholds + N≥50 floor. · driver: **A7 / STAT-F5, EVAL-F2**
  - Current PRD text excerpt (lines 478-503): §13 has skeleton (`(judge_id, axis)` unit, "human-labeled frozen pair set", "agreement score / calibration state / validation timestamp", "axis-specific, no cross-axis inheritance") but does not name the metric or thresholds.
  - Proposed (verbatim replacement of §13 "Outputs"):
    > "**Calibration metric (primary, for pairwise mode):** position-swap-symmetric pairwise-preference agreement vs human labels.
    >
    > **Thresholds:**
    > * pairwise-preference agreement `≥ 0.7`
    > * position-consistency `≥ 0.8`
    > * Cohen's κ stored as secondary chance-corrected reporting (no fixed threshold; observed-marginal calculation)
    > * minimum calibration set size = 50 pairs per `(judge_id, axis)`
    >
    > **Re-calibration cadence:** every 90 days OR at the next model version bump (whichever first).
    >
    > Calibration is axis-specific. No cross-axis inheritance allowed (load-bearing invariant — see CLAUDE.md Oracle tiering)."

### §14 — Aggregation Model

- **[A-§14-1]** · N_min floor + sequential stopping + N_max-hard-stop semantics. · driver: **A8 + A44 / STAT-F1, STAT-F3, COST-F4**
  - Current PRD text excerpt (lines 545-554):
    > "Clause passes when:
    >
    > `P(win_rate > threshold) ≥ confidence_requirement`
    >
    > Default:
    >
    > * `threshold = 0.60`
    > * `confidence_requirement = 0.95`"
  - Proposed (verbatim insertion as new sub-section "§14.1 Sampling rule", BEFORE the Pass Rule block):
    > "**Sampling rule (default):**
    > * `N_min = 8` per condition pair (above STAT-F3's analytic floor of 5)
    > * `N_inc = 4` (batch size between stop checks)
    > * `N_max = 40`
    > * Stop when `P(rate > 0.60) ≥ 0.95` (PASS) OR `P(rate > 0.60) ≤ 0.05` (FAIL); else add `N_inc`
    > * No batches past N_max. Reaching N_max without stop → hard stop → clause status `UNMEASURED(underpowered_nmax)`
    > * `stopping_reason ∈ {passed, failed, underpowered_nmax, budget_exhausted}` recorded on `runs.config_json`
    > * Variance budgeting: per-clause posterior-width stop rule + global token budget; greedy allocation by `1/posterior_width`"

- **[A-§14-2]** · Hierarchical Beta-Binomial with EB-MoM v0.1 fit method. · driver: **A9 + A53 / STAT-F2, Appendix F STAT-Q1**
  - Proposed (verbatim insertion as new sub-section "§14.2 Multiplicity / pooling"):
    > "For K clauses per skill, posterior estimates are pooled via hyperprior `Beta(α_skill, β_skill)`. This shrinks weak signals toward the skill mean and is self-immunizing against family-wise false positives.
    >
    > **v0.1 fit method:** Empirical-Bayes Method-of-Moments (`scipy.stats`, closed-form, deterministic, no MCMC). Per-clause posterior stays `Beta(1+w, 1+n−w)` (PRD §14 Pass Rule locked); hyperprior `Beta(α̂_skill, β̂_skill)` fit via MoM over per-clause `(w_k, n_k)`.
    >
    > **Convergence failure:** `α̂ ≤ 0 ∨ β̂ ≤ 0 ∨ var_between < 1e-6` → BH-FDR fallback (Benjamini-Hochberg 1995, q = 0.05) over per-clause `p_exceeds` from unpooled posterior.
    >
    > **K < 10:** EB hyperprior estimate is noisy (BDA3 §5). Default to UNPOOLED reporting with `aggregation_method = unpooled (K<10)` logged warning; hierarchical fit only triggers at K ≥ 10.
    >
    > **Determinism:** `PYTHONHASHSEED=0` environment discipline. PyMC MCMC NUTS hyperprior fit deferred to v0.2 (D21)."

- **[A-§14-3]** · Tie-encoding note (provisional, open value decision C1). · driver: **A10 / STAT-F4**
  - Proposed (verbatim insertion at end of §14, sub-section "§14.3 Tie encoding (provisional)"):
    > "Tie encoding is provisionally **half-update**: each observation with `observation = 0.5` is treated as two updates (half-win + half-loss). Same posterior mean as 0.5 encoding, slightly different variance, Bayesian semantics honest (pseudo-Bernoulli). Tie count stored separately so the operator can switch to drop-ties at report time without re-sampling.
    >
    > **Open (C1):** flip to drop-ties preserves Beta-Binomial conjugacy exactly. Data-blocked until first `(judge_id, axis)` calibration event lands."

  - Sequencing note: §14 currently has only the Pass Rule. Insert 14.1 (sampling), 14.2 (pooling/fit), 14.3 (ties) in that order, all BEFORE the existing Pass Rule block. Do NOT move or rewrite the Pass Rule block (it's a load-bearing values-decision; changing `0.60`/`0.95` requires an explicit `[values decision]` per CLAUDE.md).

### §15 — Clause Status Model

- **[A-§15-1]** · UNMEASURED sub-reasons enum. · driver: **A17 + A57 / TEST-ARCH-F4, STAT-F6, Appendix F TEST-ARCH-Q5**
  - Current PRD text excerpt (lines 574-577):
    > "### UNMEASURED
    >
    > No admissible evidence exists."
  - Proposed (verbatim replacement):
    > "### UNMEASURED
    >
    > One of the following sub-reasons applies; reported as `UNMEASURED(<sub_reason>)`:
    > * `no_data` — no verdicts written for this clause
    > * `inadmissible` — verdicts written, all inadmissible (tokens were spent; this is NOT silent skipping)
    > * `underpowered` — verdicts admissible but N below sampling-rule stop conditions, or σ(Null) below floor for confound detection
    > * `falsifying_case_missing` — clause has no frozen falsifying case (per §3.4 / §7a)
    > * `falsifying_case_stale` — clause's only frozen cases are at non-current metric_versions (see definition of \"current\" below)
    > * `budget_exhausted` — sampling halted because `--max-usd` or `--daily-cap` was hit before stop conditions"

- **[A-§15-2]** · "Current metric_version" derivation rule. · driver: **A57 / Appendix F TEST-ARCH-Q5**
  - Proposed (verbatim insertion in §15, new sub-section "§15.1 Current metric_version"):
    > "\"Current\" metric_version for a metric is derived (no stored pointer):
    > ```sql
    > SELECT version, implementation_hash FROM metric_versions
    >  WHERE metric_id = ?
    >    AND audited = 1
    >    AND mechanical_validity_test_passed = 1
    >  ORDER BY registered_at DESC
    >  LIMIT 1
    > ```
    >
    > The `audited + validity_passed` filter is load-bearing: a metric_version that failed §12.1's mechanical-validity audit must NOT be considered current.
    >
    > **Auto-flip rule:** a clause whose only frozen cases are at non-current metric_versions transitions to `UNMEASURED(falsifying_case_stale)`. Stale cases remain in `frozen_cases` (audit trail) but do NOT count toward the §19 #7 PASSED gate. **No re-freeze command** — the operator re-runs `freeze` with a new verdict collected under the current metric_version (append-only; no stamp-renewal-without-evidence path)."

  - Sequencing note: apply A-§15-1 before A-§15-2 so the `falsifying_case_stale` sub-reason exists before §15.1 references it.

### §16 — Skill-Level Reporting

- **[A-§16-1]** · Report wire format with `report_schema_version "1.0.0"`. · driver: **A60 / Appendix F OPERATOR-DX-Q8**
  - Current PRD text excerpt (lines 580-595):
    > "Skills are reported as vectors.
    > Never as a scalar score.
    >
    > ## Required Output
    >
    > * Passed Clauses
    > * Failed Clauses
    > * Confounded Clauses
    > * Unmeasured Clauses
    > * Coverage
    > * Full-vs-Null Contribution"
  - Proposed (verbatim insertion after the Required Output block, new sub-section "§16.1 Wire format"):
    > "Reports are emitted in two formats via `--format=rich|json` (default `rich` for operator terminal use).
    >
    > **JSON output** ships with mandatory top-level `report_schema_version \"1.0.0\"` (semver). v0.1 lifetime is `1.x` additive-only: additions = minor bump; removals/renames/type-changes = major bump (breaks `diff skill` consumers).
    >
    > **Required top-level keys:**
    > `report_schema_version, skill_id, generated_at_utc, harness_version, aggregation_method ∈ {ebmom_hierarchical, bh_fdr_fallback, unpooled}, aggregation_provenance, clauses[], vector (Passed/Failed/Confounded/Unmeasured/Coverage/Contribution), coverage, contribution`.
    >
    > **Per-clause fields:**
    > `clause_id, status, sub_reason (when UNMEASURED), posterior_mean, credible_interval_95, p_win_gt_threshold, frozen_case_count_at_current_metric_version, metric_id_per_axis, metric_version_per_axis, ablation_operator_hash, run_ids_aggregated`.
    >
    > **Byte-stable for identical evidence:** JSON output is sorted-keys, no internal timestamps inside the payload (single `generated_at_utc` at top level only).
    >
    > **Pipeline discipline:** `--format=json` writes ONLY to stdout; warnings (UNMEASURED count, A50 LOO-honesty caveat, incomplete-run warn) go to stderr.
    >
    > **Rejected for v0.1:** `--format=csv|md` (CSV is lossy on credible intervals + provenance; deferred)."

### §17 — System Architecture

§17 absorbs the heaviest amendment load — 11 distinct rows across the original table, Pre-Track-A impl council (Appendix C), Pre-Track-C council (Appendix D), and Pre-Track-E council (Appendix F). The original §17 text (lines 611-647) has three sub-sections: Deterministic Layer, Stochastic Layer, Persistence. All amendments add to or alongside Persistence. Recommended structure: keep the three existing sub-sections, then add a new "§17.1 Storage discipline" and "§17a Threat model" block.

- **[A-§17-1]** · Append-only via triggers + two-DB partition + cost ledger. · driver: **A1 + A2 + A12 / SCHEMA-F1, SCHEMA-F2, COST-F3, F-6**
  - Current PRD text excerpt (lines 642-646):
    > "## Persistence
    >
    > SQLite.
    > Append-only evidence model."
  - Proposed (extend Persistence sub-section, verbatim):
    > "**Append-only evidence model.** Every evidence table carries `BEFORE UPDATE` and `BEFORE DELETE` triggers raising `RAISE(ABORT, 'append_only_violation: <table>')`. Application-layer contract alone is insufficient — bypassable via any SQLite REPL.
    >
    > **Two-database partition:**
    > * `evidence.db` — all append-only domain state (skills, clauses, metric_versions, judges, calibration_events, samples, oracle_verdicts, confound_events, frozen_cases, runs)
    > * `runtime.db` — all mutable operational state (run_progress, current_calibration, cost_ledger, run_budget, skill_imports_staging, schema_migrations)
    >
    > Cross-DB FKs enforced at application layer; never via SQL.
    >
    > **Cost ledger:** `runtime.cost_ledger` records per-call token + USD spend; `runtime.run_budget` records per-run cap. Three-layer cost cap: (a) `run ablation` / `run evaluate-skill` / `calibrate` default to dry-run; `--execute` required; (b) per-run `--max-usd <X>` (default $5); (c) per-day rolling `--daily-cap <X>` (default $20)."

- **[A-§17-2]** · Schema migration runner with SHA-256 ledger. · driver: **A4 / SCHEMA-F5**
  - Proposed (verbatim insertion in §17 Persistence, after A-§17-1):
    > "**Schema migration discipline:** numbered SQL files in `migrations/{evidence,runtime}/`. Each application records `(migration_id, file_sha256)` in append-only `schema_migrations`. On startup, file-SHA mismatch against recorded SHA aborts with `MigrationTamperedError`."

- **[A-§17-3]** · Trust partition + filesystem-substitution boundary. · driver: **A23 / SECURITY-F5**
  - Proposed (verbatim insertion as new sub-section "§17a Threat model (informal)"):
    > "**Trust partition.** `evidence.db` is append-only, audited, load-bearing. `runtime.db` is mutable by design. Compromise of `runtime.db` (`current_calibration` rewrite is the load-bearing target) affects only FUTURE verdicts because past verdicts have already snapshotted `admissibility_state` at write time (§6) and `oracle_verdicts` is append-only. Symmetry between the two DBs is NOT a design goal.
    >
    > **Filesystem substitution boundary.** Append-only triggers + SHA-256 migration ledger defend against in-process unauthorized writes (developer error, SQL-injection-style mutation, library bug). They do NOT defend against an attacker who replaces the entire `evidence.db` file at the filesystem layer — the SHA ledger checks file contents against an SHA recorded inside the same DB, so a whole-DB substitution supplies both the data and the baseline. v0.1 assumes filesystem integrity (local-trust). File-replacement detection deferred to v0.2 (D6 `db_identity`).
    >
    > **PRAGMA scope.** Connections MUST go through `skill_harness.storage.migrations.open_db()`. Direct `sqlite3.connect()` bypasses connection-scoped pragmas including `foreign_keys = ON`."

- **[A-§17-4]** · `PRAGMA synchronous = FULL` for evidence; `NORMAL` for runtime. · driver: **A22 / RELIABILITY-F5**
  - Proposed (verbatim insertion in §17 Persistence, after A-§17-1):
    > "**Durability asymmetry:** `evidence.db` opens with `PRAGMA synchronous = FULL` (audit-trail invariant). `runtime.db` opens with `PRAGMA synchronous = NORMAL` (in-flight state, tolerant of replay-on-restart)."

- **[A-§17-5]** · Per-track migration number ranges. · driver: **A30 / Appendix C Q7**
  - Proposed (verbatim insertion in §17 Persistence migration discipline):
    > "Per-track migration number ranges:
    > * Track A — `0001-0099` (storage primitives)
    > * Track B — `0100-0199` (extractor)
    > * Track C — `0200-0299` (oracle / calibration)
    > * Track D — `0300-0399` (ablation runner)
    > * Track E — `0400-0499` (aggregation / status)
    >
    > `discover()` raises `BootstrapError` on duplicate version numbers."

- **[A-§17-6]** · `admissible_verdicts` SQL VIEW as canonical aggregation surface. · driver: **A29 / Appendix C Q6**
  - Proposed (verbatim insertion in §17 Persistence):
    > "**Aggregation surface:** the canonical read-side for aggregation is the SQL VIEW `admissible_verdicts` (migration `0003_admissible_verdicts_view.sql`), which selects from `oracle_verdicts` where `admissibility_state = 'admissible'` AND no matching row in `confound_events` with `delta_kind = 'confound_flagged'` for the same `(run_id, primary_clause_id)`. Raw `oracle_verdicts` access is restricted to the `audit/` module (CI grep ban on non-audit `SELECT … FROM oracle_verdicts`)."

- **[A-§17-7]** · `BEGIN IMMEDIATE` + 5s `busy_timeout` as v0.1 writer-exclusion. · driver: **A26 / Appendix C Q3**
  - Proposed (verbatim insertion in §17 Persistence):
    > "**Single-writer mechanism (v0.1):** SQLite `BEGIN IMMEDIATE` + 5-second `busy_timeout`. No in-process `queue.Queue` or writer thread. Application discipline: writes from a single thread per DB connection. Subprocess workers deferred to v0.2 (D11)."

- **[A-§17-8]** · Dual-DB write ordering — evidence-first. · driver: **A25 + A41 / Appendix C Q2, Appendix E REL-6 / COST-3**
  - Proposed (verbatim insertion in §17 Persistence):
    > "**Dual-DB write ordering:** writes spanning both DBs use `storage/dual_write.py::write_<op>_with_<companion>`. Sequence: `BEGIN IMMEDIATE` on evidence → INSERT evidence → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT runtime → COMMIT runtime. On runtime COMMIT failure, log structured `dual_write_partial` event; the gap is reconciler-eligible (do NOT auto-insert phantom runtime row). **`ATTACH DATABASE` is forbidden in production code paths** (defeats A22 FULL/NORMAL split); read-only ATTACH allowed in future `skill audit` (D7).
    >
    > **Cost re-derivable from evidence:** per-call token + USD cost columns written onto evidence rows inside the evidence transaction. `cost_ledger` becomes a projection; reconciler back-fills runs whose sums disagree (cost written from actual response `usage`, never from projection)."

- **[A-§17-9]** · PRAGMA scope enforcement as STRUCTURAL (pre-commit grep ban). · driver: **A28 / Appendix C Q5**
  - Proposed (verbatim insertion in §17a Threat model PRAGMA scope clause OR §17 Persistence):
    > "**Structural enforcement:** pre-commit + CI grep ban — `ripgrep -n 'sqlite3\\.connect\\(' src/ tests/ | grep -v 'storage/migrations.py'` MUST return empty. Upgrades the documented PRAGMA-scope discipline from PR-review to mechanism."

- **[A-§17-10]** · Repository surface restriction (defense-in-depth over A1 triggers). · driver: **A24 / Appendix C Q1**
  - Proposed (verbatim insertion in §17 Persistence):
    > "**Repository surface:** per-table modules under `storage/repositories/evidence/` and `storage/repositories/runtime/`. Functional API only — no classes (closes subclass-override escape hatches; closes per-instance-state hazard). Pydantic write-models with `model_config = ConfigDict(strict=True, extra='forbid', frozen=True)`. Evidence repos export only `insert_*` / `get_*` / `select_*` / `list_*` — no `update_*` / `delete_*` / `set_*` / `patch_*` / `modify_*` / `remove_*`. AST-walker test (`tests/test_evidence_repo_surface.py`) is the falsifying-case enforcement: regex scan rejects matching function names."

- **[A-§17-11]** · New migrations `0400_freeze_provenance` + `0401_stale_frozen_view`. · driver: **A56 + A57 / Appendix F SCHEMA-Q4, TEST-ARCH-Q5**
  - Proposed (verbatim insertion in §17 Persistence migration discipline):
    > "**Track E migrations:**
    > * `0400_freeze_provenance.sql` — extends `frozen_cases` with `verdict_id` FK, `run_id` FK, `axis`, unique-index on `(clause_id, axis, failing_input_sha256)`, and BEFORE INSERT trigger refusing rows whose joined `runs.completed_at IS NULL`
    > * `0401_stale_frozen_view.sql` — creates `current_metric_versions` VIEW and `frozen_cases_with_currency` VIEW (per §15.1 \"current metric_version\" derivation)"

  - Sequencing note for §17 as a whole:
    1. Apply A-§17-1 (triggers + two-DB + cost ledger) FIRST — it sets up the structural skeleton subsequent edits modify.
    2. Apply A-§17-2 (migration runner SHA), A-§17-5 (per-track ranges), A-§17-11 (Track E migrations) as the migration-discipline block.
    3. Apply A-§17-4 (synchronous asymmetry) and A-§17-7 (BEGIN IMMEDIATE + busy_timeout) as the connection-discipline block.
    4. Apply A-§17-8 (dual-DB ordering + cost re-derivability) and A-§17-6 (admissible_verdicts VIEW) as the write-side / read-side block.
    5. Apply A-§17-10 (repository surface) as defense-in-depth block.
    6. Apply A-§17-3 (trust partition / threat model) as the new §17a block at the end of §17.
    7. Apply A-§17-9 (PRAGMA grep ban) inside §17a PRAGMA scope clause.

### §18 — CLI

- **[A-§18-1]** · `run` defaults dry-run; `--execute`, `--max-usd`, `--daily-cap`. · driver: **A12 / COST-F3**
  - Current PRD text excerpt (lines 663-672):
    > "## `run ablation`
    >
    > Execute single-clause ablation.
    >
    > ## `run evaluate-skill`
    >
    > Run full suite."
  - Proposed (verbatim extension of both `run ablation` and `run evaluate-skill` AND `calibrate`):
    > "**Cost discipline (applies to `run ablation`, `calibrate`):**
    > * default behaviour is **dry-run**. Prints projected calls, tokens (cached / uncached split), USD on the chosen model, and cache reuse %.
    > * `--execute` required to make API calls.
    > * `--max-usd <X>` per-run hard ceiling (default $5).
    > * `--daily-cap <X>` per-day rolling ceiling over the trailing 24h (default $20).
    > * `--max-usd` and `--daily-cap` errors name the offending flag distinctly."

- **[A-§18-2]** · `calibrate` is part of the dry-run-default doctrine. · driver: **A36 / Appendix D Q6**
  - Proposed (already covered by A-§18-1 wording; this is an explicit naming addition):
    > "The dry-run / `--execute` / `--max-usd` / `--daily-cap` doctrine in §18 applies to `calibrate` in addition to `run ablation`. Note: `calibrate` projection uses a distinct formula from ablation (no per-pair cache; only system+schema prefix cacheable). Dry-run output includes `est_SE_pairwise_agreement` and `est_CI_95_width`."

- **[A-§18-3]** · `evaluate-skill` is a pure read-side aggregator. · driver: **A54 / Appendix F TEST-ARCH-Q2**
  - Current PRD text excerpt (lines 669-672):
    > "## `run evaluate-skill`
    >
    > Run full suite."
  - Proposed (verbatim replacement of the `run evaluate-skill` description):
    > "Aggregate completed ablation runs into a skill report. **Read-side only — no LLM API calls, no `--max-usd`, no `--execute` flag, no `ANTHROPIC_API_KEY` required.**
    >
    > Discovers all `runs` rows for the given `skill_id` with `run_kind='ablation'` and `completed_at IS NOT NULL`. Preflight: incomplete prior runs → refuse-to-start exit 1. No completed runs → exit 1 with operator-readable message. Aggregation uses the `admissible_verdicts` VIEW.
    >
    > May optionally mint a `runs.run_kind='evaluate_skill'` envelope as audit-trail metadata (run_ids aggregated + EB-MoM hyperprior parameters + `aggregation_method`) so the report is reproducible — NOT a sampling run."

- **[A-§18-4]** · `freeze <verdict_id>` (rename from `<sample_id>`); dry-run default; Tier-1 mechanical only. · driver: **A56 / Appendix F SCHEMA-Q4**
  - Current PRD text excerpt (lines 681-683):
    > "## `freeze`
    >
    > Promote failure into regression suite."
  - Proposed (verbatim replacement):
    > "`freeze <verdict_id>` — promote a failing verdict into the regression suite.
    >
    > **v0.1 eligibility:** `observation ∈ {0.0, 0.5}` (FAILING side) AND `admissibility_state = 'admissible'` AND `oracle_source = 'mechanical'` (Tier-1 only; Tier-2 freezing deferred to v0.2 D22).
    >
    > **Idempotent:** duplicate freeze of same `(clause_id, axis, failing_input_sha256)` raises UNIQUE → exit 0 with `\"already frozen\"` stderr (not silent no-op).
    >
    > **Dry-run default** (consistent with `skill init`, `run ablation`, `calibrate`).
    >
    > **Discoverability:** Track D ablation report adds a `verdict_id` column for operator lookup."

- **[A-§18-5]** · `diff skill` exit-code conventions + `--exit-on-divergence`. · driver: **A55 + A58 / Appendix F TEST-ARCH-Q3, OPERATOR-DX-Q6**
  - Current PRD text excerpt (lines 675-677):
    > "## `diff skill`
    >
    > Compare skill revisions."
  - Proposed (verbatim replacement):
    > "`diff skill <skill_id_a> <skill_id_b>` — compare skill revisions (revisions = distinct `skill_id` rows; `clause_id` does NOT persist across revisions).
    >
    > **Clause comparability key:** `(axis, clause_text_sha256)`. Exact match first; unaligned clauses → `ADDED` / `REMOVED`.
    >
    > **`metric_drift` guard:** per-clause status delta is `metric_drift` whenever ANY of `(metric_id, metric_version)`, `ablation_operator_hash`, `subject_model`, `user_message_sha256` diverge between A's verdict and B's verdict — the two posteriors are NOT commensurable when the measurement changed.
    >
    > **Status delta enum:** `regressed | improved | unchanged | new | removed | metric_drift`.
    >
    > **Exit codes:** default exit `0` if diff ran (semantic success is not the default signal); `--exit-on-divergence` flips exit to `2` when any clause status differs A↔B; exit `1` on hard error."

- **[A-§18-6]** · `evaluate-skill` exit codes (uniform with `run ablation`). · driver: **A48 + A58 / Appendix F STAT-1, OPERATOR-DX-Q6**
  - Proposed (verbatim insertion inside `run evaluate-skill` description, OR as a §18 sub-section "§18.1 Exit codes"):
    > "**Exit code convention (uniform across `run ablation`, `run evaluate-skill`, `diff skill`, `freeze`):**
    > * `0` = operation completed; every clause reached a verdict
    > * `1` = precondition fail (no completed ablation, incomplete prior run, aggregation error, validation refused for freeze, hard error for diff)
    > * `2` = operation completed but ≥1 UNMEASURED clause (for `evaluate-skill` / `ablation`); `--exit-on-divergence` flag flipped to 2 (for `diff`)
    > * Sub-reason discrimination lives in `report.sub_reason` field + stderr human-readable message (NOT in distinct exit codes — `UNMEASURED(underpowered)` vs `UNMEASURED(falsifying_case_stale)` both exit 2)."

- **[A-§18-7]** · Resume + progress + inspection UX on `run ablation`. · driver: **A52 / Appendix E OPERATOR-DX-Q2/Q3/Q5**
  - Proposed (verbatim insertion in `run ablation` description):
    > "**Resume / progress / inspection (flags only; no new commands — §18 surface is locked):**
    > * `--resume <run_id>` with resume-preview
    > * Bare re-run against an incomplete prior run WARNS + names the resumable `run_id` (no silent fresh-start / double-spend)
    > * `rich.progress` per-clause + live dual-cap footer
    > * `--show-rendered <clause_id>` prints verbatim Full / Ablated_k / Null + `ablation_operator_version`"

  - Sequencing note for §18: A-§18-1 → A-§18-2 → A-§18-3 → A-§18-4 → A-§18-5 → A-§18-6 → A-§18-7. The CLI section currently has six top-level `##` headings (`skill init`, `skill clauses`, `run ablation`, `run evaluate-skill`, `diff skill`, `freeze`). All edits preserve those six headings; no new commands added. Several edits replace heading-section bodies, so apply in source order to avoid cross-interference.

### §19 — Success Criteria

- **[A-§19#7-1]** · Add criterion #7: PASSED requires non-stale frozen falsifying case at current metric_version. · driver: **A15 + A57 / TEST-ARCH-F5, Appendix F TEST-ARCH-Q5**
  - Current PRD text excerpt (lines 687-696):
    > "The system succeeds if it can:
    >
    > 1. Detect clause regressions caused by skill edits.
    > 2. Distinguish failed clauses from unmeasured clauses.
    > 3. Reject uncalibrated judges automatically.
    > 4. Preserve oracle and metric provenance.
    > 5. Surface confounded measurements instead of silently aggregating them.
    > 6. Produce reproducible clause-level evidence across skill versions."
  - Proposed (verbatim insertion as criterion #7):
    > "7. Refuse to report any clause as `PASSED` without a non-stale frozen falsifying case at the current metric_version (per §3.4 / §7a and §15.1)."

---

## CF-Phase-3-3-1 — proposed amendment #45

- **[A-§16-CF1]** · Enumerate `aggregation_provenance` sub-keys. · driver: **CF-Phase-3-3-1 (mutation testing M10 + M11)**
  - Current state: A60 (in Appendix F) lists `aggregation_provenance` as a required top-level key in §16 wire-format spec but does not enumerate its required sub-keys. The Phase 3.3 mutation sweep proved that two sub-keys (`fallback_reason`, `attempted`) are load-bearing (M10 + M11 surfaced both as untested mutations against the BH-FDR fallback path).
  - Proposed (verbatim insertion in §16.1 wire-format spec):
    > "**`aggregation_provenance` required sub-keys (when `aggregation_method = ebmom_hierarchical`):** `alpha_hat, beta_hat, sample_mean, sample_var, K_clauses, pythonhashseed`.
    >
    > **`aggregation_provenance` required sub-keys (when `aggregation_method = bh_fdr_fallback`):** `fallback_reason ∈ {var_below_threshold, alpha_hat_nonpositive, beta_hat_nonpositive, unknown}`, `attempted = {alpha_hat, beta_hat, sample_mean, sample_var}` (the EB-MoM attempt that failed), `q_value` (BH-FDR q parameter, default 0.05), `pythonhashseed`.
    >
    > **`aggregation_provenance` required sub-keys (when `aggregation_method = unpooled`):** `K_clauses, k_min_for_eb` (= 10), `pythonhashseed`."

  - Sequencing note: this lands as an inline extension of A-§16-1. Apply A-§16-1 first, then A-§16-CF1 as a sub-section of the same wire-format block.

---

## Invariant cross-check

Cross-checked against the seven invariant clauses in `CLAUDE.md` (Control-flow ownership, Evidence model, Aggregation rules, Clause discipline, Confound handling, Oracle tiering, Evaluation shape, Metric provenance, Explicitly unaudited).

| Amendment | Touches invariant | Direction |
|---|---|---|
| A-§1-1 | Evaluation shape (positioning) | strengthen (reframes claim as evidentiary discipline, not estimator) |
| A-§3.1-1 | Evaluation shape | strengthen (forbids scalar grading by name, cites G-Eval) |
| A-§3.4-1 | Clause discipline | strengthen (Falsifying Case Schema makes "≥1 frozen case" mechanical) |
| A-§5T2-1 | Oracle tiering + Evaluation shape | strengthen (codifies pairwise-only; position-swap; length control) |
| A-§5T2-2 | Oracle tiering | strengthen (judge_id binding includes tool-schema hash; calibration scope tighter) |
| A-§5T2-3 | Oracle tiering | strengthen (rationale UI prefix prevents judge-to-aggregation injection path) |
| A-§5T3-1 | Oracle tiering | neutral (Tier 3 marked deferred; v0.1 scope reduction, not invariant change) |
| A-§6-1 | Oracle tiering + Aggregation rules | strengthen (admissibility gates pairwise + position + length + N≥50) |
| A-§6-2 | Oracle tiering | strengthen (calibration input schema named; operator-self-label REFUSED) |
| A-§6-3 | Oracle tiering | strengthen (raw + length-adjusted obs persisted at write time, not read) |
| A-§7-1 | Clause discipline | strengthen (vacuity 3-state split prevents silent semantic-vacuous exclusion) |
| A-§11-1 | Confound handling | strengthen (all-axes monitoring + `observed_unclaimed_delta` + σ(Null) floor) |
| A-§12-1 | Oracle tiering + Metric provenance | strengthen (honest heuristics; original metric names demoted) |
| A-§12-2 | Metric provenance + Oracle tiering | strengthen (mechanical-validity audit gate; auto-downgrade on failure) |
| A-§13-1 | Oracle tiering | strengthen (thresholds named; cadence + N≥50 codified) |
| A-§14-1 | Aggregation rules | strengthen (N_max-hard-stop → `UNMEASURED(underpowered_nmax)`, no infinite sampling) |
| A-§14-2 | Aggregation rules | strengthen (EB-MoM with explicit convergence guard + BH-FDR fallback + K<10 unpooled) |
| A-§14-3 | Aggregation rules | neutral (provisional; C1 still open) |
| A-§15-1 | Aggregation rules | strengthen (UNMEASURED sub-reasons surface "tokens spent ≠ no run") |
| A-§15-2 | Metric provenance + Clause discipline | strengthen (current-metric-version derived from audited + validity_passed) |
| A-§16-1 | Evaluation shape | strengthen (vector reporting wire-formatted; schema version semver-locked) |
| A-§17-1 | Evidence model | strengthen (triggers explicit; two-DB partition codified) |
| A-§17-2 | Evidence model | strengthen (SHA-256 ledger documented in PRD, not just schema files) |
| A-§17-3 | Evidence model | strengthen (threat model + trust partition + filesystem-substitution boundary documented) |
| A-§17-4 | Evidence model | strengthen (durability asymmetry FULL/NORMAL codified) |
| A-§17-5 | Evidence model | neutral (organizational — per-track migration ranges; no invariant change) |
| A-§17-6 | Aggregation rules + Evidence model | strengthen (`admissible_verdicts` VIEW is the canonical read-side; raw access banned outside `audit/`) |
| A-§17-7 | Evidence model | neutral (v0.1 single-writer mechanism named; operational, not invariant) |
| A-§17-8 | Evidence model | strengthen (evidence-first ordering; ATTACH banned; cost re-derivable from evidence) |
| A-§17-9 | Evidence model | strengthen (PRAGMA-scope grep ban upgrades documented discipline to CI mechanism) |
| A-§17-10 | Evidence model | strengthen (repository surface restriction defense-in-depth over A1 triggers) |
| A-§17-11 | Evidence model | strengthen (Track E migrations spec'd in PRD; UNIQUE prevents A15-gate inflation) |
| A-§18-1 | Pipeline safety (CLAUDE.md Section 13) | strengthen (dry-run-default codified in PRD, not just CLAUDE.md) |
| A-§18-2 | Pipeline safety | strengthen (`calibrate` explicitly named) |
| A-§18-3 | Control-flow ownership + Aggregation rules | strengthen (`evaluate-skill` as pure read; no LLM calls = no judge can affect aggregation) |
| A-§18-4 | Clause discipline + Evidence model | strengthen (verdict_id rename + UNIQUE + Tier-1-only v0.1 scope) |
| A-§18-5 | Metric provenance | strengthen (`metric_drift` category-error guard) |
| A-§18-6 | Aggregation rules | strengthen (exit-code uniformity; UNMEASURED ≠ FAILED at the shell layer) |
| A-§18-7 | Control-flow ownership | strengthen (`--show-rendered` makes ablation operator inspectable; "untrustworthy if not inspectable") |
| A-§19#7-1 | Clause discipline + Metric provenance | strengthen (PASSED ⇔ posterior met ∧ non-stale frozen case at current metric_version) |
| A-§16-CF1 | Metric provenance | strengthen (`aggregation_provenance` sub-keys enumerated; mutation-tested to be load-bearing) |

**No amendment weakens any load-bearing invariant.** No HALT required on invariant grounds.

The Pre-Track-D §1 reframe (A-§1-1) is the closest thing to a "framing-level" change, but Appendix E EVR-6 explicitly argues it **strengthens** the harness's defensible claim by anchoring on evidentiary discipline rather than estimator novelty. The LOO honesty caveat in the same reframe is a one-way safe failure (false-negative on contribution, never false-positive on PASS) and is consistent with the Aggregation rules invariant.

---

## CF-Phase-3-3-1 disposition

**Recommendation: ADOPT-AS-AMENDMENT-45.**

Rationale: M10 + M11 in the mutation sweep prove the two sub-keys are load-bearing (untested = a developer's "be conservative" refactor would silently null them, which downstream `diff skill` consumers depend on per A55 `metric_drift` framing — the diff-side check is structurally undermined if `aggregation_provenance` content varies silently between runs). The pro-side ("council-decision pattern" objection — that no council fire formally adopted this) is met by: (a) the source is mutation testing, which is a *mechanical* discipline producing falsifiable evidence (the appropriate authority for a wire-format enumeration question is the mutation sweep itself, not a values-debate council), and (b) the amendment is purely enumerative — it lists sub-keys that the implementation already writes; it does not add new behavior or change semantics. This is the same pattern as A56's "current schema lacks `verdict_id` FK" — a structural gap found by implementation review, adopted into the next doc-lock without firing a new council.

The conservative alternative (DEFER-TO-COUNCIL) would queue this for a Phase-3.6 council fire whose only finding would be "yes, enumerate the sub-keys"; that fire's expected cost (orchestrator time + 4-6 seat dispatches) is much higher than the value added by the additional review surface, given that the sub-keys are already mechanically tested. The mutation sweep IS the falsifying-case discipline applied to A60's wire format.

---

## Sequencing summary

1. Apply §-by-§ in this order:
   - **§1** (single amendment; reframes positioning)
   - **§3.1** (single amendment; reconciles forbidden patterns with §5 Tier 2)
   - **§3.4 / §7a** (single amendment; Falsifying Case Schema)
   - **§5 Tier 2** (three amendments; treat as one cohesive rewrite)
   - **§5 Tier 3** (single amendment; mark DEFERRED)
   - **§6** (four amendments; treat as one cohesive expansion with sub-sections §6.1 calibration input)
   - **§7** (single amendment; vacuity 3-state split)
   - **§11** (single amendment; replace Detection sub-section)
   - **§12** (two amendments; §12.1 audit-gate sub-section)
   - **§13** (single amendment; replace Outputs sub-section)
   - **§14** (three amendments; §14.1 / §14.2 / §14.3 — apply BEFORE existing Pass Rule, do NOT touch Pass Rule)
   - **§15** (two amendments; A-§15-1 BEFORE A-§15-2 so `falsifying_case_stale` exists before §15.1 references it)
   - **§16** (two amendments; A-§16-1 main wire format, A-§16-CF1 sub-key enumeration as a sub-section)
   - **§17** (eleven amendments; sequenced per §17 sub-section notes above — apply A-§17-1 first as skeleton, end with A-§17-3 + A-§17-9 in new §17a Threat model block)
   - **§18** (seven amendments; apply in source order matching the existing six `##` headings + new §18.1 Exit codes block)
   - **§19** (single amendment; add criterion #7)

2. Estimated edit count: **42 distinct text replacements** (4 amendments collapse into existing edits — A-§6-4 is a cross-reference only, A-§17-5/-7/-9 reuse blocks created by A-§17-1 / A-§17-3 — leaves 41 net edits + 1 new §17a section header = 42).

3. Risk of accidental contradictions (one amendment undoing another): **NONE detected**, with two notes:
   - **The Pre-Track-D §1 reframe (Appendix E)** explicitly *replaces* the original D2 §1 edit. Treat as ONE amendment (the audit lists it as A-§1-1 with both drivers). Do NOT apply both as separate edits — that would either double-edit or revert.
   - **A-§17 amendments overlap heavily on the Persistence sub-section.** Apply A-§17-1 first as the skeleton; subsequent §17 amendments insert into well-defined positions within that skeleton. Avoid applying §17 amendments in random order — the §17 sequencing list above is load-bearing.

---

## Open questions for the orchestrator

1. **A-§16-CF1 disposition gate.** The recommendation above (ADOPT-AS-AMENDMENT-45) bypasses the council-decision pattern. If the orchestrator's `feedback-route-to-most-expert` interpretation requires *any* PRD wire-format addition to route through a council fire, downgrade to DEFER-TO-COUNCIL and add a Phase-3.6 fire-point to PLAN.md. Audit's stance: ADOPT is correct because the source authority is mutation testing (mechanical), not values-debate, but flag this as a values-style routing choice the orchestrator may want to confirm.

2. **§17 vs §17a section ordering.** The original 2026-06-03 table had a "§17a (new) — Threat-model section" row. The audit places A-§17-3 (Trust partition + filesystem-substitution + PRAGMA scope) AND A-§17-9 (PRAGMA grep ban) into a new §17a Threat model block. Confirm this is the intended structure (vs. inlining the threat model as sub-sections of §17 itself). The audit's reading is that §17a is the right home because the original table explicitly created it; if the orchestrator prefers all-in-§17, fold §17a content into a §17 "Threat model (informal)" sub-section instead.

3. **Pre-Track-D §1 reframe identification.** Appendix E states "PRD v1.1 amendment queued (replaces the D2 §1 edit)". The audit interprets this as a 1-for-1 replacement of the original D2 row. If the orchestrator's reading is "the D2 edit ALSO applies, augmented by the Pre-Track-D reframe", apply both: drop "manufactured primitives" AND add Appendix E EVR-6's evidentiary-discipline positioning. The audit's reading is that EVR-6 already incorporates the "drop manufactured primitives" intent into its replacement text, so one edit suffices. No verbatim Appendix E text contradicts this reading, but the original table's wording "Drop \"manufactured primitives\"; add prior-art citations" is more specific on the prior-art citations than Appendix E's "P4 signature, zero hits" language — the audit's draft above preserves BOTH (prior-art citations + evidentiary-discipline framing). If the orchestrator wants only the Appendix E text, strip the prior-art citation list.

4. **A-§6 sub-sections vs flat bullet list.** §6 is the most-amended single section (four amendments). The audit's draft proposes inserting a new sub-section "§6.1 Calibration input schema" to house A-§6-2's JSONL schema. If the orchestrator prefers §6 stay flat (no sub-sections), the four amendments can collapse into a single expanded bullet list, but the JSONL schema becomes harder to reference from §13. The audit's reading is that §6.1 is cleaner; orchestrator may prefer the simpler structure.

5. **C2 disposition surfacing.** Appendix E resolved C2 (operator-self-label calibration tier) as REFUSE without surfacing to the user (per `feedback-route-to-most-expert` / `feedback-non-technical-sme`). The audit treats this as already-resolved (no PRD edit needed beyond A-§6-2's mention that operator-self-label is rejected). If the orchestrator wants C2's resolution explicitly stamped in PRD §6 prose (not just in the JSONL admissibility states), add a one-paragraph note: "Operator-self-label calibration is refused in v0.1 on independence-collapse grounds (see COUNCIL_FINDINGS Appendix E)." Audit's reading is this is already implicit in A-§6-2's "no starter set ships; user-provided" clause, but more explicit is also fine.

---

## Self-review

Re-counted amendments against the source-of-truth tables:

| Source | Tabular rows | Listed in audit |
|---|---:|---:|
| Original 2026-06-03 table (incl. 4 SECURITY/RELIABILITY rows) | 20 | 20 (4 collapsed into §17 multi-amendment block; 1 collapsed with A-§1-1; all individually mapped) |
| Pre-Track-A impl (Appendix C, A24-A30) | 6 | 6 (A-§17-5/-6/-7/-8/-9/-10) |
| Pre-Track-C (Appendix D, A31-A38) | 8 | 8 (A-§18-2, A-§6-2, A-§6-3, A-§5T2-2, A-§5T2-3, A-§12-2, A-§6-1 partly, A-§5T2-1 partly via A35; mapped across §5 Tier 2 + §6 + §12 + §18) |
| Pre-Track-D (Appendix E) — §1 reframe | 1 (replacement, not addition) | 1 (A-§1-1, both drivers cited) |
| Pre-Track-E (Appendix F, A53-A61 amendments table) | 10 | 10 (A-§14-2, A-§15-1, A-§15-2, A-§16-1, A-§17-11 ×2, A-§18-3, A-§18-4, A-§18-5/-6, A-§19#7-1) |
| Phase 3.3 fix brief (CF-Phase-3-3-1) | 1 | 1 (A-§16-CF1) |
| **Total** | **45** | **45** |

Misattribution check: Each amendment's driver finding ID was cross-checked against the source Appendix's "Adopted decisions" block. No misattribution found.

Missed amendments: None. The §17 row in the original table for "Append-only via triggers; two-DB partition; cost ledger" cites both A1 + A2 + A12 — all three drivers are preserved in A-§17-1. The Pre-Track-D Appendix E adopted A39-A52 but only A50 (LOO honesty framing) lands in the §1 reframe; A39-A49 + A51-A52 are runtime / Track D ablation specifics that affect *behaviour* but are not PRD-level wire spec (e.g., A39 ablation operator implementation, A40 sample idempotency schema). The audit confirms Appendix E's PRD-level queue is exactly one row (§1 reframe) and is captured.

CF-Phase-3-3-1 self-check: the recommendation block is honest about the routing-pattern concern (the Open Questions item #1 flags it for orchestrator confirmation).

Coverage law for this audit: 45/45 amendments → 100%. No "UNMEASURED" rows.

---

*End of audit. Orchestrator: commit this doc and proceed to Phase 3.5 PRD v1.1 edit batch per the sequencing summary.*
