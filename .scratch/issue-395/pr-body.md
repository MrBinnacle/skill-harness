# Issue 395: D4 prompt-leak check — store the comparison, refuse half-inputs, record the bound

## Criterion 1: the stored reason carries the comparison

**What was built.** `D4LeakResult` gained a `searched: tuple[str, ...]` field naming every source compared (prompt; each fixture file by name). `format_d4_leak_reason()` renders the store's `inadmissibility_reason` as a parseable string:

```
apparatus_void: D4 prompt leak; hit=prompt,RELEASING.md; searched=prompt,RELEASING.md
```

The leading prefix `apparatus_void: D4 prompt leak` is preserved verbatim so existing prefix matchers — including the re-disposition step on issue 381's criterion 3 — keep working. Everything after the first `;` is `key=comma,separated,values`.

`apply_manifest` calls `format_d4_leak_reason(leak)` instead of writing the bare `_D4_LEAK_REASON` constant.

**Tests.** `test_apply_manifest_d4_poison_refused` pins the prompt-hit shape: the stored reason contains `hit=prompt` and `searched=prompt`. `test_apply_manifest_d4_indirect_leak_via_fixture` pins the one-hop fixture shape: the stored reason contains `hit=RELEASING.md` and `searched=prompt,RELEASING.md`. `test_format_d4_leak_reason_keeps_the_prefix_and_names_both_lists` asserts the full rendered string and verifies a reader can split it back out. `test_d4_result_records_every_source_it_compared` and `test_d4_searched_is_prompt_only_when_no_fixtures_given` pin the `searched` field on `D4LeakResult` directly. `test_d4_empty_rule_searched_nothing` distinguishes "clean because nothing matched" from "clean because there was nothing to match".

## Criterion 2: refuse half-specified D4 entries; mark "not checked"

**Refusal half.** `_validate_d4_fields()` walks the manifest before any write and raises `ScreenManifestError` when an entry carries exactly one of `operative_rule` / `prompt_text`. `apply_manifest` calls it as the first operation.

**Marker half (the open item after #401).** Migration `1000_screen_d4_check_state.sql` adds a coded column:

```sql
ALTER TABLE screen_runs ADD COLUMN d4_check_state TEXT NOT NULL
  DEFAULT 'unknown_legacy'
  CHECK (d4_check_state IN ('unknown_legacy','not_applicable','ran_clean','ran_flagged'));
```

| value | meaning |
|---|---|
| `unknown_legacy` | pre-migration row only (SQLite DEFAULT; never written by the post-migration path) |
| `not_applicable` | entry carried neither field; the check did not run (ticket's "d4: not_checked") |
| `ran_clean` | check ran; no normalised verbatim match |
| `ran_flagged` | check ran; leak found |

Same-field placement (`inadmissibility_reason = "d4: not_checked"`) stays blocked: that column means WHY THIS IS INADMISSIBLE. The four-state vocabulary and the decision against a companion table are the design settled on issue 395 (owner comment, 2026-09-02).

`write_screen_evidence` takes `d4_check_state` as a **required** parameter with no Python default — omission is a type error, not a silent `unknown_legacy`. It also refuses an explicit `unknown_legacy` write. `apply_manifest` supplies `not_applicable` / `ran_clean` / `ran_flagged` from the entry's D4 fields and the check result. `ingest_screen_eval_log` (no prompt access) always writes `not_applicable`.

**Tests.** `test_apply_manifest_refuses_rule_without_prompt` / `..._prompt_without_rule` / `..._whole_manifest_before_writing_anything` pin the refusal. `test_apply_manifest_no_d4_fields_is_admitted_as_not_applicable` pins the marker. `test_apply_manifest_d4_clean_admitted` pins `ran_clean`. Poison and fixture-leak tests pin `ran_flagged`. `test_no_post_migration_write_carries_unknown_legacy` is the row-5 control. `test_d4_check_state_check_rejects_unlisted_value` is the row-4 control. `test_write_screen_evidence_refuses_unknown_legacy` pins the writer guard. `test_store_refuses_an_admissible_row_carrying_a_reason` keeps the same-field invariant.

## Criterion 3: the paraphrase bound is recorded

**What was built.** The docstring on `check_d4_prompt_leak` states that a clean result means "no normalised verbatim match" and names the three fixtures (`appendonly`, `bayes`, `judgegate`) whose leak the finding judged by reading. The findings document `docs/findings/d4-prompt-leak-into-null-arm.md` gained a section stating the substring bound and the three fixtures. No paraphrase detector is built.

## Criterion 4: tests for criteria 1 and 2 at the same seam

The test seam is `apply_manifest` with synthetic `ScreenManifestEntry` instances and a `fake_parse` callable. Criterion 1 and both halves of criterion 2 are pinned there; the migration CHECK and the unknown_legacy controls sit beside them on the same store.

## Gate

Targeted: `tests/test_screen_ingest.py`, `tests/test_screen_supersession.py`, `tests/test_cli_screen_profile.py` — 80 passed. `mypy --strict` clean on the four changed source modules. `ruff check` clean.
