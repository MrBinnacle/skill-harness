# Lever adjudication for the registered Stage 1A rule (#685)

**Date:** 2026-09-29. **#695 (part a) additions:** 2026-09-30. **Script:** `scripts/screens/419/simulate_stage1a_regime_685.py`. **Test:** `tests/test_simulate_stage1a_regime_685.py`. **Mutation receipt:** `docs/assurance/stage1a-regime-685-mutation-receipt.md`. **Data:** `docs/findings/data/stage1a-regime-685/`. **Model calls:** none. **Network calls:** none. **Spend:** none.

**Status:** no operating-characteristic result is published. The committed data are a smoke run at 20 replicates, kept to show the output schema. The original 200-replicate tables treated missing Null epochs as zero outcomes and used one Null epoch where the double-Null design declares two. They did not simulate the declared designs and are withdrawn.

## Why this record exists

#684 measured the registered design (97 pairs, 1:1:1) at p_P, p_N in {0.30, 0.35, 0.40} and found P(PASS) at most 0.055 in the observed cell and at most 0.321 anywhere on its grid, with P(CUT) never sized below d = 0.20. This record defines the Stage 1 simulation required to vary null allocation and F-N construction against that baseline. It does not adjudicate the four levers until the corrected full grid runs.

The four levers are:
1. **Pairs** (cap at 400).
2. **Null allocation at fixed total epochs** (null_per_pair in {0.5, 1, 2}).
3. **F - N construction** (registered union bound vs direct one-sided bound).
4. **Optional stopping** (anytime-valid vs fixed-n look).

## Pairing statement

Full and Placebo are paired by launch index; under independent draws this confers no matched-pairs advantage.

## What was simulated

**Stage 1 grid.** Null allocation x F-N construction, at fixed 300- and 1,200-epoch budgets. Null allocation levels: 0.5 (strictly alternating, Null-A after even-numbered pairs), 1.0 (every pair), 2.0 (every pair, two Null draws). The resulting Full/Placebo pair counts are 120, 100 and 75 at 300 epochs, and 480, 400 and 300 at 1,200 epochs. F-N constructions: union (registered: LB(mu_F) at alpha/2 minus UB(mu_N) at alpha/2) and direct (one-sided bound on the Full-minus-mean-Null observation at alpha). The direct construction uses only scheduled Null looks; it averages the two Null draws at a double-Null look. Allocations are compared at equal total epochs: `pairs_for_epoch_budget` spends each budget exactly.

**Baseline design.** #684 ran n_full = n_placebo = n_null = 97, total_epochs = 291, null_per_pair = 1.0. The lower allocation budget is 300 epochs because it is the smallest budget at or above 291 that divides exactly across every declared allocation. The 1,200-epoch budget retains the 400-pair 1:1:1 design.

**Effect axis.** d = p_F - p_P in {0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40}. Baselines p_P, p_N in {0.30, 0.35, 0.40}.

**Monte Carlo.** The smoke run committed under `docs/findings/data/stage1a-regime-685/` used 20 replicates per cell, seed 685, 8 workers; it exited 0, every calibration cell inside the limit (0.0209 + 3 SE of 20 replicates = 0.11686). Its numbers are schema evidence, not operating characteristics. The full grid defaults to 2,000 replicates per cell. The draws are seeded per cell on (seed, p_F, p_P, p_N).

**Output rows.** Every row of `per_look.tsv` and `terminal_states.tsv` carries `n_full`, `n_placebo`, `n_null`, `total_epochs`, `null_per_pair`, `fn_construction`, `stopping`, the replicate count and an MC SE (`se_pass` in the per-look rows, `se_share` in the terminal rows). Per-look rows also carry E[total epochs] at that look and an expected-spend price line beside the cap price. Terminal rows carry E[total epochs] at the cap, the expected spend, and the cap price. The rule at a look does not depend on the cap, so a replicate that stops at look k counts as stopped for every cap >= k; any smaller cap can be read from a full `per_look.tsv`.

**Smoke command (20 replicates):**

```bash
python scripts/screens/419/simulate_stage1a_regime_685.py --out docs/findings/data/stage1a-regime-685 --replicates 20 --seed 685 --workers 8
```

**What is committed.** The repository's pre-commit gate refuses any added file above 500 KB, and the full smoke `per_look.tsv` is 29 MB. The committed files are therefore filtered views of that run, and nothing else:

