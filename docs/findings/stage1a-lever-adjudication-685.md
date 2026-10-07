# Lever adjudication for the registered Stage 1A rule (#685)

**Date:** 2026-09-29. **Updated:** 2026-09-30 by #695; 2026-10-02 by #696 (the full grid); 2026-10-03 by the ruling on #696 (stage wording only, no figure changed). **Script:** `scripts/screens/419/simulate_stage1a_regime_685.py`. **Test:** `tests/test_simulate_stage1a_regime_685.py`. **Data:** `docs/findings/data/stage1a-regime-685/` (756 configurations at 2,000 replicates, seed 685; the earlier 20-replicate smoke run is in its `smoke/` subdirectory and is schema evidence only). **Model calls:** none. **Network calls:** none. **Spend:** none.

**Status:** the Stage 1 grid the script defines has run in full: anytime stopping only, at the 300- and 1,200-epoch budgets. No anytime stage-1 design reaches the power target at 0.80 or at 0.90, at either budget, and the script's stage-2 trigger fires for both targets. **The fixed-n look is lever 4 and belongs to Stage 2 (ruling of 2026-10-03, #696 comment 5970254900); `simulate_stage1a_regime_685.py` has no fixed-n stopping rule and every committed row has `stopping` = `anytime`, so no claim here covers a fixed-n design** (see Limits, item 3). Calibration holds in every configuration where a PASS or a CUT would be an error, and the script's exit code is 0. The original 200-replicate tables treated missing Null epochs as zero outcomes and used one Null epoch where the double-Null design declares two; they did not simulate the declared designs and stay withdrawn.

## Why this record exists

#684 measured the registered design (97 pairs, 1:1:1) at p_P, p_N in {0.30, 0.35, 0.40} and found P(PASS) at most 0.055 in the observed cell and at most 0.321 anywhere on its grid, with P(CUT) never sized below d = 0.20. This record reports the Stage 1 simulation that varies null allocation and F-N construction against that baseline.

The four levers are:
1. **Pairs** (cap at 400).
2. **Null allocation at fixed total epochs** (null_per_pair in {0.5, 1, 2}).
3. **F - N construction** (registered union bound vs direct one-sided bound).
4. **Optional stopping** (anytime-valid vs fixed-n look).

