# #735: Release gate assurance checks G7/G8 fail closed

## Summary

`scripts/release_gate.py` scoped G7 (assurance issues closed) and G8
(green assurance lane run) to the 0.3 minor line via `_is_zero_three`. Off
that line both gates called `_record_skip` and returned, so a `0.4.0` tag
passed the release gate with no assurance check at all: the summary printed
`RELEASE GATE: PASS (6 of 8 gates ran; skipped ...)` and the publish
pipeline's "the gate must PASS" step held with nothing assured. G8 also
accepted any historical green `assurance.yml` run, so a seven-week-old run
at a different commit satisfied the check at tag time.

Decision recorded 2026-10-05 (S516 triage): fail closed. A version line
with no declared assurance requirement fails the gate instead of skipping.
G8 counts only a green assurance run at the release candidate's own commit.
Option (b) — shipping 0.4.0 with both checks skipped as an accepted
exception — is rejected. Ground: the operator's standing values rule,
verbatim: "My values call will always be 'the hard right over the easy
wrong'".

Rework round 1 (FAIL verdict at `c2d30bc`) measured two clauses unpinned.
This head (`c4ba410`) adds the missing tests, keeps every green from the
first build, and regenerates this body from the final head.

## What changed (whole branch vs origin/main)

Files in `git diff --name-only origin/main...HEAD`:

- `scripts/release_gate.py` — removed `_is_zero_three`. Added
  `ASSURANCE_REQUIREMENTS`, a declared table keyed by minor line, and
  `AssuranceRequirement(issues, g8_required)`. The `0.3` row reproduces
  the previous requirement exactly: issues 167–174, G8 required.
  `ASSURANCE_ISSUES` is folded into that row. No other row is added by
  this ticket; declaring the `0.4` row is a separate decision. Until it
  lands the gate blocks any 0.4.x release and any merge that bumps the
  version to 0.4.x. That block is the intended outcome.
- `tests/test_release_gate_206.py` — seeded-tree suite rewritten around
  the declared table. Rework round 1 added two pins:
  `test_g8_fails_when_a_green_run_at_another_sha_is_returned_unfiltered`
  (unfiltered stub, kills the `head_sha == sha` clause) and
  `test_one_part_version_fails_closed_with_not_run` (one-part version,
  kills the `_minor_line` fallback). `_run_gate` gained
  `filter_runs_by_head_sha` (default True, matching GitHub).
- `tests/test_release_gate_real_tree.py` — stub answers
  `actions/runs?head_sha=` and 404s the removed workflow-filtered
  endpoint; `_script_assurance_issues()` parses the `0.3` row out of the
  script text.
