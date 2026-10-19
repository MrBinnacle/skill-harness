# Mutation receipt: mutant 4 of the superseding pre-registration, mechanism class 2 on the admitted path

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`
section 7, mutant 4, FROZEN 2026-09-05 (S414). **Ticket:** #442, under #360.
**Generator:** `scripts/mutation_receipt.py --select v2-section-7-mutant-4`.
**Machine-readable record:** `docs/assurance/ebmom-v2-class2-mutation-receipt.json`.

This receipt covers **one** of the four mutants section 7 registers. Mutant 1 is
`docs/assurance/ebmom-v2-form-b-mutation-receipt.md`; mutants 2 and 3 belong to the
acceptance-matrix build (#443); #444 collects all four in one place. A reader looking for section
7's full campaign should go there, not here.

The case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins the case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and the case would silently test another
tree's code.

## The mutant

Section 7, mutant 4, verbatim:

> A fourth, if section 4 freezes a mechanism: the mechanism removed (plug-in restored), killed by
> the admitted 6c cell in `low_heterogeneity` on the burned root.

One call in `src/skill_harness/aggregation/fit.py`:

```
-    posteriors = _build_shrunken_posteriors(
-        clauses, alpha_hat, beta_hat, tail_probabilities=tail_probabilities
-    )
+    posteriors = _build_shrunken_posteriors(clauses, alpha_hat, beta_hat)  # mutant: plug-in restored
```

`tail_probabilities` is an optional parameter, so dropping it is a behaviour change rather than a
syntax break: the mutant reaches the production call site and produces exactly the plug-in
posterior `Beta(alpha_hat + w_k, beta_hat + n_k - w_k)` that v2 section 4 replaced. The
admission-conditioned bootstrap still RUNS under the mutant and its result is discarded, which is
the sharper mutation of the two available: it removes the mechanism from the decision without
removing it from the code, so nothing but the decision path can account for the kill. The receipt
records that the mutant compiles and that the two source digests differ.

## Result

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-V4 | v2 section 7, mutant 4 | the admission-conditioned bootstrap removed from the admitted path, plug-in restored | **KILLED** | `tests/test_aggregation_fit_admitted_bootstrap.py::test_mutant_4_low_heterogeneity_admitted_false_fail_rate` |

Measured at `60a6548`, Python 3.13.1, `fit.py` at
`51884574aa8ee18438426a58287af9d18720a41a1b788c1ff9a168cbd51da866`. Clean baseline passed first
with 3 tests collected; the mutant collected the same 3 and exited 1. The production tree was
byte-unchanged afterwards.

## Which assertion moved, and which did not

The selection carries three node ids, not one, because a red exit code does not say what went
red. Under the mutant:

| node | clean | mutant |
|---|---|---|
| `test_mutant_4_low_heterogeneity_admitted_false_fail_rate` (the kill) | pass | **FAIL** |
| `test_control_plugin_admitted_path_rejects_on_the_same_worlds` (the control) | pass | pass |
| `test_the_four_named_worlds_reach_the_admitted_path` (the admission guard) | pass | pass |

Only the kill assertion moved. That matters for three reasons.

**The control rules out a vacuous kill.** The kill assertion is that the admitted-path false-FAIL
cell does not reject the registered exact binomial, and a cell with no decisions in it passes
that trivially. So the same four fits are also scored through the plug-in posterior the mutant
restores, and the control requires that scoring to REJECT: three false FAILs of four selected
decisions, exact binomial p = 4.8e-4 against null p = 0.05 at level 0.01. It rejects on the clean
tree and on the mutant. The condition is therefore reachable on these worlds, the test can fire,
and what stops it on the clean tree is the mechanism.

**The control also keeps the borrowed cell membership honest.** The claim that these four worlds
are the whole admitted 6c cell at R = 1000 comes from v2 section 0.5, not from this receipt (see
the limitation below). The control asserts the plug-in cell is exactly four worlds with exactly
three false, so if the code ever stopped producing that cell the control fails rather than the
kill passing quietly.

**The admission guard rules out the wrong mechanism.** A mutant that made these four worlds
REFUSED would empty the admitted cell and look like a kill for a reason that has nothing to do
with the mechanism. The guard asserts all four fits reach `ebmom_hierarchical`, and it stays green
under the mutant, so the emptied-cell explanation is excluded rather than assumed.

## The test measured here, stated exactly

Burned root `f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`, regime
`low_heterogeneity`, worlds 255, 316, 600 and 783 — the four v2 section 0.5 names, found by
`find_fail_worlds.py` over worlds 0 to 999. Per world, one FAIL decision is selected by the
seeded draw of v2 section 2.1 — SHA-256 over `<root>|<regime>|<world>|6c`, first 8 bytes
big-endian, feeding `random.Random`, choosing uniformly among that world's FAIL decisions sorted
by `clause_id` — and the selected decisions go to a one-sided exact binomial against null
`p = 0.05` at level 0.01. A cell with no decisions of its kind is NOT TESTABLE and is never
reported as passed.

Under the mechanism the cell is one false of one and does not reject. Under the plug-in it is
three false of four and rejects at p = 4.8e-4. World 255 carries the one true FAIL of the four
(true encoded mean 0.5396, below the 0.60 threshold); 316, 600 and 783 are false (0.6464, 0.6167,
0.6282).

## The limitation, stated rather than left to be discovered

**The cell's membership is borrowed, not re-derived.** This receipt re-derives the DECISIONS on
the four named worlds from production. It does not scan worlds 0 to 999 to confirm those four are
still the whole cell: doing that twice over, through a 999-replicate admission bootstrap on a
K = 200 regime, is hours of wall time and cannot sit in the gate. The control above is what makes
the borrowed membership falsifiable rather than assumed.

The consequence to hold onto: the built side of the cell is complete only if no OTHER world in
0 to 999 mints an admitted FAIL under the mechanism that the plug-in did not mint. The mechanism
widens tails on the worlds measured, which moves decisions out of FAIL rather than into it, but
that is a direction observed on four worlds and not a proof. The harness ticket's R = 1000 run is
what would settle it.

## What this receipt does not claim

- It reports no mutation score, and one mutant is not a campaign. Three of section 7's four
  mutants are not measured here at all.
- It does not claim the mechanism passes the acceptance matrix. **No confirmatory run has been
  performed**, and v2 section 5 keeps this branch unmerged until one is.
- It does not claim the mechanism is calibrated. The cell is four decisions, and v2 section 5 is
  explicit that a pass in a cell of two to four claims is weak evidence, because a lane that
  makes one claim or none passes too. This is a kill detector, not a demonstration.
- The burned root is used because that is the root the cell was registered on. Nothing measured
  on it is confirmatory, and it says nothing about the fresh root, which does not yet exist.
