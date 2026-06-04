# 2026-06-04 · phase-1-closeout

**Phase**: Phase 1 closeout — 1.2 permissions + 1.3 Stop hook + 1.5a code + 1.5b docs
**Sources of truth read at start**: PRD@7c6f5f9 · PLAN@6443f9d · COUNCIL_FINDINGS@10e4897 · checkpoint@c556a04 (post-`/compact` continuation; first turn invoked the session-startup skill as designed)
**Model**: Opus 4.7

## Context

Session began after `/compact` of the long 2026-06-04 day-arc (orchestrator + lossless infra → Phase 1.5 council fire → 1.2 permissions → 1.3 Stop hook → end-of-context). User invoked `/compact` then immediately said "Follow the SOP and proceed." The session-startup skill fired correctly: SHA line printed first, where-the-build-is paragraph, open values decisions, open questions from prior session-log, next gate.

User picked the menu option **Phase 1.5a code fixes** as the next gate.

## Council fires this session

None. Phase 1.5a/b are downstream of the council fire that happened in the prior turn arc (`docs/council-fires/2026-06-04-pre-track-a-storage/`). This session executed against that disposition; no new fires required.

## Decisions made

- **Phase 1.5a commit shape**: single cohesive `feat(storage): apply Phase 1.5a council fixes (A18-A22)` commit (`97f73fd`) rather than 5 per-finding commits. Surfaced as a 3-option AskUserQuestion; user picked single-commit. Finding IDs (A18–A22) traceable through `docs/COUNCIL_FINDINGS.md` Appendix B and the commit body lists each by ID.
- **A18 statement-splitter design**: chose `sqlite3.complete_statement` over naive `str.split(';')` because every append-only enforcement trigger has a `BEGIN ... END` body with an embedded semicolon. `complete_statement` honors SQLite's parser semantics for trigger bodies. Tested explicitly via `test_split_statements_preserves_trigger_bodies`.
- **Connection-leak hardening on A19 boundary**: `open_evidence`/`open_runtime` now wrap `apply_pending()` in try/close so a mid-apply raise doesn't leak the SQLite Connection. Caught via pytest's `PytestUnraisableExceptionWarning` after the first green test run.
- **Phase 1.5b mirror placement**: COUNCIL_FINDINGS A4 gains a "Trust partition" subsection rather than a new A24 finding, since the prose is a mirror of SECURITY.md's threat-model and the architectural-log expectation is "decisions, not duplication." SECURITY.md is the canonical statement; A4's mirror is for the architectural log's self-containment.

## Artifacts produced

- `.claude/settings.json` — added `Bash(command -v *)` allowlist entry (Phase 1.2). 1 net new (rest of frequent commands already auto-allowed by Claude Code's built-in readonly list)
- `.claude/hooks/stop-ai-slop-sentinel-trigger.sh` — Phase 1.3 hook script (envelope-parsing per `claude-code-stop-hook-envelope` skill; validated against 4 synthetic transcripts + real transcript)
- `src/skill_harness/storage/errors.py` (new) — `StorageError` base + `BootstrapError`, `MigrationApplyError`, `MigrationTamperedError` (relocated, re-exported for back-compat)
- `src/skill_harness/storage/migrations.py` — A18 atomic apply_pending, A19 BootstrapError raise, A22 synchronous PRAGMA split, connection-leak-safe error paths
- `migrations/evidence/0002_runs_trigger_split.sql` (new) — A20 column-scoped runs triggers
- `migrations/runtime/0002_schema_migrations_triggers.sql` (new) — A21 META ledger triggers
- `tests/test_smoke.py` — 8 new tests (16/16 total): A19 evidence + runtime BootstrapError raises; A22 synchronous == 2 + == 1; A20 immutable-columns abort; A21 schema_migrations UPDATE/DELETE abort; A18 atomic-rollback; `_split_statements` trigger-body integrity
- `SECURITY.md` — A23 threat-model expansion (trust partition + filesystem substitution boundary + PRAGMA scope + synchronous asymmetry)
- `docs/COUNCIL_FINDINGS.md` — A4 "Trust partition" subsection mirroring SECURITY clauses (1)+(2)
- `CLAUDE.md` — Evidence model section third bullet on synchronous asymmetry
- `.claude/state/checkpoint.md` — refreshed for Phase 1 complete state
- `docs/session-log/2026-06-04-phase-1-closeout.md` — this entry

## Commits this session

1. `0213edb` — `chore(perms): add Bash(command -v *) allowlist per Phase 1.2`
2. `3fadcd7` — `feat(hooks): install ai-slop-sentinel Stop hook per Phase 1.3`
3. `97f73fd` — `feat(storage): apply Phase 1.5a council fixes (A18-A22)`
4. `0bfb9e2` — `docs(security): apply Phase 1.5b council fixes (A23 threat model)`

Plus 2 prior-arc commits (`acdd4af` + `9d4ecb8`) carried forward. Total: 6 unpushed at start of session, all 6 pushed at end-of-session.

## Values decisions queued / resolved

No new values decisions this session. C1 (tie encoding) remains open per `COUNCIL_FINDINGS.md § C`.

## Open questions for next session

- **Pre-Track-A council fire (PLAN row 2)** — orchestrator must dispatch SCHEMA + RELIABILITY + SECURITY + TEST-ARCH on Track A's IMPLEMENTATION plan (repositories, dual-DB transactions, single-writer queue, property-based invariant test design). This is distinct from the Phase 1.5 fire that dispositioned audit-context fragility clusters. — owner: orchestrator (next session)
- **Worktree branching** — `feat/track-a-storage` + `feat/track-b-extractor` + `feat/track-c-oracle-library` per PLAN §2. — owner: orchestrator (after Pre-Track-A council disposition)
- **Stop hook live-activation status** — settings.json watcher may not have picked up the Phase 1.3 hook in the session it was created. Activation requires opening `/hooks` UI menu OR next session start. The Phase 1.5a code-edit turn would have been the first trigger candidate; whether the hook fired is observable from the session's hook-trigger log. — owner: user (one-time check; report findings before Phase 2 dispatch)

## Next gate

**Phase 2 — Pre-Track-A council fire** (PLAN.md "Named council fire points" row 2). Then `superpowers:using-git-worktrees` to set up parallel Tracks A + B + C, then `superpowers:subagent-driven-development` dispatch per PLAN.md `## TRACK A/B/C` sections.
