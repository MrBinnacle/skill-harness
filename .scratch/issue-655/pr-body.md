# #655: S476 amendment 2 render wording and CARRIED_FORWARD scope immutability

Two items that did not land in PR #654 now land here.

## Files changed

- `src/skill_harness/sitegen/render.py` — delivery channel text for `description_only`, CARRIED_FORWARD scope line, CUT(no_lift) and HAZARD_NOT_MET verbatim templates
- `src/skill_harness/sitegen/__init__.py` — `_check_carried_forward_immutability` post-schema validation
- `src/skill_harness/sitegen/templates/skill.html` — `$verdict_template_text` slot
- `tests/test_sitegen_delivery.py` — updated description_only wording test, added poison test
- `tests/test_sitegen_verdict_validity.py` — updated CARRIED_FORWARD scope line test, added CUT/HAZARD_NOT_MET template tests, added CARRIED_FORWARD immutability fixture-pair tests

## Acceptance criteria

### AC1: When the SERS delivery channel is `description_only`, the delivery reads "delivery: skill-listing description; body not loaded", never bare "model-pull"

**What I built:** Updated `_DELIVERY_CHANNEL_TEXT["description_only"]` in `render.py` from "The standing description carried the value; the skill body was never read." to "delivery: skill-listing description; body not loaded".

**Test:** `test_delivery_section_description_only` asserts the new wording appears. `test_description_only_receipt_never_renders_model_pull` asserts "model-pull" never appears in the delivery section for a `description_only` receipt.

**Observation:** Before this change, the test asserted "standing description" in HTML. After, it asserts "skill-listing description; body not loaded". The poison test confirms "model-pull" is absent from the delivery section when the channel is `description_only`.

### AC2: A carried-forward verdict reads "demonstrated on [tested model]; carried forward to [current model] under the sentinel rule; not re-validated on [current model]"; `verdict_scope.model_id` is never rewritten

**What I built:** Modified `_scope_line` to detect `currentness.state == "CARRIED_FORWARD"` and render the sentinel-rule wording instead of the standard scope line. The tested model comes from `verdict_scope.model_id`; the current model comes from `subject_identity.subject_model`.

**Test:** `test_keep_card_renders_scope_line_and_carried_forward_disclaimer` asserts the new wording appears and the standard "Shown here: effect on" line does not.

**Observation:** Before this change, a CARRIED_FORWARD receipt rendered the standard scope line. After, it renders "demonstrated on [tested model]; carried forward to [current model] under the sentinel rule; not re-validated on [current model]."

### AC3: Verbatim templates for CUT(no_lift) and HAZARD_NOT_MET

**What I built:** Added `CUT_NO_LIFT_TEMPLATE` and `HAZARD_NOT_MET_TEMPLATE` constants and `_verdict_template_text` function that renders them when the receipt carries the matching sub-reason. Integrated into the `skill.html` template via `$verdict_template_text`.

**Test:** `test_cut_no_lift_renders_verbatim_template` asserts the CUT(no_lift) template renders with scope fields. `test_hazard_not_met_renders_verbatim_template` asserts the HAZARD_NOT_MET template renders with scope fields.

**Observation:** Before this change, CUT(no_lift) and HAZARD_NOT_MET had no card-facing text. After, they render the verbatim template with the scope fields filled in.

### AC4: A CARRIED_FORWARD receipt whose `tested_at` differs from its original is refused

**What I built:** Added `_check_carried_forward_immutability` to `sitegen/__init__.py`. When a CARRIED_FORWARD receipt is loaded, the function finds the corresponding receipt in `superseded/` by `skill_name` and compares every `verdict_scope` field. Any change raises `SiteBuildError`.

**Test:** `test_carried_forward_with_matching_scope_validates` creates a fixture pair (original in `superseded/`, CARRIED_FORWARD with identical scope in `receipts/`) and asserts validation passes. `test_carried_forward_with_changed_scope_refused` creates a fixture pair where `tested_at` differs and asserts `SiteBuildError` is raised.

**Observation:** Before this change, `validate_receipts` only checked schema conformance. After, it also checks that CARRIED_FORWARD receipts do not alter the `verdict_scope` fields from their originals.

## Files changed (summary)

| File | Change |
|------|--------|
| `src/skill_harness/sitegen/render.py` | Updated `_DELIVERY_CHANNEL_TEXT["description_only"]`, added CARRIED_FORWARD scope line in `_scope_line`, added `CUT_NO_LIFT_TEMPLATE`, `HAZARD_NOT_MET_TEMPLATE`, `_verdict_template_text` |
| `src/skill_harness/sitegen/__init__.py` | Added `_check_carried_forward_immutability` called from `validate_receipts` |
| `src/skill_harness/sitegen/templates/skill.html` | Added `$verdict_template_text` slot |
| `tests/test_sitegen_delivery.py` | Updated description_only test, added poison test |
| `tests/test_sitegen_verdict_validity.py` | Updated CARRIED_FORWARD test, added 4 new tests |

## Mutation campaign

No mutation receipt was requested by this ticket. The ticket is render wording and validation plumbing — no measurement logic changed.
