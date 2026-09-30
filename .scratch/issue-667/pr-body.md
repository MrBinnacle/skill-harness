# #667: Seeded random-subset arm for the collection-effect screen

## Summary

This PR adds a seeded random-subset arm to the declared-arm machinery (#554).
Given a subject package (card name → description) and a seed,
`draw_subset_arm` resolves the package to a fixed subset of half its
descriptions, rounded down, and returns it as a plain `ArmSpec`. The existing
runner assembles and samples that spec exactly as it does any declared arm;
this change adds sampling, not a second arm system.

The draw's seed and chosen card names are frozen into `runs.config_json`
under the new `subset_draws` key when the run starts. A SERS receipt's
`subject_identity.arms` names the arm;
`trace_subset_draw(config_json, arm_name)` maps that name back to the seed
and the subset. After a run,
`build_subset_run_record(run_id, config_json, listing)` compares #664's
delivered listing with the intended subset and flags every intended card the
listing dropped or truncated. The run is kept: the check reports on the
record and never rewrites evidence.

New module: `src/skill_harness/ablation/subset_arm.py`. Changed:
`src/skill_harness/ablation/runner.py` (`RunConfig.subset_draws`,
`run_arms(subset_draws=...)`). Tests: `tests/ablation/test_subset_arm_667.py`
(34 tests). All fixture-only; the subject model is mocked at the SDK
boundary per the A32 precedent.

## Acceptance criteria

### AC1: The same package and seed give the same subset on every call; a different seed gives a different subset for a package of 14

**What I built:** `draw_subset_arm(subject_cards, *, seed=None, arm_name=...)`
in `src/skill_harness/ablation/subset_arm.py`. It samples without replacement
from a `random.Random(seed)` stream, reports the seed it used (caller input
when passed, fresh `secrets` entropy when not), and orders the chosen names
in package order so one seed always yields one sequence. The resulting
`ArmSpec` carries the chosen cards' descriptions verbatim.

**Tests:** `TestSameSeedSameSubset` — five tests: two draws at seed 1729 are
identical in names and bodies; every chosen name is a package card whose
description matches its arm body; seed 1729 and seed 2718 differ on the
14-card package; the exact seven names seed 1729 draws are pinned
(`test_the_pinned_seed_draws_the_pinned_subset`); the passed seed is the
seed reported.

**Observation:** Before the change the file failed at collection with
`ModuleNotFoundError: No module named 'skill_harness.ablation.subset_arm'` —
the feature did not exist. After the first implementation (5 tests) they
passed, and they still pass with the AC2 size fix in place; the pinned-tuple
test fails on any change to the sampling stream.

### AC2: The subset size is half the package, rounded down, and never zero for a package of two or more

**What I built:** the subset size is `len(names) // 2`. The first pass used
the ceiling ("about half"); the AC2 test forced it to the floor.

**Tests:** `TestSubsetSizeIsHalfRoundedDown` — parametrized over packages of
2, 3, 4, 5, 7 and 14 at both seeds, asserting `len == n // 2`; a
never-zero parametrization over 2, 3, 5, 7, 14, 15; and a seed-policy test
asserting two seedless draws of one package carry different seeds (the
"a new run draws a new seed unless one is passed" rule).

**Observation:** The size test was written against the ceiling pass and
failed for the right reason: `AssertionError: assert 4 == 3` on the 7-card
package (three parametrizations failed, 14 passed). Changing one line to
`len(names) // 2` turned them green: 17 passed, 0 failed.

### AC3: The seed and the subset names appear in the run record, and a receipt can be traced back to them

**What I built:** `RunConfig.subset_draws` (a tuple of
`SubsetArmDrawRecord`: arm name, seed, card names) serialized into
`runs.config_json` even when empty, and `run_arms(subset_draws=...)`, which
normalizes `SubsetArmDraw` values to records and refuses — before any run
row — a record whose arm name is not among the run's declared arms.
`trace_subset_draw(config_json, arm_name)` performs the reverse join a
receipt needs.

**Tests:** `TestRunRecordCarriesTheDraw` — four tests: after a mocked
`run_arms`, the stored `config_json` holds exactly
`{"arm_name": "subset_half", "seed": 1729, "card_names": [the seven pinned
names]}` and round-trips through `RunConfig.from_json`; a run that draws
nothing still writes the key as an empty list; a receipt minted from the
run's `receipt_arm_names()` via `build_subject_identity` reads
`arms == "subset_half"` and `trace_subset_draw` returns the seed and names
from that name alone; a draw naming an undeclared arm raises `ValueError`
with zero run rows written.

**Observation:** Before the change the test file failed at collection with
`ImportError: cannot import name 'SubsetArmDrawRecord' from
'skill_harness.ablation.subset_arm'`. After the record seam landed (field,
serialization, runner parameter, trace helper): 22 passed, 0 failed.

### AC4: A fixture where an intended card is absent from the delivered listing raises the integrity flag; a fixture where every card is delivered does not

**What I built:** `check_delivery_integrity(listing, intended_names)` returns
a `DeliveryIntegrity` naming every intended card whose #664 status is
`dropped` or `truncated` (or that the listing does not know at all), with
`integrity_ok` as the flag.
`build_subset_run_record(run_id, config_json, listing)` attaches that
verdict to the run record assembled from the frozen config. The function
never raises on a damaged delivery and never writes: the run row stays
present and completed.

**Tests:** `TestDeliveryIntegrityFlag` — five tests: a transcript listing
missing one intended card raises the flag and names that card; a listing
holding every card leaves the flag down; a shortened (truncated) intended
description raises the flag too; the full integration path —
`run_arms`, then a missing-card fixture — builds a record whose
`delivery_integrity` is flagged while the `runs` row still reads completed
with its original timestamp; the all-delivered fixture builds a clean record.

**Observation:** Before the change the file failed at collection with
`ImportError: cannot import name 'build_subset_run_record'`. After the
integrity seam landed: 27 passed, 0 failed.

### AC5: The CI gates pass — ruff check, ruff format --check, mypy --strict

Run before every commit, in the gate's order, from this repository's own
`.github/workflows/ci.yml`:

- `ruff check src tests scripts` — clean at every commit.
- `ruff format --check src tests scripts` — clean (formatter applied to the
  touched files, not the tree).
- `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py
  scripts/check_dependency_anchor.py` — clean.

**Observation:** The first full-suite run failed
`tests/test_assurance_static_analysis_171.py::test_coverage_floor_report_has_branch_results_and_honesty_warning`
with `StopIteration`: that test enumerates every module under `ablation/`
and requires a row in `docs/assurance/coverage-floors.md`, and the new
`subset_arm.py` had none. Fixed in this PR: the row (22 branches, 0
uncovered, mutation `absent`, 100.0% branch coverage, flagged `BELOW 80%`
on the mutation arm of the attention rule), a dated paragraph in the report
following the `ablation/arms.py` precedent, the later-row counts
(12 flagged of 25; six unmeasured by #166), and the `docs/receipts-index.md`
Claims line for that receipt. The refusal tests that take the module to
22/22 branches (`TestSubsetArmRefusals`) landed in the same commit.

Final gate, with CI's `PYTHONHASHSEED=0` (the earlier run without it failed
only the six `test_pythonhashseed_set` guards and the Tier-1 collection
guard, which enforce that environment variable — environment, not code):

- full CI selection: `pytest -q -n 4 -m "not live and not calibration and
  not assurance"` → **3688 passed, 40 skipped, 2 xfailed, 0 failed, 0
  errors** (12m32s).
- `python scripts/drift_check.py` → **PASS, all 22 live contracts hold.**

## Mutation campaign (hand-run, recorded here like #554's)

Ten mutants applied one at a time to the working tree, each run against
`tests/ablation/test_subset_arm_667.py`, each reverted. All ten were killed
by named assertions:

| Mutant | Change | Killed by |
|---|---|---|
| m1 | subset size `n // 2` → ceiling | `TestSubsetSizeIsHalfRoundedDown::test_subset_size_is_the_package_size_divided_by_two_rounded_down[3-1]` (and `[5-2]`, `[7-3]`) |
| m2 | `Random(seed)` → `Random(0)` | `TestSameSeedSameSubset::test_a_different_seed_gives_a_different_subset_for_a_package_of_14`, `::test_the_pinned_seed_draws_the_pinned_subset` |
| m3 | seedless draw → fixed seed `1` | `TestSubsetSizeIsHalfRoundedDown::test_a_caller_who_passes_no_seed_gets_a_fresh_drawn_seed` |
| m4 | arm bodies reversed | `TestSameSeedSameSubset::test_every_drawn_name_is_a_package_card_and_bodies_match` |
| m5 | integrity blind to `truncated` | `TestDeliveryIntegrityFlag::test_a_truncated_intended_card_is_also_flagged` |
| m6 | `integrity_ok` stuck `True` | `TestDeliveryIntegrityFlag::test_an_intended_card_absent_from_the_delivered_listing_raises_the_flag` |
| m7 | recorded seed written as `0` | `TestRunRecordCarriesTheDraw::test_run_config_json_freezes_the_seed_and_the_subset_names` |
| m8 | undeclared-arm check emptied | `TestRunRecordCarriesTheDraw::test_a_draw_naming_an_undeclared_arm_is_refused_before_any_run_row` |
| m9 | trace match inverted (`!=`) | `TestRunRecordCarriesTheDraw::test_a_receipt_traces_back_to_the_seed_and_the_subset_names`, `TestSubsetArmRefusals::test_a_trace_for_an_arm_the_run_never_drew_is_refused` |
| m10 | duplicate-name guard removed | `TestRunRecordCarriesTheDraw::test_duplicate_draws_for_one_arm_are_refused_before_any_run_row` |

This is a hand-run pass, not the #166 instrument. It does not fill the
`absent` mutation score in `docs/assurance/coverage-floors.md`, and no
mutation-receipt document exists under `docs/assurance/` for #667 — one was
not required by this ticket, and inventing a #166-style score here would
claim an instrument that never ran.

## Companions and what does not exist yet

- `docs/assurance/coverage-floors.md` (#171) carries the `subset_arm.py` row
  and dated paragraph added by this PR; `docs/receipts-index.md` names that
  row in its Claims line for the report.
- The parent issue #663 (collection-effect screen) has no artifact in this
  repository yet — no screen module, no design doc, no branch. This PR
  builds one free part of it; the screen itself does not exist yet.
- #664's delivered listing extractor exists and is unchanged;
  `extract_delivered_listing` is the input to this PR's integrity check.
- The run's SERS receipt does not carry the seed itself; the trace goes
  receipt arm name → `runs.config_json.subset_draws`. Storing the flag in a
  new evidence table was not done: migrations require SCHEMA review and this
  ticket spends none, so the flag rides on the `SubsetRunRecord` the screen
  will consume.

## Next action

Merge. The parent screen (#663) can then consume `SubsetRunRecord`: the
draw frozen at run start plus the delivery verdict computed after it.
