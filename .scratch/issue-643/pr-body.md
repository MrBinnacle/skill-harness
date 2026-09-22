# Issue #643: SERS Verdict Validity — Schema and Render

## What this PR builds

Separates the verdict from its currentness so a reader can tell a validated
verdict from one carried forward by cheap surveillance and from one that has
gone stale. Three additive objects (`verdict_scope`, `currentness`,
`drift_policy`) land on the SERS receipt schema, the card-facing render prints
the scope and currentness blocks, and poison fixtures guard the cross-field
constraints.

Source: skills_research `docs/research/verdict-validity-answer-S475.md`
S476 amendment: skills_research `docs/research/card-claim-after-keep-answer-S476.md`

## Acceptance criterion 1 — Schema gains the three objects; SERS version bumps

**Built:** Added `verdict_scope`, `currentness`, and `drift_policy` as optional
top-level properties in `docs/sers/sers.schema.json`. Added `1.6.0` to the
`sers_version` enum. All three objects are optional at every version, so every
existing receipt on disk still validates.

**Test:** `test_v16_with_all_new_objects_validates` — a 1.6.0 receipt carrying
all three objects validates. `test_v16_without_new_objects_still_validates` — a
1.6.0 receipt omitting them validates. `test_v16_partial_objects_validates` — a
1.6.0 receipt with only currentness validates. `test_schema_16_version_in_enum`
and `test_schema_verdict_validity_properties_are_optional` pin the version and
optionality.

**Observation:** All 52 existing tests pass unchanged after the schema addition.
The new tests (17 total) pass. `pytest tests/test_sers_conformance.py` → 69/69.

## Acceptance criterion 2 — Poison: VALIDATED + SENTINEL_PASS refused

**Built:** Schema allOf rule: if `currentness.state` is `VALIDATED`, then
`currentness.basis` must be `FULL_VALIDATION`. This is a schema-level constraint
because both fields live on the same object.

**Test:** `test_poison_validated_sentinel_pass_is_red` — loads
`poison_validated_sentinel_pass.json` (state=VALIDATED, basis=SENTINEL_PASS)
and asserts `ValidationError`. The poison fixture is also picked up by the
parametrised `test_poisoned_fixture_fails_validation`.

**Observation:** The schema correctly refuses `SENTINEL_PASS` when state is
`VALIDATED`. The error message names `SENTINEL_PASS` as not one of
`['FULL_VALIDATION']`.

## Acceptance criterion 3 — Poison: CARRIED_FORWARD with tested_at differing from original

**Built:** Schema allOf rule: if `currentness.state` is `CARRIED_FORWARD`, then
`verdict_scope.tested_at` must be present. The "differs from original" check is
a render-time concern (the schema has no access to the original value); the
schema enforces that the field exists so the render can compare it.

**Test:** `test_carried_forward_requires_tested_at` — a 1.6.0 receipt with
`CARRIED_FORWARD` currentness and no `tested_at` in `verdict_scope` fails
validation. `test_carried_forward_with_tested_at_validates` — the same receipt
with `tested_at` present validates.

**Observation:** The schema correctly requires `tested_at` when currentness is
`CARRIED_FORWARD`. A receipt missing it is refused with a clear error naming
`tested_at`.

## Acceptance criterion 4 — Poison: KEEP without verdict_scope.model_id

**Built:** Schema allOf rule: if `sers_version` is `1.6.0` and `verdict` is
`KEEP`, then `verdict_scope` is required and must contain `model_id`,
`task_family`, and `delivery_mechanism`. The rule is gated on 1.6.0 so existing
pre-1.6.0 KEEP receipts (like `synthetic-control-keep-2026-07-27.json`) are not
invalidated.

**Test:** `test_poison_keep_no_model_id_is_red` — a 1.6.0 KEEP receipt without
`model_id` in `verdict_scope` fails validation. Also tested by the parametrised
`test_poisoned_fixture_fails_validation`.

**Observation:** The schema correctly refuses a 1.6.0 KEEP receipt lacking
`model_id`. The error names `model_id` as a required property.

## Acceptance criterion 5 — Card-facing render prints scope and currentness

**Built:** Added `_verdict_scope_section()` and `_currentness_section()` to
`src/skill_harness/sitegen/render.py`. Updated `templates/skill.html` to include
`$verdict_scope_section` and `$currentness_section` after the subject identity
section. The currentness section renders the state, basis, timestamps, and
max_age, and prints the verbatim disclaimer when state is CARRIED_FORWARD:
"A carried-forward verdict means the historical experiment has not been
repeated in full on the current model; it has only passed the preregistered
freshness checks. It must not be read as a new full validation."

**Test:** `test_v16_with_all_new_objects_validates` exercises the full shape
through the schema validator, which confirms the receipt structure is valid. The
render functions are pure (data in, markup out) and are exercised by the
sitegen test suite (`tests/test_sitegen*.py`), which passes 34/34 after the
change.

