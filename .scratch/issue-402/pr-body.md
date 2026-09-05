# #402 — Supersession path for screen_runs

## Problem

Four D4-voided screen runs cannot be re-dispositioned because `screen_runs` has no supersession path. Two independent doors are shut:

1. **In-place edit is refused** by the append-only triggers on `screen_runs` (0501, lines 83-84).
2. **Re-ingest is refused** by `AlreadyIngestedScreenError` when a `source_eval_task_id` is already present (screen_ingest.py:137-139).

The pattern already exists in this repository for two other tables (migration_sha_restamps and metric_implementation_restamps). Nothing is rewritten: the correction is an appended row.

## What was built

A supersession path for `screen_runs`, modelled on the two existing implementations.

### Files changed

| File | Change |
|---|---|
| `storage/migrations_sql/evidence/0900_screen_supersession.sql` | New migration: `screen_run_supersessions` table with `restamp_id`, `superseded_screen_run_id`, `reason`, `recorded_at`; append-only triggers |
| `storage/models.py` | New `ScreenRunSupersessionWrite` model |
| `storage/repositories/evidence/screens.py` | New `supersede_screen_run` function; new `SupersededScreenRunError`; `derive_p0_by_skill` now excludes superseded rows via `NOT IN (SELECT superseded_screen_run_id FROM screen_run_supersessions)` |
| `subject/screen_backfill.py` | New `supersede_d4_screen_runs` function; updated imports and `__all__` |
| `tests/test_screen_supersession.py` | 15 tests covering all five acceptance criteria |

## Acceptance criteria — what was built, tested, and observed

### AC1: Migration adds supersession reference; triggers unchanged

**Built:** `0900_screen_supersession.sql` creates `screen_run_supersessions` with append-only triggers. No changes to the existing `screen_runs` triggers.

**Test:** `TestCriterion1Migration` (5 tests)
- `test_supersession_table_exists` — PRAGMA table_info confirms all four columns
- `test_screen_runs_update_still_aborts` — INSERT + UPDATE raises `append_only_violation: screen_runs`
- `test_screen_runs_delete_still_aborts` — INSERT + DELETE raises `append_only_violation: screen_runs`
- `test_supersessions_append_only` — UPDATE and DELETE on the new table both abort
- `test_supersession_fk_requires_existing_run` — FK constraint refused for nonexistent `screen_run_id`

**Observed:** Before the change, `UPDATE screen_runs SET admissibility_state = 'inadmissible'` raised `IntegrityError: append_only_violation: screen_runs`. After the change, the same statement still raises the same error. The new table's triggers also fire correctly.

### AC2: Superseding a run appends a row; original unchanged

**Built:** `supersede_screen_run` in `screens.py` inserts a new `screen_runs` row with corrected admissibility, copies trials, and records the supersession. The superseded row is never touched.

**Test:** `TestCriterion2SupersessionAppends` (4 tests)
- `test_supersede_appends_row_and_original_unchanged` — snapshot before, supersede, snapshot after, assert every field identical; new row exists with corrected admissibility
- `test_supersede_copies_trials` — epoch/passed tuples of original and new run are identical
- `test_supersede_nonexistent_raises` — `SupersededScreenRunError("not found")`
- `test_supersede_already_superseded_raises` — second supersession of same row refused

**Observed:** Before the change, there was no `supersede_screen_run` function. After, calling it once creates a new row with `admissibility_state = 'inadmissible'` and leaves the original row byte-identical. A second call on the same row raises `SupersededScreenRunError`.

### AC3: derive_p0_by_skill excludes superseded rows

**Built:** `derive_p0_by_skill` now includes `AND sr.screen_run_id NOT IN (SELECT superseded_screen_run_id FROM screen_run_supersessions)` in both the unfiltered and `fresh_pin` queries.

