#685 lever adjudication: Stage 1 results

Replicates per cell: 200. Seed: 685. MC SE of P(PASS) at the nominal 0.0209: 0.01012; calibration limit 0.0209 + 3 SE = 0.05125.

## Stage 1 designs

Null allocation x F-N construction, at caps 97 and 400.
Null allocation levels: (0.5, 1.0, 2.0).
F-N constructions: ('union', 'direct').

## Surface at the cap (subset: n_pairs=400, null_per_pair=1.0)

| n_pairs | null_pp | fn_con | p_P | p_N | d | role | p_F | P(PASS) | SE | P(CUT) | P(CANT) | E[pairs] | cal | price |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Headline: smallest d with P(PASS) >= 0.80 at 400 pairs, null_per_pair=1.0

| fn_construction | p_P | p_N | smallest d |
| --- | --- | --- | --- |
| union | 0.30 | 0.30 | not reached on this grid |
| union | 0.30 | 0.35 | not reached on this grid |
| union | 0.30 | 0.40 | not reached on this grid |
| union | 0.35 | 0.30 | not reached on this grid |
| union | 0.35 | 0.35 | not reached on this grid |
| union | 0.35 | 0.40 | not reached on this grid |
| union | 0.40 | 0.30 | not reached on this grid |
| union | 0.40 | 0.35 | not reached on this grid |
| union | 0.40 | 0.40 | not reached on this grid |
| direct | 0.30 | 0.30 | not reached on this grid |
| direct | 0.30 | 0.35 | not reached on this grid |
| direct | 0.30 | 0.40 | not reached on this grid |
| direct | 0.35 | 0.30 | not reached on this grid |
| direct | 0.35 | 0.35 | not reached on this grid |
| direct | 0.35 | 0.40 | not reached on this grid |
| direct | 0.40 | 0.30 | not reached on this grid |
| direct | 0.40 | 0.35 | not reached on this grid |
| direct | 0.40 | 0.40 | not reached on this grid |

## Headline: smallest d with P(PASS) >= 0.90 at 400 pairs, null_per_pair=1.0

| fn_construction | p_P | p_N | smallest d |
| --- | --- | --- | --- |
| union | 0.30 | 0.30 | not reached on this grid |
| union | 0.30 | 0.35 | not reached on this grid |
| union | 0.30 | 0.40 | not reached on this grid |
| union | 0.35 | 0.30 | not reached on this grid |
| union | 0.35 | 0.35 | not reached on this grid |
| union | 0.35 | 0.40 | not reached on this grid |
| union | 0.40 | 0.30 | not reached on this grid |
| union | 0.40 | 0.35 | not reached on this grid |
| union | 0.40 | 0.40 | not reached on this grid |
| direct | 0.30 | 0.30 | not reached on this grid |
| direct | 0.30 | 0.35 | not reached on this grid |
| direct | 0.30 | 0.40 | not reached on this grid |
| direct | 0.35 | 0.30 | not reached on this grid |
| direct | 0.35 | 0.35 | not reached on this grid |
| direct | 0.35 | 0.40 | not reached on this grid |
| direct | 0.40 | 0.30 | not reached on this grid |
| direct | 0.40 | 0.35 | not reached on this grid |
| direct | 0.40 | 0.40 | not reached on this grid |

## Price lines

| n_pairs | total_epochs | price @ $0.083 | price @ $0.087 | cap @ $0.30/epoch |
| --- | --- | --- | --- | --- |
| 97 | 291 | $24.15 | $25.32 | $87.30 |
| 97 | 242 | $20.09 | $21.05 | $72.60 |

## Joint terminal state (subset: n_pairs=400, null_per_pair=1.0, union)

Median [10th, 90th percentile]. LB(F-P) and UB(F-P) on d scale.

| n_pairs | null_per_pair | fn_construction | p_P | p_N | d | joint state | count | share | LB(F-P) | LB(F-N) | UB(F-P) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Model statement

These results establish operating characteristics under the declared independent-Bernoulli model. They do not establish how many real Claude Code epochs are required.

## Pairing statement

Full and Placebo are paired by launch index; under independent draws this confers no matched-pairs advantage.

## Crashed-look rule and void-epoch rule for the next paid run

Crashed-look rule: If a look crashes after at least two valid epochs, the look is void and the run continues from the next look. If the crash occurs at look 1, the entire cell is void and must be rerun.

Void-epoch rule: An epoch that produces no model output (timeout, error, or empty response) is void and excluded from the bound calculation. The run continues; void epochs do not count toward the pair cap.
