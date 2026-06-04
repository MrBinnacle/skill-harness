# Pre-Track-A implementation council (2026-06-04)

**Fire**: third council fire for this project. PLAN.md row 2 of "Named council fire points" (Storage-touching change template). Distinct from the Phase 1.5 fire (`docs/council-fires/2026-06-04-pre-track-a-storage/`) which dispositioned audit-context fragility clusters; THIS fire dispositions Track A's IMPLEMENTATION DESIGN before code lands.

**Date**: 2026-06-04
**Template**: Storage-touching change (per `.claude/skills/dev-team-council/SKILL.md` § Standard templates)
**Seats**: SCHEMA + RELIABILITY + SECURITY + TEST-ARCH (4 seats)
**Dispatch**: parallel via Agent tool, single message
**Output contract**: per-Q `Disposition / Claim / Evidence / Recommendation / What-would-change-it / Cross-seat` + mandatory `STATUS:` last line
**Cross-talk**: each seat predicts what the other 3 will be RIGHT / WRONG / MISS

## Brief

The 7 design questions for Track A implementation that the council dispositions:

1. **Repository pattern shape** — per-table modules, functional vs class, Pydantic strict, surface-restriction enforcement
2. **Dual-DB transaction primitive** — when a write spans `evidence.oracle_verdicts` + `runtime.cost_ledger`, what's the ordering + recovery?
3. **Single-writer queue** — `threading.Lock` / `queue.Queue` / SQLite's `BEGIN IMMEDIATE`?
4. **Property-based test design** — Hypothesis strategy for FK + CHECK + UNIQUE constraints, `runs.completed_at` carve-out
5. **Connection lifecycle** — long-lived per process, per-call, contextmanager? Hypothesis interaction?
6. **Admissibility filter on read** — default-on filtered? SQL VIEW vs Python? Where does PRD §6 "no admissible evidence ⇒ no claim" enforcement live?
7. **Migration sequencing across worktrees** — number ranges per track, `discover()` duplicate-version guard, CODEOWNERS gate

## Outcome (all 4 seats: STATUS: BLOCKER-FOUND)

Synthesized dispositions (highest-severity rule per `parallel-review-disposition-schema`):

| Q | SCHEMA | RELIABILITY | SECURITY | TEST-ARCH | Synthesized | Adopted ID |
|---|---|---|---|---|---|---|
| Q1 | MAJOR | MAJOR | MAJOR | MAJOR | MAJOR | **A24** |
| Q2 | BLOCKER | MAJOR | MAJOR | MAJOR | BLOCKER | **A25** |
| Q3 | MAJOR | BLOCKER | MINOR | MAJOR | BLOCKER | **A26** |
| Q4 | MAJOR | MAJOR | MAJOR | BLOCKER | BLOCKER | **A27** |
| Q5 | MINOR | MINOR | MAJOR | MAJOR | MAJOR | **A28** |
| Q6 | BLOCKER | MAJOR | BLOCKER | BLOCKER | BLOCKER | **A29** |
| Q7 | MAJOR | BLOCKER | MAJOR | MAJOR | BLOCKER | **A30** |

5 BLOCKERs + 2 MAJORs. Track A spec amended; Phase 2 dispatch is gated on the amendments landing.

## Files

- `seat-SCHEMA.md` — raw SCHEMA output
- `seat-RELIABILITY.md` — raw RELIABILITY output
- `seat-SECURITY.md` — raw SECURITY output
- `seat-TEST-ARCH.md` — raw TEST-ARCH output
- `synthesis.md` — orchestrator's disposition + adopted A24-A30 + deferred D9-D12 + cross-talk validation

## Process notes

- All 4 seats came back BLOCKER-FOUND — the design surface is substantial enough that no single-seat lens cleared every Q.
- Substantive disagreement on Q2 ordering (SECURITY runtime-first vs SCHEMA + RELIABILITY + TEST-ARCH evidence-first); orchestrator adopted evidence-first 3-vs-1, citing PLAN Track D's pre-call budget check moots SECURITY's bypass concern.
- Cross-talk predictions: 6/12 prediction targets landed (synthesis.md § "Cross-talk validation" enumerates).
