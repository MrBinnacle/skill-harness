# Mutation receipt: mutant 1 of the superseding pre-registration, form B on the refused path

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md`
section 7, mutant 1, FROZEN 2026-09-05 (S414). **Ticket:** #441, under #360.
**Generator:** `scripts/mutation_receipt.py --select v2-section-7-mutant-1`.
**Machine-readable record:** `docs/assurance/ebmom-v2-form-b-mutation-receipt.json`.

This receipt covers **one** of the four mutants section 7 registers. Mutants 2 and 3 belong to
the acceptance-matrix build (#443) and mutant 4 to the admitted-path mechanism (#442); #444
collects all four in one place. A reader looking for section 7's full campaign should go there,
not here.

The case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins the case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and the case would silently test
another tree's code.

## The mutant

Section 7, mutant 1, verbatim:

> Pooling removed on the refused path (revert to unpooled): killed by the `tie_heavy_null`
> refused 6c assertion (251 of 251 false at R = 1000; any R above 40 suffices).

One line of `src/skill_harness/aggregation/fit.py`:

```
-        c_bound = _bounded_pooling_concentration(mu, v_bound)
+        c_bound = None  # mutant: pooling removed on the refused path
```

`c_bound = None` is the revert branch the specification already defines, so the mutant reaches
the production call site and produces exactly the unpooled `Beta(1 + w, 1 + n - w)` posterior
that v2 section 3 retired. It is a behaviour change, not a syntax break: the receipt records
that it compiles and that the two source digests differ.

## Result

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-V1 | v2 section 7, mutant 1 | pooling removed on the refused path (revert to unpooled) | **KILLED** | `tests/test_aggregation_fit_bounded_pooling.py::test_mutant_1_tie_heavy_null_refused_false_fail_rate` |

**REGENERATED at `60a6548` (#442).** The first generation measured `d39440d`, `fit.py` at
`0f5250afd95a92b5ad43865d48ddc4a6a0ae1ca692273fd8cf34c4cce266022f`, and that receipt went stale
the moment #442 changed `fit.py` on the admitted path -- which is the currency gate working, not
a defect. The mutant, the selection and the verdict are unchanged; the numbers below were
re-measured against the shipping tree. The obligation string became `v2-section-7-mutant-1` so
each mutant of section 7 stays regenerable on its own now that two of them target the same file;
`--select v2-section-7` still selects the whole section for the collecting receipt #444 owns.

Measured at `60a6548`, Python 3.13.1, `fit.py` at
`51884574aa8ee18438426a58287af9d18720a41a1b788c1ff9a168cbd51da866`. Clean baseline passed first
with 3 tests collected; the mutant collected the same 3 and exited 1. The production tree was
byte-unchanged afterwards.

## Which assertion moved, and which did not

The selection carries three node ids, not one, because a red exit code does not say what went
red. Under the mutant:

| node | clean | mutant |
|---|---|---|
| `test_mutant_1_tie_heavy_null_refused_false_fail_rate` (the kill) | pass | **FAIL** |
| `test_control_unpooled_refused_path_rejects_on_the_same_worlds` (the control) | pass | pass |
| `test_the_regime_reaches_the_refused_path_at_all` (the refusal guard) | pass | pass |

Only the kill assertion moved. That matters for two reasons.

**The control rules out a vacuous kill.** The kill assertion is that the refused-path false-FAIL
cell does not reject the registered exact binomial, and a cell with no decisions in it passes
that trivially. So the same worlds are also scored through the retired unpooled fallback, and the
control requires that scoring to REJECT. It rejects on the clean tree and on the mutant. The
condition is therefore reachable in this regime, the test can fire, and what stops it on the
clean tree is the pooling.

**The refusal guard rules out the wrong mechanism.** A mutant that made `tie_heavy_null` ADMITTED
would empty the refused cell and look like a kill for a reason that has nothing to do with
pooling. The guard asserts all 41 replicates are refused, and it stays green under the mutant, so
the emptied-cell explanation is excluded rather than assumed.

## Why the regime makes every FAIL false

`tie_heavy_null` is homogeneous at a decisive rate of 0.75 with a tie rate of 0.40, so every
clause has true encoded mean `0.40 * 0.5 + 0.60 * 0.75 = 0.65`, above the 0.60 threshold. A FAIL
on that regime is false by construction, with no estimation of truth required. The unpooled
fallback mints them; form B mints none.

## The test measured here, stated exactly

Root `SMOKE_NOT_CONFIRMATORY`, R = 41, the `tie_heavy_null` regime. Per world, one FAIL decision
is selected by the seeded draw of v2 section 2.1 — SHA-256 over `<root>|<regime>|<world>|6c`,
first 8 bytes big-endian, feeding `random.Random`, choosing uniformly among that world's FAIL
decisions sorted by `clause_id` — and the selected decisions go to a one-sided exact binomial
against null `p = 0.05` at level 0.01. A cell with no decisions of its kind is NOT TESTABLE and
is never reported as passed.

R = 41 rather than 1000 because section 7 states any R above 40 suffices, and the smoke root
rather than the burned confirmatory root because nothing in this receipt is a confirmatory
result.

## What this receipt does not claim

- It reports no mutation score, and one mutant is not a campaign. Three of section 7's four
  mutants are not measured here at all.
- It does not claim form B passes the acceptance matrix. **No confirmatory run has been
  performed**, and v2 section 5 keeps this branch unmerged until one is.
- The numbers quoted are R = 41 under a throwaway root seed, chosen to show the mutant is
  detectable. They are not the R = 1000 figures section 7 cites, and they are not evidence about
  the fresh root, which does not yet exist.
- It says nothing about the admitted path. That is #442's mutant 4, whose receipt is
  `docs/assurance/ebmom-v2-class2-mutation-receipt.md`.
