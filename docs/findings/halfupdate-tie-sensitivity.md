# Finding: half-update tie sensitivity

**Severity:** `WRONG_NUMBER`  
**Ticket:** #347 (detection); parent #341 item 5  
**Status:** RULED and migrated (#368 Path C) — detector landed with strict xfail;
the estimand was ruled on #368 (2026-08-31) and recorded in `docs/INVARIANTS.md`
§8. The ablation runner now routes through `DiscordantStoppingAccumulator`
(Gate-2 discordant machinery); the seven xfails are removed with bounds unchanged.
**Harness:** `tests/test_halfupdate_tie_sensitivity.py`  
**Report:** this document

---

## Ruling and where it is recorded (#368, 2026-08-31)

The estimand of record is the **discordant table** (McNemar/sign-test convention).
Half-update stays as the interim operational heuristic. `docs/INVARIANTS.md` §8
carries the measured sensitivity, the corrected description of the error, and the
gate-by-gate result.

One correction from that ruling's own amendment belongs here, because this document's
framing invited it: **the error is NOT monotone dilution toward 0.5**. A sweep over
`w, l in [0, 60]`, `t in [1, 80]` found 80,011 grid points where half-update RAISES
`P(rate > 0.60)` relative to drop-ties. What survives is narrower and measured: zero
grid points cross the PASS gate that drop-ties keeps below it, and three escape the
FAIL gate — all to INCONCLUSIVE, never to PASS.

## Summary

Under the half-update encoding (`Tie=0.5`, `n+=1` per tie), the Beta posterior
for a tie-heavy axis converges toward `Beta(1 + w + t/2, 1 + l + t/2)` as tie
count `t` grows, pulling the posterior mean toward 0.50 regardless of the
underlying win/loss ratio. A drop-ties recompute (filtering `observation == 0.5`)
produces `Beta(1 + w, 1 + l)`, preserving the signal strength.

Both arms are measured through the production accumulator
(`BetaBinomialAccumulator.add` / `check_stop`). Measured scenarios where the
two encodings disagree:

| Scenario | `w` | `l` | `t` | half-update P(rate > 0.60) | drop-ties P(rate > 0.60) | half-update verdict | drop-ties verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `win-heavy-few-ties` | 8 | 0 | 8 | 0.874 | 0.990 | inconclusive (`None`) | PASSED |
| `win-heavy-many-ties` | 8 | 0 | 16 | 0.726 | 0.990 | inconclusive (`None`) | PASSED |

Both approaches use `N_MIN=8`, `PASS_PROB_THRESHOLD=0.95`. Drop-ties reaches
the pass threshold with `Beta(9, 1)` (n=8); half-update stays inconclusive
with `Beta(13, 5)` (n=16) or `Beta(17, 9)` (n=24) because ties dilute the
signal. Inconclusive means `check_stop().stopping_reason is None`.

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

Documented bounds in the harness: `MAX_POSTERIOR_MEAN_SHIFT = 0.15`,
`MAX_P_SENSITIVITY = 0.25`. Verdict agreement has zero tolerance.

---

## Direction and evidence strength

The two verdict flips (`win-heavy-few-ties`, `win-heavy-many-ties`) are in the
same direction: half-update stays inconclusive while drop-ties says PASSED.
The half-update encoding delays or prevents a positive verdict on axes with
strong win signals buried under many ties.

This is the dangerous direction: a skill with many both-pass ties (Full=1,
Null=1 → observation=0.5) can appear weaker than it is under half-update,
leading to false inconclusive or false FAILED verdicts. The opposite
direction (half-update says PASSED when drop-ties stays inconclusive) was not
observed at the tested grid points, but is not ruled out.

---

## Why this is a finding, not a retune

Standing rule (assurance-pass / #341): encoding sensitivity that changes a
shipped verdict is a finding, never a reason to adjust locked thresholds
(`PASS_PROB_THRESHOLD`, `FAIL_PROB_THRESHOLD`, `WIN_RATE_THRESHOLD` in
`docs/INVARIANTS.md` §1).

`docs/PRD.md` §14.3 still marks the half-update encoding as provisional and
records the open question of whether a flip to drop-ties preserves
conjugacy. `docs/INVARIANTS.md` §1 locks the encoding with no differential
oracle behind it. The finding is that the provisional encoding is material
to the shipped verdict on measured axes.

A fix would have to either:
1. Adopt drop-ties as the production encoding (filtering `observation == 0.5`
   before accumulation), which requires re-validating Beta-Binomial conjugacy
   and re-running the calibration suite, or
2. Adjust the pass/fail thresholds to account for tie-induced variance
   inflation, which is a values decision requiring a locked INVARIANTS
   amendment.

Neither change belongs inside this ticket. The fix is its own ticket on #341.

---

## Detection wiring (post #368 Path C migration)

- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement`
  — parametrized over 12 scenarios; production (`DiscordantStoppingAccumulator`)
  and drop-ties agree on every row (bounds unchanged; xfails removed).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_p_exceed_sensitivity_within_bound`
  — divergence is 0 on every row under the migrated path.
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_posterior_mean_shift_within_bound`
  — mean shift is 0 on every row under the migrated path.
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_fixture_proves_legacy_halfupdate_still_diverges`
  — positive control: the retired half-update encoding still exceeds both bounds
  on the original extreme fixture (7w, 1l, 30t).
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_migration_collapses_divergence_on_extreme_fixture`
  — migration control: production matches drop-ties on the same extreme fixture.
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_win_heavy_many_ties_passes_where_halfupdate_was_inconclusive`
  — gate scenario from this finding (w=8, l=0, t=16): production PASSED, legacy INCONCLUSIVE.
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_runner_config_records_ratification_thresholds`
  — `runs.config_json` carries `gate2_stopping.rat_id` and the registered thresholds.
- `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_runner_imports_discordant_accumulator`
  — runner source constructs `DiscordantStoppingAccumulator`, not the half-update accumulator.

---

## Reproduction

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_halfupdate_tie_sensitivity.py -v
```

Expected: all passed, 0 xfailed.
