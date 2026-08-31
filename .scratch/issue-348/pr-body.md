# PR body for #348 — confound status e2e detector

## Acceptance criteria

### Criterion 1: Detector file lands at the exact path

**Built:** `tests/test_confound_status_e2e.py` — class `TestConfoundStatusE2E`
with:
- `test_primary_confounded_rows_do_not_enter_aggregation` (green pin)
- `test_confound_events_produce_confounded_status` (strict xfail)

**Test that pins it:** Seeds a completed ablation run with all verdicts
`inadmissible` (runner's write for confounded clauses) and `confound_events`
rows for every verdict. Calls `aggregate_skill()`. Asserts
`clause.status == ClauseStatus.CONFOUNDED`.

**Observation before change:** Status is `UNMEASURED` / `inadmissible`. The
assertion fails. The xfail fires.

**Observation after change (expected):** Status would be `CONFOUNDED`. The
assertion passes. The xfail must be removed.

### Criterion 2: Row removed from ratchet baseline

**Built:** Removed the `{item: 6, detector: "tests/test_confound_status_e2e.py",
issue: 348}` row from `docs/assurance/falsification-detector-baseline.json`.

**Test that pins it:** `tests/test_falsification_plan_detectors_exist.py` —
all 5 tests pass.

### Criterion 3: Fixture proves detector goes red

**Built:** `test_confound_events_produce_confounded_status` uses
`@pytest.mark.xfail(strict=True)` with a reason naming the findings document.
Observed failure: `status == 'UNMEASURED'` with `sub_reason == 'inadmissible'`,
not `CONFOUNDED`.

### Criterion 4: Mutation receipt

Baseline (this branch): 1 passed + 1 xfailed on the module; ratchet guard green.

**Mutant 1: Remove confound_events rows from seed.**
- Compiles; reaches `aggregate_skill`.
- Named assertion still fails with the same `UNMEASURED`/`inadmissible` vs
  `CONFOUNDED` mismatch (confounds never affected status on main, so removing
  them does not change the red).
- Under `xfail(strict=True)` the suite stays green (XFAIL). **Survives** as a
  seed mutant of an xfail detector — inherent until the fix makes confounds
  change status.
- Result: SURVIVED (documented; not claimed as a kill).

**Mutant 2: Change admissibility_state from 'inadmissible' to 'admissible'.**
- Compiles; reaches `aggregate_skill`.
- With admissible + confound_events, the VIEW excludes the rows and the
  engine's confound query finds them: `all_confounded_flag` becomes true and
  status is `CONFOUNDED`.
- Named assertion **passes**; under `xfail(strict=True)` pytest reports
  XPASS and fails the run.
- Result: KILLED via unexpected pass — proves the detector's expected
  status is the one the engine already produces when the write shape matches
  its read shape. Failure mode is XPASS, not an assertion message about
  NO_DATA.

**Mutant 3: Remove frozen_case from seed.**
- Compiles; reaches `aggregate_skill`.
- Production raises `PreconditionError('no_instantiated_frozen_cases')`
  before status derivation.
- Under `xfail(strict=True)` that exception is also XFAIL. **Survives** as
  an xfail-wrapped failure (red is precondition, not the named status
  assertion).
- Result: SURVIVED under xfail wrapping; the production failure mode is real
  but does not uniquely kill the status detector.

Encoding: explicit UTF-8 throughout; no locale-dependent paths.

### Criterion 5: Red exit code alone does not satisfy

The status detector uses `@pytest.mark.xfail(strict=True)`. The assertion
message names the violated invariant (status/sub_reason vs CONFOUNDED). The
xfail reason names the findings document. A bare red exit without that
marker would not satisfy this criterion.

## Files changed

| File | Change |
|------|--------|
| `tests/test_confound_status_e2e.py` | E2E detector: green primary-exclusion pin + xfail CONFOUNDED status |
| `docs/assurance/falsification-detector-baseline.json` | Remove item 6 from `not_yet_built` |
| `docs/findings/confound-status-silent-understatement.md` | Findings document for the defect |