- `docs/assurance/release-gate-red-206.md` — transcript re-recorded: one
  failure (open issue #169), G8 skipped off a tag ref.
- `docs/receipts-index.md` — the red-206 entry's Claims and
  Refuses-to-claim lines updated to match.

Mechanism, stated once. G7 and G8 look up `_minor_line(version)` in
`ASSURANCE_REQUIREMENTS`. A missing row is NOT RUN: each gate prints the
ticket's message, appends an error, and the gate prints
`RELEASE GATE: BLOCKED` and exits 1. A row whose G7 list is explicitly
empty, or whose `g8_required` flag is explicitly false, makes that gate
print that it passed by declaration, naming the row; it never prints
SKIPPED. On a tag ref G8 reads `GITHUB_SHA`, queries
`{_api_base()}/actions/runs?head_sha=<sha>`, and passes only if a run
whose `path` is `.github/workflows/assurance.yml` has
`status == "completed"` and `conclusion == "success"` at exactly that
SHA. Off a tag ref G8 records itself as skipped with the reason "not a
tag ref, no release candidate commit", the same model G6 already used.
The script contains no `actions/workflows/assurance.yml/runs` string.
API failures still fail closed.

## Acceptance criteria

### AC1: Seeded tree at 0.4.0 with no 0.4 row prints NOT RUN for G7 and G8, prints RELEASE GATE: BLOCKED, exits 1

**Test:** `tests/test_release_gate_206.py::test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8`
Companion: `test_unknown_minor_line_blocks_even_a_patch_release` (0.2.4).

**Red before the fix** (gate reverted to `origin/main`, same test run):

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G7: SKIPPED, version 0.4.0 is not on the 0.3 minor line.
G8: SKIPPED, version 0.4.0 is not on the 0.3 minor line.
RELEASE GATE: PASS (5 of 8 gates ran; skipped G6, G7, G8), public surfaces in lockstep at version 0.4.0.

E   assert 0 == 1
```

The gate passed a 0.4.0 tree with both assurance checks skipped. That is
the defect.

**Green after the fix** (head `c4ba410`):

```text
G6: not a tag ref (local run) — tag-match check self-skips.
RELEASE GATE: BLOCKED (5 of 8 gates ran; skipped G6; not run G7, G8), 2 stale surface(s) at version 0.4.0:
  FAIL  G7: NOT RUN, no assurance requirement is declared for the 0.4 line; add a row to ASSURANCE_REQUIREMENTS before releasing 0.4.x.
  FAIL  G8: NOT RUN, no assurance requirement is declared for the 0.4 line; add a row to ASSURANCE_REQUIREMENTS before releasing 0.4.x.
```

Exit code 1. Coverage counts G7 and G8 as `not run`, never as skipped.

### AC2: A declared row with empty G7 list and G8 not required passes by declaration; neither line contains SKIPPED

**Test:** `tests/test_release_gate_206.py::test_declared_empty_requirement_passes_by_declaration`

**Red before the fix:** the test's copy helper could not insert a row —
the script had no `ASSURANCE_REQUIREMENTS` table at all:

```text
E   AssertionError: scripts/release_gate.py no longer declares ASSURANCE_REQUIREMENTS in the form this module's copy helper inserts into
```

**Green after the fix:** the copied script declares `0.9` with
`issues=()` and `g8_required=False`. The API base points at a dead port,
so a pass proves the gate did not read the network. Output:

```text
G7: PASSED by declaration, ASSURANCE_REQUIREMENTS row '0.9' declares no assurance issues for the 0.9 line.
G8: PASSED by declaration, ASSURANCE_REQUIREMENTS row '0.9' does not require a green assurance run for the 0.9 line.
RELEASE GATE: PASS (7 of 8 gates ran; skipped G6), public surfaces in lockstep at version 0.9.0.
```

No SKIPPED line for G7 or G8. Coverage counts both as ran.

### AC3: On a tag ref with a green assurance run at another SHA, G8 fails and the message names the release-candidate SHA

**Tests:**
- `tests/test_release_gate_206.py::test_g8_fails_when_the_green_run_is_at_another_sha`
  (filtered stub: the gate never sees the sha-B run)
- `tests/test_release_gate_206.py::test_g8_fails_when_a_green_run_at_another_sha_is_returned_unfiltered`
  (**R1-F1 pin:** the stub returns the sha-B run even when sha A is
  queried; this is the test that kills the `head_sha == sha` clause)

**Red before the fix** (gate at `origin/main`): G8 queried the
workflow-filtered endpoint, which the stub 404s:

```text
E   AssertionError: G8: could not read assurance workflow runs: HTTP Error 404: Not Found
E   assert 'aaaaaaaa...aaaa' in 'G8: could not read assurance workflow runs: HTTP Error 404: Not Found'
```

**R1-F1 red at `c2d30bc`** (clause deleted, unfiltered stub, measured
this session):

```text
E   AssertionError: G8 accepted a green assurance run at another SHA when the stub returned it unfiltered.
E     RELEASE GATE: PASS (8 of 8 gates ran), public surfaces in lockstep at version 0.3.0.
E   assert 0 == 1
```

At `c2d30bc` both existing G8 stubs filtered by `head_sha` before
answering, so deleting `run.get("head_sha") == sha` left all 30 tests
passing. The unfiltered stub is what pins the clause.

**Green after the fix** (both arms):

```text
RELEASE GATE: BLOCKED (8 of 8 gates ran), 1 stale surface(s) at version 0.3.0:
  FAIL  G8: no successful assurance.yml workflow run at the release candidate commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; produce one with 'gh workflow run assurance.yml --ref v0.3.0'
```

The message names `<sha A>` and the dispatch command.

### AC4: A green run at the release-candidate SHA passes; same SHA with another workflow path or non-success conclusion fails

**Tests:**
- `test_g8_passes_when_the_green_run_is_at_the_release_candidate_sha`
- `test_g8_fails_when_the_run_at_the_sha_is_another_workflow`
- `test_g8_fails_when_the_run_at_the_sha_is_not_success[red-run]`
- `test_g8_fails_when_the_run_at_the_sha_is_not_success[no-conclusion]`

**Red before the fix:** every arm 404'd on the removed endpoint (same as
AC3). The wrong-path and non-conclusion arms could not express their
cases: the stub had no `path`/`head_sha` fields and the gate had no such
checks.

**Green after the fix:**

```text
# green arm
RELEASE GATE: PASS (8 of 8 gates ran), public surfaces in lockstep at version 0.3.0.

# wrong-path arm (path=".github/workflows/ci.yml" at sha A)
FAIL  G8: no successful assurance.yml workflow run at the release candidate commit aaaa...aaaa; produce one with 'gh workflow run assurance.yml --ref v0.3.0'

# red-run arm (conclusion="failure" at sha A)
FAIL  G8: no successful assurance.yml workflow run at the release candidate commit aaaa...aaaa; produce one with 'gh workflow run assurance.yml --ref v0.3.0'
```

### AC5: On a tag ref with GITHUB_SHA unset, G8 fails

**Test:** `tests/test_release_gate_206.py::test_g8_fails_when_github_sha_is_unset_on_a_tag_ref`

**Red before the fix:** the old G8 never looked at GITHUB_SHA; it queried
the workflow-filtered endpoint and 404'd, so the named "GITHUB_SHA is
unset" failure was absent:

```text
E   AssertionError: ['G8: could not read assurance workflow runs: HTTP Error 404: Not Found']
```

**Green after the fix:**

```text
FAIL  G8: GITHUB_SHA is unset on a tag ref; the release candidate commit cannot be identified
```

`G8: SKIPPED` is not in stdout.

### AC6: Off a tag ref, G8 is skipped with the "no release candidate" reason; the script never queries the workflow-filtered endpoint

**Tests:**
- `tests/test_release_gate_206.py::test_g8_skips_off_a_tag_ref_with_no_release_candidate`
- `tests/test_release_gate_206.py::test_the_script_never_queries_the_workflow_filtered_endpoint`
- `tests/test_release_gate_real_tree.py::test_g8_self_skips_off_a_tag_ref_on_the_real_tree`

**Red before the fix:**

```text
E   AssertionError: scripts/release_gate.py queries the workflow-filtered endpoint again; #735 binds G8 to actions/runs?head_sha=
E     '/actions/workflows/assurance.yml/runs' is contained here:
E       pi_base()}/actions/workflows/assurance.yml/runs")
```

And the behavioural test on a non-tag 0.3.0 tree:

```text
RELEASE GATE: BLOCKED (7 of 8 gates ran; skipped G6), 1 stale surface(s) at version 0.3.0:
  FAIL  G8: could not read assurance workflow runs: HTTP Error 404: Not Found
