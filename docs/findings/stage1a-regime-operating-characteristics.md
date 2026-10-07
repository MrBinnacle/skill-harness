# Operating characteristics of the Stage 1A rule in the regime that was run (#684)

**Date:** 2026-09-29. **Script:** `scripts/screens/419/simulate_stage1a_regime.py`. **Test:** `tests/test_simulate_stage1a_regime_684.py`. **Data:** `docs/findings/data/stage1a-regime-684/` (`per_look.tsv`, `terminal_states.tsv`, `summary.md`). **Model calls:** none. **Network calls:** none. **Spend:** none.

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Why this record exists

Stage 1A ran 97 Full/Placebo pairs with one Null draw per pair and stopped at CANT_TELL_YET at the cap. It observed Full 50/97, Placebo 34/97 and Null 34/97. The #650 simulator (`simulate_a_design.py`, record `a-design-sim-ledger-level.md`) holds the Null rate at 1/7 and caps the run at 60 pairs, so it cannot describe that run. This record simulates the registered rule at the observed design and at baselines around the observed 0.35.

This record is a diagnostic. It does not answer the allocation question, which is how many Null draws to run per pair at a fixed budget. That question belongs to #685.

## What was simulated

**Design:** n_full = 97, n_placebo = 97, n_null = 97, total_epochs = 291, null_per_pair = 1.00. Each look adds one draw to each of the three arms. The run goes to 97 looks.

**Pairing.** Full and Placebo are paired by launch index: the i-th Full draw pairs with the i-th Placebo draw, as x = (F - P + 1) / 2, mapped back by d = 2x - 1. The three arms are drawn independently. Under independent draws the pairing gives no matched-pairs advantage: the variance of F - P is the sum of the two arm variances, exactly as for unpaired arms. Any gain from pairing in real runs would have to come from dependence between the paired epochs. This model contains no such dependence.

**Rule.** The rule is the registered one. The code is the #650 `simulate_streams`, reused unchanged:

| Outcome | Condition |
| --- | --- |
| CUT (no_lift) | UB(F - P) < 0.20, one-sided at alpha 0.05 |
| PASS | LB(F - P) >= 0.20, one-sided at alpha 0.0209, **and** LB(mu_F) - UB(mu_N) >= 0.20, each one-sided at 0.0209 / 2 = 0.01045 |
| CANT_TELL_YET | anything else at the cap |

**Construction.** The bounds are the engine's `one_sided_betting_bound`, and the engine is consumed, not modified. The #650 grid machinery reads each decision from the engine's wealth grid, and it calls the bound function wherever the grid cannot settle a decision. Two tests pin exactness in this regime:

- The first checks every stopping look and outcome against the engine bound called at every look, on streams at baselines 0.25 to 0.40. It covers all three outcomes.
- The second covers the terminal bounds in the joint-state tally. Those are vectorised over replicates (`terminal_bounds`), and the test checks them against the engine to 1e-9.

**Grid.** p_P in {0.30, 0.35, 0.40} and p_N in {0.30, 0.35, 0.40}, all nine combinations. d = p_F - p_P in {0.20, 0.25, 0.30, 0.35, 0.40}. That makes 45 cells. Each d row has a role:

- 0.20 is **calibration**, the PASS null boundary.
- 0.25 is a **small real effect**.
- 0.30 to 0.40 are **real effects**.

**Monte Carlo.** 10,000 replicates per cell, seed 684. The draws are seeded per cell on (seed, p_F, p_P, p_N). The Monte Carlo standard error of P(PASS) at the nominal 0.0209 is sqrt(0.0209 x 0.9791 / 10000) = 0.00143. The per-cell SE of each estimate is in the tables. The replicate count was chosen so that the calibration limit, 0.0209 + 3 SE = 0.0252, sits within 0.0043 of the nominal level. The SE column in the surface table is the binomial standard error of each cell's own P(PASS) estimate. It is 0 where no replicate passed, so the calibration check uses the SE at the nominal 0.0209 instead. The whole grid took 48 minutes on 8 worker processes.

**Every look is recorded.** The rule at a look does not depend on the cap, so a replicate that stops at look k counts as stopped for every cap >= k. `per_look.tsv` gives P(PASS), P(CUT), P(CANT_TELL_YET), the SE of P(PASS) and E[pairs] for every cell and every cap from 1 to 97. That is 4,365 rows, each carrying the design fields. Any smaller cap can be read from it.

To reproduce:

```bash
python scripts/screens/419/simulate_stage1a_regime.py --out OUT --replicates 10000 --seed 684 --workers 8
```

The run is deterministic under the stated seed. It writes `OUT/per_look.tsv`, `OUT/terminal_states.tsv` and `OUT/summary.md`. It exits non-zero if any calibration cell fails.

## Findings

1. **The calibration holds with a wide margin.** Across the nine d = 0.20 cells, 2 of 90,000 replicates passed by 97 pairs. The largest cell rate is 0.0001, and the limit is 0.0252. The rule is far more conservative at the boundary than its alpha, as #650 also found.
2. **P(PASS) does not reach 0.80 by 97 pairs in any of the nine (p_P, p_N) cells.** The headline row reads "not reached on this grid" in every cell. The largest P(PASS) on the grid is 0.321, at p_P = 0.40, p_N = 0.30, d = 0.40.
3. **In the observed-regime cell, p_P = p_N = 0.35, CANT_TELL_YET at 97 pairs is the likely outcome across the whole grid.** P(CANT_TELL_YET) is 0.974 at d = 0.20, 0.991 at d = 0.25, 0.996 at d = 0.30, 0.989 at d = 0.35 and 0.944 at d = 0.40.
4. **A higher Null rate lowers the pass probability at a fixed d.** At p_P = 0.35 and d = 0.40, P(PASS) is 0.149 at p_N = 0.30, 0.055 at p_N = 0.35 and 0.013 at p_N = 0.40. The F - N condition compares LB(mu_F) with UB(mu_N) at alpha 0.01045 each. A higher p_N raises UB(mu_N), so the same Full rate clears the 0.20 margin less often.
5. **Both PASS conditions keep replicates open at the cap.** At p_P = p_N = 0.35 and d = 0.40, replicates open at the cap split as follows:
   - 41.8% of all replicates have F - P passing and F - N failing.
   - 0.7% have F - N passing and F - P failing.
   - 51.9% have neither passing.

   The joint-state table below gives the terminal bounds for each state. It is descriptive and does not name a single binding condition.

