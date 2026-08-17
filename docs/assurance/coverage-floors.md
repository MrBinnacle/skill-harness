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

Applying that rule to the tables below flags **7 of the 20 modules** measured on
2026-08-12. Reading branch coverage alone would have flagged 3, and missed the 4
where coverage looks healthy and mutation does not.

Modules added to either package after that date are appended to the tables with
their own measurement date, and are counted in "Later rows" below rather than
folded into the 7-of-20 census. The census figure is a dated result; it is
quoted as such in `docs/ASSURANCE.md` and `docs/receipts-index.md` and is not
silently re-totalled when a row arrives.

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
| `src/skill_harness/aggregation/binding.py` | 14 | 0 | absent | 100.0% | BELOW 80% |
| `src/skill_harness/aggregation/confidence_sequence.py` | 54 | 17 | absent | 68.5% | BELOW 80% |
| `src/skill_harness/aggregation/engine.py` | 90 | 9 | 67.9% | 90.0% | BELOW 80% |
| `src/skill_harness/aggregation/errors.py` | 0 | 0 | 100% | n/a | no branches |
| `src/skill_harness/aggregation/fit.py` | 20 | 1 | 94.4% | 95.0% | OK |
| `src/skill_harness/aggregation/matched_bridge.py` | 32 | 2 | absent | 93.8% | BELOW 80% |
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

## Later rows, measured after the census

`aggregation/matched_bridge.py` was not in the tree on 2026-08-12. It landed on
2026-08-16 with #246, the E1 bridge that reads `matched_evidence()`, pairs the raw
arm-level records into the four-cell table, and routes it through Gate 2. It is in
the Aggregation table above because the attention rule applies to it, not because
it was part of the census: **the 7-of-20 figure and the 2,210/1,909 branch totals
are the 2026-08-12 result and do not include this row.** Counting the later row
leaves it 8 flagged of 21 today: #247 moved the branch figure over the floor, but
the attention rule reads both instruments, and mutation still reads `absent` for
this module — so the row stays flagged on the mutation arm of the rule until
#166's instrument measures it. Branch coverage alone does not clear a flag; that
is the point of pairing the columns.

Its figures - 32 branches, 2 uncovered, 93.8% - were re-measured on 2026-08-17
with coverage.py 7.15.2 and the flags in "How to reproduce", over
`tests/test_aggregation_matched_bridge.py`. That is a narrower selection than the
CI cell, and for this module it is the same number: nothing else in `src/` or
`tests/` calls `aggregate_matched_gate2` (the only other reference is the
package's re-export in `aggregation/__init__.py`), so no other test can reach an
arc in it. Re-measure under the full selection once a second caller exists.

The row read 10 branches, 3 uncovered, 70.0% and BELOW 80% when #246 landed it on
2026-08-16. #247 replaced the two evidence-shaped raises with typed refusals and
an exclusion ledger, and put tests on them, which is what moved the module over
the floor. The branch count tripled because the refusal and ledger branches are
new code, not because the old branches were removed. Review of #247 added two
more, both covered: the exclusion read resolves each id through
`audit_observation`, which answers from whichever of the three partitions holds
that id first, so the bridge now checks the returned phase stamp and refuses a
cross-partition id collision instead of pairing a calibration row into the
effect (INVARIANTS #7).

Mutation reads `absent` for the same reason `confidence_sequence.py` does: #166
predates the module. Two of the 21 modules are now unmeasured by the stronger
instrument, not one.

**The 2 arcs still uncovered are both unreachable, and neither is suppressed.**
The earlier draft of this row named three uncovered refusal guards - a pair
carrying two records for the same arm, a pair missing an arm, and an effect that
arrives without a Gate-2 decision - and said #247 would put a test on each. Two
of the three are gone: a duplicate arm and a missing arm are now ledgered
refusals, tested directly. The third raise survives at
`matched_bridge.py:321` and cannot be tested, because it cannot fire:
`gate2_decide` returns a non-optional `Gate2Decision`, and
`effect_from_matched_gate2` raises on a count disagreement rather than returning
an effect without one, so `effect.decision is None` is false on every path that
reaches it. It exists to satisfy the type checker, `EffectEstimate.decision`
being `Gate2Decision | None`. The second arc, the audit-miss exit in
`_all_matched_evidence` (`matched_bridge.py:192`), is unreachable for the same
class of reason: the observation id was read from `task_frontier_matched_obs` on
the same connection one statement earlier, so the by-id read cannot miss.

Neither carries a `# pragma: no cover`. Excluding them would lift the row to
100.0% by shrinking the denominator, and a percentage moved by the exclusion
list rather than by a test is the figure this report exists to refuse. **Decision
owed:** either delete the two dead guards and let the type checker be satisfied
another way, or keep them and register the exclusion here with this reasoning
attached. Until that is settled the row reports 93.8% and names why the
remainder is not reachable.

`aggregation/binding.py` was not in the tree on 2026-08-12 either. It landed on
2026-08-17 with #263, the E2 binding compiler. #264 added `verify_binding`, which
compares stored evidence with that pre-spend identity and returns every failed
or unavailable check in a typed ledger. Its figures - **14 branches, 0
uncovered, 100.0%** - were measured on 2026-08-17 with coverage.py 7.15.2 and the
flags in "How to reproduce", under the full ordinary CI selection. The verifier
accounts for all 14 branches. Tests exercise both whole-verification refusals,
all six evidence divergence classes, the five unverifiable axes, and both result
branches. Mutation reads `absent` because #166 predates the module. The attention
rule therefore flags this row despite complete branch reach; coverage does not
substitute for the missing mutation measurement. The census figures above remain
the 2026-08-12 result and do not include this row.

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
