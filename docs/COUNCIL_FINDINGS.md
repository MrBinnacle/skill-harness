# Council Synthesis — 2026-06-03

5-seat cross-talk council fired against PRD v1.0 before any code was written.
Seats: TEST-ARCH, STAT, SCHEMA, EVAL-RESEARCH, COST.
Total findings: 31 (10 BLOCKER, 15 MAJOR, 4 MINOR, 1 OBSERVATION).
Pattern: `cross-talk-council-dispatch` + `parallel-review-disposition-schema`.

This document is the **decision log**, not a re-summary. Each adopted decision
names the council finding(s) that drove it, the current realization status,
and (where applicable) the PRD section that must be edited before v1.1 lock.

---

## A — Adopted decisions (v0.1)

### A1 · Append-only evidence via SQLite BEFORE triggers
- **Drivers**: SCHEMA-F1, F-6
- **Decision**: Every evidence table carries `BEFORE UPDATE` + `BEFORE DELETE` triggers that `RAISE(ABORT, 'append_only_violation: <table>')`. Application-layer contract alone is insufficient — bypassable via any sqlite3 REPL.
- **Status**: REALIZED in `migrations/evidence/0001_initial.sql` (skills, clauses, metric_versions, judges, calibration_events, samples, oracle_verdicts, confound_events, frozen_cases). Runs has a single-shot `completed_at` trigger.
- **Test coverage**: `tests/test_smoke.py::test_evidence_append_only_skills`, `::test_runs_completed_at_is_set_once`.

### A2 · Two-database partition (evidence.db + runtime.db)
- **Drivers**: SCHEMA-F2
- **Decision**: All append-only domain state lives in `evidence.db`. All mutable operational state — in-flight run progress, current calibration pointers, skill import staging, cost ledger — lives in `runtime.db`. Cross-DB FKs are enforced at the application layer, never via SQL.
- **Status**: REALIZED in both migration files; `open_evidence()` / `open_runtime()` helpers in `storage/migrations.py`.

### A3 · Admissibility snapshot at write time
- **Drivers**: SCHEMA-F6, PRD §6 verbatim
- **Decision**: Every `oracle_verdicts` row stores `calibration_event_id` (FK to immutable history) and `admissibility_state` as a stored CHECK-constrained string. Never recomputed from "current" calibration on read. The `current_calibration` pointer in runtime.db is *only* used at write time to resolve which calibration_event to snapshot.
- **Status**: REALIZED in schema; aggregation code (Track E) MUST read `admissibility_state` directly and MUST NOT join to `current_calibration`.

### A4 · Schema migration with SHA-256 tamper-evidence
- **Drivers**: SCHEMA-F5, PRD §10 by extension
- **Decision**: Numbered SQL files in `migrations/{evidence,runtime}/`. Each application records `(migration_id, file_sha256)` in append-only `schema_migrations`. On startup, file SHA mismatch against recorded SHA aborts with `MigrationTamperedError`.
- **Status**: REALIZED in `storage/migrations.py`.

### A5 · Pairwise-only Tier-2 judge protocol
- **Drivers**: EVAL-F5
- **Decision**: §3.1's "forbid quality scoring" and §5 Tier 2's LLM judge are reconciled: the Tier-2 judge is admissible ONLY in pairwise-preference mode for one named axis. Judge prompts MUST present both candidates, MUST output `{A, B, tie}` for one axis, MUST NOT emit a numeric score. G-Eval-style scalar templates are explicitly forbidden.
- **Status**: REQUIRES PRD edit (§3.1 reconciliation clause; §5 Tier 2 sub-rule). Schema permits via `observation REAL CHECK (observation IN (0.0, 0.5, 1.0))`.

### A6 · Mandatory position swap + length control
- **Drivers**: EVAL-F7, EVAL-F2
- **Decision**: Every Tier-2 verdict requires BOTH `(A, B)` and `(B, A)` orderings. Disagreement on position swap → `position_swap_agreement = 0` → `admissibility_state = 'inadmissible'` with reason `position_disagreement`. Length-controlled agreement is part of the calibration metric (AlpacaEval-2 regression pattern).
- **Status**: SCHEMA: `oracle_verdicts.position_swap_agreement` realized. Track D (ablation runner) and Track C (judge module) must enforce on write.
- **Cost note**: Doubles judge call count. Folded into COST formula via §A12.

