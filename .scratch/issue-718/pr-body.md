#718: Stage 2 of #685 — stopping design x pairs

## What this change contains

- `scripts/screens/419/simulate_stage1a_regime_685_stage2.py` — a zero-spend
  simulator that varies the stopping design and the number of pairs together.
  It reuses the #685 draws (`cell_rng`), rule constants, calibration read,
  diagonal target check, price lines and rebuild path. It changes no committed
  #685 file, number or test.
- `tests/test_simulate_stage1a_regime_685_stage2.py` — 41 tests, one or more
  per acceptance criterion.
- `docs/findings/data/stage1a-regime-685-stage2/` — the reduced grid at 200
  replicates per cell, seed 685: 792 rows, replicate count on every row,
  `summary.md`, `run_meta.json`. Output never lands under `.scratch/`.
- `scripts/mutation_receipt.py` — thirteen mutants registered under their own
  `718-stage2-*` obligation prefixes.
- `docs/assurance/stage1a-regime-718-mutation-receipt.{json,md}` and the
  matching `docs/receipts-index.md` entry.
- `.scratch/issue-718/pr-body.md` — this file.

The simulator branches on `stopping`. `anytime` delegates to
`s685.run_cell`, so the reference row matches the committed #685 data.
`anytime-tuned` runs one wealth process per replicate with a lambda fixed
before the first pair. `fixed-n-betting` uses the Waudby-Smith and Ramdas
(JRSSB 2023, Theorem 3, Remark 3) fixed-time hedged bound, bets scaled for the
horizon n. `fixed-n-score` reads once at n: Tango's 1998 paired score test
against margin 0.20 on F − P, Farrington-Manning on F − N, CUT mirrored at
0.05.

## Acceptance criteria

### 1. Full grid, no calls, exit non-zero on calibration failure

Built: `stage2_grid()` covers pairs 100–800, null per pair 1.0 and 0.5, the
seven #685 effects, nine baseline cells, and every stopping design with its
declared parameter variants (union only on anytime rows; direct on every new
design; fixed-n alphas 0.0209/0.0105/0.005; starting wealths 1.0/0.5/0.25).
`main()` returns `calibration_exit_code(rows)`, which is 1 when a non-score
calibration row fails. The module imports numpy and local screens only.

Pinned by: `test_script_module_has_no_model_or_network_import`,
`test_main_exits_zero_when_calibration_holds`,
`test_main_exits_non_zero_when_a_non_score_design_fails_calibration`,
`test_main_rebuild_makes_no_simulation_call`,
`test_main_rebuild_reproduces_summary_and_exit_code`,
`test_full_grid_structure`.

Observed: before the serial-workers fix, `main()` with ProcessPoolExecutor
raised `PicklingError` when two test files shared
`simulate_stage1a_regime_685` in `sys.modules`; the rebuild test and the
exit-code test were red. After short-circuiting to serial execution at
`workers <= 1`, both are green. The calibration-failure path was exercised by
running a loosened rule through `main()` and observing exit code 1.

### 2. Calibration covers every row of every design

Built: `row_calibration_holds` checks P(PASS) against the row's declared
pass_alpha plus 3 MC SE wherever true F − P or F − N is at or below 0.20, and
P(CUT) against 0.05 plus 3 MC SE wherever true F − P is at or above 0.20.
`is_calibration_cell` is the union of both halves, as in #708.

Pinned by: `test_calibration_predicate_covers_the_fn_margin_cell`,
`test_calibration_uses_the_rows_own_pass_alpha`,
`test_cut_calibration_uses_the_futility_level`,
`test_calibration_read_covers_every_declared_design`,
`test_calibration_set_includes_every_pass_and_cut_error_cell`.

Observed: hand rows above each limit fail; rows under each limit hold. Every
stopping design's failure is visible to the read.

### 3. fixed-n-score level failure is labelled, excluded, non-fatal

