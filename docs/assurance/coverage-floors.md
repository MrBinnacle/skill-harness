# Branch-coverage floors (#171)

Branch coverage of the measurement path, measured with **coverage.py 7.15.2**
via `pytest-cov` under the ordinary CI test selection.

**This report is a floor-finder. It is not a correctness result.** A branch is
counted the moment a test steps on it, whether or not any assertion looked at
what happened there. Coverage proves nothing about correctness: a module can sit
at 100% and still be wrong in every branch, and the mutation report (#166) is the
instrument that speaks to whether the tests actually kill defects. Read the two
together, and prefer the mutation score wherever they disagree about a module's
real state.

## How to reproduce

```bash
pip install -c requirements-ci.txt -e ".[dev]"

PYTHONHASHSEED=0 pytest -q \
  -m "not live and not calibration and not assurance" \
  --cov=src/skill_harness \
  --cov-branch \
  --cov-report=json:coverage-branch.json \
  --cov-report=term
```

`--cov-branch` is what makes the numbers below branch coverage rather than
statement coverage; without it `--cov` reports statements only.

| Key | Value |
|-----|-------|
| coverage.py | 7.15.2 |
| pytest | 9.1.1 |
| Python | 3.13.1 |
| Test selection | `-m "not live and not calibration and not assurance"` (the CI cell) |
| Measured | 2026-08-12 |
| Floor | 80% branch coverage; below that a module is flagged |
| Wall clock | 8m56s (host, NTFS) |

The selection is the ordinary CI lane, so the `live`, `calibration` and
`assurance` markers are excluded. Branches reachable only from those lanes are
counted as uncovered here. That is the honest reading: these are floors under
the coverage the PR gate actually buys, not under every test in the repository.

## Aggregation

| Module | Statements | Branches | Branch coverage | Floor |
|--------|-----------:|---------:|----------------:|-------|
| `src/skill_harness/aggregation/__init__.py` | 5 | 0 | 100.0% | OK |
| `src/skill_harness/aggregation/confidence_sequence.py` | 163 | 54 | 68.5% | BELOW 80% |
| `src/skill_harness/aggregation/engine.py` | 267 | 90 | 90.0% | OK |
| `src/skill_harness/aggregation/errors.py` | 21 | 0 | 100.0% | OK |
| `src/skill_harness/aggregation/fit.py` | 105 | 20 | 95.0% | OK |
| `src/skill_harness/aggregation/profile.py` | 93 | 22 | 95.5% | OK |
| `src/skill_harness/aggregation/report.py` | 75 | 0 | 100.0% | OK |
| `src/skill_harness/aggregation/status.py` | 58 | 20 | 100.0% | OK |
| `src/skill_harness/aggregation/two_arm.py` | 56 | 14 | 100.0% | OK |
| `src/skill_harness/aggregation/value_class_registry.py` | 6 | 0 | 100.0% | OK |
| `src/skill_harness/aggregation/verdict.py` | 93 | 34 | 91.2% | OK |

## Ablation

| Module | Statements | Branches | Branch coverage | Floor |
|--------|-----------:|---------:|----------------:|-------|
| `src/skill_harness/ablation/__init__.py` | 0 | 0 | 100.0% | OK |
| `src/skill_harness/ablation/confound.py` | 98 | 28 | 96.4% | OK |
| `src/skill_harness/ablation/operator.py` | 41 | 6 | 50.0% | BELOW 80% |
| `src/skill_harness/ablation/reconciler.py` | 30 | 2 | 100.0% | OK |
| `src/skill_harness/ablation/render.py` | 42 | 6 | 83.3% | OK |
| `src/skill_harness/ablation/runner.py` | 413 | 84 | 79.8% | BELOW 80% |
| `src/skill_harness/ablation/sizing.py` | 62 | 28 | 100.0% | OK |
| `src/skill_harness/ablation/stopping.py` | 80 | 16 | 100.0% | OK |
| `src/skill_harness/ablation/subject.py` | 147 | 32 | 90.6% | OK |

## Modules under the floor

Three modules sit below 80%. None is a gate; each is a place to look.

**`operator.py` (50.0%, 6 branches).** The smallest branch count in either
package, so a single uncovered pair moves the number by 17 points. Low absolute
risk, and the cheapest of the three to lift. Note that #166 scored this module
52.0% on mutation, its worst in ablation, so here the two instruments agree.

**`confidence_sequence.py` (68.5%, 54 branches).** The largest genuine gap. This
is the module the confidence-sequence stopping rule depends on, and the branches
are real numeric edges rather than error plumbing. The uncovered mass is
concentrated in paths that only the `calibration` lane exercises, which the CI
selection excludes by design (a dense CS grid does not fit a 15m PR cell). The
floor is therefore partly an artifact of the selection rather than an absence of
tests, and the honest fix is to report the calibration lane's contribution
separately rather than to fold it into this number.

**`runner.py` (79.8%, 84 branches).** Two tenths of a point under the floor, on
the largest module measured. Flagged because the rule is the rule; treat it as
at-floor rather than as a finding.

## What a zero in the Branches column means

Four modules report 0 branches: the two package `__init__` files, plus `errors`
and `report` in aggregation. These are declarations, constants and dataclasses
with no conditional flow. Coverage.py reports 100% branch coverage for a module
with no branches, which is arithmetically true and carries no information. Do
not read those rows as evidence of anything.

## Measurement notes

- Two tests in `tests/test_skill_audit.py` could not run on the measuring host:
  they create symbolic links, and Windows refuses without Developer Mode
  (`WinError 1314`). They fail identically on `main`, so they are a property of
  the host and not of this branch. Neither touches the aggregation or ablation
  packages, so the numbers above are unaffected.
- Totals across all 107 measured files: 2210 branches, 1909 covered.
- Randomized test order (`pytest-randomly`) was not used for this measurement.
  Order does not change which branches a full-suite run reaches, and a fixed
  order keeps the report reproducible against the command printed above.