## Headline cell: p_P = p_N = 0.35, by cap

| d | role | p_F | cap | P(PASS) | P(CUT) | P(CANT_TELL_YET) | E[pairs] |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.20 | calibration | 0.55 | 33 | 0.0000 | 0.0177 | 0.9823 | 32.7 |
| 0.20 | calibration | 0.55 | 46 | 0.0000 | 0.0205 | 0.9795 | 45.5 |
| 0.20 | calibration | 0.55 | 60 | 0.0000 | 0.0230 | 0.9770 | 59.2 |
| 0.20 | calibration | 0.55 | 97 | 0.0000 | 0.0261 | 0.9739 | 95.3 |
| 0.25 | small real effect | 0.60 | 33 | 0.0000 | 0.0070 | 0.9930 | 32.9 |
| 0.25 | small real effect | 0.60 | 46 | 0.0000 | 0.0080 | 0.9920 | 45.8 |
| 0.25 | small real effect | 0.60 | 60 | 0.0002 | 0.0081 | 0.9917 | 59.7 |
| 0.25 | small real effect | 0.60 | 97 | 0.0002 | 0.0086 | 0.9912 | 96.3 |
| 0.30 | real effect | 0.65 | 33 | 0.0001 | 0.0030 | 0.9969 | 33.0 |
| 0.30 | real effect | 0.65 | 46 | 0.0003 | 0.0032 | 0.9965 | 45.9 |
| 0.30 | real effect | 0.65 | 60 | 0.0007 | 0.0032 | 0.9961 | 59.9 |
| 0.30 | real effect | 0.65 | 97 | 0.0013 | 0.0032 | 0.9955 | 96.7 |
| 0.35 | real effect | 0.70 | 33 | 0.0003 | 0.0010 | 0.9987 | 33.0 |
| 0.35 | real effect | 0.70 | 46 | 0.0016 | 0.0010 | 0.9974 | 46.0 |
| 0.35 | real effect | 0.70 | 60 | 0.0030 | 0.0010 | 0.9960 | 59.9 |
| 0.35 | real effect | 0.70 | 97 | 0.0100 | 0.0010 | 0.9890 | 96.7 |
| 0.40 | real effect | 0.75 | 33 | 0.0023 | 0.0006 | 0.9971 | 33.0 |
| 0.40 | real effect | 0.75 | 46 | 0.0074 | 0.0006 | 0.9920 | 45.9 |
| 0.40 | real effect | 0.75 | 60 | 0.0167 | 0.0006 | 0.9827 | 59.7 |
| 0.40 | real effect | 0.75 | 97 | 0.0551 | 0.0006 | 0.9443 | 95.5 |

The caps 33, 46 and 60 are the #650 cap schedule, read from the same run. Every other cap is in `per_look.tsv`.

## Surface at the cap

