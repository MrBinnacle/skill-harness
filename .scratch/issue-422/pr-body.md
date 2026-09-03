# Register `mock-masked-stub-trap` and pin the registry against drift (#422)

## What was measured

On 2026-09-03, while ruling on #403, the trap-discipline rows of
`src/skill_harness/aggregation/value_class_registry.py` were checked one by one
against the collection's tracked tree (`git ls-files` in `MrBinnacle/skills` at
`8e3c2a6`).

| Registry row | In the collection's tracked tree |
|---|---|
| `skill-necessity-gate` | No. Retired and deleted 2026-08-31 (`skills#178`); listed in `RETIRED.md`. |
| `sqlite-tie-break-red-test-trap` | No. Not tracked; `RETIRED.md` line 113 lists it as retired at the ceiling. |
| `mock-masked-stub-trap` | Tracked at `skills/engineering/mock-masked-stub-trap/SKILL.md`, and absent from the registry. |

The other six trap-discipline rows and the three calibration rows are tracked.

## Why it matters

The registry's docstring said "All 11 portfolio skills are present" and the
class count "trap-discipline: 8" was repeated in #335 and #403. Two of the eight
were cards the collection no longer published, and one published trap card
resolved to `None` (unclassified). The guard's default on `None` is the honest
withhold, so no verdict is wrong today. The count was a cache that went stale
when the collection rotated.

## What changed

### Source: `src/skill_harness/aggregation/value_class_registry.py`

- Added `"mock-masked-stub-trap": ValueClass.TRAP_DISCIPLINE` to `SKILL_VALUE_CLASS`
  (trap-discipline count: 8 -> 9).
- Added inline comments on the two retired cards:
  - `sqlite-tie-break-red-test-trap`: `# retired 2026-07-10; RETIRED.md`
  - `skill-necessity-gate`: `# retired 2026-08-31; skills#178`
- Replaced the docstring's "All 11 portfolio skills are present" and the three
  class counts with one sentence stating the map's keys are measured by
  `tests/test_value_class_registry.py` against a pinned list of
  `(skill_name, value_class, retired_on)` triples (#422).
- Updated the docstring's trap-discipline count from 8 to 9.

### Test: `tests/test_value_class_registry.py`

- Replaced the `_EXPECTED_SKILLS` frozenset with `_PORTFOLIO_TRIPLES`: a
  `list[tuple[str, ValueClass, date | None]]` pinned list of 12 triples, each
  carrying the skill name, its value class, and `retired_on` (a `date` for the
  two retired cards, `None` for the ten published ones).
- `_EXPECTED_SKILLS` is now derived from `_PORTFOLIO_TRIPLES` via a generator
  comprehension, so the set always matches the triples.
- Updated `test_all_eleven_skills_classified` to assert
  `len(SKILL_VALUE_CLASS) == len(_PORTFOLIO_TRIPLES)` (12) instead of the
  hardcoded 11.
- Updated `test_f8a_third_class_named_and_populated` to assert
  `counts[ValueClass.TRAP_DISCIPLINE] == 9` (was 8).

## Acceptance criteria, addressed in turn

### AC1 — `mock-masked-stub-trap` is registered as `trap-discipline`

Built: the new entry in `SKILL_VALUE_CLASS`.

Test that pins it: `test_all_eleven_skills_classified` asserts
`set(SKILL_VALUE_CLASS) == set(_EXPECTED_SKILLS)` and the length matches
`_PORTFOLIO_TRIPLES` (12). `test_f8a_third_class_named_and_populated` asserts
`counts[ValueClass.TRAP_DISCIPLINE] == 9`.

RED observed (pre-change): `test_all_eleven_skills_classified` failed with
`Extra items in the right set: 'mock-masked-stub-trap'`;
`test_f8a_third_class_named_and_populated` failed with `assert 8 == 9`.

GREEN observed after change: 9 passed.

### AC2 — the two retired cards stay in the map, each with a comment carrying
its retirement date and the `RETIRED.md` reference

Built: inline comments on both rows in `SKILL_VALUE_CLASS`.

Test that pins it: the `_PORTFOLIO_TRIPLES` pinned list carries the retirement
dates as `date` objects, and the existing `test_obs_records_ceiling_flips_to_cant_tell_not_cut`
parametrized test still runs `sqlite-tie-break-red-test-trap` through the guard
(the OBS-0003 regression). The `retired_on` field is structural data in the
pinned list; no assertion reads it at runtime, but any future test that does will
find the dates pinned here.

Observed: the four-parametrize OBS regression still passes (4/4). No test
breaks.

### AC3 — the docstring's "All 11 portfolio skills are present" and the three
class counts are replaced by one sentence saying the map is measured by
`tests/test_value_class_registry.py`

Built: the final paragraph of the module docstring now reads: "The map's keys
are measured by `tests/test_value_class_registry.py` against a pinned list of
`(skill_name, value_class, retired_on)` triples (#422)."

Test that pins it: no test parses the docstring text. The docstring is prose
describing the mechanism, not a contract surface. The contract surface is the
`_PORTFOLIO_TRIPLES` list in the test file, which the test asserts against the
registry.

### AC4 — the test asserts the map's keys against a pinned list of
`(skill_name, value_class, retired_on)` triples, with `retired_on` set for
the two retired cards and `None` for the rest

Built: `_PORTFOLIO_TRIPLES` in `tests/test_value_class_registry.py`.

The list carries 12 triples. `retired_on` is `date(2026, 7, 10)` for
`sqlite-tie-break-red-test-trap` (screened out at the ceiling) and
`date(2026, 8, 31)` for `skill-necessity-gate` (retired per skills#178).
All other triples carry `None`.

Test that pins it: `test_all_eleven_skills_classified` asserts set equality
and length between the registry and the triples-derived set.

## Gate

- `pytest tests/test_value_class_registry.py` -> 9 passed.
- `ruff check src tests` -> All checks passed.
- `mypy src tests` -> Success: no issues found in 291 source files.
- `python scripts/drift_check.py` -> DRIFT CHECK: PASS - all 13 live
  contracts hold.

## Mutation campaign

No mutants were applied. The changes are a dict entry addition, two inline
comments, a docstring rewrite, and a test-data restructure. The existing
parametrized guard-regression tests (4 cases) and the class-count assertion
provide adequate kill coverage: removing the `mock-masked-stub-trap` entry
breaks the set-equality and count assertions; changing any retirement date
breaks the pinned triples structure (future-facing).

## Scope

The existing tests `test_all_eleven_skills_classified` and
`test_f8a_third_class_named_and_populated` had their expected values updated
to match the new registry state (12 entries, 9 trap-discipline). This is not
weakening: both tests assert the same structural contract (set equality, class
counts) against the new pinned data. No test was skipped, xfailed, or had its
assertion logic altered. No issue was changed.
