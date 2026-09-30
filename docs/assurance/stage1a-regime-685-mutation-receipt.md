# Mutation receipt: the Stage 1A regime simulator (#685 part a, ticket #695)

**Standard:** #341. **Repair:** #695, the part (a) rebuild of #685 after three builds failed on the
whole ticket. **Generator:** `scripts/mutation_receipt.py --select 695-stage1a`.
**Machine-readable record:** `docs/assurance/stage1a-regime-685-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:52f968c36c4bb634ec6412e125d640f79f51c94ff01cd6f1d241c923282bcffe`.
**Commit at generation:** `9f0d302fc60c` — informational only; currency is checked against the
digest above by `tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Each case runs in its own git worktree at a fixed commit. Production is never mutated in place.
`PYTHONPATH` pins every case to its own sources; `scripts/screens/419` joins `src` and `scripts`
so the screen modules import by bare name. All eleven cases resolved
`simulate_stage1a_regime_685` inside their own worktree, every clean baseline passed first with
nonzero collection, every mutant imported, and the production digest was identical before and
after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-1 | 695-stage1a-exit | exit-on-calibration-failure returns 0 anyway | **KILLED** | `test_main_exits_non_zero_when_calibration_fails` |
| M-S1A-2 | 695-stage1a-direct-online-scale | direct F-N grid bound compared unscaled | **KILLED** | `test_every_decision_equals_the_engine_bound_for_each_stage1_design[direct-1.0]` |
| M-S1A-3 | 695-stage1a-direct-terminal-scale | direct F-N terminal bound drops `2*bound - 1` | **KILLED** | `test_direct_terminal_bounds_equal_the_engine_bounds` |
| M-S1A-4 | 695-stage1a-equal-epoch-grid | allocations compared at a fixed 400-pair cap again | **KILLED** | `test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations` (and `test_stage1_grid_has_expected_structure`) |
| M-S1A-5 | 695-stage1a-null-draw-count | double-null design draws one Null epoch per pair | **KILLED** | `test_null_allocation_uses_exactly_the_declared_observations` |
| M-S1A-6 | 695-stage1a-epochs-profile | epoch profile omits Null epochs | **KILLED** | `test_expected_epochs_track_the_null_allocation_profile` |
| M-S1A-7 | 695-stage1a-expected-spend-rate | expected spend priced at the cap rate | **KILLED** | `test_every_per_look_row_carries_expected_epochs_and_expected_spend` |
| M-S1A-8 | 695-stage1a-trigger-never-fires | stage-2 trigger hardcoded to never fire | **KILLED** | `test_stage2_trigger_fires_when_the_power_half_is_unmet` |
| M-S1A-9 | 695-stage1a-calibration-half-assumed | calibration half assumed to hold | **KILLED** | `test_stage2_trigger_fires_when_the_calibration_half_fails` |
| M-S1A-10 | 695-stage1a-power-half-assumed | power half assumed reached | **KILLED** | `test_stage2_trigger_fires_when_the_power_half_is_unmet` |
| M-S1A-11 | 695-stage1a-headline-inverted | headline smallest-d inequality inverted | **KILLED** | `test_target_check_states_both_halves_for_0_80_and_0_90_from_data_only` |

Eleven hand-chosen mutants. **No mutation score is reported**, because eleven cases cannot support
one; each case is a named obligation, not a sample.

The #694 verdict comment (PR #694, issue comment 5902938377) could not be read from the container
that ran this campaign: the container holds no GitHub token and network use is forbidden. The
mutants above are therefore the defect classes the #695 ticket names — the direct F-N scale, the
equal-epoch comparison, the exit-on-calibration-failure path — plus the rows the rebuild list's
requirements 4 and 5 put on the page (E[total epochs], the expected-spend price line, both halves
of the target, the stage-2 trigger). Any mutant the unreadable verdict listed outside these classes
is unattested here.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 1A suite as a whole, or that any
surviving mutant outside the eleven named cases is safe. It does not claim that the smoke-run
numbers are final operating characteristics; those come from `docs/findings/data/stage1a-regime-685/`
at a stated replicate count and the full grid belongs to part (b). It says eleven specific defects
are detected, in isolated worktrees, against baselines that passed first, and that the production
tree was byte-unchanged throughout.

*Revisit if:* the #695 deliverable changes. Then regenerate with
`scripts/mutation_receipt.py --select 695-stage1a`; the currency gate reddens automatically the
moment the simulator's bytes move.
