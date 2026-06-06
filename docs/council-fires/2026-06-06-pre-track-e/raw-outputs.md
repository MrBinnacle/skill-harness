# Pre-Track-E raw seat outputs — 2026-06-06

Six seats dispatched in parallel, Opus 4.7, read-only. This file captures each seat's headline dispositions + key claims + cross-talk + STATUS line. Full verbatim of each agent's response lives in the conversation transcript at `~/.claude/projects/.../agent-*.jsonl` for the agent IDs listed below.

---

## STAT seat (agentId: a50d8519b57e2855c)

**Q1 (lead) — Hierarchical Beta-Binomial impl + convergence-failure protocol — MAJOR.**
EB-MoM via `scipy.stats` — no PyMC dep, deterministic, closed-form. Convergence failure = `α̂ ≤ 0 ∨ β̂ ≤ 0 ∨ var_between < 1e-6` → BH-FDR fallback (q=0.05). PASSED gate on shrunken vs unpooled is `[values decision]` (later retracted by orchestrator per route-to-most-expert). scipy>=1.11 direct dep (Phase 1.1 gap — currently transitive via statsmodels at `stopping.py:32`). BDA3 §5 warns MoM degenerate at K<10 → UNPOOLED default + logged warning when K<10. Verified: `pyproject.toml:46`, `stopping.py:32`. Cross-seat: SCHEMA confirms verdict fields for EB; EVAL-RESEARCH confirms EB-MoM baseline.

**Q7 (lead) — Family-size + TA-4 verification — OBSERVATION clean pass.**
Verified `RunConfig.family_size = K × |axes|` persisted via `to_json` to `runs.config_json` at `runner.py:154,338-339,160-177`. Track E reads via `json.loads(runs.config_json)["family_size"]`. Defensive `family_size > 0` invariant at Track E entry.

**Q2 (co) — OBSERVATION:** Pure aggregator required. EB hyperprior on partial data violates "no aggregation of in-flight runs." Read `runs.completed_at IS NOT NULL` only.

**Q5 (co) — MAJOR:** Auto-flip to UNMEASURED safer; posterior unchanged (still valid evidence); status changes. Add sub-reason `falsifying_case_stale_after_metric_upgrade`.

**Cross-talk:** TEST-ARCH RIGHT on PASSED→UNMEASURED transition observability; OPERATOR-DX WRONG on collapsing UNMEASURED + frozen_stale under exit 2 (recommends exit 3 — orchestrator rejected per A48 shape); EVAL-RESEARCH under-weights K<10 noisy hyperprior; RELIABILITY RIGHT on CF-D3-1 cross-DB authority question (`evidence.runs.completed_at` is authoritative, not `runtime.run_progress.state`).

**STATUS: nominal**

---

## TEST-ARCH seat (Plan agent)

**Q2 (lead) — `run evaluate-skill` orchestration — MAJOR (BLOCKER if cost framing dropped).**
Pure read-side aggregator. Discovers `runs` rows with `skill_id` + `run_kind='ablation'` + `completed_at IS NOT NULL`. Optional `evaluate_skill` envelope as audit-trail metadata (run_ids + hyperprior params), not sampling. No `--max-usd` / `--execute`. Falsifiable: zero completed ablations → exit 2 + zero API calls + no API key required. Verified: `cli/main.py:964-970` stub.

**Q3 (lead) — `diff skill <a> <b>` semantics + metric-version divergence — MAJOR.**
Revisions = distinct skill_id (content-hash); `clause_id` doesn't persist across revisions (embeds skill_id per `0001:32`). Comparability key = `(axis, clause_text_sha256)`. Metric-version OR ablation_operator_hash drift → `INCOMPARABLE(metric_version_drift)`. Status delta enum: `{PASSED→FAILED, FAILED→PASSED, UNMEASURED→PASSED, ADDED, REMOVED, INCOMPARABLE(reason)}`. Falsifiable: self-diff → all UNCHANGED.

