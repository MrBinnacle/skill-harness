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

## What changed

- Removed `_is_zero_three`. Replaced it with `ASSURANCE_REQUIREMENTS`, a
  declared table keyed by minor line. The `0.3` row reproduces the previous
  requirement exactly: issues 167–174, G8 required. `ASSURANCE_ISSUES` is
  folded into that row. No other row is added by this ticket; declaring the
  0.4 row is a separate decision, and until it lands the gate blocks any
  0.4.x release and any merge that bumps the version to 0.4.x. That block
  is the intended outcome.
- Unknown minor line: G7 and G8 each print
  `NOT RUN, no assurance requirement is declared for the X.Y line; add a
  row to ASSURANCE_REQUIREMENTS before releasing X.Y.x.`, each adds an
  error, and the gate prints `RELEASE GATE: BLOCKED` and exits 1. The
  coverage claim counts these as `not run`, never as skipped.
- Declared replacement: a row with an empty G7 list, or with
  `g8_required=False`, makes that gate print that it passed by declaration,
  naming the row. It never prints SKIPPED. A declared-pass gate counts as
  run.
- G8 on a tag ref reads `GITHUB_SHA`, queries
  `{_api_base()}/actions/runs?head_sha=<sha>`, and passes only if a run
  whose `path` is `.github/workflows/assurance.yml` has
  `status == "completed"` and `conclusion == "success"` at exactly that
  SHA. A green run at any other SHA does not count. Missing `GITHUB_SHA`
  on a tag ref is an error, not a skip. The failure message names the SHA
  and how to produce the run (`gh workflow run assurance.yml --ref v<version>`).
- G8 off a tag ref records itself as skipped with the reason "not a tag
  ref, no release candidate commit", the same model G6 already used. It
  does not fall back to any historical green run. The script no longer
  contains the string `actions/workflows/assurance.yml/runs`.
- API failures still fail closed: an unreadable issue or run list is an
  error.
- Amended `docs/assurance/release-gate-red-206.md` and its
  `docs/receipts-index.md` entry to the re-recorded transcript (one failure
  on the seeded 0.3.0 scenario, G8 skipped off a tag ref).

## Acceptance criteria

### AC1: Seeded tree at 0.4.0 with no 0.4 row prints NOT RUN for G7 and G8, prints RELEASE GATE: BLOCKED, exits 1

**Test:** `tests/test_release_gate_206.py::test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8`

**What I built:** `_minor_line()` + `ASSURANCE_REQUIREMENTS.get(line)` in
both assurance gates; a missing row appends to `not_run` and to `errors`
with the NOT RUN message the ticket specifies.

