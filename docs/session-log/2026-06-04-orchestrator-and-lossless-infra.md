# 2026-06-04 · orchestrator-and-lossless-infra

**Phase**: Phase 1 pre-build wiring (continued from prior session)
**Sources of truth read at start**: (this session pre-dates the session-startup skill — no SHA line was printed)
**Model**: Opus 4.7

## Context

Session began as a follow-on to the 2026-06-03 close. User invoked `/zoom-out`
to map the codebase before continuing. The map surfaced an implicit
orchestrator role with no codified contract. User asked what else was needed
for an end-to-end, looping, iterative, lossless workflow.

## Council fires this session

No council fires this session.

Rationale: the orchestrator role and lossless-infra additions are
infrastructure for the council pattern itself, not architectural decisions
that require council review. The orchestrator section codifies what the main
agent was already doing implicitly; the archive + log directories are
naming-and-format conventions, not invariants.

This decision is a candidate for retrospective review at the Phase 1.5
council fire ("did we add infrastructure that should have been council-
reviewed?").

## Decisions made

- **Orchestrator role codified** as a meta-role at top of
  `.claude/skills/dev-team-council/SKILL.md`. Pinned to Opus 4.7 per
  CLAUDE.md model-pinning. Not a review seat; dispatches review seats.
  Owns: build coherence, track sequencing, council fire decisions, exit-gate
  adjudication, PRD amendment shipping, scope discipline, cross-worktree
  merge order. Anchor: `dev-team-council/SKILL.md § Orchestrator`.

- **Session-start contract** — orchestrator MUST print
  `Sources of truth read: PRD@<sha7> · PLAN@<sha7> · COUNCIL_FINDINGS@<sha7> · checkpoint@<sha7>`
  as the first user-facing line after invoking `session-startup`. Falsifiable
  check on whether the role was performed.

- **Session-end contract** — orchestrator writes both
  `.claude/state/checkpoint.md` (current state) and a new entry in
  `docs/session-log/` (history). Two-file pattern mirrors the
  runtime/evidence DB partition.

- **Council-fire archive** at `docs/council-fires/` with per-seat raw
  outputs. Synthesis still lives in `docs/COUNCIL_FINDINGS.md`; archive
  enables audit + re-fire.

- **Audit-context-building skill ran** on the current codebase. No findings
  (skill is pure context, not vuln hunt). Captured fragility clusters for
  the orchestrator's attention: migration atomicity under autocommit,
  package-path coupling via `parents[3]`, over-strict `runs` row immutability
  trigger, missing append-only triggers on `runtime.schema_migrations`.

## Artifacts produced

- `.claude/skills/dev-team-council/SKILL.md` — Orchestrator section added (~60 lines)
- `.claude/skills/session-startup/SKILL.md` — new skill
- `docs/council-fires/README.md` — archive layout spec
- `docs/session-log/README.md` — log format spec
- `docs/session-log/2026-06-04-orchestrator-and-lossless-infra.md` — this entry

## Values decisions queued / resolved

No new values decisions this session. C1 (tie encoding) remains open per
`COUNCIL_FINDINGS.md § C`; flip trigger is still ">15% tie rate on real
Tier-2 calibration sets," which is not yet observable.

## Open questions for next session

- Should the audit-context fragility clusters (migration atomicity,
  `parents[3]` install coupling, over-strict `runs` trigger, runtime ledger
  triggers) trigger a Phase 1.5 council fire BEFORE Phase 2 begins, or are
  they acceptable for v0.1 with `[OBSERVED]` entries on
  `append-only-evidence-design/gotchas.md`? — owner: orchestrator (next
  session)

- Track manifest format (queued piece #3 from this session's architecture
  discussion) — defer until first worktree opens, per prior decision.
  Confirm at Track A dispatch time. — owner: orchestrator

- Decision realization registry + `skill audit` drift-check (queued pieces
  #5 from this session's architecture discussion) — deferred to v0.2 per
  prior decision. Reconsider if Phase 1.5 council surfaces it as a
  BLOCKER. — owner: user (deferral confirmation)

## Next gate

Phase 1.2 — permission allowlist via `/fewer-permission-prompts` (per
`.claude/state/checkpoint.md` "Where to resume" §1).
