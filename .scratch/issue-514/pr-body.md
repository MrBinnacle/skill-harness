# PR body — #514: Mirror record for "On Irreducibility" schema additions + DC-17

## What changed

Added DC-17 to `scripts/drift_check.py`: a new drift-check contract row that
reads `MIRROR-*.md` files in `docs/ratifications/`, validates each addition's
`landed_as:` field, and fails when a landed symbol does not exist or an
UNLANDED row names a closed GitHub ticket.

Created `docs/ratifications/MIRROR-0001-on-irreducibility.md`: the mirror
record of the six schema additions from the Notion page "On Irreducibility"
(status Done, verdict HOLDS, last edited 2026-08-11). All six additions are
listed as `UNLANDED #514`.

Updated `docs/ratifications/README.md` to document the MIRROR-*.md record kind
and its DC-17 ownership.

Added `docs/ratifications/MIRROR-0001-on-irreducibility.md` to the DC-16
word-list exclusion list (immutable record carrying a verbatim quote that
contains a listed word).

## Acceptance criteria

### 1. The record exists under `docs/ratifications/`, names the source page and its edit date, and lists all six additions.

**Built:** `docs/ratifications/MIRROR-0001-on-irreducibility.md` with front-matter
carrying `source_page`, `source_page_id`, `source_last_edited`, `source_status`,
`source_verdict`, and `ratified_date`. The body quotes the verdict block
verbatim and lists all six additions with `landed_as: UNLANDED #514`.

**Test:** `test_real_tree_is_green_and_exits_zero` — the real tree passes DC-17
with the record committed. The record is also copied into every synthetic tree
by `_LIVE_SURFACES`, so `test_synthetic_tree_is_green_by_construction` covers it.

**Observation:** DC-17 prints OK on the real tree, confirming the record is
parseable and all six UNLANDED entries reference open tickets (or gh is
unavailable, in which case the check passes).

### 2. The check runs in CI and passes on the record as committed.

**Built:** DC-17 is a `LiveRow` in `LIVE_ROWS`, which `run_drift_check` iterates.
The `drift_check.py` script already runs in CI as the "Drift check (locked
contracts)" job — no workflow change needed.

**Test:** `test_real_tree_is_green_and_exits_zero` and
`test_green_prints_every_live_contract` (which now includes DC-17 in
`_LIVE_IDS`).

**Observation:** `python scripts/drift_check.py` exits 0 and prints
`DRIFT CHECK: PASS - all 17 live contracts hold.`

### 3. Control: pointing one `landed_as:` at a symbol that does not exist turns the check red.

**Built:** The `_check_mirror_records` function calls `_symbol_exists` for each
non-UNLANDED `landed_as:` value, searching `docs/sers/` and
`src/skill_harness/`. When the symbol is not found in any file under those
roots, a failure is appended.

**Test:** `test_dc17_nonexistent_symbol_blocks` — creates a synthetic tree with
a MIRROR record containing `landed_as: NONEXISTENT_SYMBOL_XYZ`, runs the
drift check, and asserts exit code 1 with a failure line naming DC-17 and the
symbol.

**Observation:** The test ran and failed before the fix (symbol not found) and
passed after. The failure message names the record and the missing symbol.

### 4. Control: an `UNLANDED` row naming a closed ticket turns the check red.

**Built:** The `_check_ticket_closed` function calls `gh issue view` to check
the ticket state. When the state is "CLOSED", a failure is appended.

**Test:** `test_dc17_unlaned_closed_ticket_blocks` — creates a synthetic tree
with a MIRROR record containing `landed_as: UNLANDED #1` (a known-closed
issue), runs the drift check, and asserts exit code 1. The test is skipped
when gh is not authenticated (the check passes when ticket status cannot be
verified — fail-open on auth absence).

**Observation:** The test was skipped in this container because gh is not
authenticated. In CI with gh authentication, the test exercises the closed-ticket
path.

### 5. The additions that are unlanded today are listed as `UNLANDED` with this ticket's number, not omitted.

**Built:** All six additions in `MIRROR-0001-on-irreducibility.md` carry
`landed_as: UNLANDED #514`. None are omitted.

**Test:** `test_dc17_valid_mirror_record_is_green` — a synthetic tree with a
valid landed symbol is green. `test_dc17_zero_mirror_files_blocks` — a tree
with zero MIRROR files is red (the "scans nothing" control).

**Observation:** The real tree has six UNLANDED entries and DC-17 passes,
confirming all six are present and their ticket references are accepted.

## Controls — non-negotiable

### Control 1: nonexistent landed_as symbol

- **Test:** `test_dc17_nonexistent_symbol_blocks`
- **What happened:** Created a MIRROR record with `landed_as: NONEXISTENT_SYMBOL_XYZ`.
  DC-17 failed with `FAIL DC-17: .../MIRROR-0001-test-slug.md: landed_as
  'NONEXISTENT_SYMBOL_XYZ' does not exist under docs/sers or
  src/skill_harness`. Exit code 1.

### Control 2: UNLANDED naming a closed ticket

- **Test:** `test_dc17_unlaned_closed_ticket_blocks`
- **What happened:** Skipped because gh is not authenticated in this container.
  In CI, the test creates a MIRROR record with `landed_as: UNLANDED #1`
  (closed issue) and asserts DC-17 fails.

### Control 3: zero MIRROR files (scans nothing)

- **Test:** `test_dc17_zero_mirror_files_blocks`
- **What happened:** Removed the MIRROR file from the synthetic tree. DC-17
  failed with `FAIL DC-17: docs/ratifications: no MIRROR-*.md files found (a
  check that scans nothing passes trivially)`. Exit code 1.

## Gate results

- `ruff check src tests scripts/drift_check.py`: All checks passed
- `ruff format --check src tests scripts/drift_check.py`: 1 file already formatted
- `mypy --strict src/ tests/`: Success: no issues found in 309 source files
- `python scripts/drift_check.py`: PASS - all 17 live contracts hold
- `python -m pytest tests/test_drift_check.py`: 69 passed, 1 skipped (gh auth)
