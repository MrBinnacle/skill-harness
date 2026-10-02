# Mutation receipt: the #708 diagonal ruling and calibration read

**Standard:** #341. **Repair:** #708, the diagonal aggregation, broader
calibration read, constant pin, and replicate-count model statement for the
#685 Stage 1A regime simulator. **Generator:**
`scripts/mutation_receipt.py --select 708-stage1a`. **Machine-readable
record:** `docs/assurance/stage1a-regime-708-mutation-receipt.json`.
**Pinned by content, not by commit:**
`scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:49b0576185f11964372036c14a8b0ab6b424c11e0208a32ec73252ccc05ded9b`.
**Commit at generation:** `2aa61170f049996a80c30390ef53cac3dbf23e87` —
informational only; currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Each case runs in its own git worktree at a fixed commit. Production is never
mutated in place. All five cases resolved `simulate_stage1a_regime_685` inside
their own worktree, every clean baseline passed first with nonzero collection,
every mutant imported, and the production digest was identical before and
after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-13 | 708-stage1a-diagonal-min-to-max | diagonal target check takes max instead of min | **KILLED** | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum` |
| M-S1A-14 | 708-stage1a-diagonal-to-all-nine | diagonal target check reverts to the nine-cell aggregate | **KILLED** | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum` |
| M-S1A-15 | 708-stage1a-diagonal-to-single-cell | diagonal target check reads only (0.35, 0.35) | **KILLED** | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum` |
| M-S1A-16 | 708-stage1a-pass-calibration-drops-fn | is_pass_calibration_cell drops the true F-N half | **KILLED** | `test_calibration_covers_the_fn_margin_cell_at_d030`, `test_calibration_set_includes_every_pass_and_cut_error_cell`, `test_main_exits_non_zero_when_the_fn_margin_cell_fails_pass_calibration` |
| M-S1A-17 | 708-stage1a-model-statement-always-smoke | summary_md prints the smoke sentence whatever the replicate count | **KILLED** | `test_summary_marks_smoke_output_as_schema_evidence` |

Five hand-chosen mutants. **No mutation score is reported**, because five
cases cannot support one; each case is a named obligation, not a sample.

The constant pin in `tests/test_v5_cue_stage1a.py`
(`test_simulator_constants_pin_to_the_registered_launcher`) is not a
mutation-receipt case: it reads two modules' attribute values at test time and
is killed by moving any one of `simulate_a_design.BOUNDARY`,
`simulate_a_design.PASS_ALPHA`, `simulate_a_design.FUTILITY_ALPHA`,
`v5_cue_stage1a.BOUNDARY`, `v5_cue_stage1a.LEDGER_PASS_ALPHA`, or
`v5_cue_stage1a.ALPHA`. Those six moves were applied in a one-off script
against loaded module objects and each broke the corresponding equality; the
receipt does not re-run them because the launcher is outside this campaign's
mutant set.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 1A suite as a whole,
or that any surviving mutant outside the five named cases is safe. It does not
claim the #696 full-grid operating characteristics; those files live on the
operator's host at `C:/Users/mlpgr/wt-696-out/full` and are not in this
repository. It refuses any claim about the #696 issue-comment table itself,
which this container could not read. It says five specific defects are
detected, in isolated worktrees, against baselines that passed first, and that
the production tree was byte-unchanged throughout.

*Revisit if:* the #708 deliverable changes. Then regenerate with
`scripts/mutation_receipt.py --select 708-stage1a`; the currency gate reddens
automatically the moment the simulator's bytes move.
