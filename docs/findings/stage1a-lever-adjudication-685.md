# Lever adjudication for the registered Stage 1A rule (#685)

**Date:** 2026-09-29. **Script:** `scripts/screens/419/simulate_stage1a_regime_685.py`. **Test:** `tests/test_simulate_stage1a_regime_685.py`. **Model calls:** none. **Network calls:** none. **Spend:** none.

**Status:** no operating-characteristic result is published. The original 200-replicate tables treated missing Null epochs as zero outcomes and used one Null epoch where the double-Null design declares two. They did not simulate the declared designs and are withdrawn.

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

**Stage 1 grid.** Null allocation x F-N construction, at fixed 300- and 1,200-epoch budgets. Null allocation levels: 0.5 (strictly alternating, Null-A after even-numbered pairs), 1.0 (every pair), 2.0 (every pair, two Null draws). The resulting Full/Placebo pair counts are 120, 100 and 75 at 300 epochs, and 480, 400 and 300 at 1,200 epochs. F-N constructions: union (registered: LB(mu_F) at alpha/2 minus UB(mu_N) at alpha/2) and direct (one-sided bound on the Full-minus-mean-Null observation at alpha). The direct construction uses only scheduled Null looks; it averages the two Null draws at a double-Null look.

**Baseline design.** #684 ran n_full = n_placebo = n_null = 97, total_epochs = 291, null_per_pair = 1.0. The lower allocation budget is 300 epochs because it is the smallest budget at or above 291 that divides exactly across every declared allocation. The 1,200-epoch budget retains the 400-pair 1:1:1 design.

**Effect axis.** d = p_F - p_P in {0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40}. Baselines p_P, p_N in {0.30, 0.35, 0.40}.

**Monte Carlo.** The full grid has not run. Its command defaults to 2,000 replicates per cell, seed 685. The draws are seeded per cell on (seed, p_F, p_P, p_N).

**Every look is recorded.** The rule at a look does not depend on the cap, so a replicate that stops at look k counts as stopped for every cap >= k. The script writes `per_look.tsv` with P(PASS), P(CUT), P(CANT_TELL_YET), the SE of P(PASS) and E[pairs] for every cell and every cap. Any smaller cap can be read from it.

## Crashed-look rule and void-epoch rule for the next paid run

**Crashed-look rule:** If a look crashes after at least two valid epochs, the look is void and the run continues from the next look. If the crash occurs at look 1, the entire cell is void and must be rerun.

**Void-epoch rule:** An epoch that produces no model output (timeout, error, or empty response) is void and excluded from the bound calculation. The run continues; void epochs do not count toward the pair cap.

## Finding

The prior tables cannot support a claim about calibration, power, price, a binding condition, or the relative effect of any lever. The script now executes the declared Null allocation. A full Stage 1 run is the next action. The pair-cap and optional-stopping levers remain unimplemented Stage 2 work.

## Model statement

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Relation to #684

This record changes no #684 code, test or number. The #684 script, its test file and `stage1a-regime-operating-characteristics.md` are untouched. The negative controls in `tests/test_simulate_stage1a_regime_684.py` still run. The new negative controls loosen the pass alpha to 0.6 and show calibration failure for both the baseline and a half-Null design.

## Limits of this simulation

1. **The draws are independent Bernoulli.** This record contains no dependence model.
2. **Void epochs are not modelled.** Every draw is a valid epoch.
3. **The full grid has not been run.** The grid contains 756 cells at 2,000 replicates. It must run before a paid run is sized from its results.
4. **The terminal bounds are summarised by quantiles.** The per-replicate values are not stored.

*Revisit if:* the engine's `one_sided_betting_bound` changes. Then re-run the surface.
