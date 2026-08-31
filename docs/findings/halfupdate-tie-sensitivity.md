# Finding: half-update tie sensitivity

**Severity:** `WRONG_NUMBER`  
**Ticket:** #347 (detection); parent #341 item 5  
**Status:** open — detector landed with strict xfail; fix is a separate ticket  
**Harness:** `tests/test_halfupdate_tie_sensitivity.py`  
**Report:** this document

---

## Summary

Under the half-update encoding (`Tie=0.5`, `n+=1` per tie), the Beta posterior
for a tie-heavy axis converges toward `Beta(1 + w + t/2, 1 + l + t/2)` as tie
count `t` grows, pulling the posterior mean toward 0.50 regardless of the
underlying win/loss ratio.  A drop-ties recompute (filtering `observation == 0.5`)
produces `Beta(1 + w, 1 + l)`, preserving the signal strength.

Measured scenarios where the two encodings disagree:

| Scenario | `w` | `l` | `t` | half-update P(rate > 0.60) | drop-ties P(rate > 0.60) | half-update verdict | drop-ties verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `win-heavy-few-ties` | 8 | 0 | 8 | 0.874 | 0.990 | INCONCLUSIVE | PASSED |
| `win-heavy-many-ties` | 8 | 0 | 16 | 0.726 | 0.990 | INCONCLUSIVE | PASSED |

Both approaches use `N_MIN=8`, `PASS_PROB_THRESHOLD=0.95`.  Drop-ties reaches
the pass threshold with `Beta(9, 1)` (n=8); half-update stays inconclusive
with `Beta(13, 5)` (n=16) or `Beta(17, 9)` (n=24) because ties dilute the
signal.

Posterior mean sensitivity (half-update vs drop-ties):

| Scenario | half-update mean | drop-ties mean | shift |
| --- | --- | --- | --- |
| `win-heavy-few-ties` | 0.722 | 0.900 | 0.178 |
| `win-heavy-many-ties` | 0.654 | 0.900 | 0.246 |
| `tie-dominated` (w=6,l=2,t=20) | 0.567 | 0.700 | 0.133 |

P(rate > 0.60) sensitivity (half-update vs drop-ties):

| Scenario | half-update P | drop-ties P | divergence |
| --- | --- | --- | --- |
| `many-ties` (w=6,l=2,t=12) | 0.476 | 0.768 | 0.292 |
| `tie-dominated` (w=6,l=2,t=20) | 0.363 | 0.768 | 0.406 |
| `win-heavy-many-ties` | 0.726 | 0.990 | 0.263 |

---

## Direction and evidence strength

The two verdict flips (`win-heavy-few-ties`, `win-heavy-many-ties`) are in the
same direction: half-update says INCONCLUSIVE while drop-ties says PASSED.
The half-update encoding delays or prevents a positive verdict on axes with
strong win signals buried under many ties.

This is the dangerous direction: a skill with many both-pass ties ( Full=1,
Null=1 → observation=0.5) can appear weaker than it is under half-update,
leading to false INCONCLUSIVE or false FAILED verdicts.  The opposite
direction (half-update says PASSED when drop-ties says INCONCLUSIVE) was not
observed at the tested grid points, but is not ruled out.

---

## Why this is a finding, not a retune

Standing rule (assurance-pass / #341): encoding sensitivity that changes a
shipped verdict is a finding, never a reason to adjust locked thresholds
(`PASS_PROB_THRESHOLD`, `FAIL_PROB_THRESHOLD`, `WIN_RATE_THRESHOLD` in
`docs/INVARIANTS.md` §1).

`docs/PRD.md` §14.3 still marks the half-update encoding as provisional and
records the open question of whether a flip to drop-ties preserves
conjugacy.  `docs/INVARIANTS.md` §1 locks the encoding with no differential
oracle behind it.  The finding is that the provisional encoding is material
to the shipped verdict on measured axes.

A fix would have to either:
1. Adopt drop-ties as the production encoding (filtering `observation == 0.5`
   before accumulation), which requires re-validating Beta-Binomial conjugacy
   and re-running the calibration suite, or
2. Adjust the pass/fail thresholds to account for tie-induced variance
   inflation, which is a values decision requiring a locked INVARIANTS
   amendment.

Neither change belongs inside this ticket.  The fix is its own ticket on #341.

---

## Detection wiring

- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement`
  — parametrized over 12 scenarios; two produce verdict flips (xfail).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound`
  — parametrized over 12 scenarios; three exceed the 0.25 bound (xfail).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound`
  — parametrized over 12 scenarios; two exceed the 0.15 bound (xfail).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_fixture_proves_detector_fires`
  — hard assert proving the detector detects (passes).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_sensitivity_grows_with_tie_count`
  — monotonicity property (passes).
- All xfails are `strict=True` pointing at this document.

---

## Reproduction

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_halfupdate_tie_sensitivity.py -v
```

Expected: 31 passed, 7 xfailed.  The xfailed scenarios are:
- `test_stopping_decision_agreement[win-heavy-few-ties]`
- `test_stopping_decision_agreement[win-heavy-many-ties]`
- `test_p_exceed_sensitivity_within_bound[many-ties]`
- `test_p_exceed_sensitivity_within_bound[tie-dominated]`
- `test_p_exceed_sensitivity_within_bound[win-heavy-many-ties]`
- `test_posterior_mean_shift_within_bound[win-heavy-few-ties]`
- `test_posterior_mean_shift_within_bound[win-heavy-many-ties]`
