# 2026-06-04 · track-a-1-ship

**Phase**: Phase 2 — Track A.1 dispatched, returned, reviewed, cherry-picked onto `main`
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@(local, gitignored)
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 (Track A.1 subagent via Agent tool)
**User invocation**: "Proceed" (after the dispatch-prep entry's stated "no commits, awaiting user approval" gate)

## Context

Earlier in this same session, the orchestrator drafted `docs/dispatch/track-a-brief.md` and committed it as `43a9229`. The previous session-log entry (`2026-06-04-track-a-dispatch-prep.md`) reported "no code or commits this session" and queued the Track A.1 dispatch for a future session. The user said "Proceed," interpreted as green-light for the dispatch sequence — which superseded the earlier conservative session-end framing.

## Decisions made

- **Interpretation of "Proceed"**: treat as commit-and-dispatch approval. The prior session-log entry's "no commits this session" was a forecast, not a contract; the user's drive signal overrides.
- **Worktree mechanism**: Agent tool's `isolation:"worktree"` (harness-native) per `superpowers:using-git-worktrees` Step 1a. Manual `git worktree add` not used.
- **Dispatch prompt shape**: three-part per `verbatim-content-subagent-dispatch`. Notably embedded the A.1 scope verbatim in the prompt itself, NOT just a pointer to `docs/dispatch/track-a-brief.md` — this turned out load-bearing because the harness's worktree forked from `3b74457` (BEFORE the orchestrator's `43a9229` dispatch-prep commit), so the brief file was not visible to the subagent. The verbatim-embed discipline absorbed this gracefully; pointing-not-embedding would have produced a halt.
- **`complete_run()` acceptance**: the A20 column-scoped carve-out function. Orchestrator accepted the naming as principled — descriptive, single-purpose, A24-banned-prefix-compliant, not evasive. Docstring cites A20 + A24 verbatim. No COUNCIL_FINDINGS amendment this session (CLAUDE.md §3 forbids piecemeal Phase 2 PRD/finding edits — the v1.1 doc-lock at Phase 3 is the right venue).
- **Integration mechanic**: subagent committed A.1 on its auto-named worktree branch (`worktree-agent-a81babb923f1917fd`, tip `d1f023e`); orchestrator cherry-picked onto main (`b9faeef`). Linear history preserved. No merge commit.
- **Dead branch retention**: `worktree-agent-a81babb923f1917fd` left in place because content-merged but SHA-divergent (cherry-pick creates a new commit); `git branch -d` reports not-merged + safety net blocks `-D`. User can prune. Non-blocking.

## Council fires this session

None. Track A.2 may warrant a Pre-Track-D fire planning ahead, but that's a separate decision; A.1 is implementation-following-A24-A30, not new architecture.

## Artifacts produced

- **Code (cherry-picked into main as `b9faeef`):**
  - `src/skill_harness/storage/repositories/__init__.py`
  - `src/skill_harness/storage/repositories/evidence/__init__.py` + 10 per-table modules (`skills.py`, `clauses.py`, `metric_versions.py`, `judges.py`, `calibration_events.py`, `samples.py`, `oracle_verdicts.py`, `confound_events.py`, `frozen_cases.py`, `runs.py`)
  - `src/skill_harness/storage/repositories/runtime/__init__.py` + 5 per-table modules (`skill_imports_staging.py`, `run_progress.py`, `current_calibration.py`, `run_budget.py`, `cost_ledger.py`)
  - `src/skill_harness/storage/models.py` — 15 Pydantic Write models with `ConfigDict(strict=True, extra='forbid', frozen=True)`, `_FORBIDDEN_CTRL` pre-compiled regex (NUL + C0 control reject; `\t\n\r` allowed), configurable `OUTPUT_TEXT_MAX_BYTES=256KB` + `CLAUSE_TEXT_MAX_BYTES=64KB` at module top
  - `tests/test_evidence_repo_surface.py` — AST-walker enforcement using stdlib `ast`; self-verifying `TestAstWalkerDetector` + enforcement `TestEvidenceRepoSurface` + module-count sanity
  - `tests/test_models_validators.py` — RED-first model validator tests (NUL/C0 reject, `\t\n\r` allow, oversize reject, frozen/extra=forbid)
  - `tests/test_repo_roundtrip.py` — round-trip per table across all 15 repos
- **Docs:**
  - `docs/session-log/2026-06-04-track-a-1-ship.md` (this entry).
- **Checkpoint refresh** (local-only, gitignored): next-gate updated to Track A.2.

## Verification (post-cherry-pick, on main)

- `pytest -q`: 92 passed (16 baseline + 76 new = 58 round-trip + 7 AST + 11 model validator)
- `mypy --strict src/`: 0 errors in 25 source files
- `ruff check`: clean
- `ruff format --check`: clean (run in worktree; re-verify in main on next session if desired)

## Observations / learnings

- **Worktree-forked-from-stale-HEAD**: Agent tool's `isolation:"worktree"` forked from `3b74457` even though main was at `43a9229` when the dispatch fired. Possible explanation: harness may snapshot HEAD before processing my commit, OR forks from origin/main, OR there's a sync delay. Practical takeaway: NEVER rely on the subagent reading uncommitted files in the orchestrator's working tree. The verbatim-embed-in-prompt discipline is load-bearing precisely for this case. Confirms `verbatim-content-subagent-dispatch`'s "pointing-not-embedding is the named failure mode" was the right call.
- **`complete_run()` pattern**: a known carve-out that doesn't trip the A24 AST-walker. For Track D (which uses runs), this is the canonical call to stamp `completed_at`. Code reviewers should recognize the pattern; not a new architectural decision.
- **`OracleVerdictWrite` "unused import" Pyright diagnostic** was stale (caught a mid-dispatch state); subagent's final `test_models_validators.py` imports only `ClauseWrite` and `SkillWrite`. The orchestrator's Pyright-from-main "Import skill_harness.storage.models could not be resolved" errors were similarly an IDE-level artifact (Pyright unaware of the worktree's editable install); subagent's `mypy --strict` in the worktree was the authoritative check.

## Values decisions queued / resolved

None new. C1 (tie encoding) still open per COUNCIL_FINDINGS §C.

## Open questions for next session

- **Track A.2 worktree branch flow**: A.1's worktree branch lingers as `worktree-agent-a81babb923f1917fd`. Decide whether A.2 dispatches into a new harness-managed worktree (forking from current main = `b9faeef` post-A.1) and accepts the same dead-branch pattern, or whether the orchestrator should pre-create + check out `feat/track-a-storage` and dispatch into that. Recommendation: continue with harness-managed worktrees + cherry-pick (simpler; the dead branches are cosmetic).
- **Pre-Track-D council fire timing**: the A29 confound JOIN directionality question (`primary_clause_id` vs `affected_clause_id`) is queued for EVAL-RESEARCH at Pre-Track-D. Track A.3 will land the VIEW with the A29-verbatim shape + an in-SQL comment flagging the pending question. Fire Pre-Track-D before Track D dispatch (gated by A + C completion per PLAN).
- **Dead branch cleanup**: `git branch -D worktree-agent-a81babb923f1917fd` requires safety-net override; user can run manually.

## Next gate

**Phase 2 — Track A.2 subagent dispatch.** Per `docs/dispatch/track-a-brief.md` §3a A.2 (transaction primitive + dual-write + StorageContext + fault-injection + crash-recovery + concurrent-writers serialization test). Drivers A25, A26, A28.