| p_P | p_N | d | role | p_F | P(PASS) | SE | P(CUT) | P(CANT_TELL_YET) | E[pairs] | calibration holds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.30 | 0.30 | 0.20 | calibration | 0.50 | 0.0000 | 0.0000 | 0.0253 | 0.9747 | 95.3 | yes |
| 0.30 | 0.30 | 0.25 | small real effect | 0.55 | 0.0002 | 0.0001 | 0.0079 | 0.9919 | 96.4 |  |
| 0.30 | 0.30 | 0.30 | real effect | 0.60 | 0.0022 | 0.0005 | 0.0029 | 0.9949 | 96.7 |  |
| 0.30 | 0.30 | 0.35 | real effect | 0.65 | 0.0100 | 0.0010 | 0.0013 | 0.9887 | 96.6 |  |
| 0.30 | 0.30 | 0.40 | real effect | 0.70 | 0.0504 | 0.0022 | 0.0006 | 0.9490 | 95.7 |  |
| 0.30 | 0.35 | 0.20 | calibration | 0.50 | 0.0000 | 0.0000 | 0.0250 | 0.9750 | 95.4 | yes |
| 0.30 | 0.35 | 0.25 | small real effect | 0.55 | 0.0000 | 0.0000 | 0.0092 | 0.9908 | 96.3 |  |
| 0.30 | 0.35 | 0.30 | real effect | 0.60 | 0.0002 | 0.0001 | 0.0032 | 0.9966 | 96.7 |  |
| 0.30 | 0.35 | 0.35 | real effect | 0.65 | 0.0018 | 0.0004 | 0.0012 | 0.9970 | 96.9 |  |
| 0.30 | 0.35 | 0.40 | real effect | 0.70 | 0.0141 | 0.0012 | 0.0002 | 0.9857 | 96.6 |  |
| 0.30 | 0.40 | 0.20 | calibration | 0.50 | 0.0000 | 0.0000 | 0.0252 | 0.9748 | 95.3 | yes |
| 0.30 | 0.40 | 0.25 | small real effect | 0.55 | 0.0000 | 0.0000 | 0.0092 | 0.9908 | 96.3 |  |
| 0.30 | 0.40 | 0.30 | real effect | 0.60 | 0.0000 | 0.0000 | 0.0029 | 0.9971 | 96.8 |  |
| 0.30 | 0.40 | 0.35 | real effect | 0.65 | 0.0001 | 0.0001 | 0.0013 | 0.9986 | 96.9 |  |
| 0.30 | 0.40 | 0.40 | real effect | 0.70 | 0.0015 | 0.0004 | 0.0004 | 0.9981 | 96.9 |  |
| 0.35 | 0.30 | 0.20 | calibration | 0.55 | 0.0001 | 0.0001 | 0.0254 | 0.9745 | 95.3 | yes |
| 0.35 | 0.30 | 0.25 | small real effect | 0.60 | 0.0003 | 0.0002 | 0.0090 | 0.9907 | 96.3 |  |
| 0.35 | 0.30 | 0.30 | real effect | 0.65 | 0.0065 | 0.0008 | 0.0028 | 0.9907 | 96.6 |  |
| 0.35 | 0.30 | 0.35 | real effect | 0.70 | 0.0408 | 0.0020 | 0.0016 | 0.9576 | 95.8 |  |
| 0.35 | 0.30 | 0.40 | real effect | 0.75 | 0.1492 | 0.0036 | 0.0002 | 0.8506 | 93.2 |  |
| 0.35 | 0.35 | 0.20 | calibration | 0.55 | 0.0000 | 0.0000 | 0.0261 | 0.9739 | 95.3 | yes |
| 0.35 | 0.35 | 0.25 | small real effect | 0.60 | 0.0002 | 0.0001 | 0.0086 | 0.9912 | 96.4 |  |
| 0.35 | 0.35 | 0.30 | real effect | 0.65 | 0.0013 | 0.0004 | 0.0032 | 0.9955 | 96.7 |  |
| 0.35 | 0.35 | 0.35 | real effect | 0.70 | 0.0100 | 0.0010 | 0.0010 | 0.9890 | 96.7 |  |
| 0.35 | 0.35 | 0.40 | real effect | 0.75 | 0.0551 | 0.0023 | 0.0006 | 0.9443 | 95.5 |  |
| 0.35 | 0.40 | 0.20 | calibration | 0.55 | 0.0000 | 0.0000 | 0.0236 | 0.9764 | 95.4 | yes |
| 0.35 | 0.40 | 0.25 | small real effect | 0.60 | 0.0000 | 0.0000 | 0.0094 | 0.9906 | 96.3 |  |
| 0.35 | 0.40 | 0.30 | real effect | 0.65 | 0.0004 | 0.0002 | 0.0033 | 0.9963 | 96.7 |  |
| 0.35 | 0.40 | 0.35 | real effect | 0.70 | 0.0020 | 0.0004 | 0.0012 | 0.9968 | 96.9 |  |
| 0.35 | 0.40 | 0.40 | real effect | 0.75 | 0.0130 | 0.0011 | 0.0006 | 0.9864 | 96.6 |  |
| 0.40 | 0.30 | 0.20 | calibration | 0.60 | 0.0001 | 0.0001 | 0.0260 | 0.9739 | 95.3 | yes |
| 0.40 | 0.30 | 0.25 | small real effect | 0.65 | 0.0030 | 0.0005 | 0.0083 | 0.9887 | 96.3 |  |
| 0.40 | 0.30 | 0.30 | real effect | 0.70 | 0.0197 | 0.0014 | 0.0019 | 0.9784 | 96.3 |  |
| 0.40 | 0.30 | 0.35 | real effect | 0.75 | 0.0984 | 0.0030 | 0.0013 | 0.9003 | 94.4 |  |
| 0.40 | 0.30 | 0.40 | real effect | 0.80 | 0.3211 | 0.0047 | 0.0003 | 0.6786 | 88.3 |  |
| 0.40 | 0.35 | 0.20 | calibration | 0.60 | 0.0000 | 0.0000 | 0.0259 | 0.9741 | 95.3 | yes |
| 0.40 | 0.35 | 0.25 | small real effect | 0.65 | 0.0010 | 0.0003 | 0.0095 | 0.9895 | 96.3 |  |
| 0.40 | 0.35 | 0.30 | real effect | 0.70 | 0.0075 | 0.0009 | 0.0029 | 0.9896 | 96.6 |  |
| 0.40 | 0.35 | 0.35 | real effect | 0.75 | 0.0379 | 0.0019 | 0.0011 | 0.9610 | 96.0 |  |
| 0.40 | 0.35 | 0.40 | real effect | 0.80 | 0.1605 | 0.0037 | 0.0002 | 0.8393 | 93.0 |  |
| 0.40 | 0.40 | 0.20 | calibration | 0.60 | 0.0000 | 0.0000 | 0.0267 | 0.9733 | 95.2 | yes |
| 0.40 | 0.40 | 0.25 | small real effect | 0.65 | 0.0001 | 0.0001 | 0.0085 | 0.9914 | 96.4 |  |
| 0.40 | 0.40 | 0.30 | real effect | 0.70 | 0.0015 | 0.0004 | 0.0025 | 0.9960 | 96.8 |  |
| 0.40 | 0.40 | 0.35 | real effect | 0.75 | 0.0103 | 0.0010 | 0.0009 | 0.9888 | 96.6 |  |
| 0.40 | 0.40 | 0.40 | real effect | 0.80 | 0.0632 | 0.0024 | 0.0002 | 0.9366 | 95.4 |  |

## Headline: smallest d with P(PASS) >= 0.80 by 97 pairs

| p_P | p_N | smallest d |
| --- | --- | --- |
| 0.30 | 0.30 | not reached on this grid |
| 0.30 | 0.35 | not reached on this grid |
| 0.30 | 0.40 | not reached on this grid |
| 0.35 | 0.30 | not reached on this grid |
| 0.35 | 0.35 | not reached on this grid |
| 0.35 | 0.40 | not reached on this grid |
| 0.40 | 0.30 | not reached on this grid |
| 0.40 | 0.35 | not reached on this grid |
| 0.40 | 0.40 | not reached on this grid |

## Joint terminal state of replicates open at the cap

Each bound is median [10th, 90th percentile]. LB(F-P) and UB(F-P) are on the d scale.

