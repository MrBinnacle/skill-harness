# Release gate bypasses: red before, green after (#835)

On 2026-10-28 the owner ratified one release gate for 0.5.0 and set five
acceptance requirements for this change. This record shows that the new tests
detect each bypass in the gate as it stood before the fix, and pass after it.

## What was run

The pre-fix gate is `scripts/release_gate.py` at `229d7b1`, the `main` commit
this branch starts from. `tests/test_release_gate_206.py` reads the environment
variable `RELEASE_GATE_SCRIPT_UNDER_TEST`, so the same tests can drive either
script.

```console
$ git show 229d7b1:scripts/release_gate.py > /tmp/release_gate_229d7b1.py
$ RELEASE_GATE_SCRIPT_UNDER_TEST=/tmp/release_gate_229d7b1.py PYTHONHASHSEED=0 \
    python -m pytest -q -n 4 tests/test_release_gate_206.py -k "bypass or protects or authorizes"
69 failed, 5 passed
$ PYTHONHASHSEED=0 python -m pytest -q -n 4 \
    tests/test_release_gate_206.py tests/test_release_gate_real_tree.py
116 passed
```

The host ran Python 3.13 on Windows. CI on the pull request is the record for
the other cells.

## The tests, by kind

Three name prefixes separate the kinds, so the claim each test makes can be
read from its name.

| Prefix | Meaning | Pre-fix | Post-fix |
|---|---|---|---|
| `test_bypass_` | Exposes a defect in the pre-fix gate | 68 fail | 68 pass |
| `test_authorizes_` | Positive control for the new `AUTHORIZED` verdict | 1 fails (the old gate printed `PASS`) | passes |
| `test_protects_` | Pins behavior the pre-fix gate already had | 5 pass | 5 pass |

## Each bypass and the tests that expose it

| Bypass in the pre-fix gate | Tests | Pre-fix result, observed |
|---|---|---|
| From 0.5 on, an empty issue list passed G7 "by declaration" | `test_bypass_empty_assurance_declarations_fail_from_zero_five[empty-issue-list-*]` (lines 0.5, 0.10, 1.0) | Exit 0, no G7 failure |
| From 0.5 on, `g8_required=False` passed G8 "by declaration" | `...[assurance-declared-unnecessary-*]` (lines 0.5, 0.10, 1.0) | Exit 0, no G8 failure |
| An older success masked a newer failed, cancelled or running assurance run at the same commit | `test_bypass_an_older_success_does_not_mask_a_newer_assurance_run` (3 cases); `test_bypass_a_failed_rerun_of_an_older_run_is_not_masked`; `test_bypass_equal_start_times_fall_to_the_higher_run_id` | `RELEASE GATE: PASS (8 of 8 gates ran)` |
| The drift check, structural bans, dependency audit and four calibration cells were never read | `test_bypass_each_required_ci_job_must_be_present_and_green` (7 jobs × missing, failure, skipped, cancelled, timed_out, neutral, in flight = 49 cases); `test_bypass_ci_evidence_at_another_commit_does_not_count`; `test_bypass_a_pending_newer_ci_run_blocks_authorization`; `test_bypass_jobs_are_not_combined_across_runs`; `test_bypass_a_truncated_job_list_fails_closed`; `test_bypass_no_ci_run_at_the_candidate_fails`; `test_bypass_a_required_job_listed_twice_fails` | `RELEASE GATE: PASS (8 of 8 gates ran)` in all 55 |
| A run off a tag printed an unqualified `RELEASE GATE: PASS` | `test_bypass_off_a_tag_the_gate_never_prints_an_unqualified_pass`; `test_bypass_a_strict_line_off_a_tag_skips_g9_and_is_preliminary` | `PASS` printed; G9 absent from the skipped set |

The pre-fix gate had no ninth check at all. So the 55 tests in the fourth row
fail before the fix for one reason, the missing check, and not for 55
separate defects. Each one pins a case that the new check must refuse.

## Mutation evidence for the ordering and the job count

Three rules in the new code fail open if they are weakened. Each was weakened
in a copy of the fixed script, and the bypass tests were run against that copy
through `RELEASE_GATE_SCRIPT_UNDER_TEST`.

| Weakened copy | Test that went red | Result |
|---|---|---|
| Order runs by start time only, without the run `id` | `test_bypass_equal_start_times_fall_to_the_higher_run_id` | 1 failed, 73 passed |
| Accept a required job found one or more times, not exactly once | `test_bypass_a_required_job_listed_twice_fails` | 1 failed, 73 passed |
| Order runs by `created_at`, which a re-run does not change | `test_bypass_a_failed_rerun_of_an_older_run_is_not_masked` | 1 failed, 73 passed |

GitHub keeps a run's `created_at` when the run is re-run and moves its
`run_started_at`. The gate therefore orders by `run_started_at`, and uses
`created_at` only when a run record has no `run_started_at`.

The ninth check's rename guard is `test_every_g9_required_job_name_exists_in_ci_yml`
in `tests/test_release_gate_real_tree.py`. It was shown red by renaming
`Drift check (locked contracts)` in a working copy of `ci.yml` (1 failed), then
green after the file was restored (1 passed).

## Behavior already protected before the fix

These tests pass on both scripts. They guard against a regression; they are
not evidence of a new defect.

- `test_protects_historical_lines_still_pass_by_declaration[0.1, 0.2]`: the
  compatibility boundary below 0.5.
- `test_protects_the_real_zero_four_row_is_unchanged_by_the_strict_policy`.
- `test_protects_a_newer_success_after_an_older_failure_passes`: a fixed re-run
  at the same commit counts.
- `test_protects_a_strict_tag_still_requires_the_assurance_run`.

The existing tests `test_g8_fails_when_the_run_at_the_sha_is_not_success`
(a lone failed, conclusion-less or running assurance run) and
`test_g8_fails_when_the_green_run_is_at_another_sha` also guard existing
behavior. They are not counted as new findings.

## What this record does not show

- That the live GitHub API returns these shapes. The tests use a local stand-in
  for the REST API. The first live G9 read happens when `release-authorize.yml`
  is dispatched on the 0.5.0 tag.
- That a maintainer cannot bypass the gate. A maintainer can still edit the
  workflows, or create a release without dispatching `release-authorize.yml`.
  The owner's release procedure, kept outside this repository, makes the
  authorize run a required step, and `publish.yml` runs
  the same gate again after publication.
- The squash-merge tree comparison. That control belongs to the owner's
  release procedure and its release record, not to this script.
