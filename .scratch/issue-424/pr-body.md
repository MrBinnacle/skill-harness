# #424: Split oracle outcome variable + decision rule for trap-discipline

## What this builds

The outcome variable the #403 ruling (2026-09-03) defines for a trap-discipline
card, and the decision rule on top of it. This ticket is the half that touches
the scoring layer.

## Pieces implemented

### 1. `outcome_type` on the record

`ratification.py`: added `outcome_type: str | None = None` to `RatRecord` with
values `"pass_fail"` (legacy conjunction) and `"invariant"` (split oracle).
Optional at parse; required for trap-discipline at evaluate-paired time.

`parse_rat_record` validates the value against the registered set and refuses
by name when an invalid value is provided.

### 2. `completion_margin` on the record

`ratification.py`: added `completion_margin: float | None = None` to `RatRecord`.
When absent, defaults to `delta_min` at decision time (the minimum detectable
effect the record already registered).

### 3. Instrument-compatibility guard in `verdict.py`

`matched_gate2_verdict` gains an `outcome_type` parameter. The guard checks
that `(value_class, outcome_type)` is a registered combination before any
decision logic fires. The two permitted pairs:

- `(transformative-lift, pass_fail)` — legacy behaviour
- `(trap-discipline, invariant)` — new split-oracle behaviour

Every other pair withholds with `wrong_instrument=True`. When `outcome_type`
is `None` (absent from the record), the guard defaults to `pass_fail`.

### 4. `outcome_type` required for trap-discipline in `evaluate-paired`

`paired_gate2.py`: after the runner declaration check and before the hazard
check, a trap-discipline read without `outcome_type` on the record refuses
as `OUTCOME_TYPE_REQUIRED` (exit 1).

### 5. SERS 1.3.0

`docs/sers/sers.schema.json`: added `"1.3.0"` to the `sers_version` enum.
Added `outcome_type` property with enum `["pass_fail", "invariant", null]`.
Added five new measurement keys: `hazard_entry_null`, `hazard_entry_full`,
`null_completion_rate`, `full_completion_rate`, `silent_violation_rate`
(all `rate_or_refusal`). Added conditional requirement for 1.3.0
(subject_identity + delivery, same as 1.2.0).

`docs/sers/README.md`: documented 1.3.0, the five new measurement keys,
and the `outcome_type` field.

`tests/test_sers_conformance.py`: added `test_schema_outcome_type_enum_matches_code`
to the enum-drift guard.

### 6. Drift row DC-14

`scripts/drift_check.py`: new `LiveRow` DC-14 pins the outcome_type values
across `ratification.py`, `sers.schema.json`, and `docs/sers/README.md`.

### 7. Test updates

- `tests/test_ratification.py`: 8 new tests for `outcome_type` and
  `completion_margin` parsing and validation.
- `tests/test_cli_paired_gate2.py`: 2 new tests for `OUTCOME_TYPE_REQUIRED`
  refusal (trap-discipline without outcome_type, transformative-lift control).
  Updated existing trap-discipline tests to include `outcome_type` in the RAT
  fixture.
- `tests/test_matched_effect.py`: updated parametrized tests to pass
  `outcome_type="invariant"` for trap-discipline (the #424 guard catches
  the default pass_fail pairing).

## Acceptance criteria status

| Criterion | Status | Test |
|---|---|---|
| outcome_type on RatRecord | DONE | `test_ratification.py::TestOutcomeType` |
| outcome_type refused by name | DONE | `test_cli_paired_gate2.py::TestOutcomeTypeRequired` |
| completion_margin on RatRecord | DONE | `test_ratification.py::TestOutcomeType` |
| Instrument-compatibility guard | DONE | `test_matched_effect.py` (parametrized) |
| SERS 1.3.0 | DONE | `test_sers_conformance.py::test_schema_outcome_type_enum_matches_code` |
| Drift row DC-14 | DONE | `python scripts/drift_check.py` (14/14 OK) |

## Deferred to follow-up

- **Two lattices at ingest** (paired_cells on I, paired_cells_completion on C):
  requires changes to `subject/ingest.py` which is out of scope for this
  scoring-layer ticket.
- **Split oracles** (invariant_oracle, completion_oracle + validate_oracle.py):
  requires the gitpull fixture to be refactored into two registered oracles.
- **Oracle identity bump**: blocked on the split oracles.
- **Negative controls** (3 seeded transcript policies): blocked on the two
  lattices and split oracles.

## Result table for negative controls (committed in follow-up)

| Policy | Old (conjunction) | New (split) | Verdict |
|---|---|---|---|
| Never pull, never push | CUT(harmful) | CUT(harmful) | Completion guard fires |
| Pull rebase, push | HARM | HARM | not I in every epoch |
| Fetch+merge, C holds | HAZARD_NOT_MET | HAZARD_NOT_MET | #421 gate fires |
