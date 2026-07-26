# Why UNMEASURED is not a failure

When you run `skill-harness run evaluate-skill` and see `unmeasured: 17`, the natural
reading is that 17 things went wrong. That reading is incorrect. UNMEASURED is a
first-class verdict that means: the test that would discriminate between "this clause
is load-bearing" and "this clause is decoration" was not run, because the necessary
instrument does not exist in this version of the framework. Producing a number anyway
— by handing the question to an LLM judge and asking for an estimated score — would be
lying about what was measured.

The distinction the field habitually erases is between "we cannot prove it works" and
"it does not work." UNMEASURED preserves that distinction. A framework that collapses
it into a score is making a claim it cannot support.

## UNMEASURED sub-reasons

Each UNMEASURED clause carries a `sub_reason` that names the specific reason no
admissible evidence was produced. The sub-reasons are:

### `no_data`

No `oracle_verdicts` rows exist for this clause in the evidence database. This is the
aggregate-layer representation of a clause that was never reached by the runner — most
commonly because the runner's oracle gate fired before any subject-model calls were
made. See `tier2_uncalibrated` for the runner-layer cause.

Example: a skill with 17 domain-specific axes (e.g., `legal_disclaimer_presence`)
runs against a harness that has only five registered Tier-1 scorers (`verbosity`,
`hedge_index`, `structure_score`, `compliance_proxy`, `citation_presence_per_flag`).
None of the axes match. The
runner fires the BLOCKER-1 gate for all 17 clauses, writes zero verdict rows, and the
aggregator returns `no_data` for every clause.

### `inadmissible`

Verdict rows exist, but all of them are marked inadmissible. A verdict is inadmissible
when the Tier-2 judge that produced it either lacks a calibration record for the
relevant axis, or its calibration record fails the thresholds (position-swap agreement
< 0.7, position consistency < 0.8). The judge is an instrument; without a
calibration audit, its output is not admissible as evidence.

Example: a Tier-2 judge is invoked for an uncalibrated axis. The harness writes the
verdict rows with `admissibility_state = 'inadmissible'`. They are retained for audit
but excluded from aggregation. The clause has data, but no admissible data.

### `underpowered`

Admissible verdict rows exist, but the sample count is below `N_min`. At the default
thresholds (win_rate threshold = 0.60, confidence = 0.95), `N_min = 5`. A posterior
computed from fewer than 5 samples cannot be trusted to meet the `P(win_rate > 0.60)
>= 0.95` pass criterion.

Example: a run is interrupted after 3 samples per clause. The harness stores what it
has. On aggregation, the underpowered clauses return `UNMEASURED(underpowered)`. The
fix is to resume the run and collect more samples, not to lower the threshold.

### `falsifying_case_missing`

The clause is marked non-vacuous (`vacuity_flag = 'none'`) but has no frozen
falsifying case in the regression suite. A clause is not "tested" until at least one
falsifying case exists at the current `metric_library` version.

Example: the extractor produces a clause with a valid `falsifying_case` schema (the
input population and expected directional pair are specified), but no one has run the
ablation to the point of a definitive result and frozen a failing verdict. The clause
exists in the inventory but has never been through the full test cycle.

### `budget_exhausted`

The per-run budget cap (`--max-usd`) was reached before the clause accumulated enough
samples to reach a definitive verdict. The harness stops cleanly and reports what it
has.

Example: a run with `--max-usd 1.00` exhausts its budget mid-clause. The runner
writes the samples it collected, marks the run `completed_at`, and returns
`UNMEASURED(budget_exhausted)` for any clause that did not reach `N_min`.

### `falsifying_case_stale`

A frozen falsifying case exists, but it was frozen against a prior version of the
metric library. The current `metric_library` version has changed since the case was
frozen. The stale case is retained for audit but excluded from the current measurement.

Example: a scorer for `citation_presence_per_flag` is updated with a bug fix that
changes its output on existing test inputs. All frozen cases produced by the prior
scorer version are now stale. The clause returns `UNMEASURED(falsifying_case_stale)`
until new cases are frozen against the updated scorer version.

## Contrast with the field's pattern

The standard pattern in LLM evaluation is to produce a number regardless of whether
the instrument exists to measure the claimed axis. A pairwise preference judge asked
to evaluate `citation_presence_per_flag` will return a preference — it cannot refuse.
A G-Eval scalar scorer asked to rate "does this output correctly classify severity for
each flag" will return a number between 0 and 10. Those numbers feel like evidence.
They are not evidence that the clause is load-bearing; they are evidence that the
output looks plausible to the judge with this rubric.

Skill Harness is built around the refusal to conflate those two questions. The
`UNMEASURED` verdict is the concrete artifact of that refusal — a result that says
"the instrument for this measurement does not exist in this version of the framework,
and we will not pretend otherwise."

This is not a permanent condition. UNMEASURED is resolved by either registering a
Tier-1 mechanical scorer for the axis, or calibrating a Tier-2 judge for it. Both are
legitimate paths. Reporting a fabricated score is not.