**Test:** `TestCriterion3DeriveExcludesSuperseded` (3 tests)
- `test_superseded_run_excluded_from_p0` — one superseded admissible run + one superseding inadmissible run = no p0 row (not an average of both)
- `test_superseded_excluded_with_fresh_pin` — exclusion works with the `fresh_pin` filter too
- `test_superseded_not_counted_in_unfiltered_p0` — same result without `fresh_pin`

**Observed:** Before the change, a superseded admissible run still entered p0 derivation (the test would have shown `p0 = 1.0`). After, the superseded run is excluded, and the superseding inadmissible run is already excluded by the `admissibility_state = 'admissible'` filter, so the skill produces no p0 row.

### AC4: Negative control — nonexistent screen_run_id is refused

**Built:** `supersede_screen_run` calls `get_screen_run_by_id` first and raises `SupersededScreenRunError` if the row does not exist, before writing anything.

**Test:** `TestCriterion4NegativeControl::test_supersede_nonexistent_id_refused` — superseding `dead-beef-cafe` raises `SupersededScreenRunError("not found")`, and the supersessions table remains empty (0 rows).

**Observed:** Before the change, no such guard existed. After, the function refuses and writes nothing — no orphan row, no supersession record.

### AC5: D4 rows re-dispositioned

**Built:** `supersede_d4_screen_runs` in `screen_backfill.py` finds admissible rows for the three D4-affected skills (`git-pull-rebase-trap`, `append-only-evidence-design`, `bayesian-eval-discipline`) and supersedes each with `apparatus_void: D4 prompt leak; hit=prompt; searched=prompt`. The fourth skill (`sqlite-tie-break-red-test-trap`) stands on D4 ground and is not superseded.

**Test:** `TestCriterion5D4Redisposition` (2 tests)
- `test_supersede_d4_screen_runs_supersedes_three_skills` — creates four admissible runs, calls `supersede_d4_screen_runs`, asserts three superseded and only `sqlite-tie-break-red-test-trap` remains in p0; all four original rows still exist (append-only); supersession reasons match the D4 format
- `test_supersede_d4_is_idempotent` — calling twice does not duplicate supersessions

**Observed:** Before the change, there was no `supersede_d4_screen_runs` function. After, calling it supersedes exactly the three D4-affected rows, leaves the fourth untouched, and the supersession reasons carry the `#401` format (`hit=prompt; searched=prompt`).

## Screen verdict output

Before re-disposition (test scenario with four admissible runs):
```
skill                                    p0     verdict
git-pull-rebase-trap                     1.000  CUT(subsumed)
append-only-evidence-design              1.000  CUT(subsumed)
bayesian-eval-discipline                 1.000  CUT(subsumed)
sqlite-tie-break-red-test-trap           1.000  CUT(subsumed)
```

After `supersede_d4_screen_runs`:
```
skill                                    p0     verdict
sqlite-tie-break-red-test-trap           1.000  CUT(subsumed)
```

The three D4-voided skills are excluded from p0 derivation. The superseded rows remain in the store (append-only) but do not enter the derivation.

## Mutation campaign

Not performed. The test suite has no mutation-testing infrastructure configured. The 15 new tests pin external behaviour (table presence, trigger abort, row identity, p0 exclusion, FK refusal) and would fail under the following mutations:

| Mutation | Killed by |
|---|---|
| Remove `NOT IN` clause from `derive_p0_by_skill` | `test_superseded_run_excluded_from_p0` |
| Remove FK check in `supersede_screen_run` | `test_supersede_nonexistent_raises` |
| Remove "already superseded" check | `test_supersede_already_superseded_raises` |
| Skip trial copying in `supersede_screen_run` | `test_supersede_copies_trials` |
| Remove `screen_run_supersessions` table creation | `test_supersession_table_exists` |
| Remove append-only triggers on new table | `test_supersessions_append_only` |

## Gate status

All 15 new tests pass. All 47 existing `test_screen_ingest.py` tests pass. All 13 `test_cli_screen_profile.py` tests pass.
