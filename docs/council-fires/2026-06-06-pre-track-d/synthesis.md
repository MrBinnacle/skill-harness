# Pre-Track-D Council Fire — Synthesis

**Date:** 2026-06-06
**Template:** Custom (PLAN row 4) — STAT + COST + RELIABILITY + OPERATOR-DX **+ EVAL-RESEARCH**
**Roster deviation:** EVAL-RESEARCH added to the PLAN row-4 4-seat roster because the 2026-06-06 landscape sweep (`docs/research/landscape-2026-06-06.md`) injected eval-methodology questions (Q9-Q11 ablation-attribution validity, C2 calibration) the original 4 seats under-cover. Recorded as an orchestrator roster-expansion call driven by changed inputs.
**Model:** Opus 4.7 all seats. Read-only. Dispatched in parallel (one message), cross-talk + disposition-schema contract.
**Inputs:** PLAN Track D scope, COUNCIL_FINDINGS A8/A11/A12/A13/A24-A38/§C2, landscape report §3/§5, CLAUDE.md invariants, checkpoint Q1-Q11 draft, repo state (`run ablation` stub, storage, oracles).
**Raw seat outputs:** `raw-outputs.md` (this directory).

---

## Headline

Track D's design is now decided. **14 findings adopted (A39-A52)**, **C2 resolved = REFUSE** (SME verdict, not surfaced to user), one cross-seat tension (A13 cache vs neutral substitution) **resolved**, and three **citation corrections** to the landscape report logged. Three BLOCKER-grade structural gaps were found in the *current* schema that Track D must close before it can ship safe evidence: no ablation-operator policy, no sample idempotency key, and a cost-ledger under-count window.

The deepest result: the seats **confirmed the academic warning** (single-clause LOO is the inferior estimator in its family) and converted it from a latent flaw into three concrete, cheap, design-time fixes — plus a positioning reframe (EVR-6) that turns LOO's conservatism into a *feature* for an adversarial-audit product.

---

## Convergences (3+ seats agree → adopt)

### C-1 · Ablation operator = versioned neutral matched-length substitution, NOT deletion → **A39** (BLOCKER)
Seats: STAT-4, EVR-2, ODX-5 (all BLOCKER), COST-5 (concur, cost-neutral/favorable).
Naive deletion conflates the clause's axis-effect with prompt coherence/length/format loss; **`verbosity` is one of our own four Tier-1 axes**, so deletion self-evidently contaminates it. Verified source: Li & Janson, "Optimal Ablation for Interpretability" (arXiv:2409.09951) — operator choice materially changes measured importance. (The landscape's "3-9x swing" magnitude is NOT in the abstract; the *directional* finding is confirmed and load-bearing; magnitude flagged as landscape-sourced.)
**Decision:** Track D constructs a deterministic, byte-stable, matched-length semantically-null placeholder per (clause, version). The deterministic layer builds the substituted prompt — never a model (control-flow ownership). Store `ablation_operator_id` + `implementation_hash` on every verdict at write-time (mirrors metric-version provenance).

