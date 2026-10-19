# PR: On-Irreducibility additions 3, 5, 6 — SERS schema plumbing (#526)

Three of the six ratified On-Irreducibility additions land as SERS schema
keys and a written record, so a receipt can state what a claim covers, when
it expires and what family the skill belongs to.

## Files changed

- `docs/sers/sers.schema.json` — four new optional properties, version enum
  bumped to 1.5.0, version gate added
- `docs/ratifications/MIRROR-0001-on-irreducibility.md` — additions 3, 5, 6
  moved from UNLANDED to landed with schema key names
- `tests/test_sers_conformance.py` — six new tests for 1.5.0 and the new
  fields
- `tests/test_drift_check.py` — updated DC-17 shape test to account for
  landed additions

## Schema changes

### New optional properties (additions 3, 5, 6)

| Property | Addition | Type | Author-typed |
| --- | --- | --- | --- |
| `implementation_family` | 3 | `string` | yes |
| `claim_scope` | 5 | `string` | yes |
| `retest_triggers` | 6 | `string` | yes |
| `expiry_state` | 6 | `enum` | no — read from VIEW |

All four are optional at every version. None appear in the top-level
`required` array. The schema's `additionalProperties: false` was already
true, so these are the only new keys a receipt may carry.

### Version gate

`1.5.0` added to the `sers_version` enum. The `allOf` gate for 1.5.0
mirrors the 1.4.0 gate: `subject_identity` and `delivery` required,
`subject_identity.subject_model` required. No new fields are made required
at 1.5.0 — all three additions are author-typed and optional.

### `expiry_state` enum

The three values come from the existing `frozen_cases_with_currency` VIEW:

- `current` — metric version and implementation hash match the current
  metric version
- `stale` — a newer version exists or the hash mismatches
- `no_current_metric_version` — no audited valid metric version exists

The field is populated by reading the VIEW, never recomputing it. This
follows the `build_delivery` precedent of reading a computed value.

## Acceptance criteria

### AC1: Each addition's `landed_as` names a real schema key

Addition 3 → `implementation_family`
Addition 5 → `claim_scope`
Addition 6 → `retest_triggers`, `expiry_state`

DC-17 checks string presence under `docs/sers/` or `src/skill_harness/`.
All four strings appear in `docs/sers/sers.schema.json` as property names.
Verified by running `python scripts/drift_check.py` which reports DC-17 OK.

Beyond the string check: each landed_as value is an actual property defined
in the schema's `properties` object with type, description, and constraints.
`expiry_state` carries an enum constraint matching the VIEW's output values.

### AC2: No addition marked landed by pointing at a symbol that merely mentions it

Each landed_as value is a property name, not a prose mention. The test
`test_dc17_real_mirror_names_source_and_six_unlanded_additions` asserts the
exact landed_as values: `implementation_family`, `claim_scope`,
`retest_triggers`, `expiry_state`. Each is verified to be a defined schema
property by `test_schema_new_properties_are_optional` which checks the
top-level required list does not include them (confirming they exist as
optional properties, not just prose mentions).

### AC3: Addition 6's expiry value read from existing currency VIEW

`expiry_state` is an enum with values `current`, `stale`,
`no_current_metric_version` — exactly the three outputs of the
`frozen_cases_with_currency` VIEW defined in
`src/skill_harness/storage/migrations_sql/evidence/0401_stale_frozen_view.sql`.
The field is never recomputed; the receipt author reads the VIEW output and
records it. This follows the `build_delivery` precedent (reading a computed
value, never recalculating it).

### AC4: Every receipt in the tree still validates; poison fixtures still fail

All 5 receipts under `docs/sers/receipts/` validate against the updated
schema (test: `test_receipt_conforms_to_sers_schema`, 5 parametrized cases).
All 12 poison fixtures under `tests/fixtures/sers/poison_*.json` still fail
validation (test: `test_poisoned_fixture_fails_validation`, 12 parametrized
cases). The 2 minted fixtures also validate.

### AC5: `drift_check.py` passes and conformance suite is green

`python scripts/drift_check.py` reports PASS on all 17 live contracts
including DC-17. The full conformance suite (`test_sers_conformance.py`)
passes 47 tests (41 original + 6 new). `test_receipts_index.py` passes 18
tests.

## Tests

### New tests in `test_sers_conformance.py`

1. `test_v15_with_all_new_fields_validates` — builds a 1.5.0 instance with
   all four new fields and validates it against the schema. Pins that the
   schema accepts the new version and properties.

2. `test_v15_without_new_fields_still_validates` — same 1.5.0 instance with
   the four new fields removed. Pins that the fields are optional and do not
   break existing receipt shapes.

3. `test_expiry_state_rejects_invalid_value` — sets `expiry_state` to
   `"expired"` (not in the enum) and asserts ValidationError. Pins the enum
   constraint.

4. `test_v14_receipt_without_new_fields_still_validates` — the existing
   1.4.0 instance without any new fields validates. Pins backward
   compatibility.

5. `test_schema_15_version_in_enum` — asserts `"1.5.0"` is in the
   `sers_version` enum. Pins the version bump.

6. `test_schema_new_properties_are_optional` — asserts none of the four new
   keys appear in the top-level `required` array. Pins the author-typed
   contract.

### Updated test in `test_drift_check.py`

`test_dc17_real_mirror_names_source_and_six_unlanded_additions` — updated
count from 4 to 5 landed_as rows (addition 1 UNLANDED, additions 3 and 5
landed, addition 6 landed with two keys). Assertions added for the four
landed symbols.

### Red-phase verification

Each new test was run before the schema change and confirmed to fail for
the right reason:
- `test_v15_with_all_new_fields_validates` — fails with "1.5.0 is not one of
  ['1.0.0', ...]" (version not in enum)
- `test_expiry_state_rejects_invalid_value` — fails because `expiry_state`
  is not a recognized property (additionalProperties: false)
- `test_schema_15_version_in_enum` — fails because 1.5.0 not in enum
- `test_schema_new_properties_are_optional` — fails because the properties
  don't exist in the schema yet

All six pass after the schema change.

## Mutation campaign

No mutation receipt was requested by this ticket. The ticket is schema
plumbing — no measurement logic changed.
