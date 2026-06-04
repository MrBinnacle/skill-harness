---
name: session-startup
description: >
  Invoke at the start of every session before any other action touches the
  codebase. Reads the four sources of truth (PRD, PLAN, COUNCIL_FINDINGS,
  checkpoint), prints the source-of-truth SHA line that proves re-entry was
  performed, surfaces queued values decisions, names the next gate. Companion
  to the dev-team-council orchestrator role.
---

# Session Startup

This skill enforces the orchestrator role's session-start contract (codified
in `.claude/skills/dev-team-council/SKILL.md` § Orchestrator). Without it,
the orchestrator's promise to read state before acting is unverifiable.

## When to invoke

- Every new session, before any tool call or response touches the codebase.
- After a `/compact` that may have lost mid-session orchestrator state.
- At the start of any subagent dispatched as a "next track" entry point.

## What it does

1. Read in order:
   - `PRD.md` — product spec
   - `PLAN.md` — locked execution plan
   - `docs/COUNCIL_FINDINGS.md` — adopted decisions + amendment queue
   - `.claude/state/checkpoint.md` — last session's resume entry
2. Compute the short SHA (7 chars) of each file's current content.
3. List the most recent two entries in `docs/session-log/` if present.
4. List unresolved `[values decision]` items from COUNCIL_FINDINGS § C.
5. Identify the next gate from checkpoint's "Where to resume" section.

## Output contract (mandatory first line)

The first user-facing line of the orchestrator's response after invocation
MUST match this exact format:

```
Sources of truth read: PRD@<sha7> · PLAN@<sha7> · COUNCIL_FINDINGS@<sha7> · checkpoint@<sha7>
```

A session that proceeds without printing this line has skipped re-entry.
Correct by aborting whatever action is in flight and re-invoking the skill.

## What to surface after the SHA line

- One paragraph: where the build is now (phase, recent council fires,
  blockers).
- Open values decisions queue (numbered list, with C-IDs from
  COUNCIL_FINDINGS).
- The next gate (one sentence; e.g., "Phase 1.2 — permission allowlist").
- Anything in the most recent session-log entry's "open questions" section.

## Inputs

The four sources of truth above, plus:
- `docs/session-log/` (if present) — most recent two entries
- `docs/council-fires/` (if present) — most recent fire's archive path

## Related skills

- `dev-team-council` — defines the orchestrator role this skill enforces
- `cross-talk-council-dispatch` — dispatch mechanics for council fires
- `parallel-review-disposition-schema` — synthesis pattern for council outputs

## Anti-rationalizations

| Thought | Why wrong | Required action |
|---|---|---|
| "I read those files in the last session" | Each session starts with no memory of prior tool results | Read them again. The SHA line proves it. |
| "I can skip the SHA line and just summarize" | The SHA line is the falsifiable check on the role | Print it verbatim, exact format. |
| "Only Phase 2 sessions need this" | Drift hides in routine sessions too | Every session, every time. |
| "Files haven't changed since last session" | Maybe true; the SHA line is still the contract | Compute and print the SHAs anyway. |
