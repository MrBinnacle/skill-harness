# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Skill Harness** — a deterministic evaluation framework for LLM skills (instruction files, prompt modules, behavioral overlays) that measures clause-level contribution via differential ablation rather than output quality scoring. The harness never asks "is this output good?" — it asks "does output A beat output B on the single axis claimed by clause N?"

**Sources of truth** (read in this order before non-trivial work):
1. `PRD.md` — product spec (v1.0; v1.1 amendments queued in `docs/COUNCIL_FINDINGS.md`)
2. `docs/COUNCIL_FINDINGS.md` — adopted architectural decisions from the 5-seat pressure-test council (2026-06-03), with sources
3. `PLAN.md` — locked v0.1 implementation plan (5 worktree tracks, exit criteria, skill loadings)
4. `.claude/state/checkpoint.md` — session state, next-step entry

The invariants below are the ones most likely to be silently violated by code that "looks right."

## Skill kit (load these per phase)

- `bayesian-eval-discipline` — Beta-Binomial traps, N_min floor, multiplicity. Track D + E.
- `llm-judge-calibration` — pairwise mode, position swap, κ thresholds. Track B + C.
- `append-only-evidence-design` — SQLite triggers, two-DB partition, write-time snapshot. Track A.
- `ai-slop-sentinel` — fresh-context review at every track exit + as Stop hook (Phase 1.3).
- `claude-api` — Anthropic SDK + prompt caching strategy. Track C + D.
- `sqlite-expert` — broader SQLite operational guidance. Track A.
- `windows-claude-code-env` — UTF-8 / CRLF / regex traps on Windows. All tracks.
- `superpowers:test-driven-development` — RED → GREEN → REFACTOR per track.
- `superpowers:using-git-worktrees` — Phase 2 isolation.
- `superpowers:subagent-driven-development` — Phase 2 track dispatch.

## Model pinning

- **Opus 4.7** (`claude-opus-4-7`) for: synthesis, council fires, plan-locking, ADR authoring, ambiguity-heavy planning.
- **Sonnet 4.6** (`claude-sonnet-4-6`) for: per-track TDD execution, schema migrations, CLI wiring, throughput work.

Switch via `/config` or pin via dispatch.

## Repo status

Greenfield. No code, tests, or package manifests exist yet. Do **not** fabricate `pytest` / `pip install` / CLI invocations as if they work — check the repo state first. The target stack per PRD §17 is a Python deterministic runner with SQLite persistence; nothing has been scaffolded.

## Load-bearing invariants

These are the contracts that make the harness mean what it claims. A change that violates any of them is a bug even if tests pass.

### Control-flow ownership
- The deterministic Python layer owns orchestration, sampling, scoring, storage, and aggregation.
- Stochastic model workers (subjects, injectors, judges) generate content only. A code path that lets a model decide what gets stored, scored, or aggregated is broken — even if it "works."

### Evidence model
- Persistence is SQLite, **append-only**. No `UPDATE` against evidence rows. No `DELETE` outside explicit retention jobs.
- Provenance (source, oracle, version, admissibility state) is recorded at **write time** and never recomputed. Recomputing admissibility at read time would let calibration drift retroactively rewrite history — forbidden.

### Aggregation rules
- Only verdicts that are **both** `admissible` AND `non-confounded` enter aggregation. Inadmissible and confounded rows are stored for audit but cannot affect results.
- **No admissible evidence ⇒ no claim.** A clause with zero admissible measurements is `UNMEASURED`, never `PASSED`.
- Skills are reported as vectors (`Passed / Failed / Confounded / Unmeasured / Coverage / Contribution`). Never collapse to a scalar score.

### Clause discipline
- A clause without a constructible falsifying case is **vacuous** — metadata, not a contract — and is excluded from testing.
- A clause is not "tested" until ≥1 falsifying case exists in the frozen regression suite. `Coverage = tested_clauses / total_clauses`.

### Confound handling
- Ablating clause N may move axes belonging to other clauses. When that cross-axis delta exceeds threshold, the result is `FLAGGED_CONFOUNDED`, not pass/fail. A contaminated delta must never be reported as clean evidence.

### Oracle tiering
- **Tier 1** (mechanical, deterministic counting) is preferred whenever a metric exists.
- **Tier 2** (human-calibrated judge) is inadmissible without a calibrated `(judge_id, axis)` record. The judge is an instrument, never the source of truth.
- **Tier 3** (real-world consequence) is the terminal oracle, highest authority.
- Calibration is axis-specific. **No cross-axis inheritance.**

### Evaluation shape
- All evaluation is directional/comparative: `A beats B on axis X`.
- Forbidden: quality scoring, holistic grading, LLM self-grading.
- Required conditions per test: `Full` / `Ablated` (exactly one clause removed) / `Null` (no skill). Measurements are deltas between conditions.

### Metric provenance
- Mechanical oracles are versioned artifacts. Every frozen case stores metric identity, version, and implementation hash so re-audit is possible when a metric changes.

### Explicitly unaudited
- Rhythm metrics / sentence-length variance: **no frozen cases may be minted from them** until validated. This is a known trap, not an oversight.

## Pass rule

Clause passes when `P(win_rate > 0.60) ≥ 0.95` under a `Beta(1,1)` prior with posterior `Beta(1+w, 1+n−w)` where `w` is the wins count (Win=1, Tie=0.5, Loss=0). Changing either threshold is a `[values decision]` — surface to the user, do not silently retune.

## CLI surface (spec'd, not yet built)

Per PRD §18 — do not invent flags beyond these without updating the PRD:

- `skill init` — import a skill artifact and extract clauses
- `skill clauses` — inspect clause inventory
- `run ablation` — execute single-clause ablation
- `run evaluate-skill` — full suite
- `diff skill` — compare skill revisions
- `freeze` — promote a failure into the regression suite

## Language / tooling

Python (per PRD §17). When code lands:
- `pytest` for tests
- `python -m py_compile` for quick syntax check
- Verify every schema change preserves the append-only invariant before applying

## Pipeline safety

The frozen regression suite and the evidence table are append-only **by design**. A script that mutates either in place — even to "clean up" a stale row — violates the core invariant and corrupts the audit trail. Any write to `evidence`, `frozen_cases`, or `calibration` tables must support `--dry-run` and default to it during development.
