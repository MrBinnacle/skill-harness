# Normalise `ExtractedClause.axis` at the extractor boundary (#504)

## What changed

Added a `@model_validator(mode="before")` on `ExtractedClause` that strips leading
and trailing whitespace from the `axis` field before Pydantic validation. The
normalisation happens at the extractor boundary so no downstream consumer ever sees
a padded axis value.

## Files touched

- `src/skill_harness/extractor/models.py:198-209` — new `_normalise_axis` validator
- `tests/extractor/test_models.py:104-148` — four new tests pinning the behaviour

---

## Criterion 1: padded axis stores identically to its unpadded twin

**What was built:** A `@model_validator(mode="before")` on `ExtractedClause` that calls
`data["axis"].strip()` before validation runs.

**Test that pins it:** `test_axis_whitespace_stripped_at_boundary` — parametrised over
five whitespace variants (`"  list_usage  "`, `"\tlist_usage\n"`, `" list_usage "`,
`"list_usage "`, `"  list_usage"`). Each constructs an `ExtractedClause` with a padded
axis and asserts the stored value equals `"list_usage"`.

**Observation:** Before the change, `ExtractedClause.model_validate(_valid_clause(axis="  list_usage  "))` stored `"  list_usage  "` — the padded string passed straight through Pydantic's `Field(min_length=1)` with no stripping. After the change, the validator strips the whitespace before validation runs, and the stored value is `"list_usage"`.

**Mutation campaign:** Applied a mutant that removes the `data["axis"] = data["axis"].strip()` line (deleting the normalisation). All five parametrised cases fail: the stored value retains whitespace, and the `assert clause.axis == "list_usage"` assertion fails for every padded variant. The mutant is killed by every case.

---

## Criterion 2: no-op on an already-clean corpus

**What was built:** The validator only strips; it does not alter the value when it
already lacks leading or trailing whitespace. The `if isinstance(data.get("axis"), str)` guard ensures non-string inputs are not touched.

**Test that pins it:** `test_axis_clean_value_unchanged` — constructs two
`ExtractedClause` instances with the clean axis `"list_usage"` and asserts both store
the same value. This pins that the normalisation is a no-op on present data: no
existing clean axis is altered.

**Observation:** The 217 extractor tests and 34 axis registry tests all pass with no
changes to their expected values. No existing test broke. The change is invisible on
clean data.

---

## Criterion 3: no consumer performs its own axis normalisation

**What was found:** A grep for `strip.*axis` and `axis.*strip` across `src/` returned
zero production-code matches. The only reference is in the `axis_registry.py` module
docstring, which documents the trade-off and calls out the extractor-boundary fix as
a deliberate follow-up. No compensation to remove.

**No code changes required.** The acceptance criterion is satisfied by the current
codebase: no consumer strips axis. The normalisation at the boundary makes this safe
going forward.

---

## What did NOT change

- `classify_axis()` stays strict: it does not strip. The tripwire test
  `test_no_normalisation_at_all_not_even_a_whitespace_strip` in
  `tests/oracles/tier1/test_axis_registry.py` continues to pass because it calls
  `classify_axis` directly, not through the `ExtractedClause` model. The classifier
  remains fail-closed on near-misses.
- No consumer was altered. The normalisation at the boundary means downstream code
  never sees a padded axis.
- No data migration. The measured corpus has zero padded axes, so no rows need repair.

## Gate results

```
ruff check src tests          — All checks passed
ruff format --check src tests — 329 files already formatted
mypy --strict src/ tests/     — Success: no issues found
pytest tests/extractor/       — 217 passed, 4 skipped
pytest tests/oracles/tier1/test_axis_registry.py — 34 passed
```
