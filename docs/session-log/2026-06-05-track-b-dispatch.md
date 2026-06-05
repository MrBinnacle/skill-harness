# 2026-06-05 · track-b-dispatch

**Phase**: Phase 2 — Track B dispatched in background; session closeout for fresh context next iteration
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@(local, refreshed after slop-cleanup)
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 (Track B subagent, background)
**User invocation**: "Proceed" → then mid-iteration: "begin preparing for session closeout (synthesis deserves a fresh orchestrator context window) as this session finishes"

## Context

Continuing the iterative-drive pattern. Prior iteration completed Track A end-of-track ai-slop-sentinel review + cleanup (`ff7a9dd` + `a4f3b29`, pushed to origin). With Track A SLOP-CLEAN, the next gates per checkpoint were Track B dispatch (unblocked) and Pre-Track-C council fire (4-seat parallel; gates Track C).

Orchestrator decision (per `feedback-non-technical-sme` + `feedback-route-to-most-expert`): dispatch Track B in **background** this iteration; defer Pre-Track-C council fire to next iteration. Rationale: Track B is a substantial multi-module build (~30–60 min subagent runtime) that the harness can run autonomously; Pre-Track-C council fire is a 4-seat parallel dispatch requiring fresh orchestrator context for synthesis. Running both this iteration would saturate orchestrator context.

User then signaled closeout mid-iteration. Track B left running; will return into next session's context.

## Decisions made

- **Track B as single dispatch (not sub-tracked)**: PLAN.md presents Track B as one scope unit; A15 + A16 + D4 + the Track A storage substrate adjudicate the architectural shape. No need to mirror Track A's A.1–A.4 subdivision (which was driven by the 1.5c council expansion specific to storage).
- **Architectural shape set by orchestrator before dispatch** (not surfaced to user — technical sequencing per fluency profile):
  - Module home `src/skill_harness/extractor/` (parser / models / claude / pipeline / errors)
  - Functional API consistency with storage A24 pattern
  - Anthropic SDK + tool_use structured output; model `claude-sonnet-4-6` per CLAUDE.md model pinning
  - Mocked Claude in unit tests; one `@pytest.mark.live` smoke test (skipped by default; uses pre-existing `live` marker in pyproject.toml)
  - 3 SKILL.md test corpora: ai-slop-sentinel (real, dense), `tests/extractor/fixtures/frontmatter_only.md`, `tests/extractor/fixtures/mostly_prose.md`
  - `mechanical_vacuous` detection deferred to post-Track-C integration (metric_library is Track C scope); Track B's vacuity_flag is binary `none` vs `semantic_vacuous_pending_review`
  - CLI `skill init <path> [--execute]` — defaults to dry-run per CLAUDE.md pipeline safety; Claude API call DOES happen even in dry-run (extraction is the only way to preview)
- **Background dispatch over foreground**: subagent has `run_in_background=true`. Orchestrator stops here for closeout per user instruction. Track B's return will be a harness notification in next session.

## Council fires this session

None. Track B has no gating council per PLAN.md (correct — A15 + A16 + D4 adjudicate the architectural shape). Pre-Track-C council deferred.

## Artifacts produced

- **Track B dispatch prompt**: composed inline in this turn's `Agent` tool call. Not committed as `docs/dispatch/track-b-brief.md` (Track A had a brief for reference across multiple subagent sessions; Track B is one dispatch, so the inline prompt is sufficient — but a future archaeology trace requires reading this session-log + the prior turn's Agent tool call).
- **Checkpoint refresh**: Track B in-flight state + 2-gate next-session resume (Track B return handling + Pre-Track-C council fire timing + question draft).
- **Session-log entry**: this file.

## Verification

Pre-dispatch baseline confirmed: 149 passed, mypy --strict + ruff + ruff format clean on `a4f3b29`. No code changes this iteration outside the subagent's worktree.

## Observations

- **Architectural decisions inlined in the dispatch prompt**: this is a deviation from the lossless-orchestrator-infrastructure pattern (which would put architectural calls into COUNCIL_FINDINGS amendments). The rationale: these are implementation calls within the bounds A15/A16/D4 + Track A storage already established; they don't warrant a new finding ID. If the Track B subagent's return reveals one of these calls was wrong (e.g., functional API doesn't fit the extractor's stateful Anthropic client), the cleanup will surface it.
- **`~/.claude/skills/ai-slop-sentinel/SKILL.md` access**: a known risk. The skill is global (lives outside the worktree). If the subagent's environment cannot read it, the recovery is to copy it into `tests/extractor/fixtures/`. The dispatch prompt instructs the subagent to halt with NEEDS_CONTEXT in that case.
- **Live API cost**: the subagent was permitted ONE live API test invocation against the ai-slop-sentinel fixture (gated behind `@pytest.mark.live`). Expected cost: tiny (a few cents). If subagent runs it and reports clauses, that's the v0.1 ground truth for ≥5 clauses extracted (per PLAN exit criterion).

## Values decisions queued / resolved

None new. C1 (tie encoding) still open per COUNCIL_FINDINGS §C.

## Open questions for next session

- **Track B return shape**: assume READY_FOR_COMMIT until proven otherwise. If NEEDS_CONTEXT on the ai-slop-sentinel path: copy into fixtures + send back. If BLOCKED on Anthropic SDK shape ambiguity: load `claude-api` skill in orchestrator context + consult Context7 MCP for current SDK docs.
- **Pre-Track-C council fire question list**: draft above in checkpoint §Next-gate. Refine before firing.
- **Track B dead branch cleanup**: will be `worktree-agent-a093403c36eb3fa85` after cherry-pick. Same `-D` pattern as before.

## Next gate

**Two gates queued for next session:**
1. **Track B return adjudication** — review, verify gates, cherry-pick onto main, push to origin.
2. **Pre-Track-C council fire** — 4-seat parallel (EVAL-RESEARCH + SECURITY + COST + STAT) per PLAN.md "Named council fire points" row 3. Synthesis appends to COUNCIL_FINDINGS Appendix D; adopted findings become A31-AXX; gates Track C dispatch.

Both fire in one iteration if context permits.
