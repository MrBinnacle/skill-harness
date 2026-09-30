# #695: Stage 1A regime simulator, part (a) of #685

**Branch:** `agent/issue-695`, starting from #694 at `c8a4cb6` (the branch the #694 verdict called a valid starting point; requirements 1 and 2 were already met there). **Parent:** #685. **Part (b):** #696, the full grid. **Model calls:** none. **Network calls:** none. **Spend:** none.

## What this diff contains

Net change against `main`, exactly ten files:

| file | what it is |
|---|---|
| `scripts/screens/419/simulate_stage1a_regime_685.py` | the Stage 1A regime simulator (from #694, plus the #695 additions below) |
| `tests/test_simulate_stage1a_regime_685.py` | its test file (from #694, plus the #695 tests below) |
| `docs/findings/stage1a-lever-adjudication-685.md` | the #685 findings record, updated for the #695 additions |
| `docs/receipts-index.md` | registry entries for the finding (updated) and the mutation receipt (added) |
| `scripts/mutation_receipt.py` | eleven M-S1A mutants registered under obligation prefix `695-stage1a`; `_env` gains `scripts/screens/419` |
| `docs/assurance/stage1a-regime-685-mutation-receipt.json` | machine record of that campaign |
| `docs/assurance/stage1a-regime-685-mutation-receipt.md` | prose companion, Claims/Refuses lines, digest pinned |
| `docs/findings/data/stage1a-regime-685/per_look.tsv` | smoke-run per-look rows (filtered; see AC3) |
| `docs/findings/data/stage1a-regime-685/terminal_states.tsv` | smoke-run terminal rows (filtered; see AC3) |
| `docs/findings/data/stage1a-regime-685/summary.md` | smoke-run summary, unfiltered |
| `.scratch/issue-695/pr-body.md` | this file, committed on the branch |

Nothing under `.scratch/` other than this evidence body in this diff. `git ls-files .scratch` on the branch also shows `.scratch/issue-526/pr-body.md` and `.scratch/issue-555/pr-body.md`, which predate this branch on `main`; this ticket adds no data files there. No output lands under `.scratch/` at run time; the simulator's `--out` target for the committed data is `docs/findings/data/stage1a-regime-685/`.

## Acceptance criteria, each in turn

### AC1 — rebuild requirements 1, 2, 4, 5, 6 and 8, each shown met with the command that shows it

Each requirement has its own section below, with the command and the red-phase observation. Summary of the showing commands:

```bash
# requirement 1 (direct F-N scale)
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py -k "engine_bound and direct" -q

# requirement 2 (allocations at equal total epochs)
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py::test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations -q

# requirement 4 (E[total epochs] and expected-spend price on every row)
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py -k "expected_epochs or expected_spend or terminal_row or surface_row or committed_smoke" -q

# requirement 5 (headline target check, both halves, 0.80 and 0.90, stage-2 trigger)
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py -k "target_check or stage2_trigger" -q

# requirement 6 (mutants turned red; exit-on-calibration-failure has its own test)
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py -k "main_exits" -q
python scripts/mutation_receipt.py --select 695-stage1a --out docs/assurance/stage1a-regime-685-mutation-receipt.json

# requirement 8 (this file)
# .scratch/issue-695/pr-body.md, committed on the branch
```

### AC2 — every data row carries the design fields, replicate count and MC SE

**Built:** `per_look.tsv` rows carry `n_full`, `n_placebo`, `n_null`, `total_epochs`, `null_per_pair`, `fn_construction`, `stopping`, `replicates`, `se_pass` (MC SE of P(PASS)); `terminal_states.tsv` rows carry the same design fields, `replicates`, and `se_share` (MC SE of the joint-state share), which the #694 build lacked.

**Test that pins it:** `test_committed_smoke_per_look_rows_carry_the_full_schema` and `test_committed_smoke_terminal_rows_carry_mc_se_and_price_lines` read the committed files and assert every row, every column.

**Observation:** before the change the terminal rows had no MC SE column and the per-look rows had no expected-epochs/spend columns; the tests failed on the missing names. After the change both files pass the tests. Command: `pytest tests/test_simulate_stage1a_regime_685.py -k committed_smoke -q` → 3 passed.

### AC3 — output under `docs/findings/data/stage1a-regime-685/`, smoke run committed

**Built:** the smoke run below wrote `per_look.tsv`, `terminal_states.tsv`, `summary.md` under `docs/findings/data/stage1a-regime-685/`. The repository's pre-commit gate (`check-added-large-files`, `--maxkb=500`) refuses the full 29 MB `per_look.tsv`, so the two TSVs are filtered views of that run and the filter is stated exactly in `docs/findings/stage1a-lever-adjudication-685.md`: `per_look.tsv` keeps every design x cell at look 1 and at the cap look, plus every look of the diagonal family (p_P = p_N = 0.35) at the 300-epoch budget, union, null_per_pair = 1.0 (2,198 rows; every design-field value appears); `terminal_states.tsv` keeps every joint state of every cell at the 300-epoch budget (1,512 rows); `summary.md` is unfiltered. Every committed row carries the design fields, the replicate count, the MC SE, E[total epochs], and the expected-spend price line beside the cap price.

**Smoke run, 20 replicates:**

```bash
python scripts/screens/419/simulate_stage1a_regime_685.py --out docs/findings/data/stage1a-regime-685 --replicates 20 --seed 685 --workers 8
```

Observed: exit 0 after 9m28s on 8 workers; every calibration cell inside the limit (0.0209 + 3 SE of 20 replicates = 0.11686). `summary.md` states "Replicates per cell: 20."

**Test that pins it:** the three `committed_smoke` tests above. This diff adds no files under `.scratch/` except this evidence body; the committed data live under `docs/findings/data/stage1a-regime-685/`.

### AC4 — #684 negative controls still run; one new loosened-rule negative control under a non-baseline design

**Built:** nothing in the #684 files was touched. The #685 test file carries `test_calibration_fails_for_loosened_rule_under_non_baseline_design` (null_per_pair = 0.5, pass alpha 0.6) and `test_calibration_fails_when_pass_alpha_is_loosened` (baseline design); both loosen the pass rule to 0.6 and assert the calibration check fails against the registered limit.

**Commands and observations:**

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_684.py -q
# 12 passed

PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py -k "loosened or main_exits" -q
# passed
```

`test_main_exits_zero_when_calibration_holds` is the control for the exit path: it runs the same non-baseline design under the registered rule and asserts exit code 0, so the failure-path kill cannot pass on an emptied cell.

### AC5 — no model calls, no network calls, no spend

The simulator imports `numpy`, `argparse`, `concurrent.futures`, `skill_harness.aggregation.confidence_sequence` and `simulate_a_design` — pure computation. Command:

```bash
grep -cn "anthropic\|openai\|urlopen\|requests\.\|http" scripts/screens/419/simulate_stage1a_regime_685.py
# 0
```

The smoke run and the mutation campaign both executed offline. No spend path exists in this code.

## Rebuild requirements of #685, one at a time

### Requirement 1 — direct F − N scale fix, test fails without it at d > 0.20 where allocations differ

**From #694:** the direct construction's online grid shortcut compared the raw one-sided bound against the d-scale boundary; the fix scales it to `2 * bound − 1`, and `_terminal_bounds_direct` applies the same scale at the terminal. **Pinning tests:** `test_every_decision_equals_the_engine_bound_for_each_stage1_design[direct-*]` and `test_direct_terminal_bounds_equal_the_engine_bounds`.

**Red phase observed:** with the grid-scale hunk reverted (the pre-fix form `lb_fn_br.lo[r] >= BOUNDARY`), the engine-parity test failed on all three direct parametrizations — `direct-0.5`, `direct-1.0`, `direct-2.0` — at cell (0.85, 0.25, 0.30), d = 0.60 > 0.20, allocations differing across the parametrizations. With the fix restored, all six parametrizations pass. Re-run: the `-k "engine_bound and direct"` command above.

### Requirement 2 — allocations compared at equal total epochs

**From #694:** `pairs_for_epoch_budget` sizes each null allocation to spend a fixed epoch budget exactly (300 and 1,200); the grid runs allocations at equal total epochs instead of equal pair counts. **Pinning test:** `test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations`.

**Red phase observed:** with the grid reverted to fixed pair caps (97, 400), that test failed and `test_stage1_grid_has_expected_structure` failed with it — pair counts no longer divide the declared budgets across allocations. With the fix restored both pass. Re-run: the requirement-2 command above.

### Requirement 4 — E[total epochs] and an expected-spend price line beside the cap price on every row

**Built:** `LookRow` carries `expected_epochs`; `per_look_rows` computes E[total epochs] from the null-allocation epoch profile `2k + (Null epochs scheduled through k)`, averaged over each replicate's stopping time. `per_look.tsv` and `terminal_states.tsv` carry `expected_epochs` and `expected_spend` (list-rate price at E[total epochs], `$0.083–$0.087` per epoch) beside the existing cap-price column `price_range`. The summary surface table carries `E[epochs]` and `expected spend` beside `price`. Terminal rows additionally carry `se_share`.

**Tests that pin it:** `test_every_per_look_row_carries_expected_epochs_and_expected_spend`, `test_expected_epochs_track_the_null_allocation_profile` (exact identity E[epochs] = (2 + null_per_pair) × E[pairs] at null_per_pair 1.0 and 2.0; bounds at 0.5), `test_every_terminal_row_carries_mc_se_expected_epochs_and_cap_price`, `test_surface_rows_carry_expected_epochs_and_expected_spend_beside_the_cap_price`, and the `committed_smoke` tests.

**Red phase observed:** before the change all four new tests failed — the columns did not exist in either TSV and the surface header had no `E[epochs]`. After the change they pass. The spend test fails under a cap-rate mutant (M-S1A-7 below) and the epochs test fails under an unpriced-null mutant (M-S1A-6).

### Requirement 5 — headline table checking both halves of the target, for 0.80 and for 0.90, stating whether the stage-2 trigger fires, from data only

**Built:** `target_check_rows(results)` computes, per target level and per F−N construction, (1) the **calibration half** — every d = 0.20 cell under the construction passes the calibration check — and (2) the **power half** — at the 1,200-epoch budget (400 pairs, null_per_pair = 1.0) all nine (p_P, p_N) baseline cells reach the target on the effect axis. The stage-2 trigger fires when either half is unmet. `summary_md` renders the table for 0.80 and 0.90 and prints the trigger per target. Every cell of the table is read from the simulated results; nothing is hardcoded.

**Definition note:** the #685 issue body is not readable from this container (no token, network use forbidden). The calibration-plus-power definition above is this record's stated reading of "both halves of the target", implemented in `target_check_rows` and printed in `summary.md`; it is recorded as limit 5 of the findings document. If the spec means something else, the table is the seam to change.

**Tests that pin it:** `test_target_check_states_both_halves_for_0_80_and_0_90_from_data_only`, `test_stage2_trigger_fires_when_the_power_half_is_unmet`, `test_stage2_trigger_reads_each_target_from_its_own_power_half` (0.85 power data: 0.80 met, 0.90 unmet, each target reported from its own half), `test_stage2_trigger_fires_when_the_calibration_half_fails`, and `test_committed_smoke_summary_reports_the_target_check`.

**Red phase observed:** before the change all four target-check tests failed — `summary_md` had no `## Target check` section. After the change they pass. In the smoke run the table reads: calibration half holds for all four construction rows; power half unmet (5/9, 8/9, 4/9, 7/9 cells reached); stage-2 trigger fires at 0.80 and at 0.90 — computed from the 20-replicate data, and stated there as noise, not a finding.

### Requirement 6 — tests that turn every mutant the #694 verdict listed red, plus a test of its own for the exit-on-calibration-failure path

**Caveat, stated plainly:** the #694 verdict comment (PR #694, issue comment 5902938377) could not be read from this container — no GitHub token, and the ticket forbids network use. The mutants enumerated here are the defect classes the #695 ticket names and the classes the rebuild requirements 1, 2, 4 and 5 put on the page. Any mutant the unreadable verdict listed outside these classes is unattested.

**Built, exit path:** `main()` gained keyword-only `grid` and `pass_alpha` inputs (CLI unchanged) so the exit-on-calibration-failure path is exercisable without a long run. `test_main_exits_non_zero_when_calibration_fails` drives a non-baseline design (null_per_pair = 0.5) under pass alpha 0.6 and asserts exit code 1; `test_main_exits_zero_when_calibration_holds` is the control at the registered rule.

**Red phase observed:** before the seam the exit tests failed with `TypeError` (unexpected keyword arguments). After the seam both pass. With the mutant `return 0 if all_hold else 1` → `return 0`, the failure-path test turns red and the control stays green — not an empty-cell kill.

**Campaign:** `scripts/mutation_receipt.py --select 695-stage1a` on the committed tree recorded eleven M-S1A cases; **all eleven KILLED**, production tree byte-unchanged (digest `52f968c36c4bb634ec6412e125d640f79f51c94ff01cd6f1d241c923282bcffe`). Record: `docs/assurance/stage1a-regime-685-mutation-receipt.json`, prose companion `docs/assurance/stage1a-regime-685-mutation-receipt.md`, indexed in `docs/receipts-index.md`.

| mutant | mutation | killing assertion |
|---|---|---|
| M-S1A-1 | exit-on-calibration-failure returns 0 anyway | `test_main_exits_non_zero_when_calibration_fails` |
| M-S1A-2 | direct F−N grid bound compared unscaled | `test_every_decision_equals_the_engine_bound_for_each_stage1_design[direct-1.0]` |
| M-S1A-3 | direct F−N terminal bound drops `2*bound − 1` | `test_direct_terminal_bounds_equal_the_engine_bounds` |
| M-S1A-4 | allocations compared at a fixed 400-pair cap | `test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations` |
| M-S1A-5 | double-null design draws one Null epoch per pair | `test_null_allocation_uses_exactly_the_declared_observations` |
| M-S1A-6 | epoch profile omits Null epochs | `test_expected_epochs_track_the_null_allocation_profile` |
| M-S1A-7 | expected spend priced at the cap rate | `test_every_per_look_row_carries_expected_epochs_and_expected_spend` |
| M-S1A-8 | stage-2 trigger hardcoded to never fire | `test_stage2_trigger_fires_when_the_power_half_is_unmet` |
| M-S1A-9 | calibration half assumed to hold | `test_stage2_trigger_fires_when_the_calibration_half_fails` |
| M-S1A-10 | power half assumed reached | `test_stage2_trigger_fires_when_the_power_half_is_unmet` |
| M-S1A-11 | headline smallest-d inequality inverted | `test_target_check_states_both_halves_for_0_80_and_0_90_from_data_only` |

M-S1A-4 and M-S1A-11 also reddened `test_stage1_grid_has_expected_structure` and `test_stage2_trigger_fires_when_the_power_half_is_unmet` respectively, by name, in the same receipt run.

### Requirement 8 — a PR body that describes exactly what the diff contains

This file. It lists all ten files in the diff, the smoke command and its 20-replicate count, the filter applied to the committed TSVs, the mutation campaign, the gate results, and the unreadable companions. It is committed at `.scratch/issue-695/pr-body.md` on the branch.

## Compound gate

Run on this branch after the last code commit, with `PYTHONHASHSEED=0` (the suite requires it; the unset-env run's five `test_pythonhashseed_set` failures are environmental and pass once the variable is set — verified by re-running those files):

```bash
ruff check src tests scripts                                          # All checks passed
ruff format --check src tests scripts                                 # 423 files already formatted
mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py
                                                                     # Success: no issues found in 383 source files
PYTHONHASHSEED=0 python -m pytest -q -n 4 -m "not live and not calibration and not assurance"
                                                                     # 3712 passed, 40 skipped, 2 xfailed
PYTHONHASHSEED=0 python -m pytest -q -m calibration -p no:randomly   # 34 passed, 1 skipped (inspect_ai absent)
python scripts/drift_check.py                                        # DRIFT CHECK: PASS - all 22 live contracts hold
PYTHONHASHSEED=0 python -m pytest tests/test_simulate_stage1a_regime_685.py tests/test_simulate_stage1a_regime_684.py tests/test_simulate_a_design_650.py tests/test_receipts_index.py tests/test_mutation_receipt.py -q
                                                                     # all green
```

## Which test covers which criterion

| criterion | covering tests |
|---|---|
| requirement 1 (direct F−N scale) | `test_every_decision_equals_the_engine_bound_for_each_stage1_design[direct-*]`, `test_direct_terminal_bounds_equal_the_engine_bounds`; mutants M-S1A-2, M-S1A-3 |
| requirement 2 (equal total epochs) | `test_stage1_grid_holds_each_epoch_budget_constant_across_null_allocations`; mutant M-S1A-4 |
| requirement 4 (E[total epochs], expected spend, MC SE) | `test_every_per_look_row_carries_expected_epochs_and_expected_spend`, `test_expected_epochs_track_the_null_allocation_profile`, `test_every_terminal_row_carries_mc_se_expected_epochs_and_cap_price`, `test_surface_rows_carry_expected_epochs_and_expected_spend_beside_the_cap_price`; mutants M-S1A-6, M-S1A-7 |
| requirement 5 (target check, stage-2 trigger) | `test_target_check_states_both_halves_for_0_80_and_0_90_from_data_only`, `test_stage2_trigger_fires_when_the_power_half_is_unmet`, `test_stage2_trigger_reads_each_target_from_its_own_power_half`, `test_stage2_trigger_fires_when_the_calibration_half_fails`; mutants M-S1A-8, M-S1A-9, M-S1A-10, M-S1A-11 |
| requirement 6 (mutants; exit path) | the mutation receipt (eleven kills, above); `test_main_exits_non_zero_when_calibration_fails` + control; mutant M-S1A-1 |
| requirement 8 (this PR body) | `.scratch/issue-695/pr-body.md` |
| AC2 (row schema) | `test_committed_smoke_per_look_rows_carry_the_full_schema`, `test_committed_smoke_terminal_rows_carry_mc_se_and_price_lines` |
| AC3 (output path, smoke data) | the `committed_smoke` tests; the smoke command recorded above |
| AC4 (#684 controls; new negative control) | the 12 tests in `tests/test_simulate_stage1a_regime_684.py`; `test_calibration_fails_for_loosened_rule_under_non_baseline_design`, `test_calibration_fails_when_pass_alpha_is_loosened`, `test_main_exits_zero_when_calibration_holds` |
| AC5 (no calls, no spend) | the grep command recorded above; the code path it covers |

## What was not done, and what does not exist

- **The full grid has not run.** 756 cells at 2,000 replicates belongs to part (b), #696. The ticket's revisit clause — a single build completing the full grid — is not met; #696 remains necessary and is not subsumed.
- **The #685 issue body and the #694 verdict comment do not exist in this container.** They live on GitHub and cannot be read offline. The target halves definition and the mutant list above are this record's stated readings, marked as such.
- **Operating characteristics are not claimed.** The smoke numbers at 20 replicates are schema evidence. The findings document and its receipts-index entry refuse any operating-characteristic claim from them.
- **No prose companion digest drift.** `tests/test_mutation_receipt.py` checks the receipt JSON against the live simulator bytes and the prose companion against the receipt digest; both pass on this branch.

## Next action

Run the full grid (#696) at 2,000 replicates, commit the output under `docs/findings/data/stage1a-regime-685/` as the gate allows, and read the target check and stage-2 trigger off those numbers before any paid run is sized from them.
