# Why UNMEASURED is not a failure

When you run `skill-harness run evaluate-skill` and see `unmeasured: 17`, the natural
reading is that 17 things went wrong. That reading is incorrect. UNMEASURED is a
recorded state, not a failure. It maps to the `CANT_TELL_YET` verdict and means the test that would discriminate between "this clause
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

No `oracle_verdicts` rows exist for this clause in the evidence database, and the
clause's axis *is* mechanically scoreable — an unscoreable axis returns
`mechanical_vacuous` first (see below), because `no_data` would falsely imply that
more sampling could resolve it. This is the aggregate-layer representation of a
scoreable clause that was never reached by the runner. See `tier2_uncalibrated`
for the runner-layer cause.

Example: a skill's clauses land on registered axes, but the run that would sample
this clause was never started — or ended before this clause's first sample was
made and stored. Zero verdict rows exist. The fix is to run (or resume) the
evaluation; the instrument exists, the evidence does not yet.

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

Admissible verdict rows exist, but the sample count is below `N_min = 8`
(`aggregation/status.py`). A posterior computed from fewer than 8 samples cannot be
trusted to meet the `P(win_rate > 0.60) >= 0.95` pass criterion.

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

### `fdr_correction_failed`

The raw (uncorrected) posterior crossed the pass threshold, but the skill-level
BH-FDR correction rejected this clause (`bh_fdr_pass = False`). Distinct from
`underpowered`: the sample count and the raw posterior are both fine — what failed
is the multiple-testing correction, not the sample size. Testing many clauses at
once inflates the chance that at least one crosses the threshold by luck; this
sub-reason names a clause that did not survive the correction that keeps the
family of results honest.

Example: a skill with 40 clauses runs to completion. One clause's raw posterior
reads `P(win_rate > 0.60) = 0.96`, but across 40 simultaneous tests the BH-FDR
gate rejects it. Reporting "not enough evidence yet" would be a false explanation
— there is enough evidence, and it does not survive correction.

### `mechanical_vacuous`

No registered Tier-1 mechanical scorer can see this clause's axis, so no amount of
further sampling could ever produce a mechanical measurement. This is Rule 0 —
checked before everything else, including `no_data` — because when no instrument
exists, "no data yet" is a false explanation: it implies more sampling would
resolve the clause, and it would not.

Scoreability is exact membership in the axis registry
(`oracles/tier1/axis_registry.py`) — never fuzzy, never case-insensitive, never a
Tier-2 judge. And it is recomputed from the current registry on every aggregation
read, never frozen onto the clause: registering a scorer for the axis resolves it
on the next read, with no re-extraction.

This is orthogonal to the write-time `vacuity_flag`: a clause can be constructibly
testable — carrying a structurally complete falsifying case — and still be
mechanically unscoreable today.

Example: a skill with 17 domain-specific axes (e.g., `legal_disclaimer_presence`)
runs against a harness that has only five registered Tier-1 scorers (`verbosity`,
`hedge_index`, `structure_score`, `compliance_proxy`,
`citation_presence_per_flag`). None of the 17 match. Every one of those clauses
returns `UNMEASURED(mechanical_vacuous)` — not `no_data` — naming the missing
instrument rather than implying missing effort.

## Contrast with the field's pattern

The standard pattern in LLM evaluation is to produce a number regardless of whether
the instrument exists to measure the claimed axis. A pairwise preference judge asked
to evaluate `citation_presence_per_flag` will return a preference — it cannot refuse.
A G-Eval scalar scorer asked to rate "does this output correctly classify severity for
each flag" will return a number between 0 and 10. Those numbers feel like evidence.
They are not evidence that the clause is load-bearing; they are evidence that the
output looks plausible to the judge with this rubric.

Skill Harness is built around the refusal to conflate those two questions. The
recorded `UNMEASURED` state is the concrete artifact of that refusal — a result that says
"the instrument for this measurement does not exist in this version of the framework,
and we will not pretend otherwise."

This is not a permanent condition. UNMEASURED is resolved by either registering a
Tier-1 mechanical scorer for the axis, or calibrating a Tier-2 judge for it. Both are
legitimate paths. Reporting a fabricated score is not.
