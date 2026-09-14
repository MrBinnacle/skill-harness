# RED demonstration: the real-tree release-gate control (#563 question 2)

`tests/test_release_gate_real_tree.py` asserts that `scripts/release_gate.py`
passes on the tree it lives in. A green assertion that the tree is clean cannot
tell a working gate from one that returns an empty failure list. This receipt
records the runs that prove the control can go red, so the green is evidence
rather than decoration.

Both demonstrations were established by running them, then restored. The tree
is unmodified.

Recorded 2026-09-14 on branch `agent/563-release-gate-real-tree`, against a
tree declaring version `0.3.0`.

## Demonstration 1: a stale surface in the real-tree path

This is the criterion #563 names: *a seeded stale surface in the real-tree
path proves the test can fail.* The README status banner was set to `v0.2.9`
while `pyproject.toml` declared `0.3.0`, which is the G3 lockstep failure.

Command:

```text
python scripts/release_gate.py
```

Output:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
RELEASE GATE: BLOCKED — 1 stale surface(s) at version 0.3.0:
  FAIL  G3: README.md status banner does not say 'Status: v0.3.0' (found 'Status: v0.2.9') - repository-internal check against pyproject.toml; it cannot observe the published package
```

Exit code: `1`

Both tests that read the verdict went red:

```text
FAILED tests/test_release_gate_real_tree.py::test_real_tree_passes_the_release_gate
FAILED tests/test_release_gate_real_tree.py::test_the_pass_line_names_the_version_this_tree_declares
```

## Demonstration 2: a gate that stops reading the tree

The first demonstration proves the control sees a stale surface. It does not
prove the control would notice a gate that stopped checking. So `main` was
short-circuited: the call to `gate_versions_lockstep` was replaced with a
constant, and the gate no longer read the tree's version.

Output:

```text
G6: not a tag ref (local run) — tag-match check self-skips.
RELEASE GATE: BLOCKED — 3 stale surface(s) at version 0.0.0-mutant:
  FAIL  G2: CHANGELOG.md has no rolled '## [0.0.0-mutant] - YYYY-MM-DD' section — roll [Unreleased] before tagging
  FAIL  G2: CHANGELOG.md is missing the '[0.0.0-mutant]: <compare-url>' link reference
  FAIL  G3: README.md status banner does not say 'Status: v0.0.0-mutant' (found 'Status: v0.3.0') - repository-internal check against pyproject.toml; it cannot observe the published package
```

Exit code: `1`

The assertion that failed, by name, in
`test_the_pass_line_names_the_version_this_tree_declares`:

```text
assert f"lockstep at version {version}." in result.stdout
```

That assertion exists for this mutant. It is why the module reads the version
from `pyproject.toml` and compares it to the PASS line, rather than matching
the PASS line alone.

Three tests went red, not two:

```text
FAILED tests/test_release_gate_real_tree.py::test_real_tree_passes_the_release_gate
FAILED tests/test_release_gate_real_tree.py::test_the_pass_line_names_the_version_this_tree_declares
FAILED tests/test_release_gate_real_tree.py::test_the_assurance_gates_asked_for_exactly_the_issues_the_script_names
```

The third is a second, independent detection of the same mutant. G7 and G8
apply only to the 0.3 line, so a constant of `0.0.0-mutant` made both
self-skip and the gate asked the stub for nothing at all. The request-set
assertion caught that silence.

## Demonstration 3: the mutant that survived

Reported as a measured limit, not as a pass.

`gate_workflows_sha_pinned` (G5) was neutered so its glob matched no file:

```text
for wf in sorted((root / ".github" / "workflows").glob("*.NEVERMATCHES")):
```

The gate still exited `0` with a PASS line, and both
`tests/test_release_gate_real_tree.py` and `tests/test_release_gate_206.py`
stayed green. `gate_workflows_sha_pinned` has no seeded mutant anywhere in the
suite, so nothing in the repository kills it.

This is a property of the seam, not a defect in this module. A control that
reads a verdict from outside detects a gate that reports the wrong answer. It
cannot detect a check that stops asking, because a check scanning nothing
finds nothing on a tree that is already clean. Killing that mutant needs a
seeded unpinned action in `tests/test_release_gate_206.py`, which is the
module that owns the seeded seam.

`#563` carries the measurement.

## Reproducing

Each demonstration is a one-line edit, a run, and a restore. The control that
keeps this receipt honest is
`test_red_receipt_names_the_command_the_mutation_and_the_exit_code`, which
asserts the receipt still names the command, the seeded mutation and the exit
code. It does not compare the transcripts to a live run, because the runs
above mutate the real tree and a test cannot do that safely under parallel
workers. Treat the transcripts as a dated record.
