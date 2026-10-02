# Mutation receipt: the #712 sensitivity sentence, CUT calibration read, and rebuild

**Standard:** #341. **Repair:** #712, the three non-author findings on PR #711
(PASS+NOTES at `05e607e`): the false sensitivity sentence, the under-tested
CUT half of the calibration read, and the simulator's inability to read its
own output. **Generator:** `scripts/mutation_receipt.py --select 712-stage1a`.
**Machine-readable record:** `docs/assurance/stage1a-regime-712-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:1a295c27a442116a29bcbbbdb64d44e72f45ab4cba8567ed4157ae881c3ea205`.
**Commit at generation:** `1b316f6704358114638233513d94485ac6427ac0` —
informational only; currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.15.

Each case runs in its own git worktree at a fixed commit. Production is never
mutated in place. All four cases resolved `simulate_stage1a_regime_685` inside
their own worktree, every clean baseline passed first with nonzero collection,
every mutant imported, and the production digest was identical before and
after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-18 | 712-stage1a-sensitivity-sentence-nine-cell | the sensitivity sentence is restored to the false nine-cell-aggregate claim | **KILLED** | `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum` |
| M-S1A-19 | 712-stage1a-calibration-read-drops-cut | `is_calibration_cell` returns only the PASS half, dropping CUT-error cells above d = 0.20 from the exit code | **KILLED** | `test_calibration_read_includes_cut_error_cells_above_boundary`, `test_calibration_exit_code_filters_on_is_calibration_cell` |
| M-S1A-20 | 712-stage1a-rebuild-disabled | the `--rebuild` early return is removed, so rebuilding runs a second simulation | **KILLED** | `test_rebuild_makes_no_simulation_call`, `test_rebuild_reproduces_summary_and_exit_code_byte_identically` |
| M-S1A-21 | 712-stage1a-off-diag-cells-to-all-nine | `off_diagonal_cells` returns the full nine-cell grid, so sensitivity rows report nine-cell minima | **KILLED** | `test_sensitivity_rows_report_off_diagonal_minima_not_nine_cell_minima`, `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum` |

Four hand-chosen mutants. **No mutation score is reported**, because four
cases cannot support one; each case is a named obligation, not a sample.

M-S1A-18 and M-S1A-21 are two faces of the same finding the non-author verdict
named: the printed sentence claimed a nine-cell aggregate while the code
computed off-diagonal minima. On the #712 fixture the two disagree (0.75 vs
0.40), so both the wording and the cell set are pinned.

M-S1A-19 is the calibration defect. The verdict recorded that narrowing
`is_calibration_cell` to the PASS half dropped every CUT-error cell above
d = 0.20 from the exit code and no behavioural test failed; only the receipt
digest check went red. The new tests go through `calibration_exit_code`, the
same filter `main()` returns, with a hand result whose P(CUT) sits above the
futility limit on a CUT-only cell (0.65, 0.35, 0.35).

M-S1A-20 pins the rebuild path. The killing test monkeypatches `run_cell` to
raise, so a rebuild that simulates fails before it can write a summary.

## Companion campaigns

The same simulator digest is pinned by two earlier receipts, regenerated in
this change because the subject moved:

- `docs/assurance/stage1a-regime-685-mutation-receipt.json` (obligation prefix
  `695-stage1a`): twelve mutants from the #695 repair.
- `docs/assurance/stage1a-regime-708-mutation-receipt.json` (obligation prefix
  `708-stage1a`): five mutants from the #708 diagonal-aggregation repair.

Both carry the same digest as this receipt after regeneration.

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 1A suite as a whole,
or that any surviving mutant outside the four named cases is safe. It does not
claim the #696 full-grid operating characteristics; those files live on the
operator's host and are not in this repository. It refuses any claim about the
#711 verdict comment itself, which this container could not read. It says four
specific defects are detected, in isolated worktrees, against baselines that
passed first, and that the production tree was byte-unchanged throughout.

*Revisit if:* the #712 deliverable changes. Then regenerate with
`scripts/mutation_receipt.py --select 712-stage1a`; the currency gate reddens
automatically the moment the simulator's bytes move.
