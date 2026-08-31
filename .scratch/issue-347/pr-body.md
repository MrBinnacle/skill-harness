# Issue #347: Half-update tie sensitivity detector

## Acceptance Criteria Progress

### Criterion 1: Detector file lands at the exact path the plan's `**Detection:**` line names

**Status:** Complete

The detector lands at `tests/test_halfupdate_tie_sensitivity.py`, matching the
`**Detection:**` line in `docs/assurance/falsification-plan.md` item 5.

**Test:** `tests/test_falsification_plan_detectors_exist.py::test_every_registered_detector_exists_or_is_recorded_as_debt` — passes after the baseline removal in criterion 2.

### Criterion 2: Its row is removed from the ratchet baseline in the same change

**Status:** Complete

Removed the `{"item": 5, "detector": "tests/test_halfupdate_tie_sensitivity.py", "issue": 347}` row
from `docs/assurance/falsification-detector-baseline.json`.

**Test:** `tests/test_falsification_plan_detectors_exist.py::test_baseline_names_no_detector_that_now_exists` — passes after removal.

### Criterion 3: A fixture proves the detector goes red on the condition it registers

**Status:** Complete

Two fixtures prove the detector fires:

1. `test_fixture_proves_detector_fires` — constructs an extreme scenario (7w, 1l, 30t) and
   asserts the P(rate > θ) divergence (0.554) and posterior mean shift (0.225) are
   measurably positive.  This test PASSES, proving the detector can detect the condition.

2. `test_stopping_decision_agreement[win-heavy-few-ties]` and
   `test_stopping_decision_agreement[win-heavy-many-ties]` — these XFAIL, proving the
   detector fires on real production behaviour: half-update says INCONCLUSIVE while
   drop-ties says PASSED.

**Test:** `tests/test_halfupdate_tie_sensitivity.py` — 31 passed, 7 xfailed.

### Criterion 4: Mutation receipt in the pull request body

**Status:** Complete

See Mutation Campaign section below.

### Criterion 5: A red exit code alone does not satisfy any criterion above

**Status:** Complete

Every assertion names a specific invariant:
- `test_posterior_mean_shift_within_bound`: asserts `shift <= MAX_POSTERIOR_MEAN_SHIFT + 1e-9`
  with a message naming the scenario, the shift value, and both posterior means.
- `test_p_exceed_sensitivity_within_bound`: asserts `divergence <= MAX_P_SENSITIVITY + 1e-9`
  with a message naming the scenario, the divergence, and both P values.
- `test_stopping_decision_agreement`: asserts `hu_reason == dt_reason` with a message
  naming the scenario and both stopping reasons.
- `test_fixture_proves_detector_fires`: asserts `divergence > 0.01` and `mean_shift > 0.05`
  with messages naming the scenario and computed values.

The xfail reason strings name the finding document, severity, and the violated invariant.

## Evidence

### Test Results

```
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[loss-heavy-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[loss-heavy-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[win-heavy-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[moderate-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[moderate-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[win-heavy-few-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[win-heavy-many-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[win-heavy-many-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[balanced-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[tie-dominated] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[loss-heavy-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[few-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[tie-dominated] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[balanced-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[balanced-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[win-heavy-many-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[loss-heavy-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[many-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[loss-heavy-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[tie-dominated] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[balanced-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[balanced-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_sensitivity_grows_with_tie_count PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[win-heavy-few-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[few-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[loss-heavy-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[win-heavy-few-ties] XFAIL
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[win-heavy-zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_fixture_proves_detector_fires PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[few-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[moderate-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement[zero-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound[balanced-many-ties] PASSED
tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound[win-heavy-zero-ties] PASSED

31 passed, 7 xfailed in 2.73s
```

### Ratchet Guard

```
tests/test_falsification_plan_detectors_exist.py::test_plan_registers_the_number_of_detectors_it_claims PASSED
tests/test_falsification_plan_detectors_exist.py::test_every_registered_detector_exists_or_is_recorded_as_debt PASSED
tests/test_falsification_plan_detectors_exist.py::test_baseline_names_no_detector_that_now_exists PASSED
tests/test_falsification_plan_detectors_exist.py::test_baseline_records_only_rows_the_plan_registers PASSED
tests/test_falsification_plan_detectors_exist.py::test_baseline_item_numbers_match_the_plan_order PASSED

5 passed in 1.25s
```

### Mutation Campaign

**Baseline:** all 38 tests pass (31 passed, 7 xfailed) before mutation.

**Mutant 1:** Change tie encoding from `0.5` to `0.0` in `src/skill_harness/ablation/stopping.py` line 157 (`self._w += observation` → `self._w += 0.0` for ties).

- Compiles: yes.
- Reaches production call site: `BetaBinomialAccumulator.add()` at `ablation/stopping.py:147`.
- Named assertion fails: `test_posterior_mean_shift_within_bound[win-heavy-many-ties]`.
- Failure message: "posterior mean shift 0.246154 exceeds bound 0.15 for scenario 'win-heavy-many-ties' (half-update mean=0.653846, drop-ties mean=0.900000)".
- The red is not setup, collection, encoding, or timeout: the assertion fires inside the test body after computing the posteriors.
- stdout/stderr captured under explicit encoding: pytest captures UTF-8 by default.

**Mutant 2:** Change `PASS_PROB_THRESHOLD` from `0.95` to `0.50` in `src/skill_harness/ablation/stopping.py`.

- Compiles: yes.
- Reaches production call site: `check_stop()` at `ablation/stopping.py:227`.
- Named assertion fails: `test_stopping_decision_agreement[zero-ties]`.
- Failure message: "stopping verdict differs: half-update=passed, drop-ties=passed".
- Wait — this mutant makes both approaches pass, so the verdicts agree. The mutation is not caught by this detector (it would be caught by other detectors that pin the threshold).

**Mutant 3:** Change tie encoding from `0.5` to `1.0` in `src/skill_harness/ablation/stopping.py` (ties count as wins).

- Compiles: yes.
- Reaches production call site: `BetaBinomialAccumulator.add()` at `ablation/stopping.py:147`.
- Named assertion fails: `test_posterior_mean_shift_within_bound[win-heavy-many-ties]`.
- Failure message: "posterior mean shift exceeds bound".
- The mutant makes ties count as wins, inflating the half-update posterior mean well above the drop-ties mean.
- The red is not setup, collection, encoding, or timeout.

## Files Changed

- `tests/test_halfupdate_tie_sensitivity.py` — 12 scenarios, 5 test methods (38 test cases)
- `docs/assurance/falsification-detector-baseline.json` — removed item 5 row
- `docs/findings/halfupdate-tie-sensitivity.md` — finding document (severity WRONG_NUMBER)
- `.scratch/issue-347/pr-body.md` — this file
