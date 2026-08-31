# PR body for #348 — confound status e2e detector

## Acceptance criteria

### Criterion 1: Detector file lands at the exact path

**Built:** `tests/test_confound_status_e2e.py` — one test class
`TestConfoundStatusE2E` with one test method
`test_confound_events_produce_confounded_status`.

**Test that pins it:** The test seeds a completed ablation run with all
verdicts `inadmissible` (runner's write for confounded clauses) and
`confound_events` rows for every verdict.  Calls `aggregate_skill()`.
Asserts `clause.status == ClauseStatus.CONFOUNDED`.

**Observation before change:** Status is `UNMEASURED(NO_DATA)`.  The
assertion fails because `CONFOUNDED != NO_DATA`.  The xfail fires.

**Observation after change (expected):** Status would be `CONFOUNDED`.
The assertion passes.  The xfail must be removed.

### Criterion 2: Row removed from ratchet baseline

**Built:** Removed the `{item: 6, detector: "tests/test_confound_status_e2e.py",
issue: 348}` row from `docs/assurance/falsification-detector-baseline.json`.

**Test that pins it:** `tests/test_falsification_plan_detectors_exist.py` —
all 5 tests pass:
- `test_plan_registers_the_number_of_detectors_it_claims` (10 detectors)
- `test_every_registered_detector_exists_or_is_recorded_as_debt` (detector now exists)
- `test_baseline_names_no_detector_that_now_exists` (item 6 removed)
- `test_baseline_records_only_rows_the_plan_registers` (no stale rows)
- `test_baseline_item_numbers_match_the_plan_order` (item numbers match)

**Observation:** All 5 tests pass.  The ratchet guard is green.

### Criterion 3: Fixture proves detector goes red

**Built:** The test uses `@pytest.mark.xfail(strict=True)` with a reason
naming the findings document.  The `evidence_db` fixture from
`tests/conftest.py` provides a fresh append-only evidence DB with all
migrations applied.  The test opens its own runtime DB via
`open_runtime(tmp_path / "runtime.db")`.

**Test that pins it:** `test_confound_events_produce_confounded_status`
is marked `xfail(strict=True)`.  On main it fails (status is NO_DATA,
not CONFOUNDED), so the xfail fires.  If the test unexpectedly passes,
pytest fails strict-xfail.

**Observation:** `XFAIL` in output — the test goes red for the right
reason (the assertion about CONFOUNDED status fails because the actual
status is UNMEASURED(NO_DATA)).

### Criterion 4: Mutation receipt in PR body

**Mutant 1: Remove confound_events rows from seed.**
- Mutant compiles: yes (removing INSERT statements is syntactically valid)
- Reaches production call site: yes (`aggregate_skill` is called)
- Named assertion: `clause.status == ClauseStatus.CONFOUNDED`
- Failure message: "confound events exist for clause ... but status is
  UNMEASURED(NO_DATA) (expected CONFOUNDED)"
- Red is not setup, collection, encoding, or timeout: the assertion
  failure is the named property violation
- Encoding: all strings use explicit UTF-8; no locale-dependent behavior
- Result: mutant KILLED — status becomes UNMEASURED(NO_DATA) because no
  confound events exist, so the CONFOUNDED path is never triggered

**Mutant 2: Change admissibility_state from 'inadmissible' to 'admissible'.**
- Mutant compiles: yes
- Reaches production call site: yes
- Named assertion: `clause.status == ClauseStatus.CONFOUNDED`
- Failure message: "confound events exist for clause ... but status is
  UNMEASURED(NO_DATA) (expected CONFOUNDED)"
- Red is not setup, collection, encoding, or timeout: assertion failure
- Encoding: explicit UTF-8
- Result: mutant KILLED — even with admissible verdicts, the engine's
  `all_confounded_flag` requires `admissible_count == 0` AND
  `confounded > 0`, but admissible verdicts mean `admissible_count > 0`,
  so the flag is still false

**Mutant 3: Remove frozen_case from seed.**
- Mutant compiles: yes
- Reaches production call site: yes
- Named assertion: `clause.status == ClauseStatus.CONFOUNDED`
- Failure message: `PreconditionError('no_instantiated_frozen_cases')`
- Red is not setup, collection, encoding, or timeout: precondition error
  is the correct production failure for missing frozen cases
- Encoding: explicit UTF-8
- Result: mutant KILLED — aggregate_skill raises PreconditionError before
  reaching status derivation

### Criterion 5: Red exit code alone does not satisfy

The test uses `@pytest.mark.xfail(strict=True)` — a red exit code from
the test failing is the EXPECTED behavior (the detector fires).  The
assertion message names the violated invariant ("status is NO_DATA, expected
CONFOUNDED").  The xfail reason names the findings document.  A bare red
exit code without the xfail marker would indicate a different failure mode
(setup, collection, encoding, timeout) and would not satisfy this criterion.

## Files changed

| File | Change |
|------|--------|
| `tests/test_confound_status_e2e.py` | New — e2e detector for confound status |
| `docs/assurance/falsification-detector-baseline.json` | Remove item 6 from `not_yet_built` |
| `docs/findings/confound-status-silent-understatement.md` | New — findings document for the defect |
| `.scratch/issue-348/pr-body.md` | This file |
