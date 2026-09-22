# Mutation receipt: the dependency-anchor exact-pin comparison (#557)

**Standard:** #341. **Build:** the pre-flight check
`scripts/check_dependency_anchor.py`, which refuses a dependency bump an
exact-pinned anchor cannot satisfy before the test matrix runs.
**Generator:** `scripts/mutation_receipt.py --select 557-anchor-pin`.
**Machine-readable record:** `docs/assurance/anchor-pin-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/check_dependency_anchor.py`
at `sha256:6b64376aa2a24d731d5a62346e1aa26c337e2f88be121b4cd2452aea186eac72`.
**Commit at generation:** `7c66da8` — informational only; currency is checked
against the digest above by `tests/test_mutation_receipt.py`.

Each case ran in its **own git worktree** at the recorded commit. Production
was never mutated in place; the generator asserts the production tree is
byte-unchanged afterwards, that the clean baseline passes first with nonzero
collection, that the mutant imports, and that the named test fails under it.

## What the comparison is

`check_exact_pin_constraint` is the only mechanism that produces a refusal:
for each candidate anchor it reads the anchor's published `requires_dist`
and returns the `==` pin when the proposed version is above it.  Disable it
and an unmergeable bump reads as a pass — exactly the #549 failure mode, in
which dependabot bumped `pydantic-core` 2.46.5 -> 2.49.0 above `pydantic`'s
`==2.46.5` pin and pip raised `ResolutionImpossible` at install time after
the whole grid had already run.

A test that monkeypatches `check_exact_pin_constraint` does not satisfy this
criterion: patching the function leaves the shipped file unchanged, so the
test passes against the exact defect the standard exists to catch.  This
receipt mutates the shipped file in a worktree instead.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-A1 | 557-anchor-pin | replace `if proposed > pinned:` with `if False:` so the comparison never returns a blocking `==` pin | **KILLED** | `tests/test_check_dependency_anchor.py::TestReproducesIssue549::test_reproduces` |

One hand-chosen mutant. **No mutation score is reported** — one case cannot
support one; the case is a named obligation, not a sample.

## Why the selection carries a control

The selection runs two node ids so the receipt shows, by name, which
assertion moved and which did not:

- **Kill** — `TestReproducesIssue549::test_reproduces`: the #549 fixture
  asserts the check refuses (`result == 1`).  Under the mutant the check
  passes (`result == 0`), so the assertion fails.  This is the named fixture
  that turns red, asserted by name rather than by exit code.
- **Control** — `TestPassesCoordinatedBump::test_passes`: a coordinated bump
  the anchor's `==` pin permits asserts the check passes (`result == 0`).
  It stays green under the mutant (disabling refusals cannot break a pass),
  which excludes an empty-cell kill: the mutant flipped the refusal path and
  left the pass path intact, so the kill is attributable to the comparison
  and not to a fixture that failed to collect.

The clean baseline collected two tests and passed; the mutant collected two
tests and the kill failed while the control stayed green; the production
tree was byte-unchanged afterwards.
