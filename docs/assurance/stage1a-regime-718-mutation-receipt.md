# Mutation receipt: the #718 Stage 2 stopping-design simulator

**Standard:** #341. **Repair:** #718, Stage 2 of #685 — stopping design x
pairs. **Generator:** `scripts/mutation_receipt.py --select 718-stage2`.
**Machine-readable record:** `docs/assurance/stage1a-regime-718-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685_stage2.py` at
`sha256:2256a2abe304393a178bbb546788cb1476f437665246f164f3338df73807bf6d`.
**Commit at generation:** `10fb0cc2d1283a4e4fc0472531299035e7191ae5` —
informational only; currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Each case runs in its own git worktree at a fixed commit. Production is never
mutated in place. All sixteen cases resolved
`simulate_stage1a_regime_685_stage2` inside their own worktree, every clean
baseline passed first with nonzero collection, every mutant imported, and the
production digest was identical before and after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S2-1 | 718-stage2-fixed-n-interim-look | a fixed-n-betting row records an interim look at n/2 instead of reading once at n | **KILLED** | `test_fixed_n_designs_read_once_at_n` |
| M-S2-2 | 718-stage2-fixed-n-anytime-bound-at-n | fixed-n-betting reads the anytime bound at n in place of its own horizon-scaled fixed-time bound | **KILLED** | `test_fixed_n_betting_run_cell_matches_horizon_scaling_not_anytime_at_n`, `test_fixed_n_betting_uses_horizon_scaled_bets_not_time_scaled` |
| M-S2-3 | 718-stage2-score-test-margin-dropped | the score tests use delta0 = 0 in place of the registered margin 0.20 | **KILLED** | `test_fixed_n_score_run_cell_holds_its_level_at_the_margin_boundary`, `test_score_tests_use_the_registered_margin_0_20`, `test_tango_score_equals_mcnemar_at_delta0_zero` |
| M-S2-4 | 718-stage2-statistic-contrast-mismatch | the paired Tango statistic is applied to the F - N contrast instead of F - P | **KILLED** | `test_fixed_n_score_applies_the_paired_statistic_to_fp_and_unpaired_to_fn` |
| M-S2-5 | 718-stage2-joint-pass-fp-only | joint PASS reads the F - P half only | **KILLED** | `test_joint_pass_requires_both_halves` |
| M-S2-6 | 718-stage2-alpha-label-computation-mismatch | the rule is always computed at 0.0209 whatever alpha the row declares | **KILLED** | `test_pass_alpha_label_matches_computation` |
| M-S2-7 | 718-stage2-starting-wealth-ignored | anytime-tuned ignores starting_wealth and always starts at W0 = 1.0 | **KILLED** | `test_starting_wealth_changes_anytime_tuned_decisions` |
| M-S2-8 | 718-stage2-tuned-bet-lookahead | the tuned wealth factor divides by a term that depends on the current pair's outcome | **KILLED** | `test_tuned_lambda_is_fixed_before_the_first_pair` |
| M-S2-9 | 718-stage2-calibration-skips-fixed-n | the calibration read skips fixed-n rows | **KILLED** | `test_calibration_exit_code_covers_fixed_n_rows` |
| M-S2-10 | 718-stage2-stopping-label-disagrees | fixed-n-betting is produced by the anytime path, so the label disagrees with the simulation | **KILLED** | `test_stopping_column_on_the_tsv_matches_the_path_that_produced_it` |
| M-S2-11 | 718-stage2-headline-pair-count | the headline reports a stale 100-pair count | **KILLED** | `test_headline_reads_n_pairs_from_each_row` |
| M-S2-12 | 718-stage2-cut-direction-reversed | the CUT wealth factor bets upward instead of downward | **KILLED** | `test_cut_direction_is_downward` |
| M-S2-13 | 718-stage2-exit-code-forced-zero | the calibration exit code is forced to 0 | **KILLED** | `test_exit_code_is_not_forced_to_zero` |
| M-S2-14 | 718-stage2-tuned-rejection-running-max | the anytime-tuned rejection reads the current wealth instead of its running maximum | **KILLED** | `test_anytime_tuned_rejection_uses_running_maximum` |
| M-S2-15 | 718-stage2-score-cut-level-010 | the fixed-n-score CUT test runs at 0.10 instead of 0.05 | **KILLED** | `test_fixed_n_score_cut_is_decided_at_0_05` |
| M-S2-16 | 718-stage2-joint-pass-fn-alone | the fixed-n-score joint PASS reports its F - N half alone | **KILLED** | `test_fixed_n_score_joint_pass_requires_both_halves_not_fn_alone` |

Sixteen hand-chosen mutants, one per acceptance obligation. **No mutation
score is reported**, because sixteen named cases cannot support one; each
case is an obligation, not a sample.

M-S2-2, M-S2-3, M-S2-6, M-S2-7, M-S2-10 and M-S2-11 first survived an earlier
campaign whose tests pinned only unit-level helpers or used non-strict
inequalities the mutant could satisfy by equality. The killing tests named
above were rewritten to assert run_cell-level external behaviour: a
horizon-scaled pass rate that differs from an anytime-at-n read, a boundary
cell whose PASS rate stays near the row's alpha only under the registered
margin, a strict pass-rate ordering across declared alphas, a strict
starting-wealth ordering on a cell that actually passes, a full-cap
expected-epochs figure that the anytime path cannot produce, and a headline
fixture where only the 300-pair configuration meets the target.

M-S2-14, M-S2-15 and M-S2-16 were added in the #718 rework (S510). The first
campaign left three behaviours of the new designs unpinned: the
anytime-tuned rejection's use of the running maximum, the fixed-n-score CUT
level of 0.05, and the requirement that joint PASS on a fixed-n-score row
carry both halves. Each mutant is killed by a test written for it.

## Companion campaigns

The Stage 1A simulator under #685 is untouched by this change. Its own
receipts remain current:

- `docs/assurance/stage1a-regime-685-mutation-receipt.json` (obligation prefix
  `695-stage1a`).
- `docs/assurance/stage1a-regime-708-mutation-receipt.json` (obligation prefix
  `708-stage1a`).
- `docs/assurance/stage1a-regime-712-mutation-receipt.json` (obligation prefix
  `712-stage1a`).

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 2 suite as a whole,
or that any surviving mutant outside the sixteen named cases is safe. It
does not claim the full-replicate Stage 2 operating characteristics; the
committed data directory holds the reduced grid at 200 replicates only, and
the full grid is the next ticket. It refuses any claim about which stopping
design meets the #685 power target on the full pair grid — the reduced
committed run reports every diagonal configuration as not reached at 100
pairs, and the full pair grid has not been simulated. It says sixteen
specific defects are detected, in isolated worktrees, against baselines that
passed first, and that the production tree was byte-unchanged throughout.

*Revisit if:* the #718 deliverable changes. Then regenerate with
`scripts/mutation_receipt.py --select 718-stage2`; the currency gate reddens
automatically the moment the Stage 2 simulator's bytes move.
