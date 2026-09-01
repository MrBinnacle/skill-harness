# Issue #347: Half-update tie sensitivity detector

## Acceptance Criteria Progress

### Criterion 1: Detector file lands at the exact path the plan's `**Detection:**` line names

**Status:** Complete

The detector lands at `tests/test_halfupdate_tie_sensitivity.py`, matching the
`**Detection:**` line in `docs/assurance/falsification-plan.md` item 5.

**Test:** `tests/test_falsification_plan_detectors_exist.py::test_every_registered_detector_exists_or_is_recorded_as_debt`

### Criterion 2: Its row is removed from the ratchet baseline in the same change

**Status:** Complete

Removed the `{"item": 5, "detector": "tests/test_halfupdate_tie_sensitivity.py", "issue": 347}` row
from `docs/assurance/falsification-detector-baseline.json`.

**Test:** `tests/test_falsification_plan_detectors_exist.py::test_baseline_names_no_detector_that_now_exists`

### Criterion 3: A fixture proves the detector goes red on the condition it registers

**Status:** Complete

1. `test_fixture_proves_detector_fires` — extreme scenario (7w, 1l, 30t) must
   exceed both documented bounds through the production accumulator. Passes
   while the condition holds; goes red if a future encoding collapses the gap.
2. Seven cells carry `@pytest.mark.xfail(strict=True)` on real production
   behaviour: two verdict flips (`win-heavy-few-ties`, `win-heavy-many-ties`)
   and five bound exceedances. Strict marks XPASS→fail if the sensitivity is
   removed without clearing the marks.

**Test:** `tests/test_halfupdate_tie_sensitivity.py` — 32 passed, 7 xfailed
(plus one zero-ties sanity control: 33 production-related cells + fixture +
monotonicity + zero-ties = 32 pass + 7 xfail).

### Criterion 4: Mutation receipt in the pull request body

**Status:** Complete

See Mutation Campaign section below.

### Criterion 5: A red exit code alone does not satisfy any criterion above

**Status:** Complete

Every assertion names a specific invariant:
- `test_posterior_mean_shift_within_bound`: `shift <= MAX_POSTERIOR_MEAN_SHIFT`
  with scenario, shift, and both means in the message.
- `test_p_exceed_sensitivity_within_bound`: `divergence <= MAX_P_SENSITIVITY`
  with scenario, divergence, and both P values in the message.
- `test_stopping_decision_agreement`: `hu_reason == dt_reason` with both reasons.
- `test_fixture_proves_detector_fires`: divergence and mean shift must exceed
  the documented bounds (not a bare `> 0`).

Both comparison arms call `BetaBinomialAccumulator.add` / `check_stop`. The
drop-ties arm is an in-test oracle (ties never enter the accumulator).

## Evidence

### Test Results

```
32 passed, 7 xfailed in ~2.6s
```

Xfailed (strict) cells:
- `test_stopping_decision_agreement[win-heavy-few-ties]`
- `test_stopping_decision_agreement[win-heavy-many-ties]`
- `test_p_exceed_sensitivity_within_bound[many-ties]`
- `test_p_exceed_sensitivity_within_bound[tie-dominated]`
- `test_p_exceed_sensitivity_within_bound[win-heavy-many-ties]`
- `test_posterior_mean_shift_within_bound[win-heavy-few-ties]`
- `test_posterior_mean_shift_within_bound[win-heavy-many-ties]`

### Ratchet Guard

```
tests/test_falsification_plan_detectors_exist.py — 5 passed
```

### Mutation Campaign

**Baseline:** 32 passed, 7 xfailed before mutation. Production file restored
after each mutant.

**Mutant 1:** In `BetaBinomialAccumulator.add`, ties contribute `w += 0.0`
instead of `w += observation` (still `n += 1`).

- Compiles: yes.
- Reaches production call site: `add()` at `ablation/stopping.py`.
- Named assertion fails (among others):
  `test_posterior_mean_shift_within_bound[few-ties]`
- Failure message: `posterior mean shift 0.200000 exceeds bound 0.15 for
  scenario 'few-ties' (half-update mean=0.500000, drop-ties mean=0.700000)`.
- Also fails `test_p_exceed_sensitivity_within_bound[moderate-ties]` and
  several verdict-agreement cells that were green under the real encoding.
- The red is assertion failure inside the test body, not setup/collection/
  encoding/timeout.
- 14 failed, 18 passed, 7 xfailed.

**Mutant 2:** Ties increment `w` but do not increment `n`
(`if observation != 0.5: self._n += 1.0`).

- Compiles: yes.
- Reaches production call site: `add()` at `ablation/stopping.py`.
- Named assertion fails: `test_fixture_proves_detector_fires`
- Failure message: `detector did not fire: P(rate > theta) divergence nan is
  at or below bound 0.25 for extreme scenario (7w, 1l, 30t)`.
- Also fails `test_stopping_decision_agreement[loss-heavy-many-ties]`:
  `stopping verdict differs: half-update=passed, drop-ties=failed`.
- 14 failed, 18 passed, 7 xfailed.

**Mutant 3:** Ties contribute `w += 1.0` (ties count as wins).

- Compiles: yes.
- Reaches production call site: `add()` at `ablation/stopping.py`.
- Named assertion fails:
  `test_posterior_mean_shift_within_bound[balanced-many-ties]`
- Failure message: `posterior mean shift 0.307692 exceeds bound 0.15 for
  scenario 'balanced-many-ties' (half-update mean=0.807692, drop-ties
  mean=0.500000)`.
- Strict xfail cells for win-heavy mean shift XPASS (half-update mean moves
  toward the drop-ties mean when ties count as wins); strict mode turns those
  into failures as well.
- 6 failed on the mean-shift parametrization alone.

## Files Changed

- `tests/test_halfupdate_tie_sensitivity.py` — detector (production arms,
  documented bounds, strict xfails)
- `docs/assurance/falsification-detector-baseline.json` — removed item 5 row
- `docs/findings/halfupdate-tie-sensitivity.md` — finding (severity WRONG_NUMBER)
- `.scratch/issue-347/pr-body.md` — this file
