# 2026-06-04 · phase-1-5-council-fire-2

**Phase**: Phase 1.5 — pre-Track-A council fire (continuation of 2026-06-04 session)
**Sources of truth read at start**: (continuation session; session-startup skill was published this same day — the SHA line is mandated for FUTURE sessions, not this mid-session continuation)
**Model**: Opus 4.7

## Context

User chose Path A from prior turn ("fire a Phase 1.5 council fire before Phase 2 begins"). Fire dispatched per `.claude/skills/dev-team-council/SKILL.md` "Storage-touching change" template + the Phase 1.5 row in PLAN.md's "Named council fire points" table. Four seats fired in parallel.

## Council fires this session

- **Fire**: 2026-06-04 pre-Track-A storage review
- **Seats**: TEST-ARCH (Plan), SCHEMA (general-purpose), RELIABILITY (general-purpose), SECURITY (general-purpose)
- **Outcome**: all 4 returned `STATUS: BLOCKER-FOUND`
- **Archive**: `docs/council-fires/2026-06-04-pre-track-a-storage/` — 4 raw seat outputs + README + synthesis
- **Adopted finding IDs**: A18 (M1 atomicity), A19 (M2 raise-on-empty), A20 (M3 column-scoped triggers), A21 (M4 runtime ledger triggers), A22 (synchronous=FULL for evidence), A23 (trust-model docs)
- **Deferred**: D5 (terminal_state column), D6 (db_identity), D7 (skill audit CLI), D8 (importlib.resources packaging)

## Decisions made

- **META-vs-DOMAIN framing for `schema_migrations` adopted** (A21). 3 seats (TEST-ARCH + SECURITY + RELIABILITY) framed the runtime ledger as a meta-bookkeeping table whose append-only nature is independent of the runtime/evidence partition. SCHEMA dissented (treated as intentional partition asymmetry). 3-vs-1 vote on cross-talk-aware grounds adopts META framing. SCHEMA's "uniformity" concern documented but does not outweigh the tamper-evidence integrity loss. Anchors: `docs/COUNCIL_FINDINGS.md § A21`.

- **A3 bound confirmed by SECURITY**: `current_calibration` rewrites affect only FUTURE verdicts; past verdicts have already snapshotted their `admissibility_state` at write time. The bound is real and load-bearing. Anchor: SECURITY-F4.

- **F3 intent resolution (load-bearing answer)**: column-immutable per SCHEMA; the implementation contradicts its own comment + name + error message. Trigger split into two named-column triggers via new migration. Anchor: `COUNCIL_FINDINGS.md § A20`.

- **Phase 1.5a (code) + 1.5b (docs)** inserted into PLAN.md as new pre-Phase-2 gates. ~150 LOC + 2 new migrations + 3 new smoke tests + typed exception module. Track A is now blocked on 1.5a completion.

- **PRD v1.1 amendments queued** — 4 new amendments (all §17) in addition to the original 16 from the first council fire. Apply as a single doc-lock PR per CLAUDE.md "PRD amendments queue for v(N+1) doc lock, NOT piecemeal edits."

## Artifacts produced

- `docs/council-fires/2026-06-04-pre-track-a-storage/seat-TEST-ARCH.md` — raw output
- `docs/council-fires/2026-06-04-pre-track-a-storage/seat-SCHEMA.md` — raw output
- `docs/council-fires/2026-06-04-pre-track-a-storage/seat-RELIABILITY.md` — raw output
- `docs/council-fires/2026-06-04-pre-track-a-storage/seat-SECURITY.md` — raw output
- `docs/council-fires/2026-06-04-pre-track-a-storage/README.md` — archive overview
- `docs/council-fires/2026-06-04-pre-track-a-storage/synthesis.md` — orchestrator synthesis
- `docs/COUNCIL_FINDINGS.md` — Appendix B added (A18–A23 + D5–D8 + cross-talk validation); PRD amendments table extended with 4 new rows
- `PLAN.md` — Phase 1.5 marked fired; Phase 1.5a + 1.5b sections inserted; council fire points table updated

## Values decisions queued / resolved

No new values decisions this session. C1 (tie encoding) remains open per `COUNCIL_FINDINGS.md § C`.

## Open questions for next session

- **Acceptance of A18–A23 dispositions** — orchestrator's synthesis adopted META-vs-DOMAIN over SCHEMA dissent on A21. Confirm user concurrence. — owner: user

- **Phase 1.5a execution shape** — single PR (since all changes touch storage and the new migrations are sequenced) OR per-decision branches (A18, A19, A20, A21, A22 each in its own commit on the same branch)? Recommendation: single PR with logically-grouped commits, since the 5 decisions interact (A22 changes `open_db()` signature; A18 uses the new signature; A20+A21 are migrations the new code applies). — owner: orchestrator (next session, before dispatch)

- **Should `session-startup` skill be invoked at the top of this very next-action turn** to demonstrate the contract on a real session start? (This continuation session does not count.) — owner: orchestrator (next session)

## Next gate

Phase 1.2 (permission allowlist via `/fewer-permission-prompts`) remains the immediate next step. Order:
1. **1.2** — permission allowlist
2. **1.3** — ai-slop-sentinel Stop hook (read `claude-code-stop-hook-envelope` first)
3. **1.4** — CLAUDE.md skill-kit + model-pinning verify
4. **1.5a** — apply A18–A22 code fixes (NEW; blocks Track A)
5. **1.5b** — apply A23 doc updates (NEW; can land in parallel)
6. **Phase 2** — parallel Track A + B + C worktrees