```

**Green after the fix:**

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G8: SKIPPED, not a tag ref, no release candidate commit.
RELEASE GATE: PASS (6 of 8 gates ran; skipped G6, G8), public surfaces in lockstep at version 0.3.0.
```

The stub's request log contains no `/actions/runs` path. The script text
contains no `actions/workflows/assurance.yml/runs`. The real-tree control
asserts the same skip on the live tree at 0.3.0, and the stub's request
set is exactly `/issues/167` … `/issues/174`.

### AC7: At 0.3.0 the 0.3 row produces the same G7 issue reads (167 to 174) as before

**Test:** `tests/test_release_gate_206.py::test_zero_three_row_reads_the_same_assurance_issues_as_before`
Real-tree companion: `tests/test_release_gate_real_tree.py::test_the_assurance_gates_asked_for_exactly_the_issues_the_script_names`

**Red before the fix:** the old code also read 167–174, but the run was
blocked by G8's 404 on the removed endpoint before the request-set
assertion could be evaluated:

```text
RELEASE GATE: BLOCKED (7 of 8 gates ran; skipped G6), 1 stale surface(s) at version 0.3.0:
  FAIL  G8: could not read assurance workflow runs: HTTP Error 404: Not Found
```

**Green after the fix:** the stub sees exactly `/issues/167` …
`/issues/174` and nothing else on a non-tag ref; the gate exits 0. The
real-tree stub's request set matches the same eight paths, parsed from
the `0.3` row rather than copied as literals.

### AC8: Each red shown run; mutation campaign recorded at the final head

Reds for AC1–AC7 and the two R1 pins are inlined above: fail-before /
pass-after, each from a command run in this session.

Mutation campaign at head `c4ba410`. Each mutant applied to a copy of
`scripts/release_gate.py`, the named test run, the tree restored. Counts
come from that run.

