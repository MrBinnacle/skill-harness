# 2026-06-04 · track-a-dispatch-prep

**Phase**: Phase 2 entry, dispatch-prep substep — orchestrator-only session, no code or commits
**Sources of truth read at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@52e78e8
**Model**: Opus 4.7 (orchestrator)
**User invocation**: "Spin up the council and SOP" → then meta-correction: "I'm not the technical SME in this loop." → then: "Always find the MOST knowledgable/expert/resource relevant to whatever 'what should I do here...'."

## Context

User opened with "Spin up the council and SOP" — read as: run `session-startup` (SOP) + invoke `dev-team-council` so the orchestrator role + roster + dispatch protocol are in context. After SOP output (SHA line + state summary), the orchestrator surfaced three options (Track A now / Pre-Track C first / both) as a user-facing choice. **The user corrected the framing twice in succession**: (a) "I'm not the technical SME in this loop" — denying that technical sequencing is a values decision; (b) "Always find the MOST knowledgable/expert/resource relevant to whatever 'what should I do here...'" — reinforcing that uncertainty should route to expert resources, not the user. This is the second time this discipline has needed reinforcement in 24h (first was the SOP-grounded-decisions correction; see `feedback-sop-grounded-decisions`).

The correction shifted the session shape from "decision point pending user input" to "drive the next gate." Per `dev-team-council` orchestrator role (Track sequencing) + PLAN.md §Phase 2 + checkpoint §Where-to-resume, the next gate is Track A subagent dispatch. Per CLAUDE.md §9 (Context Hygiene: clear and reload at ~40%), an in-session dispatch + mid-session adjudication-on-return would saturate orchestrator context; safer to draft the brief in this session and dispatch in a fresh-context next session.

## Council fires this session

None. Orchestrator-only session.

## Decisions made

- **Track A dispatch shape**: 4 sequential subagent dispatches (A.1 → A.4) with two-stage review between (per `superpowers:subagent-driven-development` per-task dispatch doctrine), each in its own Agent tool `isolation: "worktree"` call. Master brief at `docs/dispatch/track-a-brief.md` orients the subagent; per-subtrack dispatch prompts derive from the brief at fire time.
- **Worktree mechanism**: Agent tool `isolation: "worktree"` parameter (harness-native), NOT manual `git worktree add`. Rationale: per `superpowers:using-git-worktrees` Step 1a + Red Flags, manual `git worktree add` when a native tool exists "creates phantom state your harness can't see or manage." Orchestrator stays in `main` — does not enter a worktree itself (orchestrator writes only checkpoint/session-log/COUNCIL_FINDINGS/PRD/PLAN, all of which belong on `main`).
- **Brief shape**: three-part per `verbatim-content-subagent-dispatch` — role identity + instrument binding + output contract with halt-on-ambiguity. PLAN.md TRACK A + COUNCIL_FINDINGS A24–A30 + CLAUDE.md load-bearing invariants embedded VERBATIM, not as pointers. Pointing-not-embedding is the named failure mode; the brief avoids it.
- **Defer dispatch to next session**: this session's context utilization is too high for mid-session adjudication on Track A return (~7 test families, ~3 modules, 1 migration, 2 docs). Next session reads brief + dispatches A.1 with full Opus headroom.

## Artifacts produced

- `docs/dispatch/track-a-brief.md` — master Track A subagent dispatch brief. ~7k words. Embeds PLAN §Phase 2 Track A + COUNCIL_FINDINGS A24, A25, A26, A27, A28, A29, A30 + CLAUDE.md load-bearing invariants verbatim. Subdivides into A.1/A.2/A.3/A.4 commits with file-level scope per subtrack. Includes halt-on-ambiguity discipline + return contract.
- `.claude/state/checkpoint.md` — refreshed: last-session entry, next-gate entry, dispatch sequence pointing at the brief.
- `docs/session-log/2026-06-04-track-a-dispatch-prep.md` (this entry).
- `~/.claude/projects/.../memory/feedback-non-technical-sme.md` — new feedback memory: user is not the technical SME; orchestrator owns technical sequencing/dispatch/test-architecture; never surface those as "which would you prefer?".
- `~/.claude/projects/.../memory/feedback-route-to-most-expert.md` — new feedback memory (supersedes scope of non-technical-SME): for any "what should I do here?" route to the most knowledgeable expert/resource (skill, council seat, canonical doc, Context7 MCP) — never default to user. Includes a question-class → expert-resource triage table.
- `~/.claude/projects/.../memory/MEMORY.md` — index updated with both new entries.

## Values decisions queued / resolved

No new values decisions. C1 (tie encoding) remains the only open values decision per COUNCIL_FINDINGS §C.

## Open questions for next session

- **A29 confound JOIN directionality** (`primary_clause_id` vs `affected_clause_id`) — flagged in A29 verbatim for EVAL-RESEARCH at Pre-Track-D council. The brief instructs the Track A subagent to implement per A29 verbatim (`primary_clause_id`) with an in-SQL comment flagging the pending confirmation. Not a Track A blocker. — owner: EVAL-RESEARCH (Pre-Track-D council fire)
- **Pre-Track C council timing** — orchestrator's call: fire in the same session as Track C dispatch, OR after Track A return. No forcing function. — owner: orchestrator (next or next-next session)
- **`lossless-orchestrator-infrastructure` skill promotion** — still in `~/.claude/skills/_quarantine/`. Awaiting §1.5 manual review. — owner: user (skill promotion is a quality-curation call, not technical)

## Verification

This session:
- Read all 4 sources of truth + 2 recent session-log entries + 4 skills (`session-startup`, `dev-team-council`, `superpowers:using-git-worktrees`, `verbatim-content-subagent-dispatch`).
- Wrote 1 dispatch brief + 1 checkpoint update + 1 session-log entry + 2 memory files + 1 MEMORY.md index update.
- No code changes. No migrations changes. No tests changes. No commits.
- Brief verification: master brief embeds PLAN TRACK A + A24, A25, A26, A27, A28, A29, A30 + load-bearing invariants verbatim. Subdivision A.1–A.4 maps 1:1 to PLAN exit-criteria bullets. Halt-on-ambiguity discipline covers all known spec gaps (A29 directionality + dual-write call sites + CODEOWNERS scaffolding).

## Next gate

**Phase 2 — Track A subagent dispatch (A.1 first).**

Next-session protocol:
1. `session-startup` skill — print SHA line.
2. Read `docs/dispatch/track-a-brief.md`.
3. Derive A.1 dispatch prompt from brief §3a A.1 subsection.
4. Dispatch via Agent tool: `subagent_type: "general-purpose"`, `model: "sonnet"`, `isolation: "worktree"`.
5. On return: review diff (fresh-context `ai-slop-sentinel` + `code-review-sentinel`); orchestrator stages + commits per CLAUDE.md §3; rename branch to `feat/track-a-storage`; proceed to A.2 dispatch.

If user wants to commit the dispatch-prep artifacts (this session's working-tree changes — brief + checkpoint + session-log + memory) before opening the next session, the working tree at end-of-session is:

```
?? docs/dispatch/
M  .claude/state/checkpoint.md
?? docs/session-log/2026-06-04-track-a-dispatch-prep.md
```

Plus the two memory files (outside the repo). Suggested commit message:

```
docs(dispatch): draft Track A subagent dispatch brief + session log
```

Per CLAUDE.md §3 NEVER list, the orchestrator does NOT auto-commit. Awaiting user approval.