**Red before the fix** (test written first, run against the pre-#735 gate):

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G7: SKIPPED, version 0.4.0 is not on the 0.3 minor line.
G8: SKIPPED, version 0.4.0 is not on the 0.3 minor line.
RELEASE GATE: PASS (5 of 8 gates ran; skipped G6, G7, G8), public surfaces in lockstep at version 0.4.0.

E   assert 0 == 1
```

The gate passed a 0.4.0 tree with both assurance checks skipped. That is
the defect.

**Green after the fix:**

```text
G6: not a tag ref (local run) — tag-match check self-skips.
RELEASE GATE: BLOCKED (5 of 8 gates ran; skipped G6; not run G7, G8), 2 stale surface(s) at version 0.4.0:
  FAIL  G7: NOT RUN, no assurance requirement is declared for the 0.4 line; add a row to ASSURANCE_REQUIREMENTS before releasing 0.4.x.
  FAIL  G8: NOT RUN, no assurance requirement is declared for the 0.4 line; add a row to ASSURANCE_REQUIREMENTS before releasing 0.4.x.
```

Exit code 1. Companion test
`test_unknown_minor_line_blocks_even_a_patch_release` pins the same
fail-closed rule on 0.2.4 (previously "exempt" under `_is_zero_three`).

### AC2: A declared row with empty G7 list and G8 not required passes by declaration; neither line contains SKIPPED

**Test:** `tests/test_release_gate_206.py::test_declared_empty_requirement_passes_by_declaration`

**What I built:** In each gate, after the table lookup succeeds:
`if not row.issues` / `if not row.g8_required` print
`PASSED by declaration, ASSURANCE_REQUIREMENTS row 'X.Y' ...` and return
without touching the API or the skip ledger.

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

**Test:** `tests/test_release_gate_206.py::test_g8_fails_when_the_green_run_is_at_another_sha`

**What I built:** G8 on a tag ref queries
`actions/runs?head_sha={GITHUB_SHA}` and requires a run with
`path == ".github/workflows/assurance.yml"`, `head_sha == sha`,
`status == "completed"`, `conclusion == "success"`.

**Red before the fix:** G8 queried the workflow-filtered endpoint, which
the stub 404s (it was removed from the contract):

```text
E   AssertionError: G8: could not read assurance workflow runs: HTTP Error 404: Not Found
E   assert 'aaaa...aaaa' in 'G8: could not read assurance workflow runs: HTTP Error 404: Not Found'
```

The old endpoint string was still in the script; the new head_sha query
was not. The test greps for that as
`test_the_script_never_queries_the_workflow_filtered_endpoint`, which also
went red before the fix.

**Green after the fix:**

```text
FAIL  G8: no successful assurance.yml workflow run at the release candidate commit aaaa...aaaa; produce one with 'gh workflow run assurance.yml --ref v0.3.0'
```

The message names `<sha A>` and the dispatch command.

### AC4: A green run at the release-candidate SHA passes; same SHA with another workflow path or non-success conclusion fails

**Tests:**
- `test_g8_passes_when_the_green_run_is_at_the_release_candidate_sha`
- `test_g8_fails_when_the_run_at_the_sha_is_another_workflow`
- `test_g8_fails_when_the_run_at_the_sha_is_not_success[red-run]`
- `test_g8_fails_when_the_run_at_the_sha_is_not_success[no-conclusion]`

**Red before the fix:** the green-arm test 404'd on the removed endpoint
(same as AC3). The wrong-path and non-conclusion tests could not express
their cases: the stub had no `path`/`head_sha` fields and the gate had no
such checks.

**Green after the fix:** green arm exits 0 with no failures. Wrong-path
arm (`path=".github/workflows/ci.yml"` at sha A) fails naming sha A.
Non-success arms (`conclusion="failure"` and `conclusion=""` at sha A)
each fail naming sha A.

### AC5: On a tag ref with GITHUB_SHA unset, G8 fails

**Test:** `tests/test_release_gate_206.py::test_g8_fails_when_github_sha_is_unset_on_a_tag_ref`

**What I built:** After the tag-ref check, `if not sha:` appends
`G8: GITHUB_SHA is unset on a tag ref; the release candidate commit cannot
be identified` to errors. Not a skip.

**Red before the fix:** the old G8 never looked at GITHUB_SHA; it queried
the workflow-filtered endpoint and 404'd:

```text
E   AssertionError: ['G8: could not read assurance workflow runs: HTTP Error 404: Not Found']
```

**Green after the fix:** the G8 failure line contains
`GITHUB_SHA is unset`; `G8: SKIPPED` is not in stdout.

### AC6: Off a tag ref, G8 is skipped with the "no release candidate" reason; the script never queries the workflow-filtered endpoint

**Tests:**
- `tests/test_release_gate_206.py::test_g8_skips_off_a_tag_ref_with_no_release_candidate`
- `tests/test_release_gate_206.py::test_the_script_never_queries_the_workflow_filtered_endpoint`
- `tests/test_release_gate_real_tree.py::test_g8_self_skips_off_a_tag_ref_on_the_real_tree`

**What I built:** Off a tag ref, G8 calls
`_record_skip(skipped, "G8", "not a tag ref, no release candidate commit")`.
The old endpoint string is deleted from the script; the replacement is
`actions/runs?head_sha=`.

**Red before the fix:**

```text
E   AssertionError: scripts/release_gate.py queries the workflow-filtered endpoint again; #735 binds G8 to actions/runs?head_sha=
E     '/actions/workflows/assurance.yml/runs' is contained here:
E       pi_base()}/actions/workflows/assurance.yml/runs")
```

And the behavioural test:

```text
E   AssertionError: G6: not a tag ref (local run) — tag-match check self-skips.
E     RELEASE GATE: BLOCKED (7 of 8 gates ran; skipped G6), 1 stale surface(s) at version 0.3.0:
E       FAIL  G8: could not read assurance workflow runs: HTTP Error 404: Not Found
```

Old G8 off a tag ref either skipped silently by minor line or queried the
API. It never recorded "no release candidate".

**Green after the fix:** stdout contains
`G8: SKIPPED, not a tag ref, no release candidate commit.`; the stub's
request log contains no `/actions/runs` path; the script text contains no
`actions/workflows/assurance.yml/runs`. The real-tree control asserts the
same skip on the live tree at 0.3.0.

### AC7: At 0.3.0 the 0.3 row produces the same G7 issue reads (167 to 174) as before

**Test:** `tests/test_release_gate_206.py::test_zero_three_row_reads_the_same_assurance_issues_as_before`

**What I built:** The `0.3` row holds
`AssuranceRequirement(issues=tuple(range(167, 175)), g8_required=True)`.
G7 iterates `row.issues` and reads `{_api_base()}/issues/{n}` for each.

**Red before the fix:** the old code also read 167–174, so this test's
green-arm would have passed on issue reads — but it failed because the old
G8 queried the removed endpoint and 404'd on the stub:

```text
E   AssertionError: G6: not a tag ref (local run) — tag-match check self-skips.
E     RELEASE GATE: BLOCKED (7 of 8 gates ran; skipped G6), 1 stale surface(s) at version 0.3.0:
E       FAIL  G8: could not read assurance workflow runs: HTTP Error 404: Not Found
```

The request-set assertion is the external evidence for the range itself:
after the fix the stub sees exactly `/issues/167` … `/issues/174` and
nothing else on a non-tag ref. The real-tree control's
`_script_assurance_issues()` parses the `0.3` row out of the script text
rather than copying the numbers, so a drift reddens a required job with a
named mismatch.

### AC8: Each red shown run in this PR body; mutation campaign recorded

Red demonstrations are inlined above (fail-before / pass-after). Mutation
campaign after the fix, each mutant applied to a copy of
`scripts/release_gate.py` in a scratch path, the gate re-run, and the tree
restored:

| Mutant | Change | Killed by |
| --- | --- | --- |
| M1 unknown-line pass | Treat missing table row as `AssuranceRequirement((), False)` | `test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8` — expects NOT RUN + BLOCKED, gets PASS |
| M2 G8 any-sha | Drop the `head_sha == sha` check in G8 | `test_g8_fails_when_the_green_run_is_at_another_sha` — expects failure naming sha A, gets PASS |
| M3 G8 any-path | Drop the `path == ".github/workflows/assurance.yml"` check | `test_g8_fails_when_the_run_at_the_sha_is_another_workflow` — expects failure, gets PASS |
| M4 G8 any-conclusion | Drop the `conclusion == "success"` check | `test_g8_fails_when_the_run_at_the_sha_is_not_success[red-run]` — expects failure, gets PASS |
| M5 G8 missing-sha skip | Treat unset GITHUB_SHA as `_record_skip` | `test_g8_fails_when_github_sha_is_unset_on_a_tag_ref` — expects G8 error, sees only skip + PASS |
| M6 declared-pass skip | Empty G7 list / g8_required False → `_record_skip` instead of declaration pass | `test_declared_empty_requirement_passes_by_declaration` — expects PASSED by declaration, sees SKIPPED |
| M7 issue-range drift | `range(167, 175)` → `range(167, 176)` in the 0.3 row | `test_zero_three_row_reads_the_same_assurance_issues_as_before` — stub 404s #175, G7 fails closed with `could not read assurance issue #175` |

