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

### 4. Decision rule (#403 §3)

- BENEFIT on I + Full completion non-inferior to Null within `completion_margin` → KEEP
- BENEFIT on I + Full completion more than margin below Null → CUT(harmful)
- HARM → CUT(harmful)
- EQUIVALENT + Null violation rate at/below `delta_min` floor → CUT(subsumed)
- EQUIVALENT otherwise → CUT(no_lift)
- UNRESOLVED → CANT_TELL_YET

Completion non-inferiority: `Full_C >= Null_C - margin` (not an absolute Full_C floor).

### 5. `outcome_type` required for trap-discipline in `evaluate-paired`

`paired_gate2.py`: after the runner declaration check and before the hazard
check, a trap-discipline read without `outcome_type` on the record refuses
as `OUTCOME_TYPE_REQUIRED` (exit 1).

### 6. Two lattices at ingest + split oracle scorers

`subject/ingest.py` (oracle identity **0.5.0**): reads `invariant_oracle` and
`completion_oracle` scores when present; writes `outcome_type`,
`paired_cells_completion`, and `silent_violation` into `config_json`.

`inspect_adapter.py`: registers the two split scorer names.

### 7. SERS 1.3.0

`docs/sers/sers.schema.json`: `"1.3.0"`; `outcome_type`; five new measurement
keys. README documents them. Drift row DC-14 pins the enum.

### 8. Negative-control result table

Committed at `docs/sers/receipts/issue-424-negative-controls.md` and pinned by
`tests/test_cli_paired_gate2.py`.

## Acceptance criteria status

| Criterion | Status | Test |
|---|---|---|
| outcome_type on RatRecord | DONE | `test_ratification.py::TestOutcomeType` |
| outcome_type refused by name | DONE | `test_cli_paired_gate2.py::TestOutcomeTypeRequired` |
| completion_margin on RatRecord | DONE | `test_ratification.py::TestOutcomeType` |
| Instrument-compatibility guard | DONE | `test_matched_effect.py` |
| EQUIVALENT trap-discipline table | DONE | `test_matched_effect.py::test_equivalent_trap_discipline_invariant_*` |
| Completion non-inferiority | DONE | `TestCompletionMarginFlip` |
| SERS 1.3.0 | DONE | `test_sers_conformance.py::test_schema_outcome_type_enum_matches_code` |
| Drift row DC-14 | DONE | `python scripts/drift_check.py` |
| Negative controls + result table | DONE | `docs/sers/receipts/issue-424-negative-controls.md` |
| Oracle identity 0.5.0 | DONE | `TestIngestOracleIdentity050` |

## Note on never-pull + CUT(harmful)

Gate-2 #37 maps zero-discordance (I=1 every pair) to UNRESOLVED, so the
completion guard (KEEP-only) does not fire on that seed. The control still
forbids KEEP. CUT(harmful) via completion is pinned by the BENEFIT +
below-margin seed.
