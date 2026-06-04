# Phase 1.5 — Pre-Track-A Storage Review (2026-06-04)

## Brief

Disposition four storage-layer fragility clusters surfaced by `audit-context-building`
before Track A code lands. Fire dispatched per `.claude/skills/dev-team-council/SKILL.md`
"Storage-touching change" template + the explicit Phase 1.5 row in `PLAN.md`'s
"Named council fire points" table.

## Clusters dispositioned

- **M1** — Migration apply not atomic under autocommit (`src/skill_harness/storage/migrations.py:103-108`)
- **M2** — `parents[3]` package-path coupling silently fails under wheel install (`migrations.py:24-26`)
- **M3** — `runs_completed_at_once` trigger over-strict (entire row immutable post-completion) (`migrations/evidence/0001_initial.sql:203-205`)
- **M4** — `runtime.schema_migrations` lacks BEFORE UPDATE/DELETE triggers (`migrations/runtime/0001_initial.sql:9-14`)

## Seats fired (4 of 9; per "Storage-touching change" template)

| Seat | Subagent type | Status |
|---|---|---|
| TEST-ARCH | Plan | BLOCKER-FOUND |
| SCHEMA | general-purpose | BLOCKER-FOUND |
| RELIABILITY | general-purpose | BLOCKER-FOUND |
| SECURITY | general-purpose | BLOCKER-FOUND |

## Raw outputs

- `seat-TEST-ARCH.md`
- `seat-SCHEMA.md`
- `seat-RELIABILITY.md`
- `seat-SECURITY.md`

## Synthesis

See `synthesis.md` for the orchestrator's synthesis, adopted-decision IDs, deferred-to-v0.2 items, and PRD/PLAN amendments queued.

## Dispatch discipline applied

- `cross-talk-council-dispatch` — each seat predicted RIGHT/WRONG/MISS for the other three
- `parallel-review-disposition-schema` — fixed BLOCKER/MAJOR/MINOR/OBSERVATION vocabulary, per-finding output block, mandatory status line as last line of each seat's output
- `verbatim-content-subagent-dispatch` — cluster descriptions embedded verbatim in each seat's prompt
- `subagent-research-reliability` — external citations (Python sqlite3 docs, SQLite docs) verified before adoption into synthesis
