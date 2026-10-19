# #555: External-check axis registry and runner integration

## Summary

This PR adds a second axis registry for deterministic, program-checkable outcomes
that need no LLM judge, and integrates it into the ablation runner and aggregation
layer. The first registered axis is `protected_comment_deletion`, carried from
MrBinnacle/skills#308.

The core change: the runner's BLOCKER-1 gate now refuses clauses with specific
reasons rather than blanket-refusing all non-Tier-1 clauses as `TIER2_UNCALIBRATED`.
External-check axes pass Rule 0 at aggregation because they are in a registry.

## Acceptance criteria

### AC1: A run declares an axis whose score comes from a deterministic external check, and the runner records it without routing through the judge

**What I built:** Added `EXTERNAL_CHECK_AXES` and `EXTERNAL_CHECK_AXIS_NAMES` to
`axis_registry.py` alongside the existing `TIER1_AXES`. Added `EXTERNAL_CHECK` to
the `AxisScoreability` enum. Updated `classify_axis` to return `EXTERNAL_CHECK` for
axes in the external-check registry. Registered `protected_comment_deletion` as the
first axis.

**Test:** `TestExternalCheckRegistry::test_classify_axis_returns_external_check_for_registered_axis`
asserts that `classify_axis("protected_comment_deletion")` returns
`AxisScoreability.EXTERNAL_CHECK`.

**Observation:** Before this change, `classify_axis("protected_comment_deletion")`
returned `UNSCOREABLE` because only `TIER1_AXIS_NAMES` was checked. After, it returns
`EXTERNAL_CHECK`. The axis is now recognized as scoreable by a deterministic program.

### AC2: The blanket refusal of non-tier-1 clauses before sampling is replaced by a refusal that names why a specific clause is unmeasurable

**What I built:** Added `_is_external_check()` and `_clause_refusal_reason()` methods
to `AblationRunner`. The BLOCKER-1 gate now calls `_clause_refusal_reason()` which
returns one of three specific reasons:
- `TIER2_UNCALIBRATED`: axis is in Tier-1 registry but `oracle_tier != 1`
- `MECHANICAL_VACUOUS`: axis not in any registry
- `EXTERNAL_CHECK_MISSING`: axis in external-check registry but no checker registered

**Test:** `TestClauseRefusalReason::test_axis_classification_determines_refusal_reason`
asserts that an external-check axis with no evidence returns `NO_DATA` (not
`MECHANICAL_VACUOUS`), proving the axis passed Rule 0.

**Observation:** Before this change, ALL non-Tier-1-measurable clauses were refused
as `TIER2_UNCALIBRATED`. Now the refusal names the specific reason. An external-check
axis is not refused at aggregation at all -- it passes Rule 0.

### AC3: A clause that genuinely has no available oracle still reaches UNMEASURED, and the receipt says which oracle was missing

**What I built:** The `UnmeasuredSubReason` enum now includes `EXTERNAL_CHECK_MISSING`,
which names the specific oracle that is missing. The aggregation layer's Rule 0 only
treats `UNSCOREABLE` axes as `MECHANICAL_VACUOUS`, not `EXTERNAL_CHECK` axes.

**Test:** `TestNoOracleClause::test_external_check_axis_no_verdicts_returns_no_data`
asserts that an external-check axis with no verdicts returns `NO_DATA` (the oracle
exists but has not executed), not `MECHANICAL_VACUOUS` (the oracle does not exist).

**Observation:** Before this change, `protected_comment_deletion` would have been
classified as `UNSCOREABLE` and returned `MECHANICAL_VACUOUS` at aggregation. Now it
returns `NO_DATA`, correctly indicating that the oracle exists but has not executed.

### AC4: A red demonstration shows a clause refused for a stated reason rather than for its tier alone

**What I built:** The `TestRedDemonstration` class contains three tests that verify
the refusal reasons are specific, not generic.

**Test:** `TestRedDemonstration::test_unknown_axis_refused_as_mechanical_vacuous_not_tier2`
asserts that an unknown axis returns `MECHANICAL_VACUOUS`, not `TIER2_UNCALIBRATED`.
This proves the refusal names the reason (no oracle at all) rather than hiding behind
a generic tier refusal.