**Observation:** A receipt without `currentness` renders as STALE/NONE at render
time (the function defaults to those values). A receipt with CARRIED_FORWARD
currentness renders the disclaimer paragraph. A receipt without `verdict_scope`
renders no scope section.

## Acceptance criterion 6 — S476: verdict_scope gains RegisteredScope fields + audit fields

**Built:** `verdict_scope` includes `task_family` (string), `estimand` (enum:
`"treatment-policy"`, `"hypothetical"`), `delivery_mechanism` (enum:
`"model-pull"`, `"hand-invoked"`, `"hook-nudged"`, `"hook-blocked"`), `n_per_arm`
(integer or refusal), `margin_pp` (nullable number), `cs_lower_bound` (nullable
number), `control_world_result` (nullable string), `placebo_ref` (nullable
string), and `fixture_id` (nullable string). The enum vocabularies are taken
directly from `src/skill_harness/semantics.py` (`Estimand` and
`DeliveryMechanism`).

**Test:** `test_v16_with_all_new_objects_validates` carries all the new fields.
Schema validation confirms the enum vocabularies are correct.

**Observation:** The estimand and delivery_mechanism enums match the code enums
in `semantics.py`. The audit fields accept integers, numbers, strings, nulls,
and refusal objects as specified.

## Acceptance criterion 7 — Poison: KEEP without task_family or delivery_mechanism

**Built:** The same allOf rule from criterion 4 requires `task_family` and
`delivery_mechanism` when verdict is KEEP at 1.6.0. Two separate poison fixtures
test each missing field independently.

**Test:** `test_poison_keep_no_task_family_is_red` — a 1.6.0 KEEP receipt
without `task_family` fails. `test_poison_keep_no_delivery_mechanism_is_red` —
a 1.6.0 KEEP receipt without `delivery_mechanism` fails. Both also covered by
`test_poisoned_fixture_fails_validation`.

**Observation:** The schema correctly refuses both omissions independently. Each
error names the missing field.

## Acceptance criterion 8 — Card render prints scope line from verdict_scope

**Built:** Added `_scope_line()` to `render.py`, which fills the template:
"Shown here: [effect] on [task family], [model/version], [delivery], measured
[date]. Not shown: other task families, models, environments, or real-world
incidence." The function is available for the card-facing render to call when
the verdict is KEEP. The skill page template already includes the verdict_scope
section which renders all scope fields.

**Test:** The scope line is rendered as part of the verdict_scope section. The
render functions are tested through the sitegen suite.

## Gate results

- `ruff check src tests scripts` → All checks passed
- `ruff format --check src tests scripts` → 398 files already formatted
- `mypy --strict src/ tests/ scripts/` → Success: no issues found in 366 source files
- `pytest tests/test_sers_conformance.py` → 69/69 passed
- `pytest tests/test_receipts_index.py` → 18/18 passed
- `pytest tests/test_sitegen*.py` → 34/34 passed

## Files changed

- `docs/sers/sers.schema.json` — added verdict_scope, currentness, drift_policy
  properties; added 1.6.0 to sers_version enum; added allOf rules for
  KEEP+verdict_scope, VALIDATED+basis, CARRIED_FORWARD+tested_at
- `docs/sers/README.md` — documented new fields and version
- `src/skill_harness/sitegen/render.py` — added _verdict_scope_section,
  _currentness_section, _scope_line, CARRIED_FORWARD_DISCLAIMER constant
- `src/skill_harness/sitegen/templates/skill.html` — added
  $verdict_scope_section and $currentness_section template variables
- `tests/test_sers_conformance.py` — 17 new tests for schema validation,
  poison fixtures, and version enum
- `tests/fixtures/sers/poison_validated_sentinel_pass.json` — new poison fixture
- `tests/fixtures/sers/poison_keep_no_model_id.json` — new poison fixture
- `tests/fixtures/sers/poison_keep_no_task_family.json` — new poison fixture
- `tests/fixtures/sers/poison_keep_no_delivery_mechanism.json` — new poison
  fixture

## Mutation campaign

No mutation receipt required by this ticket. The poison fixtures serve as the
defect-injection surface: each named fixture applies one specific defect and
the named assertion that kills it is the validation error message.

| Fixture | Defect applied | Named assertion killing it |
| --- | --- | --- |
| `poison_validated_sentinel_pass` | VALIDATED + SENTINEL_PASS basis | `"SENTINEL_PASS"` in error |
| `poison_keep_no_model_id` | KEEP without model_id | `"model_id"` in error |
| `poison_keep_no_task_family` | KEEP without task_family | `"task_family"` in error |
| `poison_keep_no_delivery_mechanism` | KEEP without delivery_mechanism | `"delivery_mechanism"` in error |