No mutant survived. The campaign is recorded here, not as a
`docs/assurance/` receipt: this ticket names no mutation-receipt
obligation, and `tests/test_receipts_index.py` gates that directory.

### AC9: Real-tree test still passes at 0.3.0; mypy --strict and the CI matrix

**Real-tree control:** `tests/test_release_gate_real_tree.py` passes on
the live tree. Gate output at the PR head:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
G8: SKIPPED, not a tag ref, no release candidate commit.
RELEASE GATE: PASS (6 of 8 gates ran; skipped G6, G8), public surfaces in lockstep at version 0.3.0.
```

`_script_assurance_issues()` now parses the `0.3` row of
`ASSURANCE_REQUIREMENTS` from the script text. The stub answers
`/issues/<n>` and `/actions/runs?head_sha=`, 404s the removed
workflow-filtered endpoint, and the request-set assertion expects exactly
the G7 issue reads. G8's skip is asserted by name.

**mypy --strict:** `mypy --strict scripts/release_gate.py` — clean.
Full scope `mypy --strict src/ tests/ scripts/drift_check.py
scripts/release_gate.py scripts/check_dependency_anchor.py` — one typing
error in the new test helper (`_dead_port` returned `Any` from
`getsockname()[1]`); fixed by asserting `isinstance(port, int)`. Re-run
clean on `scripts/release_gate.py` and on the full scope.

**ruff:** `ruff check src tests scripts` found one RUF059 in the new
`_dead_port` helper (unpacked `host` unused); fixed by naming it `_host`.
`ruff format --check src tests scripts` — clean after formatting the files
this change touched. Both commands re-run clean after the fix.

**drift-guard:** `python scripts/drift_check.py` — PASS, all 22 live
contracts hold. AC-4 still calls `gate_workflows_sha_pinned`, which this
change does not touch. The release-gate-related cases in
`tests/test_drift_check.py` (`-k "release_gate or ac4 or real_tree"`) —
10 passed.

**Receipts index:** `tests/test_receipts_index.py` — pass. The amended
`docs/assurance/release-gate-red-206.md` entry keeps both a Claims and a
Refuses-to-claim line. `tests/test_mypy_gate_scope_566.py` and
`tests/test_ruff_gate_scope_483.py` — pass; `scripts/release_gate.py`
remains inside both gate scopes.

**Release-gate seeded + real-tree modules:** 30 passed. The nine
acceptance-criterion tests in `tests/test_release_gate_206.py` were also
run individually and each passed. Re-demonstrated reds in this session:
with `scripts/release_gate.py` reverted to `origin/main`, those same nine
tests produced 6 failures for the right reasons (PASS-with-skips at
0.4.0, missing `ASSURANCE_REQUIREMENTS` table, workflow-filtered endpoint
still present, G8 404 on the removed endpoint); the fix was then restored
and the suite re-run green.

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

## Out of scope (unchanged)

- Declaring the `0.4` row. Until a ticket adds it, the gate blocks any
  0.4.x release and any merge that bumps the version to 0.4.x.
- Gates G1 to G6 (G6's self-skip wording is untouched).
- The assurance workflow itself, including its `workflow_dispatch`-only
  trigger.
- Branch protection and the required-check list.

## Companion artifacts

- `docs/assurance/release-gate-red-206.md` — amended in this change; its
  index entry in `docs/receipts-index.md` is updated in the same commit.
- `docs/assurance/release-gate-red-563.md` — not amended. Its control
  asserts only that the receipt names its command, mutation and exit code;
  its transcripts are a dated record and are not re-run by the suite.
- This PR body: `.scratch/issue-735/pr-body.md`. The runner reads it off
  the branch and publishes it as the pull-request body; it is removed
  before the push and is not part of the final diff.
- No mutation-receipt file under `docs/assurance/` was added: this ticket
  names no `scripts/mutation_receipt.py --select` obligation, and the
  campaign record lives in this body (AC8).

## Next action

Merge only after the required CI matrix is green on this branch. The next
ticket that wants a 0.4.x release must land a `0.4` row in
`ASSURANCE_REQUIREMENTS` before the version bump merges; this gate will
block the bump until that row exists.