Stage 1 varies levers 2 and 3 at two epoch budgets, under the registered anytime rule. Levers 1 and 4 are Stage 2 (#685, "Two stages, cheapest lever first") and are outside this simulation: the script's docstring says so, and its `Design.stopping` field defaults to `anytime`, which no simulation path changes.

## Pairing statement

Full and Placebo are paired by launch index; under independent draws this confers no matched-pairs advantage.

## What was simulated

**Stage 1 grid.** Null allocation x F-N construction, at fixed 300- and 1,200-epoch budgets. Null allocation levels: 0.5 (strictly alternating, Null-A after even-numbered pairs), 1.0 (every pair), 2.0 (every pair, two Null draws). The resulting Full/Placebo pair counts are 120, 100 and 75 at 300 epochs, and 480, 400 and 300 at 1,200 epochs. F-N constructions: union (registered: LB(mu_F) at alpha/2 minus UB(mu_N) at alpha/2) and direct (one-sided bound on the Full-minus-mean-Null observation at alpha). The direct construction uses only scheduled Null looks; it averages the two Null draws at a double-Null look.

**Baseline design.** #684 ran n_full = n_placebo = n_null = 97, total_epochs = 291, null_per_pair = 1.0. The lower allocation budget is 300 epochs because it is the smallest budget at or above 291 that divides exactly across every declared allocation. The 1,200-epoch budget retains the 400-pair 1:1:1 design.

**Effect axis.** d = p_F - p_P in {0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40}. Baselines p_P, p_N in {0.30, 0.35, 0.40}.

**Monte Carlo.** 7 effects x 9 baseline cells x 6 designs x 2 F-N constructions = 756 configurations, 2,000 replicates each, seed 685, anytime stopping only. The draws are seeded per cell on (seed, p_F, p_P, p_N). MC SE of a proportion at 2,000 replicates is at most 0.0112 (at P = 0.5), 0.0032 at the PASS level 0.0209 and 0.0049 at the CUT level 0.05. The run was launched 2026-10-01T23:50Z and finished 2026-10-02; `per_look.tsv` and `terminal_states.tsv` are its output with line endings normalised to LF by the repository's pre-commit hook. `summary.md` was rebuilt from those two files by `--rebuild` (#712), with no simulation.

**Every look is recorded.** The rule at a look does not depend on the cap, so a replicate that stops at look k counts as stopped for every cap >= k. `per_look.tsv` carries P(PASS), P(CUT), P(CANT_TELL_YET), the MC SE of P(PASS), E[pairs], E[total epochs], an expected-spend price line (E[total epochs] x $0.083 and x $0.087), the cap price and the replicate count for every configuration at every look. Any smaller cap can be read from it.

**Target check.** A design meets the target at effect d when both halves hold in every cell where both true contrasts equal d (ruling of 2026-10-02, #696 comment 5944534509). On this grid that is the p_P = p_N diagonal (0.30, 0.35, 0.40): the minimum over those three cells of P(PASS) at d = 0.30 and of P(CUT) at d = 0.10, each against the target in {0.80, 0.90}. The six off-diagonal cells are sensitivity, not the target. The check is price-free. The stage-2 trigger for a target fires when no design family reaches that target on the diagonal at either budget.

## Results

Every figure is P at the final look of its configuration, read from `per_look.tsv`.

### Headline table, targets 0.80 and 0.90

| epochs | Null per pair | F-N | pairs | min P(PASS) at d = 0.30 | min P(CUT) at d = 0.10 | target 0.80 | target 0.90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 300 | 0.5 | union | 120 | 0.0000 | 0.1900 | not reached | not reached |
| 300 | 0.5 | direct | 120 | 0.0100 | 0.1900 | not reached | not reached |
| 300 | 1.0 | union | 100 | 0.0015 | 0.1680 | not reached | not reached |
| 300 | 1.0 | direct | 100 | 0.0245 | 0.1680 | not reached | not reached |
| 300 | 2.0 | union | 75 | 0.0010 | 0.1310 | not reached | not reached |
| 300 | 2.0 | direct | 75 | 0.0225 | 0.1310 | not reached | not reached |
| 1,200 | 0.5 | union | 480 | 0.0170 | 0.5070 | not reached | not reached |
| 1,200 | 0.5 | direct | 480 | 0.1560 | 0.5070 | not reached | not reached |
| 1,200 | 1.0 | union | 400 | 0.0195 | 0.4585 | not reached | not reached |
| 1,200 | 1.0 | direct | 400 | 0.2335 | 0.4585 | not reached | not reached |
| 1,200 | 2.0 | union | 300 | 0.0235 | 0.3525 | not reached | not reached |
| 1,200 | 2.0 | direct | 300 | 0.2255 | 0.3525 | not reached | not reached |

The best PASS half is 0.2335 (1,200 epochs, Null per pair 1.0, direct) and the best CUT half is 0.5070 (1,200 epochs, Null per pair 0.5, either construction). No value in this headline table is within 2 MC SE of 0.80 or of 0.90 (the nearest is more than 20 SE away), so no threshold crossing is claimed or denied on Monte Carlo noise.

**Stage-2 trigger statement.** No anytime stage-1 design family meets the price-free diagonal target at either budget, for 0.80 or for 0.90. The script's stage-2 trigger fires for both targets. It fires on the data: the diagonal contains no cell where an alternative sits at its own null, so the result is not forced by the construction of the grid. The statement is about the anytime designs only, and Stage 1 contains no others. #685 describes the gap between an anytime design and a fixed-n look at the same alpha and the same n as "the price of the right to stop early"; this grid has no fixed-n row (every row has `stopping` = `anytime`) and cannot say whether a fixed-n design at these budgets reaches the target. That measurement is Stage 2's lever 4.

### Per-lever marginals

Each figure is the mean, over the levels of the other lever, of the diagonal minimum at 1,200 epochs.

| lever | level | P(PASS) at d = 0.30 | P(CUT) at d = 0.10 | P(PASS) at d = 0.40 |
| --- | --- | --- | --- | --- |
| Null per pair | 0.5 | 0.0865 | 0.5070 | 0.7395 |
| Null per pair | 1.0 | 0.1265 | 0.4585 | 0.8362 |
| Null per pair | 2.0 | 0.1245 | 0.3525 | 0.8273 |
| F-N construction | union | 0.0200 | 0.4393 | 0.6563 |
| F-N construction | direct | 0.2050 | 0.4393 | 0.9457 |

- **Null allocation** trades the two halves against each other. Fewer Null epochs leave more pairs, and P(CUT) at d = 0.10 rises from 0.3525 to 0.5070 as Null per pair falls from 2.0 to 0.5. P(PASS) at d = 0.30 moves the other way and is highest at 1.0 or 2.0. No allocation helps both halves.
- **F-N construction** moves only the PASS half. P(CUT) is identical across the two constructions in every one of the 378 matched configurations (maximum difference 0.0), as it must be: CUT reads F - P only. On the diagonal at d = 0.30 and 1,200 epochs the direct form gives 0.1560 to 0.2335 where the union form gives 0.0170 to 0.0235. At d = 0.40 the direct form's diagonal minimum is 0.9105, 0.9780 and 0.9485 at Null per pair 0.5, 1.0 and 2.0; the union form's is 0.5685, 0.6945 and 0.7060.
- **Budget.** At 300 epochs no design exceeds 0.0245 on the PASS half or 0.1900 on the CUT half.

### Calibration

- **PASS where a PASS is an error.** 480 configurations have a true F - P or a true F - N at or below 0.20. The largest P(PASS) among them is 0.0080, at (p_P 0.30, p_N 0.40), d = 0.30, direct, 1,200 epochs, Null per pair 0.5: the F - N margin cell. The nominal level is 0.0209 and the limit with 3 MC SE is 0.0305.
- **CUT where a CUT is an error.** 432 configurations have a true F - P at or above 0.20. The largest P(CUT) is 0.0360, at (0.35, 0.35), d = 0.20, 1,200 epochs, Null per pair 1.0. The nominal level is 0.05 and the limit with 3 MC SE is 0.0646. By effect the maximum is 0.0360 at d = 0.20, 0.0140 at 0.25, 0.0050 at 0.30 and 0.0020 at 0.40.
- The script's calibration read covers both kinds of cell (#712), and `--rebuild` on the committed data exits 0.

### Sensitivity

The off-diagonal minima are in `summary.md` under "Sensitivity (off-diagonal cells)". At 1,200 epochs the off-diagonal minimum P(PASS) at d = 0.30 is at most 0.0080, because the six off-diagonal cells include (0.30, 0.40), where the F - N contrast sits at its own margin. They do not enter the target check.

### Price lines

The target check is price-free. These rows are for the operator's gate, which reads expected spend at list rates for the decision and the cap price as the exposure.

| epochs | price at $0.083 per epoch | price at $0.087 per epoch | cap at $0.30 per epoch |
| --- | --- | --- | --- |
| 300 | $24.90 | $26.10 | $90.00 |
| 1,200 | $99.60 | $104.40 | $360.00 |

Expected epochs on the diagonal, from `per_look.tsv`:

| epochs | Null per pair | F-N | E[epochs] at d = 0.30 | E[epochs] at d = 0.10 |
| --- | --- | --- | --- | --- |
| 1,200 | 0.5 | union | 1,188 to 1,190 | 800 to 838 |
| 1,200 | 0.5 | direct | 1,117 to 1,122 | 800 to 838 |
| 1,200 | 1.0 | union | 1,185 to 1,191 | 863 to 876 |
| 1,200 | 1.0 | direct | 1,066 to 1,079 | 863 to 876 |
| 1,200 | 2.0 | union | 1,182 to 1,188 | 925 to 955 |
| 1,200 | 2.0 | direct | 1,079 to 1,087 | 925 to 955 |

At 300 epochs every design runs close to its cap at d = 0.30 (296 to 300 expected epochs) and at d = 0.10 (266 to 278). No anytime design reaches the target, so no row here prices a design that meets it.

## Crashed-look and void-epoch rules

skill-harness #697 owns the crashed-look rule and the void-epoch rule for the next paid run; this record states neither.

## Finding

Under the declared independent-Bernoulli model and anytime stopping, neither null allocation nor the F-N construction brings the registered Stage 1A rule to P(PASS) >= 0.80 at d = 0.30 together with P(CUT) >= 0.80 at d = 0.10, at 300 or at 1,200 epochs. The direct F-N construction raises P(PASS) about tenfold over the registered union construction at 1,200 epochs and stays inside the PASS level in every cell where a PASS would be an error; it still leaves every design short at d = 0.30. The rule keeps its error rates throughout the grid.

This record does not decide whether to file a pre-registration amendment for the direct form, what Stage 2 is, whether the margin or the d = 0.30 target should change, or anything about price. Those belong to the owner of the pre-registration and to the operator's gate. No pre-registration text, threshold, estimand or harness file was edited to produce it.

## Model statement

The grid establishes the operating characteristics of the registered rule under the declared independent-Bernoulli model at the stated baselines and effect sizes. It does not establish how many real Claude Code epochs are required, and it says nothing about dependence between epochs.

## Relation to #684

This record changes no #684 code, test or number. The #684 script, its test file and `stage1a-regime-operating-characteristics.md` are untouched. The negative controls in `tests/test_simulate_stage1a_regime_684.py` still run. The #695 negative controls loosen the pass alpha to 0.6 and show calibration failure for both the baseline design and a half-Null non-baseline design.

## Mutation assurance

Twelve mutants are registered in `scripts/mutation_receipt.py` under obligation prefix `695-stage1a`, with further campaigns under #708 (the diagonal aggregation and the pinned constants) and #712 (the sensitivity sentence, the CUT half of the calibration read and the rebuild path). The campaign records are under `docs/assurance/` and indexed in `docs/receipts-index.md`. The rebuild path's tests are known to be weak against three mutants; that is skill-harness #715.

## Reproduction

`python scripts/screens/419/simulate_stage1a_regime_685.py --out <dir> --rebuild` on a copy of the data directory rewrites `summary.md` from `per_look.tsv` and `terminal_states.tsv` and returns the calibration exit code. A cell is reproduced by running the script's `run_cell` at seed 685 and 2,000 replicates for that cell's (p_F, p_P, p_N) and design; the per-cell seeding makes a cell independent of the rest of the grid. The independent reproduction of a sample of cells is on the pull request for #696.

## Limits of this simulation

1. **The draws are independent Bernoulli.** This record contains no dependence model.
2. **Void epochs are not modelled.** Every draw is a valid epoch.
3. **Only anytime stopping ran.** Stage 1 is levers 2 and 3; the fixed-n look is lever 4 and belongs to Stage 2 (#685, "Two stages, cheapest lever first"). #685 rebuild requirement 3 defines Stage 1 as levers 2 and 3 "anytime and fixed-n, at caps 97 and 400", and #696 repeats it; the ruling of 2026-10-03 (#696 comment 5970254900) reads the words "anytime and fixed-n" as a drafting error against the ticket's own staging, so the grid here is the full Stage 1 grid. The merged script has no fixed-n stopping rule (its `Design.stopping` field defaults to `anytime`, and no simulation path changes it), and it compares allocations at equal 300- and 1,200-epoch budgets (requirement 2) where requirement 3 names caps of 97 and 400 pairs; the 400-pair design is the Null-per-pair-1.0 row at 1,200 epochs, and a 97-pair cap reads off the per-look rows of the 100-pair design. The stage-2 trigger statement holds for anytime designs only; this record measures no fixed-n design at any budget.
4. **The grid has no uptake axis.** The effect axis is the intention-to-treat difference; no configuration varies how often the card is taken up (#696 comment 5954740080, a lead for the Stage 2 design and not a finding).
5. **The terminal bounds are summarised by quantiles.** The per-replicate values are not stored.
6. **The committed data files carry five decimal places.** A fresh run now writes ten (#712). The rebuild re-reads the five-place columns, so a value in `summary.md` can differ from the as-run summary in its last printed digit; none of the figures in this record is affected.

*Revisit if:* the engine's `one_sided_betting_bound` changes; then re-run the surface. Or the target is redefined as a worst case over the whole baseline neighbourhood; then the grid must be restricted to cells where both contrasts exceed the margin at the target d, and this record must say so.
