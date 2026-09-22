# #557: Pre-flight check for exact-pinned anchor dependency bumps

## What this PR builds

A pre-flight check, `scripts/check_dependency_anchor.py`, that refuses a
dependency bump an exact-pinned anchor cannot satisfy, before the test
matrix runs. For each requirement the diff changes, it reads each candidate
anchor's published PyPI metadata (`info.requires_dist`) and refuses when an
anchor pins the changed package with `==` at a version below the proposed
one — the shape that makes pip raise `ResolutionImpossible` at install time.
The anchor relationship is discovered from published metadata, not from a
hand-maintained list of known pairs.

## Files changed

- `scripts/check_dependency_anchor.py` — the check.
- `tests/test_check_dependency_anchor.py` — 34 tests, one criterion per
  test where the criterion admits a unit test; AC8 is pinned by the
  mutation receipt below.
- `.github/workflows/ci.yml` — a dedicated pre-flight job that the `test`
  matrix must pass before it resolves the full constraints set.
- `scripts/mutation_receipt.py` — registers mutant M-A1 against the check.
- `docs/assurance/anchor-pin-mutation-receipt.{json,md}` — the mutation
  receipt and its prose companion.
- `docs/receipts-index.md` — the assurance index entry.

## Where the exact pins live

`pydantic==2.13.5` and `pydantic_core==2.46.5` are pinned in
`requirements-ci.txt`, not `pyproject.toml`. `pyproject.toml` carries only
open-ended `>=` bounds (`pydantic>=2.6`), so a diff against `pyproject.toml`
would never see the #549 bump. The CI step and the check both read
`requirements-ci.txt`. The #549 fixture uses the real pin from the ticket,
`pydantic-core==2.46.5`, not a synthesized range.

## Acceptance criteria

### AC1 — runs before the test matrix and fails the run early

Built: an isolated `dependency-anchor` job that installs only the check's
`packaging` dependency, fetches `origin/main` shallow, writes the
`requirements-ci.txt` diff to a temp file, and runs the check against it. The
matrix `test` job declares `needs: dependency-anchor`, so none of its four
cells reaches its constrained `Install` step when the check refuses.

Test: `TestRunsBeforeTheMatrix::test_matrix_needs_the_pre_flight_gate` reads
the real `ci.yml`, asserts the gate names `requirements-ci.txt`, and asserts
the matrix job needs that gate. A same-job step cannot satisfy the criterion:
the conflicting constraints fail its preceding install first.

Observed: a same-job check was unreachable on the #549 failure path because
the constrained install failed first in every matrix cell. The isolated gate
now finishes before those cells start. The subprocess test `test_script_runs`
confirms the script exits 0 on `--help`.

### AC2 — refuses a follower bump above an exact-pinned anchor's requirement

Built: `check_exact_pin_constraint` parses the anchor's `requires_dist` for
an `==` clause on the changed package and returns the blocking `==<version>`
when the proposed version is above it. `check_anchors` collects refusals
naming the anchor, the changed package, the pin, and the proposed version.
`main` prints the refusal to stderr and states that no published anchor
satisfies the proposed version, then exits 1.

Test: `TestRefusesBumpAboveExactPin::test_refuses` — `requirements-ci.txt`
with `pydantic==2.13.5` and `pydantic-core==2.46.5`, a diff bumping
`pydantic-core` to 2.48.0, and a mock returning pydantic's real
`pydantic-core==2.46.5` pin. Asserts exit 1 and that stderr names `pydantic`,
`==2.46.5`, `2.48.0`, and `No published anchor satisfies`.

Observed: with the comparison absent the check returns no refusals and exits
0; the assertion on exit 1 fails. With the comparison in place it exits 1
and the message carries all four terms.

### AC3 — passes a bump where the anchor's pin permits the new version

Built: the comparison refuses only when the proposed version is strictly
above the `==` pin, so a proposed version at the pin is permitted.

Test: `TestPassesCoordinatedBump::test_passes` — a coordinated bump where a
newer `pydantic==2.14.0` pins `pydantic-core==2.49.0` and the diff bumps both
together. The mock returns the `==2.49.0` pin; the proposed 2.49.0 is not
above it. Asserts exit 0.

Observed: the coordinated bump resolves under pip (the anchor already pins
the proposed), and the check exits 0. This is the same fixture the mutation
receipt uses as its control.

### AC4 — passes a bump of a package no anchor pins with `==`

Built: when no anchor's `requires_dist` carries an `==` clause on the
changed package below the proposed, `check_anchors` returns no refusals.

Test: `TestPassesUnpinnedPackage::test_passes` — bumps `click` 8.5.0 -> 8.6.0
with every anchor returning an empty `requires_dist`. Asserts exit 0.

Observed: no anchor constrains `click`, so no refusal is produced and the
check exits 0.

### AC5 — discovers the anchor relationship from published metadata

Built: `collect_anchor_metadata` fetches every package in the current
requirements as a candidate anchor at its declared version and reads its
`requires_dist`. No hardcoded pair list. Each candidate is read once (not once
per changed package), which minimises the surface on which a network failure
can refuse a clean run.