| p_P | p_N | d | joint state | count | share | LB(F-P) | LB(mu_F) - UB(mu_N) | UB(F-P) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.30 | 0.30 | 0.20 | fp_passes_fn_fails | 19 | 0.0019 | 0.216 [0.204, 0.241] | 0.003 [-0.104, 0.066] | 0.582 [0.543, 0.632] |
| 0.30 | 0.30 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.30 | 0.20 | neither_passes | 9728 | 0.9728 | -0.010 [-0.106, 0.087] | -0.136 [-0.237, -0.036] | 0.391 [0.298, 0.488] |
| 0.30 | 0.30 | 0.25 | fp_passes_fn_fails | 172 | 0.0172 | 0.218 [0.202, 0.263] | 0.008 [-0.086, 0.102] | 0.594 [0.553, 0.646] |
| 0.30 | 0.30 | 0.25 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.30 | 0.25 | neither_passes | 9747 | 0.9747 | 0.037 [-0.060, 0.132] | -0.089 [-0.191, 0.012] | 0.438 [0.344, 0.534] |
| 0.30 | 0.30 | 0.30 | fp_passes_fn_fails | 664 | 0.0664 | 0.222 [0.203, 0.268] | 0.041 [-0.054, 0.126] | 0.606 [0.551, 0.661] |
| 0.30 | 0.30 | 0.30 | fn_passes_fp_fails | 3 | 0.0003 | 0.154 [0.123, 0.181] | 0.218 [0.212, 0.238] | 0.568 [0.546, 0.588] |
| 0.30 | 0.30 | 0.30 | neither_passes | 9282 | 0.9282 | 0.082 [-0.014, 0.164] | -0.044 [-0.148, 0.054] | 0.482 [0.387, 0.564] |
| 0.30 | 0.30 | 0.35 | fp_passes_fn_fails | 2051 | 0.2051 | 0.232 [0.205, 0.288] | 0.063 [-0.030, 0.147] | 0.616 [0.562, 0.674] |
| 0.30 | 0.30 | 0.35 | fn_passes_fp_fails | 17 | 0.0017 | 0.159 [0.089, 0.186] | 0.226 [0.209, 0.247] | 0.557 [0.477, 0.617] |
| 0.30 | 0.30 | 0.35 | neither_passes | 7819 | 0.7819 | 0.118 [0.029, 0.182] | -0.000 [-0.100, 0.099] | 0.513 [0.427, 0.586] |
| 0.30 | 0.30 | 0.40 | fp_passes_fn_fails | 4200 | 0.4200 | 0.244 [0.208, 0.305] | 0.089 [0.001, 0.163] | 0.625 [0.571, 0.689] |
| 0.30 | 0.30 | 0.40 | fn_passes_fp_fails | 62 | 0.0062 | 0.164 [0.136, 0.192] | 0.215 [0.203, 0.241] | 0.553 [0.506, 0.596] |
| 0.30 | 0.30 | 0.40 | neither_passes | 5228 | 0.5228 | 0.146 [0.070, 0.190] | 0.041 [-0.058, 0.132] | 0.538 [0.463, 0.597] |
| 0.30 | 0.35 | 0.20 | fp_passes_fn_fails | 13 | 0.0013 | 0.217 [0.202, 0.244] | -0.103 [-0.206, 0.025] | 0.587 [0.533, 0.621] |
| 0.30 | 0.35 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.35 | 0.20 | neither_passes | 9737 | 0.9737 | -0.013 [-0.105, 0.084] | -0.192 [-0.293, -0.090] | 0.390 [0.298, 0.487] |
| 0.30 | 0.35 | 0.25 | fp_passes_fn_fails | 144 | 0.0144 | 0.217 [0.202, 0.254] | -0.053 [-0.146, 0.045] | 0.599 [0.554, 0.645] |
| 0.30 | 0.35 | 0.25 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.35 | 0.25 | neither_passes | 9764 | 0.9764 | 0.038 [-0.061, 0.129] | -0.145 [-0.249, -0.039] | 0.439 [0.342, 0.534] |
| 0.30 | 0.35 | 0.30 | fp_passes_fn_fails | 719 | 0.0719 | 0.224 [0.204, 0.271] | -0.015 [-0.111, 0.075] | 0.609 [0.556, 0.663] |
| 0.30 | 0.35 | 0.30 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.35 | 0.30 | neither_passes | 9247 | 0.9247 | 0.083 [-0.015, 0.163] | -0.099 [-0.204, 0.003] | 0.480 [0.387, 0.565] |
| 0.30 | 0.35 | 0.35 | fp_passes_fn_fails | 2143 | 0.2143 | 0.233 [0.206, 0.292] | 0.011 [-0.081, 0.106] | 0.616 [0.565, 0.676] |
| 0.30 | 0.35 | 0.35 | fn_passes_fp_fails | 2 | 0.0002 | 0.181 [0.180, 0.181] | 0.230 [0.223, 0.237] | 0.598 [0.597, 0.598] |
| 0.30 | 0.35 | 0.35 | neither_passes | 7825 | 0.7825 | 0.120 [0.029, 0.181] | -0.052 [-0.155, 0.043] | 0.513 [0.429, 0.584] |
| 0.30 | 0.35 | 0.40 | fp_passes_fn_fails | 4594 | 0.4594 | 0.247 [0.209, 0.314] | 0.045 [-0.046, 0.134] | 0.629 [0.572, 0.693] |
| 0.30 | 0.35 | 0.40 | fn_passes_fp_fails | 3 | 0.0003 | 0.183 [0.126, 0.192] | 0.212 [0.206, 0.215] | 0.578 [0.525, 0.587] |
| 0.30 | 0.35 | 0.40 | neither_passes | 5260 | 0.5260 | 0.147 [0.070, 0.190] | -0.015 [-0.113, 0.078] | 0.538 [0.464, 0.602] |
| 0.30 | 0.40 | 0.20 | fp_passes_fn_fails | 22 | 0.0022 | 0.216 [0.203, 0.242] | -0.139 [-0.181, -0.027] | 0.591 [0.550, 0.651] |
| 0.30 | 0.40 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.40 | 0.20 | neither_passes | 9726 | 0.9726 | -0.009 [-0.104, 0.086] | -0.245 [-0.346, -0.143] | 0.392 [0.299, 0.488] |
| 0.30 | 0.40 | 0.25 | fp_passes_fn_fails | 156 | 0.0156 | 0.220 [0.203, 0.254] | -0.097 [-0.182, -0.018] | 0.601 [0.549, 0.657] |
| 0.30 | 0.40 | 0.25 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.40 | 0.25 | neither_passes | 9752 | 0.9752 | 0.036 [-0.062, 0.127] | -0.199 [-0.303, -0.096] | 0.437 [0.342, 0.528] |
| 0.30 | 0.40 | 0.30 | fp_passes_fn_fails | 655 | 0.0655 | 0.224 [0.204, 0.267] | -0.074 [-0.173, 0.019] | 0.609 [0.555, 0.659] |
| 0.30 | 0.40 | 0.30 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.40 | 0.30 | neither_passes | 9316 | 0.9316 | 0.079 [-0.014, 0.162] | -0.150 [-0.253, -0.051] | 0.480 [0.389, 0.561] |
| 0.30 | 0.40 | 0.35 | fp_passes_fn_fails | 2150 | 0.2150 | 0.233 [0.206, 0.289] | -0.040 [-0.138, 0.057] | 0.617 [0.563, 0.676] |
| 0.30 | 0.40 | 0.35 | fn_passes_fp_fails | 1 | 0.0001 | 0.152 [0.152, 0.152] | 0.206 [0.206, 0.206] | 0.533 [0.533, 0.533] |
| 0.30 | 0.40 | 0.35 | neither_passes | 7835 | 0.7835 | 0.118 [0.028, 0.180] | -0.109 [-0.209, -0.008] | 0.514 [0.427, 0.584] |
| 0.30 | 0.40 | 0.40 | fp_passes_fn_fails | 4582 | 0.4582 | 0.246 [0.209, 0.315] | -0.004 [-0.105, 0.088] | 0.626 [0.570, 0.692] |
| 0.30 | 0.40 | 0.40 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.30 | 0.40 | 0.40 | neither_passes | 5399 | 0.5399 | 0.147 [0.070, 0.189] | -0.066 [-0.165, 0.028] | 0.537 [0.467, 0.599] |
| 0.35 | 0.30 | 0.20 | fp_passes_fn_fails | 21 | 0.0021 | 0.214 [0.202, 0.248] | 0.009 [-0.079, 0.095] | 0.603 [0.572, 0.634] |
| 0.35 | 0.30 | 0.20 | fn_passes_fp_fails | 1 | 0.0001 | 0.163 [0.163, 0.163] | 0.218 [0.218, 0.218] | 0.503 [0.503, 0.503] |
| 0.35 | 0.30 | 0.20 | neither_passes | 9723 | 0.9723 | -0.015 [-0.111, 0.083] | -0.087 [-0.188, 0.015] | 0.394 [0.300, 0.494] |
| 0.35 | 0.30 | 0.25 | fp_passes_fn_fails | 128 | 0.0128 | 0.218 [0.206, 0.257] | 0.039 [-0.054, 0.132] | 0.601 [0.554, 0.654] |
| 0.35 | 0.30 | 0.25 | fn_passes_fp_fails | 14 | 0.0014 | 0.137 [0.088, 0.189] | 0.209 [0.202, 0.236] | 0.533 [0.462, 0.619] |
| 0.35 | 0.30 | 0.25 | neither_passes | 9765 | 0.9765 | 0.033 [-0.066, 0.125] | -0.040 [-0.142, 0.060] | 0.440 [0.345, 0.535] |
| 0.35 | 0.30 | 0.30 | fp_passes_fn_fails | 639 | 0.0639 | 0.226 [0.204, 0.266] | 0.082 [-0.003, 0.155] | 0.607 [0.559, 0.659] |
| 0.35 | 0.30 | 0.30 | fn_passes_fp_fails | 50 | 0.0050 | 0.147 [0.084, 0.186] | 0.216 [0.206, 0.234] | 0.537 [0.474, 0.614] |
| 0.35 | 0.30 | 0.30 | neither_passes | 9218 | 0.9218 | 0.080 [-0.016, 0.162] | 0.011 [-0.093, 0.105] | 0.480 [0.387, 0.565] |
| 0.35 | 0.30 | 0.35 | fp_passes_fn_fails | 1781 | 0.1781 | 0.231 [0.205, 0.286] | 0.106 [0.020, 0.169] | 0.612 [0.562, 0.675] |
| 0.35 | 0.30 | 0.35 | fn_passes_fp_fails | 199 | 0.0199 | 0.157 [0.110, 0.186] | 0.217 [0.202, 0.253] | 0.546 [0.492, 0.600] |
| 0.35 | 0.30 | 0.35 | neither_passes | 7596 | 0.7596 | 0.120 [0.030, 0.181] | 0.055 [-0.044, 0.145] | 0.513 [0.429, 0.584] |
| 0.35 | 0.30 | 0.40 | fp_passes_fn_fails | 3340 | 0.3340 | 0.240 [0.207, 0.301] | 0.128 [0.049, 0.181] | 0.620 [0.567, 0.683] |
| 0.35 | 0.30 | 0.40 | fn_passes_fp_fails | 394 | 0.0394 | 0.167 [0.120, 0.192] | 0.227 [0.206, 0.271] | 0.554 [0.495, 0.606] |
| 0.35 | 0.30 | 0.40 | neither_passes | 4772 | 0.4772 | 0.143 [0.068, 0.189] | 0.091 [-0.003, 0.167] | 0.533 [0.460, 0.596] |
| 0.35 | 0.35 | 0.20 | fp_passes_fn_fails | 20 | 0.0020 | 0.219 [0.203, 0.235] | -0.024 [-0.168, 0.034] | 0.593 [0.564, 0.626] |
| 0.35 | 0.35 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.35 | 0.35 | 0.20 | neither_passes | 9719 | 0.9719 | -0.016 [-0.111, 0.083] | -0.141 [-0.245, -0.041] | 0.394 [0.301, 0.491] |
| 0.35 | 0.35 | 0.25 | fp_passes_fn_fails | 175 | 0.0175 | 0.219 [0.203, 0.258] | 0.002 [-0.102, 0.091] | 0.609 [0.552, 0.656] |
| 0.35 | 0.35 | 0.25 | fn_passes_fp_fails | 1 | 0.0001 | 0.135 [0.135, 0.135] | 0.218 [0.218, 0.218] | 0.552 [0.552, 0.552] |
| 0.35 | 0.35 | 0.25 | neither_passes | 9736 | 0.9736 | 0.034 [-0.065, 0.129] | -0.094 [-0.197, 0.008] | 0.440 [0.344, 0.535] |
| 0.35 | 0.35 | 0.30 | fp_passes_fn_fails | 670 | 0.0670 | 0.225 [0.204, 0.270] | 0.032 [-0.063, 0.122] | 0.609 [0.561, 0.658] |
| 0.35 | 0.35 | 0.30 | fn_passes_fp_fails | 6 | 0.0006 | 0.148 [0.074, 0.191] | 0.219 [0.209, 0.255] | 0.552 [0.452, 0.628] |
| 0.35 | 0.35 | 0.30 | neither_passes | 9279 | 0.9279 | 0.081 [-0.015, 0.163] | -0.045 [-0.149, 0.056] | 0.482 [0.388, 0.566] |
| 0.35 | 0.35 | 0.35 | fp_passes_fn_fails | 2064 | 0.2064 | 0.230 [0.205, 0.286] | 0.064 [-0.030, 0.146] | 0.614 [0.562, 0.674] |
| 0.35 | 0.35 | 0.35 | fn_passes_fp_fails | 19 | 0.0019 | 0.162 [0.124, 0.175] | 0.210 [0.203, 0.230] | 0.552 [0.503, 0.602] |
| 0.35 | 0.35 | 0.35 | neither_passes | 7807 | 0.7807 | 0.119 [0.031, 0.182] | 0.001 [-0.098, 0.098] | 0.514 [0.430, 0.586] |
| 0.35 | 0.35 | 0.40 | fp_passes_fn_fails | 4178 | 0.4178 | 0.244 [0.208, 0.309] | 0.091 [0.004, 0.165] | 0.623 [0.569, 0.687] |
| 0.35 | 0.35 | 0.40 | fn_passes_fp_fails | 73 | 0.0073 | 0.165 [0.123, 0.189] | 0.220 [0.204, 0.250] | 0.555 [0.510, 0.603] |
| 0.35 | 0.35 | 0.40 | neither_passes | 5192 | 0.5192 | 0.146 [0.070, 0.190] | 0.042 [-0.054, 0.132] | 0.535 [0.461, 0.597] |
| 0.35 | 0.40 | 0.20 | fp_passes_fn_fails | 23 | 0.0023 | 0.215 [0.202, 0.229] | -0.079 [-0.173, -0.004] | 0.610 [0.571, 0.640] |
| 0.35 | 0.40 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.35 | 0.40 | 0.20 | neither_passes | 9741 | 0.9741 | -0.013 [-0.110, 0.082] | -0.196 [-0.299, -0.093] | 0.395 [0.302, 0.492] |
| 0.35 | 0.40 | 0.25 | fp_passes_fn_fails | 145 | 0.0145 | 0.223 [0.205, 0.259] | -0.043 [-0.138, 0.063] | 0.603 [0.549, 0.643] |
| 0.35 | 0.40 | 0.25 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.35 | 0.40 | 0.25 | neither_passes | 9761 | 0.9761 | 0.036 [-0.066, 0.128] | -0.147 [-0.251, -0.043] | 0.441 [0.344, 0.536] |
| 0.35 | 0.40 | 0.30 | fp_passes_fn_fails | 661 | 0.0661 | 0.224 [0.204, 0.272] | -0.016 [-0.109, 0.072] | 0.610 [0.556, 0.666] |
| 0.35 | 0.40 | 0.30 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.35 | 0.40 | 0.30 | neither_passes | 9302 | 0.9302 | 0.082 [-0.015, 0.162] | -0.098 [-0.205, 0.003] | 0.482 [0.390, 0.566] |
| 0.35 | 0.40 | 0.35 | fp_passes_fn_fails | 2153 | 0.2153 | 0.234 [0.206, 0.289] | 0.012 [-0.076, 0.102] | 0.617 [0.564, 0.675] |
| 0.35 | 0.40 | 0.35 | fn_passes_fp_fails | 5 | 0.0005 | 0.181 [0.162, 0.194] | 0.213 [0.207, 0.253] | 0.578 [0.564, 0.596] |
| 0.35 | 0.40 | 0.35 | neither_passes | 7810 | 0.7810 | 0.120 [0.031, 0.182] | -0.052 [-0.152, 0.044] | 0.516 [0.430, 0.587] |
| 0.35 | 0.40 | 0.40 | fp_passes_fn_fails | 4612 | 0.4612 | 0.248 [0.209, 0.312] | 0.047 [-0.046, 0.136] | 0.628 [0.570, 0.693] |
| 0.35 | 0.40 | 0.40 | fn_passes_fp_fails | 11 | 0.0011 | 0.186 [0.118, 0.194] | 0.209 [0.203, 0.218] | 0.542 [0.506, 0.577] |
| 0.35 | 0.40 | 0.40 | neither_passes | 5241 | 0.5241 | 0.148 [0.073, 0.190] | -0.009 [-0.104, 0.085] | 0.536 [0.463, 0.600] |
| 0.40 | 0.30 | 0.20 | fp_passes_fn_fails | 24 | 0.0024 | 0.215 [0.204, 0.235] | 0.079 [-0.004, 0.147] | 0.597 [0.559, 0.638] |
| 0.40 | 0.30 | 0.20 | fn_passes_fp_fails | 11 | 0.0011 | 0.064 [0.026, 0.143] | 0.219 [0.205, 0.233] | 0.459 [0.431, 0.582] |
| 0.40 | 0.30 | 0.20 | neither_passes | 9704 | 0.9704 | -0.013 [-0.112, 0.083] | -0.035 [-0.138, 0.065] | 0.397 [0.300, 0.496] |
| 0.40 | 0.30 | 0.25 | fp_passes_fn_fails | 112 | 0.0112 | 0.219 [0.202, 0.255] | 0.097 [0.015, 0.168] | 0.603 [0.563, 0.655] |
| 0.40 | 0.30 | 0.25 | fn_passes_fp_fails | 89 | 0.0089 | 0.128 [0.054, 0.178] | 0.215 [0.203, 0.258] | 0.518 [0.450, 0.604] |
| 0.40 | 0.30 | 0.25 | neither_passes | 9686 | 0.9686 | 0.034 [-0.064, 0.129] | 0.015 [-0.089, 0.111] | 0.441 [0.344, 0.533] |
| 0.40 | 0.30 | 0.30 | fp_passes_fn_fails | 553 | 0.0553 | 0.221 [0.203, 0.262] | 0.124 [0.027, 0.178] | 0.606 [0.554, 0.656] |
| 0.40 | 0.30 | 0.30 | fn_passes_fp_fails | 321 | 0.0321 | 0.130 [0.052, 0.181] | 0.218 [0.203, 0.259] | 0.516 [0.449, 0.580] |
| 0.40 | 0.30 | 0.30 | neither_passes | 8910 | 0.8910 | 0.079 [-0.016, 0.161] | 0.062 [-0.040, 0.150] | 0.478 [0.386, 0.561] |
| 0.40 | 0.30 | 0.35 | fp_passes_fn_fails | 1374 | 0.1374 | 0.230 [0.206, 0.281] | 0.139 [0.065, 0.183] | 0.609 [0.561, 0.665] |
| 0.40 | 0.30 | 0.35 | fn_passes_fp_fails | 850 | 0.0850 | 0.144 [0.083, 0.183] | 0.227 [0.204, 0.277] | 0.529 [0.464, 0.590] |
| 0.40 | 0.30 | 0.35 | neither_passes | 6779 | 0.6779 | 0.117 [0.029, 0.179] | 0.102 [0.007, 0.172] | 0.508 [0.423, 0.578] |
| 0.40 | 0.30 | 0.40 | fp_passes_fn_fails | 1939 | 0.1939 | 0.238 [0.206, 0.294] | 0.154 [0.088, 0.189] | 0.614 [0.561, 0.673] |
| 0.40 | 0.30 | 0.40 | fn_passes_fp_fails | 1277 | 0.1277 | 0.160 [0.105, 0.190] | 0.237 [0.207, 0.293] | 0.536 [0.480, 0.594] |
| 0.40 | 0.30 | 0.40 | neither_passes | 3570 | 0.3570 | 0.145 [0.072, 0.188] | 0.133 [0.051, 0.186] | 0.527 [0.455, 0.588] |
| 0.40 | 0.35 | 0.20 | fp_passes_fn_fails | 20 | 0.0020 | 0.209 [0.202, 0.236] | -0.007 [-0.074, 0.102] | 0.585 [0.561, 0.625] |
| 0.40 | 0.35 | 0.20 | fn_passes_fp_fails | 2 | 0.0002 | 0.102 [0.096, 0.108] | 0.220 [0.214, 0.225] | 0.518 [0.496, 0.539] |
| 0.40 | 0.35 | 0.20 | neither_passes | 9719 | 0.9719 | -0.014 [-0.113, 0.083] | -0.090 [-0.194, 0.010] | 0.396 [0.302, 0.496] |
| 0.40 | 0.35 | 0.25 | fp_passes_fn_fails | 154 | 0.0154 | 0.219 [0.202, 0.258] | 0.054 [-0.031, 0.132] | 0.599 [0.561, 0.659] |
| 0.40 | 0.35 | 0.25 | fn_passes_fp_fails | 10 | 0.0010 | 0.154 [0.070, 0.173] | 0.216 [0.205, 0.232] | 0.528 [0.428, 0.572] |
| 0.40 | 0.35 | 0.25 | neither_passes | 9731 | 0.9731 | 0.035 [-0.066, 0.129] | -0.041 [-0.145, 0.061] | 0.441 [0.344, 0.535] |
| 0.40 | 0.35 | 0.30 | fp_passes_fn_fails | 644 | 0.0644 | 0.226 [0.203, 0.269] | 0.078 [-0.011, 0.155] | 0.607 [0.553, 0.662] |
| 0.40 | 0.35 | 0.30 | fn_passes_fp_fails | 53 | 0.0053 | 0.137 [0.067, 0.189] | 0.217 [0.204, 0.251] | 0.524 [0.465, 0.575] |
| 0.40 | 0.35 | 0.30 | neither_passes | 9199 | 0.9199 | 0.082 [-0.016, 0.164] | 0.010 [-0.091, 0.109] | 0.482 [0.387, 0.565] |
| 0.40 | 0.35 | 0.35 | fp_passes_fn_fails | 1821 | 0.1821 | 0.232 [0.205, 0.284] | 0.108 [0.019, 0.173] | 0.611 [0.560, 0.674] |
| 0.40 | 0.35 | 0.35 | fn_passes_fp_fails | 177 | 0.0177 | 0.160 [0.095, 0.186] | 0.225 [0.203, 0.259] | 0.541 [0.477, 0.591] |
| 0.40 | 0.35 | 0.35 | neither_passes | 7612 | 0.7612 | 0.119 [0.032, 0.180] | 0.055 [-0.043, 0.144] | 0.511 [0.426, 0.580] |
| 0.40 | 0.35 | 0.40 | fp_passes_fn_fails | 3458 | 0.3458 | 0.241 [0.208, 0.301] | 0.129 [0.049, 0.181] | 0.616 [0.561, 0.679] |
| 0.40 | 0.35 | 0.40 | fn_passes_fp_fails | 438 | 0.0438 | 0.166 [0.109, 0.191] | 0.222 [0.204, 0.277] | 0.540 [0.479, 0.592] |
| 0.40 | 0.35 | 0.40 | neither_passes | 4497 | 0.4497 | 0.148 [0.076, 0.189] | 0.097 [0.004, 0.170] | 0.529 [0.458, 0.592] |
| 0.40 | 0.40 | 0.20 | fp_passes_fn_fails | 22 | 0.0022 | 0.215 [0.204, 0.229] | -0.007 [-0.124, 0.075] | 0.586 [0.557, 0.631] |
| 0.40 | 0.40 | 0.20 | fn_passes_fp_fails | 0 | 0.0000 | - | - | - |
| 0.40 | 0.40 | 0.20 | neither_passes | 9711 | 0.9711 | -0.016 [-0.114, 0.082] | -0.145 [-0.246, -0.042] | 0.396 [0.301, 0.494] |
| 0.40 | 0.40 | 0.25 | fp_passes_fn_fails | 146 | 0.0146 | 0.218 [0.203, 0.255] | -0.004 [-0.076, 0.077] | 0.602 [0.555, 0.652] |
| 0.40 | 0.40 | 0.25 | fn_passes_fp_fails | 1 | 0.0001 | 0.075 [0.075, 0.075] | 0.210 [0.210, 0.210] | 0.532 [0.532, 0.532] |
| 0.40 | 0.40 | 0.25 | neither_passes | 9767 | 0.9767 | 0.035 [-0.065, 0.129] | -0.093 [-0.196, 0.009] | 0.441 [0.344, 0.535] |
| 0.40 | 0.40 | 0.30 | fp_passes_fn_fails | 702 | 0.0702 | 0.223 [0.204, 0.270] | 0.031 [-0.061, 0.118] | 0.608 [0.559, 0.664] |
| 0.40 | 0.40 | 0.30 | fn_passes_fp_fails | 6 | 0.0006 | 0.147 [0.131, 0.178] | 0.221 [0.205, 0.239] | 0.544 [0.494, 0.573] |
| 0.40 | 0.40 | 0.30 | neither_passes | 9252 | 0.9252 | 0.083 [-0.014, 0.163] | -0.042 [-0.146, 0.056] | 0.482 [0.388, 0.563] |
| 0.40 | 0.40 | 0.35 | fp_passes_fn_fails | 2127 | 0.2127 | 0.233 [0.206, 0.289] | 0.066 [-0.027, 0.145] | 0.612 [0.560, 0.674] |
| 0.40 | 0.40 | 0.35 | fn_passes_fp_fails | 26 | 0.0026 | 0.170 [0.118, 0.186] | 0.217 [0.205, 0.246] | 0.527 [0.493, 0.625] |
| 0.40 | 0.40 | 0.35 | neither_passes | 7735 | 0.7735 | 0.122 [0.035, 0.183] | 0.006 [-0.092, 0.102] | 0.512 [0.429, 0.582] |
| 0.40 | 0.40 | 0.40 | fp_passes_fn_fails | 4364 | 0.4364 | 0.243 [0.208, 0.308] | 0.094 [0.008, 0.167] | 0.617 [0.563, 0.685] |
| 0.40 | 0.40 | 0.40 | fn_passes_fp_fails | 88 | 0.0088 | 0.163 [0.107, 0.189] | 0.219 [0.205, 0.265] | 0.537 [0.477, 0.591] |
| 0.40 | 0.40 | 0.40 | neither_passes | 4914 | 0.4914 | 0.148 [0.076, 0.190] | 0.049 [-0.048, 0.135] | 0.530 [0.456, 0.590] |

