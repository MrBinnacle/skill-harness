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

#### A4 · Trust partition (Phase 1.5 mirror of SECURITY F5 / A23)

The append-only triggers + SHA-256 ledger defend against *in-process* unauthorized writes (developer error, SQL-injection-style mutation, library bug). They do **not** defend against an attacker who replaces the entire `evidence.db` file at the filesystem layer — the SHA ledger checks file contents against an SHA recorded *inside* the same DB, so a whole-DB substitution supplies both the data and the baseline-it-is-checked-against. v0.1 assumes filesystem integrity (local-trust); file-replacement detection is deferred to v0.2 (candidate D6 `db_identity`).

The runtime/evidence partition is itself a security boundary: `evidence.db` is append-only, audited, load-bearing; `runtime.db` is mutable by design. Compromise of `runtime.db` (`current_calibration` rewrite is the load-bearing target) affects only FUTURE verdicts because past verdicts have already snapshotted `admissibility_state` at write time and `oracle_verdicts` is append-only (A3 + A1). **Symmetry between the two DBs is not a design goal.** The single exception is `runtime.schema_migrations`, framed as META not DOMAIN — its append-only triggers (A21) live on the runtime side because the ledger's tamper-evidence is independent of operational mutability. See `SECURITY.md` "Threat model (informal)" for the canonical statement; this is the architectural-log mirror.

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

## C — Open value decisions

> **Ownership note (2026-06-05):** Not every item here is the user's to decide. C1 (tie encoding) is a genuine scope/reporting trade and is data-blocked. C2 was mis-filed as "user owns" — it is a calibration-*methodology* question and routes to the **STAT seat** (con) cross-checked by **COST** (pro) at the Pre-Track-D council, per `feedback-route-to-most-expert`. The user's lane is *what claim v0.1 should make*; admissibility validity is the SME seat's lane.

### C1 · Tie encoding
- **Default (provisional)**: half-update (pseudo-Bernoulli) per §A10
- **Alternative**: drop ties — preserves Beta-Binomial conjugacy exactly, simpler reporting; cost is discarding any verdict where the judge said "tie"
- **Recommendation to flip**: if Tier-2 judges show high tie rates (>15%) on real calibration sets, dropping ties wastes data; half-update is correct. If tie rates are low (<5%), drop ties for cleaner math.
- **Dispositionable when**: Track C calibration_events rows accumulate (need `n_tie/N` and `judge_n_tie/N_calls` per A37). C1 cannot be resolved until at least one (judge_id, axis) calibration has landed.

