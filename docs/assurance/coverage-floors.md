# Branch-coverage floors (#171)

Branch coverage of the measurement path, measured with **coverage.py 7.15.2**
via `pytest-cov` under the ordinary CI test selection, paired in every row with
that module's mutation score from the #166 report.

**This report is a floor-finder. It is not a correctness result.** A branch is
counted the moment a test steps on it, whether or not any assertion looked at
what happened there. Coverage proves nothing about correctness: a module can sit
at 100% and still be wrong in every branch.

The pairing is structural on purpose. A caveat at the top of a page does not
travel with a number that gets quoted from the middle of it, so the qualifier is
in the row rather than in the preamble, and the operative rule below is stated as
a rule rather than as advice.

## The attention rule

A module needs attention when **either** figure is below 80%.

- **Both below** - the instruments agree; the module is genuinely thin.
- **Branch coverage at or above 80%, mutation below it** - they disagree, and
  **mutation decides.** Coverage is non-evidence for that module: the tests reach
  the branches and do not check what happens in them. Rank the work by mutation
  ascending.
- **Mutation absent** - the stronger instrument never measured this module.
  Coverage does not substitute for it, and the module is listed as unmeasured
  rather than as passing.

Applying that rule to the tables below flags **7 of the 20 modules**. Reading
branch coverage alone would have flagged 3, and missed the 4 where coverage looks
healthy and mutation does not.

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

`--cov-branch` is what makes these numbers branch coverage rather than statement
coverage; without it `--cov` reports statements only. Mutation scores are read
from `mutation-report.md` in this directory and are not re-derived here.

| Key | Value |
|-----|-------|
| coverage.py | 7.15.2 |
| pytest | 9.1.1 |
| Python | 3.13.1 |
| Test selection | `-m "not live and not calibration and not assurance"` (the CI cell) |
| Measured | 2026-08-12 |
| Floor | 80%, applied to both figures per the attention rule |
| Wall clock | 8m56s (host, NTFS) |

The selection is the ordinary CI lane, so the `live`, `calibration` and
`assurance` markers are excluded. These are floors under the coverage the PR gate
actually buys.

## Aggregation

| Module | Branches | Uncovered | Mutation #166 | Branch coverage | Floor |
|--------|---------:|----------:|--------------:|----------------:|-------|
| `src/skill_harness/aggregation/__init__.py` | 0 | 0 | not mutated | n/a | no branches |
| `src/skill_harness/aggregation/confidence_sequence.py` | 54 | 17 | absent | 68.5% | BELOW 80% |
| `src/skill_harness/aggregation/engine.py` | 90 | 9 | 67.9% | 90.0% | BELOW 80% |
| `src/skill_harness/aggregation/errors.py` | 0 | 0 | 100% | n/a | no branches |
| `src/skill_harness/aggregation/fit.py` | 20 | 1 | 94.4% | 95.0% | OK |
| `src/skill_harness/aggregation/matched_bridge.py` | 14 | 3 | absent | 78.6% | BELOW 80% |
| `src/skill_harness/aggregation/profile.py` | 22 | 1 | 98.0% | 95.5% | OK |
| `src/skill_harness/aggregation/report.py` | 0 | 0 | 97.6% | n/a | no branches |
| `src/skill_harness/aggregation/status.py` | 20 | 0 | 100% | 100.0% | OK |
| `src/skill_harness/aggregation/two_arm.py` | 14 | 0 | 97.7% | 100.0% | OK |
| `src/skill_harness/aggregation/value_class_registry.py` | 0 | 0 | 100% | n/a | no branches |
| `src/skill_harness/aggregation/verdict.py` | 34 | 3 | 71.5% | 91.2% | BELOW 80% |

## Ablation

| Module | Branches | Uncovered | Mutation #166 | Branch coverage | Floor |
|--------|---------:|----------:|--------------:|----------------:|-------|
| `src/skill_harness/ablation/__init__.py` | 0 | 0 | not mutated | n/a | no branches |
| `src/skill_harness/ablation/confound.py` | 28 | 1 | 92.9% | 96.4% | OK |
| `src/skill_harness/ablation/operator.py` | 6 | 3 | 52.0% | 50.0% | BELOW 80% |
| `src/skill_harness/ablation/reconciler.py` | 2 | 0 | 81.3% | 100.0% | OK |
| `src/skill_harness/ablation/render.py` | 6 | 1 | 65.9% | 83.3% | BELOW 80% |
| `src/skill_harness/ablation/runner.py` | 84 | 17 | 79.6% | 79.8% | BELOW 80% |
| `src/skill_harness/ablation/sizing.py` | 28 | 0 | 90.0% | 100.0% | OK |
| `src/skill_harness/ablation/stopping.py` | 16 | 0 | 82.9% | 100.0% | OK |
| `src/skill_harness/ablation/subject.py` | 32 | 3 | 62.4% | 90.6% | BELOW 80% |

