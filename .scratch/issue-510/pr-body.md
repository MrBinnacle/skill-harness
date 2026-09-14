# #510: Test cell completes inside its 25-minute budget

## What happened

Run 34713831470 at head `9a00e62b` on `agent/issue-360` stopped all four Test cells
with the annotation "The job has exceeded the maximum execution time of 25m0s".
That run was the first time the code on `agent/issue-360` was gated at all, because
PR #506 widened the `pull_request` trigger that PR #492 found scoped to `main`.

## The cause

Coverage instrumentation. Measured on the dominant fixture
(`tests/test_aggregation_fit_ebmom_recovery.py`) with `pytest -p no:randomly`:

| Arm | Wall clock | Reported coverage |
|---|---|---|
| `--cov`, default core | 664s | 10298 statements, 8825 missed, 14% |
| `--no-cov` | 142s | none collected |
| `--cov` with `COVERAGE_CORE=sysmon` | 152s | 10298 statements, 8825 missed, 14% |

Instrumentation costs 522 seconds. `COVERAGE_CORE=sysmon` recovers 512 of them (98%),
and reported coverage is **identical** rather than merely comparable.

## The fix

`COVERAGE_CORE: "sysmon"` was added to the Test job's existing `env:` block in
`ci.yml` on PR #506, which merged at `681824d`. The variable lives at `ci.yml:111`,
alongside `--durations=25 --durations-min=1.0` at the pytest step.

## Acceptance criterion 1: per-test durations

`--durations=25 --durations-min=1.0` runs on this branch and the cells of run
34764117821 reached session end, so the table exists in that run's job logs.

**Still owed on the ticket body:** quote the slowest rows from one Test job of
run 34764117821 onto issue #510. This review seat cannot download those logs
(API returns 403 without admin rights). Cell-level durations from that run are
below; the per-test table is the missing quote.

| Cell | Duration |
|---|---|
| windows-latest py3.12 | 12m40s |
| ubuntu-latest py3.13 | 12m55s |
| ubuntu-latest py3.12 | 14m20s |
| windows-latest py3.13 | 20m00s |

The previous run on this branch killed all four at exactly 25m00s.

Pre-fix per-test evidence already on the ticket (run 34724342821 on `main`,
windows py3.13) named the dominant suite before sysmon landed:

```
223.89s call     tests/test_oc_frontier.py::test_full_grid_assembly_every_row_no_shortlist
57.50s call     tests/test_aggregation_calibration.py::test_coverage_within_binomial_tolerance_per_grid_point[small]
57.30s call     tests/test_aggregation_calibration.py::test_calibration_harness_is_deterministic
```

That table satisfies the "name the tests that dominate" half on `main` hardware.
The post-sysmon table from 34764117821 is what criterion 1 still asks to paste.

## Acceptance criterion 2: cell finishes inside 25 minutes

`timeout-minutes: 25` is unchanged at `ci.yml:88`. All four cells in run
34764117821 completed successfully, with the slowest (windows py3.13) at 20m00s —
5 minutes of headroom.

## Acceptance criterion 3: coverage is no smaller

The three-arm measurement above shows identical coverage: 10298 statements,
8825 missed, 14% in both the default-core and sysmon arms. The sysmon core
uses CPython's sys.monitoring API instead of the default tracer, which avoids
the per-line callback cost without changing what coverage.py collects.

## Acceptance criterion 4: second commit reproduces the result

This branch's control commit is a second commit after the fix on `main`. The
Test cells on the PR for this branch are the reproduction run; record all four
durations on the ticket once they finish.

## Non-negotiable: control for the fix

`tests/test_ci_coverage_core_sysmon_510.py` is the control. It reads the
real `ci.yml` and fails when `COVERAGE_CORE` is absent from the Test job's
env block. Four tests:

1. `test_coverage_core_is_set_in_test_job_env` — the variable exists.
2. `test_coverage_core_value_is_sysmon` — the value is `"sysmon"`.
3. `test_coverage_core_lives_inside_existing_env_block` — exactly one
   job-level `env:` key, and COVERAGE_CORE sits in that block with
   `PYTHONHASHSEED` and `SKILL_HARNESS_REQUIRE_VALE` (a second `env:` key
   would silently replace the first).
4. `test_coverage_core_sysmon_reaches_coverage` — subprocess proof that
   `COVERAGE_CORE=sysmon` selects `SysMonitor`, and that reported coverage
   on a module with a deliberate miss matches the default core (criterion 3).

## What remains

- Quote the per-test durations table from run 34764117821 onto issue #510
  (criterion 1; needs log access).
- Record the four cell durations from this PR's Test cells (criterion 4).

Do not thin a test, do not move a suite to its own lane, and do not raise the
ceiling.

## Revisit if

- The windows py3.13 cell lands near 20 minutes rather than near 13 on
  subsequent runs. The 20m00s cell has the least headroom, and a bad runner
  draw could still straddle the ceiling.
- `sysmon` reports smaller coverage on any cell. It did not on the measured
  file, but that was one file on one cell.
- Branch coverage is ever enabled for this cell. These runs use statement
  coverage only; there is no `[tool.coverage]` table and no `.coveragerc`
  in the repository.
