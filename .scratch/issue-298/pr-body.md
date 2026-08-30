# PR #298: Add `subject_identity` block to SERS receipt schema (v1.1.0)

## Acceptance Criteria

### 1. Schema 1.1.0 validates the four existing receipts unchanged

**What I built:** Updated `docs/sers/sers.schema.json` to support `sers_version` `"1.0.0"` and `"1.1.0"`. The `subject_identity` block is optional for `1.0.0` receipts and required from `1.1.0` onward. Added a conditional `allOf` rule: when `sers_version == "1.1.0"`, `subject_identity` must be present.

**Test that pins it:** `test_sers_conformance.py::test_receipt_conforms_to_sers_schema` — parametrized over all five receipt files under `docs/sers/receipts/`. The four existing `1.0.0` receipts pass validation unchanged; the new `1.1.0` receipt also passes.

**What I observed:** All four existing receipts validated before and after the schema change. The schema's `allOf` conditional correctly skips the `subject_identity` requirement for `1.0.0` receipts. The `Draft202012Validator.check_schema()` self-check passes on the updated schema.

### 2. The omit-`skill_id` poison fixture fails in CI

**What I built:** Created `tests/fixtures/sers/poison_missing_skill_id.json` — a `sers_version: "1.1.0"` receipt with a `subject_identity` block that omits the required `skill_id` field.

**Test that pins it:** `test_sers_conformance.py::test_poisoned_fixture_fails_validation[poison_missing_skill_id.json]` — the existing parametrized test discovers the new fixture via the `poison_*.json` glob and asserts it raises `ValidationError`.

**What I observed:** The fixture fails validation with `'skill_id' is a required property` — the correct field-level error. The test passes, confirming the poison is detected.

### 3. One receipt carries all five fields populated by the harness

**What I built:** Created `docs/sers/receipts/harness-evidenced-keep-2026-08-15.json` with `sers_version: "1.1.0"` and a complete `subject_identity` block carrying all five fields:
- `skill_id`: SHA-256 hex (fixture value)
- `harness_version`: `"0.2.3"` (from `_resolve_harness_version()`)
- `metric_version`: `"0.3.0"` (from `ORACLE_METRIC_VERSION` in `ingest.py`)
- `implementation_hash`: SHA-256 of `ingest.py` bytes (computed from the live module)
- `arms`: `["null", "full"]` (both arms ran)

**Test that pins it:** `test_sers_conformance.py::test_receipt_conforms_to_sers_schema[harness-evidenced-keep-2026-08-15.json]` — validates the receipt against the schema, confirming all five fields pass the pattern/enum/required constraints.

**What I observed:** The receipt validates cleanly. The `implementation_hash` was computed from the actual `ingest.py` module (`7997bf55c86231f65048711e66587f0bd4e3236dee14fc665626cd45250d14c1`), matching the value the harness would produce at ingest time.

## Gate Results

```
tests/test_sers_conformance.py   19 passed
tests/test_receipts_index.py     14 passed
tests/sitegen/test_receipts.py   22 passed
────────────────────────────────────────
Total:                           55 passed
```

`mypy` on touched modules: clean. `ruff check src/ tests/ --exclude "*.json"`: clean.

## Files Changed

| File | Change |
|------|--------|
| `docs/sers/sers.schema.json` | `sers_version` enum expanded to `["1.0.0", "1.1.0"]`; `subject_identity` property added; conditional `allOf` rule added |
| `tests/fixtures/sers/poison_missing_skill_id.json` | New poison fixture: `1.1.0` receipt missing `skill_id` |
| `docs/sers/receipts/harness-evidenced-keep-2026-08-15.json` | New `1.1.0` receipt with all five `subject_identity` fields |
| `docs/receipts-index.md` | New entry for `harness-evidenced-keep-2026-08-15.json` |