### C2 · Operator-self-label calibration tier (new, Pre-Track-C 2026-06-05)
- **Question**: Should v0.1 admit `state = "operator_self_labeled"` as a bootstrap-grade calibration tier (where the operator running `calibrate` provides the labels themselves), or refuse all calibration that isn't externally human-labeled per `(judge_id, axis)`?
- **Default if not flipped**: REFUSE — no `operator_self_labeled` tier. Track C ships requiring user-provided externally-labeled JSONL.
- **Pro (COST framing)**: v0.1 ships testable; operator can calibrate against their own preferences without external rater infrastructure.
- **Con (STAT framing)**: Methodologically suspect — judge calibrating against operator who'll be running the harness against operator's skills creates a closed loop. "κ on a self-labeled set is structurally κ-with-yourself ≈ 1.0."
- **If flipped**: explicit `state = "operator_self_labeled"` flag; downstream aggregation MUST refuse to enter operator-self-labeled verdicts into the Beta-Binomial pool; admin UI surfaces flag prominently; re-calibration cadence shortened (e.g., 30 days vs A7's 90).
- **Surfaced by**: Pre-Track-C council (full framing in `docs/council-fires/2026-06-05-pre-track-c/synthesis.md`).
- **Routing (2026-06-05)**: STAT seat decides at the Pre-Track-D council, countered by COST. **Not a user values decision** — it is calibration-methodology. SME prior to pressure-test: **HOLD REFUSE for v0.1**, on *independence-of-ground-truth* grounds (per `llm-judge-calibration` Disciplines 3–6: κ and the N≥50 / 0.7-0.8-0.65-0.4 thresholds are only meaningful when the labeling rater is independent of the evaluated artifact; the operator labeling pairs while owning the skills under test collapses that independence). Note the con's original "κ-with-yourself ≈ 1.0" phrasing is imprecise — judge and operator are distinct raters, so κ≠1.0; the real defect is that a self-labeled calibration can only ever certify "agrees with this operator," never an axis-level claim. The flip's own guardrail (downstream pool must reject self-labeled verdicts) concedes the verdicts aren't evidence-grade.

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
| §17 | Trust partition: evidence.db append-only/audited/load-bearing; runtime.db mutable by design | A23, SECURITY-F5 |
| §17 | PRAGMA scope: `open_db()` is the sanctioned connection entry; FK enforcement is connection-scoped | A23, SECURITY-F5 |
| §17 | `PRAGMA synchronous = FULL` for evidence; `NORMAL` for runtime | A22, RELIABILITY-F5 |
| §17a (new) | Threat-model section: filesystem-substitution boundary; tamper-evidence is in-process, not file-replacement-resistant | A23, SECURITY-F5 |

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

---

## Appendix B — Phase 1.5 pre-Track-A council fire (2026-06-04)

Four-seat fire (TEST-ARCH + SCHEMA + RELIABILITY + SECURITY) dispositioned the four storage-layer fragility clusters surfaced by `audit-context-building`. All seats returned `STATUS: BLOCKER-FOUND`. Raw seat outputs + synthesis archived at `docs/council-fires/2026-06-04-pre-track-a-storage/`.

### A18 · Migration apply atomicity via explicit transaction
- **Drivers**: SCHEMA-F1, RELIABILITY-F1, TEST-ARCH-F1, SECURITY-F1, M1
- **Decision**: Replace `with conn:` + `executescript` (which is a no-op for atomicity under `isolation_level=None`) with explicit `conn.execute("BEGIN IMMEDIATE")` + statement-by-statement execution + `INSERT INTO schema_migrations` + `conn.execute("COMMIT")`; `conn.execute("ROLLBACK")` on exception. Define typed `BootstrapError` / `MigrationApplyError`. Emit structured log lines (`migration_applying`, `migration_applied`, `migration_failed`). Add a smoke test for the half-applied recovery path.
- **Status**: PENDING — implement in Phase 1.5a before Track A.
- **Sources verified**: Python sqlite3 docs (https://docs.python.org/3/library/sqlite3.html); SQLite transaction docs (https://www.sqlite.org/lang_transaction.html); SQLite `executescript` semantics (https://www.sqlite.org/c3ref/exec.html).

### A19 · `open_evidence` / `open_runtime` raise on empty migration discovery
- **Drivers**: TEST-ARCH-F2, RELIABILITY-F2, SECURITY-F2, SCHEMA-F2, M2
- **Decision**: When `discover()` returns `[]` from a configured migrations directory, `open_evidence` and `open_runtime` MUST raise `BootstrapError` (or `MigrationDiscoveryError`) naming the searched directory + resolved `REPO_ROOT` + `__file__`. Silent zero-migration is a vacuity hazard (per PRD §7) AND a forgeable "no findings" report (SECURITY's framing). Invert the integration assertion: `open_evidence()` never returns a usable-looking-but-empty DB. Long-term `importlib.resources` packaging deferred to D8.
- **Status**: PENDING — implement in Phase 1.5a before Track A.

### A20 · `runs` immutability is column-scoped, not row-scoped
- **Drivers**: SCHEMA-F3, TEST-ARCH-F3, RELIABILITY-F3, M3
- **Decision** (load-bearing intent statement): the intent IS column-immutable, NOT row-immutable. The current trigger (`migrations/evidence/0001_initial.sql:203-205`) contradicts its own comment + name + error message; that is implementation drift. Replace with two named-column triggers per SCHEMA's proposal:
  ```sql
  CREATE TRIGGER runs_completed_at_set_once BEFORE UPDATE OF completed_at ON runs
      WHEN OLD.completed_at IS NOT NULL
      BEGIN SELECT RAISE(ABORT, 'runs.completed_at is immutable once set'); END;
  CREATE TRIGGER runs_immutable_columns BEFORE UPDATE OF run_id, skill_id, run_kind, config_json, started_at ON runs
      BEGIN SELECT RAISE(ABORT, 'append_only_violation: runs immutable columns'); END;
  ```
- **Status**: PENDING — implement via new migration `migrations/evidence/0002_runs_trigger_split.sql` in Phase 1.5a. SQLite does not support direct trigger replacement in this case; the new migration DROPs the old trigger and creates the two named-column triggers. **Note**: `DROP TRIGGER` is the only legitimate operation on the migrations side that does NOT violate append-only on data — it modifies meta-schema, which is governed by the SHA-256 ledger (A4), not by row-level triggers.

### A21 · `runtime.schema_migrations` triggered append-only (META vs DOMAIN framing)
- **Drivers**: TEST-ARCH-F4, SECURITY-F4, RELIABILITY-F4, M4
- **Council disposition**: 3 seats (TEST-ARCH + SECURITY + RELIABILITY) framed `schema_migrations` as a META table whose append-only nature is independent of the runtime/evidence partition (A2). SCHEMA dissented (treated it as intentional partition asymmetry). The 3-vs-1 vote on cross-talk-aware grounds adopts the META framing. SCHEMA's "uniformity" concern is documented but does not outweigh the tamper-evidence integrity loss.
- **Decision**: Add `BEFORE UPDATE` and `BEFORE DELETE` triggers to `runtime.schema_migrations` only (NOT to other runtime tables — `run_progress`, `current_calibration`, `cost_ledger`, `run_budget`, `skill_imports_staging` remain mutable per A2). Add a smoke test mirroring `test_evidence_append_only_skills`.
- **SCHEMA's load-bearing dissent (backfilled 2026-06-04 per `lossless-orchestrator-infrastructure` discipline)**: SCHEMA argued the partition asymmetry between `evidence.db` (append-only) and `runtime.db` (mutable) is itself the load-bearing design property. Adding append-only triggers to ANY runtime table — even one framed as META — breaks partition uniformity. The "META vs DOMAIN" distinction is convenient framing, but SCHEMA's lens is that the partition itself is the contract, and any append-only structure on the runtime side is a contract violation regardless of how it is justified. The dissent was overridden on tamper-evidence-integrity grounds, but the framing is on record.
- **Flip condition**: would re-evaluate IF (a) a legitimate operational use case for mutating `schema_migrations` rows emerges in v0.2+ (schema rollback for failed migrations, retention GC, test-suite reset of the ledger between runs), OR (b) the runtime partition's uniformity becomes load-bearing for a feature that must extend uniformly to `schema_migrations` (e.g., a "wipe runtime, recreate from evidence" recovery flow that needs `schema_migrations` to be wipeable too), OR (c) the META vs DOMAIN distinction turns out empirically misleading — e.g., `schema_migrations` ends up coupled to operational sequencing in ways A21 did not anticipate.
- **Status**: REALIZED — migration `migrations/runtime/0002_schema_migrations_triggers.sql` applied in Phase 1.5a (commit `97f73fd`). Backfill of the flip condition is a documentation amendment only; it does NOT reopen the decision.

### A22 · `synchronous = FULL` for evidence; `NORMAL` for runtime
- **Drivers**: RELIABILITY-F5
- **Decision**: `evidence.db` opens with `PRAGMA synchronous = FULL` (audit-trail invariant). `runtime.db` keeps `PRAGMA synchronous = NORMAL` (in-flight state, tolerant of replay-on-restart). Requires `open_db()` to accept a pragma-set parameter or splitting into `open_evidence_raw()` / `open_runtime_raw()`. Document the asymmetry in CLAUDE.md "Evidence model" section.
- **Status**: PENDING — implement in Phase 1.5a alongside A18.
- **Sources verified**: SQLite WAL durability docs (https://www.sqlite.org/wal.html); SQLite PRAGMA semantics (https://www.sqlite.org/pragma.html#pragma_synchronous).

### A23 · Trust partition + tamper-evidence threat model documented
- **Drivers**: SECURITY-F5 (cross-cutting; documentation-debt)
- **Decision**: Update `SECURITY.md` "Threat model" section with three clauses:
  1. **Trust partition**: `evidence.db` is append-only, audited, load-bearing. `runtime.db` is mutable by design. Compromise of runtime.db affects only FUTURE evidence rows via `current_calibration` snapshot at verdict write time (bounded by A3). Symmetry between the two databases is NOT a design goal.
  2. **Filesystem substitution boundary**: append-only triggers + SHA-256 migration ledger defend against in-process unauthorized writes. They do NOT defend against an attacker who replaces the entire DB file at the filesystem layer. v0.1 threat model assumes filesystem integrity (local-trust).
  3. **PRAGMA scope**: connections MUST go through `skill_harness.storage.migrations.open_db()`. Direct `sqlite3.connect()` bypasses connection-scoped pragmas including `foreign_keys = ON`.
- Mirror clauses (1) + (2) as a "Trust partition" subsection under §A4 above.
- **Status**: PENDING — documentation only; land in Phase 1.5b.

---

### Deferred to v0.2 (Phase 1.5 fire additions)

#### D5 · `evidence.runs.terminal_state` enum column
- **Driver**: RELIABILITY-F3 expansion
- **Why deferred**: meaningful expansion of the run state machine but not blocking for Track A. Adding `terminal_state TEXT CHECK (terminal_state IN ('completed','failed','aborted_budget','crashed_reconciled'))` would clarify "why did the run end" as admissible evidence rather than implicit, and would unblock a crashed-run reconciler. v0.2 follow-up migration; preserves A1 via single-shot trigger on the new column.

#### D6 · `db_identity` row + cross-DB identity check
- **Driver**: RELIABILITY-F4 sub-finding
- **Why deferred**: defense against silent runtime-DB restore-from-backup (e.g., post-disk-failure). v0.2 adds a single-row `db_identity` table holding a UUID generated at first open; cross-references on subsequent opens detect identity change. Necessary for production deployments; not blocking for v0.1 single-operator local-trust model.

#### D7 · `skill audit` CLI command for cross-DB calibration audit
- **Driver**: SECURITY-F4 sub-finding
- **Why deferred**: A3's bound (calibration rewrites affect only future verdicts) is the load-bearing guarantee. Detection of a lying `current_calibration` requires an auditor to verify that every `oracle_verdicts.calibration_event_id` resolves to a `calibration_events` row whose `validated_at` ≤ verdict's `written_at` AND whose `expires_at` > verdict's `written_at`. v0.2 ships `skill audit` implementing this check. v0.1 documents the audit recipe in SECURITY.md without implementing the command.

#### D8 · `importlib.resources` migration packaging
- **Driver**: M2 long-term fix
- **Why deferred**: A19's runtime assertion (raise on empty discovery) makes the failure loud immediately; the structural fix is to ship migrations as package data via `importlib.resources.files("skill_harness").joinpath("storage/migrations/evidence")`. v0.2 refactor; eliminates `parents[3]` brittleness entirely.

### Cross-talk validation note

7 of 8 cross-seat predictions were accurate. The substantive miss (SCHEMA + TEST-ARCH expecting SECURITY to BLOCKER M4) is healthy disagreement-discovery: SECURITY's explicit A3-bound is a sharper threat-model statement than other seats anticipated. The council pattern surfaced this; synthesis adopts SECURITY's framing (MAJOR not BLOCKER) for F4 while still requiring the trigger fix.

---

## Appendix C — Pre-Track-A implementation council (2026-06-04)

Third council fire. PLAN.md row 2 of "Named council fire points" (Storage-touching change template). Distinct from the Phase 1.5 fire (Appendix B) which dispositioned audit-context fragility clusters; THIS fire dispositions Track A's IMPLEMENTATION DESIGN before code lands. Archive: `docs/council-fires/2026-06-04-pre-track-a-impl/`.

Seats: SCHEMA + RELIABILITY + SECURITY + TEST-ARCH (4 seats). All returned `STATUS: BLOCKER-FOUND` across the 7 design questions. Synthesized: 5 BLOCKERs (Q2, Q3, Q4, Q6, Q7), 2 MAJORs (Q1, Q5). Substantive disagreement on Q2 ordering (SECURITY runtime-first vs. SCHEMA + RELIABILITY + TEST-ARCH evidence-first) resolved 3-vs-1 on cross-talk-aware grounds (PLAN Track D's pre-call budget check moots SECURITY's budget-bypass premise).

### A24 · Repository pattern shape
- **Drivers**: all 4 seats (Q1)
- **Decision**: per-table modules under `src/skill_harness/storage/repositories/evidence/` (10 modules) and `src/skill_harness/storage/repositories/runtime/` (5 modules). **Functional API only** — no classes (closes subclass-override escape hatches; closes hidden-per-instance-state hazard). Pydantic write-models in `src/skill_harness/storage/models.py` with `model_config = ConfigDict(strict=True, extra='forbid', frozen=True)`. Per-model `field_validator` rejects NUL bytes + non-printable C0 controls except `\t\n\r`; configurable size caps (default `output_text` 256 KB, `clause_text` 64 KB) owned by the Python validator (NOT the DB-layer CHECK). Evidence repos export only `insert_*`/`get_*`/`select_*`/`list_*` — no `update_*`/`delete_*`/`set_*`/`patch_*`/`modify_*`/`remove_*` symbols. **AST-walker test** `tests/test_evidence_repo_surface.py` is the falsifying-case enforcement: regex scan over `repositories/evidence/*.py` rejects matching function names. Defense-in-depth over A1's SQL-layer triggers.
- **Status**: PENDING Track A implementation.

### A25 · Dual-DB transaction primitive — evidence-first ordering
- **Drivers**: SCHEMA (BLOCKER, Q2) + RELIABILITY + TEST-ARCH (MAJOR, evidence-first); SECURITY dissented MAJOR (runtime-first)
- **Decision**: writes that span both DBs (e.g., verdict + cost ledger, run-start + budget, calibration_event + current_calibration pointer) use `src/skill_harness/storage/dual_write.py::write_<op>_with_<companion>(evidence_conn, runtime_conn, ...)`. Sequence: `BEGIN IMMEDIATE` on evidence → INSERT evidence → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT runtime → COMMIT runtime. On runtime COMMIT failure, log structured `dual_write_partial` event; the gap is reconciler-eligible (do NOT auto-insert phantom runtime row). **`ATTACH DATABASE` is forbidden in production code paths** (attached DBs share journal-mode/synchronous settings, defeating A22's FULL/NORMAL split); ATTACH allowed READ-ONLY in future `skill audit` (D7). SECURITY's runtime-first counter-framing recorded as load-bearing dissent (would re-evaluate if post-call accounting becomes the budget oracle or cost_ledger becomes part of admissibility). Cited as moot in v0.1 because PLAN Track D specifies pre-call budget cap check.
- **Status**: PENDING Track A implementation.

### A26 · Single-writer mechanism — SQLite native, no in-process queue
- **Drivers**: RELIABILITY (BLOCKER, Q3); SCHEMA + TEST-ARCH MAJOR; SECURITY MINOR
- **Decision**: v0.1 single-writer mechanism is **SQLite `BEGIN IMMEDIATE` + 5-second `busy_timeout`** (already set in `migrations.py:212`). NO `queue.Queue` + writer thread. Application discipline: writes from a single thread per DB connection. Documented in `storage/__init__.py` module docstring. `threading.Lock` per `Connection` adopted as optional belt-and-braces ONLY if used as a context-manager wrapper around `BEGIN IMMEDIATE` (not as a queue mechanism). Track D's sampling loop is single-threaded in v0.1; subprocess workers deferred to D11. `tests/test_concurrent_writers_serialize.py` proves the SQLite-level lock + `busy_timeout` behavior under 2-thread interleave.
- **Status**: PENDING Track A documentation + test.

### A27 · Property-based test design — two-property + separate crash-injection family
- **Drivers**: TEST-ARCH (BLOCKER owned, Q4) + others MAJOR
- **Decision**: `tests/property/test_evidence_append_only.py` with two properties:
  - **P1** (all tables except `runs`): for all valid `r` drawn from `row_strategy(table)`, the sequence `[INSERT r; UPDATE table SET <any_col>=<any_val> WHERE pk=r.pk]` raises `sqlite3.IntegrityError` matching `r'append_only_violation: ' + table`. DELETE analogue.
  - **P2** (runs-specific carve-out per A20): for all valid `r`, INSERT then UPDATE of `skill_id`/`run_kind`/`config_json`/`started_at` aborts; INSERT then single UPDATE of `completed_at` succeeds; INSERT then second UPDATE of `completed_at` aborts.

  FK closure via schema introspection (`PRAGMA foreign_key_list`), NOT hand-coded. `@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])`. Crash injection lives in a separate test family `tests/test_crash_recovery.py` (RELIABILITY framing — Hypothesis shrinking fails with side-effects-across-rules). SECURITY's adversarial corpus (`adversarial_text()` exporting NUL/control/oversized) imports into both families. `RuleBasedStateMachine` reserved for D13 (cross-write consistency property).
- **Status**: PENDING Track A implementation.

### A28 · Connection lifecycle — long-lived + structural enforcement + savepoint fixture
- **Drivers**: SECURITY + TEST-ARCH (MAJOR, Q5); SCHEMA + RELIABILITY MINOR
- **Decision**: long-lived per-process connection. `open_evidence`/`open_runtime` return a `Connection`; caller owns lifecycle. Repos take a `Connection` parameter (do NOT construct one). `src/skill_harness/storage/context.py::StorageContext` dataclass + `__enter__`/`__exit__` for CLI use. `src/skill_harness/storage/transaction.py::writer_transaction(conn) -> Iterator[None]` context manager (`BEGIN IMMEDIATE` on enter, COMMIT on clean exit, ROLLBACK on exception via `contextlib.suppress(sqlite3.Error)`). **Structural enforcement of A23 PRAGMA scope**: pre-commit grep ban `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` MUST be empty (upgrades A23's "PR review" to CI-enforced). **Hypothesis savepoint fixture** (TEST-ARCH framing): `evidence_db_savepoint` wraps each `@given` example in `SAVEPOINT hyp_example; ...; ROLLBACK TO hyp_example;`. Property tests use this; smoke tests use the existing `evidence_db`. `tests/test_hypothesis_savepoint_isolation` verifies isolation. Plus smoke test asserting `PRAGMA foreign_keys` returns 1 on a freshly-opened repo connection.
- **Status**: PENDING Track A implementation.

### A29 · Admissibility filter — SQL VIEW + repo-function wrappers
- **Drivers**: SCHEMA + SECURITY + TEST-ARCH (BLOCKER, Q6); RELIABILITY MAJOR
- **Decision**: defense-in-depth on both layers. New migration `migrations/evidence/0003_admissible_verdicts_view.sql` creates a SQL VIEW `admissible_verdicts` that selects from `oracle_verdicts` where `admissibility_state = 'admissible'` AND no matching row exists in `confound_events` with `delta_kind = 'confound_flagged'` for the same `(run_id, primary_clause_id)`. The VIEW is the structural defense (ad-hoc `sqlite3` queries inherit safe defaults). Python repo functions: `get_admissible_verdicts(conn, run_id)` reads the VIEW; `audit_all_verdicts(conn, run_id)` reads raw `oracle_verdicts`. Names are load-bearing — `_for_audit` makes the wrong-call obvious. CI grep ban: any code outside `src/skill_harness/audit/` referencing raw `oracle_verdicts` in `SELECT` fails CI. Tests: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`. **Falsifying-case test for A3 promoted from D7 audit territory into Track A**: insert verdict; flip `runtime.current_calibration` post-write; assert verdict's `admissibility_state` is unchanged (proves write-time snapshot survives runtime tampering). Confound JOIN directionality (`primary_clause_id` vs `affected_clause_id`) flagged for EVAL-RESEARCH confirmation at next Track-D-prep council fire.
- **Status**: PENDING Track A implementation + new migration.

### A30 · Migration sequencing — per-track ranges + discover() duplicate-version guard + CODEOWNERS
- **Drivers**: RELIABILITY (BLOCKER, Q7); SCHEMA + SECURITY + TEST-ARCH MAJOR
- **Decision**: per-track migration number ranges (PLAN.md amendment):
  - Track A: `0001-0099` (storage primitives)
  - Track B: `0100-0199` (extractor)
  - Track C: `0200-0299` (oracle / calibration)
  - Track D: `0300-0399` (ablation runner)
  - Track E: `0400-0499` (aggregation / status)

  `discover()` raises `BootstrapError` on duplicate version numbers (smoke test `test_discover_rejects_duplicate_versions`). `migrations/README.md` documents the reservation. `.github/CODEOWNERS` requires SCHEMA + SECURITY seat sign-off on any PR touching `migrations/*` (upgrades PLAN's "Pre-merge council fire" from discretionary to mechanism).
- **Status**: PENDING Track A implementation + `migrations/README.md` + `.github/CODEOWNERS`.

---

### Deferred to v0.2 (Phase 2-entry fire additions)

#### D9 · `current_calibration` rewrite + verdict admissibility falsifying-case
- **Driver**: TEST-ARCH (Q6 cross-talk)
- **Status**: **NOT DEFERRED**. Adopted into Track A scope per A29 (the falsifying-case test for A3 write-time-snapshot lives in Track A, not Track E).

#### D10 · `db_identity` row + cross-DB identity check
- **Driver**: SECURITY Phase 1.5 F2 reinforced; carry-forward from D6
- **Why deferred**: defense against silent runtime-DB restore-from-backup. Necessary for production but not v0.1 local-trust.

#### D11 · Multi-process single-writer (subprocess workers)
- **Driver**: RELIABILITY (Q3 future-work)
- **Why deferred**: Track D in v0.1 is single-threaded sampling; subprocess workers require `queue.Queue` + writer thread OR shared FIFO + per-subprocess connection. v0.2 throughput optimization.

#### D12 · Denormalized `confound_flagged` boolean on `oracle_verdicts`
- **Driver**: SCHEMA + RELIABILITY (Q6 fallback)
- **Why deferred**: trigger ONLY if A29's VIEW EXISTS subquery becomes performance-pathological at Track E scale. v0.2 perf migration.

#### D13 · `RuleBasedStateMachine` consistency-across-writes property
- **Driver**: SCHEMA + TEST-ARCH (Q4 future-work)
- **Why deferred**: A27 covers per-INSERT append-only invariant; cross-write consistency (verdict-vs-cost-ledger reconciler test, calibration-vs-verdict snapshot test) is a separate property family.

#### D14 · DB-layer CHECK on `output_text`/`clause_text` size
- **Driver**: SECURITY (Q1 fallback)
- **Why deferred**: trigger IF Python-layer cap proves insufficient under real-world adversarial input. v0.2 hardening migration.

### PRD v1.1 amendments queued (this fire)

In addition to the 20 amendments queued before this fire (16 original + 4 Phase 1.5):

| Section | Amendment | Driver |
|---|---|---|
| §17 | Declare per-track migration number ranges (A 0001-0099, B 0100-0199, C 0200-0299, D 0300-0399, E 0400-0499) | A30 |
| §17 | Declare `admissible_verdicts` SQL VIEW as canonical aggregation surface; raw `oracle_verdicts` access restricted to `audit/` module | A29 |
| §17 | Declare SQLite `BEGIN IMMEDIATE` + 5s `busy_timeout` as v0.1 writer-exclusion mechanism (no in-process queue.Queue) | A26 |
| §17 | Declare dual-DB write ordering: evidence-first; runtime gaps reconcilable from evidence; ATTACH forbidden in production paths | A25 |
| §17 | Declare PRAGMA scope enforcement as STRUCTURAL (pre-commit grep ban on raw `sqlite3.connect` outside `migrations.py`), upgrading A23's "PR review" | A28 |
| §17 | Declare repository surface restriction (evidence repos export `insert_*`/`get_*`/`select_*` only; AST-walker test) as defense-in-depth over A1 triggers | A24 |

**Total PRD v1.1 amendments queued: 26.**

### Cross-talk validation note (this fire)

Cross-prediction quality: 6/12 prediction targets landed, 4 missed, 2 inverted. Down from 7/8 in Phase 1.5 fire — lower lens distinctness this round (RELIABILITY + TEST-ARCH overlap on test discipline; SCHEMA + RELIABILITY overlap on durability framing). For the next storage-touching fire, consider firing only 3 seats (drop one of the overlapping pair) OR sharpen the seat briefs to emphasize lens distinctness.

The substantive cross-talk yield was the convergent finding combining RELIABILITY's "separate test families" + TEST-ARCH's "savepoint fixture" + SECURITY's "structural pre-commit grep enforcement" = a coherent test infrastructure shape that no single seat would have produced. Adopted into A27 + A28.

Substantive disagreement on Q2 ordering surfaced cleanly — the orchestrator resolved by citing PRD Track D's pre-call cap check (moots SECURITY's premise without dismissing the framing). That's exactly the cross-talk-dispatch use case.

---

## Appendix D — Pre-Track-C council fire (2026-06-05)

**Trigger**: PLAN.md row 3 of "Named council fire points" — gates Track C dispatch.
**Seats**: EVAL-RESEARCH + SECURITY + COST + STAT (4 seats, Custom template per PLAN).
**Model**: Opus 4.7 per CLAUDE.md model pinning ("council fires").
**Archive**: `docs/council-fires/2026-06-05-pre-track-c/` (4 raw seat outputs + README + synthesis).
**Outcome**: all 4 seats `STATUS: BLOCKER-FOUND`. 6 BLOCKERs + 2 MAJORs synthesized (highest-severity per Q).

### Question disposition summary

| Q | EVAL-RESEARCH | SECURITY | COST | STAT | Synthesized | Adopted |
|---|---|---|---|---|---|---|
| Q1 (judge response shape) | MAJOR | BLOCKER | MAJOR | MAJOR | **BLOCKER** | **A31** |
| Q2 (position-swap test) | MAJOR | MAJOR | OBSERVATION | MAJOR | **MAJOR** | **A32** |
| Q3 (Tier-1 offline test) | MAJOR | BLOCKER | MINOR | MAJOR | **BLOCKER** | **A33** |
| Q4 (calibration JSONL) | MAJOR | MAJOR | MAJOR | BLOCKER | **BLOCKER** | **A34** |
| Q5 (length control) | MINOR | MAJOR | MINOR | MAJOR | **MAJOR** | **A35** |
| Q6 (calibrate projection) | MINOR | MAJOR | BLOCKER | MINOR | **BLOCKER** | **A36** |
| Q7 (CalibrationEventWrite extensions) | OBSERVATION | OBSERVATION | MAJOR | BLOCKER | **BLOCKER** | **A37** |
| Q8 (adversarial injection) | BLOCKER | BLOCKER | MINOR | MAJOR | **BLOCKER** | **A38** |

### Adopted decisions (A31–A38, summarized; full text in `docs/council-fires/2026-06-05-pre-track-c/synthesis.md`)

- **A31 · Tier-2 judge response shape**: tool_use with `strict: true`, `tool_choice` forced, `report_verdict({choice: enum[A,B,tie], rationale_brief})`. `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)`. Rationale field is audit-only; displayed in UI with `[untrusted model output]` prefix.
- **A32 · Position-swap test mechanics**: mock at SDK boundary (`anthropic.Anthropic.messages.create`); side-effect callable inspects prompt content; parameterized 9-cell (AB×BA) table; three minimum RED tests covering admissible / inadmissible-by-position-disagreement / tie-symmetry. EVAL's Track-C-abstraction framing recorded as MINOR dissent.
- **A33 · Tier-1 mechanical validity audit primitive**: `pytest-socket` + bit-equality. Module-level `pytestmark = pytest.mark.disable_socket`. `metric_versions.mechanical_validity_test_passed = 1` flips only on tests pass AND zero socket attempts. `PYTHONHASHSEED=0` discipline.
- **A34 · Calibration JSONL schema + three-tier admissibility**: 8-field strict JSONL (`pair_id, axis, prompt, response_a, response_b, human_preference, labeler_id, labeled_at`). State enum: `rejected` (N<50) / `conditional` (50≤N<100) / `calibrated` (N≥100). Cohen's κ on 3-class uses observed marginals (not 1/3 uniform). v0.1: NO starter set ships; user-provided. Operator-self-label is **value decision C2**.
- **A35 · Length-controlled scoring**: both prompt-level (max_tokens=80, "length should not influence" instruction) AND observation-time AlpacaEval-2 regression. `length_regression_coefficient` stored separately from `length_controlled_agreement`. Apply correction at verdict-write time (not at read). Store both `raw_observation` and `length_adjusted_observation`. EVAL's observation-only framing recorded as MINOR dissent.
- **A36 · Calibrate budget projection**: distinct formula from ablation (no per-pair cache; only system+schema prefix cacheable); shared envelope with ablation (per-run `--max-usd` $5 + shared daily `cost_ledger` cap $20). `_warmup_first_call()` serialization discipline before fan-out. Dry-run output includes STAT's `est_SE_pairwise_agreement` + `est_CI_95_width`. PRD §18 amendment queued.
- **A37 · `CalibrationEventWrite` extensions**: 10 new fields — STAT (`n_a, n_b, n_tie, judge_n_a, judge_n_b, judge_n_tie, length_regression_coefficient, chance_baseline`) + COST (`total_usd_spent, cost_ledger_run_id`). New migration `migrations/evidence/0200_calibration_event_extensions.sql` (first Track C migration per A30 range). SECURITY's A25 dissent does NOT become load-bearing for this write per SECURITY's own self-assessment.
- **A38 · Adversarial injection defense**: 7-layer concentric defense — tool_use schema (A31) + 8KB output truncation + XML-delimited sandboxing + meta-token regex short-circuit + position-swap (PARTIAL not complete per STAT correction) + null-baseline distributional check (STAT contribution, amortized with A11 confound pairs) + rationale UI prefix.

### Deferred to v0.2 (Phase 2-entry fire additions)

- **D15 · Multi-rater Krippendorff α calibration** — v0.1 single-rater baseline.
- **D16 · `--bootstrap-with-judge-labels` opt-in** — gated on C2 user disposition.
- **D17 · Sanitization pre-pass for adversarial calibration sets** — only if real-world injection rate > 1%.
- **D18 · Multi-axis calibration parallelization (`--parallel-axes`)** — 4× cache-write cost trade-off.
- **D19 · PII redaction policy for calibration JSONLs** — append-only constraint requires upstream policy.
- **D20 · Anthropic Batches API for calibration** — 50% cost saving, 24h SLA, v0.2.

### New value decision

- **C2 · Operator-self-label calibration tier** — surface to user. Default: refuse. See `synthesis.md` for full framing.

### PRD v1.1 amendments queued (this fire)

Total queue: **34** (26 prior + 8 from this fire):

| Section | Amendment | Driver |
|---|---|---|
| §18 / A12-(a) | Doctrine names `calibrate` alongside `run ablation` and `run evaluate-skill` as dry-run-default commands | A36 |
| §6/§7 | Calibration JSONL schema + three-tier admissibility states (`rejected`/`conditional`/`calibrated`) | A34 |
| §6 | Length-control both-sides + `length_regression_coefficient` storage + raw vs length-adjusted observation separation | A35 |
| §7 | `CalibrationEventWrite` extension fields (n_a/n_b/n_tie, judge_n_*, length_regression_coefficient, chance_baseline, total_usd_spent, cost_ledger_run_id) | A37 |
| §6 | Adversarial injection defense layers (tool_use + truncation + XML + meta-token + null-baseline + rationale UI prefix) | A38 |
| §12 | Tier-1 mechanical metric validity audit primitive (`pytest-socket` + bit-equality + `PYTHONHASHSEED=0`) | A33 |
| §5 Tier 2 | Judge `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)` — tool schema part of calibration scope | A31 |
| §5 Tier 2 | AlpacaEval-2 length-regression protocol named with citation (Dubois et al. 2404.04475) | A35 |

### Cross-talk validation (this fire)

- **Predictions landed**: 4+ (STAT predicted EVAL's calibration-vs-runtime separation; EVAL predicted STAT's tie-rate signal; COST predicted SEC's no-signed-JSONL restraint; SEC self-resolved own A25 dissent as non-load-bearing for this write).
- **Cross-derived findings**: 1 (Q8 content-anchored injection caveat from STAT's self-correction — STAT did the empirical work within their own response, the load-bearing move per `cross-talk-council-dispatch` skill).
- **Genuine disagreements surfaced**: Q7 (EVAL+SEC vs STAT+COST) — clean 2-vs-2 split by lens distinctness. Resolved by adopting BOTH extension sets (statistical + cost-provenance) since they are load-bearing for different downstream concerns.
- **Yield rate**: ~50% prediction landing rate consistent with prior fires; Track C surface is genuinely contested (8 questions, 4 distinct lenses, multiple legitimate positions).

---

## Appendix E — Pre-Track-D council (2026-06-06)

**Template:** Custom (PLAN row 4) — STAT + COST + RELIABILITY + OPERATOR-DX **+ EVAL-RESEARCH** (5th seat added by orchestrator because the 2026-06-06 landscape sweep injected eval-methodology questions the row-4 roster under-covers). Opus 4.7, parallel, read-only. Archive: `docs/council-fires/2026-06-06-pre-track-d/` (`synthesis.md` + `raw-outputs.md`). Trigger input: `docs/research/landscape-2026-06-06.md` (34-agent landscape + buildability sweep, no-twin verdict).

**Outcome:** 14 findings adopted (A39–A52); C2 resolved = REFUSE (SME verdict, not surfaced to user); A29 JOIN directionality confirmed correct (closes the open question); 3 landscape-report citation corrections logged; 1 PRD §1 positioning reframe queued for v1.1. Three BLOCKER-grade structural gaps in the current schema found and given concrete fixes. No unresolved BLOCKER → Track D cleared to dispatch.

### Adopted findings

- **A39 — Ablation operator = versioned neutral matched-length substitution, NOT deletion.** BLOCKER-grade. Deletion conflates a clause's axis-effect with prompt coherence/length/format loss; `verbosity` is one of our own Tier-1 axes so deletion self-contaminates it. Track D constructs a deterministic, byte-stable, matched-length semantically-null placeholder per (clause, version) — the deterministic layer builds it, never a model. Store `ablation_operator_id` + `implementation_hash` on every verdict at write-time (mirrors metric-version provenance). Resolves the A13-cache collision cost-favorably: a matched-length placeholder keeps the skill-prefix token count constant, stabilizing the cacheable prefix. Source: STAT-4, EVR-2, ODX-5 (BLOCKER), COST-5 (concur). Verified: arXiv:2409.09951 (operator choice changes measured importance; "3-9x" magnitude is landscape-sourced, not abstract-confirmed).
- **A40 — Sample idempotency + resumability.** BLOCKER. `samples` currently has no positional key → crash-resume double-counts → corrupts Beta-Binomial w/n → uncorrectable under append-only. New migration `0300` (Track D range) adds `sample_index INTEGER NOT NULL` + `UNIQUE(run_id, clause_id, condition, sample_index)`. Resume = set-difference of existing tuples vs the frozen plan in `runs.config_json`; per-call policy retry(transient)/skip(permanent 400)/abort(budget). Exit criterion: kill-at-1,732/4,000 resumes to exactly 4,000, never 4,001. Source: REL-2.
- **A41 — Cost re-derivable from evidence.** BLOCKER. `cost_ledger` write is a separate runtime txn after the evidence commit and swallows failure (`dual_write.py:91-105`) → crash between commits silently under-counts spend → budget over-run possible. Write per-call token/usd cost columns onto evidence rows inside the evidence transaction (`synchronous=FULL`); `cost_ledger` becomes a projection; reconciler back-fills any run whose sums disagree. Cost written from the actual response `usage`, never the projection. Source: REL-6, COST-3.
- **A42 — Budget cap check + reservation in ONE `writer_transaction(runtime)`.** Race-safe under A26 single-writer (`BEGIN IMMEDIATE` serializes read-modify-write); race only reappears at multi-process (D11). Pre-call gate uses worst-case projected next-call cost; post-call write reconciles to actual. Test mirrors `test_concurrent_writers_serialize.py`. Source: COST-2, REL-4.
- **A43 — Prompt-cache discipline (and Track C gap).** `system` rendered as typed blocks with `cache_control:{type:ephemeral}`; two breakpoints (end-of-system, end-of-skill-prefix); ablated-clause-last (confirmed correct — maximizes shared prefix across a clause's K conditions; reuse is K-local, not M-global); warmup-or-serialize so the cache-write lands before reads. **Track C's ~71% reuse is currently aspirational** — `judge.py` passes `system` as a bare string with no markers. Cache-marker assertion test (mock at SDK boundary per A32). Source: COST-1, COST-4.
- **A44 — Sequential stopping: N_max-without-stop = hard stop → `UNMEASURED(underpowered)`.** No batches past N_max. Record `stopping_reason ∈ {passed, failed, underpowered_nmax, budget_exhausted}` on the run config snapshot with the achieved posterior. Bayesian-posterior stop is not per-clause frequentist-alpha-inflating (the cross-clause concern is multiplicity → A49). Source: STAT-1.
- **A45 — Confound stays two-table; do NOT denormalize.** `confound_events` written once at detection in the same orchestration pass; exclusion via the `admissible_verdicts` VIEW at read-time. This is write-time-snapshot-COMPATIBLE — the invariant binds admissibility/calibration state, not confound geometry. Source: STAT-3, REL-5.
- **A46 — A29 JOIN directionality CONFIRMED CORRECT (closes A29 open question).** `primary_clause_id` = the ablated clause = the verdict being judged; `v.clause_id = ce.primary_clause_id` correctly taints N's own verdict. Do NOT also taint the affected clause M (over-excludes, shrinks coverage; M's unclaimed move is an `observed_unclaimed_delta` audit row per A11). Track D write-side assertion: `primary_clause_id == ablated_clause_id`. Source: EVR-5 (verified `0003_admissible_verdicts_view.sql:29-35`).
- **A47 — Confound storage = threshold-triggered events only.** No dense per-sample×axis matrix (would be 16k+ rows/run of non-events). All-axes deltas computed in-memory per condition-cell. σ(Null) estimated per-(run, axis) at write-time, N_null≥30 floor, k=2.0; below floor → confound detection disabled for that axis, affected verdicts `UNMEASURED(underpowered)`. Uncalibrated Tier-2 axes excluded from σ(Null). Source: STAT-2, REL-3.
- **A48 — UNMEASURED ≠ FAILED (PRD §19.2 success criterion).** BLOCKER. FAILED renders red `FAILED (P(win)≤.05)`; UNMEASURED renders yellow `UNMEASURED(<subreason>)` (`no_data | inadmissible | underpowered | falsifying_case_missing | budget_exhausted`). Exit codes: `0` = every clause reached a verdict; `2` = ≥1 UNMEASURED; non-2 reserved for hard errors. Falsifiable test: an underpowered clause exits 2, not the FAILED path. Source: ODX-4, STAT-1.
- **A49 — Multiplicity owned by Track E (A9), Track D persists provenance.** Track E applies the hierarchical Beta-Binomial (BH-FDR fallback). Track D obligation: every verdict carries `(run_id, clause_id, axis, comparison)` + run config records family size K×|axes| so Track E has the multiplicity denominator without re-deriving. Documented in the Track D brief so the hand-off isn't dropped. Source: STAT-7.
- **A50 — LOO honesty framing + redundancy limitation.** Report column = `Contribution (single-clause LOO; lower-bound under redundancy)`; "absence of delta is not absence of contribution." Redundancy cancellation (JoPA, arXiv:2405.20404) = documented v0.1 limitation; triggered (NOT blanket — O(m²)) paired-ablation probe optional behind `--probe-redundancy`, charges budget, only reclassifies UNMEASURED (never upgrades to PASSED). Random-subset surrogate (ContextCite-style, ~2-4m calls, NOT 2^m) = documented v0.2 upgrade. Source: STAT-5, STAT-6, EVR-1, EVR-3.
- **A51 — Dry-run discipline.** Per-clause table (`clause# | axis | conditions | N_proj(min..max) | est_CI_width | status{TESTABLE | VACUOUS-EXCLUDED | NO-FALSIFYING-CASE}`); offline projection — no DB conn, no `JudgeClient`, no API key required (pull-forward TC-SLOP-001/002); terminal line `NO CALLS MADE — re-run with --execute`; distinct `--max-usd` (per-run) vs `--daily-cap` (trailing-24h) errors naming the offending flag. Source: ODX-1, ODX-6.
- **A52 — Resume + progress + inspection UX (flags on `run ablation`, no new command — PRD §18 locked).** `--resume <run_id>` with resume-preview; bare re-run against an incomplete prior run WARNS + names the resumable run_id (no silent fresh-start/double-spend); `rich.progress` per-clause + live dual-cap footer; `--show-rendered <clause_id>` prints verbatim Full/Ablated_k/Null + `ablation_operator_version` (a run is untrustworthy if the ablation operator isn't inspectable). Source: ODX-2, ODX-3, ODX-5.

### C2 — RESOLVED = REFUSE (SME verdict; NOT surfaced to user)

Unanimous across the three relevant seats (EVR-4 primary, STAT-8, COST-6 concur). No `operator_self_labeled` admissible tier in v0.1. The defect is **independence collapse** (a self-labeled set certifies only "agrees with this operator," never an axis-level claim — the cross-axis-inheritance prohibition restated), NOT "κ≈1.0." The flip's own guardrail concedes the verdicts aren't evidence-grade; COST's ship-testable PRO is met by a synthetic test fixture. If ever flipped (v0.2 opt-in): `provisional_non_admissible`, hard-excluded from the Beta-Binomial pool at the VIEW layer, 30-day cadence, every report stamped `[operator-calibrated — not independently validated]`. C2 is removed from the §C user-owned queue.

### Citation corrections to `landscape-2026-06-06.md` (seats verified primary sources)

Load-bearing claims survive; three citations corrected: (1) **arXiv:2405.20404 = "JoPA: Joint Prompt Attribution" (Chang et al., ACL 2025)**, not "XPrompt/JoPA"; doctor/patient example is report illustration, not a paper quote. (2) **arXiv:2312.15395** applies Shapley to whole-prompt ensembles, NOT within-prompt components — supports the concept, not a clause-decomposition precedent. (3) **arXiv:2510.09738 ("Judge's Verdict")** classifies judge capability; it does NOT prescribe refusing uncalibrated judges — the REFUSE authority is `llm-judge-calibration` + independence theory. (4) arXiv:2409.09951 "3-9x swing" is directionally confirmed; the magnitude is landscape-sourced.

### PRD v1.1 amendment queued (replaces the D2 §1 edit)

**§1 reframe (EVR-6):** the harness's novel, defensible claim is the *evidentiary discipline* — "falsifiable directional contracts with write-time admissibility-gated, append-only provenance" (the P4 signature, zero hits in the eval domain per landscape §1) — NOT the estimator. LOO is honestly the *conservative* estimator inside that discipline; under-crediting contribution is a safe failure for an adversarial audit (false-negative on contribution, never false-positive on a PASS).

### Deferred (D-items, v0.2+)

Random-subset/ContextCite surrogate estimator (`--estimator=subset-surrogate`); blanket joint-ablation sweep (O(m²)); multi-process sampling (D11, reintroduces the budget race A42 closes); `operator_self_labeled` bootstrap affordance (non-admissible, VIEW-excluded); cost reconciler as a `skill audit` subcommand (folds into D7).

### Cross-talk validation (this fire)

- **Predictions landed**: 4+ — A13-cache × neutral-substitution collision (COST↔ODX); resume corrupts sequential `n` (STAT↔REL); `ablation_operator_id` must pin to run not re-resolve on resume (EVR↔REL); cost_ledger is also the crash-recovery ledger (COST↔REL).
- **Cross-derived findings**: the four above are findings no single seat's lens alone would have produced — each arose from one seat predicting another's concern, which the predicted seat made concrete.
- **Genuine disagreements**: none unresolved. The one apparent tension (A13 cache vs substitution) resolved cost-favorably, not a real conflict.
- **Citation discipline**: STAT + EVAL-RESEARCH independently verified the landscape report's arXiv ids at primary source and caught 3 mischaracterizations — the load-bearing move per `subagent-research-reliability`.

---

## Appendix F — Pre-Track-E council (2026-06-06, later turn)

**Template:** Custom — STAT + TEST-ARCH + SCHEMA + OPERATOR-DX + RELIABILITY + EVAL-RESEARCH (6 seats). Opus 4.7, parallel, read-only. Archive: `docs/council-fires/2026-06-06-pre-track-e/`. Trigger: Track E dispatch readiness (PLAN.md lines 223-238 + 4 checkpoint carry-forwards: CF-D3-1, A51 amendment, TA-4, SEC judge-injection).

**Outcome:** 9 findings adopted (A53–A61); 2 BLOCKERs (A56 freeze schema gap, A57 stale-frozen-case rule); 4 MAJORs cleanly resolved; 2 OBSERVATION/MINOR; 1 Track D bug surfaced (CLI signature `freeze <sample_id>` → `<verdict_id>` at `main.py:983` + verdict_id discoverability gap on ablation report); 0 unresolved BLOCKER. C3 candidate (shrunken-vs-unpooled PASSED gate) considered + retracted per `feedback-route-to-most-expert` (calibration methodology, not user values; STAT SME default = shrunken-primary + unpooled-audit-companion).

### Adopted findings

- **A53 · Hierarchical Beta-Binomial fit method.** v0.1: Empirical-Bayes Method-of-Moments via `scipy.stats` — closed-form, deterministic, no MCMC, no new heavy dep. Per-clause posterior stays `Beta(1+w, 1+n−w)` (PRD §14 locked); hyperprior `Beta(α̂_skill, β̂_skill)` fit via MoM over per-clause `(w_k, n_k)`. **Convergence failure** = `α̂ ≤ 0 ∨ β̂ ≤ 0 ∨ var_between < 1e-6` → BH-FDR fallback per A9 (q=0.05 over per-clause `p_exceeds` from unpooled posterior). When **K < 10**, EB hyperprior estimate is noisy (BDA3 §5) — default to UNPOOLED reporting with logged warning `aggregation_method = unpooled (K<10)`; hierarchical fit only triggers at K≥10. Direct dep promotion: `scipy>=1.11` added to `pyproject.toml` (Phase 1.1 supply-chain audit gap — already imported via transitive statsmodels at `stopping.py:32`). Determinism: pin `PYTHONHASHSEED=0` discipline already in env recipe. PyMC MCMC NUTS hyperprior fit deferred to D21. **Driver**: STAT-Q1, EVAL-RESEARCH-Q1. **Dissent**: EVAL-RESEARCH preferred PyMC NUTS with R-hat<1.03 + ESS≥400 — recorded; flip condition = "K<10 sparse-data noise proves to materially distort PASSED rates in v0.1 dogfooding."

- **A54 · `run evaluate-skill <skill_id>` = pure read-side aggregator.** Discovers all `runs` rows for `skill_id` with `run_kind='ablation'` and `completed_at IS NOT NULL`. Preflight per A61 incomplete-run gate: if any incomplete prior run → refuse-to-start exit 1 (operator-correctable). If no completed runs exist → exit 1 with `"No completed ablation run found for skill <skill_id>. Run 'run ablation <skill_id> --execute' first."`. Aggregation over admissible+non-confounded verdicts via the `admissible_verdicts` VIEW (A29). May optionally mint a `runs.run_kind='evaluate_skill'` envelope as audit-trail metadata (run_ids aggregated + EB-MoM hyperprior parameters + aggregation_method) so report is reproducible — NOT a sampling run. No `--max-usd` / `--execute` flags; aggregation cost ≈ $0 (no LLM calls). Falsifiable test: against a skill with zero completed ablation runs, `evaluate-skill` exits 1, makes zero API calls, requires no `ANTHROPIC_API_KEY`. 4-seat consensus (TEST-ARCH lead, OPERATOR-DX + STAT + RELIABILITY concur). **Driver**: TEST-ARCH-Q2.

- **A55 · `diff skill <skill_id_a> <skill_id_b>` semantics.** Revisions = distinct `skill_id` rows (content-hash; `skills.skill_id` per `0001:23`). Clause comparability key = `(axis, clause_text_sha256)` — exact match first; unaligned → `ADDED` / `REMOVED`. `clause_id` does NOT persist across revisions (embeds `skill_id` per `0001:32`), so naive `clause_id` equality is broken by construction. **Metric-version divergence rule**: per-clause status delta is `metric_drift` whenever ANY of the following diverge between A's verdict and B's verdict for the matched clause: `(metric_id, metric_version)`, `ablation_operator_hash`, `subject_model`, `user_message_sha256`. The two posteriors are NOT commensurable when the measurement changed — `metric_drift` is a category-error guard. Status delta enum: `regressed | improved | unchanged | new | removed | metric_drift`. Diff is read-only; no migration; no schema change. Default exit 0 if diff ran (semantic success not default signal); `--exit-on-divergence` flag flips to 2 when any status differs (CI use). Falsifiable: diff a skill against itself → all `unchanged`, zero `metric_drift`. **Driver**: TEST-ARCH-Q3 + SCHEMA + EVAL-RESEARCH-Q3 (added `metric_drift` framing).

- **A56 · `freeze <verdict_id>` write contract + new migration `0400_freeze_provenance.sql`.** BLOCKER: current `frozen_cases` schema (`0001:157-177`) lacks the FK + uniqueness needed to make `freeze` correct under A1 + A15. Migration `0400_freeze_provenance.sql` (Track E range 0400-0499 per A30) adds: (i) `verdict_id TEXT REFERENCES oracle_verdicts(verdict_id) NOT NULL` for new rows; (ii) `run_id TEXT REFERENCES runs(run_id)`; (iii) `axis TEXT`; (iv) `CREATE UNIQUE INDEX idx_frozen_unique ON frozen_cases(clause_id, axis, failing_input_sha256)` — duplicate freeze of same input is permanent (append-only) and would inflate A15's "≥1 frozen_case_at_current_metric_version" gate; (v) `BEFORE INSERT ON frozen_cases` trigger refusing INSERT if joined `runs.completed_at IS NULL` (incomplete-parent guard, RELIABILITY-flagged). Repository: `freeze_verdict(conn, verdict_id, oracle_source, *, labeled_by=None)` in `repositories/evidence/frozen_cases.py`. Idempotent: dup raises UNIQUE → exit 0 with `"already frozen"` stderr (not silent no-op per A48 discipline). CLI: **rename `freeze <sample_id>` → `freeze <verdict_id>` at `main.py:983`** (existing Track D stub bug). Eligibility: `observation ∈ {0.0, 0.5}` (FAILING side) AND `admissibility_state='admissible'` AND `oracle_source='mechanical'` (Tier-1 only in v0.1; Tier-2 deferred to D22). Provenance auto-fill on insert: `(metric_id, metric_version, implementation_hash)` from verdict's `metric_versions` row. Dry-run default (consistency with `skill init`, `run ablation`, `calibrate` per project Pipeline-Safety doctrine). Discoverability: Track D ablation report adds a `verdict_id` column (fits inside existing surface; not a new command — PRD §18 locked). **Driver**: SCHEMA-Q4 (BLOCKER) + TEST-ARCH + OPERATOR-DX + RELIABILITY co.

- **A57 · Stale-frozen-case auto-flip + new migration `0401_stale_frozen_view.sql`.** BLOCKER: A15's "PASSED requires frozen case at *current* metric_version" not implementable as written — no "current" pointer exists. **"Current metric_version" derived definition**: `SELECT version, implementation_hash FROM metric_versions WHERE metric_id = ? AND audited = 1 AND mechanical_validity_test_passed = 1 ORDER BY registered_at DESC LIMIT 1`. The `audited + validity_passed` filter is load-bearing — a metric_version that failed A14/A33 mechanical validity must NOT be "current." Migration `0401_stale_frozen_view.sql` creates `current_metric_versions` VIEW and `frozen_cases_with_currency` VIEW. **Auto-flip rule**: a clause whose only frozen cases are non-current flips to `UNMEASURED(falsifying_case_stale)`. **A17 sub-reason enum extended**: `no_data | inadmissible | underpowered | falsifying_case_missing | budget_exhausted | falsifying_case_stale` (6 reasons). Stale cases remain in `frozen_cases` (audit-trail) but don't count toward A15. **No re-freeze command** — operator re-runs `freeze` with a new verdict collected under the current metric_version (append-only spirit; no stamp-renewal evidence-free path). Falsifiable: bump a `metric_versions` row backing clause X's frozen case (with audited=1 + validity_passed=1) → next `evaluate-skill` flips clause X to `UNMEASURED(falsifying_case_stale)`, not PASSED, not FAILED. STAT's stale-vs-underpowered action discrimination lives in stderr message + report sub_reason (NOT in distinct exit code — A48 clean-shape preserved per A58). **Driver**: TEST-ARCH-Q5 (BLOCKER) + SCHEMA + STAT co.

- **A58 · A48 exit-code uniform extension.** `run evaluate-skill`: `0` = aggregation completed, no UNMEASURED in family; `2` = aggregation completed, ≥1 UNMEASURED; `1` = precondition fail (no completed ablation, incomplete prior, aggregation error). `diff skill`: default `0` if diff ran (operational success), `--exit-on-divergence` flag → `2` when any clause status differs A↔B; `1` on hard error. `freeze`: `0` = frozen (or "already frozen" on UNIQUE collision); `1` = validation refused (dup-error-message, missing verdict_id, stale-metric-version refusal, non-FAILED verdict, inadmissible verdict, incomplete-parent); `2` = unused. STAT's pushback for granular non-zero codes (exit 3 for stale-distinct-from-underpowered) resolved on A48 clean-shape grounds — discrimination lives in `report.sub_reason` field + stderr human-readable message. Falsifiable per command: synthesize a skill with ≥1 UNMEASURED → `evaluate-skill` exits 2; diff with metric_drift on any clause + `--exit-on-divergence` → exits 2; double-freeze same verdict → exits 0 with "already frozen". **Driver**: OPERATOR-DX-Q6 + TEST-ARCH co.

- **A59 · TA-4 verified closed (family-size persistence).** OBSERVATION (clean pass). Track D persists `family_size = K × |axes|` as typed int in `runs.config_json` via `RunConfig.to_json()` at `ablation/runner.py:154,338-348,365`. Track E reads `json.loads(runs.config_json)["family_size"]` directly — no schema change, no denormalization onto verdict rows. Defensive checks at Track E aggregation entry: (i) `family_size > 0` invariant (default 0 indicates malformed/legacy run; aggregator refuses); (ii) sanity assertion `family_size == len(clauses_in_config) * len(distinct_axes_in_config)`; mismatch → logged data-integrity warning, treat as A41 reconciler-style anomaly (no panic). RELIABILITY confirmed: A40 sample idempotency requires frozen plan written under `writer_transaction(evidence)` BEFORE first sample (runner.py:358), so `config_json` is trustworthy even when `completed_at IS NULL`. 3-seat consensus (STAT lead, SCHEMA + RELIABILITY concur). **Driver**: STAT-Q7 + checkpoint TA-4 carry-forward.

- **A60 · Report serialization: dual format with `report_schema_version`.** `--format=rich|json` (default `rich` for operator terminal use). JSON output ships with mandatory top-level `report_schema_version "1.0.0"` (semver). v0.1 lifetime is `1.x` additive-only — additions = minor bump, removals/renames/type-changes = major bump (breaks `diff skill` consumer). **Required top-level keys**: `report_schema_version, skill_id, generated_at_utc, harness_version, aggregation_method ∈ {ebmom_hierarchical, bh_fdr_fallback, unpooled}, aggregation_provenance (EB-MoM α̂/β̂ or BH-FDR-fallback-reason; PYTHONHASHSEED), clauses[], vector (§16 — Passed/Failed/Confounded/Unmeasured/Coverage/Contribution), coverage, contribution`. **Per-clause fields**: `clause_id, status, sub_reason (when UNMEASURED), posterior_mean, credible_interval_95, p_win_gt_threshold, frozen_case_count_at_current_metric_version, metric_id_per_axis, metric_version_per_axis, ablation_operator_hash, run_ids_aggregated`. JSON byte-stable for identical evidence: sorted keys, no internal timestamps inside payload (single `generated_at_utc` field only). `--format=json` writes ONLY to stdout; all warnings (UNMEASURED count, A50 LOO-honesty caveat, CF-D3-1 incomplete-run warn) go to stderr (shell pipeline safe). **Reject `--format=csv|md`** in v0.1 (scope creep; CSV lossy on credible intervals + provenance). EVAL-RESEARCH: HELM open user issues #2322 #2484 prove community pays cost of skipping schema versioning — cheap audit-trail discipline. **Driver**: OPERATOR-DX-Q8 + TEST-ARCH (field set) + EVAL-RESEARCH (prior art).

- **A61 · CF-D3-1 fix lands in Track E entry — lift to shared module.** RELIABILITY MAJOR: keeping `_find_incomplete_run` private to `cli/main.py:543-619` forces second refactor or silent inconsistency. Track E `evaluate-skill` precondition gate + `freeze` parent-run completeness check both need this lookup. **Lift to** `src/skill_harness/storage/recovery.py` with three signatures: (i) `find_incomplete_runs(skill_id, *, evidence_conn_ro, runtime_conn) -> list[IncompleteRun]` — two-step runtime→evidence lookup via `open_evidence_readonly` (A51 ratification confirmed: `open_evidence_readonly` exists at `storage/migrations.py:280`); (ii) `run_is_complete(run_id, *, evidence_conn_ro) -> bool` for the `freeze` parent-completeness check; (iii) `find_resumable_run_for_skill(skill_id, ...) -> str | None` keeps Track D `run ablation` bare-rerun semantics (delegates to (i) + first match by most-recent heartbeat). Migrate `main.py:800` call site to use (iii). No schema change (per A25 — cross-DB join in Python, not SQL). Track E `evaluate-skill` precondition: incomplete runs → refuse-to-start exit 1 (per A54); no admissible evidence for a clause → emit `UNMEASURED(no_data)` exit 2 (per A48) — distinct failure modes per RELIABILITY. Track E `freeze`: A56 BEFORE INSERT trigger is the SQL-level guard; `run_is_complete(...)` is the application-level pre-check that produces the operator-readable error before write attempt. 3-seat consensus (RELIABILITY lead, SCHEMA + OPERATOR-DX concur). **Driver**: RELIABILITY-Q9 + checkpoint CF-D3-1 carry-forward.

### Deferred to v0.2 (this fire)

- **D21 PyMC MCMC NUTS hyperprior fit.** EB-MoM is v0.1; PyMC opt-in deferred until K<10 sparse-data noise empirically distorts PASSED rates. Re-evaluate post-v0.1 dogfooding.
- **D22 Tier-2 verdict freezing.** Requires operator-supplied human label (PRD §9 "Human" oracle source requires `labeled_by + labeled_at`); v0.1 admits Tier-1 mechanical freezes only.
- **D23 `clause_semantic_id`** for stable inter-revision identity. v0.1 uses content-hash match per `(axis, clause_text_sha256)`; v0.2 adds a semantic-anchor column if exact-match yields too many `ADDED+REMOVED` pairs for trivial edits.
- **D24 `re-freeze` command.** v0.1 operator re-runs `freeze` with a new verdict under current metric_version. Stamp-renewal-without-evidence is the path explicitly rejected by A57.
- **D25 Fuzzy clause matching** in `diff skill`. v0.1 exact-match only; unaligned clauses → ADDED/REMOVED.

### Open items (carry-forward unchanged)

- **C1 — Tie encoding** (half-update vs drop-ties): still data-blocked per Pre-Track-D §C ownership note; resolvable when first calibration_event lands.
- **C3 candidate (shrunken-vs-unpooled PASSED gate)**: NOT added to §C queue. Per `feedback-route-to-most-expert`, this is calibration-methodology — STAT SME default holds (shrunken posterior is primary; unpooled persisted in `aggregation_provenance` for audit). If post-v0.1 dogfooding shows user dissatisfaction with shrunken-by-default, flip condition is "user requests unpooled-primary report."

### PRD v1.1 amendments queued (this fire)

In addition to the 34 amendments queued before this fire:

| Section | Amendment | Driver |
|---|---|---|
| §14 | EB-MoM hierarchical Beta-Binomial as v0.1 fit method; `α̂ ≤ 0 ∨ β̂ ≤ 0 ∨ var<1e-6` → BH-FDR fallback; K<10 → unpooled with logged warning | A53 |
| §15 | Add UNMEASURED sub-reason `falsifying_case_stale` (now 6-value enum) | A57 |
| §15 | Define "current metric_version" derivation rule (`audited=1 AND validity_passed=1 ORDER BY registered_at DESC LIMIT 1`) | A57 |
| §16 | Report wire format: `--format=rich\|json` (default rich); JSON with mandatory `report_schema_version "1.0.0"` semver; v0.1 lifetime additive-only on `1.x` | A60 |
| §16 | Top-level required keys + per-clause field-set spec'd above | A60 |
| §17 | New migrations: `0400_freeze_provenance` (Track E range), `0401_stale_frozen_view` (VIEWs) | A56, A57 |
| §18 | `evaluate-skill` defined as pure read-side aggregator; no API calls; no `--max-usd` / `--execute` flags | A54 |
| §18 | `freeze <verdict_id>` (rename from `<sample_id>`); dry-run default; Tier-1 mechanical only in v0.1 | A56 |
| §18 | `diff skill` exit-code conventions + `--exit-on-divergence` flag | A55, A58 |
| §19 #7 | "PASSED requires non-stale frozen falsifying case at current metric_version" (strengthening) | A57 |

**Total PRD v1.1 amendments queued: 44** (34 prior + 10 from this fire).

### Cross-talk validation (this fire)

- **Predictions landed (8+ accurate)**: STAT→TEST-ARCH PASSED→UNMEASURED transition observability (landed); STAT→OPERATOR-DX exit-2 collapse of stale-vs-underpowered (landed and resolved); STAT→EVAL-RESEARCH K<10 hyperprior noise under-weight (landed; EVAL-RESEARCH did not address); TEST-ARCH→SCHEMA "materialized status column" wrong-prediction (SCHEMA defended VIEW per A1 — predictively wrong, substantively right); TEST-ARCH→OPERATOR-DX sub-reason distinctness under-weighting (landed); SCHEMA→TEST-ARCH freeze auto-trigger wrong-prediction (TEST-ARCH framed operator-driven correctly); SCHEMA→RELIABILITY conservative over-warn defense (landed); SCHEMA→EVAL-RESEARCH metric_version literature citation (landed); RELIABILITY→SCHEMA freeze parent-completeness as SQL CHECK (partially — became A56 BEFORE INSERT trigger); EVAL-RESEARCH→TEST-ARCH metric_drift first-class status (partial — TEST-ARCH used `INCOMPARABLE(metric_version_drift)`, same concept, EVAL-RESEARCH's simpler `metric_drift` term adopted).
- **Cross-derived findings**: (1) Stale-vs-underpowered action discrimination tension surfaced in STAT↔OPERATOR-DX cross-talk (resolved: discrimination lives in stderr + sub_reason, not exit code). (2) `freeze` discoverability gap (OPERATOR-DX surfaced) cross-validated against SCHEMA's `verdict_id` FK requirement → fix is a single Track-D-extension column on the ablation report.
- **Genuine disagreements resolved**: (1) STAT EB-MoM vs EVAL-RESEARCH PyMC NUTS — adopted EB-MoM; PyMC → D21. (2) STAT exit 3 vs OPERATOR-DX uniform exit 2 — OPERATOR-DX wins on A48 clean-shape; STAT concern met via stderr. (3) TEST-ARCH audited+validity_passed filter vs SCHEMA raw registered_at — TEST-ARCH's filter is correct.
- **Citation discipline**: EVAL-RESEARCH verified at primary source: arXiv:2510.04265 (Pass@k Bayesian) + arXiv:2505.05602 (HiBayES) + PyMC canonical hierarchical pooling example URL + lm-evaluation-harness `evaluation_tracker.py` (no schema version field, confirmed) + HELM open issues #2322 #2484 + AlpacaEval README + arXiv:2602.10371 (model-diffing; not transferable, confirmed).
- **Lens distinctness**: 6 seats with 9 questions kept lens distinctness high. RELIABILITY + OPERATOR-DX overlap on CF-D3-1 warning UX (both correct, complementary not redundant). EVAL-RESEARCH provided 4 net-new citations + the `metric_drift` framing that TEST-ARCH adopted under different naming.

---

## Appendix G — Phase 3.4 fire: M1-r Coverage Law denominator (2026-06-07)

**Template:** Custom 4-seat — TEST-ARCH + STAT + EVAL-RESEARCH + OPERATOR-DX (CORE roster, SCHEMA omitted because no schema touched, COST omitted because no API call surface). Opus 4.7, parallel, read-only. Archive: this Appendix only (no separate dispatch dir — fire was values-decision-narrow, 4 self-contained outputs synthesized inline). Trigger: Phase 3.4 code-review-sentinel surfaced M1-r as a `[values decision]`; user override directed "Deliberate with the council - Azimuth as applicable."

**Outcome:** 1 finding adopted (A62); 5 observations surfaced (1 fix-loop scope expansion, 1 doc-lock companion-pass item, 3 v0.2 punch-list items). 0 unresolved BLOCKER. Azimuth explicitly skipped — M1-r is a sub-decision (downside bounded; reversibility high); azimuth scope is initiative-level go/no-go and reserved for the v0.1 launch council per PLAN.md §4.2.

**Vote tally:**

| Seat | Reading | Severity-if-wrong | v0.1 action recommended |
|---|---|---|---|
| TEST-ARCH | C | MAJOR | No engine change; PRD §8 sentence pointing at D3 |
| STAT | C | MAJOR | No engine change; PRD §8 sentence |
| EVAL-RESEARCH | C | MINOR | No engine change; cite Stryker + DO-178C + MMLU-Redux |
| OPERATOR-DX | A | MAJOR | No engine change; add rich-render vacuity adjunct |

Functionally unanimous on v0.1 behavior. Reading A and Reading C are identical at the wire (no engine change either way); they differ only on whether the PRD §8 disambiguating sentence + D3-deferral note land in v1.1 doc-lock.

### Adopted finding

- **A62 · Coverage Law denominator v0.1 = Reading A (`tested / authored`); D3 two-numerator deferral preserved.** Engine code at `src/skill_harness/aggregation/engine.py:94-95, 425` already implements Reading A; no engine change. PRD §8 gains a disambiguating sentence in v1.1 doc-lock: *"In v0.1, `total_clauses` is the authored clause set including all vacuity_flag values. v0.2 will additionally report `(tested / (total − mechanical_vacuous))` per Council D3, gated on extractor-calibration audit (D4)."* Reading A's behavioral nudge — "your skill has unverifiable surface area; this counts against you" — is the load-bearing v0.1 signal per PRD §20 ("A clause that cannot be falsified is not a contract. It is metadata.") and the Goodhart-resistance argument (Reading B incentivizes over-flagging clauses as vacuous to inflate Coverage). Reading C's two-numerator endpoint is field-standard per Stryker Mutator (`detected/valid` AND `detected/covered`), DO-178C §6.4.4.3 (uncovered code requires positive justification, not silent denominator removal), and MMLU-Redux (reports BOTH `Original EM` and `OK/Erroneous EM`). **Driver**: TEST-ARCH-M1r-1 + STAT-M1r-1 + EVAL-RESEARCH-M1r-1 + OPERATOR-DX-M1r-1 + Phase 3.4 code-review M1-r. **Dissent**: none material — OPERATOR-DX's READING-A is operationally identical to TEST-ARCH/STAT/EVAL-RESEARCH's READING-C for v0.1 wire output. **Flip condition**: (a) v0.1 dogfooding shows extractor-flagged vacuity rate ≥15% on ≥20% of imported skills AND operators report Reading A as actively misleading-discouraging (Goodhart pattern surfacing); (b) Reading B becomes a wire requirement before D4 extractor calibration lands — at which point D3's v0.2 ship accelerates into v0.1.x.

### Observations (5)

- **OBS-G1 (TEST-ARCH-M1r-2) · D3 formula clarification for v0.2.** D3's verbatim formula `(total − mechanical_vacuous)` excludes only the deterministic vacuous bucket and KEEPS `semantic_vacuous_pending_review` in the denominator (per A16's framing — semantic vacuous is UNMEASURED, not silently excluded). This is defensible but should be stated explicitly when D3 ships in v0.2 so the implementor doesn't re-derive it from A16 + A17 + D3. **Action**: surface to Phase 3.5 doc-lock companion pass on COUNCIL_FINDINGS.md D3 entry.
- **OBS-G2 (STAT-additional) · `total_clause_count == 0` precondition refusal.** Today `engine.py:425` returns `0.0` when no clauses are authored — meaningless. Should raise `PreconditionError("no_clauses")` so the CLI surfaces a clear operator message instead of a `Coverage: 0%` falsehood. **Action**: add to Phase 3.4 fix-loop scope (~10 LOC). Severity: MINOR.
- **OBS-G3 (EVAL-RESEARCH-additional) · DO-178C three-disposition pattern for v0.2 D3.** v0.2 D3 work should mirror DO-178C §6.4.4.3's three-disposition pattern: every vacuous clause should have an explicit disposition `fixable_by_rewrite | retain_as_metadata | mechanical_no_metric_exists`, not just a binary "vacuous" flag. Aligns with A16's existing mechanical-vs-semantic split. **Action**: surface to Phase 3.5 doc-lock as D3 expansion text.
- **OBS-G4 (EVAL-RESEARCH-flip) · v0.2 D3 acceleration trigger.** If v0.1 corpus shows extractor-flagged vacuity rate ≥15% on a representative skill, pressure to ship Reading B becomes operationally justified before extractor calibration (D4) completes. Document as a "watch-for-v0.2-acceleration" trigger in PRD §8. **Action**: include in Phase 3.5 PRD §8 amendment text.
- **OBS-G5 (OPERATOR-DX-additional) · Rich render vacuity adjunct.** Today `cli/main.py:1591` displays `f"{report.coverage:.1%}"` as a bare scalar. Additive UX upgrade: render `"Coverage: 60.0% (6 verified / 10 authored; 2 mech-vacuous excluded from testing)"` when vacuity_flag count is non-zero. No wire format change; rich-render only. **Action**: add to Phase 3.4 fix-loop scope (~15 LOC). Severity: MINOR.

### Cross-talk validation (this fire)

- **Functional unanimity on v0.1 behavior**: all 4 seats agree on the engine's current behavior. Disagreement is entirely on the PRD §8 / doc-lock framing (Reading A vs Reading C labeling) — both produce identical wire output for v0.1.
- **Predictions landed (9+ accurate)**: TEST-ARCH→STAT C with rate-semantics-purity rationale (correct); TEST-ARCH→OPERATOR-DX A-with-vacuity-adjunct (correct); STAT→TEST-ARCH C citing UNMEASURED-orthogonality (correct); STAT→EVAL-RESEARCH C citing prior art (correct); STAT→OPERATOR-DX split A-or-C with vacuity surfacing (correct — OPERATOR-DX went A); EVAL-RESEARCH→TEST-ARCH A (predicted A, actual C; partial — TEST-ARCH's recommendation IS A behavior, framed as C); EVAL-RESEARCH→STAT C with denominator-confound argument (correct); EVAL-RESEARCH→OPERATOR-DX A for v0.1 with D3 v0.2 support (correct); OPERATOR-DX→TEST-ARCH A on §20 anchor (partial — TEST-ARCH framed as C); OPERATOR-DX→STAT A or C on rate-semantics (correct); OPERATOR-DX→EVAL-RESEARCH B on lcov analogy (wrong — EVAL-RESEARCH went C citing Stryker dual-numerator practice).
- **Cross-derived findings (5 net-new)**: D3 formula clarification (TEST-ARCH cross-derived from A16 + D3 alignment check); precondition refusal for zero-clauses (STAT cross-derived from Reading A's degenerate-case analysis); DO-178C three-disposition pattern (EVAL-RESEARCH primary-source-driven); v0.2 D3 acceleration trigger (EVAL-RESEARCH operationalization); rich-render vacuity adjunct (OPERATOR-DX cross-derived during the Scenario 1 analysis).
- **Genuine disagreements resolved**: A vs C framing — synthesizes to "Reading A behavior with D3 deferral acknowledged in PRD," which is operationally Reading C and labeled A by the OPERATOR-DX seat. No material disagreement.
- **Citation discipline**: EVAL-RESEARCH verified at primary source — Stryker Mutator metrics docs (URL fetched), DO-178C §6.4.4.3 via LDRA (URL fetched), MMLU-Redux arXiv:2406.04127 (abstract + HTML fetched). STAT cited MMLU recall-from-training (flagged ABSTRACT-ONLY for HELM, training-memory for MMLU). external-citations-verified: YES with appropriate caveats.
- **Lens distinctness**: 4 seats with 1 question kept lens distinctness high. TEST-ARCH owned PRD §20 invariant. STAT owned rate-semantics + denominator-confound. EVAL-RESEARCH owned prior art (3 frameworks). OPERATOR-DX owned wire format + UX scenarios with concrete numbers. No redundancy; complementary.

### PRD v1.1 amendments queued (this fire)

In addition to the 45 amendments queued by the Phase 3.5 audit:

| Section | Amendment | Driver |
|---|---|---|
| §8 | Disambiguating sentence: "In v0.1, `total_clauses` is the authored clause set including all vacuity_flag values. v0.2 will additionally report `(tested / (total − mechanical_vacuous))` per Council D3, gated on extractor-calibration audit (D4)." | A62 |
| §8 | "Watch-for-v0.2-acceleration" trigger note: ≥15% extractor-flagged vacuity rate on a representative skill triggers D3 ship in v0.1.x. | OBS-G4 |

**Total PRD v1.1 amendments queued: 47** (45 from Phase 3.5 audit + 2 from this fire). CF-Phase-3-4-1 in Phase 3.4 fix-brief retired (replaced by these two specific amendments).
