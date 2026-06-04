# Session Log — Append-Only Journal

Sessions write here on close. Distinct from `.claude/state/checkpoint.md`:

- `checkpoint.md` = **current state**, overwritten each session
- `docs/session-log/` = **history**, append-only

The two pair like `runtime.db` (mutable) and `evidence.db` (append-only). Same
discipline; same reason.

## Layout

```
docs/session-log/
  <YYYY-MM-DD>-<slug>.md
```

One file per session. Slug is short kebab-case naming the session's main
output: `orchestrator-and-lossless-infra`, `phase-1-2-allowlist`,
`track-a-storage-red`.

If a single calendar day contains multiple sessions, suffix `-2`, `-3`, etc.

## Required entries

Every session-log file MUST contain:

```markdown
# <YYYY-MM-DD> · <slug>

**Phase**: <entered, completed>
**Sources of truth read at start**: PRD@<sha7> · PLAN@<sha7> · COUNCIL_FINDINGS@<sha7> · checkpoint@<sha7>
**Model**: <Opus 4.7 | Sonnet 4.6 | mixed>

## Council fires this session

- Fire: <date>-<reason> · seats: <list> · finding IDs: <list> · archive: <path>
- (If none: "No council fires this session — <reason>: routine implementation
  per decision A_N" OR "no qualifying triggers".)

## Decisions made

- <decision> · rationale · anchors: <PRD § | COUNCIL_FINDINGS § | PLAN §>

## Artifacts produced

- <path> · purpose · SHA on commit (if committed)

## Values decisions queued / resolved

- C_N: <state>
- (If none new: omit section.)

## Open questions for next session

- <question> — owner: <orchestrator | user | track>

## Next gate

<one sentence pointing at the next PLAN entry or checkpoint resume line>
```

## Discipline

- Append-only: do not edit prior session-log entries. Errors get corrections in
  a later entry, like a ship's log.
- Citations to PRD / PLAN / COUNCIL_FINDINGS use § anchors so future readers
  can navigate forward.
- The orchestrator writes this. Subagents return findings to the orchestrator
  who synthesizes into the entry.
- The session-startup skill reads the most recent two entries to seed
  context. Keep them scannable — bullet points over prose.