### C-2 · A13 cache-ordering vs neutral-substitution tension → **RESOLVED within A39/A43**
Flagged by COST-1/COST-5, ODX-5, STAT cross-talk. A13 ("reorder ablated clause LAST") is a deletion-style operator; neutral substitution puts a placeholder *in* the prompt.
**Resolution (not a real disagreement):** substitution is *cost-favorable* (COST-5) — a matched-length placeholder keeps the skill-prefix token count constant across Full/Ablated_k, stabilizing the cacheable prefix and making cost projection deterministic; deletion perturbs it. Requirement: the placeholder must be deterministic/byte-stable per (clause, version) or it busts the cache each run. Track D validates cache-prefix placement with a cache-marker assertion test. Cache reuse is **K-local** (within one clause's conditions), not M-global.

### C-3 · Sample idempotency + resumability → **A40** (BLOCKER)
Seats: REL-2 (BLOCKER), STAT cross-talk (resumed `n` must be exact), COST cross-talk (resume must sum ledger), ODX-3 (resume surface).
**`samples` has no `(run_id, clause_id, condition, sample_index)` key** — only a content-derived PK. On crash-resume the runner cannot tell which samples already exist → re-issues paid calls → writes duplicates that inflate Beta-Binomial `w`/`n`, and append-only makes this **uncorrectable**.
**Decision:** migration 0300 adds `sample_index INTEGER NOT NULL` + `UNIQUE(run_id, clause_id, condition, sample_index)`. Resume = set-difference of existing tuples against the frozen plan in `runs.config_json`; issue calls only for missing slots. Per-call policy: retry-with-backoff (transient 429/500/network) / skip-and-record (permanent 400) / abort-run (budget). TRACK-D-EXIT-CRITERION: kill-at-1,732/4,000 resumes to exactly 4,000, never 4,001.

### C-4 · Cost re-derivable from evidence (ledger under-count) → **A41** (BLOCKER)
Seats: REL-6 (BLOCKER), COST-3 (ledger writes actual usage).
`cost_ledger` write is a *separate* runtime transaction committed AFTER the evidence verdict, and the helper **swallows the runtime failure** (`dual_write.py:91-105`). Crash between commits → real spend happened, ledger under-counts → daily-cap sum reads low → **budget over-run becomes possible**. Runtime is `synchronous=NORMAL` yet is currently the *only* record of spend.
**Decision:** write per-call token/usd cost columns onto the evidence rows (samples/verdicts) **inside the evidence transaction** (`synchronous=FULL`, durable). `cost_ledger` becomes a *projection* of evidence; reconciler replays evidence cost into the ledger for any run whose sums disagree (A25 "orphan is reconciler-detectable" philosophy). Cost written from the actual response `usage` block, never from the projection.

### C-5 · UNMEASURED ≠ FAILED — distinct vocabulary + exit codes → **A48** (BLOCKER)
Seats: ODX-4 (BLOCKER — it's PRD §19.2 success criterion), STAT-1, STAT cross-talk.
**Decision:** FAILED renders red `FAILED (P(win)≤.05)`; UNMEASURED renders yellow `UNMEASURED(<subreason>)` with A17 sub-reason inline (`no_data | inadmissible | underpowered | falsifying_case_missing | budget_exhausted`). Exit codes: `0` = every clause reached a verdict; `2` = ≥1 UNMEASURED; non-2 reserved for hard errors. Falsifiable test: an `underpowered` clause exits 2, not the FAILED path.

### C-6 · C2 operator-self-label calibration → **RESOLVED = REFUSE** (SME verdict; NOT surfaced to user)
Seats: EVR-4 (primary, BLOCKER-to-flip), STAT-8 (HOLD REFUSE), COST-6 (concede PRO, concur REFUSE). **Unanimous.**
The defect is **independence collapse**, not "κ≈1.0" (judge and operator are distinct raters; κ≠1.0). A self-labeled set certifies only "agrees with this operator," never an axis-level claim — which is the cross-axis-inheritance prohibition restated. The flip's own guardrail (downstream pool must reject self-labeled verdicts) concedes they aren't evidence-grade. COST's "ships testable" PRO is met by a synthetic test fixture, not by minting an invalid tier. Per landscape §4, the calibration corpus is *the moat* — a self-labeled corpus is worthless as the asset (its "agrees-with-operator" basis is exactly what the third-party-audit buyer distrusts).
**Decision:** No `operator_self_labeled` admissible tier in v0.1. If ever flipped (v0.2, opt-in): `provisional_non_admissible` state, hard-excluded from the Beta-Binomial pool **at the VIEW layer**, 30-day cadence, every report stamped `[operator-calibrated — not independently validated]`. **Correction also feeds the EVAL-RESEARCH citation note:** do NOT cite arXiv:2510.09738 ("Judge's Verdict") as the REFUSE authority — it classifies judge capability, it does not prescribe refusing uncalibrated judges; the authority is `llm-judge-calibration` + independence theory.

---

## Single-seat / co-owned adopts

| ID | Finding | Severity | Seats | Disposition |
|---|---|---|---|---|
| **A42** | Budget cap check + reservation in ONE `writer_transaction(runtime)`; race-safe under A26 single-writer; abort writes `run_progress` terminal state. Race only reappears at multi-process (D11). | MAJOR | COST-2, REL-4 | TRACK-D-EXIT-CRITERION |
| **A43** | Cache discipline: `system` as typed blocks with `cache_control:{type:ephemeral}`; two breakpoints (end-of-system, end-of-skill-prefix); ablated-clause-last; warmup-or-serialize so cache-write lands before reads; cache-marker assertion test. **Track C's ~71% reuse is currently aspirational — judge.py passes `system` as a bare string, no markers.** | MAJOR | COST-1, COST-4 | ADOPT + TRACK-D-EXIT-CRITERION |
| **A44** | N_max reached without stop = hard stop → `UNMEASURED(underpowered)` with achieved posterior recorded; `stopping_reason ∈ {passed, failed, underpowered_nmax, budget_exhausted}` on run config snapshot. No "add batches past N_max." Bayesian-posterior stop is not frequentist-alpha-inflating per-clause (multiplicity is the cross-clause concern → A49). | MAJOR | STAT-1 | TRACK-D-EXIT-CRITERION |
| **A45** | Confound stays two-table: `confound_events` written once at detection in the same orchestration pass; exclusion via `admissible_verdicts` VIEW at read-time. This is write-time-snapshot-COMPATIBLE (the invariant binds admissibility/calibration state, not confound geometry). Do NOT denormalize a `confound_flagged` column onto verdicts. | MAJOR | STAT-3, REL-5 | ADOPT |
| **A46** | **A29 JOIN directionality CONFIRMED CORRECT — closes the open question.** `primary_clause_id` = the ablated clause = the verdict being judged; matching `v.clause_id = ce.primary_clause_id` correctly taints N's own verdict. Do NOT also taint the *affected* clause M (would over-exclude, silently shrink coverage; M's unclaimed move is an `observed_unclaimed_delta` audit row per A11, not an exclusion). Write-side assertion: `primary_clause_id == ablated_clause_id`. | MINOR | EVR-5 | ADOPT (closes A29) + TRACK-D-EXIT-CRITERION |
| **A47** | Confound storage = threshold-triggered events only (NO dense per-sample×axis matrix — would be 16k+ rows/run of mostly non-events). All-axes deltas computed in-memory per condition-cell. σ(Null) estimated **per-(run,axis)** at write-time (not pooled-at-read), N_null≥30 floor, k=2.0. Below floor → confound detection disabled for that axis, affected verdicts carry `UNMEASURED(underpowered)`. Uncalibrated Tier-2 axes excluded from σ(Null) (no admissible instrument ⇒ no confound claim). | MAJOR | STAT-2, REL-3 | ADOPT |
| **A49** | Multiplicity owned by **Track E** (A9 hierarchical Beta-Binomial; BH-FDR fallback). Track D obligation = lossless per-comparison provenance: every verdict carries `(run_id, clause_id, axis, comparison)` + run config records family size K×\|axes\| so Track E has the multiplicity denominator without re-deriving. Documented in the Track D brief so the hand-off isn't dropped. | MAJOR | STAT-7 | TRACK-D-EXIT-CRITERION (metadata) |
| **A50** | LOO honesty framing: report column = `Contribution (single-clause LOO; lower-bound under redundancy)`; "absence of delta is not absence of contribution." Random-subset surrogate (ContextCite-style LASSO over masks, ~2-4m fitted ablations, NOT 2^m) = documented **v0.2** upgrade. Redundancy cancellation (JoPA, arXiv:2405.20404) = **documented v0.1 limitation**; triggered (NOT blanket — O(m²)) paired-ablation probe optional behind `--probe-redundancy`, charges budget, only *reclassifies* UNMEASURED (never upgrades to PASSED). | MAJOR | STAT-5, STAT-6, EVR-1, EVR-3 | DOCUMENTED-LIMITATION + optional flag |
| **A51** | Dry-run discipline: per-clause table (`clause# \| axis \| conditions \| N_proj(min..max) \| est_CI_width \| status{TESTABLE \| VACUOUS-EXCLUDED \| NO-FALSIFYING-CASE}`); **offline projection** — constructs no DB conn, no `JudgeClient`, requires no API key (pull-forward TC-SLOP-001/002); terminal line `NO CALLS MADE — re-run with --execute`; distinct `--max-usd` (per-run) vs `--daily-cap` (trailing-24h) errors naming the offending flag. | MAJOR | ODX-1, ODX-6 | TRACK-D-EXIT-CRITERION |
| **A52** | Resume + progress + inspection UX, all as FLAGS on `run ablation` (PRD §18 command set is locked — no new command): `--resume <run_id>` with a resume-preview line; bare re-run against an incomplete prior run WARNS + names the resumable run_id (no silent fresh-start/double-spend); `rich.progress` per-clause + live dual-cap footer `spent $X / cap $Y (run) · $Z / $W (day)`; `--show-rendered <clause_id>` prints verbatim Full/Ablated_k/Null + `ablation_operator_version` (a run is untrustworthy if the ablation operator isn't inspectable). | MAJOR | ODX-2, ODX-3, ODX-5 | ADOPT + TRACK-D-EXIT-CRITERION |

---

## Citation corrections (per subagent-research-reliability — seats verified primary sources)

The landscape report's load-bearing claims **survive**, but three citations were corrected by STAT + EVAL-RESEARCH at primary source. Fold into any external-facing use of the report:

1. **arXiv:2405.20404 is "JoPA: Joint Prompt Attribution" (Chang et al., ACL 2025)** — the landscape report called it "XPrompt/JoPA." XPrompt is a different (PEFT) line. Cite as **JoPA**. The combinatorial/non-additivity claim is verified; the "doctor/patient false-negative" example is NOT in the abstract — treat as report illustration, not a paper quote.
2. **arXiv:2312.15395 (Liu et al., Shapley prompt valuation)** applies Shapley to **whole prompts in an ensemble, NOT within-prompt components.** It supports the *concept* of Shapley-over-LOO but is NOT a within-prompt-component-decomposition precedent. The clause-level Shapley argument rests on ContextCite's random-subset design + textbook Shapley-vs-LOO theory.
3. **arXiv:2510.09738 ("Judge's Verdict")** is a judge-capability/human-agreement classification paper; it does **not** prescribe "refuse uncalibrated judges." The REFUSE discipline's authority is `llm-judge-calibration` + independence theory, not this paper. The landscape report over-claimed it.
4. **arXiv:2409.09951 "3-9x swing"** — the *directional* finding (operator choice changes measured importance) is verified; the specific 3-9x magnitude is not abstract-confirmed. Cite directionally.

---

## Deferred (D-items, v0.2+)

- Random-subset / ContextCite-style surrogate estimator (`run ablation --estimator=subset-surrogate`) — the principled fix for redundancy, ~2-4m calls/skill.
- Blanket joint-ablation sweep — O(m²), budget non-starter; only the triggered probe is in scope.
- Multi-process sampling (D11) — reintroduces the budget race A42 closes for single-writer.
- `operator_self_labeled` bootstrap affordance — v0.2 opt-in, non-admissible, VIEW-excluded.
- Cost reconciler as a `skill audit` subcommand — folds into D7.

---

## PRD v1.1 amendment queued (positioning — EVR-6)

Replace the D2 "manufactured primitives" edit to PRD §1 with the **EVR-6 reframe**: the harness's novel, defensible claim is **not** the estimator (LOO is the field's inferior estimator) — it is the *evidentiary discipline*: **"falsifiable directional contracts with write-time admissibility-gated, append-only provenance"** (the P4 signature that returned zero hits in the eval domain, landscape §1). LOO is then honestly the *conservative* estimator inside that discipline — under-crediting contribution is a *safe* failure for an adversarial audit (a false-negative on contribution, never a false-positive on a PASS). Pitch: *"we don't claim to fairly attribute; we claim every PASS is backed by admissible, provenance-stamped, directional evidence — and we refuse to claim anything else."*

---

## Cross-talk yield (findings no single seat would have produced)

1. **A13-cache × neutral-substitution collision** — surfaced by COST + ODX cross-predicting each other; neither STAT (who owns the operator) nor COST alone would have caught that the validity fix and the cost optimization interact. Resolved cost-favorably.
2. **Resume corrupts sequential `n`** — STAT predicted RELIABILITY would catch idempotency; REL-2 made it a BLOCKER; STAT then noted the *statistical* consequence (resumed run must restore exact `n`, not re-derive) that REL alone framed only as durability. Two lenses, one fix.
3. **`ablation_operator_id` must be pinned to the run, not re-resolved on resume** — EVR predicted RELIABILITY's write-once shape meets the provenance requirement: a crash-resume that picks up a new operator version silently mixes two operators in one condition-pair. Neither seat alone owns this.
4. **Cost-ledger is also the crash-recovery ledger** — COST × RELIABILITY co-derived that resume must sum existing `cost_ledger` rows to rebuild `usd_spent` or it double-spends — a shared invariant, not either seat's solo finding.

---

## Status

All 5 seats returned `status: nominal`. No blocked/degraded seats. No unresolved BLOCKER (the three BLOCKER-grade gaps are adopted with concrete fixes). C2 resolved. Track D is cleared to dispatch once A39-A52 are folded into the Track D brief + exit criteria.