## Relation to #650

This record changes no #650 code, test or number. The #650 script, its test file and `a-design-sim-ledger-level.md` are untouched. The negative control in `tests/test_simulate_a_design_650.py` still loosens the pass alpha to 0.6 and still fails the calibration check.

This record adds a second negative control in the new regime. It sits at the off-diagonal boundary cell (p_F = 0.55, p_P = 0.35, p_N = 0.30), where the loosened pass alpha of 0.6 fails the check. On the diagonal (p_P = p_N = 0.35) the same loosening reaches only about 0.03 at 600 replicates. There, both PASS conditions sit at their margin at once, so a loosened F - P test alone does not over-pass. The off-diagonal cell shows that the check can still detect a rule that over-passes.

The #650 sizing does not carry over. At p_N = 1/7, #650 found 83 pairs for 80% at (0.75, 0.25). Here the Null rate is 0.30 to 0.40, and 97 pairs reach 80% nowhere on the grid.

## Limits of this simulation

1. **The draws are independent Bernoulli.** This record contains no dependence model. Revisit that only if real epochs are shown to be dependent.
2. **Void epochs are not modelled.** Every draw is a valid epoch.
3. **The allocation is fixed at 1:1:1.** Varying the Null ratio at a fixed budget is #685.
4. **The terminal bounds are summarised by quantiles.** `terminal_states.tsv` gives the minimum, the 10th, 25th, 50th, 75th and 90th percentiles, and the maximum for each state. The per-replicate values are not stored.

*Revisit if:* the engine's `one_sided_betting_bound` changes. Then re-run the surface. The vectorised terminal bound in `terminal_bounds` repeats the engine's grid scan and bisection, and `test_terminal_bounds_equal_the_engine_bounds` fails if the two drift apart.
