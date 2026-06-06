# Skill Harness — v0.1 Implementation Plan

**Status**: LOCKED — exit criteria are testable, no open questions.
**Input**: `PRD.md` (v1.0) + `docs/COUNCIL_FINDINGS.md` (5-seat synthesis, 2026-06-03)
**Owner**: this plan executes across multiple sessions; per-session checkpoint at `.claude/state/checkpoint.md`.

---

## Phase 0 — Bootstrap ✅ COMPLETE (session 1, 2026-06-03)

`git init` · `pyproject.toml` · `src/skill_harness/` package · `tests/` · `.gitignore` · `.gitattributes` · `pyrightconfig.json` · two-DB migration runner · `migrations/evidence/0001_initial.sql` · `migrations/runtime/0001_initial.sql` · 7 smoke tests (including append-only enforcement + runs.completed_at single-shot).

**Gate**: smoke tests collect and pass under `pytest`. (Verification deferred — requires venv setup; see Phase 1.0.)

---

## Phase 1 — Pre-build wiring (session 2 START)

Sequential. These MUST land before any Phase 2 worktree fires; they protect the build from regressions and friction.

### 1.0 · Venv + verify the bootstrap

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest -q
```

**Gate**: 7 smoke tests pass. The two append-only triggers fire `sqlite3.IntegrityError` with the expected messages. If any fail, debug per `superpowers:systematic-debugging` BEFORE proceeding.

### 1.1 · Supply-chain audit of declared deps

Invoke `supply-chain-risk-auditor:supply-chain-risk-auditor` against `pyproject.toml`. Deps in scope: `anthropic`, `click`, `pydantic`, `rich`, `pytest`, `ruff`, `mypy`, `hypothesis`.

**Gate**: no MAJOR or BLOCKER risk findings. Any MINOR is logged in `docs/COUNCIL_FINDINGS.md` Appendix and accepted.

### 1.2 · Permission allowlist

Invoke `fewer-permission-prompts` to scan transcript history and emit a project `.claude/settings.json` allowlist for the read-only Bash + MCP patterns this session has already used.

**Gate**: settings.json committed; subsequent sessions don't prompt-storm on `python`, `git`, `sqlite3`, `pytest`, `pip`, `ls`.

### 1.3 · ai-slop-sentinel Stop hook

Read `claude-code-stop-hook-envelope` first — it documents the JSON envelope gotcha that silently breaks naive Stop hooks. Then via `update-config`, install a Stop hook that:

- Parses `transcript_path` (JSONL) — does NOT grep stdin
- Extracts the last assistant message
- If the message touched `src/skill_harness/**/*.py`, dispatch `ai-slop-sentinel` as a fresh-context review
- Posts findings inline before next turn

**Gate**: hook fires correctly on a test turn that edits `src/skill_harness/cli/main.py`. Hook exits 0 silently on turns that don't.

### 1.4 · CLAUDE.md model-pinning note + skill-kit reference

Append to `CLAUDE.md` (project-local):

- Model pinning: Opus 4.7 for synthesis, council fires, plan-locking; Sonnet 4.6 for per-track TDD execution.
- Skill kit reference: `bayesian-eval-discipline`, `llm-judge-calibration`, `append-only-evidence-design`, `ai-slop-sentinel` — invoke at the relevant track per below.

### 1.5 · Pre-Track-A storage council fire ✅ FIRED 2026-06-04

Storage-touching-change template (TEST-ARCH + SCHEMA + RELIABILITY + SECURITY) dispositioned four audit-context fragility clusters before Track A code lands. All seats returned BLOCKER-FOUND. Adopted A18–A23; deferred D5–D8. Raw outputs + synthesis at `docs/council-fires/2026-06-04-pre-track-a-storage/`. Outcome creates 1.5a (code) and 1.5b (docs) gates below.

### 1.5a · Apply Phase 1.5 council code fixes (pre-Track-A blocker)

Sequential or single-PR; touches storage only. ~150 LOC + 2 new migrations + 3 new smoke tests + typed exception module.

- **A18** — `apply_pending`: replace `with conn:` + `executescript` with explicit `BEGIN IMMEDIATE` / statement-by-statement execution / `INSERT schema_migrations` / `COMMIT`, `ROLLBACK` on exception. New typed exceptions in `src/skill_harness/storage/errors.py` (`BootstrapError`, `MigrationApplyError`). Structured logging at each migration apply.
- **A19** — `open_evidence` / `open_runtime` raise `BootstrapError` when `discover()` returns `[]`. Add smoke test `test_open_evidence_raises_on_no_migrations` that uses a tmp dir without migrations and asserts the raise (replacing/supplementing the current inverted-assertion test).
- **A20** — new migration `migrations/evidence/0002_runs_trigger_split.sql`: DROP `runs_completed_at_once`, CREATE two named-column triggers (`runs_completed_at_set_once` + `runs_immutable_columns`). Add smoke test that an UPDATE of a non-frozen-non-completed_at column after completion succeeds (currently no such column exists, so test is parametric on the SQL primitive `BEFORE UPDATE OF`).
- **A21** — new migration `migrations/runtime/0002_schema_migrations_triggers.sql`: add BEFORE UPDATE + BEFORE DELETE triggers on `runtime.schema_migrations`. Add smoke test mirroring `test_evidence_append_only_skills`.
- **A22** — split `open_db()` to accept a pragma-set parameter OR per-DB helpers. `evidence` uses `PRAGMA synchronous = FULL`; `runtime` keeps `NORMAL`. Add smoke test asserting `PRAGMA synchronous` value per connection.

**Gate**: `pytest -q` green (all new + existing tests); `mypy --strict` clean; `ruff check` clean. Ai-slop-sentinel review at the change boundary.

### 1.5b · Apply Phase 1.5 council documentation updates

Documentation-only; can land in parallel with 1.5a.

- **A23** — `SECURITY.md` "Threat model" section gains three clauses (trust partition / filesystem substitution boundary / PRAGMA scope). Mirror trust-partition + filesystem boundary as a subsection under `docs/COUNCIL_FINDINGS.md` §A4. Note `synchronous=FULL`/`NORMAL` asymmetry in CLAUDE.md "Evidence model" section.

**Gate**: documentation review — no acceptance criteria beyond "all three clauses present and accurate."

### 1.5c · Pre-Track-A implementation council fire ✅ FIRED 2026-06-04

Storage-touching-change template (SCHEMA + RELIABILITY + SECURITY + TEST-ARCH) dispositioned 7 Track A implementation design questions BEFORE Phase 2 dispatch. All seats returned BLOCKER-FOUND across the 7 Qs. Synthesis: 5 BLOCKERs (Q2, Q3, Q4, Q6, Q7), 2 MAJORs (Q1, Q5). Adopted A24–A30; deferred D10–D14. Raw outputs + synthesis at `docs/council-fires/2026-06-04-pre-track-a-impl/`. Outcome expands Track A scope below (no separate gate beyond Track A's own exit criteria).

Substantive disagreement resolved: SECURITY argued runtime-first dual-DB ordering on audit-asymmetry grounds; SCHEMA + RELIABILITY + TEST-ARCH argued evidence-first on source-of-truth grounds. Orchestrator adopted evidence-first 3-vs-1 citing PLAN Track D's pre-call budget cap check, which moots SECURITY's bypass premise without dismissing the framing. SECURITY's runtime-first framing recorded as load-bearing dissent in `docs/COUNCIL_FINDINGS.md` §A25.

---

## Phase 2 — Parallel build via 5 worktrees (sessions 2–N)

Each track is one git worktree, one branch, one subagent dispatched via `superpowers:subagent-driven-development`. Tracks A–C can run in parallel (no shared files). D depends on A + C. E depends on D.

`superpowers:using-git-worktrees` sets the worktrees up:

```powershell
git worktree add ../youwontdoit-track-a feat/track-a-storage
git worktree add ../youwontdoit-track-b feat/track-b-extractor
git worktree add ../youwontdoit-track-c feat/track-c-oracle-library
```

### TRACK A · Storage layer

**Scope** (expanded by 1.5c council per A24–A30):
- Repositories: per-table modules under `src/skill_harness/storage/repositories/evidence/` (10 modules) + `src/skill_harness/storage/repositories/runtime/` (5 modules). Functional API only; no classes.
- Pydantic write-models in `src/skill_harness/storage/models.py` (`strict=True, extra='forbid', frozen=True`; NUL + control-byte rejection; size caps on `output_text`/`clause_text`).
- Transaction primitives: `src/skill_harness/storage/transaction.py::writer_transaction(conn)` context manager (`BEGIN IMMEDIATE` / COMMIT-or-ROLLBACK).
- Dual-DB write helper: `src/skill_harness/storage/dual_write.py` — evidence-first ordering per A25; ATTACH forbidden in production paths.
- Connection lifecycle: `src/skill_harness/storage/context.py::StorageContext` dataclass with `__enter__`/`__exit__` for CLI use.
- New migration: `migrations/evidence/0003_admissible_verdicts_view.sql` — VIEW joining admissibility + confound exclusion per A29.
- Discovery hardening: `discover()` raises `BootstrapError` on duplicate version numbers per A30.
- Documentation: `migrations/README.md` documenting per-track number ranges; `.github/CODEOWNERS` requiring SCHEMA + SECURITY seat sign-off on `migrations/*` PRs.
- Concurrency model: SQLite `BEGIN IMMEDIATE` + 5s `busy_timeout` is THE writer-exclusion mechanism for v0.1 per A26 (no in-process `queue.Queue`).

**Driving findings**: A1, A2, A3, A4 (original SCHEMA seat) + A24–A30 (1.5c council).

**Skills loaded**: `append-only-evidence-design`, `sqlite-expert`, `property-based-testing` (for the append-only invariant — Hypothesis tests P1 generic + P2 runs-carve-out per A27), `windows-claude-code-env` (UTF-8 / regex traps on Windows).

**Exit criteria**:
- All 9 evidence tables + 5 runtime tables instantiated by `open_evidence()` / `open_runtime()`.
- **Property-based test** (`tests/property/test_evidence_append_only.py`) per A27:
  - **P1** (all tables except `runs`): `∀ valid r drawn from row_strategy(table), [INSERT r; UPDATE table SET <any_col>=<any_val> WHERE pk=r.pk] raises sqlite3.IntegrityError matching r'append_only_violation: ' + table`. DELETE analogue. FK closure via `PRAGMA foreign_key_list` introspection. `@settings(max_examples=50)`.
  - **P2** (runs-specific carve-out per A20): `∀ valid r, INSERT then UPDATE of skill_id|run_kind|config_json|started_at aborts; INSERT then single UPDATE of completed_at succeeds; INSERT then second UPDATE aborts`.
- **AST-walker test** (`tests/test_evidence_repo_surface.py`) per A24: regex scan over `repositories/evidence/*.py` rejects function names matching `^(update|delete|set|patch|modify|remove)_`.
- **Admissibility VIEW tests** (`tests/test_admissible_view.py`) per A29: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`.
- **A3 write-time-snapshot falsifying-case test** per A29 (promoted from D7 into Track A): insert verdict; flip `runtime.current_calibration` post-write; assert verdict's `admissibility_state` is unchanged.
- **`discover()` duplicate-version guard test** (`tests/test_discover_rejects_duplicate_versions`) per A30.
- **Hypothesis savepoint fixture** (`evidence_db_savepoint` in conftest) per A28 + `tests/test_hypothesis_savepoint_isolation` to verify between-example isolation.
- **`PRAGMA foreign_keys = 1` smoke test** per A28: assert PRAGMA is set on freshly-opened repo connections.
- **Concurrent-writers serialization test** (`tests/test_concurrent_writers_serialize.py`) per A26: 2-thread interleave under SQLite's lock + `busy_timeout` — both writes succeed.
- **Dual-write fault-injection tests** (`tests/test_dual_write_partial.py`) per A25: `unittest.mock.patch` injection on each known dual-write call site; evidence row exists, runtime row absent, structured `dual_write_partial` log emitted, no exception propagates past helper.
- **Crash-recovery test family** (`tests/test_crash_recovery.py`) per A27 (separate from property tests): kill between BEGIN/COMMIT during apply_pending (already covered); kill between evidence COMMIT and runtime BEGIN in dual-write; reopen DB after WAL truncation.
- **Structural enforcement** per A28: pre-commit grep ban verified — `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` returns empty.
- **CI grep ban** per A29: any code outside `src/skill_harness/audit/` (stub OK) that uses raw `oracle_verdicts` in a `SELECT` fails CI.
- `pytest -q` green; `mypy --strict src/` clean; `ruff check` clean; `ruff format --check` clean.

### TRACK B · Clause extractor

**Scope**: Markdown SKILL.md parser, frontmatter → metadata extraction, body → atomic clauses, axis/comparator inference, vacuity flag (mechanical vs semantic), falsifying-case-schema scaffolding. Reference subject: `ai-slop-sentinel` (a known-shaped real skill).

**Driving findings**: A15, A16, D4.

**Skills loaded**: `claude-api` (the extractor itself is a Claude call), `verbatim-content-subagent-dispatch` (its prompt must derive verbatim from SKILL.md sections), `llm-judge-calibration` (the extractor is a Tier-2 judge).

**Exit criteria**:
- `skill init <path>` ingests `ai-slop-sentinel/SKILL.md` and emits ≥5 clauses.
- Each clause has `axis`, `comparator`, `oracle_tier`, `vacuity_flag` populated.
- `clauses.falsifying_case_schema_sha256` populated for clauses with constructible schemas; NULL for `semantic_vacuous_pending_review`.
- Tests on three skills of varying shape (dense markdown, frontmatter-only, mostly-prose).

### TRACK C · Oracle library

**Scope**: Tier-1 mechanical metrics with audit gate; Tier-2 judge module with pairwise + position-swap discipline + adversarial-injection defense; calibration_events writer with statistical + cost-provenance fields.

**Driving findings**: A5, A6, A7, A14 (original) + **A31–A38** (Pre-Track-C council 2026-06-05).

**Skills loaded**: `llm-judge-calibration`, `claude-api`, `append-only-evidence-design`, `bayesian-eval-discipline`, `windows-claude-code-env`.

**Dev deps to add (per A33)**: `pytest-socket`, `tiktoken` (offline tokenizer, version-pinned).

**Exit criteria** (substantially expanded by Pre-Track-C council 2026-06-05; archive: `docs/council-fires/2026-06-05-pre-track-c/`):

*Tier-1 mechanical validity (A33):*
- Tier-1 registry seeded with the 4 honestly-mechanical metrics (Hedge Index with frozen wordlist, Verbosity, Structure Score, redefined Compliance Proxy).
- Each Tier-1 metric ships with `mechanical_validity_test` under `pytest-socket` `--disable-socket` module marker + bit-equality assertion (`metric(case) == metric(case)`) over fixed 3-5 input corpus + `PYTHONHASHSEED=0` discipline. Plus meta-test verifies pytest-socket itself fires.
- `metric_versions.mechanical_validity_test_passed = 1` flips ONLY when tests pass AND zero socket attempts. Auto-downgrade to Tier 2 at registry-insert time on failure.

*Tier-2 judge module (A31, A32, A35, A38):*
- Anthropic SDK `tool_use` with `strict: true`, forced `tool_choice={"type":"tool","name":"report_verdict"}`, schema `{choice: enum[A,B,tie], rationale_brief: str(maxLength=500)}`. `thinking={"type":"disabled"}`. `max_tokens=80`. `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)`.
- Pairwise + position-swapped pairs; deterministic SDK-boundary mocking (`anthropic.Anthropic.messages.create` side-effect callable); 9-cell (AB×BA) parameterized test table covering admissible / inadmissible / tie-symmetry paths. `admissibility_state` resolved at write time.
- Length control: both prompt-level ("length should not influence" instruction, `max_tokens=80` ceiling) AND observation-time AlpacaEval-2 regression (Dubois et al. 2404.04475). `length_regression_coefficient` stored separately; correction applied at verdict-write time. Both `raw_observation` and `length_adjusted_observation` stored on `oracle_verdicts`.
- 7-layer adversarial injection defense: tool_use schema + 8KB output truncation + XML-delimited sandboxing + meta-token regex short-circuit (`src/skill_harness/oracles/tier2/injection_guard.py`) + position-swap (PARTIAL not complete) + null-baseline distributional check (amortized with A11 confound pairs, N=30) + `[untrusted model output]` UI prefix on rationale.

*Calibration command (A34, A36, A37):*
- `calibrate <judge_id> <axis> <pair_set.jsonl> [--max-usd USD] [--daily-cap USD]` defaults to dry-run; `--execute` required.
- JSONL strict Pydantic schema (`extra='forbid'`): 8 fields per line (`pair_id`, `axis`, `prompt`, `response_a`, `response_b`, `human_preference ∈ {A,B,tie}`, `labeler_id`, `labeled_at`). NUL/control-char validation reuses Track A.2 `_check_text`.
- Three-tier admissibility state: `rejected` (N<50, refuse-to-write) / `conditional` (50≤N<100, write with credible-interval-widening penalty downstream) / `calibrated` (N≥100, all four thresholds: pairwise_agreement ≥ 0.7, position_consistency ≥ 0.8, length_controlled_agreement ≥ 0.65, cohen_kappa ≥ 0.4).
- Cohen's κ on 3-class with observed marginals (Cohen 1960): `p_e = Σ_c (n_human_c/N) × (n_judge_c/N)`. Store both `p_o` and `p_e` (chance_baseline) so audit can re-derive κ.
- v0.1 sourcing: NO starter calibration set ships; user provides. Operator-self-label tier is **value decision C2** (default: refuse).

*Storage extensions (A37):*
- New migration `migrations/evidence/0200_calibration_event_extensions.sql` (first Track C migration per A30 range 0200-0299). Adds 10 columns to `evidence.calibration_events`: `n_a, n_b, n_tie, judge_n_a, judge_n_b, judge_n_tie, length_regression_coefficient, chance_baseline, total_usd_spent, cost_ledger_run_id`. Preserves A22 `synchronous = FULL` + A21 append-only triggers.
- `CalibrationEventWrite` Pydantic model extended in `src/skill_harness/storage/models.py`. State enum gains: `"conditional"`, `"rejected"`, `"expired"`, `"uncalibrated"` (plus `"operator_self_labeled"` gated on C2 user disposition).
- Reuses Track A.2 `write_calibration_event_with_pointer` helper at `dual_write.py:145` (no signature change).

*Budget projection (A36):*
- Projection formula: `N_calls = N_pairs × 2`; cacheable prefix (system + tool schema) vs unique tail (per-pair candidates); net ~71% input-token cache reuse.
- `_warmup_first_call()` serializes first call (await first streamed token) before fanning out 2..N (cache-write must complete before reads).
- Shared `cost_ledger` envelope with ablation (per-day cap shared); per-run `--max-usd` independent. Hard ceiling on `--daily-cap` ($100) prevents operator bypass.
- Dry-run output includes `est_SE_pairwise_agreement` + `est_CI_95_width` per STAT discipline.

### TRACK D · Ablation runner

**Scope** (substantially expanded by Pre-Track-D council 2026-06-06 per A39–A52; archive `docs/council-fires/2026-06-06-pre-track-d/`): Full / Ablated_k / Null orchestration; **versioned neutral-substitution ablation operator** (not deletion); clause rendering for K-local cache reuse; sequential stopping rule; confound monitoring on all metric_library axes; budget enforcement; **sample-idempotency + crash-resumability**; **cost re-derivable from evidence**.

**Driving findings**: A8, A11, A12, A13 (original) + **A39–A52** (Pre-Track-D council 2026-06-06). Trigger input: `docs/research/landscape-2026-06-06.md` (no-twin landscape sweep; LOO-is-inferior-estimator academic warning).

**Skills loaded**: `bayesian-eval-discipline`, `claude-api` (prompt caching — A43 cache-marker discipline), `subagent-research-reliability`, `windows-claude-code-env`.

**Depends on**: A (storage), C (oracles).

**New migration**: `migrations/evidence/0300_*.sql` (Track D range 0300-0399 per A30): adds `sample_index` + `UNIQUE(run_id, clause_id, condition, sample_index)` (A40), per-call cost columns on evidence rows (A41), `ablation_operator_id`/`implementation_hash` columns (A39). Preserves A22 `synchronous=FULL` + append-only triggers.

**Exit criteria** (original 5 + the council additions):
- `run ablation <skill_id>` dry-runs by default. **Offline projection** — constructs no DB conn, no `JudgeClient`, requires no API key (A51); prints the A12-(a) one-liner + a per-clause table (`N_proj`, `est_CI_width`, status `TESTABLE | VACUOUS-EXCLUDED | NO-FALSIFYING-CASE`); terminal line `NO CALLS MADE — re-run with --execute`.
- `--execute` invokes real API calls with `cache_control:{type:ephemeral}` typed-block markers at end-of-system + end-of-skill-prefix, ablated-clause-last, warmup-or-serialize; **cache-marker assertion test** (A43).
- **Ablation operator (A39)**: deterministic matched-length semantically-null placeholder, NOT deletion. `ablation_operator_id` + `implementation_hash` stamped on every verdict at write-time; no verdict writes without it. `--show-rendered <clause_id>` exposes verbatim Full/Ablated_k/Null + operator version (A52).
- Per-condition sampling honors `N_min=8`, `N_inc=4`, `N_max=40` with sequential stop on `P(rate>0.60) ≥ 0.95` or `≤ 0.05`. **N_max-without-stop = hard stop → `UNMEASURED(underpowered)`** with achieved posterior + `stopping_reason` recorded; no batches past N_max (A44).
- `confound_events` rows emitted (threshold-triggered only, no dense matrix — A47) for all metric_library axes whose movement exceeds `k·σ_Null` (k=2.0, σ per-(run,axis) at write-time, N_null≥30 floor; below floor → detection disabled, verdicts `UNMEASURED(underpowered)`). Two-table design, exclusion via VIEW at read-time, no verdict denormalization (A45). Write-side assertion `primary_clause_id == ablated_clause_id` (A46).
- **Sample idempotency + resume (A40)**: `UNIQUE(run_id, clause_id, condition, sample_index)`; resume = set-difference vs frozen plan; retry(transient)/skip(permanent)/abort(budget); kill-at-N test resumes to exactly N, never N+1. `--resume <run_id>` flag with preview; bare re-run against incomplete prior run WARNS + names resumable run_id (A52).
- **Budget (A42)**: cap check + reservation inside ONE `writer_transaction(runtime)`; abort with terminal `run_progress.state` if `--max-usd` exceeded; distinct `--max-usd` vs `--daily-cap` errors naming the flag (A51).
- **Cost re-derivable from evidence (A41)**: per-call token/usd columns written inside the evidence transaction; `cost_ledger` is a projection; reconciler back-fills on sum-mismatch; ledger written from actual response `usage`, never projection. Kill-between-commits test shows the reconciler restores true spend.
- **`runs.completed_at` single-shot (A40-adjacent / REL-1)**: written once via a dedicated `writer_transaction(evidence)` after the last verdict commits, gated on `samples_collected == samples_planned`, never in a per-sample loop; `run_progress.state` terminal value as the last runtime write (crash-vs-complete discriminator).
- **UNMEASURED ≠ FAILED (A48)**: distinct render + exit codes (`0` all-verdicts-reached, `2` ≥1 UNMEASURED); falsifiable test that an underpowered clause exits 2.
- **Reporting honesty (A50)**: Contribution labeled `single-clause LOO; lower-bound under redundancy`. Redundancy = documented limitation; triggered `--probe-redundancy` optional (reclassify-only, never →PASSED). Random-subset surrogate = v0.2.
- **Multiplicity provenance (A49)**: every verdict carries `(run_id, clause_id, axis, comparison)`; run config records family size K×|axes| for Track E. Multiplicity correction itself is Track E (A9).
- `rich.progress` per-clause + live dual-cap footer during `--execute` (A52).
- `pytest -q` green; `mypy --strict src/` clean; `ruff check` clean; `ruff format --check` clean.

### TRACK E · Aggregation + reporting + CLI completion

**Scope**: Hierarchical Beta-Binomial posterior per clause; status derivation (PASSED / FAILED / CONFOUNDED / UNMEASURED with sub-reason); skill-vector report; `diff skill` revision comparison; `freeze` command; remaining CLI surface.

**Driving findings**: A9, A15, A17, plus PRD §16 reporting shape.

**Skills loaded**: `bayesian-eval-discipline`, `verify` (manual report-output verification).

**Depends on**: A, D.

**Exit criteria**:
- `run evaluate-skill <skill_id>` outputs the §16 vector: Passed / Failed / Confounded / UNMEASURED (subreasons) / Coverage / Full-vs-Null Contribution.
- Hierarchical posterior fits across all clauses in the skill; falls back to BH-FDR with logged warning if convergence fails.
- PASSED requires `posterior_threshold_met ∧ ≥1 frozen_case_at_current_metric_version`.
- `diff skill <a> <b>` reports per-clause status delta between revisions.
- `freeze <verdict_id>` promotes a failing verdict into `frozen_cases` with full provenance.

---

## Phase 3 — Integration + verification (after E green)

3.1 · End-to-end: `skill init ai-slop-sentinel/SKILL.md` → `run evaluate-skill --execute` → report vector matches expected shape.
3.2 · `ai-slop-sentinel` review pass across all 5 tracks (fresh context, per-track).
3.3 · `mutation-testing:mutation-testing` on the storage + aggregation modules — confirm tests would catch real bugs.
3.4 · `code-review-sentinel` on the full diff before merge.
3.5 · Update `PRD.md` → v1.1 applying the 16 amendments from `docs/COUNCIL_FINDINGS.md`.
3.6 · `verify` skill: drive the CLI through the §19 success criteria checklist; document each as a manual-verified line item.
3.7 · `superpowers:verification-before-completion` final gate.

---

## Phase 4 — Pre-launch council (before v0.1 tag)

4.1 · `adversarial-spec` on PRD v1.1 amendments — multi-LLM debate, capture disagreement.
4.2 · `azimuth` go/no-go for v0.1 tag.
4.3 · `insecure-defaults` sweep.
4.4 · `claudeception` to extract observed gotchas → `[OBSERVED]` entries on the three Tier-B skills + ai-slop-sentinel.

---

## Out of scope for v0.1 (per Council §D)

- Tier 3 Real-World Consequence oracle (D1)
- "Manufactured primitives" framing edit in PRD §1 (D2 — cosmetic, defer to v1.1 doc pass)
- Two-numerator Coverage reporting (D3)
- Extractor calibration `(extractor_id, skill_genre)` (D4)
- `agentic-actions-auditor` (no CI yet)

---

## Named council fire points

Every track below has a council fire point declared up-front. These are not optional; they are how the build maintains the coherence established in `docs/COUNCIL_FINDINGS.md`.

| When | Template | Seats | Why |
|---|---|---|---|
| Phase 1.5 (before any Track A code lands) ✅ FIRED 2026-06-04 | Custom (Storage-touching) | TEST-ARCH + SCHEMA + SECURITY + RELIABILITY | Archive: `docs/council-fires/2026-06-04-pre-track-a-storage/`. Adopted A18–A23; deferred D5–D8. Phase 1.5a + 1.5b are the resulting blockers. |
| Phase 1.5c — Pre-Track A implementation council ✅ FIRED 2026-06-04 | Storage-touching change | SCHEMA + RELIABILITY + SECURITY + TEST-ARCH | Archive: `docs/council-fires/2026-06-04-pre-track-a-impl/`. Adopted A24–A30; deferred D10–D14. Track A scope expanded; exit criteria expanded. Substantive disagreement on dual-DB ordering resolved 3-vs-1 (evidence-first) with SECURITY's runtime-first framing recorded as load-bearing dissent. |
| Pre-Track C start | Custom | EVAL-RESEARCH + SECURITY + COST + STAT | Judge module is where prompt-injection-by-adversarial-skill-output enters; STAT owns the verdict aggregation that downstream Track E depends on |
| Pre-Track D start ✅ FIRED 2026-06-06 | Custom | STAT + COST + RELIABILITY + OPERATOR-DX **+ EVAL-RESEARCH** | Archive: `docs/council-fires/2026-06-06-pre-track-d/`. EVAL-RESEARCH added (landscape sweep injected eval-methodology Qs). Adopted A39–A52; C2 resolved REFUSE; A29 confirmed; 3 citation corrections; PRD §1 reframe queued. Track D scope + exit criteria expanded above. No unresolved BLOCKER. |
| Pre-merge for any PR touching `migrations/` | Storage-touching change | SCHEMA + RELIABILITY + SECURITY + TEST-ARCH | Schema changes can silently break the append-only invariant; gate at PR time |
| Pre-v0.1 tag | Pre-tag launch council | All 9 seats | Last-look before public-facing release; full coverage |

Each fire produces findings that synthesize into a `COUNCIL_FINDINGS.md` appendix. Phase progression GATES on council disposition: a track with a BLOCKER finding does not start until the BLOCKER is resolved or explicitly downgraded with documented rationale.

## Cross-cutting invariants (every track honors)

- TDD per `superpowers:test-driven-development`: RED → GREEN → REFACTOR.
- Verification before completion: every track's exit gate requires `pytest -q` green AND `mypy --strict` clean AND `ruff check` clean.
- ai-slop-sentinel as Stop-hook reviewer (Phase 1.3) AND as end-of-track council seat.
- No commits without explicit user approval (CLAUDE.md global §3).
- Append-only invariant is load-bearing — any code that writes to an evidence table must use the repository APIs from Track A, never direct SQL.
- Cost: every API-calling code path uses prompt caching (claude-api skill) with the ablated-clause-last ordering (A13).

---

*End of plan. Resume via `.claude/state/checkpoint.md`.*
