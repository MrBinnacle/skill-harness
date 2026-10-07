# Operating characteristics of the #621 A-world design at the ledger level (#650)

**Date:** 2026-09-22. **Script:** `scripts/screens/419/simulate_a_design.py`. **Test:** `tests/test_simulate_a_design_650.py`. **Model calls:** none. **Spend:** none.

This record is the sizing input for the Stage 1B gate. It replaces the fixed-horizon normal approximation in the steering repository's S476 record of the outside answer on the first card's alpha with a simulation of the confidence-sequence rule itself.

## What was simulated

Three arms, Full-A, Placebo-A and Null-A, are independent Bernoulli streams. Each look adds one draw to every arm. Full and Placebo pair by launch index, the i-th draw of each, and the pair is bounded as x = (F - P + 1) / 2, mapped back by d = 2x - 1. After every pair the rule registered for the #649 launcher is applied:

| Outcome | Condition |
| --- | --- |
| CUT (no_lift) | UB(F - P) < 0.20, one-sided at alpha 0.05 |
| PASS | LB(F - P) >= 0.20, one-sided at alpha 0.0209, **and** LB(mu_F) - UB(mu_N) >= 0.20, each one-sided at 0.0209 / 2 = 0.01045 |
| continue | anything else, until the cap n_max |

The one-sided bounds come from single capital processes, `one_sided_betting_bound`. The script holds a local copy of that function with the signature the #649 branch adds to `skill_harness.aggregation.confidence_sequence`. #649 owns it, and the script should import the engine version once #649 merges.

Each cell also runs the same rule on the same draws with the two edges of the two-sided hedged sequence, `betting_confidence_sequence`. That comparison row is labelled `hedged` and shows what the one-sided construction gains.

**Grid:** p_F in {0.55, 0.65, 0.75, 0.85}, p_P in {0.15, 0.25, 0.35}, p_N = 1/7, n_max in {16, 33, 46, 60}. 2,000 replicates per cell, seed 650, draws seeded per (p_F, p_P) cell. The rule at a look does not depend on the cap, so each replicate runs once to 120 pairs and every smaller cap is read from its first stopping look. The run to 120 pairs also gives the exact number of pairs where the pass probability reaches a power target.

**Exactness.** The script carries the engine's wealth processes on the engine's mu grid for all replicates at once, and reads each decision from the grid. Where the grid cannot settle a decision, it calls the bound function on that prefix. The test asserts that every stopping look and outcome equals the result of calling the bound functions at every look, for both constructions. It also asserts that the grid wealth equals the engine's wealth at every grid point to 1e-10. The full run took about 50 minutes on the steering host.

To reproduce:

```
python scripts/screens/419/simulate_a_design.py --out OUT --replicates 2000 --seed 650 --horizon 120
```

It writes `OUT/a_design_sim.tsv` and `OUT/summary.md`, and exits non-zero if the boundary calibration fails.

## Boundary calibration

The grid has one boundary cell, p_F - p_P = 0.55 - 0.35 = 0.20. There, the chance of passing must be at most 0.0209, within Monte Carlo error. The limit used is 0.0209 plus 3 standard errors at the nominal level: sqrt(0.0209 x 0.9791 / 2000) = 0.0032, so the limit is 0.0305.

| Construction | n_max | P(pass) | Passes out of 2,000 | Holds |
| --- | --- | --- | --- | --- |
| one_sided | 16 | 0.0000 | 0 | yes |
| one_sided | 33 | 0.0015 | 3 | yes |
| one_sided | 46 | 0.0020 | 4 | yes |
| one_sided | 60 | 0.0020 | 4 | yes |
| hedged | 16 | 0.0000 | 0 | yes |
| hedged | 33 | 0.0000 | 0 | yes |
| hedged | 46 | 0.0005 | 1 | yes |
| hedged | 60 | 0.0005 | 1 | yes |

**The calibration holds, with a wide margin.** The largest boundary pass rate is 0.0020 at n_max 46 and 60, about a tenth of 0.0209. The pairing and the one-sided reading are valid on this check. The rule is conservative at the boundary, which is expected: a Ville-inequality bound spends its alpha over all times, and the F - N condition must also hold.

The test repeats the check on a reduced grid (the boundary cell, 1,000 replicates, n_max 33). A negative control loosens the pass alpha to 0.6, and the same check then fails. So the check can detect a rule that over-passes.

