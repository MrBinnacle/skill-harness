#718 Stage 2: stopping design x pairs under #685

Replicates per cell: 200. Seed: 685.
Stoppings: anytime, anytime-tuned, fixed-n-betting, fixed-n-score.
Pairs: (100, 200, 300, 400, 500, 600, 800). Null per pair: (1.0, 0.5).
Fixed-n pass alphas: (0.0209, 0.0105, 0.005). Starting wealths: (1.0, 0.5, 0.25).
CUT alpha 0.05 on every row. F - N construction: direct on every new design;
union only on anytime rows.

## Headline: smallest priced configuration meeting the diagonal target

The diagonal target is the minimum over the three p_P = p_N cells of
P(joint PASS) at d = 0.30 and of P(CUT) at d = 0.10, each at or above the
target. Rows that fail calibration are excluded unless they are fixed-n-score
rows, which are labelled as not holding their level. Configurations are
ranked by total_epochs (the cap price), then by expected epochs.

| stopping | pass_alpha | starting_wealth | target | smallest priced configuration | total_epochs | expected spend | cap price | P(PASS) at d=0.30 | P(CUT) at d=0.10 | missing half | holds level |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anytime | 0.0209 | 1.00 | 0.80 | not reached | - | - | - | 0.0000 | 0.1650 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime | 0.0209 | 1.00 | 0.90 | not reached | - | - | - | 0.0000 | 0.1650 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 0.25 | 0.80 | not reached | - | - | - | 0.0000 | 0.0100 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 0.25 | 0.90 | not reached | - | - | - | 0.0000 | 0.0100 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 0.50 | 0.80 | not reached | - | - | - | 0.0000 | 0.0400 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 0.50 | 0.90 | not reached | - | - | - | 0.0000 | 0.0400 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 1.00 | 0.80 | not reached | - | - | - | 0.0050 | 0.1200 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| anytime-tuned | 0.0209 | 1.00 | 0.90 | not reached | - | - | - | 0.0050 | 0.1200 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0050 | 1.00 | 0.80 | not reached | - | - | - | 0.0000 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0050 | 1.00 | 0.90 | not reached | - | - | - | 0.0000 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0105 | 1.00 | 0.80 | not reached | - | - | - | 0.0100 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0105 | 1.00 | 0.90 | not reached | - | - | - | 0.0100 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0209 | 1.00 | 0.80 | not reached | - | - | - | 0.0150 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-betting | 0.0209 | 1.00 | 0.90 | not reached | - | - | - | 0.0150 | 0.1300 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0050 | 1.00 | 0.80 | not reached | - | - | - | 0.0250 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0050 | 1.00 | 0.90 | not reached | - | - | - | 0.0250 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0105 | 1.00 | 0.80 | not reached | - | - | - | 0.0550 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0105 | 1.00 | 0.90 | not reached | - | - | - | 0.0550 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0209 | 1.00 | 0.80 | not reached | - | - | - | 0.1150 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |
| fixed-n-score | 0.0209 | 1.00 | 0.90 | not reached | - | - | - | 0.1150 | 0.3950 | P(joint PASS) >= target at d = 0.30 and P(CUT) >= target at d = 0.10 | yes |

From the committed data: no design meets the 0.80 target with a cap price under $100, and no design meets it with expected spend under $100.

## Calibration read

P(PASS) is an error wherever the true F-P or F-N is at or below 0.20,
compared against the row's pass_alpha plus 3 MC SE. P(CUT) is an error
wherever the true F-P is at or above 0.20, compared against 0.05 plus
3 MC SE. A fixed-n-score row that fails calibration is labelled as not
holding its level and left out of the headline; it does not fail the run.
Every other design's failure does.

Rows that fail calibration: 0.
Fixed-n-score rows labelled not holding level: 0.
Fatal calibration failures (non-score designs): 0.

These smoke-run results establish only the output schema under the declared
independent-Bernoulli model. They do not establish operating characteristics
or how many real Claude Code epochs are required.

## Price lines

List rates $0.083 and $0.087 per epoch; cap rate $0.30.

## Pairing statement

Full and Placebo are paired by launch index; under independent draws
this confers no matched-pairs advantage.

## Crashed-look and void-epoch rules

skill-harness #697 owns the crashed-look rule and the void-epoch rule
for the next paid run; this record states neither.
