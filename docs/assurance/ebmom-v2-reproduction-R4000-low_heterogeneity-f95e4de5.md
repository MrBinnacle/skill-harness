# Reproduction receipt: `low_heterogeneity` at R = 4000 on the burned root, parts (a), (b) and (c)

**Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md` sections 2, 2.1,
2.2, 4 and 5, FROZEN 2026-09-05 (S414), as amended by the "Ruled S417" paragraph in section 9.
**Ticket:** #443, under #360. **Amendment of record:** skill-harness#442, the S417 comment.
**Generator:** `scripts/ebmom_form_b_reproduction.py --v2`.
**Machine-readable record:**
`docs/assurance/ebmom-v2-reproduction-R4000-low_heterogeneity-f95e4de5.json`, with the per-clause
flip rows in the sidecar
`docs/assurance/ebmom-v2-reproduction-R4000-low_heterogeneity-f95e4de5-flips.json`.
**Receipt identity, both halves of v1 section 8 plus the v2 SHA:**
`docs/assurance/ebmom-v2-reproduction-identity-f95e4de5.json`.
**Compared against:** `proto-pb-low_heterogeneity-R4000-f95e4de5.json` in the steering
repository, SHA-256 `73757f0e03e3694402accf152d0f8ed2f1612c3318513dda982a2d8fb71f58d6`.

NOT CONFIRMATORY. The root is the BURNED root
`f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`, whose 5,000 worlds became
development evidence when the 2026-09-05 run rejected. No confirmatory run has been performed and
v2 section 5 keeps `agent/issue-360` unmerged until one is. Wall time 5,718 s.

## The result, stated before the explanation

**Part (a), port identity, holds.** Under `--prototype-seed` production reproduces the dump with
**zero differing cells**, across all four columns (`cand_pb`, `cand_bpB`, `oracle`, `main`), both
paths, both rows, the pooled rows and the vs-oracle excesses. The mechanism as built is the
arithmetic v2 section 4 froze.

**Part (b), the production seed, differs in 11 places, all of them `cand_pb`.** Reported, never a
kill.

| cell | built | dump | direction |
|---|---|---|---|
| `row5c_false_pass_admitted.count` | 2,844 | 2,830 | +14 |
| `row5c_false_pass_admitted.of` | 89,072 | 89,214 | -142 |
| `row5c_false_pass_admitted.false_worlds` | 1,563 | 1,566 | -3 |
| `row6c_false_fail_admitted.of` | 8 | 6 | +2 |
| `row6c_false_fail_admitted.worlds` | 8 | 6 | +2 |
| `excess_over_main_vs_oracle` | 23,752 / -2,259 / -29,283 | 23,695 / -2,261 / -29,482 | +57 / +2 / +199 |

The three pooled 5c rows and the two pooled 6c rows carry the same differences by construction and
are not counted twice here. **`cand_bpB`, `oracle` and `main` agree cell for cell**, which is what
the S417 ruling predicts: none of them draws the admitted-path stream.

**Part (c), the freeze condition on worlds 1,000 to 3,999 under the production seed: no cell
rejects.**

## Why the production seed differs, and why that is not a defect

The prototype seeds each world's admitted-path draws from `<root>|<regime>|<world>|pb`, which a
harness can compute because it knows which world it drew. `fit_skill` never receives the world and,
under the frozen v1 section 3 rule, seeds from `<canonical clause encoding>|pb`. Different integers
draw different streams.

The flip listing measures what that costs, per clause, over all 565,000 admitted clause decisions:

| quantity | value |
|---|---|
| admitted worlds | 2,825 |
| admitted clause decisions | 565,000 |
| decisions that flip between the two seeds | 2,458 |
| clauses within 0.03 of a cut under the production seed | 136,644 |
| largest distance to a cut among the flipped clauses | **0.003736** |
| largest absolute tail movement over all 565,000 clauses | **0.037853** |

Every flipped clause sits within 0.0038 of a decision cut. The flips are almost entirely at the
PASS cut and close to symmetric: 1,299 move UNDECIDED to PASS, 1,157 move PASS to UNDECIDED, and 2
move FAIL to UNDECIDED. That is Monte Carlo error in an averaged tail landing on the other side of
a boundary, not a different mechanism.

## Part (c): the freeze condition on worlds 1,000 to 3,999, production seed

v2 section 4's S414 rule evaluates the condition on 3,000 burned-root worlds never generated for
any class, under the section 2.1 exact test. The S417 ruling repeats it once on the production
stream. Candidate column, per path:

| cell | false / decisions | `G` | `g` | selected false | rejects at | `p` | verdict |
|---|---|---|---|---|---|---|---|
| admitted 5c | 2,168 / 67,384 | 2,138 | 1,201 | 71 | 132 | 1.000 | passes |
| refused 5c | 2,291 / 44,948 | 859 | 643 | 45 | 59 | 0.396 | passes |
| **admitted 6c** | **1 / 7** | **7** | **1** | **1** | **3** | **0.302** | **passes** |
| refused 6c | 0 / 0 | 0 | 0 | - | - | - | not testable |

The admitted 6c cell is the one v2 section 0.7 measured at `1 / 5 (G = 5), p = 0.226` on the
prototype stream. On the production stream it is `1 / 7 (G = 7), p = 0.302`. **It passes with
power**: the rejecting count is 3, so three false selections of seven would have rejected it, and
one did not. This is a replication of the S414 experiment on a second stream, and it agrees with
S414 in direction and in kind.

**The oracle self-check passes** both testable cells on this range. The two 6c cells are not
testable because the oracle mints no FAIL claim here, which is the abstention v2 section 4's
freeze condition asks the mechanism to match.

**This receipt does not decide the consequence.** v2 section 4 owns it, and section 9's S417
ruling says so in terms: a rejection here would resume that section's sequence rather than create
a new kill. Nothing rejected.

## The full range, reported because section 5 asks for it

Over all 4,000 worlds under the production seed, candidate column:

| cell | false / decisions | `G` | `g` | selected false | rejects at | `p` | verdict | world-block bound |
|---|---|---|---|---|---|---|---|---|
| admitted 5c | 2,844 / 89,072 | 2,825 | 1,563 | 95 | 170 | 1.000 | passes | 0.0306 |
| refused 5c | 3,064 / 61,199 | 1,172 | 887 | 60 | 78 | 0.444 | passes | 0.0476 |
| **admitted 6c** | **2 / 8** | **8** | **2** | **2** | **3** | **0.0572** | **passes** | 0.0000 |
| refused 6c | 0 / 0 | 0 | 0 | - | - | - | not testable | - |

**The admitted 6c cell is one selection away from rejecting, and that is stated rather than
buried.** Two of the eight selected FAIL decisions are false; three would have rejected at level
0.01. v2 section 6 wrote this cell's distribution before the run: at the burned-root rate a fresh
root rejects it with probability about 0.07. The full range is **not** one of the pre-committed
freeze ranges — (c) is worlds 1,000 to 3,999, and it passes there at `p = 0.302` — so this figure
is reported evidence about the cell's sparsity, not a verdict.

The world-block bound reads 0.0000 on that cell, which is the vacuity v2 section 2.1 demoted it
for: with two false-bearing worlds in 4,000, the bound is 0 by construction whatever the rate.

`main` on the same worlds fails both 6c cells decisively — admitted 703 / 2,001 across 1,336
worlds, 457 of 1,336 selected decisions false, `p = 9.7e-244`; refused 85 / 266 across 241 worlds,
77 of 241 selected false, `p = 3.4e-40`. Reported, and it is not a verdict on `main`: it is the
measured reason v2 section 1 stopped using `main` as the comparator.

## Rows 2, 3, 4 and 9

Admission rate 2,825 / 4,000 = 0.706. Relative bias of `latent_raw` -0.0091, well inside the
0.10 tolerance. Every refusal is `latent_variance_not_identified` (1,175 of them) and the pooled
path reverted to unpooled **zero** times.

The reliability table shows where the two deciders differ, in tenths of the fitted
`P(theta > 0.60)` against the empirical frequency of `theta > 0.60`:

| bin | `cand_pb` n | `cand_pb` freq | `main` n | `main` freq |
|---|---|---|---|---|
| 0.0-0.1 | 76 | 0.263 | 7,769 | **0.429** |
| 0.1-0.2 | 697 | 0.330 | 22,384 | 0.552 |
| 0.4-0.5 | 14,663 | 0.580 | 45,848 | 0.762 |
| 0.9-1.0 | 335,200 | 0.937 | 203,602 | 0.958 |

`main` assigns 7,769 clause decisions a fitted tail below 0.10 while 43 percent of them are
truly above the threshold. That is the miscalibration its 6c cell reports as a rate, shown here
as a shape.

## What this receipt claims and does not claim

- **Claims:** that the built mechanism reproduces the prototype dump exactly under the
  prototype's own seed, all four columns and every cell; that under production's own seed
  eleven `cand_pb` cells differ and every one of the flips behind them sits within 0.0038 of a
  decision cut; and that v2 section 4's freeze condition, evaluated once on worlds 1,000 to
  3,999 under the production seed, rejects no cell and passes the admitted 6c cell with a
  rejecting count of 3.
- **Does not claim** that the candidate reproduces `cand_pb` under its own seed. It does not, and
  the S417 amendment is why that is reported rather than treated as a defect.
- **Does not claim** any confirmatory result. The root is burned development evidence; the fresh
  root does not yet exist and its digest is committed by a session that neither built nor ruled.
- **Does not decide** the consequence of part (c). v2 section 4 owns it.
- **Does not claim** the admitted 6c cell is safe. At `2 / 8` over the full range it is one
  selection from rejecting, and v2 section 5 is explicit that a pass in a cell that small is weak
  evidence.
