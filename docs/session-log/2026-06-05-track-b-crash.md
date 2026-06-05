# 2026-06-05 · track-b-crash

**Phase**: Phase 2 — Track B background dispatch crashed mid-build; session closeout addendum
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@(local, refreshed for Track-B-dispatched state)
**Model**: Opus 4.7 (orchestrator)
**Trigger**: harness notification — Track B subagent (id `a093403c36eb3fa85`) terminated with `API Error: 500 Internal server error` after 708,830 ms (~12 min) and 53 tool uses.

## Context

The prior session-log entry (`2026-06-05-track-b-dispatch.md`, commit `bdf22ae`) recorded Track B dispatched in background with closeout pending the subagent's eventual return. That entry assumed the return would be a clean READY_FOR_COMMIT in a future session.

The subagent crashed instead, mid-build. Anthropic API server-side 500 — not a subagent or worktree fault. The 12-minute / 53-tool-use runtime indicates the subagent had completed most of its module writing before the crash; partial work is preserved in the worktree.

This entry is the addendum to the prior closeout, documenting the crash and the next-session recovery protocol.

## Decisions made

- **Preserve the worktree** (do NOT remove it this session): the partial work has potential salvage value. Subagent reportedly wrote `extractor/{__init__, errors, models, parser, claude, pipeline}.py` + `cli/main.py` modifications + `tests/extractor/test_parser.py` (and likely more). Inspection deferred to next session per the user's "fresh orchestrator context window" directive.
- **Document a 3-option triage matrix** in checkpoint §Next-gate so next session has decision support without re-deriving: salvage / re-dispatch / in-context completion.
- **Flag the one known real bug**: `cli/main.py` lines 69 + 72 reference `_print_result` which is not defined (Pyright `reportUndefinedVariable`). Other Pyright diagnostics are stale-cache + Click decorator misreads (`Cannot access attribute "group" for class "FunctionType"` — the `cli` symbol's type was inferred as `FunctionType` instead of `click.Group` after `@click.group()` decoration; this is a known Pyright weakness with Click, not a real bug).

## Council fires this session

None.

## Artifacts produced

- `docs/session-log/2026-06-05-track-b-crash.md` (this entry).
- Checkpoint refresh: Track B state changed from "in-flight, return pending" to "crashed, salvage required"; next-session triage protocol added.

## Verification

Main is unchanged this turn — at `bdf22ae` post the prior session-log commit. No code committed; no gates re-run (no need — orchestrator did not touch code).

The worktree at `.claude/worktrees/agent-a093403c36eb3fa85` is in an indeterminate state (uncommitted, possibly half-written, contains a known bug). Verification gates would fail; do not run them in closeout, defer to next session.

## Observations

- **Anthropic 500 mid-dispatch** is a new failure mode for this build. Prior Track A subagent dispatches all completed cleanly. The 500 is server-side; no recovery action against the SDK is warranted. Future dispatches should consider: longer dispatch tasks (~12 min+) have non-trivial probability of hitting transient API errors. Mitigation: subagent could opt for more incremental checkpoints (e.g., commit after each module group), but that conflicts with the "subagent stages, orchestrator commits" pattern. Re-dispatch on API failure is the cleaner recovery.
- **Background dispatch crash visibility**: the harness correctly notified completion-with-error. The `task-notification` carries enough metadata (duration_ms, tool_uses, output-file path) for the orchestrator to assess without reading the full output transcript.
- **Pyright stale-cache pattern reinforced**: many of the "import could not be resolved" errors are the standard stale-Pyright-from-outside-worktree noise (`anthropic`, `pydantic`, `click`, `pytest`, `skill_harness.*`). One real bug (`_print_result` undefined) was caught by `reportUndefinedVariable`. Triage discipline: filter Pyright noise by separating import-resolution failures (almost always stale) from semantic errors (often real).

## Values decisions queued / resolved

None new.

## Open questions for next session

- **Salvage vs re-dispatch decision**: requires inspecting the partial worktree state. Decision matrix in checkpoint §Next-gate.
- **API failure threshold for re-dispatch**: if a re-dispatched Track B also hits an API 500, that's signal to (a) wait + retry, OR (b) split the dispatch into smaller subtracks. Unlikely needed but documented.
- **Pre-Track-C council fire**: still queued for next session, after Track B completion. Question draft of 7 items lives in checkpoint.

## Next gate

**Next session protocol** (per refreshed checkpoint):
1. Session-startup SOP — print SHA line.
2. **Triage Track B partial state** — `git status` + `git diff main` in the worktree, run gates as-is to map the failure surface.
3. **Decision**: salvage (small completion subagent), re-dispatch (full Track B re-run), or in-context completion (only if minimal — preserve orchestrator context for council fire).
4. **Pre-Track-C council fire** — fires after Track B lands.
