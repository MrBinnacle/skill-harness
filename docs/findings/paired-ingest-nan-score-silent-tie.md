# A NaN score in a paired log is recorded as a tie

**Status:** OPEN. **Severity:** WRONG_NUMBER (a missing measurement becomes evidence).
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

## Next action

Repair ticket filed (see the issue referencing this document). Detector stays strict-xfail
until the refusal lands.
