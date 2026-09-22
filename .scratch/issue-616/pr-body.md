# Evidence body — issue #616

## What was built

### Criterion 1: Script runs offline in under a minute and exits 0

`scripts/ablation_value_class.py` loads every SERS receipt on disk (current and superseded
directories under `docs/sers/receipts/`), extracts the screen measurement (p0) and value_class
from each, recomputes the verdict twice — once through `screen_verdict` as shipped, once with
every class replaced by `TRANSFORMATIVE_LIFT` — and prints a comparison table with a total.

The script is pure local I/O (JSON reads, no network, no model calls). It imports
`skill_harness.aggregation.verdict` for the recomputation and exits 0. On the repository's
7 receipts it completes in under 2 seconds.

**Test that pins it:** `tests/test_ablation_value_class.py::test_ablation_script_exits_zero`
writes a minimal receipt to a temp directory and runs the script as a subprocess, asserting exit
0 and the expected output string. The test would fail if the script crashed or exited non-zero.

### Criterion 2: Test is green and fails when the ablation is not applied

Two synthetic-receipt tests exercise the recomputation logic directly (no subprocess):

- `test_trap_discipline_above_bar_must_change`: builds a receipt with
  `value_class="trap-discipline"` and `p0=1.0` (above the 0.3 transformative ceiling).
  Asserts shipped = CANT_TELL_YET, ablated = CUT(subsumed), and shipped != ablated. This is
  the "must change" case: the value_class branch withholds CUT for trap-discipline; ablating
  it makes above-bar p0 produce CUT(subsumed) for every class.

- `test_transformative_lift_below_bar_must_not_change`: builds a receipt with
  `value_class="transformative-lift"` and `p0=0.0` (below ceiling). Asserts both shipped and
  ablated = CANT_TELL_YET and shipped == ablated. This is the "must not change" case: the
  value_class branch fires only above the ceiling, so below-bar receipts are unaffected.

**Observation before change:** The "must change" test requires `s_verdict != a_verdict`. Without
the ablation logic (or with the branch removed from `screen_verdict`), both calls return the
same verdict and the assertion fails. The "must not change" test requires `s_verdict == a_verdict`,
which holds regardless of whether the branch exists — the below-bar path is class-independent.

**Observation after change:** Both tests pass. The script correctly identifies 3 of 7 receipts
as recomputable, and all 3 change under ablation.

### Criterion 3: Amendment block in the preregistration doc

`docs/findings/class-hypothesis-preregistration.md` gains an Amendment 1 block (dated 2026-09-22)
appended at the end of the file. No registered text above the amendment line was edited.

The amendment states:
- The count: 3 of 3 recomputable verdicts changed (all screen-path receipts).
- The interpretation per the registered rule: non-zero means the question is live, the count
  measures how much rides on it, and classifying the currently unclassified live skills is the
  justified next step.
- The limitation: 4 paired-path receipts are not recomputable by this script; the paired path
  does not branch on `value_class` by construction, so the ablation is not expected to affect
  them.

## What was observed

The ablation run produced:

```
Receipt                                            Skill                               Shipped                        Ablated                        Changed
-----------------------------------------------------------------------------------------------------------------------------------------------------------------
double-ceiling-nogo-2026-07-09                     sqlite-expert                       CANT_TELL_YET                  CUT(subsumed)                  YES
reclass-append-only-evidence-design                append-only-evidence-design         CANT_TELL_YET                  CUT(subsumed)                  YES
reclass-git-pull-rebase-trap (superseded)          git-pull-rebase-trap                CANT_TELL_YET                  CUT(subsumed)                  YES

Total receipts:        7
Recomputable (screen): 3
Not recomputable:      4
Verdicts changed:      3
Verdicts unchanged:    0
```

All three screen-path receipts carry `value_class != transformative-lift` and `p0 > 0.3`. The
shipped code withholds CUT (wrong instrument) for each; the ablated code produces CUT(subsumed).
The paired-path receipts (gitpull-paired-n32, synthetic-control-keep, gitpull-paired-k8 x2)
lack a screen measurement and are not recomputable.

## Mutation campaign

No mutation campaign was applied. The ticket does not name a mutation receipt. The test suite
pins both outcomes (must-change and must-not-change) with synthetic fixtures, which provides the
same falsification pressure as a mutation campaign for this specific behaviour: a mutant that
removes the value_class branch from `screen_verdict` fails `test_trap_discipline_above_bar_must_change`;
a mutant that adds a value_class check to the below-bar path fails
`test_transformative_lift_below_bar_must_not_change`.

## Acceptance checklist

| Criterion | Status | Test |
|---|---|---|
| Script runs offline, under a minute, exits 0 | Met | `test_ablation_script_exits_zero` |
| Test is green and fails without ablation | Met | `test_trap_discipline_above_bar_must_change` (must-change), `test_transformative_lift_below_bar_must_not_change` (must-not-change) |
| Amendment block states count and interpretation | Met | Amendment 1 in `class-hypothesis-preregistration.md` |
