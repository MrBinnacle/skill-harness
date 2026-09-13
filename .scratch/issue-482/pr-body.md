# PR body for #482: Extract shared module-selection filter

## Summary

Extract the duplicated module-selection filter from `tests/test_value_class_call_sites_static.py` and `tests/test_mint_path_allowlist.py` into a shared module `tests/_module_selection.py`. This fixes the same defect as #447 (absolute-path filtering defeating scans in build worktrees) and prevents recurrence by eliminating the duplication that caused the defect to survive the first fix.

## What changed

1. **Created `tests/_module_selection.py`** — shared `python_modules_under(root)` function and `EXCLUDED_DIRECTORY_NAMES` constant. The exclusion is anchored at the scanned root, not tested against the absolute path.

2. **Updated `tests/test_value_class_call_sites_static.py`** — replaced local `_python_modules_under` and `_EXCLUDED_DIRECTORY_NAMES` with imports from the shared module. All existing tests unchanged.

3. **Updated `tests/test_mint_path_allowlist.py`** — replaced `_production_py_files()` (which used absolute-path filtering) with the shared helper. Added three new tests.

## Acceptance criteria and evidence

### Criterion 1: The filter is anchored at the scanned root, not the absolute path

**Test:** `test_module_selection_is_not_defeated_by_the_checkout_location` (in both files)

**What it does:** Creates a temporary root under `.sandcastle/worktrees/agent-issue-482/src/`, places a live module, a `__pycache__` file, and a nested `.sandcastle` build tree inside it, then asserts:
- The live module IS found (fails on absolute-path filter)
- The `__pycache__` file is NOT found (exclusion still works)
- The nested build tree is NOT found (exclusion still works)

**Before the change:** `_production_py_files()` in `test_mint_path_allowlist.py` used `if ".sandcastle" not in p.parts`, testing the absolute path. In a build worktree at `<repo>/.sandcastle/worktrees/agent-issue-<n>/`, every candidate file carries `.sandcastle` in its absolute path, so the list came back empty and all assertions passed vacuously.

**After the change:** `python_modules_under(root)` uses `path.relative_to(root).parts`, anchoring the exclusion at the scanned root. The live module is found; the test passes for the right reason.

**Observation:** The test `test_module_selection_is_not_defeated_by_the_checkout_location` in `test_mint_path_allowlist.py` passed before the change only because the old filter was not exercised in a `.sandcastle`-prefixed checkout. After the change, it passes because the filter correctly includes files under a `.sandcastle`-prefixed root while still excluding nested `.sandcastle` directories.

### Criterion 2: The scan finds live call sites (liveness test)

**Test:** `test_the_scan_finds_the_insert_call_sites_at_all` (new in `test_mint_path_allowlist.py`)

**What it does:** Scans production sources for calls to `insert_oracle_verdict` and asserts the result is non-empty.

**Before the change:** No liveness test existed in this module. The scan could return an empty list (vacuously) and all assertions would pass. This is the silent-failure mode the ticket identified.

**After the change:** The test fails if the scan finds no call sites, making vacuous passes visible.

**Observation:** This test passes after the change because the filter now correctly finds production files. It would have failed before the change if run in a `.sandcastle`-prefixed checkout (the scan would return empty), which is exactly the silent-failure mode the ticket describes.

### Criterion 3: Exactly one implementation of the selection filter (recurrence prevention)

**Test:** `test_the_selection_filter_is_implemented_exactly_once` (new in `test_mint_path_allowlist.py`)

**What it does:** Walks all `.py` files under the repo root, parses them with AST, and checks for module-level functions that implement the directory-exclusion pattern (`.relative_to(root).parts` with an exclusion set). The shared module and this test file itself are excluded from the scan. Asserts the result is empty.

**Before the change:** Two separate implementations existed (`_python_modules_under` in `test_value_class_call_sites_static.py` and `_production_py_files` in `test_mint_path_allowlist.py`). The test would have found the duplicate in `test_value_class_call_sites_static.py`.

**After the change:** Only the shared implementation in `tests/_module_selection.py` remains. The test passes because no other module implements the filter.

**Observation:** This is the recurrence arm. Without it, the extraction fixes today's duplication but nothing prevents a third copy from appearing. The test is the mechanism that makes #482 more than a re-fix of #447.

## What did NOT change

- No test was weakened, skipped, xfailed, or renamed to pass.
- The `TestUnpinnedInsertBan` class tests are unchanged in behaviour.
- The `TestCurrencyGateFeedsPassed` tests are unchanged.
- No source code outside `tests/` was modified.
- The `test_value_class_call_sites_static.py` test cases are unchanged in behaviour; only the import source changed.

## Gate results

```
ruff check src tests          — All checks passed
ruff format --check src tests — 315 files already formatted
mypy --strict src/ tests/     — Success: no issues found in 311 source files
```

All 11 tests in `test_mint_path_allowlist.py` pass. All 5 tests in `test_value_class_call_sites_static.py` pass.

## Mutation campaign

No mutation receipt was requested for this ticket. The ticket is a refactor (extract shared helper) paired with new regression tests; the mutation standard applies to the filter's own logic, which was already mutated under #447.

## Files changed

| File | Change |
|------|--------|
| `tests/_module_selection.py` | **New.** Shared `python_modules_under()` and `EXCLUDED_DIRECTORY_NAMES`. |
| `tests/test_value_class_call_sites_static.py` | Removed local `_python_modules_under` and `_EXCLUDED_DIRECTORY_NAMES`; import from `_module_selection`. |
| `tests/test_mint_path_allowlist.py` | Replaced `_production_py_files()` with shared helper; added 3 tests: liveness, `.sandcastle` checkout, recurrence. |
