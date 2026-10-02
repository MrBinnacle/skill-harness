# Mutation receipt: the Stage 1A regime simulator (#685 part a, ticket #695)

**Standard:** #341. **Repair:** #695, the part (a) rebuild of #685 after three builds
failed on the whole ticket. **Generator:** `scripts/mutation_receipt.py --select 695-stage1a`.
**Machine-readable record:** `docs/assurance/stage1a-regime-685-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:1a295c27a442116a29bcbbbdb64d44e72f45ab4cba8567ed4157ae881c3ea205`.
**Commit at generation:** `a3a26ac4f814e08e9a20de975b3ec3fb46bd2954` — informational only; currency is checked against the
digest above by `tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Regenerated after #712 changed the simulator; the twelve mutants and their
killing assertions are unchanged and were re-run against the committed tree.

Each case runs in its own git worktree at a fixed commit. Production is never mutated in place.
`PYTHONPATH` pins every case to its own sources; `scripts/screens/419` joins `src` and `scripts`
so the screen modules import by bare name. All twelve cases resolved
`simulate_stage1a_regime_685` inside their own worktree, every clean baseline passed first with
nonzero collection, every mutant imported, and the production digest was identical before and
after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-1 | 695-stage1a-exit | exit-on-calibration-failure returns 0 anyway | **KILLED** | `test_main_exits_non_zero_when_calibration_fails` |
| M-S1A-2 | 695-stage1a-direct-online-scale | direct F-N grid bound compared unscaled | **KILLED** | `test_every_decision_equals_the_engine_bound_for_each_stage1_design[direct-1.0]` |
| M-S1A-3 | 695-stage1a-direct-terminal-scale | direct F-N terminal bound drops `2*bound - 1` | **KILLED** | `test_direct_terminal_bounds_equal_the_engine_bounds` |
| M-S1A-4 | 695-stage1a-equal-epoch-grid | allocations compared at a fixed pair cap again | **KILLED** | `test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations` (and `test_stage1_grid_has_expected_structure`) |
| M-S1A-5 | 695-stage1a-fp-exact-alpha | exact F-P fallback swaps pass_alpha for FUTILITY_ALPHA (#694 M1b) | **KILLED** | `test_exact_fp_fallback_uses_the_registered_pass_alpha` |
| M-S1A-6 | 695-stage1a-fn-exact-alpha | direct F-N exact fallback uses alpha/2 instead of pass_alpha | **KILLED** | `test_direct_fn_exact_fallback_is_pinned_to_the_engine` |
| M-S1A-7 | 695-stage1a-union-fn-exact-always-true | union F-N exact fallback forced true (#694 M2b) | **KILLED** | `test_union_fn_exact_fallback_is_pinned_to_the_engine` and `test_every_decision_equals_the_engine_bound_for_each_stage1_design[union-2.0]` |
| M-S1A-8 | 695-stage1a-price-hi | list high price rate $0.087 shifted to $0.078 (#694 M5) | **KILLED** | `test_price_constants_are_the_registered_rates` |
| M-S1A-9 | 695-stage1a-price-cap | cap price rate $0.30 shifted to $0.03 (#694 M6) | **KILLED** | `test_cap_price_string_carries_the_cap_rate` and `test_price_constants_are_the_registered_rates` |
| M-S1A-10 | 695-stage1a-role-boundary | role() uses d < 0.15 instead of d <= 0.15 (#694 M8) | **KILLED** | `test_role_labels_d_equal_to_0_15_as_no_lift` |
| M-S1A-11 | 695-stage1a-calibration-look-one | pass_calibration_holds reads look 1 instead of the cap | **KILLED** | `test_calibration_holds_reads_the_cap_look_not_look_one` |
| M-S1A-12 | 695-stage1a-headline-pairs | headline filters on a stale 97-pair count (#694 M10) | **KILLED** | `test_headline_reads_the_pairs_cap_designs_in_the_results` |

Twelve hand-chosen mutants. **No mutation score is reported**, because twelve cases cannot
support one; each case is a named obligation, not a sample.

The #694 verdict comment (PR #694, issue comment 5902938377) could not be read from the container
that chose these mutants: the container holds no GitHub token and network use is forbidden. The
mutants above are the defect classes the #695 ticket names and the classes the #694 verdict
table listed as survived (M1b, M5, M6, M8, M9, M10, M13) plus the already-killed scale and
equal-epoch defects re-pinned by name, plus the exact-path F-N defect the #704 verdict found
open. The pure always-true form of direct F-N in the exact fallback is observationally equivalent
on this grid: 108 exact-path evaluations across the searched cells never had a failing bound, so
forcing True does not change any per-look output. M-S1A-6 therefore pins the alpha defect in
that same path, which is observable.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 1A suite as a whole, or that any
surviving mutant outside the twelve named cases is safe. It does not claim that the smoke-run
numbers are final operating characteristics; those come from
`docs/findings/data/stage1a-regime-685/` at a stated replicate count and the full grid belongs
to part (b), #696. It says twelve specific defects are detected, in isolated worktrees, against
baselines that passed first, and that the production tree was byte-unchanged throughout. It
refuses any claim about the #694 verdict comment itself, which the build container could not read.

*Revisit if:* the #695 deliverable changes. Then regenerate with
`scripts/mutation_receipt.py --select 695-stage1a`; the currency gate reddens automatically the
moment the simulator's bytes move.
