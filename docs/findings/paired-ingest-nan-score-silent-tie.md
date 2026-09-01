# A NaN score in a paired log is recorded as a tie

**Status:** RESOLVED 2026-09-01 by #363 at commit `210ac93`. **Severity:** WRONG_NUMBER
(a missing measurement becomes evidence).
**Found by:** `tests/test_paired_arm_epoch_adversarial.py::test_nan_score_is_refused_or_fails_closed`
(falsification plan item 8, #350), first run 2026-08-31.
**Registered in advance:** the module docstring predicted this exact mechanism and outcome
before the first run.

## What happened

`_score_to_float` (`src/skill_harness/subject/ingest.py`) accepts any `int | float` value,
including `float('nan')`. `_observation(full_score, null_score)` decides win/loss/tie by two
ordered comparisons; both comparisons with NaN are False, so the fall-through returns 0.5.

## The mechanism

A sample whose score is absent-but-encoded-as-NaN (a scorer crash, a serialization gap, an
upstream tool emitting NaN for unscorable output) flows through parse and write untouched and
lands in `oracle_verdicts.observation` as 0.5 — the same value as a genuine measured tie.
Measured on first run: a beneficial pair with one NaN epoch wrote observations
`[0.5, 1.0, 1.0]`.

## Consequence and allocation

Every Gate-2 table built from the pair is diluted toward no-effect. Enough NaN epochs turn a
real benefit into `CANT_TELL_YET` or a real harm into a pass — in either direction the minted
verdict claims a measurement that never happened. The reader of the receipt pays: the
half-update `w` carries the phantom tie at half weight and nothing marks it.

## What a fix has to change

`_score_to_float` should refuse non-finite values the way it refuses unmappable strings —
`math.isfinite(value)` or raise `EvalLogIngestError` naming the sample — OR the pydantic
`ParsedSample.score_value` field should carry `allow_inf_nan=False`. Refusal at parse/validate
time is the module's own stated convention for apparatus errors. The strict xfail in the
detector un-marks in the same change.

## Uncertainty

None on the mechanism: the failure is deterministic and reproduced by construction. Open only
whether production `.eval` logs have ever actually carried NaN scores; no historical re-scan
was run here.

## The repair that landed

Both surfaces named above were closed, not one of them. `ParsedSample.score_value` carries
`allow_inf_nan=False`, so a non-finite score cannot be constructed; `_score_to_float` raises
`EvalLogIngestError` naming the log path, so the parse path keeps its typed refusal.

The model layer is the enforcing surface, and that placement was measured rather than chosen.
PR #364's receipt recorded M4 as an honest survivor: a guard in `_score_to_float` alone left
this detector red, because the detector constructs `ParsedSample` directly and the write path
never reaches the helper. `docs/assurance/nan-score-refusal-mutation-receipt.md` records the
converse case killing, in an isolated worktree, against a baseline that passed first.

The detector's strict xfail is removed and its registered bound is unchanged: no observation
may be 0.5.

## Next action

None for the mechanism. The open uncertainty above is unchanged: no historical re-scan of
stored `.eval` logs was run, so whether a production log has ever carried a non-finite score
is still unmeasured. A re-scan would be a separate ticket, and its result cannot change the
refusal.
