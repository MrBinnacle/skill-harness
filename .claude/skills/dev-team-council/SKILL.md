---
name: dev-team-council
description: >
  Multi-seat parallel council review pattern for the skill-harness project,
  fired as the DEFAULT mechanism for architectural decisions, storage-touching
  changes, new external surfaces, and pre-tag launches. Names the 9-seat
  roster (5 CORE + 4 SPECIALIST), explicit trigger conditions, four standard
  council templates, and delegates dispatch mechanics to the global
  cross-talk-council-dispatch and parallel-review-disposition-schema skills.
---

# Dev-Team Council

This skill codifies the project's standing review body. The first council fire
(2026-06-03, documented in `docs/COUNCIL_FINDINGS.md`) produced 17 adopted
decisions that gate every Phase 2 track. This skill exists so the pattern is
repo-resident infrastructure, not a thing the assistant happens to remember.

## When to fire

Triggers:

- New PRD section or scope change
- New ADR-worthy architectural decision
- New external surface (CLI command, API endpoint, evidence/runtime schema table)
- Any change crossing a load-bearing invariant listed in CLAUDE.md
- Pre-merge for changes touching `migrations/`, `src/skill_harness/storage/`, or judge-prompt code paths
- Pre-launch for any version tag (v0.1, v0.2, ...) — full council with all 9 seats
- Disagreement between two prior reviewers on an architectural call (escalation)

When NOT to fire:

- Routine implementation following an already-decided invariant
- Dependency bumps with no API surface change
- Documentation-only edits
- Test-only refactors

## Roster

The roster has two tiers. The 5 CORE seats fire on every architectural
decision. The 4 SPECIALIST seats fire when their domain trigger condition is
met. All seats default to READ-ONLY per CLAUDE.md global §4 unless the main
agent escalates per-segment.

### CORE seats (fire on every architectural decision)

| # | Seat | Scope | Subagent | Cross-talk partners |
|---|---|---|---|---|
| 1 | **TEST-ARCH** | Falsifiability gate, vacuity detection, confound symmetry, clause status state machine. Owns PRD §3.4, §7, §8, §11, §15, §20. | `Plan` | STAT, SCHEMA, EVAL-RESEARCH |
| 2 | **STAT** | Beta-Binomial conjugacy, multiplicity correction, variance budgeting, sample-size floors, sequential stopping. Owns PRD §14. | `general-purpose` (WebSearch) | TEST-ARCH, EVAL-RESEARCH, COST |
| 3 | **SCHEMA** | Append-only enforcement, two-DB partition, write-time snapshot, schema migration tamper-evidence, index design. Owns PRD §6, §9, §10, §17. | `general-purpose` | TEST-ARCH, RELIABILITY, SECURITY |
| 4 | **EVAL-RESEARCH** | Prior art across LLM eval literature, judge calibration protocols (κ, ICC, pairwise-preference accuracy, position-swap), Tier-3 realizability. Owns PRD §5 Tier 2/3, §13. | `general-purpose` (WebSearch + WebFetch heavy) | STAT, TEST-ARCH, SECURITY |
| 5 | **COST** | Token economics, prompt-cache placement, sampling strategy, hard-cap enforcement, dry-run shape. Owns PRD §18 cost surface, `runtime.run_budget` table. | `general-purpose` | STAT, RELIABILITY, OPERATOR-DX |

### SPECIALIST seats (fire when domain triggered)

| # | Seat | Scope | Fires when | Subagent | Cross-talk partners |
|---|---|---|---|---|---|
| 6 | **SECURITY** | Adversarial input handling (judge outputs are attacker-influenced), prompt injection in evaluated outputs, API key surface, supply-chain mitigations. | new external input surface; key-handling code; judge prompt design; dep changes; public visibility flip | `general-purpose` | SCHEMA, EVAL-RESEARCH, RELIABILITY |
| 7 | **RELIABILITY** | Partial-run recovery, crash safety, observability, single-writer queue backpressure, retry policy, idempotency. | long-running operations; crash-recovery code; write-queue design; run state machine | `general-purpose` | SCHEMA, COST, OPERATOR-DX |
| 8 | **OPERATOR-DX** | CLI shape, error messages, dry-run UX, progress reporting, naming, exit codes. | CLI surface changes; new commands; error-path changes; public-facing config keys | `general-purpose` | COST, DOCS-DX, RELIABILITY |
| 9 | **DOCS-DX** | Onboarding clarity, README accuracy vs reality, surface drift, CHANGELOG entries, public API renames. | user-facing doc changes; release prep; public API renames | `general-purpose` | OPERATOR-DX, EVAL-RESEARCH |

## Dispatch protocol

- Every seat dispatched in **PARALLEL** using the Agent tool. Multiple Agent tool uses in ONE message run concurrently; multiple messages run serially. A council fired one seat per turn is sequentially scheduled and loses the cross-talk synthesis quality.
- Each seat's prompt MUST include the `cross-talk-council-dispatch` mandatory cross-talk block (predict what each OTHER firing seat will be RIGHT about, WRONG about, MISS).
- Each seat's prompt MUST use the `parallel-review-disposition-schema` output contract: fixed `BLOCKER / MAJOR / MINOR / OBSERVATION` decision vocabulary; per-item block with `ID / Title / Severity / PRD anchor / Claim / Evidence / Recommendation / Cross-seat`; mandatory status line as the last line of the response.
- Seats are READ-ONLY by default per CLAUDE.md global §4. Lift the read-only default per segment with bounded, audited escalation if needed.
- Each seat's prompt embeds: the question(s) being asked verbatim, locked decisions to NOT relitigate, the names + scopes of the OTHER firing seats (for cross-talk grounding), and file paths it may need to read.
- Post-return: synthesize via the `parallel-review-disposition-schema` mechanical pattern. Verify every external citation per `subagent-research-reliability` discipline before adopting any finding.
- Adopted decisions append to `docs/COUNCIL_FINDINGS.md` with seat-finding IDs as provenance. PRD amendments queue for v(N+1) doc lock, NOT piecemeal edits.

## Standard council templates

Four named templates so common fires don't require re-thinking the roster.

- **PRD pressure-test (pre-build)** — 5 CORE + SECURITY + RELIABILITY. The expanded original (the first fire's 5-seat roster + the two specialist seats it under-covered).
- **Storage-touching change** — SCHEMA + RELIABILITY + SECURITY + TEST-ARCH. 4 seats.
- **CLI / surface change** — OPERATOR-DX + DOCS-DX + COST + SECURITY. 4 seats.
- **Pre-tag launch council** — all 9 seats.

## Antecedents

- `docs/COUNCIL_FINDINGS.md` — the first council fire output (5-seat synthesis, 2026-06-03)
- `~/.claude/skills/cross-talk-council-dispatch/` — cross-talk dispatch mechanics
- `~/.claude/skills/parallel-review-disposition-schema/` — output contract / synthesis pattern
- `~/.claude/skills/subagent-research-reliability/` — citation verification discipline
- `~/.claude/skills/verbatim-content-subagent-dispatch/` — for content-producing dispatch