| Mutant | Change | Killed by |
| --- | --- | --- |
| M1 unknown-line pass | Treat missing table row as `AssuranceRequirement((), False)` | `test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8` — expects NOT RUN + BLOCKED, gets PASS by declaration |
| M2 G8 any-sha | Drop the `head_sha == sha` check in G8 | `test_g8_fails_when_a_green_run_at_another_sha_is_returned_unfiltered` — expects failure naming sha A, gets `RELEASE GATE: PASS (8 of 8 gates ran)` |
| M3 G8 any-path | Drop the `path == ".github/workflows/assurance.yml"` check | `test_g8_fails_when_the_run_at_the_sha_is_another_workflow` — expects failure, gets PASS |
| M4 G8 any-conclusion | Drop the `conclusion == "success"` check | `test_g8_fails_when_the_run_at_the_sha_is_not_success[red-run]` — expects failure, gets PASS |
| M5 G8 missing-sha skip | Treat unset GITHUB_SHA as `_record_skip` | `test_g8_fails_when_github_sha_is_unset_on_a_tag_ref` — expects G8 error, sees skip + PASS |
| M6 declared-pass skip | Empty G7 list → `_record_skip` instead of declaration pass | `test_declared_empty_requirement_passes_by_declaration` — expects PASSED by declaration, sees SKIPPED |
| M7 issue-range drift | `range(167, 175)` → `range(167, 176)` in the 0.3 row | `test_zero_three_row_reads_the_same_assurance_issues_as_before` — stub 404s #175, G7 fails closed |
| M8 `_minor_line` fallback dropped | Delete `if len(parts) >= 2 else version` | `test_one_part_version_fails_closed_with_not_run` — one-part version crashes with IndexError instead of NOT RUN |

**8 of 8 killed.** Correction to the previous body: "M2 G8 any-sha" was
*not* killed by `test_g8_fails_when_the_green_run_is_at_another_sha` at
`c2d30bc`. That test's stub filters by `head_sha` before answering, so
the gate never saw a run at another commit and the mutant survived
(verified: that test passes under the mutant). The unfiltered-stub test
added in this rework is what kills M2.

Measured, not required by the ticket: the old filtered-stub test still
survives the any-sha mutant by construction. M18 (dropping
`status == "completed"`) predates this PR. G8's run query sends no
`per_page`, so it reads only the first 30 runs at a commit; that can
block a good release but never passes a bad one.

No mutant-receipt file under `docs/assurance/` was added: this ticket
names no `scripts/mutation_receipt.py --select` obligation, and
`tests/test_receipts_index.py` gates that directory.

### AC9: Real-tree test still passes at 0.3.0; mypy --strict and the CI matrix

