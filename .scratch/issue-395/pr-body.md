# Issue 395: D4 prompt-leak check — store the comparison, refuse half-inputs, record the bound

## Criterion 1: the stored reason carries the comparison

**What was built.** `D4LeakResult` gained a `searched: tuple[str, ...]` field naming every source compared (prompt; each fixture file by name). `format_d4_leak_reason()` renders the store's `inadmissibility_reason` as a parseable string:

```
apparatus_void: D4 prompt leak; hit=prompt,RELEASING.md; searched=prompt,RELEASING.md
```

The leading prefix `apparatus_void: D4 prompt leak` is preserved verbatim so existing prefix matchers — including the re-disposition step on issue 381's criterion 3 — keep working. Everything after the first `;` is `key=comma,separated,values`.

`apply_manifest` now calls `format_d4_leak_reason(leak)` instead of writing the bare `_D4_LEAK_REASON` constant.

**Tests.** `test_apply_manifest_d4_poison_refused` pins the prompt-hit shape: the stored reason contains `hit=prompt` and `searched=prompt`. `test_apply_manifest_d4_indirect_leak_via_fixture` pins the one-hop fixture shape: the stored reason contains `hit=RELEASING.md` and `searched=prompt,RELEASING.md`. `test_format_d4_leak_reason_keeps_the_prefix_and_names_both_lists` asserts the full rendered string and verifies a reader can split it back out. `test_d4_result_records_every_source_it_compared` and `test_d4_searched_is_prompt_only_when_no_fixtures_given` pin the `searched` field on `D4LeakResult` directly. `test_d4_empty_rule_searched_nothing` distinguishes "clean because nothing matched" from "clean because there was nothing to match".

**Before and after.** Before the change, `test_apply_manifest_d4_poison_refused` asserted `reason == "apparatus_void: D4 prompt leak"` — a fixed string with no comparison metadata. After the change, the same test asserts `reason.startswith("apparatus_void: D4 prompt leak")` plus `hit=prompt` and `searched=prompt`. The old assertion would have failed against the new reason format (exact-match failure); the new assertion would have failed against the old reason (missing `hit=` / `searched=`).

## Criterion 2: refuse half-specified D4 entries

**What was built.** `_validate_d4_fields()` walks the manifest before any write and raises `ScreenManifestError` when an entry carries exactly one of `operative_rule` / `prompt_text`. `apply_manifest` calls it as the first operation. An entry with neither field is admitted and stores NULL in `inadmissibility_reason`.

The `d4: not_checked` marker the ticket wanted is NOT BUILT. Three placements were considered (see the comment above `_D4_LEAK_REASON` in `screen_backfill.py`): same-field is blocked by the `write_screen_evidence` guard that refuses an admissible row carrying an `inadmissibility_reason`; adjacent-column is blocked by the absence of a spare column in migration 0501; `screen_trials.scorer_explanation` is per-trial, not per-run. The refusal half is the critical one: a half-specified entry can no longer be admitted with the check silently skipped.

**Tests.** `test_apply_manifest_refuses_rule_without_prompt` asserts `ScreenManifestError` matching `prompt_text`. `test_apply_manifest_refuses_prompt_without_rule` asserts the mirror case matching `operative_rule`. `test_apply_manifest_refuses_whole_manifest_before_writing_anything` places the bad entry second and asserts that zero rows were written (up-front validation, not per-entry). `test_apply_manifest_no_d4_fields_is_admitted_with_a_null_reason` pins the admission path with NULL reason. `test_store_refuses_an_admissible_row_carrying_a_reason` pins the invariant that blocks the `d4: not_checked` marker placement — it attempts to write an admissible row with `inadmissibility_reason="d4: not_checked"` and asserts the store refuses it.

**Before and after.** Before the change, an entry with `operative_rule="Do not rewrite a commit."` and no `prompt_text` was silently admitted — the `if entry.operative_rule is not None and entry.prompt_text is not None:` guard skipped the check, and the row was written as admissible with NULL reason. The old `test_apply_manifest_no_d4_fields_skips_check` (now renamed) would have passed. After the change, the same entry hits `_validate_d4_fields` and raises `ScreenManifestError` before any write. The old test that described skipping would now fail (the entry is refused, not skipped). The new tests assert the refusal and the zero-rows-written invariant.

## Criterion 3: the paraphrase bound is recorded

**What was built.** The docstring on `check_d4_prompt_leak` states that a clean result means "no normalised verbatim match" and names the three fixtures (`appendonly`, `bayes`, `judgegate`) whose leak the finding judged by reading. The findings document `docs/findings/d4-prompt-leak-into-null-arm.md` gained a new section, "How the audit above was made, and what the shipped check does instead", stating the substring bound and the three fixtures. No paraphrase detector is built.

**Tests.** The docstring and document are the tests — the acceptance criterion is about a reader meeting the check, not about runtime behaviour. No runtime test is appropriate for a documented bound.

**What was observed.** The existing test `test_d4_clean_prompt_no_leak` returns `leaked=False` for a prompt that does not contain the rule verbatim. A paraphrased version of the rule would also return `False`, which is the correct answer under the substring check but weaker than the finding's audit standard. The docstring and findings doc now say so explicitly.

## Criterion 4: tests for criteria 1 and 2 at the same seam

**What was built.** The test seam is `apply_manifest` with synthetic `ScreenManifestEntry` instances and a `fake_parse` callable, the same pattern as the parent's tests. Twelve new or updated tests cover the two criteria:

| Test | Criterion | Pins |
|---|---|---|
| `test_apply_manifest_d4_poison_refused` | 1 | Store reason contains `hit=prompt; searched=prompt` |
| `test_apply_manifest_d4_indirect_leak_via_fixture` | 1 | Store reason contains `hit=RELEASING.md; searched=prompt,RELEASING.md` |
| `test_format_d4_leak_reason_keeps_the_prefix_and_names_both_lists` | 1 | Full rendered string is prefix-compatible and parseable |
| `test_d4_result_records_every_source_it_compared` | 1 | `searched` tuple lists prompt and each fixture file |
| `test_d4_searched_is_prompt_only_when_no_fixtures_given` | 1 | `searched` is `("prompt",)` when no fixtures given |
| `test_d4_empty_rule_searched_nothing` | 1 | Empty rule produces empty `searched` |
| `test_apply_manifest_refuses_rule_without_prompt` | 2 | `ScreenManifestError` raised, message names `prompt_text` |
| `test_apply_manifest_refuses_prompt_without_rule` | 2 | `ScreenManifestError` raised, message names `operative_rule` |
| `test_apply_manifest_refuses_whole_manifest_before_writing_anything` | 2 | Zero rows written when a late entry is half-specified |
| `test_apply_manifest_no_d4_fields_is_admitted_with_a_null_reason` | 2 | Entry with neither field admitted, store reason is NULL |
| `test_store_refuses_an_admissible_row_carrying_a_reason` | 2 | Invariant blocking `d4: not_checked` marker placement |
| `test_apply_manifest_keeps_a_curated_inadmissibility_reason` | 2 | Pre-existing inadmissibility reason not overwritten |

## Mutation campaign

No mutation campaign was run. The check is a pure string-comparison function with no branching logic beyond the substring test; mutations would target the normalisation or the reason format, both already pinned by assertion-heavy tests. The acceptance criteria do not require a mutation receipt.

## Gate

All 47 tests in `tests/test_screen_ingest.py` pass. `mypy` reports no type errors. `ruff check` reports no lint violations.
