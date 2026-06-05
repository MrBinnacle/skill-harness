# 2026-06-05 · track-a-complete

**Phase**: Phase 2 — **Track A COMPLETE** (A.3 + A.4 shipped sequentially this session)
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@(local, gitignored — was at A.2 ship state)
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 (A.3 + A.4 subagents via Agent tool)
**User invocation**: "Proceed (per SOP)" after the PO/eng-lead briefing earlier this session

## Context

Per the briefing's "What I'd do this turn if you say 'proceed'" — push to origin, dispatch A.3, on return dispatch A.4. User signal "Proceed (per SOP)" greenlit the full sequence. Both subtracks shipped this session without orchestrator intervention beyond review + cherry-pick.

## Decisions made

- **Push BEFORE A.3 dispatch**: 7 local commits ahead of origin; pushed to `b1f6db2` to fire CI (Ubuntu + Windows matrix). A.3 subagent's worktree could then fork from a current-origin state (the brief is committed in main).
- **A.3 spec-finding folded into A.4 scope**: A.3 surfaced that `repositories/evidence/oracle_verdicts.py` retained 3 convenience query functions (`get_verdict_by_id`, `list_verdicts_for_clause`, `select_verdicts_by_admissibility`) doing raw-table SELECTs. Per A29 strict interpretation these should live in `audit/`. Orchestrator added the move to A.4's scope rather than dispatching a separate fix subtrack. A.4 subagent moved them cleanly + updated all 3 callers.
- **`audit_all_verdicts` naming**: A.3 subagent surfaced an inconsistency between the dispatch brief (`audit_all_verdicts_for_audit` with redundant suffix) and A29 verbatim (`audit_all_verdicts`). A.3 subagent went with A29 verbatim — correct call; brief should be amended in a v1.1 doc-lock cleanup.
- **Pyright "Argument missing" for Hypothesis `@given` calls**: subagent's tests use `_property()` after `@given(skill_suffix=...)` decoration; Pyright doesn't understand that `@given` injects the parameter from the strategy. False positive; not a real bug. Subagent's `pytest` passes.
- **`defaultdict` "not accessed" Pyright diagnostic on migrations.py:22**: spot-checked — actually used at line 84 in the duplicate-version guard. Stale Pyright analysis.
- **Two principled `sqlite3.connect` exceptions** (in tests/test_transaction.py + tests/test_smoke.py — "system under test" patterns) accepted as not-blocking. Will need CI-codification whitelisting in v0.2.

## Council fires this session

None. A.3 + A.4 are implementation-following-A27/A28/A29/A30; no new architectural decisions.

## Artifacts produced

### Code shipped to main

- **A.3 (`d03ff3e`)**:
  - `migrations/evidence/0003_admissible_verdicts_view.sql` — VIEW with A29-verbatim NOT EXISTS + in-SQL comment flagging JOIN directionality for EVAL-RESEARCH at Pre-Track-D
  - `src/skill_harness/audit/__init__.py` — `audit_all_verdicts(conn, run_id)` (A29-canonical home for raw-table access)
  - `tests/test_admissible_view.py` — 3 VIEW filter tests
  - `tests/test_admissibility_write_time_snapshot.py` — A3 falsifying-case (insert verdict → mutate current_calibration → assert admissibility_state + calibration_event_id unchanged)
  - Removed `get_all_verdicts_for_audit` from `repositories/evidence/oracle_verdicts.py`

