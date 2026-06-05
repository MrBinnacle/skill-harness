# 2026-06-05 · track-a-slop-review-and-cleanup

**Phase**: Phase 2 — Track A end-of-track ai-slop-sentinel review + cleanup
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@212bb3e
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 (ai-slop-sentinel review subagent + cleanup subagent)
**User invocation**: "Iteratively spin up the council and proceed per SOP"

## Context

Per my prior PO/eng-lead briefing's recommendation and PLAN.md Phase 3.2's discipline, an `ai-slop-sentinel` fresh-context review of the full Track A diff was due before Tracks B/C begin (to catch AI-authored patterns the per-subtrack Stop hook may have missed at scale). "Iteratively" interpreted as drive multiple gates per session; this iteration delivered the review + cleanup as a single forward step.

## Decisions made

- **Sentinel triage** (orchestrator's call per `feedback-non-technical-sme`): 4 of 6 findings approved for cleanup; 2 deferred.

| ID | Severity | Decision |
|---|---|---|
| TA-SLOP-001 | Important | **Applied** — duplicate `_row_to_dict` positional indexing across 14 modules; consolidated to `cursor.description` pattern matching `audit_all_verdicts` + `get_admissible_verdicts`. |
| TA-SLOP-002 | Minor | **Deferred to Track E** — `dict[str, Any]` repo return types should become typed read models in Track E; sentinel acknowledged as adjudicated. |
| TA-SLOP-003 | Minor | **Applied** — `evidence_db_savepoint` fixture was a misleading pass-through; renamed to `evidence_db_for_property_tests` + clarified docstring. Per-example SAVEPOINT discipline lives in `@given` bodies (pytest fixture lifecycle + Hypothesis example loop precludes fixture-side wrapping). |
| TA-SLOP-004 | Minor | **Applied** — tautological `assert isinstance(tmp_path, object)` removed; `from pathlib import Path` lifted to module level; `tmp_path: object` → `tmp_path: Path`. Pyright-placation slop. |
| TA-SLOP-005 | Minor | **Applied** — `OracleVerdictWrite`/`FrozenCaseWrite`/`CostLedgerWrite` multi-field optional validators report `info.field_name` via `ValidationInfo` instead of generic `"optional_text_field"`. Real debugging cost on adversarial input. |
| TA-SLOP-006 | Minor | **Accepted as-is** — `dual_write.py` ASCII sequence diagram is pedagogically useful for cross-DB ordering at a glance; sentinel's "WHAT-not-WHY" application is reasonable disagreement, not a blocking call. |

- **Dispatch shape**: cleanup as a single subagent dispatch (not 4 parallel) — fixes are mechanically coupled (e.g., refactoring `_row_to_dict` in repos + audit/ must stay in lockstep) and small enough to fit one Sonnet 4.6 session. Same `isolation:"worktree"` envelope as the Track A subtrack subagents.

- **Cleanup subagent finding accepted**: the new fixture name `evidence_db_for_property_tests` (30 chars) overflows the 100-char line limit; `ruff format` auto-wraps 18 test signatures. Cosmetic only. If a tighter name (`evidence_db_property`?) is preferred later, easy follow-up rename. Not blocking.

- **Two dead worktree branches from A.3 + A.4 attempted safe-delete**: both report "not fully merged" (cherry-pick SHA divergence); orchestrator did NOT use `-D` (safety net). User can prune.

## Council fires this session

None. ai-slop-sentinel is a fresh-context REVIEWER dispatch, not a council fire. Council fires (multi-seat parallel) are reserved for architectural decisions; sentinel reviews are code-quality discipline.

## Artifacts produced

- **Code (cherry-picked into main as `ff7a9dd`):** 18 files modified, +190 / -311 lines:
  - 11 repository modules: `_row_to_dict` removed; `cursor.description` inlined at each call site
  - `src/skill_harness/audit/__init__.py`: `_row_to_dict` removed; same pattern as `audit_all_verdicts`
  - `src/skill_harness/storage/models.py`: 3 multi-field optional validators threaded with `ValidationInfo`
  - `tests/conftest.py`: fixture renamed + docstring corrected
  - `tests/property/test_evidence_append_only.py`: 18 fixture-reference updates (signatures auto-wrapped by ruff format)
  - `tests/test_hypothesis_savepoint_isolation.py`: 3 fixture-reference updates
  - `tests/test_discover_rejects_duplicate_versions.py`: tautological assert removed, Path import lifted, type annotations corrected
- `docs/session-log/2026-06-05-track-a-slop-review-and-cleanup.md` (this entry).
- Checkpoint refresh (local-only, gitignored).

## Verification (post-cherry-pick, on main)

- `pytest -q`: 149 passed (unchanged — refactor)
- `mypy --strict src/`: 0 errors in 29 source files
- `ruff check`: clean
- `ruff format --check`: clean
- grep ban `sqlite3.connect outside migrations.py`: empty in `src/`
- grep ban `FROM oracle_verdicts outside audit/`: empty

## Observations

- **Pyright stale-cache artifacts** appeared TWICE this session: first showing `_row_to_dict is not defined` in `audit/__init__.py` (would have been runtime errors if real) and `_row_to_dict is not accessed` in 5 runtime/evidence modules (would have been dead code if real). Verified on-disk with `grep`: zero `_row_to_dict` references in any file. Reconfirmed mypy --strict + pytest both pass. Pyright was reading mid-flight subagent state. This is the 5th session with stale-Pyright artifacts; the orchestrator pattern is now: verify on-disk + re-run gates before treating Pyright as authoritative.
- **Sentinel quality**: high. The TA-SLOP-001 finding is structurally significant — it would have replicated across Tracks B-E if uncaught. The triage cost (one cleanup dispatch) is the right investment. Future tracks should consider a per-track sentinel pass before declaring exit.
- **Refactor risk realized**: zero. The cursor-description pattern was already proven in `audit_all_verdicts` + `get_admissible_verdicts`; the consolidation propagated it without surfacing any hidden column-order bugs.

## Values decisions queued / resolved

None new. C1 (tie encoding) still open per COUNCIL_FINDINGS §C.

## Open questions for next session

- **Track B dispatch (no gating council)** + **Pre-Track-C council fire** (Custom seats: EVAL-RESEARCH + SECURITY + COST + STAT) can fire in the same iteration since Tracks B + C share no files. Orchestrator's call.
- **Dead branches** from A.3 + A.4 + this session's slop-cleanup still lingering; user can `git branch -D` when convenient.
- **TA-SLOP-002 carry-forward**: Track E read models should provide typed return shapes (TypedDict or dataclass) replacing the `dict[str, Any]` repo returns. Add to Track E exit criteria.

## Next gate

User-routable: **Track B dispatch** (no gating; clause extractor; PLAN.md Phase 2 Track B) and/or **Pre-Track-C council fire** (Custom 4-seat parallel: EVAL-RESEARCH + SECURITY + COST + STAT; required before Track C dispatch). Both can run in the same next-iteration session; orchestrator decides sequencing.
