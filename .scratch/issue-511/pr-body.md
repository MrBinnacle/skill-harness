# PR body — issue #511

## What changed

Decision S442 (2026-09-12) kept `slow` as an advisory marker. The comments above
the `test` job called it "the slow lane" and prescribed thinning it as the overrun
remedy, but no CI job selects or deselects on `slow`. A maintainer who followed
the file's own instruction saw no change.

Review found the first implement still offered "thin the slow-marked tests or move
them to their own job" as the >15 remedy — a rename of "lane", not the S442 stop
on offering `slow` as a CI remedy. The comments now name local deselection only
and point overrun thinning at measured dominators (#510). The check parses the
marker registry and both workflow files; controls cover `slow` (red),
`calibration` (green), and `assurance` (green).

## Files changed

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Guidance names `slow` as local-only advisory; overrun remedy is measure-then-thin (#510), not the slow marker |
| `tests/test_ci_marker_lane_consistency_511.py` | Parses pyproject markers + ci.yml/assurance.yml `-m` expressions; orphans fail; three controls |

## Acceptance criteria

### AC1: Marking a test `slow` changes which job runs it, or `slow` no longer
appears as a lane/remedy in the job's guidance (S442: keep marker, rewrite guidance).

**What shipped:** Comments no longer call `slow` a lane or prescribe it as a CI
remedy. Registry and `@pytest.mark.slow` sites unchanged.

**Test:** `test_comment_lane_markers_have_a_selecting_job` — no registered marker
is called a lane without a positively selecting job. `test_registered_markers_called_lane_are_selected`
asserts `slow` stays registered and is not selected by any job.

### AC2: The guidance above the `test` job describes what the repository does.

**What shipped:** Guidance states local deselection via `-m 'not slow'`, that no
CI job selects or deselects on `slow`, and that overrun thinning follows measured
dominators (#510).

**Test:** same pair — the live file stays green; injecting `slow lane` goes red.

### AC3 (S442): A test parses the marker registry and ci.yml, and fails when any
ci.yml comment calls a marker a "lane" while no job's `-m` expression selects on it.
Controls: `slow lane` red; `calibration lane` and `assurance lane` green.

**What shipped:** Registry read from `pyproject.toml`. Positive `-m` selection from
`ci.yml` and `assurance.yml` (bare and quoted). Three controls as specified.
