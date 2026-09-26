# PR: Claim ladder above KEEP — family record, receipt fields, render (#647)

Set the ledger's claim ladder above KEEP with three rungs: KEEP, REPLICATED, ROBUST.
Adopted as program policy per the Fable 5 adjudication session (S477/S478).

## Files changed

- `src/skill_harness/task_frontier/family_record.py` — new module: family record
  schema with five mechanism fields and two registration checks
- `src/skill_harness/task_frontier/__init__.py` — export family record public names
- `src/skill_harness/aggregation/verdict.py` — new `ClaimLevel` enum (KEEP, REPLICATED, ROBUST)
- `docs/sers/sers.schema.json` — five new optional receipt properties, version gate unchanged
- `src/skill_harness/sitegen/render.py` — `render_claim_level_sentence()` with three sentences
- `tests/task_frontier/test_family_record.py` — 18 tests for family record schema and guards
- `tests/test_claim_level_receipt_fields.py` — 13 tests for receipt field schema conformance
- `tests/test_claim_level_render.py` — 9 tests for claim level sentence rendering
- `tests/test_sers_conformance.py` — new `test_schema_claim_level_enum_matches_code` drift guard

## Acceptance criteria

### AC1: Family record schema with five mechanism fields

A frozen dataclass `FamilyRecord` with fields: `mechanism_id`, `hazard_condition`,
`intervention_action`, `outcome`, `allowed_substitutions`, plus `fixture_path` and
`registered_at`. Loaded via `load_family_record()` which validates all seven fields
are non-empty strings and refuses unrecognised keys.

**Test:** `test_family_record.py::TestFamilyRecordRoundTrip` — three tests verify
the minimal record loads, is frozen, and all five mechanism fields are present.

**Red-phase:** Before the module existed, importing `load_family_record` raised
`ImportError`. After the module was created, all three tests pass.

### AC2: Registration checks (predate-first-epoch, fixture-path uniqueness)

`check_predate_first_epoch(family, first_epoch_at)` refuses a family whose
`registered_at` is on or after `first_epoch_at` (ISO-8601 lexicographic comparison).
`check_fixture_path_uniqueness(new_family, existing)` refuses a family whose
`fixture_path` matches an existing registered family.

**Test:** `test_family_record.py::TestPredateFirstEpoch` — three tests verify
pass (before), refuse (on), refuse (after). `TestFixturePathUniqueness` — three
tests verify pass (different path), refuse (same path), pass (empty registry).

**Red-phase:** Before the functions existed, importing them raised `ImportError`.
After creation, all six tests pass.

### AC3: Receipt fields (designer, designer_independent, family_replication, model_replication, claim_level)

Five new optional properties added to `docs/sers/sers.schema.json`:
- `designer` (string) — seat or person who designed the family
- `designer_independent` (boolean) — whether designer is independent from card author
- `family_replication` (integer, minimum 1) — number of materially distinct families
- `model_replication` (integer, minimum 1) — number of distinct model families
- `claim_level` (nullable enum: KEEP, REPLICATED, ROBUST) — the claim ladder rung

All are optional at every version. The `ClaimLevel` enum in `verdict.py` matches
the schema enum exactly (drift-guarded by `test_schema_claim_level_enum_matches_code`).

**Test:** `test_claim_level_receipt_fields.py` — 13 tests verify schema property
existence, enum values, nullable type, receipt validation with each claim level,
receipt without claim_level still validates, invalid value rejected, and combined
fields validate.

**Red-phase:** Before the schema change, `test_claim_level_property_exists` failed
with "claim_level" not in properties. After adding the properties, all 13 tests pass.

### AC4: Render three claim level sentences

`render_claim_level_sentence()` in `render.py` produces:
- **KEEP:** "This result is a single registration; it is a scoped claim only."
- **REPLICATED:** "Replicated across N families under program policy." with
  "(same designer)" suffix when `designer_independent=False`
- **ROBUST:** "Robust across N families under program policy; at least one family
  was designed by an independent seat."
- **null:** returns empty string

**Test:** `test_claim_level_render.py` — 9 tests verify each sentence's content,
the same-designer qualifier, the program policy wording, and null returns empty.

**Red-phase:** Before `render_claim_level_sentence` existed, importing it raised
`ImportError`. After adding it, all 9 tests pass.

### AC5: Existing receipts validate; conformance suite green

All 5 existing receipts under `docs/sers/receipts/` validate against the updated
schema (73 conformance tests pass, up from 72 with the new drift guard). The 12
poison fixtures still fail validation.

### AC6: Gate green

- `ruff check src tests scripts` — all checks passed
- `ruff format --check src tests scripts` — 415 files already formatted
- `mypy --strict src/ tests/ scripts/` — no issues found in 377 source files

## Mutation campaign

No mutation receipt was requested by this ticket. The ticket adds schema plumbing
and a rendering function; no measurement logic changed.

## Commit history

1. `c7655af` — #647: family record schema with five mechanism fields and registration checks
2. `394fe24` — #647: receipt fields for claim level ladder
3. `36c2074` — #647: render claim level sentences with same-designer qualifier