## Sizing: pairs needed for 80% and 90% pass probability

| Construction | p_F | p_P | Pairs for 80% | Pairs for 90% | Smallest grid n_max for 80% | Smallest grid n_max for 90% |
| --- | --- | --- | --- | --- | --- | --- |
| one_sided | 0.75 | 0.25 | 83 | 97 | none of 16, 33, 46, 60 | none |
| one_sided | 0.85 | 0.25 | 47 | 54 | 60 | 60 |
| hedged | 0.75 | 0.25 | 94 | 109 | none | none |
| hedged | 0.85 | 0.25 | 54 | 61 | 60 | none |

A "pair" is one look, which adds one run to each of the three arms.

1. **For d = 0.50 (0.75 against 0.25), the registered rule needs 83 pairs for 80% and 97 for 90%.** The fixed-horizon normal approximation said about 35 and 46. The anytime-valid rule needs 2.1 to 2.4 times as many runs here.
2. **For d = 0.60 (0.85 against 0.25), it needs 47 pairs for 80% and 54 for 90%.**
3. **33 pairs is undersized for both.** At n_max 33 the pass probability is 0.098 for (0.75, 0.25) and 0.426 for (0.85, 0.25).
4. **The one-sided construction saves about 7 to 12 pairs** against the hedged edges at these targets, and it raises the pass probability in every cell with a real effect.

## Every cell

P(CUT) is near zero everywhere because no cell has d below 0.20. The lowest is the boundary cell, where CUT reaches 0.025 at n_max 60.

