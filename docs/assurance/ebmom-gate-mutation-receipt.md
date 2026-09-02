# Mutation receipt: the #360 heterogeneity gate and peel

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment.md`
section 6. **Generator:** `scripts/ebmom_mutation_receipt.py`. **Machine-readable record:**
`docs/assurance/ebmom-gate-mutation-receipt.json`.

Each case runs in its **own git worktree** at a fixed commit. Production is never mutated in
place. `PYTHONPATH` pins every case to its own sources, because the editable install would
otherwise resolve `skill_harness` to the main repository and each case would silently test
another tree's code.

Per case the generator records and asserts: both worktree HEADs, the `module.__file__` actually
imported, the clean and mutant source digests, that those digests differ, that the clean
baseline **passes first** with **nonzero collection**, the **named** failing assertion under the
mutant, that the mutant **imports** (a stillborn mutant is not a kill), and that the production
tree is byte-unchanged afterwards.

## Results

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-A1 | A | revert the finite-K correction: `/(k-1)` to `/k` | **KILLED** | `test_aggregation_differential.py::TestFitSkillDifferential::test_1000_seeded_inputs_match_reference` |
| M-A2 | A | wrong peel denominator: `(n-1)*n` to `n*n` | **KILLED** | same assertion |
| M-A3 | A | tie-blind peel: ignore `sum_sq`, use the Bernoulli form | **SURVIVED** | none in the differential suite |
| M-B1 | B | remove the gate: always admit | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_marginal_heterogeneity_is_refused_not_fitted` |
| M-B2 | B | seed from a constant rather than from the data | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_seed_covers_sum_sq_not_just_w_and_n` |
| M-B3 | B | drop the `+1` finite-bootstrap correction | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_marginal_heterogeneity_is_refused_not_fitted` |
| M-B4 | B | hold each clause's tie count fixed at its observed value (the superseded null's tie treatment; redefined 2026-09-02) | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_tie_propensity_heterogeneity_is_admitted` |

**The survivor is preserved as a finding.** It is not folded into a score, and no mutation
score is reported: seven hand-chosen mutants cannot support one. Re-run 2026-09-02 on a clean
tree after the null was amended; `commit_under_test` and `production_tree_unchanged` are in the
JSON. M-B4 changed meaning with the amendment; both its definitions are recorded below.

## The mechanization caught a live regression on its first run

On the first mechanized run all four obligation-B cases returned `INVALID_BASELINE` rather than
a verdict. Their clean baseline was already red: production had renamed a provenance field from
`null_win_rate` to `null_encoded_mean` and the assertion still named the old one, because the
file was not re-run after the rename.

**Without the baseline-passes-first check, four kills would have been recorded against a test
that was already failing**, and a red baseline cannot distinguish a killed mutant from a test
that was broken before the mutation. The regression was fixed and the campaign re-run; the table
above is the re-run.

This is the same class of defect as the earlier in-place restoration failure, which restored
production through a path the interpreter could not see and reported a mutant's numbers as
"clean". Both are exit-code-shaped: something looked green that had never proved its predicate.

## Survivor M-A3: a tie-blind peel is invisible to the differential suite

The differential suite's 1,000 seeded inputs are tie-free, and on tie-free data `sum_sq == w`,
so the sufficient-statistic peel and the Bernoulli peel are algebraically identical. The
reference and production agree because on that data they are the same function. No quantity of
additional tie-free inputs would change this.

It is caught by the registered tie **signal** regime instead. Root seed
`SMOKE_NOT_CONFIRMATORY`, R=20, a development smoke configuration and not a confirmatory result:

| code | `tie_heavy_signal` relative bias of `latent_raw` | within the 10 percent bound | admission |
|---|---|---|---|
| clean | +0.0420 | yes | 1.00 |
| M-A3 | **-0.9281** | no | 0.25 |

## M-B4 after the 2026-09-02 amendment: the ties-fixed draw, killed by the fixture that pins the ruling

The M-B4 of the first campaign ("hold the null decisive rate common across clauses") mutated a
line the amended null no longer has. Chasing that survivor exposed the contract inconsistency the
amendment's open-questions note recorded, and the ruling of 2026-09-02 on #360 resolved it: the
lane's heterogeneity target is the encoded clause mean, so the null redraws ties from one pooled
categorical distribution rather than holding each clause's tie count fixed.

M-B4 is now the superseded null's tie treatment itself, as a one-line mutant of the amended draw:
`ties_b = _decompose(clause)[1]` in place of the pooled redraw. It is **KILLED** by
`tests/test_aggregation_fit.py::TestFitSkillEbmom::test_tie_propensity_heterogeneity_is_admitted`,
a deterministic fixture with a common decisive rate and a split tie propensity (ten clauses
`(wins, ties, losses) = (60, 20, 20)`, ten `(28, 60, 12)`). The amended null admits that world at
`p_boot = 0.001`; the ties-fixed mutant refuses it at `p_boot = 0.335`.

**Why the fixture and not the acceptance matrix.** The registered regimes cannot see this
mutant: `tie_heavy_null` is homogeneous under both the encoded and the decisive reading, and
`tie_heavy_signal` has a common tie rate, so a ties-fixed null with a common decisive rate is
calibrated on both (measured at R=200: 7 of 200 and, for the amended null, 5 of 200). The
surface that distinguishes the two nulls is a world with a common decisive rate and clause-varying
tie propensity, which the matrix does not contain. That is what the fixture is. Recorded here
because a future reader of the matrix alone would conclude the two nulls are interchangeable.

The first campaign's M-B4 result and the reasoning around it are preserved in the section below
as the record of how the inconsistency was found.

## The first campaign's M-B4: the null's estimand was not pinned by any test

M-B4 replaces the per-clause null rate with a common one. Nothing in the unit or differential
suites detects it. The acceptance matrix's calibration row is the surface that should, and at
R=40 it does not either: the mutant admits 0/40 where the clean code admits 16/40.

That comparison exposed a **contract inconsistency rather than a code defect**, recorded in full
in the amendment's open-questions note. Both survivors therefore point at the same place: the
tie-carrying surfaces are where this change is actually tested, and one of them is not yet
internally consistent.

## What this receipt does not claim

- It reports no mutation score, and the mutant set is not exhaustive. Seven mutants probe the
  seams the amendment freezes; they do not saturate the space.
- It does not claim the candidate passes the acceptance matrix. **No confirmatory run has been
  performed.** After the 2026-09-02 amendment the development smoke passes acceptance row 1 on
  `tie_heavy_null` (0 of 40, calibrated) and still returns `REJECTED` on the kill criterion in
  three regimes; the amendment's section 0 carries the numbers.
- The smoke numbers quoted for M-A3 exist only to show that mutant is detectable. They are
  R=20 under a throwaway root seed.
- It does not claim obligation B is fully covered. Four hand-chosen method-selection mutants
  are not a coverage measurement, and the first campaign's M-B4 survived every unit test until
  the fixture that now kills it was written.
