# Mutation receipt: mutant 3 of the superseding pre-registration, the one-per-world selection

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`
section 7, mutant 3, FROZEN 2026-09-05 (S414). **Ticket:** #443, under #360.
**Generator:** `scripts/mutation_receipt.py --select v2-section-7-mutant-3`.
**Machine-readable record:** `docs/assurance/ebmom-v2-one-per-world-mutation-receipt.json`.

This receipt covers **one** of the four mutants section 7 registers. Mutant 1 is
`docs/assurance/ebmom-v2-form-b-mutation-receipt.md`, mutant 2 is
`docs/assurance/ebmom-v2-per-path-split-mutation-receipt.md`, mutant 4 is
`docs/assurance/ebmom-v2-class2-mutation-receipt.md`; #444 collects all four in one place.

The case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place, and `PYTHONPATH` carries the worktree's `src/` and `scripts/` so the case is pinned to its
own sources.

## The mutant

Section 7, mutant 3, verbatim:

> One-per-world selection replaced by all decisions: killed by an assertion on a fixture world
> with two correlated false decisions, where the all-decision test rejects and the registered
> test does not.

One line in `scripts/ebmom_acceptance_matrix.py`, inside `ColumnTally.cell`:

```
-        trials, trial_false = clusters, sum(1 for value in selected if value == 1)
+        trials, trial_false = decisions, false_total  # mutant: all decisions
```

Both quantities are already computed on the clean tree, so the mutation is the smallest edit that
restores the retired test: the same exact binomial, at the same null and the same level, applied
to every decision rather than to one per world. Nothing else about the cell changes — `G`, `g`,
the rate and the world-block bound are all reported identically under both trees — so the kill
can only be about which trials the test counts.

## Result

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-V3 | v2 section 7, mutant 3 | the one-decision-per-world selection replaced by all decisions | **KILLED** | `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_3_two_correlated_false_decisions_do_not_reject` |

Measured at `16da76b`, Python 3.13.1, `scripts/ebmom_acceptance_matrix.py` at
`84ee23c6a71a2ec18215486e9578f1dbfda0d64cf1afbf2220c39f5fad72105c`. Clean baseline passed first
with 3 tests collected; the mutant collected the same 3 and exited 1. The production tree was
byte-unchanged afterwards.

## Which assertion moved, and which did not

| node | clean | mutant |
|---|---|---|
| `test_mutant_3_two_correlated_false_decisions_do_not_reject` (the kill) | pass | **FAIL** |
| `test_control_the_all_decision_test_rejects_on_the_same_fixture` (the control) | pass | pass |
| `test_the_fixture_is_one_world_carrying_two_decisions` (the guard) | pass | pass |

Only the kill assertion moved.

**The control rules out a fixture that cannot fire.** It applies the retired all-decision test to
the same cell explicitly and requires it to REJECT: two false of two, exact binomial
`p = 0.0025` against null `p = 0.05` at level 0.01. It computes that from the cell's own reported
counts rather than through the mutated line, so it rejects on the clean tree and on the mutant
alike. Without it, a kill that passed because the fixture was inert would be indistinguishable
from a kill that passed because the selection absorbed the correlation.

**The guard pins the fixture's shape.** One world, two decisions, both false: `decisions = 2`,
`false = 2`, `G = 1`, `g = 1`. A fixture spread over two worlds would give the two tests the same
answer and could not separate them; a fixture with one false decision would not reject under
either.

## The test measured here, stated exactly

The fixture is one world carrying two FAIL decisions on clauses `c0` and `c1`, both on clauses
whose true encoded mean is 0.80, above the 0.60 threshold, so both FAILs are false by
construction. The world is fed to the tally directly rather than drawn: what is under test is the
tally's arithmetic, and a drawn world would make the fixture a hostage to the generator.

Under the registered test of v2 section 2.1, that cell is **one trial**. One decision is selected
from the world by the seeded draw — SHA-256 over `<root>|<regime>|<world>|<row>`, first eight
bytes big-endian, feeding `random.Random`, choosing uniformly among the world's FAIL decisions
sorted by `clause_id` — and it is false, so the statistic is one of one and
`P(Binomial(1, 0.05) >= 1) = 0.05`, which does not reject at level 0.01.

Under the all-decision test it is **two trials**, both false, and
`P(Binomial(2, 0.05) >= 2) = 0.0025`, which rejects.

That gap is the whole reason section 2.1 discards all but one decision per world. Two false
decisions drawn from one world are not two independent observations: they share the world's mean
error. A test that counts them as two manufactures evidence, and on a cell of this size it
manufactures enough to convict.

## What this receipt does not claim

- It reports no mutation score, and one mutant is not a campaign. Three of section 7's four
  mutants are not measured here.
- It says nothing about any registered regime's cells. The fixture is synthetic and carries two
  decisions; it is a kill detector for the selection, not a measurement of the candidate.
- It does not claim the selection has the right power, only the right level. Section 2.1 states
  what is discarded and why the remaining power is judged sufficient; nothing here tests that.
- It does not claim the candidate passes the acceptance matrix. **No confirmatory run has been
  performed**, and v2 section 5 keeps this branch unmerged until one is.
