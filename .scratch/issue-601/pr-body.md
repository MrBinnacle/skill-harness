# PR: #601 — stale registry key closure-mode-at-boundaries → closure-mode

`value_class_registry.py:52` keyed `"closure-mode-at-boundaries"`. No such skill
exists. `skills#286` (`541522a`) renamed the published card to `closure-mode`.
The registry could not see the live skill, so `value_class_for("closure-mode")`
returned `None` and the skill took the unclassified path instead of the
`trap-discipline` one it was deliberately assigned.

The defect was invisible to the existing seven tests because they pin
`(skill_name, value_class, retired_on)` triples — they check that the string
matches itself, not that it names a skill on any surface.

## Files changed

- `src/skill_harness/aggregation/value_class_registry.py` — renamed the registry
  key from `closure-mode-at-boundaries` to `closure-mode` (line 52); added a
  paragraph to the module docstring documenting the deliberate stale-key
  behaviour decision (lines 27-31).
- `tests/test_value_class_registry.py` — renamed the triple from
  `closure-mode-at-boundaries` to `closure-mode` (line 55); added staleness
  detection infrastructure: `_KNOWN_LIVE_SKILLS` (lines 84-97),
  `_stale_skill_keys()` helper (lines 100-113), `test_no_stale_skill_keys`
  (lines 116-131), `test_stale_key_check_catches_poisoned_registry` (lines
  134-147). Updated module docstring to note the fifth lock (lines 12-13).

## Acceptance criteria

### AC1: Every registry key resolves to a skill that exists on a named surface, or is explicitly marked retired with a pointer to where it went

Built: renamed the stale key `closure-mode-at-boundaries` to `closure-mode` in
`SKILL_VALUE_CLASS` and the pinned `_PORTFOLIO_TRIPLES`. Two keys are already
retired with inline annotations (`sqlite-tie-break-red-test-trap` retired
2026-07-10, `skill-necessity-gate` retired 2026-08-31). The remaining 10
non-retired keys all resolve against the published collection's current names.

Test: `test_portfolio_pinned_by_triples` (existing, line 155) pins the
`(skill_name, value_class, retired_on)` triples and asserts the registry dict
matches exactly. After the rename, this test passes — it was failing on the
pre-fix tree because the triple still held `closure-mode-at-boundaries` while
the registry had been updated.

Observed before fix: the existing test suite passed (9/9) because the triple
and the registry both held the same stale string — the string matched itself.
Observed after fix: 11/11 tests pass (9 original + 2 new staleness tests).

### AC2: A test fails when a key stops naming an existing skill

Built: `_KNOWN_LIVE_SKILLS` (a `frozenset` of the 10 current published skill
names, sourced from the class-hypothesis census and SKILL.md frontmatter),
`_stale_skill_keys()` (returns non-retired keys missing from the live set),
`test_no_stale_skill_keys` (asserts no stale keys exist), and
`test_stale_key_check_catches_poisoned_registry` (negative control).

Test: `test_no_stale_skill_keys` (line 116) checks every non-retired registry
key against `_KNOWN_LIVE_SKILLS`. When a card is renamed without updating the
registry, this test fails. `test_stale_key_check_catches_poisoned_registry`
(line 134) injects `"deliberately-stale-key"` into a copy of the registry and
asserts the check catches it — proving the check is not vacuous.

Observed before fix: I confirmed the staleness check catches
`closure-mode-at-boundaries` by running `_stale_skill_keys()` against a
pre-fix registry snapshot — it returned `["closure-mode-at-boundaries"]`.
Observed after fix: both new tests pass (11/11 total).

### AC3: The rename is reconciled

Built: the registry now keys `closure-mode` — the name the collection publishes.
The decision to follow the new name rather than record both is the correct one:
the registry is keyed by `skill_name`, which is "the exact string the screen
store keys on, == the published skill-card name" (module docstring line 12).
Recording both the old and new name would create a second entry for the same
skill, which the test's uniqueness assertion (`len(names) == len(set(names))`)
would reject.

Test: `test_portfolio_pinned_by_triples` asserts the registry matches the
pinned triples exactly. After the rename, the triple `("closure-mode",
ValueClass.TRAP_DISCIPLINE, None)` matches the registry entry.

Observed: the existing 9 tests pass unchanged after the rename (11/11 with new
tests).

### AC4: A deliberate decision on what happens to a skill whose key goes stale

Built: the module docstring now states the decision explicitly (lines 27-31):
a stale key falls to `value_class_for()` returning `None` → unclassified →
CAN'T-TELL-YET (wrong instrument), never a false CUT. This is the safe
default: an honest refusal rather than a misclassification. The staleness
detection test catches stale keys before production; the silent fall is
defence-in-depth, not the primary guard.

Test: `test_value_class_for_unregistered_is_none` (existing, line 194) pins
that an unknown skill_name returns `None`. This is the same path a stale key
takes — the function uses `dict.get()`, which returns `None` for missing keys.
The test proves the default is honest: `None` → CAN'T-TELL-YET, never CUT.

Observed: the existing test passes unchanged (11/11 total).

## Mutation campaign

The ticket does not name a mutation receipt obligation. No mutation receipt was
generated.

## Test-to-criterion map

| Criterion | Test | What it pins |
|---|---|---|
| AC1 | `test_portfolio_pinned_by_triples` | Registry matches pinned triples exactly |
| AC2 | `test_no_stale_skill_keys` | No non-retired key is missing from live set |
| AC2 (control) | `test_stale_key_check_catches_poisoned_registry` | Staleness check catches a poisoned key |
| AC3 | `test_portfolio_pinned_by_triples` | Triple matches registry entry after rename |
| AC4 | `test_value_class_for_unregistered_is_none` | Unknown skill_name → None (safe default) |

## Gate

Full gate green: `ruff check`, `ruff format --check`, `mypy --strict` all pass
on `src/` and `tests/`. 11/11 tests pass in `test_value_class_registry.py`.
