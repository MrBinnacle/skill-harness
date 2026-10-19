# What the paired-ingest boundary structurally cannot see

**Status:** RECORDED (residual risk, not a repairable defect). **Severity:** BOUNDARY.
**Found by:** `tests/test_paired_arm_epoch_adversarial.py` (falsification plan item 8, #350),
2026-08-31.

## The surface that IS closed

The item 8 detector measured the arm-swap surface as fully refused, correcting the plan's
open question:

- A swap that keeps the samples' true `condition` labels fails the role/condition check.
- A label-consistent swap that places invoked samples in the Null role fails the
  control-arm contamination check (#46).
- A label-consistent swap that presents a Full role with zero invocations fails the
  dead-treated-arm check (`ZeroInvocationError`, pi_c_hat = 0). This third refusal was not
  predicted by the detector's own pre-registration, which had reasoned the case invisible;
  the first run refuted the prediction and the correction is recorded in the test module.

Passing all three simultaneously requires fabricated invocation traces inside the message
stream, which is forgery, not mis-keying.

## The residual undetectable

**A permutation of epoch labels within the same epoch set, in one arm.** The epoch number is
itself the join key: `full_by_epoch[e]` is paired with `null_by_epoch[e]` and nothing else
ties a Full sample to a Null sample. If one arm's epochs are relabelled within the same set,
the sets compare equal, every sample is internally well formed, and the pairs silently
decouple. `test_epoch_permutation_within_set_is_structurally_invisible` pins this acceptance
as a characterisation test so any future defence forces this document to be revisited.

## Why this is recorded rather than repaired

Detecting a within-set permutation from inside the pair is impossible in general: the
corrupted quantity is the only linking information. A defence would need out-of-band pairing
evidence (for example a per-epoch content fingerprint shared across arms at generation time,
or task-input hashes carried per sample). That is a design change to the log producer, not a
validation the ingest boundary can add.

## Bound on the damage

Permutation cannot invert an effect that is constant across epochs (all wins stay all wins);
it corrupts exactly the epoch-level pairing structure, so its damage is bounded by the
within-arm score variance. Homogeneous tables — the ones strong verdicts come from — are the
least damaged; heterogeneous tables, where pairing carries the signal, are the most.

## Next action

None owed now. *Revisit if:* the log producer starts carrying per-epoch task-input
fingerprints (then ingest can and should verify the join), or the characterisation test goes
red.
