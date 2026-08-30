# PR #298: Add `subject_identity` block to SERS receipt schema (v1.1.0)

## Acceptance Criteria

### 1. Schema 1.1.0 validates the four existing receipts unchanged

**What:** `docs/sers/sers.schema.json` accepts `sers_version` `"1.0.0"` and `"1.1.0"`.
`subject_identity` is optional on `1.0.0` and required on `1.1.0` via an `allOf`
conditional. The four published `1.0.0` receipts under `docs/sers/receipts/` are
byte-unchanged.

**Test:** `test_sers_conformance.py::test_receipt_conforms_to_sers_schema` over every
file in `docs/sers/receipts/`.

### 2. The omit-`skill_id` poison fixture fails in CI

**What:** `tests/fixtures/sers/poison_missing_skill_id.json` is a `1.1.0` receipt whose
`subject_identity` omits `skill_id`.

**Test:** `test_poisoned_fixture_fails_validation[poison_missing_skill_id.json]` and
`test_poison_missing_skill_id_is_red` (asserts the error names `skill_id`).

### 3. One receipt minted from a real run carries all five fields populated by the harness

**What:** `skill_harness.sers.build_subject_identity` fills all five fields from harness
sources (`skill_id` = SHA-256 of SKILL.md bytes; `harness_version` via
`_resolve_harness_version`; `metric_version` = `ORACLE_METRIC_VERSION`;
`implementation_hash` via `_oracle_implementation_hash`; `arms` closed set).

The mint is `tests/fixtures/sers/minted_synthetic_control_v1_1_0.json`: the documented
2026-07-27 synthetic-control KEEP (Full 8/8 vs Null 0/8, p_win 0.99), with
`subject_identity` equal to a live `build_subject_identity` call. Not published under
`docs/sers/receipts/` because the site generator refuses two receipts for one
`skill_name`; the 1.0.0 card stays the published instance.

**Test:** `test_build_subject_identity_uses_live_harness_sources` and
`test_v11_receipt_subject_identity_matches_harness_mint` (re-mints and asserts equality;
invented KEEP numbers are refused by the second test's 8/8 vs 0/8 assertions).

**Honesty note:** original 2026-07-27 SKILL.md bytes are not in-tree. `skill_id` is the
SHA-256 of the reconstructed control fixture at
`tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`. Receipt notes state
that.