**Q5 (lead) — Stale-frozen-case rule — BLOCKER.**
A15's "current metric_version" not implementable as written — no `current_metric_version` pointer table exists (grep-verified). Auto-flip to UNMEASURED(falsifying_case_stale). "Current" derived = `WHERE audited=1 ∧ mechanical_validity_test_passed=1 ORDER BY registered_at DESC LIMIT 1` (using `implementation_hash` for tamper-evident comparison). Add `falsifying_case_stale` as 6th sub-reason (A17 enum extension). No re-freeze command in v0.1 (operator runs `freeze` with new verdict — preserves append-only spirit).

**Q4 (co) — MAJOR:** Eligibility: FAILING-side verdict (observation ∈ {0.0, 0.5}), admissible, Tier-1 mechanical only in v0.1. Tier-2 needs human label → v0.2. Fix CLI signature `freeze <sample_id>` → `<verdict_id>`.

**Q6 (co) — MINOR:** Same A48 codes; reject granular subcodes for `freeze`.

**Q8 (co) — MINOR:** Field set: `(clause_id, status, subreason_if_unmeasured, posterior_mean, posterior_credible_interval, p_win_gt_threshold, frozen_case_count_at_current_metric_version, metric_id_per_axis, metric_version_per_axis, ablation_operator_hash, run_ids_aggregated)`.

**Cross-talk:** STAT RIGHT on convergence-failure protocol carry-through to report's `aggregation_method` field; SCHEMA WRONG if proposing materialized `clause_status` column on `clauses` (would violate A1/A3); OPERATOR-DX under-weights sub-reason distinctness (collapsing erases action-affordance); RELIABILITY RIGHT on CF-D3-1 intersecting Q2; EVAL-RESEARCH RIGHT on revision-diff novelty (no clause-level precedent → falsifiable framing required).

**STATUS: BLOCKER-FOUND** (Q5: "current metric_version" not implementable as A15 written — Track E must define the derivation rule.)

---

## SCHEMA seat (agentId: a4de32dd6a249b095)

**Q4 (lead) — `freeze <verdict_id>` contract — BLOCKER.**
Schema gap: `frozen_cases` (`0001:157-177`) lacks `verdict_id` FK, `run_id` FK, `axis` column, UNIQUE on `(clause_id, axis, failing_input_sha256)`. Without UNIQUE, duplicate freezes inflate A15 count. Migration `0400_freeze_provenance.sql`. UNIQUE-collision = idempotent (exit 0 "already frozen", not silent). `failing_input_text` derived from `samples.output_text`. Add BEFORE INSERT trigger refusing incomplete-parent.

**Q3 (co) — MAJOR:** skill_id = content-hash; clause_id embeds skill_id so doesn't persist; comparability via `(axis, clause_text_sha256)`. Metric-version + ablation_operator_hash + subject_model + user_message_sha256 must all match for comparability.

**Q5 (co) — MAJOR:** "Current" = highest `registered_at` per `metric_id` (semver string sort unsafe). Detection via VIEW, not trigger. Migration `0401_stale_frozen_view.sql` creates `current_metric_versions` + `frozen_cases_with_currency` VIEWs.

**Q7 (co) — OBSERVATION:** TA-4 satisfied (verified `runner.py:154,338-339,160-177,179-195`). `family_size = 0` legacy treated as "unknown, compute from verdict population."

**Q9 (co) — MAJOR:** Two-step Python join (`open_evidence_readonly` per A51) — no schema change. Alternative (add `skill_id` to `run_progress`) not recommended.

**Cross-talk:** STAT RIGHT on UNIQUE dedup BLOCKER stickiness (Bayesian harm framing); TEST-ARCH WRONG if framing freeze trigger as FAILED-status (verdicts are per-comparison, not clause-level — freeze is operator-driven); OPERATOR-DX under-weights Q5 stale-rendering (report must surface `frozen_cases: {current: N, stale: M}`); RELIABILITY RIGHT on Q9 over-warn safety (preserve false-positive WARNING > false-negative double-spend); EVAL-RESEARCH RIGHT on Q3 metric_version comparability (HELM/BIG-bench treat metric-version drift as hard incomparability).