The `Floor` column applies the attention rule, so a module can read `BELOW 80%`
on a healthy branch percentage when its mutation score is the one under the line.
That is the intended behaviour: the column answers "does this need attention",
not "is the coverage number large".

## The seven, and why each one is here

**The instruments agree on two.** `operator.py` at 50.0% branch and 52.0%
mutation, on 6 branches total, of which 3 are uncovered. Smallest branch count in
either package, so the percentage is volatile and the count is the honest figure.
`runner.py` sits at 79.8% and 79.6%, two tenths under on both, on the largest
module measured. At-floor rather than alarming.

**They disagree on four, and mutation decides all four.** `engine.py` (90.0%
branch, 67.9% mutation), `verdict.py` (91.2% / 71.5%), `subject.py` (90.6% /
62.4%) and `render.py` (83.3% / 65.9%). In every case the tests reach the
branches and do not check what happens inside them. **A coverage-only report
would have marked all four `OK`,** which is the failure mode this pairing exists
to prevent.

**One is unmeasured by the stronger instrument.** `confidence_sequence.py` has
the worst branch coverage here, 17 uncovered arcs of 54, and **no mutation score
at all** - #166 predates it, so it is absent from that report rather than scoring
badly in it. The module with the weakest coverage is the one the better
instrument has never looked at.

Its 17 uncovered arcs were read rather than characterised, and they are guard
clauses: invalid-parameter rejection (`alpha` outside `(0,1)`, `mu` at or beyond
the unit bounds, a non-positive cap), degenerate inputs (`n == 0`, `lo > hi`), and
the log-wealth overflow cap. These are error paths no test exercises. They are
not paths a wider test selection would reach - a calibration grid drives the
normal path at many rates and never passes `alpha = 1.5`.

## What a zero in the Branches column means

Five modules report 0 branches: both package `__init__` files, plus `errors`,
`report` and `value_class_registry` in aggregation. These are declarations,
constants and dataclasses with no conditional flow. Coverage.py reports 100%
branch coverage for a module with no branches; **this report prints `n/a`
instead**, because a percentage that is arithmetically true and informationally
empty is exactly the figure that gets quoted later. Their statement coverage is
real and lives in the ordinary coverage report.

## Measurement notes

- Two tests in `tests/test_skill_audit.py` could not run on the measuring host:
  they create symbolic links, and Windows refuses without Developer Mode
  (`WinError 1314`). They fail identically on `main` and pass in CI, where the
  runner holds the privilege. Neither touches a measured package.
- Totals across all 107 measured files: 2210 branches, 1909 covered.
- Randomized test order (`pytest-randomly`) was not used for this measurement.
  Order does not change which branches a full-suite run reaches, and a fixed
  order keeps the report reproducible against the command above.

### Correction, recorded rather than silently fixed

An earlier draft of this report stated that the uncovered mass in
`confidence_sequence.py` was "substantially an artifact" of the excluded
calibration lane. **That claim was not measured. It was inferred from the
module's name matching the lane's name, and it is false.** The `missing_branches`
data needed to check it was in the same JSON the table was generated from.

It was then measured, and the size of the error is worth recording. Re-running
with **both** excluded lanes included (`-m "not live"`, 2,120 tests, 26m37s):

| Module | CI selection | plus calibration + assurance | Delta |
|--------|-------------:|-----------------------------:|------:|
| `aggregation/confidence_sequence.py` | 68.5% | 70.4% | +1.9 |
| every other module in both packages | - | - | +0.0 |

The two excluded lanes account for **one uncovered arc out of seventeen** on the
one module they touch at all, and for nothing anywhere else in either package.
The remaining sixteen are the input-validation guards described above, which no
lane exercises. So the selection is not the explanation, and the earlier claim
was wrong about the mechanism and wrong about the magnitude by an order of
magnitude.

That comparison is a useful figure in its own right: **the `calibration` and
`assurance` lanes buy almost no additional branch reach over the measurement
path.** They exist to check numerical behaviour, not to cover branches, and this
report should not be read as an argument for folding them into the PR cell.

The claim is recorded here rather than deleted because a report about what the
tests do not check should not quietly drop the thing its own author did not
check.
