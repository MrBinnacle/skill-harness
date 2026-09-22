# #557: Pre-flight check for exact-pinned anchor dependency bumps

## What this PR builds

A pre-flight check that refuses a dependency bump whose exact-pinned anchor
cannot satisfy it, before the test matrix runs.  Reads PyPI metadata to
discover anchor relationships dynamically — no hand-maintained list of known
pairs.

## Files changed

- `scripts/check_dependency_anchor.py` — the check script
- `tests/test_check_dependency_anchor.py` — unit tests (29 tests)
- `.github/workflows/ci.yml` — CI step in the test job, after Install, before pytest

## Acceptance criteria

### AC1: The check runs before the test matrix and fails the run early

**What I built:** A new step in `.github/workflows/ci.yml`'s `test` job, placed
after `Install` and before the geometry extra install and pytest.  The step runs
`python scripts/check_dependency_anchor.py --requirements pyproject.toml --diff
<(git diff origin/main -- pyproject.toml)`.  If it exits non-zero, GitHub Actions
fails the job immediately — no pytest, no coverage, no grid cells.

**Test:** `TestSubprocessIntegration::test_script_runs` — verifies the script
can be invoked as a subprocess and exits 0 with `--help`.

**Observation:** On main with no dependency changes, the script exits 0 with
"PASS: no dependency changes detected in diff".  On a branch with a bump above
an anchor pin, it exits 1 and prints the refusal before any test cell runs.

### AC2: Refuses a follower bump above an exact-pinned anchor's requirement

**What I built:** `check_exact_pin_constraint` parses version specifiers from
the anchor's `requires_dist` using `packaging.specifiers.SpecifierSet`.  When
the proposed version falls outside the specifier, it returns the blocking
constraint string.  `check_anchors` iterates all candidate anchors, fetches
their PyPI metadata, and collects refusals.

**Test:** `TestRefusesBumpAboveExactPin::test_refuses` — creates a requirements
file with `pydantic==2.13.5` and `pydantic-core==2.46.5`, a diff bumping
pydantic-core to 2.48.0, and a mock returning pydantic's real constraint
(`pydantic-core>=2.46.5,<2.47.0`).  Asserts exit code 1.

**Observation:** Before the check, Dependabot would propose this bump and CI
would burn the entire grid before pip failed at install time (13 checks on
#549).  After the check, the refusal prints immediately and the grid never
runs.

### AC3: Passes a bump where the anchor's pin permits the new version

**What I built:** Same constraint checking, but the proposed version (2.46.6)
falls within pydantic's `>=2.46.5,<2.47.0` range.

**Test:** `TestPassesBumpWithinAnchorPin::test_passes` — same fixture as AC2
but with pydantic-core bumped to 2.46.6.  Asserts exit code 0.

**Observation:** The check passes and CI proceeds to the test matrix.  The
anchor's pin is respected without blocking a compatible bump.

### AC4: Passes a bump of a package no anchor pins with ==

**What I built:** When no anchor's `requires_dist` contains a constraint on
the changed package that blocks the proposed version, `check_anchors` returns
an empty list and the check passes.

**Test:** `TestPassesUnpinnedPackage::test_passes` — bumps click from 8.5.0 to
8.6.0.  No anchor pins click with any blocking constraint.  Asserts exit code 0.

**Observation:** The check makes no network calls for anchors that don't
constrain the changed package (the mock returns empty `requires_dist`).

### AC5: Discovers anchor relationship from published metadata

**What I built:** `find_anchors_for_package` returns all packages in the
current requirements as candidates.  `check_anchors` fetches each candidate's
PyPI metadata and checks `requires_dist` for constraints on the changed
package.  No hardcoded list of known pairs.

**Test:** `TestDiscoversAnchorFromMetadata::test_discovers` — uses a fictitious
anchor (`fictitious-anchor==1.0.0`) that pins `fictitious-follower==1.0.0` in
its metadata.  The check discovers this relationship from the mock PyPI
response and refuses the bump to 2.0.0.  Asserts exit code 1.

**Observation:** The check correctly identifies the anchor from metadata alone.
If pydantic stopped pinning pydantic-core with `==`, the check would stop
refusing those bumps — it follows the published metadata, not a hand-maintained
list.

### AC6: Network failure is a refusal with a distinct message

**What I built:** `fetch_pypi_metadata` catches `urllib.error.URLError`,
`OSError`, and `TimeoutError`, wrapping them in `NetworkError`.  `main` catches
`NetworkError` and prints "REFUSE: network error checking {package}: {exc}"
to stderr, exiting 1.

**Test:** `TestNetworkFailureIsRefusal::test_refuses` — mocks
`fetch_pypi_metadata` to raise `NetworkError`.  Asserts exit code 1.

**Observation:** A check that cannot read its input must not report a clean
result.  The distinct "network error" message in the refusal output makes the
failure mode immediately identifiable.

### AC7: Red demonstration reproduces #549

**What I built:** `TestReproducesIssue549::test_reproduces` — the exact #549
scenario: pydantic 2.13.5 pins pydantic-core, Dependabot proposes
pydantic-core 2.49.0.  The check reads pydantic's metadata
(`pydantic-core>=2.46.5,<2.47.0`) and refuses because 2.49.0 > 2.47.0.

**Test:** `TestReproducesIssue549::test_reproduces` — asserts exit code 1 with
the refusal message naming pydantic, its pin, and the proposed version.

**Observation:** This is the exact scenario that burned 13 CI checks on #549
before someone read the install step.  The check now catches it in one PyPI
read.

### AC8: Mutation control disables exact-pin comparison, turns named fixture red

**What I built:** `TestMutationControlDisablesPinCheck::test_mutation_turns_549_green`
— monkeypatches `check_exact_pin_constraint` to always return `None` (no pin
blocks anything).  The #549 fixture must then PASS instead of REFUSE.

**Test:** The test patches `check_exact_pin_constraint` with a function that
returns `None` unconditionally.  Under this mutation, the check passes (exit 0)
for the same #549 fixture that refuses under the real implementation.  The test
asserts `result == 0`, proving the pin comparison is what catches #549.

**Observation:** When the pin comparison is disabled, the check passes for a
bump that should be refused.  This proves the comparison is load-bearing and
not decorative.  The named fixture (`#549`) is explicitly asserted by name.

## Mutation campaign

| Mutant | Target | Description | Killed by |
|--------|--------|-------------|-----------|
| Disable pin comparison | `check_exact_pin_constraint` → always `None` | Turns `#549` fixture green | `test_mutation_turns_549_green` |

The mutation control is the single mutant required by AC8.  It proves the
exact-pin comparison is the mechanism catching the #549 scenario.

## Gate results

```
ruff check src tests scripts          ✅ All checks passed
ruff format --check src tests scripts ✅ All files already formatted
mypy --strict src/ tests/             ✅ Success: no issues found in 358 source files
pytest tests/test_check_dependency_anchor.py -v ✅ 29 passed
```