- `per_look.tsv` (2,198 rows): every design x cell at look 1 and at the cap look, plus every look of the diagonal cell family (p_P = p_N = 0.35) at the 300-epoch budget, union construction, null_per_pair = 1.0. Every design-field value on the grid appears at least once.
- `terminal_states.tsv` (1,512 rows): every joint state of every cell at the 300-epoch budget, all six null-allocation x construction designs.
- `summary.md` (unfiltered): the surface table, both headline tables, the target check, and the price lines.

Regenerate the unfiltered output with the command above; the committed files are schema evidence, not the run's full record.

## Target check and the stage-2 trigger

The Stage 1 target has two halves, both read from the simulated results:

1. **Calibration half.** Every d = 0.20 cell under a construction passes the calibration check: P(PASS) at or below 0.0209 + 3 SE of the replicate count.
2. **Power half.** At the 1,200-epoch budget (400 pairs, null_per_pair = 1.0) all nine (p_P, p_N) baseline cells reach the target level on the effect axis.

The headline table in `summary.md` reports both halves for target levels 0.80 and 0.90, per F-N construction, and states whether the stage-2 trigger fires. The trigger fires when either half is unmet; stage 2 is the pair-cap and optional-stopping levers. In the smoke run the power half is unmet at both target levels, so the trigger fires at 0.80 and at 0.90. That reading will move when the full grid runs; the trigger's direction at 20 replicates is noise, not a finding.

## Crashed-look rule and void-epoch rule for the next paid run

**Crashed-look rule:** If a look crashes after at least two valid epochs, the look is void and the run continues from the next look. If the crash occurs at look 1, the entire cell is void and must be rerun.

**Void-epoch rule:** An epoch that produces no model output (timeout, error, or empty response) is void and excluded from the bound calculation. The run continues; void epochs do not count toward the pair cap.

## Finding

The prior tables cannot support a claim about calibration, power, price, a binding condition, or the relative effect of any lever. The script now executes the declared Null allocation, prices E[total epochs] beside the cap price on every row, and computes the target check and stage-2 trigger from data only. The committed smoke run shows the schema at 20 replicates and exits 0 on calibration. A full Stage 1 run is the next action. The pair-cap and optional-stopping levers remain unimplemented Stage 2 work; #696 owns the full grid.

## Model statement

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Relation to #684

This record changes no #684 code, test or number. The #684 script, its test file and `stage1a-regime-operating-characteristics.md` are untouched. The negative controls in `tests/test_simulate_stage1a_regime_684.py` still run. The negative controls in `tests/test_simulate_stage1a_regime_685.py` loosen the pass alpha to 0.6 and show calibration failure for both the baseline design and a half-Null design (`null_per_pair = 0.5`, a non-baseline allocation). The exit-on-calibration-failure path has its own test: `test_main_exits_non_zero_when_calibration_fails` drives that non-baseline design under the loosened rule and asserts exit code 1, while `test_main_exits_zero_when_calibration_holds` is the control.

## Mutation campaign

`scripts/mutation_receipt.py --select 695-stage1a` recorded eleven M-S1A cases against this script at `sha256:52f968c36c4bb634ec6412e125d640f79f51c94ff01cd6f1d241c923282bcffe`. All eleven were KILLED by their named assertions; the machine record is `docs/assurance/stage1a-regime-685-mutation-receipt.json`. The #694 verdict comment could not be read from the generating container (no token, no network), so mutants outside these eleven named classes are unattested.

## Limits of this simulation

1. **The draws are independent Bernoulli.** This record contains no dependence model.
2. **Void epochs are not modelled.** Every draw is a valid epoch.
3. **The full grid has not been run.** The grid contains 756 cells at 2,000 replicates. The committed data are a 20-replicate smoke run. The full grid must run before a paid run is sized from its results.
4. **The terminal bounds are summarised by quantiles.** The per-replicate values are not stored.
5. **The target halves are this record's stated definition.** The #685 issue body is not readable from the container that built #695; the calibration-plus-power definition above is what `target_check_rows` implements and what the headline table reports.

*Revisit if:* the engine's `one_sided_betting_bound` changes. Then re-run the surface. The vectorised terminal bound in `terminal_bounds` repeats the engine's grid scan and bisection, and `test_terminal_bounds_equal_the_engine_bounds` fails if the two drift apart.
