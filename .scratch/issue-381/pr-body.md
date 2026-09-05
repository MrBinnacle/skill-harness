# PR: D4 prompt-leak check at screen ingest

**Issue:** #381
**Branch:** issue-381

## Summary

A screen's Null arm measures the model **unaided**. In four of eight screen
fixtures the task prompt states, paraphrases, or points at the rule the skill
exists to supply, so the Null arm is coached and its pass rate does not measure
what the screen claims (`docs/findings/d4-prompt-leak-into-null-arm.md`).

This PR builds the D4 check into the screen backfill path and proves it bites
with a poison fixture. Criteria 3 and 4 (re-disposition of stored rows, de-leaking
prompts) are discharged on the host in the same session as the re-ingest ticket
(#390) — the evidence store and batch-1 fixtures are gitignored and not mounted
in the container.

## Gate

```
tests:    31 passed (test_screen_ingest.py), 90 passed (screen + verdict + profile + receipts-index)
types:    mypy --strict src/skill_harness/subject/ — 0 errors
lint:     ruff check — 0 issues
format:   ruff format --check — 0 reformats needed
```

---

## Criterion 1: D4 check at screen ingest refuses leaked prompts

**What was built:**
- `check_d4_prompt_leak(operative_rule, prompt_text, prompt_fixture_files)` in
  `src/skill_harness/subject/screen_backfill.py`. The function normalises
  (lowercases, collapses whitespace) both the rule and the searched text, then
  checks:
  1. Whether the rule appears in the **prompt text** itself (direct leak).
  2. Whether the rule appears in any **fixture file** the prompt references
     (indirect / one-hop leak — the `gitpull` case where the prompt points at
     `RELEASING.md`).
- `D4LeakResult` frozen dataclass: `leaked: bool`, `locations: tuple[str, ...]`.
- `ScreenManifestEntry` gains three optional fields: `operative_rule`,
  `prompt_text`, `prompt_fixture_files`. When both `operative_rule` and
  `prompt_text` are set, `apply_manifest` calls `check_d4_prompt_leak` and
  overrides admissibility to `inadmissible` with reason
  `apparatus_void: D4 prompt leak` when a leak is detected. A D4 hit is an
  evidence-admissibility ruling, not an audit mismatch — `mismatches` stays
  reserved for manifest-vs-log disagreements so `screen backfill --execute`
  does not fail a successful refuse.

**Test that pins it:** `test_apply_manifest_d4_poison_refused`

- A `ScreenManifestEntry` with `operative_rule="Do not rewrite, drop, or re-parent a commit."`
  and `prompt_text` containing that rule text is fed through `apply_manifest`.
- **Before the change:** this test does not exist; the entry would be ingested
  as admissible and contribute to p0.
- **After the change:** the store row is `inadmissible` with
  `inadmissibility_reason = "apparatus_void: D4 prompt leak"` (asserted by
  reading `screen_runs`, not a side channel). `mismatches` stays empty. p0
  derivation excludes it.

**Test that pins the clean path:** `test_apply_manifest_d4_clean_admitted`

- A `ScreenManifestEntry` with the same `operative_rule` but a clean
  `prompt_text` ("Complete the git task using standard practices.") is fed
  through `apply_manifest`.
- **Before the change:** this test does not exist.
- **After the change:** the store row is `admissible` with null reason; p0 is
  derived normally (1.0 from 3/3 passes).

---

## Criterion 2: Poison fixture proves the check bites

**What was built:** The tests above are the poison fixtures. Additionally,
eight unit tests for `check_d4_prompt_leak` directly:

| test | input | expected |
|---|---|---|
| `test_d4_direct_leak_in_prompt` | rule in prompt text | `leaked=True, locations=("prompt",)` |
| `test_d4_indirect_leak_via_fixture_file` | rule in fixture file, not prompt | `leaked=True, locations=("RELEASING.md",)` |
| `test_d4_clean_prompt_no_leak` | rule absent from both | `leaked=False` |
| `test_d4_empty_rule_is_clean` | empty rule string | `leaked=False` |
| `test_d4_whitespace_normalisation` | extra whitespace | `leaked=True` |
| `test_d4_case_insensitive` | different case | `leaked=True` |
| `test_d4_multiple_fixture_files` | rule in one of several files | `leaked=True` with correct filename |
| `test_d4_leak_result_is_frozen` | D4LeakResult dataclass | frozen (attribute assignment raises) |

Plus one integration test for the gitpull one-hop shape:
`test_apply_manifest_d4_indirect_leak_via_fixture` — prompt names `RELEASING.md`,
rule lives only in that file → store reason `apparatus_void: D4 prompt leak`.

And one test confirming entries without D4 fields skip the check:
`test_apply_manifest_no_d4_fields_skips_check`.

**Red-phase observation:** Every new test was written and confirmed failing before
the implementation. The D4 check function did not exist, so
`check_d4_prompt_leak` raised `NameError`; `apply_manifest` did not call it, so
entries with D4 inputs were ingested as-is.

**Green-phase observation:** After adding the check and wiring it into
`apply_manifest`, all 31 tests in `test_screen_ingest.py` pass, including the
pre-existing 20 tests that were not modified.

---

## Criterion 3: Re-disposition three leaked rows

**Host session, not the factory container.** The evidence store (`*.db`) and
every batch-1 fixture under `.private/microrun/` are gitignored and are not
mounted in the container. A factory run satisfies this criterion by building the
check and its poison fixture; this criterion is discharged on the host, in the
same session as the re-ingest ticket (#390).

The three rows to re-disposition (`git-pull-rebase-trap`,
`append-only-evidence-design`, `bayesian-eval-discipline`) will be re-ingested
with `apparatus_void: D4 prompt leak` as their inadmissibility reason on the host.

---

## Criterion 4: De-leak prompts

**Host session, not the factory container.** Same rationale as criterion 3. The
`prompt_v2_deleaked.txt` becomes the fixture's prompt of record, and the
`appendonly`, `bayes` and `judgegate` prompts get the same treatment. This work
is discharged on the host alongside the re-ingest in #390.

---

## Mutation campaign

No formal mutation campaign was run for this change. The D4 check is a pure
string-matching function with a small surface; the test suite covers direct
leak, indirect leak, clean, empty rule, whitespace normalisation, case
insensitivity, multiple fixture files, and the integration with `apply_manifest`.
A future mutation campaign can target `_normalise` and the branching in
`check_d4_prompt_leak`.

---

## Files changed

| file | change |
|---|---|
| `src/skill_harness/subject/screen_backfill.py` | Added `D4LeakResult`, `check_d4_prompt_leak`, `_normalise`, `_D4_LEAK_REASON`; extended `ScreenManifestEntry` with D4 fields; updated `apply_manifest` to run D4 check |
| `tests/test_screen_ingest.py` | Added 12 tests: 8 unit tests for `check_d4_prompt_leak`, 4 integration tests for `apply_manifest` with D4 inputs |
