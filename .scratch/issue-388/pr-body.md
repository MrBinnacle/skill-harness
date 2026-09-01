# SERS delivery block: value attribution for skill products (#388)

## What changed

SERS receipts now carry a `delivery` block identifying which of a skill's two
products (description or body) carried the measured value. The change is additive:
a new minor version (`1.2.0`), every existing receipt still validates, and
receipts from different versions stay marked non-comparable by the version enum.

## Evidence by acceptance criterion

### AC1: `sers_version` enum gains the next minor value; delivery block optional for older, required for new

**Built:** Added `"1.2.0"` to the `sers_version` enum in `sers.schema.json`. Added an `allOf`
conditional requiring `delivery` when `sers_version` is `"1.2.0"`. The existing `subject_identity`
requirement for `1.1.0` is unchanged.

**Test:** `test_receipt_conforms_to_sers_schema` (parametrized) — the existing `1.0.0` and
`1.1.0` receipts continue to validate; a new `1.2.0` fixture
(`tests/fixtures/sers/minted_synthetic_control_v1_2_0.json`) validates. `test_poisoned_fixture_fails_validation`
catches the new `poison_delivery_missing_v12.json` which omits `delivery` on a `1.2.0` receipt.

**Observation:** Before the schema change, no `1.2.0` version existed. After, the new fixture
validates and the poison fails with `'delivery' is a required property`.

### AC2: `delivery` carries exposure, pi_c, channel vocabulary, typed refusal shape

**Built:** Defined the `delivery` property in the schema with three sub-fields:
- `channel`: closed enum (`description_only`, `body_and_description`, `not_instrumented`)
- `exposure`: `oneOf` measured object (`value`, optional `passes`/`epochs`) or refusal
- `pi_c`: `oneOf` measured object (`invocations`, `trials`, `hat`, `ci_low`, `ci_high`, `confidence`, `detector`) or refusal

Added two cross-field `allOf` conditions:
- `channel: description_only` requires `pi_c.hat == 0` (or `pi_c` as a refusal)
- `channel: body_and_description` requires `pi_c.invocations > 0` (or `pi_c` as a refusal)

**Test:** `test_poisoned_fixture_fails_validation` catches two poison fixtures:
- `poison_delivery_description_only_nonzero_pi_c.json`: `hat=0.5` with `channel=description_only` — fails the cross-field rule
- `poison_delivery_body_and_description_zero_invocations.json`: `invocations=0` with `channel=body_and_description` — fails the cross-field rule

**Observation:** Both poisons fail with clear schema errors. The `1.2.0` fixture uses
`channel: not_instrumented` with `pi_c` as a refusal, which avoids the cross-field rules
and validates cleanly.

### AC3: Poison fixtures that must fail

**Built:** Three poison fixtures under `tests/fixtures/sers/`:
1. `poison_delivery_description_only_nonzero_pi_c.json` — `hat > 0` with `description_only`
2. `poison_delivery_body_and_description_zero_invocations.json` — `invocations = 0` with `body_and_description`
3. `poison_delivery_missing_v12.json` — `1.2.0` with no `delivery` block

**Test:** `test_poisoned_fixture_fails_validation` (parametrized, existing) automatically
picks up all `poison_*.json` fixtures. All three fail validation as required.

**Observation:** Before the schema change, these poisons did not exist. After, the
parametrized test runs 7 poison fixtures (4 existing + 3 new) and all fail.

### AC4: Receipt minting path reads pi_c and exposure from run config_json

**Built:** Added `src/skill_harness/sers/delivery.py` with `build_delivery(config_json)`.
This function reads `pi_c` and `exposure` from a parsed config_json dict and constructs a
conforming `delivery` block. It never recomputes either figure — values are copied verbatim
from the ingest-written config_json.

**Test:** `tests/test_delivery.py` (7 tests):
- `test_build_delivery_body_and_description`: invocations > 0 → correct channel
- `test_build_delivery_description_only`: invocations == 0 → correct channel
- `test_build_delivery_reads_not_recomputes`: pi_c values are copied, not recalculated
- `test_build_delivery_with_exposure`: exposure data carried through
- `test_build_delivery_missing_pi_c_yields_not_instrumented`: empty config → not_instrumented
- `test_delivery_block_conforms_to_schema`: output validates against schema
- `test_not_instrumented_delivery_conforms_to_schema`: refusal shape validates

**Observation:** The function reads config_json keys verbatim. The test
`test_build_delivery_reads_not_recomputes` pins this by asserting `hat == config["pi_c"]["hat"]`.

### AC5: Sitegen renders the delivery block on the receipt page

**Built:** Added `_delivery_section()` to `src/skill_harness/sitegen/render.py` and
`$delivery_section` to `templates/skill.html`. The section renders between measurements
and evidence admissibility. Channel vocabulary is rendered in plain words (e.g.,
"The standing description carried the value; the skill body was never read").
Receipts without a delivery block produce an empty string (no section rendered).

Added `_DELIVERY_CHANNEL_TEXT` mapping channel enum values to prose.

**Test:** `tests/test_sitegen_delivery.py` (8 tests):
- `test_delivery_section_description_only`: renders "standing description" prose
- `test_delivery_section_body_and_description`: renders "body was read" prose
- `test_delivery_section_not_instrumented`: renders "not instrumented" prose
- `test_delivery_section_absent_when_no_block`: empty string for 1.0.0/1.1.0
- `test_delivery_section_pi_c_refusal`: refusal renders "REFUSED" line
- `test_delivery_section_exposure_refusal`: refusal renders "REFUSED" line
- `test_delivery_section_in_full_render`: delivery appears in full skill page
- `test_full_render_no_delivery_block`: 1.0.0 receipt has no delivery section

**Observation:** Before the change, the `Value delivery` heading never appeared on any
rendered page. After, it appears for 1.2.0 receipts and is absent for older versions.

### AC6: docs gain the delivery block definition

**Built:** Updated `docs/sers/README.md`:
- `sers_version` now lists `"1.2.0"` as supported
- Added `### delivery (required from sers_version 1.2.0)` section beside the cost section
- Updated `subject_identity` to note 1.2.0 requirement

Updated `docs/sers/what-sers-is.md`:
- Added delivery block to "What SERS requires today" section
- Added "The delivery block (1.2.0)" to the prose-rules enumeration
- Updated version semantics to include 1.2.0

**Test:** `test_receipt_conforms_to_sers_schema` (parametrized) continues to validate all
receipts. `test_schema_uses_qualified_evidence_admissibility_term` still passes (delivery
does not collide with the gate term). No new doc-specific test needed — the schema
conformance test gates the docs' structural claims.

**Observation:** The README's delivery section documents the same cross-field rules the
schema enforces. The what-sers-is.md prose-rules enumeration now lists the delivery block
beside the refusal shape and gate term.

## Mutation campaign

No mutation campaign was run. The delivery block is additive schema surface — the existing
mutation receipt machinery (`scripts/mutation_receipt.py`) targets the aggregation verdict
path, not the schema definition. The poison fixtures serve as the equivalent negative test:
each poison is a single-field mutation of a valid receipt, and the schema rejects it.

## Test summary

| Test file | Tests | Status |
|---|---|---|
| `tests/test_sers_conformance.py` | 25 | all pass |
| `tests/test_receipts_index.py` | 14 | all pass |
| `tests/test_delivery.py` | 7 | all pass |
| `tests/test_sitegen_delivery.py` | 8 | all pass |
| **Total** | **54** | **all pass** |
