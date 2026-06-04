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

**Scope**: idempotent migrations, repositories for skills/clauses/metric_versions/judges/calibration_events/runs/samples/oracle_verdicts/confound_events/frozen_cases, dual-DB transaction patterns, single-writer queue.

**Driving findings**: A1, A2, A3, A4 (all SCHEMA seat).

**Skills loaded**: `append-only-evidence-design`, `sqlite-expert`, `property-based-testing` (for the append-only invariant — Hypothesis test that no UPDATE/DELETE on evidence tables succeeds for arbitrary valid INSERTs).

**Exit criteria**:
- All 9 evidence tables + 5 runtime tables instantiated by `open_evidence()` / `open_runtime()`.
- Property-based test: ∀ valid INSERT on any evidence table, ∄ subsequent UPDATE or DELETE that succeeds.
- Repository module per table with typed read/write APIs.
- `pytest -q` green; `mypy --strict src/` clean.

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

**Scope**: Tier-1 mechanical metrics with audit gate; Tier-2 judge module with pairwise + position-swap discipline; calibration_events writer.

**Driving findings**: A5, A6, A7, A14.

**Skills loaded**: `llm-judge-calibration`, `claude-api`, `append-only-evidence-design` (for calibration_events writes), `windows-claude-code-env` (UTF-8 / regex traps on Windows).

**Exit criteria**:
- Tier-1 registry seeded with the 4 honestly-mechanical metrics (Hedge Index with frozen wordlist, Verbosity, Structure Score, redefined Compliance Proxy).
- Each Tier-1 metric ships with `mechanical_validity_test` that runs offline (network blocked) and produces identical output across two invocations on the same input. Pass flips `metric_versions.mechanical_validity_test_passed = 1`.
- Tier-2 judge module invokes Anthropic with pairwise + position-swapped pairs, writes `oracle_verdicts` with `position_swap_agreement` populated and `admissibility_state` resolved at write time.
- `calibrate <judge_id> <axis> <pair_set.jsonl>` command computes `pairwise_agreement`, `position_consistency`, `length_controlled_agreement`, `cohen_kappa`, writes `calibration_events` row and updates `current_calibration`.

### TRACK D · Ablation runner

**Scope**: Full / Ablated_k / Null orchestration; clause rendering reorder for cache reuse; sequential stopping rule; confound monitoring on all metric_library axes; budget enforcement.

**Driving findings**: A8, A11, A12, A13.

**Skills loaded**: `bayesian-eval-discipline`, `claude-api` (prompt caching), `subagent-research-reliability` (if any sub-research is dispatched).

**Depends on**: A (storage), C (oracles).

**Exit criteria**:
- `run ablation <skill_id>` dry-runs by default. Prints projected calls / tokens / cost using the F-COST-1 closed-form.
- `--execute` flag invokes real API calls with prompt-cache breakpoints at end-of-system and end-of-skill-prefix.
- Per-condition sampling honors `N_min=8`, `N_inc=4`, `N_max=40` defaults with sequential stop on `P(rate>0.60) ≥ 0.95` or `≤ 0.05`.
- `confound_events` rows emitted for all axes in metric_library whose movement exceeds `2·σ_Null`.
- Budget check inside writer transaction (no read-then-write race); abort with `aborted_budget` state if `--max-usd` exceeded.

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
| Phase 1.5 (before any Track A code lands) | Custom | TEST-ARCH + SECURITY + RELIABILITY | The original PRD fire under-covered security and reliability lenses; close the gap before storage code goes in |
| Pre-Track A start | Storage-touching change | SCHEMA + RELIABILITY + SECURITY + TEST-ARCH | Storage is the highest-stakes track; crash safety + adversarial input + write-time snapshot all need a coordinated review |
| Pre-Track C start | Custom | EVAL-RESEARCH + SECURITY + COST + STAT | Judge module is where prompt-injection-by-adversarial-skill-output enters; STAT owns the verdict aggregation that downstream Track E depends on |
| Pre-Track D start | Custom | STAT + COST + RELIABILITY + OPERATOR-DX | Ablation runner is the cost-hot-path and the user-visible long-running operation; dry-run UX is OPERATOR-DX's lane |
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