Test: `TestDiscoversAnchorFromMetadata::test_discovers` uses a fictitious
`fictitious-anchor==1.0.0` that pins `fictitious-follower==1.0.0` in its
mock metadata; no hand-list could supply the pair. Asserts exit 1.
`test_collect_caches_each_anchor_once` asserts each candidate is fetched
exactly once at its declared version.
`test_uses_the_anchor_version_declared_in_constraints` proves a newer anchor
release cannot stand in for the version this repository installs.

Observed: the check finds the fictitious pair from metadata alone and
refuses the bump to 2.0.0; the cache test records exactly one fetch per
candidate at its declared version.

### AC6 — network failure is a refusal with a distinct message, never a pass

Built: `fetch_pypi_metadata` wraps `URLError`, `OSError`, and `TimeoutError`
in `NetworkError` (a 404 returns `{}`, since a package PyPI does not know
cannot be an anchor). `main` catches `NetworkError`, prints
`REFUSE: network error reaching the index: ...` to stderr, and exits 1.

Test: `TestNetworkFailureIsRefusal::test_refuses_with_distinct_message` mocks
`fetch_pypi_metadata` to raise `NetworkError` on the first candidate. Asserts
exit 1 and that stderr contains `network error reaching the index`.

Observed: the first fetch raises, `collect_anchor_metadata` propagates it,
and `main` refuses with the distinct message. The check never reports a
clean result it could not establish.

### AC7 — a red demonstration reproduces #549

Built: `TestReproducesIssue549::test_reproduces` is the exact #549 scenario:
`pydantic-core` 2.46.5 -> 2.49.0 against `pydantic`'s `==2.46.5` pin. This is
the named fixture the mutation receipt kills.

Test: asserts exit 1.

Observed: the check refuses, naming pydantic, `==2.46.5`, and `2.49.0`. This
is the bump that burned thirteen checks on #549 before someone read the
install step.

### AC8 — a mutation control disables the exact-pin comparison and turns a named fixture red

Built: mutant M-A1 in `scripts/mutation_receipt.py` replaces
`if proposed > pinned:` with `if False:` in `check_exact_pin_constraint`, so
the comparison never returns a blocking `==` pin. The selection carries two
node ids: the kill `TestReproducesIssue549::test_reproduces` and the control
`TestPassesCoordinatedBump::test_passes`.

This is a real mutation receipt, not a monkeypatch. A test that monkeypatches
`check_exact_pin_constraint` leaves the shipped file unchanged, so it passes
against the exact defect the standard exists to catch; the prior run's
AC8 test did that and is removed. The receipt mutates the shipped file in its
own git worktree.

Test: `scripts/mutation_receipt.py --select 557-anchor-pin` generates
`docs/assurance/anchor-pin-mutation-receipt.json`. The receipt asserts the
clean baseline passes with nonzero collection, the mutant imports, the
source digests differ, and the production tree is byte-unchanged afterwards.
The kill is asserted by name — `killing_assertions` records
`tests/test_check_dependency_anchor.py::TestReproducesIssue549::test_reproduces`
— not by the overall exit code.

Observed: I ran the generator. Verdict: `M-A1 [557-anchor-pin] KILLED:
tests/test_check_dependency_anchor.py::TestReproducesIssue549::test_reproduces`.
Clean baseline collected two tests and passed; the mutant collected two,
the kill failed (`result == 1` became `result == 0`), and the control stayed
green. The control staying green excludes an empty-cell kill: the mutant
flipped the refusal path and left the pass path intact, so the kill is
attributable to the comparison and not to a fixture that failed to collect.

## Mutation campaign

| mutant | target | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-A1 | `scripts/check_dependency_anchor.py` | `if proposed > pinned:` -> `if False:` (the exact-pin comparison never returns a blocking pin) | KILLED | `tests/test_check_dependency_anchor.py::TestReproducesIssue549::test_reproduces` |

One hand-chosen mutant. No mutation score is reported; one case cannot
support one. The case is a named obligation, not a sample.

## Design notes the reader will check

The check reads each anchor's published metadata at the version declared in
`requirements-ci.txt` (`https://pypi.org/pypi/<anchor>/<version>/json`). A
newer release cannot stand in for that anchor: pip still resolves the declared
version until the dependency update changes it. The check is exact-pin only: a
range cap or lower bound is out of scope (the group coordinates ranges; the
defect is the `==` anchor with nothing new to bump to). The `pydantic-stack`
group is not changed.

## Gate results

```
ruff check src tests scripts          All checks passed
ruff format --check src tests scripts All files already formatted
mypy --strict src/ tests/             Success: no issues found in 358 source files
pytest tests/test_check_dependency_anchor.py -q   34 passed
scripts/mutation_receipt.py --select 557-anchor-pin  M-A1 KILLED (named fixture)
scripts/drift_check.py                DRIFT CHECK: PASS
```