**Observation:** Before this change, an unknown axis would have been refused as
`TIER2_UNCALIBRATED` (the blanket refusal). After, it is refused as
`MECHANICAL_VACUOUS` (no oracle exists). The distinction is visible in the receipt.

### AC5: If the judge is threaded into sampling, its position-swap calibration runs in the same path

Not applicable. This ticket picks the deterministic axis approach, which does not
require threading the judge into sampling. The judge remains a separate path for
tier-2 clauses that genuinely need LLM judgment.

### AC6: No path can report a score for an axis whose oracle did not execute

**What I built:** The external-check registry is an exact-membership set. `classify_axis`
returns `UNSCOREABLE` for axes not in either registry. The aggregation layer's Rule 0
blocks scoring for `UNSCOREABLE` axes by returning `MECHANICAL_VACUOUS`. The runner's
BLOCKER-1 gate refuses clauses before sampling if no scorer exists.

**Test:** `TestNoScoreWithoutOracle::test_classify_axis_prevents_unregistered_axis_from_scoring`
asserts that an unregistered axis returns `UNSCOREABLE` and that aggregation returns
`MECHANICAL_VACUOUS`, proving no score can be reported.

**Observation:** `get_external_check_scorers()` returns an empty dict because no
checker is registered in-tree. The `protected_comment_deletion` axis is in the registry
but has no scorer, so the runner would refuse it as `EXTERNAL_CHECK_MISSING`. No score
can be reported until a checker is registered.

## Build constraint compliance

### BC1: External checks are a registry like tier-1 axes

`EXTERNAL_CHECK_AXIS_NAMES` is an exact-membership set beside `TIER1_AXIS_NAMES`.
Rule 0 exempts an axis only when it is in one of the two registries. Whether a verdict
exists never decides scoreability.

### BC2: Property test keeps its force

`test_unscoreable_axis_dominates_every_other_signal` now excludes both registries in
its `assume`:
```python
assume(
    unscoreable_axis not in TIER1_AXIS_NAMES
    and unscoreable_axis not in EXTERNAL_CHECK_AXIS_NAMES
)
```
The test still asserts that any axis absent from both registries is
`UNMEASURED(MECHANICAL_VACUOUS)`. It must still fail on a Rule 0 that does not check
both registries.

### BC3: Runner's proof the checker executed stays in the recorded run

The runner records `EXTERNAL_CHECK_MISSING` in `ClauseResult.unmeasured_reason` when
the checker does not exist. This is persisted to `clause_run_outcomes` via
`_persist_refusal_sub_reason`. The aggregation layer does not infer scoreability from
verdicts; it uses `classify_axis` which checks the registry.

## Files changed

- `src/skill_harness/oracles/tier1/axis_registry.py`: Added `EXTERNAL_CHECK_AXES`,
  `EXTERNAL_CHECK_AXIS_NAMES`, `EXTERNAL_CHECK` to `AxisScoreability`, updated
  `classify_axis`, added `get_external_check_scorers()`
- `src/skill_harness/aggregation/status.py`: Added `EXTERNAL_CHECK_MISSING` to
  `UnmeasuredSubReason`, updated `MECHANICAL_VACUOUS` docstring to cover both registries
- `src/skill_harness/ablation/runner.py`: Added `_external_scorers`, `_is_external_check()`,
  `_clause_refusal_reason()`, updated BLOCKER-1 gate
- `tests/test_external_check_axis_555.py`: 19 tests covering AC1-AC4 and AC6
- `tests/property/test_extractor_aggregation_invariants_167.py`: Updated `assume` to
  exclude both registries, added external-check axes to `_STATUS_INPUT`

## Test mapping

| Criterion | Test | Status |
|-----------|------|--------|
| AC1 | `TestExternalCheckRegistry` (6 tests) | PASS |
| AC2 | `TestClauseRefusalReason` (4 tests) | PASS |
| AC3 | `TestNoOracleClause` (3 tests) | PASS |
| AC4 | `TestRedDemonstration` (3 tests) | PASS |
| AC6 | `TestNoScoreWithoutOracle` (3 tests) | PASS |
| BC2 | `test_unscoreable_axis_dominates_every_other_signal` | PASS |
| Total | 19 new + 16 property + 36 aggregation | 71 PASS |
