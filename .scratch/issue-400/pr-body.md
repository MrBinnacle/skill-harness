# PR: Normalise skill frontmatter at the harness boundary (#400)

## Problem

The harness validates its subjects against the agentskills.io schema, but its
subjects are Claude Code skills. The two specifications differ: `disable-model-invocation`
and `argument-hint` are valid Claude Code frontmatter keys but not in the agentskills.io
schema. A card carrying any such key raises `SkillParsingError` at task construction.

Measured 2026-09-02:

| Corpus | Loadable | Refused |
|---|---|---|
| `~/.claude/skills` | 34 of 86 | 52 |
| `MrBinnacle/skills` published cards | 11 of 14 | 3 |

The refusal itself is loud (raises rather than skipping), so no run has silently
dropped a card. What is silent is the aggregate: nothing reports how much of the
corpus the instrument cannot reach.

## What was built

### AC1: `normalise_skill_frontmatter` function

**File:** `src/skill_harness/subject/inspect_adapter.py:127`

A named function that reads SKILL.md, drops keys outside the agentskills.io schema,
and writes a temporary normalised copy. The on-disk SKILL.md is never modified.

Normalisation rules (deliberately conservative — drop, never rewrite values that
change semantics):
- Any key not in the agentskills.io schema is dropped.
- `allowed-tools` given as a list is converted to a space-delimited string.
- `description` exceeding the 1024-character cap is truncated to 1024 characters.

The function returns a `NormalisedSkillResult` carrying the temporary directory
and the list of dropped keys.

**Test:** `test_normalise_drops_disable_model_invocation` in `tests/test_subject_layer.py:568`
- Creates a skill directory with `disable-model-invocation: true`
- Calls `normalise_skill_frontmatter` and verifies the on-disk SKILL.md is unchanged
- Verifies the normalised copy has the key removed

Additional tests cover: `argument-hint` (line 586), `allowed-tools` list-to-string
conversion (line 635), long description truncation (line 665), `author`/`date`/`version`
dropping (line 693), and no-op for compliant cards (line 624).

**Red phase observation:** Before the normalisation function existed, calling
`read_skills` on a card with `disable-model-invocation` raised `SkillParsingError`.
After adding the function, the card constructs successfully and the on-disk file is
unchanged.

### AC2: Dropped keys in `config_json`

**File:** `src/skill_harness/subject/inspect_adapter.py:460` (Task metadata)

`build_paired_tasks` now adds `normalised_keys_dropped` to the Task's metadata
dict. During ingestion, this field is extracted from the eval log and included
in the run's `config_json`.

**File:** `src/skill_harness/subject/ingest.py:242` (`ParsedSample.normalised_keys_dropped`)
**File:** `src/skill_harness/subject/ingest.py:734` (config_json construction)

**Test:** `test_build_paired_tasks_records_dropped_keys_in_metadata` in `tests/test_subject_layer.py:716`
- Creates a card with both `disable-model-invocation` and `argument-hint`
- Verifies both keys appear in `tasks[arm].dataset[0].metadata["normalised_keys_dropped"]`

**Red phase observation:** Before the change, `normalised_keys_dropped` was not in
the metadata dict. After the change, the list is populated with the exact keys that
were stripped.

### AC3: Coverage reporting

**File:** `src/skill_harness/subject/inspect_adapter.py:546` (`SkillCorpusCoverage` class)
**File:** `src/skill_harness/subject/inspect_adapter.py:574` (`skill_corpus_coverage` function)

A function that iterates over immediate subdirectories of a corpus directory,
attempts to normalise each card, and reports:
- `candidate_count`: total cards found (with SKILL.md)
- `constructible_count`: cards that normalised successfully
- `refused_count`: cards that failed with reasons
- `refused`: list of (path, reason) tuples

The function returns a `SkillCorpusCoverage` object with an `as_dict()` method
for serialisation.

**CLI command:** `skill-harness skill coverage <corpus_dir>` in
`src/skill_harness/cli/main.py:563`

**Test:** `test_skill_corpus_coverage_reports_refused_cards` in `tests/test_subject_layer.py:754`
- Creates a corpus with a good card, a refused card (schema-unknown key), and
  a directory without SKILL.md
- Verifies the correct shape: candidates, constructible, refused with reasons
- Verifies the refused set is a subset of the candidate set

**Red phase observation:** Before the coverage function, there was no way to
measure how many cards the harness could not reach without running the parser
by hand (which is how this issue was found).

### AC4: Shape assertions, not literal counts

No test asserts a literal loadable/refused count. All tests assert structural
properties:

- The refused set is a subset of the candidate set (`test_skill_corpus_coverage_refused_subset_of_candidates`, line 818)
- A card whose only offending key is stripped moves from refused to constructible
  (`test_skill_corpus_coverage_reports_refused_cards`, line 754)
- A zero-count report has `candidate_count == 0` (`test_skill_corpus_coverage_empty_directory`, line 860)
- A nonexistent directory returns zero counts (`test_skill_corpus_coverage_nonexistent_directory`, line 878)

## Mutation campaign

No formal mutation campaign was run. The tests are designed to fail if:
- The normalisation function drops nothing (all normalise tests create cards with
  schema-unknown keys)
- The function modifies the on-disk file (test checks original content unchanged)
- The function returns a non-compliant normalised copy (test verifies the normalised
  content does not contain the dropped keys)
- The coverage report omits refused cards (test verifies refused paths are in the
  candidate set)
- The `config_json` is missing dropped keys (test verifies the metadata field)

## Test results

All 40 tests in `tests/test_subject_layer.py` pass (1 skipped because the inspect
extra IS installed — the error path for the not-installed case is unreachable).

```
tests/test_subject_layer.py — 40 passed, 1 skipped
tests/test_subject_ingest.py — 76 passed, 1 skipped
tests/test_smoke.py — 14 passed
tests/test_receipts_index.py — 14 passed
```

## Files changed

| File | Change |
|---|---|
| `src/skill_harness/subject/inspect_adapter.py` | Added `normalise_skill_frontmatter`, `NormalisedSkillResult`, `SkillCorpusCoverage`, `skill_corpus_coverage`; modified `build_paired_tasks` to normalise before passing to `claude_code` |
| `src/skill_harness/subject/__init__.py` | Exported new public names |
| `src/skill_harness/subject/ingest.py` | Added `normalised_keys_dropped` to `ParsedSample`; extracted it in `parse_eval_log`; added it to `config_json` |
| `src/skill_harness/cli/main.py` | Added `skill coverage` command |
| `tests/test_subject_layer.py` | Added 12 tests covering AC1, AC2, AC3, AC4 |