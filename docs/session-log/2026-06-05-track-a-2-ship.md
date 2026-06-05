# 2026-06-05 · track-a-2-ship

**Phase**: Phase 2 — Track A.2 dispatched, returned, reviewed, cherry-picked onto `main`
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@96bd348
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 (Track A.2 subagent via Agent tool)
**User invocation**: "Spin up council and proceed" (after pruning the A.1 dead branch)

## Context

Following the same pattern as the 2026-06-04 A.1 ship. User opened with the now-customary "Spin up council and proceed" — interpreted (per `feedback-non-technical-sme` + `feedback-route-to-most-expert` memories) as run-SOP + dispatch-the-next-gate, without surfacing technical sequencing as a values decision. Track A.2 was the next gate per `docs/dispatch/track-a-brief.md` §3a A.2 and the prior checkpoint's "Next gate" entry.

## Decisions made

- **A.2 dispatch shape**: same envelope as A.1 — Agent tool with `subagent_type:"general-purpose"`, `model:"sonnet"`, `isolation:"worktree"`. Dispatch prompt embedded A.2 deliverables verbatim from the brief §3a A.2 + concrete dual-write call site signatures + logger structured-field requirements + the FailOnInsertProxy hint anticipating the sqlite3.Connection C-built-in limitation.
- **Spec finding accepted**: `FailingOnInsertProxy` / `FailOnBeginProxy` duck-typing pattern is the right workaround for fault injection on `sqlite3.Connection.execute()`. The C built-in is not `patch.object`-able. The dual_write helpers don't isinstance-check, so duck-typed proxies satisfy the type contract at runtime. Documented in both test files' module docstrings.
- **`upsert_current_calibration` accepted**: minor extension of A.1's `repositories/runtime/current_calibration.py`. Runtime tables are mutable per A2 partition; runtime repos permit mutation symbols per A24; the AST-walker only scans evidence/. No surprise.
- **Integration mechanic**: same as A.1 — subagent committed on auto-named worktree branch (`worktree-agent-a816f4ecabe9f025d`, tip `dae2b51`); orchestrator cherry-picked onto main (`d84d0ad`). Linear history. The harness's worktree forked from `c304319` (current main) this time — A.1's stale-HEAD pattern did not recur, possibly because origin/main and local main were already in sync.

## Council fires this session

None. A.2 is implementation-following-A25-A26-A28; no new architectural decisions.

## Artifacts produced

- **Code (cherry-picked into main as `d84d0ad`):**
  - `src/skill_harness/storage/transaction.py` — `writer_transaction(conn)` context manager
  - `src/skill_harness/storage/dual_write.py` — `write_verdict_with_cost_entry` / `write_run_start_with_budget` / `write_calibration_event_with_pointer` (evidence-first per A25 verbatim, structured WARNING log on runtime failure, ATTACH DATABASE forbidden docstring)
  - `src/skill_harness/storage/context.py` — `StorageContext` dataclass (leak-safe `__enter__`, suppress-on-close `__exit__`)
  - `src/skill_harness/storage/__init__.py` — A26 paragraph + `__all__` re-exports
  - `src/skill_harness/storage/repositories/runtime/current_calibration.py` — `upsert_current_calibration` (INSERT OR REPLACE)
- **Tests (+21, total 113 green):**
  - `tests/test_transaction.py` — 6 (commit / rollback / propagation / suppress / multi-statement / integration)
  - `tests/test_dual_write_partial.py` — 6 (3 helpers × 2 cases: runtime INSERT failure + evidence INSERT failure)
  - `tests/test_crash_recovery.py` — 3 (kill-between-evidence-COMMIT-and-runtime-BEGIN; WAL truncation durability; multi-statement migration idempotence)
  - `tests/test_concurrent_writers_serialize.py` — 2 (two-thread contention + single-thread baseline)
  - `tests/test_storage_context.py` — 4 (opens both / closes on clean exit / closes on body exception / accepts string paths)
- **Docs:**
  - `docs/session-log/2026-06-05-track-a-2-ship.md` (this entry).
- **Checkpoint refresh** (local-only, gitignored): next-gate updated to Track A.3.

## Verification (post-cherry-pick, on main)

- `pytest -q`: 113 passed (92 baseline + 21 new)
- `mypy --strict src/`: 0 errors in 28 source files
- `ruff check`: clean
- `ruff format --check`: clean

## Observations

- **Brief discoverability now works**: the dispatch brief committed in A.1's session lived in main at dispatch time; A.2's subagent rebased onto main and read the brief from its worktree. Confirms the "embed the brief verbatim in the dispatch prompt" was load-bearing for A.1 (where the brief wasn't yet in HEAD) but redundant for A.2. The verbatim-content discipline is conservative-by-default; that's fine.
- **`sqlite3.Connection` C-built-in `.execute()` patching limitation**: a real, transferable spec finding. Any future fault injection on Connection methods in this codebase will need the proxy pattern. Worth noting in a future-loadable skill or gotcha if the pattern repeats.
- **`upsert_current_calibration` naming**: runtime repo uses `upsert_*` — not in the A24 banned list (banned = `update|delete|set|patch|modify|remove`). Discoverable distinct prefix. Same principled-naming pattern as `complete_run` from A.1: name reflects intent precisely, not a generic mutator.

## Values decisions queued / resolved

None new. C1 (tie encoding) still open per COUNCIL_FINDINGS §C.

## Open questions for next session

- **A29 confound JOIN directionality** — Track A.3 implements the VIEW with `primary_clause_id` per A29 verbatim + an in-SQL comment flagging the pending EVAL-RESEARCH confirmation at Pre-Track-D council. Not a Track A.3 blocker.
- **Dead branch cleanup**: `worktree-agent-a816f4ecabe9f025d` lingers in addition to user already pruning A.1's `worktree-agent-a81babb923f1917fd`. Safe to `git branch -D` after confirming A.2 is content-merged on main.

## Next gate

**Phase 2 — Track A.3 subagent dispatch.** Per `docs/dispatch/track-a-brief.md` §3a A.3: admissible_verdicts VIEW migration + repo wrappers (`get_admissible_verdicts` already exists from A.1 awaiting the VIEW; add `audit/` stub module) + 3 VIEW tests + A3 write-time-snapshot falsifying-case test. Driver: A29.
