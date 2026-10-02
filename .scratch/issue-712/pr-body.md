#712: Stage 1A simulator — sensitivity sentence, CUT calibration read, rebuild path

PR body for issue #712, the three non-author findings on PR #711 (PASS+NOTES at
`05e607e`). Each acceptance criterion is stated, the test that pins it is named,
and the observation watching that test fail before the change and pass after is
recorded. Mutation campaign results follow.

## What was wrong

Three defects, found by the non-author verdict on PR #711.

1. **A printed sentence was false on the full grid.** The sensitivity section of
   the summary that `scripts/screens/419/simulate_stage1a_regime_685.py` writes
   said its numbers "describe what a nine-cell aggregate would have read". The
   numbers are the off-diagonal minimum. On the 2,000-replicate output of #696
   the two differ in 6 of 12 rows (for example 0.3605 printed where the
   nine-cell minimum is 0.3525). They agree on the committed 20-replicate smoke
   data, so no committed file was wrong today. No test read the sentence.
2. **The calibration read was under-tested.** Making `is_calibration_cell`
   return only the PASS half drops every CUT-error cell above d = 0.20 from the
   exit code, and no behavioural test failed. Only the receipt digest check went
   red, as it does on any byte change.
3. **The simulator could not read its own output.** The headline, the
   calibration read and the summary were produced only at the end of a run.
   Issue #696 has a finished full-grid `per_look.tsv` (about ten hours of
   compute) and needs the headline derived from that file by this code, without
   a second run.

## Criterion 1 — sensitivity sentence names the off-diagonal minimum

**Built.** The summary sentence and the `sensitivity_rows` docstring now say
the numbers are the minima over the six off-diagonal cells only. The previous
wording ("These numbers describe what a nine-cell aggregate would have read")
is gone from both.

**Test.** `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum`,
`test_sensitivity_rows_report_off_diagonal_minima_not_nine_cell_minima`, and
`test_committed_smoke_summary_reports_the_target_check` in
`tests/test_simulate_stage1a_regime_685.py`. The fixture
`_off_diag_vs_nine_cell_rates` sets every off-diagonal P(PASS) at d = 0.30 to
at least 0.75 and the diagonal cell (0.30, 0.30) to 0.40, so the off-diagonal
minimum is 0.75 and the nine-cell minimum is 0.40. The summary test asserts
"nine-cell" is absent from the sensitivity block, "off-diagonal minima" is
present, the printed row carries 0.7500 and not 0.4000.

