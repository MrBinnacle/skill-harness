# CLAUDE.md

Guidance for Claude Code in this repo. **Skill Harness** = deterministic eval
framework for LLM skills; measures clause-level contribution via differential
ablation, not output-quality scoring (axis: "does A beat B on clause N's claimed
axis?"). Expanded intent + invariant rationale: `.claude/reference/invariant-rationale.md` (load on demand).

**Sources of truth** (read in order before non-trivial work):
1. `PRD.md` — product spec (v1.0; v1.1 amendments queued in COUNCIL_FINDINGS)
2. `docs/COUNCIL_FINDINGS.md` — adopted decisions, 5-seat council 2026-06-03, 17 decisions, with sources
3. `PLAN.md` — locked v0.1 plan (5 worktree tracks, exit criteria, skill loadings)
4. `.claude/state/checkpoint.md` — session state, next-step entry

## Dev-team council (default decision mechanism)

Multi-seat council review is the **default** for architectural decisions, not ad-hoc.
Roster/triggers/dispatch: `.claude/skills/dev-team-council/SKILL.md`. First fire
(2026-06-03) → COUNCIL_FINDINGS.md (17 decisions gating Phase 2).

**FIRE before writing code** when any holds:
- New ADR-worthy architectural decision
- Change touches `migrations/`, `src/skill_harness/storage/`, or judge-prompt paths
- Change crosses a load-bearing invariant below
- New external surface (CLI command, schema table, public API)
- Two prior reviewers disagree on an architectural call

**Do NOT fire:** routine impl of an already-decided invariant · dep bumps with no surface change · doc-only edits · test refactors.

Findings synthesized per `parallel-review-disposition-schema`, appended to COUNCIL_FINDINGS.md. PRD amendments queue for the next doc-lock PR — never applied piecemeal.

## Skill kit (load per phase)

- `bayesian-eval-discipline` — Beta-Binomial traps, N_min floor, multiplicity. Track D + E.
- `llm-judge-calibration` — pairwise mode, position swap, κ thresholds. Track B + C.
- `append-only-evidence-design` — SQLite triggers, two-DB partition, write-time snapshot. Track A.
- `ai-slop-sentinel` — fresh-context review at every track exit + as Stop hook (Phase 1.3).
- `claude-api` — Anthropic SDK + prompt caching. Track C + D.
- `sqlite-expert` — SQLite operational guidance. Track A.
- `windows-claude-code-env` — UTF-8 / CRLF / regex traps. All tracks.
- `superpowers:test-driven-development` — RED → GREEN → REFACTOR per track.
- `superpowers:using-git-worktrees` — Phase 2 isolation.
- `superpowers:subagent-driven-development` — Phase 2 track dispatch.

## Model pinning

- **Opus 4.7** (`claude-opus-4-7`): synthesis, council fires, plan-locking, ADR authoring, ambiguity-heavy planning.
- **Sonnet 4.6** (`claude-sonnet-4-6`): per-track TDD execution, schema migrations, CLI wiring, throughput.

Switch via `/config` or pin via dispatch.

## Repo status

Greenfield — no code/tests/manifests yet. Do **not** fabricate `pytest` / `pip install` / CLI invocations as if they work; check repo state first. Target stack per PRD §17: Python deterministic runner + SQLite persistence (nothing scaffolded).

## Load-bearing invariants

Contracts that make the harness mean what it claims; violating any is a bug even if tests pass. Rationale/failure-modes: `.claude/reference/invariant-rationale.md`.

**Control-flow ownership** — Deterministic Python owns orchestration, sampling, scoring, storage, aggregation. Stochastic workers (subjects, injectors, judges) generate content only; a path letting a model decide what is stored/scored/aggregated is broken even if it "works."

**Evidence model** — SQLite, append-only: no `UPDATE` on evidence rows, no `DELETE` outside explicit retention jobs. Provenance (source, oracle, version, admissibility) recorded at **write time**, never recomputed. A22 asymmetric durability: `evidence.db` = `PRAGMA synchronous = FULL`; `runtime.db` = `synchronous = NORMAL`. Always go through `open_db()` (provides connection-scoped `foreign_keys = ON`); bypassing it to call `sqlite3.connect()` directly degrades durability + drops FK enforcement — review-block.

**Aggregation rules** — Only verdicts that are **both** `admissible` AND `non-confounded` enter aggregation (inadmissible/confounded rows stored for audit only). No admissible evidence ⇒ clause is `UNMEASURED`, never `PASSED`. Skills reported as vectors (`Passed / Failed / Confounded / Unmeasured / Coverage / Contribution`), never a scalar.

**Clause discipline** — A clause with no constructible falsifying case is **vacuous** (metadata, excluded from testing). Not "tested" until ≥1 falsifying case exists in the frozen regression suite. `Coverage = tested_clauses / total_clauses`.

**Confound handling** — When ablating clause N moves another clause's axis beyond threshold, result is `FLAGGED_CONFOUNDED`, not pass/fail. A contaminated delta is never reported as clean evidence.

**Oracle tiering** — Tier 1 (mechanical, deterministic counting) preferred whenever a metric exists. Tier 2 (human-calibrated judge) inadmissible without a calibrated `(judge_id, axis)` record — judge is an instrument, never source of truth. Tier 3 (real-world consequence) terminal, highest authority. Calibration is axis-specific: **no cross-axis inheritance.**

**Evaluation shape** — All evaluation directional/comparative: `A beats B on axis X`. Forbidden: quality scoring, holistic grading, LLM self-grading. Required conditions per test: `Full` / `Ablated` (exactly one clause removed) / `Null` (no skill); measurements are deltas between conditions.

**Metric provenance** — Mechanical oracles are versioned artifacts; every frozen case stores metric identity, version, and implementation hash so re-audit is possible when a metric changes.

**Explicitly unaudited** — Rhythm metrics / sentence-length variance: **no frozen cases may be minted from them** until validated. Known trap, not an oversight.

## Pass rule

Clause passes when `P(win_rate > 0.60) ≥ 0.95` under a `Beta(1,1)` prior with posterior `Beta(1+w, 1+n−w)`, `w` = wins (Win=1, Tie=0.5, Loss=0). Changing either threshold is a `[values decision]` — surface to the user, do not silently retune.

## CLI surface (spec'd, not built)

Per PRD §18 — do not invent flags beyond these without updating the PRD:
- `skill init` — import a skill artifact and extract clauses
- `skill clauses` — inspect clause inventory
- `run ablation` — execute single-clause ablation
- `run evaluate-skill` — full suite
- `diff skill` — compare skill revisions
- `freeze` — promote a failure into the regression suite

## Language / tooling

Python (PRD §17). When code lands: `pytest` for tests; `python -m py_compile` for quick syntax check; verify every schema change preserves the append-only invariant before applying.

## Pipeline safety

Frozen regression suite + evidence table are append-only **by design**; no in-place mutation, even to "clean up" a stale row (corrupts the audit trail). Any write to `evidence`, `frozen_cases`, or `calibration` must support `--dry-run` and default to it during development.
