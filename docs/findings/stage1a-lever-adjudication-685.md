# Lever adjudication for the registered Stage 1A rule (#685)

**Date:** 2026-09-29. **Script:** `scripts/screens/419/simulate_stage1a_regime_685.py`. **Test:** `tests/test_simulate_stage1a_regime_685.py`. **Data:** `.scratch/issue-685/data/` (`per_look.tsv`, `terminal_states.tsv`, `summary.md`). **Model calls:** none. **Network calls:** none. **Spend:** none.

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Why this record exists

#684 measured the registered design (97 pairs, 1:1:1) at p_P, p_N in {0.30, 0.35, 0.40} and found P(PASS) at most 0.055 in the observed cell and at most 0.321 anywhere on its grid, with P(CUT) never sized below d = 0.20. This record varies each of the four design levers alone against that baseline, then combines, to find which lever moves the operating characteristics most.

The four levers are:
1. **Pairs** (cap at 400).
2. **Null allocation at fixed total epochs** (null_per_pair in {0.5, 1, 2}).
3. **F - N construction** (registered union bound vs direct one-sided bound).
4. **Optional stopping** (anytime-valid vs fixed-n look).

## Pairing statement

Full and Placebo are paired by launch index; under independent draws this confers no matched-pairs advantage.

## What was simulated

**Stage 1 grid.** Null allocation x F-N construction, at caps 97 and 400. Null allocation levels: 0.5 (strictly alternating, Null-A after even-numbered pairs), 1.0 (every pair), 2.0 (every pair, two Null draws). F-N constructions: union (registered: LB(mu_F) at alpha/2 minus UB(mu_N) at alpha/2) and direct (one-sided bound on mu_F - mu_N at alpha).

**Baseline design.** n_full = n_placebo = n_null = 97, total_epochs = 291, null_per_pair = 1.0.

**Effect axis.** d = p_F - p_P in {0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40}. Baselines p_P, p_N in {0.30, 0.35, 0.40}.

**Monte Carlo.** 200 replicates per cell, seed 685. The draws are seeded per cell on (seed, p_F, p_P, p_N). The MC standard error of P(PASS) at the nominal 0.0209 is sqrt(0.0209 x 0.9791 / 200) = 0.01012. The calibration limit is 0.0209 + 3 SE = 0.05125.

**Every look is recorded.** The rule at a look does not depend on the cap, so a replicate that stops at look k counts as stopped for every cap >= k. `per_look.tsv` gives P(PASS), P(CUT), P(CANT_TELL_YET), the SE of P(PASS) and E[pairs] for every cell and every cap. Any smaller cap can be read from it.

## Crashed-look rule and void-epoch rule for the next paid run

**Crashed-look rule:** If a look crashes after at least two valid epochs, the look is void and the run continues from the next look. If the crash occurs at look 1, the entire cell is void and must be rerun.

**Void-epoch rule:** An epoch that produces no model output (timeout, error, or empty response) is void and excluded from the bound calculation. The run continues; void epochs do not count toward the pair cap.

## Findings

1. **Calibration holds for every design at d = 0.20.** Across all tested designs (baseline, half-null, double-null, direct construction), P(PASS) at the boundary is at most 0.005 against the limit of 0.05125. The rule is conservative at the boundary under every lever setting.

2. **The null allocation lever moves P(CUT) at d = 0.00 but has minimal effect on P(PASS) at d >= 0.25.** At d = 0.00, the null_per_pair = 0.5 design has fewer Null draws, so the F-N condition clears less often and fewer replicates are cut. At d >= 0.25, the dominant constraint is the F-P condition, which does not depend on the Null allocation.

3. **The direct F-N construction differs from the union bound.** The direct construction applies a single one-sided bound at alpha = 0.0209 to the paired difference mu_F - mu_N, while the union bound applies two bounds at alpha/2 = 0.01045 each. The direct construction is less conservative (one test instead of two), so it can produce higher P(PASS) at the same design.

4. **No design under $100 meets the default target at 97 pairs.** The default target is P(PASS) >= 0.80 at d = 0.30 and P(CUT) >= 0.80 at d = 0.10. At 97 pairs, the largest P(PASS) on the grid is below 0.80 for every design. The fork is genuine: relax the margin, accept a lower target, or stop testing this card on this world.

5. **The price of optional stopping is measurable.** For any design, the fixed-n pass rate at the same alpha and n gives the cost of the right to stop early. The anytime-valid rule pays for adaptivity by requiring more evidence than a fixed-horizon test.

## Model statement

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Relation to #684

This record changes no #684 code, test or number. The #684 script, its test file and `stage1a-regime-operating-characteristics.md` are untouched. The negative controls in `tests/test_simulate_stage1a_regime_684.py` still run, and one new negative control shows that calibration holds for non-baseline designs under the registered rule.

## Limits of this simulation

1. **The draws are independent Bernoulli.** This record contains no dependence model.
2. **Void epochs are not modelled.** Every draw is a valid epoch.
3. **The full grid has not been run.** The initial data files use 200 replicates on a subset of the grid. The full grid (630 cells at 2000 replicates) requires approximately 4 hours on 8 workers and should be run before a paid run is sized from these results.
4. **The terminal bounds are summarised by quantiles.** The per-replicate values are not stored.

*Revisit if:* the engine's `one_sided_betting_bound` changes. Then re-run the surface.
