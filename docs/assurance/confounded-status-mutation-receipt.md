# Mutation receipt: reaching CONFOUNDED (#366)

**Standard:** #341. **Repair:** #366, filed from the item 6 detector (#348).
**Finding:** `docs/findings/confound-status-silent-understatement.md`.
**Generator:** `scripts/mutation_receipt.py --select 366`. **Machine-readable record:**
`docs/assurance/confounded-status-mutation-receipt.json`.
**Pinned by content, not by commit:** `src/skill_harness/aggregation/engine.py` at
`sha256:c64986c3f154e1b2b74e2fb37738633357dba5201ced47851100a89cef5f2176`.
**Commit at generation:** `e1bfe205ab20` — informational only; currency is checked against the
digest above by `tests/test_mutation_receipt.py`. **Python:** 3.13.1.

Each case runs in its own git worktree at a fixed commit. Production is never mutated in place.
`PYTHONPATH` pins every case to its own sources, because the editable install would otherwise
resolve `skill_harness` to the main repository and each case would silently test another tree's
code. All three cases resolved `skill_harness.aggregation.engine` inside their own worktree,
every clean baseline passed first with nonzero collection, and the production digest was
identical before and after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-C1 | reason read | stop reading the persisted `inadmissibility_reason` | **KILLED** | `test_confound_events_produce_confounded_status` |
| M-C2 | flag condition | fire CONFOUNDED only when admissible work DID survive | **KILLED** | `test_confound_events_produce_confounded_status` |
| M-C3 | reason read | count every inadmissible verdict except `scorer_error` as confounded | **KILLED** | `test_underpowered_discard_does_not_read_as_confounded` |

Three hand-chosen mutants. **No mutation score is reported**, because three cases cannot support
one; each case is a named obligation, not a sample.

## M-C3 survived on the first run, and that survival was the finding

On the first campaign M-C3 **SURVIVED**, killed by nothing in the suite. The cause was a fixture
monoculture: every fixture in the repository discards verdicts for confound, so an engine that
ignored the discard reason entirely was indistinguishable from one that read it — including the
engine #366 had just shipped.

The consequence was not cosmetic. An `underpowered` clause — the Null accumulator below the A47
floor — would have reported CONFOUNDED, sending a reader hunting a confound that was never
there. That is the same defect class as the understatement #366 replaced: a status asserting
more than the evidence supports.

The survivor was closed rather than banked. `test_underpowered_discard_does_not_read_as_confounded`
seeds `('inadmissible', 'underpowered')` while leaving the `confound_events` rows in place, so it
also pins that the engine reads the verdict's own reason rather than the mere presence of a
confound event elsewhere in the run. The re-run above records the kill, by that named test.

The #341 standard permits preserving a survivor as a finding. It was not preserved here because
the gap was in this ticket's own change, so closing it was finishing the work rather than
widening it.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the aggregation suite as a whole, or that any
historical report ever understated a confound — no production re-scan was run. It does not touch
the admissible VIEW's `affected_clause_id` question, which the finding records as open. It says
three specific defects are detected, in isolated worktrees, against baselines that passed first.

*Revisit if:* a fourth `inadmissibility_reason` is added to
`AblationRunner._snapshot_admissibility`. M-C3 discriminates `confounded` from `underpowered`
only; a new reason would need its own case, or the fixture monoculture that hid M-C3 the first
time reappears in a new shape.