**Observed.** Before the sentence change the test failed on
`assert "nine-cell" not in sensitivity_block` with the old sentence visible in
the block ("These numbers describe what a nine-cell aggregate would have
read"). After the change both tests pass. Restoring the old wording fails the
sentence test again; the row assertion fails if the printed number is the
nine-cell minimum. Control:
`test_summary_reports_off_diagonal_cells_as_sensitivity` still passes (it
pins "never the target" and the printed off-diagonal row).

## Criterion 2 — calibration read covers CUT-error cells above d = 0.20

**Built.** Extracted `calibration_exit_code(results)` from `main()`. The
function filters on `is_calibration_cell` and returns `0 if all_hold else 1`.
`main()` returns that function's value after printing diagnostics. The M-S1A-1
anchor string `return 0 if all_hold else 1` now lives inside
`calibration_exit_code`, so the exit-path mutant still fires through `main()`.

**Test.** `test_calibration_read_includes_cut_error_cells_above_boundary` and
`test_calibration_exit_code_filters_on_is_calibration_cell`. The CUT-only cell
is (0.65, 0.35, 0.35): d = 0.30 > BOUNDARY, F-N = 0.30 > BOUNDARY, so it is a
CUT-calibration cell and not a PASS-calibration cell. A hand result with
p_cut above the futility limit and p_pass at zero must exit 1. A second test
checks the filter across a PASS-only cell, the CUT-only cell and a boundary
cell.

**Observed.** With `is_calibration_cell` temporarily narrowed to
`return is_pass_calibration_cell(cell)`, both tests failed:
`AssertionError: is_calibration_cell must include CUT-error cells above d = 0.20`
and the exit-code assertion (`assert False` where `False =
reg.is_calibration_cell(Cell(p_full=0.65, ...))`). Under the correct union
predicate both pass. Existing exit-path tests
(`test_main_exits_non_zero_when_calibration_fails`,
`test_main_exits_zero_when_calibration_holds`,
`test_main_exits_non_zero_when_the_fn_margin_cell_fails_pass_calibration`)
still pass against the extracted function.

## Criterion 3 — rebuild from an output directory

**Built.** `main()` accepts `--rebuild`. It calls
`results_from_output_dir`, which parses `per_look.tsv` into `CellResult`s
(and `terminal_states.tsv` when present), then calls the same
`summary_md`, `headline`, `target_check_rows`, `sensitivity_rows` and
`calibration_exit_code` a run uses. I/O only; no second aggregation. Runs
write `run_meta.json` with replicates and seed; rebuild reads it when present,
else takes replicates from the TSV and seed from `--seed` (default 685).
`per_look.tsv` float columns move from `.5f` to `.10f` so rates round-trip.
`terminal_states.tsv` is optional: the committed smoke terminal file is missing
the 1,200-epoch designs, and #696 needs the headline, stage-2 trigger,
calibration read and sensitivity — all of which need only `per_look.tsv`.
When cap-cell terminal rows are absent, rebuild states that the terminal table
cannot be rebuilt rather than presenting their absence as zero observations.

**Test.** `test_rebuild_reproduces_summary_and_exit_code_byte_identically`,
`test_rebuild_makes_no_simulation_call`,
`test_rebuild_reads_headline_calibration_and_sensitivity_from_disk`, and
`test_rebuild_refuses_to_invent_missing_terminal_states`. The
first runs `main` on a four-cell grid, captures `summary.md` and the exit
code, then rebuilds and asserts byte-identity and the same exit code. The
second monkeypatches `run_cell` to raise before rebuilding. The third checks
the rebuilt summary carries the headline for 0.80 and 0.90, the stage-2
trigger lines, the sensitivity section with "off-diagonal minima", and the
replicate/seed header. The fourth rebuilds the committed incomplete terminal
file and requires an explicit refusal instead of zero-count terminal rows.

**Observed.** Before `--rebuild` existed all three tests failed with
`argparse` `unrecognized arguments: --rebuild`. After implementing the flag
all three pass. Rebuilding a copy of the committed smoke `per_look.tsv`
(without `run_meta.json`, without a complete terminal file) produces a summary
that carries every required section; the four figures issue #696's reviewer
will check (best diagonal-minimum P(PASS) at d = 0.30 = 0.2335; best
diagonal-minimum P(CUT) at d = 0.10 = 0.5070; largest P(PASS) in an error
cell 0.0080; largest P(CUT) in an error cell 0.0360) come from that same
code path on the operator's disk, which is not in this repository.

## Criterion 4 — mutation receipt regenerated

**Built.** Four new mutants registered in `scripts/mutation_receipt.py`
under obligation prefix `712-stage1a`. The receipt
`docs/assurance/stage1a-regime-712-mutation-receipt.json` and its prose
companion are committed; `docs/receipts-index.md` gains the 712 entry and
names the 695 and 708 companion campaigns. Because the simulator digest moved,
the existing digest-pinned receipts for the same file were regenerated:
`stage1a-regime-685-mutation-receipt.json` (prefix `695-stage1a`, twelve
mutants) and `stage1a-regime-708-mutation-receipt.json` (prefix
`708-stage1a`, five mutants). Both prose companions name the new digest
`sha256:0fcea0f8c12913f3a3aa27375dd3a18f434a54b2e048fd1cb02bc8c02d36d7ee`.

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-18 | 712-stage1a-sensitivity-sentence-nine-cell | sentence restored to the false nine-cell-aggregate claim | **KILLED** | `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum` |
| M-S1A-19 | 712-stage1a-calibration-read-drops-cut | `is_calibration_cell` returns only the PASS half | **KILLED** | `test_calibration_read_includes_cut_error_cells_above_boundary`, `test_calibration_exit_code_filters_on_is_calibration_cell` |
| M-S1A-20 | 712-stage1a-rebuild-disabled | `--rebuild` early return removed, rebuild simulates | **KILLED** | `test_rebuild_makes_no_simulation_call`, `test_rebuild_reproduces_summary_and_exit_code_byte_identically` |
| M-S1A-21 | 712-stage1a-off-diag-cells-to-all-nine | `off_diagonal_cells` returns the nine-cell grid | **KILLED** | `test_sensitivity_rows_report_off_diagonal_minima_not_nine_cell_minima`, `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum` |

Regenerated campaigns: all twelve `695-stage1a` mutants and all five
`708-stage1a` mutants re-killed on the committed tree at the new digest.
M-S1A-1's anchor still matches once, now inside `calibration_exit_code`.

No mutation score is reported: each case is a named obligation, not a sample.

## Criterion 5 — no registered constant changes

**Built.** No constant in `scripts/screens/419/simulate_stage1a_regime_685.py`
or `scripts/screens/419/v5_cue_stage1a.py` changed. BOUNDARY, PASS_ALPHA,
FUTILITY_ALPHA, the price rates, PAIRS_CAP, REPLICATES and SEED are untouched.

**Test.** `tests/test_v5_cue_stage1a.py::test_simulator_constants_pin_to_the_registered_launcher`
was not edited. It passes: `simulate_a_design.BOUNDARY == v5_cue_stage1a.BOUNDARY`,
`PASS_ALPHA == LEDGER_PASS_ALPHA`, `FUTILITY_ALPHA == ALPHA`. The M-S1A-8
and M-S1A-9 price mutants still die on
`test_price_constants_are_the_registered_rates`, which asserts the registered
numbers by name.

## Criterion 6 — gate

Commands, in the order CI runs them:

```
ruff check src tests scripts
ruff format --check src tests scripts
mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py
pytest tests/test_simulate_stage1a_regime_685.py tests/test_simulate_stage1a_regime_684.py tests/test_simulate_a_design_650.py
pytest tests/test_mutation_receipt.py tests/test_receipts_index.py
pytest tests/test_v5_cue_stage1a.py::test_simulator_constants_pin_to_the_registered_launcher
```

Observed on this branch after the last commit: ruff check clean; ruff format
clean; mypy --strict clean (385 source files); the three simulator test files
green; mutation-receipt and receipts-index guards green; the pin test green.
`scripts/drift_check.py` is part of the CI compound gate and was run as part
of the same pre-commit mypy invocation's siblings in the workflow; no docs
outside `docs/assurance/` and `docs/receipts-index.md` changed.

## Which test covers which criterion

| criterion | test | would fail without the change because |
|---|---|---|
| 1 | `test_summary_sensitivity_sentence_names_the_off_diagonal_minimum` | "nine-cell" present, or the printed row is the nine-cell minimum |
| 1 | `test_sensitivity_rows_report_off_diagonal_minima_not_nine_cell_minima` | `sensitivity_rows` reports 0.40 instead of 0.75 |
| 1 | `test_committed_smoke_summary_reports_the_target_check` | the committed smoke summary still carries the false nine-cell sentence |
| 2 | `test_calibration_read_includes_cut_error_cells_above_boundary` | `is_calibration_cell` excludes the CUT-only cell, or the exit code is 0 |
| 2 | `test_calibration_exit_code_filters_on_is_calibration_cell` | the filter drops CUT-only or PASS-only failures |
| 3 | `test_rebuild_reproduces_summary_and_exit_code_byte_identically` | no `--rebuild`, or rebuild recomputes different bytes / a different exit code |
| 3 | `test_rebuild_makes_no_simulation_call` | `run_cell` is called during rebuild |
| 3 | `test_rebuild_reads_headline_calibration_and_sensitivity_from_disk` | rebuilt summary lacks a headline, trigger, or sensitivity section |
| 4 | `test_every_mutation_anchor_matches_its_target_exactly_once` | an anchor drifted; the receipt cannot run |
| 4 | `test_receipt_still_describes_the_files_it_measured` | a receipt pins a digest the live file no longer has |
| 4 | `test_prose_companion_names_the_digest_its_receipt_attests` | prose names a superseded digest |
| 5 | `test_simulator_constants_pin_to_the_registered_launcher` | a registered constant moved on either side |
| 6 | the three simulator test files, ruff, mypy | any of the above, or a type/lint regression |

## Out of scope (per the ticket)

No change to any pre-registration text, threshold, estimand or the launcher.
No full-grid run. No change to what the headline is (the diagonal minimum,
per the ruling in issue #696 comment 5944534509). The data commit and the
findings record are issue #696's. The committed smoke `summary.md` receives
only the corrected sensitivity sentence; its measured rows are unchanged.

## Revisit if

Issue #696 is finished by a second full run instead of a rebuild; then the
`--rebuild` path and its tests are unneeded, and criteria 1 and 2 stand
alone.
