# Track D Dispatch Brief — Ablation Runner

**Status:** ready to dispatch. Pre-Track-D council fired 2026-06-06 (✅), adopted A39–A52, no unresolved BLOCKER.
**Depends on:** Track A (storage, complete) + Track C (oracles, complete). Both on `origin/main` at `bb1cd1f`.
**Model:** Sonnet 4.6 (per-subtrack TDD execution). Orchestrator (Opus) writes the brief, dispatches, runs two-stage review per `superpowers:subagent-driven-development`.
**Canonical specs (this brief is self-contained; these are provenance):** `PLAN.md` "TRACK D" exit criteria · `docs/COUNCIL_FINDINGS.md` Appendix E (A39–A52) · `docs/council-fires/2026-06-06-pre-track-d/synthesis.md`.

---

## What Track D is

The **ablation runner**: the deterministic orchestration engine that, for each clause in a skill, renders the three conditions (Full / Ablated_k = exactly one clause removed-by-substitution / Null = no skill), samples subject outputs, scores them through the Track-C oracles, monitors confounds across all metric_library axes, enforces budget, and writes append-only verdicts. It is the cost-hot-path and the user-visible long-running operation. `run ablation` in `src/skill_harness/cli/main.py` is currently a stub.

## Non-negotiable invariants (do NOT violate — review-block any PR that does)

- **Deterministic Python owns ALL control flow.** Models generate content only (subject outputs, judge verdicts). No code path lets a model decide what is stored, scored, sampled, or aggregated.
- **Append-only evidence.** No UPDATE on evidence rows except the `runs.completed_at` single-shot carve-out (A20) and `run_progress` (mutable by design). Write-time admissibility snapshot, never recomputed. `evidence.db` opens `synchronous=FULL` via `open_db()` — never reach `sqlite3.connect()` directly.
- **Directional/comparative only.** Never "is this output good?" — always "does A beat B on the single axis clause N claims?" No quality scoring, no LLM self-grading, no scalar collapse.
- **Only admissible AND non-confounded verdicts aggregate.** No admissible evidence ⇒ UNMEASURED, never PASSED.
- **Pass rule (locked):** P(win_rate>0.60) ≥ 0.95 under Beta(1,1) → Beta(1+w, 1+n−w); Win=1/Tie=0.5/Loss=0.
- **Evidence-first dual-write (A25); single-writer BEGIN IMMEDIATE + busy_timeout (A26).** No in-process queue.
- **CLI command set is locked (PRD §18).** No new commands — only flags within `run ablation`.

## TDD + gates (every subtrack)

RED → GREEN → REFACTOR per `superpowers:test-driven-development`. Each subtrack exit: `PYTHONHASHSEED=0 pytest -q -m "not live"` green · `mypy --strict src/` clean · `ruff check` clean · `ruff format --check` clean. Windows env: UTF-8, CRLF, regex traps per `windows-claude-code-env`. Halt-on-ambiguity: if the spec is unclear, STOP and ask the orchestrator — do not guess on a load-bearing invariant.

---

## Subdivision (sequential — D.2 depends on D.1, D.3 on D.2)

### D.1 — Foundations: migration 0300 + ablation operator + condition renderer

**Scope.** The storage + rendering substrate the runner needs. Migration design is already decided by A39/A40/A41 (routine implementation of an already-decided invariant — no separate council fire per CLAUDE.md).

- **Migration `migrations/evidence/0300_track_d_ablation.sql`** (Track D range 0300–0399 per A30). Preserves A22 `synchronous=FULL` + existing append-only triggers. Adds:
  - `sample_index INTEGER NOT NULL` on `samples` + `UNIQUE(run_id, clause_id, condition, sample_index)` (A40 idempotency key).
  - Per-call cost columns on the evidence rows that produced an API call (`input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`, `usd`) — written inside the evidence transaction so spend is durable at `synchronous=FULL` and re-derivable (A41).
  - `ablation_operator_id TEXT` + `ablation_operator_hash TEXT` columns on `oracle_verdicts` (and/or `samples` as appropriate) — provenance stamped at write-time (A39).
  - Append-only triggers extended to cover the new columns; the A20 `runs.completed_at` carve-out untouched.