**Real-tree control** (`tests/test_release_gate_real_tree.py`, 6 tests):
all pass at `c4ba410`. Gate output on the live tree with the stub
serving the `0.3` row's issues:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G8: SKIPPED, not a tag ref, no release candidate commit.
RELEASE GATE: PASS (6 of 8 gates ran; skipped G6, G8), public surfaces in lockstep at version 0.3.0.
requested: ['/issues/167', '/issues/168', '/issues/169', '/issues/170', '/issues/171', '/issues/172', '/issues/173', '/issues/174']
```

**Release-gate modules:** `tests/test_release_gate_206.py` (26 tests) +
`tests/test_release_gate_real_tree.py` (6 tests) = 32 passed at
`c4ba410`.

**mypy --strict:** full CI scope `mypy --strict src/ tests/
scripts/drift_check.py scripts/release_gate.py
scripts/check_dependency_anchor.py` — clean at `c4ba410`
(`Success: no issues found in 388 source files`).

**ruff:** `ruff check src tests scripts` — All checks passed.
`ruff format --check src tests scripts` — 431 files already formatted
after applying the formatter to `tests/test_release_gate_206.py`.

**drift-guard:** `python scripts/drift_check.py` — `DRIFT CHECK: PASS -
all 22 live contracts hold.`

**Receipts index and gate-scope tests:**
`tests/test_receipts_index.py`, `tests/test_mypy_gate_scope_566.py`,
`tests/test_ruff_gate_scope_483.py` — pass. The amended
`docs/assurance/release-gate-red-206.md` entry keeps both a Claims and a
Refuses-to-claim line. `scripts/release_gate.py` remains inside both gate
scopes.

## Existing tests this change updates, and why

The constraint against editing existing tests is a constraint against
greening the suite by making it check less. These edits do the opposite:
they re-pin behaviour the #735 decision explicitly overturned, with
stronger assertions than the old ones carried.

| Old test | Old assertion | Why it had to move |
| --- | --- | --- |
| `test_gate_names_the_assurance_gates_it_skips_off_the_zero_three_line` | 0.4.0 → PASS, G7/G8 SKIPPED | Ticket decision rejects skip; AC1 requires NOT RUN + BLOCKED. Replaced by `test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8`. |
| `test_gate_reports_all_eight_running_on_the_zero_three_line` | 0.3.9 non-tag → only G6 skipped | After #735 G8 skips off a tag ref (no release candidate). Replaced by `test_gate_reports_g7_running_and_g8_skipping_on_the_zero_three_line` and `test_gate_reports_all_eight_running_on_a_tag_ref`. |
| `test_patch_release_is_exempt_from_the_assurance_gate` | 0.2.4 → PASS | No 0.2 row is declared; unknown line fails closed. Replaced by `test_unknown_minor_line_blocks_even_a_patch_release`. |
| `test_zero_three_release_is_blocked_without_a_successful_assurance_run` | non-tag 0.3.0 + seeded runs → G8 fails | G8 does not read the API off a tag ref. Replaced by the tag-ref G8 suite (AC3–AC5). |
| `test_zero_three_release_is_blocked_when_the_assurance_state_is_unreadable` | dead API → both G7 and G8 read errors on non-tag | G8 has nothing to read off a tag ref. Rewritten to run on a tag ref so both reads are exercised. |
| `test_the_assurance_reads_authenticate_when_a_token_is_present` | `len(seen) == len(ASSURANCE_ISSUES) + 1` | The +1 was the runs read; off a tag ref G8 does not read. Now `len(seen) == len(ZERO_THREE_ISSUES)`. |
| G3/G5 differential tests seeded at 0.2.4 | relied on 0.2.x being outside assurance scope | They now run a script copy that declares the `0.2` row, so the green arm is a declared line and the red arm's single failure stays attributable to G3/G5. |
| `test_red_receipt_records_the_output_the_gate_actually_prints` | transcript with two failures (open issue + no green run) | Re-recorded receipt: one failure, G8 skipped off a tag ref. The comparison is unchanged — it still checks the receipt against live output. |

`tests/test_release_gate_real_tree.py` changes are named in the ticket:
the stub must answer the new endpoint, and the module must still pass on
the real tree at 0.3.0.

## Rework round 1 findings, and what this head does about them

| Finding | Measurement at `c2d30bc` | Fix at `c4ba410` |
| --- | --- | --- |
| R1-F1: G8 `head_sha == sha` unpinned | Deleting the clause left all 30 tests passing; against an unfiltered stub the mutant printed `RELEASE GATE: PASS (8 of 8 gates ran)` | Added `test_g8_fails_when_a_green_run_at_another_sha_is_returned_unfiltered` and the `filter_runs_by_head_sha=False` stub mode. Mutant now red; test green with the clause. |
| R1-F2: `_minor_line` fallback unpinned | Deleting the else-branch crashed a one-part version with IndexError instead of NOT RUN | Added `test_one_part_version_fails_closed_with_not_run`. Mutant now red (IndexError); test green (NOT RUN + BLOCKED). |
| R1-B: PR body stale | AC8's M2 row named a test that does not kill M2 at that head | This body is regenerated from `c4ba410`. Every mutant row names a test that kills it at this head; every count comes from a command run here. |

## Out of scope (unchanged)

- Declaring the `0.4` row. Until a ticket adds it, the gate blocks any
  0.4.x release and any merge that bumps the version to 0.4.x.
- Gates G1 to G6 (G6's self-skip wording is untouched).
- The assurance workflow itself, including its `workflow_dispatch`-only
  trigger.
- Branch protection and the required-check list.

## Companion artifacts

- `docs/assurance/release-gate-red-206.md` — amended in this change; its
  index entry in `docs/receipts-index.md` is updated in the same change.
- `docs/assurance/release-gate-red-563.md` — not amended. Its control
  asserts only that the receipt names its command, mutation and exit code;
  its transcripts are a dated record and are not re-run by the suite.
- This PR body: `.scratch/issue-735/pr-body.md`. The runner reads it off
  the branch and publishes it as the pull-request body; it is removed
  before the push and is not part of the final diff.

## Next action

Merge only after the required CI matrix is green on this branch. The next
ticket that wants a 0.4.x release must land a `0.4` row in
`ASSURANCE_REQUIREMENTS` before the version bump merges; this gate will
block the bump until that row exists.