Built: `is_nonfatal_calibration_failure` is true only for fixed-n-score rows
that fail. `headline_includes` is `row.holds_level` — a failing score row
stays out of the headline. `calibration_exit_code` is 0 when every failing
calibration row is a fixed-n-score row; every other design's failure returns
1.

Pinned by: `test_fixed_n_score_calibration_failure_is_labelled_and_non_fatal`,
`test_headline_excludes_fixed_n_score_rows_that_fail_calibration`,
`test_negative_control_loosened_rule_fails_fixed_n_score`.

Observed: a hand score row with P(PASS) 0.40 is labelled, excluded from the
headline, and leaves the exit code at 0. The same hand row on an
anytime-tuned design sets the exit code to 1.

### 4. Regression: anytime cell at seed 685, 2,000 replicates

Built: `_run_anytime` delegates to `s685.run_cell` with the same seed, pair
count, construction and alpha, so the reference path cannot drift from the
committed #685 data.

Pinned by: `test_anytime_cell_matches_the_committed_685_row`. The test
re-runs the committed 100-pair, null 1.0, direct, d = 0.30 diagonal cells at
seed 685 and 2,000 replicates and compares cap-look P(PASS) and P(CUT) to
`docs/findings/data/stage1a-regime-685/per_look.tsv` at 1e-12. It also reads
the 400-pair diagonal minimum from the same committed file and asserts
0.2335, the figure the ticket names. A 400-pair re-run at 2,000 replicates
takes about 17 minutes on one core; the suite pins the cheaper committed
family instead and states why.

Observed: the three 100-pair diagonal rows match the committed file exactly
(p_pass 0.02450, 0.02750, 0.02950 at the cap look). The 400-pair committed
minimum is 0.2335.

### 5. Reduced grid in the suite; committed data holds it

Built: `reduced_grid()` is pairs {100}, null per pair {1.0, 0.5}, effects
{0.00, 0.10, 0.20, 0.30}, all nine baseline cells, every stopping design with
its declared variants. The committed directory holds that run at 200
replicates. Every row carries `replicates`, `pass_alpha`, `starting_wealth`,
the half rates, joint PASS, CUT, CANT_TELL_YET, expected epochs, both price
lines and MC SE.

Pinned by: `test_reduced_grid_covers_every_stopping_design`,
`test_reduced_grid_runs_end_to_end`,
`test_committed_data_holds_the_reduced_grid_with_replicate_counts`,
`test_committed_summary_is_what_rebuild_writes`.

Observed: the committed `per_look.tsv` has 792 data rows at replicates 200;
every reduced-grid key is present; `--rebuild` reproduces `summary.md` byte
for byte; the data directory is under `docs/findings/data/`, not `.scratch/`.

### 6. Negative control: loosened calibration fails per new design

Built: `run_cell` accepts `pass_alpha_override`, which loosens the rule while
the row keeps the alpha it declares. Calibration reads the declared alpha.

Pinned by: `test_negative_control_loosened_rule_fails_anytime_tuned`,
`test_negative_control_loosened_rule_fails_fixed_n_betting`,
`test_negative_control_loosened_rule_fails_fixed_n_score`.

Observed: with the rule computed at 0.60 on a boundary cell and the row
declaring 0.0209, P(Joint PASS) exceeds 0.0209 + 3 MC SE on every new design.
The betting and tuned rows fail the exit code; the score row is labelled and
leaves it at 0.

### 7. Thirteen mutants, each under its own obligation prefix

Built: `scripts/mutation_receipt.py` registers M-S2-1 … M-S2-13 under
obligations `718-stage2-fixed-n-interim-look` …
`718-stage2-exit-code-forced-zero`. Each case runs in its own git worktree
against the committed tree. The receipt is
`docs/assurance/stage1a-regime-718-mutation-receipt.json`, pinned at
`sha256:dd6d13ad3c10b17eccc3dd36aa0770304b30f327c5e1531376a7e6d4a0d372aa`,
with prose in `docs/assurance/stage1a-regime-718-mutation-receipt.md` and the
Claims/Refuses entry in `docs/receipts-index.md`.