- **AblationOperator** (`src/skill_harness/ablation/operator.py`): a versioned artifact producing a **deterministic, byte-stable, matched-length, semantically-null placeholder** for a removed clause. NOT deletion. `ablation_operator_id` = stable id; `implementation_hash` = sha256 of the implementation (mirror the Tier-1 `metric_versions` discipline). The deterministic layer constructs the substituted prompt — never a model.
- **Condition renderer** (`src/skill_harness/ablation/render.py`): given a skill + clause inventory + a target clause k, render `Full`, `Ablated_k` (clause k replaced by the operator's placeholder), `Null` (no skill). Cache-marker placement per A43: `system` as typed blocks with `cache_control:{type:ephemeral}` at end-of-system + end-of-skill-prefix; clause-under-ablation rendered last so the shared prefix is maximized (K-local reuse). Renderer returns the exact request structure; a test asserts the cache markers are present and correctly placed (mock at SDK boundary per A32 precedent).

**Exit criteria / tests.**
- Migration applies cleanly; new UNIQUE constraint + columns present; append-only still enforced (smoke test mirrors existing append-only tests). A double-INSERT on the same `(run_id, clause_id, condition, sample_index)` raises IntegrityError.
- `AblationOperator` is deterministic: `op.render(clause) == op.render(clause)` byte-equal; placeholder token-length matches the removed clause within tolerance; `implementation_hash` stable across runs.
- Renderer: Full/Ablated_k/Null produced correctly; Ablated_k differs from Full only by the operator substitution at clause k; cache-marker assertion test passes; **verbosity axis of Ablated_k vs Full is not perturbed by length** (the falsifying-case demonstration for A39 — substitution must not contaminate the length axis the way deletion would).
- Gates green.

### D.2 — Orchestration engine: sampling, stopping, confound, budget, resume, cost

**Scope.** The core runner (`src/skill_harness/ablation/runner.py` + aggregation-feeding writes). Depends on D.1.

- Full/Ablated_k/Null sampling loop honoring `N_min=8, N_inc=4, N_max=40`, sequential stop on `P(rate>0.60) ≥ 0.95` or `≤ 0.05`. **N_max-without-stop = hard stop → `UNMEASURED(underpowered)`** with achieved posterior + `stopping_reason ∈ {passed, failed, underpowered_nmax, budget_exhausted}` recorded on the run config snapshot (A44). No batches past N_max.
- **Confound monitoring (A47):** score every sample on ALL registered metric_library axes in-memory; σ(Null) estimated per-(run, axis) at write-time with N_null≥30 floor, k=2.0; emit a `confound_events` row ONLY when |delta| > k·σ_Null (threshold-triggered, no dense per-sample×axis matrix). Below the N_null floor → confound detection disabled for that axis, affected verdicts `UNMEASURED(underpowered)`. Uncalibrated Tier-2 axes excluded from σ(Null). Write-side assertion: `primary_clause_id == ablated_clause_id` (A46). Confound stays two-table; exclusion is the read-time VIEW, never a verdict-row state (A45).
- **Budget (A42):** cap check + reservation inside ONE `writer_transaction(runtime)`; pre-call gate uses worst-case projected next-call cost, post-call write reconciles to actual; abort writes terminal `run_progress.state` if `--max-usd` exceeded.
- **Idempotency + resume (A40):** resume = set-difference of existing `(run_id, clause_id, condition, sample_index)` tuples vs the frozen plan in `runs.config_json`; issue calls only for missing slots. Per-call policy: retry-with-backoff (transient 429/500/network) / skip-and-record (permanent 400) / abort-run (budget).
- **Cost re-derivable (A41):** write per-call token/usd onto evidence rows inside the evidence transaction, from the actual response `usage` block (never the projection); `cost_ledger` is a projection; reconciler back-fills any run whose Σevidence.usd ≠ Σcost_ledger.usd.
- **`runs.completed_at` single-shot (REL-1):** written once via a dedicated `writer_transaction(evidence)` after the last verdict commits, gated on `samples_collected == samples_planned`, never in a per-sample loop; `run_progress.state` terminal value as the last runtime write (crash-vs-complete discriminator).
- **Multiplicity provenance (A49):** every verdict carries `(run_id, clause_id, axis, comparison)`; run config records family size K×|axes| for Track E. (Multiplicity *correction* is Track E, not here.)
- **Warmup-or-serialize (A43/COST-4):** first render of a shared prefix serialized so the cache-write lands before reads.

**Exit criteria / tests.** Sequential-stop tests (pass/fail/underpowered_nmax); kill-at-1,732/4,000 resume test → exactly 4,000 samples, never 4,001; confound threshold-trigger test + write-side directionality assertion; budget cap race test (`test_budget_check_serializes`); kill-between-commits cost-reconciler test restores true spend; `runs.completed_at` written exactly once. Gates green.

### D.3 — CLI surface: dry-run, execute, resume, progress, reporting honesty

**Scope.** The operator-facing `run ablation` command (`src/skill_harness/cli/main.py`). Depends on D.2.

- **Dry-run default, offline (A51):** constructs no DB conn, no `JudgeClient`, requires no API key (pull-forward TC-SLOP-001/002); prints the A12-(a) one-liner + a per-clause table (`clause# | axis | conditions | N_proj(min..max) | est_CI_width | status{TESTABLE | VACUOUS-EXCLUDED | NO-FALSIFYING-CASE}`); terminal line `NO CALLS MADE — re-run with --execute`.
- `--execute` invokes the real runner; distinct `--max-usd` (per-run) vs `--daily-cap` (trailing-24h) errors naming the offending flag.
- **`--resume <run_id>`** flag with a resume-preview line; bare re-run against an incomplete prior run WARNS + names the resumable run_id (no silent fresh-start/double-spend) (A52).
- **`--show-rendered <clause_id>`** prints verbatim Full/Ablated_k/Null + `ablation_operator_version` (a run is untrustworthy if the operator isn't inspectable) (A52).
- **UNMEASURED ≠ FAILED (A48):** FAILED red `FAILED (P(win)≤.05)`; UNMEASURED yellow `UNMEASURED(<subreason>)`. Exit codes: `0` all-verdicts-reached, `2` ≥1 UNMEASURED, non-2 reserved for hard errors. Test: an underpowered clause exits 2, not the FAILED path.
- **`rich.progress`** per-clause + live dual-cap footer `spent $X / cap $Y (run) · $Z / $W (day)` during `--execute` (emitted from the deterministic orchestrator, not model workers).
- **Reporting honesty (A50):** Contribution labeled `single-clause LOO; lower-bound under redundancy`; "absence of delta is not absence of contribution." Redundancy = documented limitation; `--probe-redundancy` triggered probe optional (reclassify-only, never →PASSED). (Random-subset surrogate is explicitly v0.2 — do NOT build it.)

**Exit criteria / tests.** Dry-run runs with no `ANTHROPIC_API_KEY` set and constructs no client/conn; exit-code contract test; resume-preview + bare-rerun-warns test; `--show-rendered` output test; UNMEASURED-vs-FAILED render + exit-code test. Gates green.

---

## Out of scope (v0.2 — do NOT build)

Random-subset/ContextCite surrogate estimator; blanket joint-ablation sweep; multi-process sampling (D11); `operator_self_labeled` tier (C2 = REFUSE); cost reconciler as a `skill audit` subcommand (the reconciler *logic* is in D.2; exposing it as a subcommand is D7/v0.2).

## Dispatch order

D.1 → (two-stage review) → D.2 → (two-stage review) → D.3 → (two-stage review) → Track D ai-slop-sentinel review → cherry-pick to main. One implementer at a time (sequential; D.2/D.3 depend on prior). Worktree: `git worktree add ../youwontdoit-track-d feat/track-d-ablation` (or per-subtrack worktrees per Track C precedent).
