# Mutation receipt: mutant 2 of the superseding pre-registration, the per-path split

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`
section 7, mutant 2, FROZEN 2026-09-05 (S414). **Ticket:** #443, under #360.
**Generator:** `scripts/mutation_receipt.py --select v2-section-7-mutant-2`.
**Machine-readable record:** `docs/assurance/ebmom-v2-per-path-split-mutation-receipt.json`.

This receipt covers **one** of the four mutants section 7 registers. Mutant 1 is
`docs/assurance/ebmom-v2-form-b-mutation-receipt.md`, mutant 3 is
`docs/assurance/ebmom-v2-one-per-world-mutation-receipt.md`, mutant 4 is
`docs/assurance/ebmom-v2-class2-mutation-receipt.md`; #444 collects all four in one place. A
reader looking for section 7's full campaign should go there, not here.

The case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins the case to its own sources. This is the first case in the registry
whose target lives under `scripts/`, which is not a package, so the worktree's `scripts/`
directory joins its `src/` on that path; without it the compile and isolation assertions could
not import the mutated module and the case would have been recorded as `INVALID_ISOLATION`
rather than measured.

## The mutant

Section 7, mutant 2, verbatim:

> Per-path split removed (rows pooled): killed by an assertion that the refused-path cell in
> `low_heterogeneity` is reported separately with its own `G`, and that a pooled-only tally
> cannot produce it.

One line in `scripts/ebmom_acceptance_matrix.py`, inside `ColumnTally.add`:

```
-        lane = path
+        lane = "admitted"  # mutant: per-path split removed, rows pooled
```

The tally still receives the path and still files every decision; what it stops doing is filing
them on the lane they belong to. That is the sharper of the two available mutations: it removes
the split from the report without removing the path from the code, so nothing but the split can
account for the kill.

## Result

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-V2 | v2 section 7, mutant 2 | the per-path split removed, every decision tallied on one lane | **KILLED** | `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G` |

Measured at `9a81e83`, Python 3.13.1, `scripts/ebmom_acceptance_matrix.py` at
`84ee23c6a71a2ec18215486e9578f1dbfda0d64cf1afbf2220c39f5fad72105c`. Clean baseline passed first
with 3 tests collected; the mutant collected the same 3 and exited 1. The production tree was
byte-unchanged afterwards.

## Which assertion moved, and which did not

| node | clean | mutant |
|---|---|---|
| `test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G` (the kill) | pass | **FAIL** |
| `test_control_the_pooled_tally_keeps_every_decision_either_way` (the control) | pass | pass |
| `test_the_fixture_worlds_reach_both_paths` (the guard) | pass | pass |

Only the kill assertion moved.

**The control rules out a kill that fires because the fixture emptied.** Pooling loses the path
and never the decisions, so the pooled cell is the same cell under both trees and the control
stays green. Had the mutant deleted the fixture's decisions instead of pooling them, the kill
would have gone red for a reason that has nothing to do with the split, and the control would
have gone red with it.

**The guard rules out the wrong mechanism.** It re-derives each fixture world's path from
`fit_skill` rather than from the tally, and requires the two worlds to reach different paths. A
mutant that sent both down one path would empty a cell and look like a kill for a reason
unrelated to the report's structure.

**The first control was wrong and is recorded here rather than quietly replaced.** It asserted
the pooled cell was strictly larger than either path's. Under this mutant the pooled cell *is*
the admitted cell, so that control went red beside the kill and the generator reported two
killing assertions. A control that dies with the mutant controls nothing. The half of it worth
keeping — that a pooled-only tally cannot produce the refused cell, which is the second clause of
the specification's wording — moved into the kill assertion, where it belongs.

## The fixture, stated exactly

Burned root `f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`, regime
`low_heterogeneity`, worlds 0 and 1. World 0 reaches the refused path and world 1 the admitted
one, which is what makes the pair discriminating; both are re-derived from `fit_skill` by the
guard rather than quoted. Row 5c: the refused cell reports `G = 1` with its own decision count,
the admitted cell reports `G = 1` with a different one, and the pooled cell reports `G = 2` with
their sum.

Two worlds rather than a thousand. What the kill asserts is that the refused cell is REPORTED
separately with its own cluster count, which one world of each kind settles. The rate on such a
cell is not a result and is not asserted.

## What this receipt does not claim

- It reports no mutation score, and one mutant is not a campaign. Three of section 7's four
  mutants are not measured here.
- It says nothing about any cell's rate, verdict or kill status. It is a receipt about the
  report's structure, not about the candidate.
- It does not claim the candidate passes the acceptance matrix. **No confirmatory run has been
  performed**, and v2 section 5 keeps this branch unmerged until one is.
- The burned root is used because that is the root the fixture's worlds were drawn on. Nothing
  measured on it is confirmatory, and it says nothing about the fresh root, which does not yet
  exist.