Observed: an earlier campaign killed six mutants and left seven survived,
because the tests pinned unit helpers or used non-strict inequalities the
mutant could satisfy by equality. The six survivors' tests were rewritten to
assert run_cell-level external behaviour (horizon-scaled pass rate vs
anytime-at-n, boundary PASS rate under the registered margin, strict alpha
ordering, strict starting-wealth ordering on a cell that passes, full-cap
expected epochs, a headline fixture where only 300 pairs meets). The
look-ahead mutant was changed to divide by a term that actually binds on
[0, 1]. After regeneration, all thirteen verdicts are KILLED, each by a
named assertion, with clean baselines passing first and the production tree
byte-unchanged.

| mutant | obligation | killing test |
|---|---|---|
| M-S2-1 | 718-stage2-fixed-n-interim-look | `test_fixed_n_designs_read_once_at_n` |
| M-S2-2 | 718-stage2-fixed-n-anytime-bound-at-n | `test_fixed_n_betting_run_cell_matches_horizon_scaling_not_anytime_at_n` |
| M-S2-3 | 718-stage2-score-test-margin-dropped | `test_fixed_n_score_run_cell_holds_its_level_at_the_margin_boundary` |
| M-S2-4 | 718-stage2-statistic-contrast-mismatch | `test_fixed_n_score_applies_the_paired_statistic_to_fp_and_unpaired_to_fn` |
| M-S2-5 | 718-stage2-joint-pass-fp-only | `test_joint_pass_requires_both_halves` |
| M-S2-6 | 718-stage2-alpha-label-computation-mismatch | `test_pass_alpha_label_matches_computation` |
| M-S2-7 | 718-stage2-starting-wealth-ignored | `test_starting_wealth_changes_anytime_tuned_decisions` |
| M-S2-8 | 718-stage2-tuned-bet-lookahead | `test_tuned_lambda_is_fixed_before_the_first_pair` |
| M-S2-9 | 718-stage2-calibration-skips-fixed-n | `test_calibration_exit_code_covers_fixed_n_rows` |
| M-S2-10 | 718-stage2-stopping-label-disagrees | `test_stopping_column_on_the_tsv_matches_the_path_that_produced_it` |
| M-S2-11 | 718-stage2-headline-pair-count | `test_headline_reads_n_pairs_from_each_row` |
| M-S2-12 | 718-stage2-cut-direction-reversed | `test_cut_direction_is_downward` |
| M-S2-13 | 718-stage2-exit-code-forced-zero | `test_exit_code_is_not_forced_to_zero` |

No mutation score is reported: thirteen named cases cannot support one.

### 8. PR body describes only the diff

This file is that body. It states what the diff contains, what each test
pins, and what the committed data shows. It makes no claim about which
stopping design meets the #685 power target on the full pair grid, because
the full grid has not been simulated.

## What the committed data shows

The reduced run at 100 pairs and 200 replicates per cell, seed 685, is
committed under `docs/findings/data/stage1a-regime-685-stage2/`. Every
headline configuration in that run reads not reached: the diagonal minimum
P(Joint PASS) at d = 0.30 sits between 0.0000 and 0.1150 across the four
stopping designs, and the diagonal minimum P(CUT) at d = 0.10 sits between
0.0100 and 0.3950, all below 0.80 and 0.90. Calibration holds on every
calibration row of that run: zero rows fail, zero fixed-n-score rows are
labelled. The summary's price sentence reads: no design in this reduced run
meets the 0.80 target with a cap price under $100, and none meets it with
expected spend under $100. That sentence is about the 100-pair reduced grid
only. The full pair grid (100 through 800) is the next ticket.

## Gate

`ruff check src tests scripts`, `ruff format --check src tests scripts`,
`mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py
scripts/check_dependency_anchor.py`, `python scripts/drift_check.py` and
`python -m pytest` on the stage-2, stage-1, mutation-receipt and
receipts-index test files are green at `37604ad`.

## Next

Simulate the full pair grid at the stated replicate count (the next ticket),
then read the headline from that data.
