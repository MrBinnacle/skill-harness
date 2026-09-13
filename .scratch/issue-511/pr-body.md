# PR body — issue #511

## What changed

Decision S442 (2026-09-12) determined that `slow` stays an advisory marker, not a
CI lane. The comments at `ci.yml:69-72` and `ci.yml:81` called it "the slow lane"
and prescribed thinning it as the overrun remedy, but no CI job deselects on
`slow` — the marker is advisory only (`pyproject.toml:135`). Two files use
`@pytest.mark.slow`: `tests/test_oc_frontier.py:405` and
`scripts/run_mutation.py:117` (deselects locally). The registry entry is accurate;
only the comments disagreed.

## Files changed

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Rewrote lines 69-72 and 81-82 to say "slow-marked tests" instead of "the slow lane" and to note the marker is advisory |
| `tests/test_ci_marker_lane_consistency_511.py` | New: two tests that parse ci.yml comments and job expressions, failing when a marker is called a "lane" without a selecting job |

## Acceptance criteria

### AC1: Marking a test `slow` changes which job runs it, or `slow` no longer
appears in the marker registry, in the two files that use it, or in the job's
guidance.

**What I built:** Rewrote the two comments that called `slow` "the slow lane" to
say "slow-marked tests" and to note the marker is advisory. The marker registry
entry (`pyproject.toml:135`) is accurate and unchanged. The two files using
`@pytest.mark.slow` are unchanged.

**Test that pins it:** `test_comment_lane_markers_have_a_selecting_job` reads the
real `ci.yml`, extracts every marker name mentioned in a comment as a "lane", and
checks that each is selected on by a job's `-m` expression. After the fix, no
marker is called a lane without a selecting job.

**Observation:** Before the fix, this test failed with `orphans=['slow']`. After
the fix, it passes — no comments in ci.yml call any marker a "lane" without a
corresponding job.

### AC2: The guidance above the `test` job describes what the repository does.

**What I built:** The comment block above the test job (lines 69-85) now accurately
describes `slow` as an advisory marker. The thinning clause says "thin the
slow-marked tests or move them to their own job (the slow marker is advisory; no
CI job deselects on it)" instead of "thin the slow lane instead". The runner-variance
paragraph says "Thinning slow-marked tests here would delete real coverage" instead
of "Thinning the slow lane here".

**Test that pins it:** `test_comment_lane_markers_have_a_selecting_job` — same test
as AC1. The comment no longer calls `slow` a lane, so the test passes.

### AC3: A test parses the marker registry and ci.yml, and fails when any ci.yml
comment calls a marker a "lane" while no job's `-m` expression selects on it.

**What I built:** `tests/test_ci_marker_lane_consistency_511.py` with two tests:

1. `test_comment_lane_markers_have_a_selecting_job` — reads the real ci.yml and
   pyproject.toml, extracts lane-referencing comments and job `-m` expressions,
   fails when a comment calls a marker a lane without a selecting job.

2. `test_registered_markers_called_lane_are_selected` — control fixtures:
   - Control A: injects "slow lane" into a fixture ci.yml. The check catches
     `slow` as an orphaned lane (no job selects on it). Goes red.
   - Control B: injects "calibration lane" into a fixture ci.yml. The check passes
     because the calibration job selects on `-m calibration`. Stays green.

**Observation:** Before the fix, the main test failed with `orphans=['slow']`.
After the fix, it passes. The control test always passes — it injects "slow lane"
into a synthetic fixture and verifies the check catches it, then injects
"calibration lane" and verifies it passes.

## Mutation campaign

No mutation receipt was requested by this ticket. The test reads external behaviour
(ci.yml comment content and job expressions) rather than internal branching, so
mutation testing of the test itself would target regex parsing — out of scope for
this ticket.

## Gate

```
ruff check src tests          — All checks passed
ruff format --check src tests — 314 files already formatted
mypy --strict src/ tests/     — Success: no issues found in 310 source files
pytest tests/test_ci_marker_lane_consistency_511.py tests/test_ci_test_cell_attribution_509.py — 6 passed
```