| Construction | p_F | p_P | n_max | P(pass) | P(CUT) | P(unresolved) | E[pairs] |
| --- | --- | --- | --- | --- | --- | --- | --- |
| one_sided | 0.55 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.55 | 0.15 | 33 | 0.0025 | 0.0000 | 0.9975 | 33.0 |
| one_sided | 0.55 | 0.15 | 46 | 0.0080 | 0.0000 | 0.9920 | 45.9 |
| one_sided | 0.55 | 0.15 | 60 | 0.0250 | 0.0000 | 0.9750 | 59.7 |
| hedged | 0.55 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.55 | 0.15 | 33 | 0.0005 | 0.0000 | 0.9995 | 33.0 |
| hedged | 0.55 | 0.15 | 46 | 0.0025 | 0.0000 | 0.9975 | 46.0 |
| hedged | 0.55 | 0.15 | 60 | 0.0105 | 0.0000 | 0.9895 | 59.9 |
| one_sided | 0.55 | 0.25 | 16 | 0.0000 | 0.0010 | 0.9990 | 16.0 |
| one_sided | 0.55 | 0.25 | 33 | 0.0005 | 0.0020 | 0.9975 | 33.0 |
| one_sided | 0.55 | 0.25 | 46 | 0.0035 | 0.0020 | 0.9945 | 45.9 |
| one_sided | 0.55 | 0.25 | 60 | 0.0095 | 0.0025 | 0.9880 | 59.8 |
| hedged | 0.55 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.55 | 0.25 | 33 | 0.0000 | 0.0010 | 0.9990 | 33.0 |
| hedged | 0.55 | 0.25 | 46 | 0.0000 | 0.0010 | 0.9990 | 46.0 |
| hedged | 0.55 | 0.25 | 60 | 0.0045 | 0.0015 | 0.9940 | 59.9 |
| one_sided | 0.55 | 0.35 | 16 | 0.0000 | 0.0085 | 0.9915 | 16.0 |
| one_sided | 0.55 | 0.35 | 33 | 0.0015 | 0.0235 | 0.9750 | 32.7 |
| one_sided | 0.55 | 0.35 | 46 | 0.0020 | 0.0250 | 0.9730 | 45.3 |
| one_sided | 0.55 | 0.35 | 60 | 0.0020 | 0.0255 | 0.9725 | 59.0 |
| hedged | 0.55 | 0.35 | 16 | 0.0000 | 0.0005 | 0.9995 | 16.0 |
| hedged | 0.55 | 0.35 | 33 | 0.0000 | 0.0065 | 0.9935 | 32.9 |
| hedged | 0.55 | 0.35 | 46 | 0.0005 | 0.0095 | 0.9900 | 45.8 |
| hedged | 0.55 | 0.35 | 60 | 0.0005 | 0.0100 | 0.9895 | 59.7 |
| one_sided | 0.65 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.65 | 0.15 | 33 | 0.0295 | 0.0000 | 0.9705 | 32.9 |
| one_sided | 0.65 | 0.15 | 46 | 0.1090 | 0.0000 | 0.8910 | 45.1 |
| one_sided | 0.65 | 0.15 | 60 | 0.2035 | 0.0000 | 0.7965 | 56.9 |
| hedged | 0.65 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.65 | 0.15 | 33 | 0.0090 | 0.0000 | 0.9910 | 33.0 |
| hedged | 0.65 | 0.15 | 46 | 0.0525 | 0.0000 | 0.9475 | 45.6 |
| hedged | 0.65 | 0.15 | 60 | 0.1325 | 0.0000 | 0.8675 | 58.4 |
| one_sided | 0.65 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.65 | 0.25 | 33 | 0.0170 | 0.0000 | 0.9830 | 32.9 |
| one_sided | 0.65 | 0.25 | 46 | 0.0595 | 0.0000 | 0.9405 | 45.5 |
| one_sided | 0.65 | 0.25 | 60 | 0.1275 | 0.0000 | 0.8725 | 58.2 |
| hedged | 0.65 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.65 | 0.25 | 33 | 0.0045 | 0.0000 | 0.9955 | 33.0 |
| hedged | 0.65 | 0.25 | 46 | 0.0275 | 0.0000 | 0.9725 | 45.8 |
| hedged | 0.65 | 0.25 | 60 | 0.0730 | 0.0000 | 0.9270 | 59.2 |
| one_sided | 0.65 | 0.35 | 16 | 0.0000 | 0.0005 | 0.9995 | 16.0 |
| one_sided | 0.65 | 0.35 | 33 | 0.0045 | 0.0015 | 0.9940 | 33.0 |
| one_sided | 0.65 | 0.35 | 46 | 0.0165 | 0.0015 | 0.9820 | 45.8 |
| one_sided | 0.65 | 0.35 | 60 | 0.0345 | 0.0015 | 0.9640 | 59.5 |
| hedged | 0.65 | 0.35 | 16 | 0.0000 | 0.0005 | 0.9995 | 16.0 |
| hedged | 0.65 | 0.35 | 33 | 0.0005 | 0.0005 | 0.9990 | 33.0 |
| hedged | 0.65 | 0.35 | 46 | 0.0035 | 0.0005 | 0.9960 | 46.0 |
| hedged | 0.65 | 0.35 | 60 | 0.0145 | 0.0005 | 0.9850 | 59.8 |
| one_sided | 0.75 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.75 | 0.15 | 33 | 0.1735 | 0.0000 | 0.8265 | 32.0 |
| one_sided | 0.75 | 0.15 | 46 | 0.4385 | 0.0000 | 0.5615 | 41.2 |
| one_sided | 0.75 | 0.15 | 60 | 0.6665 | 0.0000 | 0.3335 | 47.5 |
| hedged | 0.75 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.75 | 0.15 | 33 | 0.0870 | 0.0000 | 0.9130 | 32.7 |
| hedged | 0.75 | 0.15 | 46 | 0.2970 | 0.0000 | 0.7030 | 43.4 |
| hedged | 0.75 | 0.15 | 60 | 0.5465 | 0.0000 | 0.4535 | 51.7 |
| one_sided | 0.75 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.75 | 0.25 | 33 | 0.0975 | 0.0000 | 0.9025 | 32.6 |
| one_sided | 0.75 | 0.25 | 46 | 0.3250 | 0.0000 | 0.6750 | 43.0 |
| one_sided | 0.75 | 0.25 | 60 | 0.5410 | 0.0000 | 0.4590 | 51.0 |
| hedged | 0.75 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.75 | 0.25 | 33 | 0.0320 | 0.0000 | 0.9680 | 32.9 |
| hedged | 0.75 | 0.25 | 46 | 0.1815 | 0.0000 | 0.8185 | 44.7 |
| hedged | 0.75 | 0.25 | 60 | 0.4120 | 0.0000 | 0.5880 | 54.6 |
| one_sided | 0.75 | 0.35 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.75 | 0.35 | 33 | 0.0505 | 0.0000 | 0.9495 | 32.8 |
| one_sided | 0.75 | 0.35 | 46 | 0.1460 | 0.0000 | 0.8540 | 44.5 |
| one_sided | 0.75 | 0.35 | 60 | 0.2600 | 0.0000 | 0.7400 | 55.8 |
| hedged | 0.75 | 0.35 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.75 | 0.35 | 33 | 0.0135 | 0.0000 | 0.9865 | 33.0 |
| hedged | 0.75 | 0.35 | 46 | 0.0745 | 0.0000 | 0.9255 | 45.4 |
| hedged | 0.75 | 0.35 | 60 | 0.1650 | 0.0000 | 0.8350 | 57.8 |
| one_sided | 0.85 | 0.15 | 16 | 0.0010 | 0.0000 | 0.9990 | 16.0 |
| one_sided | 0.85 | 0.15 | 33 | 0.5480 | 0.0000 | 0.4520 | 29.3 |
| one_sided | 0.85 | 0.15 | 46 | 0.8590 | 0.0000 | 0.1410 | 32.9 |
| one_sided | 0.85 | 0.15 | 60 | 0.9715 | 0.0000 | 0.0285 | 34.0 |
| hedged | 0.85 | 0.15 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.85 | 0.15 | 33 | 0.3705 | 0.0000 | 0.6295 | 31.3 |
| hedged | 0.85 | 0.15 | 46 | 0.7735 | 0.0000 | 0.2265 | 36.8 |
| hedged | 0.85 | 0.15 | 60 | 0.9405 | 0.0000 | 0.0595 | 38.7 |
| one_sided | 0.85 | 0.25 | 16 | 0.0005 | 0.0000 | 0.9995 | 16.0 |
| one_sided | 0.85 | 0.25 | 33 | 0.4260 | 0.0000 | 0.5740 | 30.6 |
| one_sided | 0.85 | 0.25 | 46 | 0.7865 | 0.0000 | 0.2135 | 35.6 |
| one_sided | 0.85 | 0.25 | 60 | 0.9435 | 0.0000 | 0.0565 | 37.4 |
| hedged | 0.85 | 0.25 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.85 | 0.25 | 33 | 0.2465 | 0.0000 | 0.7535 | 32.1 |
| hedged | 0.85 | 0.25 | 46 | 0.6565 | 0.0000 | 0.3435 | 39.3 |
| hedged | 0.85 | 0.25 | 60 | 0.8915 | 0.0000 | 0.1085 | 42.3 |
| one_sided | 0.85 | 0.35 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| one_sided | 0.85 | 0.35 | 33 | 0.2280 | 0.0000 | 0.7720 | 31.9 |
| one_sided | 0.85 | 0.35 | 46 | 0.5460 | 0.0000 | 0.4540 | 40.0 |
| one_sided | 0.85 | 0.35 | 60 | 0.7540 | 0.0000 | 0.2460 | 44.8 |
| hedged | 0.85 | 0.35 | 16 | 0.0000 | 0.0000 | 1.0000 | 16.0 |
| hedged | 0.85 | 0.35 | 33 | 0.0960 | 0.0000 | 0.9040 | 32.7 |
| hedged | 0.85 | 0.35 | 46 | 0.3935 | 0.0000 | 0.6065 | 42.7 |
| hedged | 0.85 | 0.35 | 60 | 0.6445 | 0.0000 | 0.3555 | 49.4 |

## Limits of this simulation

1. **The Null arm grows with every look here.** Stage 1A reads F - N against the 7 fixed Null-A epochs from the Stage 1 screen. With 1 correct out of 7, UB(mu_N) one-sided at 0.01045 is 0.737 from the same bound function. The F - N condition then needs LB(mu_F) >= 0.937. Sixty Full runs that are all correct give LB(mu_F) = 0.864. So, with Null-A held at those 7 epochs, **no number of Full and Placebo runs can pass the F - N condition.** The sizes above hold only if Null-A is run alongside the other arms at the same count. Whether Stage 1B adds Null-A runs is a design decision for the head, not for this script.
2. **Void epochs are not modelled.** Every draw is a valid epoch. A void rate v multiplies the runs needed by about 1 / (1 - v).
3. **The B-world condition is not simulated.** A KEEP also needs it; this record sizes the A-world pass only.

*Revisit if:* #649's engine `one_sided_betting_bound` differs from the local copy once it merges. The script then imports the engine version and this run is repeated.