**STATUS: BLOCKER-FOUND** (Q4 frozen_cases schema lacks verdict_id/run_id/axis + UNIQUE — Track-E migration 0400 required before `freeze` command lands.)

---

## OPERATOR-DX seat (agentId: a2d49a03009a90465)

**Q6 (lead) — Exit-code surface — MAJOR.**
Uniform A48 extension. `evaluate-skill` 0/2/1. `diff skill` default 0 + `--exit-on-divergence` flag → 2 (preserves A48 "2 = UNMEASURED" semantics). `freeze` 0/1 (no UNMEASURED concept). Rejects granular non-zero codes for `freeze` (degrades A48 clean shape; operators read stderr).

**Q8 (lead) — Report serialization — BLOCKER for diff machine-readability, MAJOR overall.**
`--format=rich|json` default rich. JSON with mandatory top-level `report_schema_version "1.0.0"` semver. Additive-only on `1.x` through v0.1 lifetime. Byte-stable for identical evidence (sorted keys, no internal timestamps). JSON to stdout only, warnings to stderr. Reject CSV/MD.

**Q2 (co) — MAJOR:** Pure aggregator. Wrapping breaks A48 exit-code disambiguation (UNMEASURED-from-ablation vs UNMEASURED-from-aggregation). Precondition error "no completed ablation run" → exit 1.

**Q4 (co) — MAJOR:** Discoverability gap — no path to obtain verdict_id today. Add `verdict_id` column to ablation report (cheap CLI change; not new command). Default `freeze` to dry-run (pattern consistency with `skill init`, `run ablation`, `calibrate`).

**Q9 (co) — MAJOR:** Track E inherits warning UX. Copy template shifts for aggregation context (no resume affordance). "Skill-accurate" def matches docstring sketch at `main.py:594-613`.