### A7 · Calibration metric + thresholds named
- **Drivers**: STAT-F5, EVAL-F2
- **Decision**: For pairwise verdicts (the primary mode), calibration metric is **position-swap-symmetric pairwise-preference agreement vs human labels**, threshold ≥ 0.7; position-consistency threshold ≥ 0.8. Cohen's κ stored as secondary chance-corrected reporting. Minimum calibration set size = 50 pairs per `(judge_id, axis)`. Re-calibrate every 90 days or model version bump.
- **Status**: SCHEMA: `calibration_events` carries all five fields (`pairwise_agreement`, `position_consistency`, `length_controlled_agreement`, `cohen_kappa`, `pair_set_size`). Track C must enforce on calibration write.

### A8 · Sequential stopping rule + N_min floor
- **Drivers**: STAT-F1, STAT-F3, COST-F4
- **Decision**: Default sampling rule:
  - `N_min = 8` per condition pair (above STAT-F3's analytic floor of 5)
  - `N_inc = 4` (batch size between stop checks)
  - `N_max = 40`
  - Stop when `P(rate > 0.60) ≥ 0.95` (PASS) OR `P(rate > 0.60) ≤ 0.05` (FAIL); else add `N_inc`
  - Stopping rationale recorded per condition pair (will need a new column in v0.2 or a JSON config snapshot on `runs.config_json`)
- **Variance budgeting** (STAT-F1): per-clause posterior-width stop rule + global token budget. Greedy allocation by `1/posterior_width`. Operationalized in Track D.
- **Status**: PRD edit pending (§14). Track D implements.

### A9 · Multiplicity correction: hierarchical Beta-Binomial
- **Drivers**: STAT-F2
- **Decision**: For K clauses per skill, pool via hyperprior `Beta(α_skill, β_skill)`. This shrinks weak signals toward the skill mean and is self-immunizing against family-wise false positives. BH-FDR is the cheap fallback if the hierarchical fit doesn't converge.
- **Status**: PRD edit pending (§14). Track E implements; STAT track (which is folded into Track E) owns the prior fitting.

### A10 · Tie encoding: half-update (provisional, open for user flip)
- **Drivers**: STAT-F4
- **Decision (provisional)**: Treat `Tie = 0.5` observations as TWO updates (half-win + half-loss). Same posterior mean as 0.5 encoding, slightly different variance, but Bayesian semantics are honest (pseudo-Bernoulli). Tie count is stored separately (`tie_count` column in v0.2 reporting view) so the operator can switch to drop-ties at report time without re-sampling.
- **Open**: User may flip to "drop ties" — preserves Beta-Binomial conjugacy exactly. See §C1.

### A11 · Confound detection across ALL metric_library axes
- **Drivers**: TEST-ARCH-F3, EVAL-F6
- **Decision**: §11 must monitor every axis in `metric_library_v1`, not just clause-claimed axes. Movement on a non-claimed axis is recorded as `delta_kind = 'observed_unclaimed_delta'` (audit only, never aggregated). Movement on a claimed-but-other-clause axis is `'confound_flagged'`. Threshold: `delta > k · σ_axis(Null)` with default `k = 2.0`, `N_null ≥ 30` for variance estimation.
- **Status**: SCHEMA: `confound_events.delta_kind` + `null_sigma` + `k_threshold` realized. Track D implements monitoring. PRD edit pending (§11).

### A12 · Three-layer cost cap with dry-run default
- **Drivers**: COST-F3
- **Decision**:
  - **(a)** `run ablation` and `run evaluate-skill` default to dry-run. Print: `projected: N calls, T_in input (cached/uncached split), T_out output, ≈$X on <model>; cache reuse: P%`. `--execute` flag required to call the API.
  - **(b)** Per-run hard ceiling `--max-usd <X>` (default $5). Tracked in `runtime.run_budget.usd_spent`; aborts run if projection of remaining > ceiling.
  - **(c)** Per-day rolling ceiling `--daily-cap <X>` (default $20). Sum trailing 24h from `runtime.cost_ledger`; refuse start if `--daily-cap` would be exceeded.
- **Status**: SCHEMA: `run_budget` + `cost_ledger` realized in runtime.db. Track D + Track CLI implement.

### A13 · Prompt cache: ablated clause LAST
- **Drivers**: COST-F2
- **Decision**: At runtime, rearrange skill so the ablated clause is last in the prompt. This makes `system + skill_minus_last_clause` a shared cacheable prefix across Full and Ablated_k requests. Place `cache_control: ephemeral` breakpoint at end of system block and end of skill prefix. ~3.5× reduction in subject input cost on K=10/N=20 example. Authoring order (`clauses.clause_index`) and rendering order (`clauses.rendering_index`) are stored separately so provenance survives the reorder.
- **Status**: SCHEMA: `clauses.rendering_index` realized. Track C / Track D implement at API call.

### A14 · Tier-1 mechanical metric validity audit
- **Drivers**: COST-F5, EVAL-F4
- **Decision**: Two of the six §12 "Supported" metrics are NOT mechanical:
  - **Assertion Density** (`factual_claims / sentences`) — requires NLI / claim extraction
  - **Unsupported Claim Ratio** — requires claim extraction AND evidence-attribution
  - **Compliance Proxy** — requires directive classifier (heuristic, fragile)
  - **Citation Density** (regex) — false-positives on markdown code blocks
  - **Hedge Index** — depends on a corpus-bound, context-blind wordlist
- **Two-track fix**:
  1. **Redefine as honest heuristics**: e.g., `assertion_density := declarative_sentences / total_sentences` (regex on punctuation + leading-verb), `unsupported_claim_ratio := sentences_lacking_inline_citation_marker / declarative_sentences` (regex for `[N]`, `[Author Year]`, URL, `(source: …)`). These proxies are honest about being heuristic; the originals are not.
  2. **Mechanical Validity Audit gate** (`metric_versions.mechanical_validity_test_passed`): every Tier-1 metric must pass an offline-only, network-blocked, deterministic-output test before its `tier = 1` row inserts. Failures auto-downgrade to Tier 2.
- **Status**: SCHEMA: `mechanical_validity_test_passed` flag realized. Track C implements the audit gate. PRD edit pending (§12 demotion list + audit rule).

### A15 · Falsifying Case Schema + PASSED requires frozen case
- **Drivers**: TEST-ARCH-F1, TEST-ARCH-F5
- **Decision**: §3.4 / §8's "at least one falsifying case" gets a concrete type: every clause declares `(input_population_spec, expected_directional_pair, min_reproducibility)`. Until that schema is frozen (SHA-256 stored in `clauses.falsifying_case_schema_sha256`), the clause cannot transition to PASSED — regardless of posterior. `PASSED ⇔ posterior_threshold_met ∧ ≥1 frozen_case_at_current_metric_version`.
- **Status**: SCHEMA: `clauses.falsifying_case_schema_sha256` realized (nullable until populated). Track B (clause extractor) emits the schema; Track E gates the PASSED transition. PRD edit pending (§7a + §15 + §19 #7).

### A16 · Vacuity split: mechanical vs semantic
- **Drivers**: TEST-ARCH-F2
- **Decision**: §7's three vacuity criteria split into two states:
  - `mechanical_vacuous` — axis not in metric_library (deterministic, auto-exclude)
  - `semantic_vacuous_pending_review` — extractor judged it had no measurable axis or no falsifying case (LLM judgment; stored as `UNMEASURED` with reason, NOT silently excluded)
- The extractor itself is a Tier-2 judge — `(extractor_id, skill_genre)` needs a calibration entry in v0.2.
- **Status**: SCHEMA: `clauses.vacuity_flag` realized as 3-value enum. Track B implements. Coverage formula reports two numerators in v0.2. PRD edit pending (§7).

### A17 · UNMEASURED sub-reasons + INADMISSIBLE distinct
- **Drivers**: TEST-ARCH-F4, STAT-F6
- **Decision**: §15 keeps four headline states (`PASSED / FAILED / CONFOUNDED / UNMEASURED`) but `UNMEASURED` carries an explicit sub-reason: `no_data | inadmissible | underpowered | falsifying_case_missing | budget_exhausted`. A clause with verdicts but all inadmissible is `UNMEASURED(inadmissible)`, never `PASSED`, never silently aggregated as "we didn't run it" — the tokens were spent.
- **Status**: Sub-reason column TBD in v0.2 status view (status is derived, not stored — per §A1/A3 discipline). Track E surfaces in reports. PRD edit pending (§15).

---

## D — Deferred to v0.2 or later

### D1 · Tier 3 Real-World Consequence oracle
- **Driver**: EVAL-F3
- **Why deferred**: No published precedent attributes a real-world outcome to a single skill clause. The Copilot RCTs (Peng et al. 2023; Cui et al. 4000+ devs) measure whole-tool effects, not clause-level. Lag time weeks-to-months; SNR effectively zero without a clause-instrumented RCT.
- **Action**: PRD §5 Tier 3 reframed as "deferred — Tier 3 oracles require external instrumented studies." `frozen_cases.oracle_source` CHECK constraint excludes `'real_world'` for v0.1. Re-evaluate post-v0.1 dogfooding.

### D2 · "Manufactured primitives" framing
- **Driver**: EVAL-F1
- **Why deferred**: Cosmetic copy-edit. PRD §1 should drop the "four manufactured primitives" framing and instead position as "applies clause-level prompt-component ablation (Sclar et al. 2310.11324, FLAN component ablations, et al.) to skill artifacts, with three disciplines: directional-only oracles, admissibility gating, append-only provenance." Not a blocker for v0.1 code; queue for PRD v1.1 doc pass.

### D3 · Coverage Law two-numerator reporting
- **Driver**: TEST-ARCH-F2
- **Why deferred**: Reporting refinement. v0.1 ships single-numerator coverage; v0.2 adds the `(tested / (total − mechanical_vacuous))` second numerator and audits the extractor's exclusion rate.

### D4 · Extractor calibration (`extractor_id, skill_genre`)
- **Driver**: TEST-ARCH-F2 follow-on
- **Why deferred**: Track B (clause extractor) is its own Tier-2 judge. Calibrating it properly requires a labeled skill corpus we don't yet have. v0.1 uses uncalibrated extraction with `semantic_vacuous_pending_review` sentinel; v0.2 adds extractor calibration once enough skills are imported.

---

## C — Open value decisions (user owns)

### C1 · Tie encoding
- **Default (provisional)**: half-update (pseudo-Bernoulli) per §A10
- **Alternative**: drop ties — preserves Beta-Binomial conjugacy exactly, simpler reporting; cost is discarding any verdict where the judge said "tie"
- **Recommendation to flip**: if Tier-2 judges show high tie rates (>15%) on real calibration sets, dropping ties wastes data; half-update is correct. If tie rates are low (<5%), drop ties for cleaner math.

---

## PRD amendments required before v1.1 lock

These are the concrete edits Phase 3 expects. Track B may produce a PR that applies them all.

| § | Edit | Source |
|---|---|---|
| §1 | Drop "manufactured primitives"; add prior-art citations | D2, EVAL-F1 |
| §3.1 | Add pairwise-only reconciliation clause | A5, EVAL-F5 |
| §3.4 / new §7a | Falsifying Case Schema spec | A15, TEST-ARCH-F1 |
| §5 Tier 2 | Position-swap mandatory; pairwise-only mode | A5, A6 |
| §5 Tier 3 | Mark DEFERRED to v0.2 | D1 |
| §6 | Admissibility includes position-consistency + length-control gates | A6, A7 |
| §7 | Split vacuity mechanical/semantic; extractor calibration future | A16, D4 |
| §11 | Watch ALL metric_library axes; threshold = `k·σ(Null)`; `observed_unclaimed_delta` | A11 |
| §12 | Demote Assertion Density + Unsupported Claim Ratio + Compliance Proxy + raw Hedge Index | A14 |
| §13 | Name metric, thresholds (≥0.7 pairwise, ≥0.8 position-consistency, κ secondary), N≥50 | A7 |
| §14 | N_min=5 floor; sequential stopping (`N_min=8, N_inc=4, N_max=40`); hierarchical Beta-Binomial; tie-encoding note | A8, A9, A10 |
| §15 | UNMEASURED sub-reasons; PASSED requires frozen falsifying case | A17, A15 |
| §17 | Append-only via triggers; two-DB partition; cost ledger | A1, A2, A12 |
| §17 | Schema migration runner with SHA-256 ledger | A4 |
| §18 | `run` defaults dry-run; `--execute`, `--max-usd`, `--daily-cap` | A12 |
| §19 | Add criterion #7: "No clause may be reported PASSED without frozen falsifying case at current metric_library version" | A15 |

---

## Lineage / antecedents

The discipline embedded above is epistemically isomorphic to the `ai-slop-sentinel` skill (now global at `~/.claude/skills/ai-slop-sentinel/`):

- *"Every flag cites the watch + source"* ↔ §6 verdicts snapshot `calibration_event_id`
- *"Re-validation, not accretion" + freshness gate* ↔ §13 `expires_at` 90-day default
- *"Graduate ONLY proven-stable structural patterns"* ↔ §A14 `mechanical_validity_test_passed` gate
- *"Fresh context, never the author's own session"* ↔ §A6 position-swap
- *"Critical / Important / Minor"* ↔ council BLOCKER / MAJOR / MINOR / OBSERVATION
- *"Watch is append-only, dated, model-era-tagged"* ↔ frozen suite + metric_version snapshot

The sentinel is hand-curated review; the harness is automated measurement; the discipline is identical.

---

## Verified external citations

URLs and arXiv IDs the council seats produced were verified except where seat declared `external-citations-verified=NO` (TEST-ARCH only — relied on well-known canonical literature names).

- Prompt caching pricing & breakpoints: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
- Anthropic API pricing: https://platform.claude.com/docs/en/docs/about-claude/pricing
- SQLite triggers: https://www.sqlite.org/lang_createtrigger.html
- SQLite WAL: https://www.sqlite.org/wal.html
- SQLite pragmas: https://www.sqlite.org/pragma.html
- Sclar et al., FormatSpread: arXiv:2310.11324
- Longpre et al., FLAN Collection: arXiv:2301.13688
- Zheng et al., MT-Bench (pairwise vs scalar): arXiv:2306.05685
- Liu et al., G-Eval: arXiv:2303.16634 (cited as the §3.1-forbidden pattern)
- Length-Controlled AlpacaEval: arXiv:2404.04475
- Position bias in pairwise judges: arXiv:2406.07791
- Judge's Verdict (κ + correlation prefilter): arXiv:2510.09738
- Hedge detection origins: Ganter & Strube ACL 2009; arXiv:2405.13319
- Benjamini-Hochberg FDR: https://rss.onlinelibrary.wiley.com/doi/10.1111/j.2517-6161.1995.tb02031.x
- Lan-DeMets alpha-spending: https://onlinelibrary.wiley.com/doi/abs/10.1002/sim.4780131308
- Peng et al., Copilot RCT: arXiv:2302.06590

---

*End of synthesis. See `PLAN.md` for the Phase-3 execution plan derived from this document.*

---

## Appendix A — Supply-chain audit (Phase 1.1, 2026-06-03)

Trail of Bits `supply-chain-risk-auditor` skill executed against production + dev deps. Full report at `.supply-chain-risk-auditor/results.md`. Decision: **PROCEED-WITH-MITIGATIONS**.

### Verified MAJOR findings

- **anthropic** — Two medium CVEs published 2026-03-31 against the optional Memory Tool surface:
  - `GHSA-q5f5-3gjm-7mfm` / `CVE-2026-34450` — Insecure Default File Permissions
  - `GHSA-w828-4qhx-vxx3` / `CVE-2026-34452` — Path Validation Race / Sandbox Escape
  - Both patched in `anthropic 0.87.0` (verified via `gh api repos/anthropics/anthropic-sdk-python/security-advisories`). Installed version 0.105.2 (released 2026-05-29) is well past the patch line.
  - **Mitigation applied**: `pyproject.toml` pin raised from `>=0.39` to `>=0.87`. Memory Tool surface is not used by the harness.

- **pydantic** — Deserialization is a structurally high-risk feature.
  - **Mitigation rule**: Anthropic API responses validated through Pydantic with `strict=True`. Never instantiate arbitrary types from untrusted input. Track C + Track E enforce.

### MINOR observations (logged, not blocking)

- **rich** — Solo maintainer (willmcgugan, well-known prolific contributor). Bus-factor / credential-compromise risk. **Constraint**: terminal output only; no business logic depends on it.
- **pytest / pytest-cov / pytest-xdist / hypothesis** — No SECURITY.md at repo or pytest-dev org level. Dev-only; blast radius bounded to local test execution. Acceptable for v0.1.
- **pytest-xdist** — Near-single-maintainer (RonnyPfannschmidt + bots). Kept for property-based test parallelism; small enough to drop later if needed.

### Deferred mitigations

- **pip-audit in CI**: defer until CI exists (no CI workflows yet; out of v0.1 scope per §D).
- **Quarterly re-audit + major-version-bump re-audit**: documented as ongoing discipline; first re-audit due 2026-09-03 or at the next `anthropic` major bump (whichever first).

### Citation verification

Per `subagent-research-reliability` discipline, the subagent's CVE-specific claims were independently verified by direct `gh api` queries before mitigations were applied. CVE IDs, patch versions, and publication dates above are from primary source.