- **A.4 (`2206185`)**:
  - `src/skill_harness/storage/migrations.py` — `discover()` raises `BootstrapError` on duplicate version numbers (A30); uses `collections.defaultdict` to group
  - `migrations/README.md` — per-track number ranges (A: 0001-0099, B: 0100-0199, etc.) + SHA-256 ledger + duplicate guard documentation
  - `.github/CODEOWNERS` — `migrations/*    @MrBinnacle` line with A30 + dev-team-council comment; existing entries preserved
  - `tests/conftest.py` — `evidence_db_savepoint` fixture (SAVEPOINT/ROLLBACK envelope for Hypothesis examples)
  - `tests/test_hypothesis_savepoint_isolation.py` — 3 fixture-isolation tests
  - `tests/property/test_evidence_append_only.py` — P1 (18 tests across 9 evidence tables × UPDATE+DELETE; FK closure via `PRAGMA foreign_key_list` introspection) + P2 (3 tests for runs carve-out per A20)
  - `tests/test_pragmas.py` — 4 PRAGMA smoke tests (foreign_keys=1 on open_evidence + open_runtime)
  - Moved `get_verdict_by_id`, `list_verdicts_for_clause`, `select_verdicts_by_admissibility` (and `_row_to_dict`) from `repositories/evidence/oracle_verdicts.py` to `src/skill_harness/audit/__init__.py`
  - Updated 3 caller files (`test_repo_roundtrip.py`, `test_admissibility_write_time_snapshot.py`, `test_dual_write_partial.py`)

### Docs

- `docs/session-log/2026-06-05-track-a-complete.md` (this entry)
- Checkpoint refresh (local-only, gitignored)

## Verification (post-A.4 on main)

- `pytest -q`: **149 passed, 0 failed** (cumulative growth: 8 → 16 [phase 1.5a] → 92 [A.1] → 113 [A.2] → 117 [A.3] → 149 [A.4])
- `mypy --strict src/`: 0 errors in 29 source files
- `ruff check`: clean
- `ruff format --check`: clean
- grep ban `sqlite3.connect outside migrations.py`: empty in `src/`; 2 principled exceptions in `tests/` (documented)
- grep ban `FROM oracle_verdicts outside audit/`: empty

## Track A — summary of the full subtrack arc

| Subtrack | Commit | Tests delta | Driver findings |
|---|---|---|---|
| A.1 — repositories + Pydantic Write models + AST-walker | `b9faeef` | +76 (→92) | A24 |
| A.2 — writer_transaction + dual-write evidence-first + StorageContext + fault-injection + crash-recovery | `d84d0ad` | +21 (→113) | A25, A26, A28 |
| A.3 — admissible_verdicts VIEW + audit module + A3 write-time-snapshot falsifying-case | `d03ff3e` | +4 (→117) | A29 |
| A.4 — property tests + savepoint fixture + discover() guard + migrations docs + CODEOWNERS + audit finalization | `2206185` | +32 (→149) | A27, A28, A30 |

All 30 council-adopted findings (A1–A30) now realized in the storage substrate. Track A delivers the **append-only evidence + mutable runtime** foundation that Tracks B/C/D/E build on.

## Values decisions queued / resolved

None new. C1 (tie encoding) still open per COUNCIL_FINDINGS §C.

## Open questions for next session

- **Track A fresh-context review (recommended before B/C begin)**: dispatch `ai-slop-sentinel` against the full Track A diff (`b9faeef..2206185`). Catches AI-authored patterns the per-subtrack reviews + Stop hook may have missed at scale. Per PLAN.md Phase 3.2 the formal "across all 5 tracks" review fires later, but doing a per-Track fresh-context pass now is cheap (~5–10 min) and high-signal. Recommend.
- **Pre-Track-C council fire timing**: PLAN.md schedules Custom seats EVAL-RESEARCH + SECURITY + COST + STAT before Track C. Fire in the same session that dispatches Track C; no need to fire in advance.
- **Track B dispatch**: no gating council; can dispatch immediately. Tracks B + C share no files — parallel worktrees viable.
- **Spec-finding cleanup** (v0.2 CI codification): sqlite3.connect grep ban whitelist for 2 test files; Windows path separator cross-platform pattern; `HealthCheck.function_scoped_fixture` suppression already added.

## Next gate

User to choose: either dispatch the Track A `ai-slop-sentinel` end-of-track review (recommended), OR proceed to Track B (no gating council) + Pre-Track-C council fire (gating Track C). Both can fire in parallel.