**Cross-talk:** STAT RIGHT on multiplicity-block in JSON schema reservation; TEST-ARCH WRONG if proposing `evaluate-skill` wraps `run ablation` (collides A12 cost-cap doctrine + A48 semantics); SCHEMA under-weights discoverability (verdict_id column on ablation report is the load-bearing UX fix); RELIABILITY RIGHT on aggregation-vs-concurrent-ablation race (snapshot identity must bind report); EVAL-RESEARCH WRONG if proposing wholesale HELM/lm-eval-harness adoption (assumes scalar quality scores, conflicts with project's directional `A beats B` invariant).

**STATUS: nominal**

---

## RELIABILITY seat (agentId: a2fec337dff7c417f)

**Q9 (lead) — CF-D3-1 scope — MAJOR.**
Lift helper to shared module NOW. Track E `freeze` + `evaluate-skill` both need it. Three signatures in `src/skill_harness/ablation/recovery.py` (or `storage/recovery.py`): `find_incomplete_runs(skill_id, *, evidence_conn_ro, runtime_conn)`, `run_is_complete(run_id, ...)`, `find_resumable_run_for_skill(...)`. Two-step lookup via `open_evidence_readonly` (verified exists at `storage/migrations.py:280`). Migrate `main.py:800` to use the new helper. No schema change.

**Q2 (co) — MAJOR:** Refuse-to-start on incomplete vs emit-UNMEASURED on no-evidence — distinct failure modes operators must discriminate. Precondition gate: for every `(clause_id, condition)` in clauses, ≥1 admissible verdict exists.

**Q7 (co) — OBSERVATION + MINOR:** Family-size durably frozen at run start (A40 sample-idempotency requires it). Add sanity assertion `family_size == len(clauses_in_config) * len(distinct_axes_in_config)`.

**Cross-talk:** STAT RIGHT on partial pooling effect on missing-clause UNMEASURED semantics (surviving clauses' posteriors validity); OPERATOR-DX WRONG if proposing single shared "incomplete run" exit code (per-command human-readable messages tied to recovery step); TEST-ARCH under-weights "incomplete prior run" as refuse-to-start (NOT an UNMEASURED sub-reason — it's an input-validation failure); SCHEMA under-weights `freeze` parent-completeness as needing BEFORE INSERT trigger (not just FK); EVAL-RESEARCH RIGHT on revision-diff precondition gate (HELM/MMLU-revision protocols may surface stronger requirements).

**STATUS: nominal**

---

## EVAL-RESEARCH seat (agentId: a20e42ab70dc4523b)

**Q1 (co) — Hierarchical Beta-Binomial — MAJOR.**
Closed-form per-clause Beta (no MCMC per-clause); PyMC NUTS for hyperprior. Cites: arXiv:2510.04265 "Don't Pass@k" (Beta closed-form > MCMC at small N); arXiv:2505.05602 HiBayES (hierarchical Bayesian GLMs for AI eval); PyMC canonical hierarchical partial pooling example. Convergence gate: R-hat < 1.03 + bulk-ESS ≥ 400 per hyperparameter (PyMC's own example threshold). Pin seed + record `pymc_version + numpyro_version + n_chains + n_draws` in aggregation provenance.

*(Orchestrator disposition: EB-MoM scipy adopted as v0.1 default per STAT; PyMC NUTS deferred to D21. EVAL-RESEARCH PyMC framing recorded as dissent with flip condition.)*

**Q3 (co) — `diff skill` semantics — MAJOR.**
No mainstream LLM eval framework ships principled `diff`. AlpacaEval CSV-only-no-diff; HELM open issues #2322 #2484 (users asking for diff-able format). Greenfield. Closest prior art arXiv:2602.10371 is *behavioral* diff (SAE features), not transferable to clause-status diff. Proposes `status_delta=metric_drift` as load-bearing category. Recommends exit 4 on metric_drift *(orchestrator: adopted as exit 2 under `--exit-on-divergence` for A48 shape; `metric_drift` term adopted in status enum).*

**Q8 (co) — Report serialization — MAJOR.**
JSON-as-primary with `report_schema_version` + provenance block. Open HELM issues prove community pays cost of skipping schema versioning. Required top-level keys: `report_schema_version, skill_id, skill_revision, generated_at_utc, harness_version, aggregation_method, aggregation_provenance, clauses[], vector, coverage, contribution`. v0.1 schema is `1.x` additive-only.

**Q2/Q4/Q5/Q6/Q7/Q9 — NOT-MY-LANE.**

**Cross-talk:** STAT RIGHT on conjugate-per-clause + MCMC-hyperprior not being "same Bayesian model" (partial pooling requires joint sampling); SCHEMA WRONG if defaulting metric_version to "current at diff time" (must snapshot per side of diff per A22 write-time discipline); OPERATOR-DX under-weights `report_schema_version` as ceremony (single cheapest audit-trail discipline; HELM issues prove cost); TEST-ARCH under-weights `metric_drift` as first-class status (lives at eval-methodology layer, not state-machine layer); RELIABILITY RIGHT on CF-D3-1 extending to `diff skill` precondition.

**Citations verified at primary source:** arXiv:2510.04265 + repo `mohsenhariri/scorio`; arXiv:2505.05602 HiBayES; PyMC canonical `hierarchical_partial_pooling` example URL; `scipy.stats.betabinom` docs; `EleutherAI/lm-evaluation-harness` repo; `stanford-crfm/helm` issues #2322 #2484; `tatsu-lab/alpaca_eval` README; arXiv:2602.10371 model-diffing.

**STATUS: nominal**

---

## Cross-talk yield summary

10+ accurate cross-predictions. 2 useful wrong predictions (OPERATOR-DX→TEST-ARCH wrapping; SCHEMA→TEST-ARCH freeze auto-trigger). 2 cross-derived findings (stale-vs-underpowered action-discrimination tension; freeze discoverability gap → ablation report verdict_id column). 3 genuine disagreements resolved with documented dissent.

See `synthesis.md` for the orchestrator-led disposition + adopted A53–A61.
