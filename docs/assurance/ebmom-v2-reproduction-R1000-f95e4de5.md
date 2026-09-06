# Reproduction receipt: all five regimes at R = 1000 on the burned root, parts (a), (b) and (c)

**Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md` sections 2, 2.1,
2.2, 4 and 5, FROZEN 2026-09-05 (S414), as amended by the "Ruled S417" paragraph in section 9.
**Ticket:** #443, under #360. **Amendment of record:** skill-harness#442, the S417 comment.
**Generator:** `scripts/ebmom_form_b_reproduction.py --v2`.
**Machine-readable record:** `docs/assurance/ebmom-v2-reproduction-R1000-f95e4de5.json`, with
the per-clause flip rows in the sidecar
`docs/assurance/ebmom-v2-reproduction-R1000-f95e4de5-flips.json`.
**Receipt identity, both halves of v1 section 8 plus the v2 SHA:**
`docs/assurance/ebmom-v2-reproduction-identity-f95e4de5.json`.
**Compared against:** `proto-pb-all-R1000-f95e4de5.json` in the steering repository, SHA-256
`624ed720d4bb5609285f5de87fd9fefa6ffd3831667eef41f89e566a5a7cc70d`.

NOT CONFIRMATORY. The root is the BURNED root
`f95e4de5d261feb7815743abd181105a856ac4a9e79d14f8805146e2d9a42a8a`, seen in full before every
choice v2 records. No confirmatory run has been performed, the fresh root does not yet exist, and
v2 section 5 keeps `agent/issue-360` unmerged until one is. Wall time 9,428.5 s across the five
regimes.

## The result, stated before the explanation

**Part (a), port identity, holds in every regime.** Under `--prototype-seed` production
reproduces the dump with **zero differing cells** — five regimes, four columns, both paths, both
rows, the pooled rows and the vs-oracle excesses. The mechanism as built is the arithmetic v2
section 4 froze.

**Part (b), the production seed, differs in 39 cells, every one of them `cand_pb`.** Reported,
never a kill. `cand_bpB`, `oracle` and `main` agree cell for cell in all five regimes, which is
what the S417 ruling predicts: none of them draws the admitted-path stream.

| regime | wall time | admitted | port diffs | production-seed diffs |
|---|---|---|---|---|
| `small_n_bite` | 1,193.2 s | 979 / 1000 | **0** | 11 |
| `low_heterogeneity` | 1,565.2 s | 687 / 1000 | **0** | 7 |
| `benign_large_n` | 3,105.2 s | 1000 / 1000 | **0** | 9 |
| `tie_heavy_null` | 1,676.0 s | 39 / 1000 | **0** | 3 |
| `tie_heavy_signal` | 1,888.9 s | 1000 / 1000 | **0** | 9 |

**Part (c), the freeze condition on worlds 500 to 999 under the production seed: no candidate
cell rejects in any regime, and the oracle self-check passes every testable cell.**

## Why the production seed differs, and how far the flips reach

The prototype seeds each world's admitted-path draws from `<root>|<regime>|<world>|pb`; production
cannot, because `fit_skill` never receives the world, so v1 section 3's frozen rule seeds it from
the canonical clause encoding. Different integers draw different streams. Measured per clause:

| regime | admitted clause decisions | flips | largest absolute tail movement |
|---|---|---|---|
| `small_n_bite` | 195,800 | 759 | 0.0268 |
| `low_heterogeneity` | 137,400 | 751 | 0.0361 |
| `benign_large_n` | 200,000 | 76 | 0.0042 |
| `tie_heavy_null` | 7,800 | 139 | 0.0381 |
| `tie_heavy_signal` | 200,000 | 1,111 | 0.0340 |

2,836 flips in 740,800 admitted clause decisions, and the largest tail movement anywhere is
0.0381. Every flipped clause sits inside the near-cut band. The per-clause listing with both
tails, the truth and each flipped clause's distance to the nearer cut is in the sidecar, one row
per flip under the field order `flip_fields` declares.

## Part (c): the freeze condition, worlds 500 to 999, production seed

Candidate column, per regime and path. `rejects at` is the smallest number of false selections
that would reject the cell at level 0.01; `-` means **no selection could reject it**.

| regime | cell | false / decisions | `G` | `g` | selected false | rejects at | `p` | verdict |
|---|---|---|---|---|---|---|---|---|
| `small_n_bite` | admitted 5c | 296 / 7,089 | 479 | 168 | 16 | 37 | 0.968 | passes |
| `small_n_bite` | refused 5c | 16 / 147 | 7 | 1 | 0 | 3 | 1.000 | passes |
| `small_n_bite` | admitted 6c | 7 / 120 | 79 | 7 | 6 | 10 | 0.203 | passes |
| `low_heterogeneity` | admitted 5c | 335 / 10,859 | 347 | 184 | 15 | 28 | 0.753 | passes |
| `low_heterogeneity` | refused 5c | 409 / 8,011 | 153 | 126 | 10 | 16 | 0.237 | passes |
| **`low_heterogeneity`** | **admitted 6c** | **1 / 1** | **1** | **1** | **1** | **-** | **0.050** | **passes** |
| `benign_large_n` | admitted 5c | 284 / 46,321 | 500 | 207 | 5 | 38 | 1.000 | passes |
| `benign_large_n` | admitted 6c | 147 / 18,084 | 500 | 127 | 6 | 38 | 1.000 | passes |
| `tie_heavy_null` | admitted 5c | 0 / 890 | 18 | 0 | 0 | 5 | 1.000 | passes |
| `tie_heavy_null` | refused 5c | 0 / 60,914 | 482 | 0 | 0 | 37 | 1.000 | passes |
| `tie_heavy_signal` | admitted 5c | 158 / 11,012 | 499 | 111 | 8 | 38 | 1.000 | passes |

Every other cell is not testable: the candidate mints no decision of that kind there.

**The `low_heterogeneity` admitted 6c cell is the one v2 section 0.6 wrote about, and it behaves
exactly as that section says it does.** One decision-bearing world, one selected decision, and it
is false. It passes — and it passes because with `G = 1` the largest attainable statistic is one
false selection and `P(Binomial(1, 0.05) >= 1) = 0.05`, which is above the level. The harness
prints `rejects at: -` rather than a threshold, so the pass is legible as a property of the
cell's size and not as evidence about the candidate. That is the vacuity section 0.6 named, made
visible instead of inferred. The S414 ruling extended the condition to worlds 1,000 to 3,999 for
exactly this reason; that extension is the companion receipt
`ebmom-v2-reproduction-R4000-low_heterogeneity-f95e4de5.md`, where the same cell is `1 / 7` with
`G = 7`, `rejects at 3`, `p = 0.302` — a pass with power.

**The oracle self-check passes every testable cell in every regime** (11 testable cells across
the five). v2 section 5 makes an oracle failure a harness defect that voids the regime's result;
none occurred.

## The full range, all five regimes, production seed

Candidate column. **No cell rejects.**

| regime | cell | false / decisions | `G` | selected false | rejects at | `p` | verdict |
|---|---|---|---|---|---|---|---|
| `small_n_bite` | admitted 5c | 588 / 13,599 | 963 | 39 | 66 | 0.927 | passes |
| `small_n_bite` | refused 5c | 18 / 220 | 17 | 0 | 4 | 1.000 | passes |
| `small_n_bite` | admitted 6c | 16 / 261 | 160 | 10 | 16 | 0.280 | passes |
| `low_heterogeneity` | admitted 5c | 676 / 21,688 | 687 | 24 | 49 | 0.976 | passes |
| `low_heterogeneity` | refused 5c | 773 / 16,251 | 313 | 15 | 26 | 0.603 | passes |
| `low_heterogeneity` | admitted 6c | 1 / 1 | 1 | 1 | - | 0.050 | passes |
| `benign_large_n` | admitted 5c | 578 / 93,026 | 1000 | 8 | 68 | 1.000 | passes |
| `benign_large_n` | admitted 6c | 291 / 36,322 | 1000 | 8 | 68 | 1.000 | passes |
| `tie_heavy_null` | admitted 5c | 0 / 1,771 | 39 | 0 | 7 | 1.000 | passes |
| `tie_heavy_null` | refused 5c | 0 / 120,466 | 961 | 0 | 65 | 1.000 | passes |
| `tie_heavy_signal` | admitted 5c | 322 / 22,744 | 998 | 16 | 68 | 1.000 | passes |

Under v2 section 5's kill criterion — any rejection in any 5c or 6c cell, on either path, in any
registered regime — **no cell convicts on the burned root**. That is a development reading and
not a verdict: the criterion is written for the fresh root, and section 5 is explicit that a pass
in a sparse cell is weak evidence.

**`main` reproduces v2 section 6's prediction to the decimal.** Section 6 predicted `main` fails
6c on the admitted path in `small_n_bite` and `low_heterogeneity` "(12.4 and 40 percent false)".
Measured here: `low_heterogeneity` admitted 6c 203 / 504 = **40.3 percent**, 141 of 340 selected
decisions false, `p < 1e-300`; `small_n_bite` admitted 6c 437 / 3,510 = **12.4 percent**, 132 of
952 selected false, `p < 1e-300`. `main` also fails `low_heterogeneity` refused 6c, 27 / 84
across 75 worlds. Reported, and it is not a verdict on `main`: it is the measured reason v2
section 1 stopped using `main` as the comparator, arriving independently through the built
harness.

## Rows 1 to 4

`tie_heavy_null` admits 39 of 1,000, against the registered `alpha = 0.05`. Relative bias of
`latent_raw` is within 0.02 in absolute value in every heterogeneous regime (0.0001, -0.0175,
-0.0147, 0.0001), well inside the 0.10 tolerance. Every refusal in every regime is
`latent_variance_not_identified`, and the pooled path reverted to unpooled **zero times** across
all 5,000 replicate-regimes.

## What this receipt claims and does not claim

- **Claims:** that the built mechanism reproduces the prototype dump exactly under the
  prototype's own seed, in all five registered regimes and every cell; that under production's
  own seed 39 `cand_pb` cells differ, driven by 2,836 near-cut flips in 740,800 admitted clause
  decisions with a largest tail movement of 0.0381; and that v2 section 4's freeze condition,
  evaluated once on worlds 500 to 999 under the production seed, rejects no candidate cell and
  passes the oracle self-check on every testable cell.
- **Does not claim** that the candidate reproduces `cand_pb` under its own seed. It does not, and
  the S417 amendment is why that is reported rather than treated as a defect.
- **Does not claim** a confirmatory result or a verdict on the candidate. The root is burned
  development evidence; the fresh root does not exist yet and its digest is committed by a
  session that neither built nor ruled.
- **Does not decide** the consequence of part (c). v2 section 4 owns it, and nothing rejected.
- **Does not claim** the `low_heterogeneity` admitted 6c cell is evidence of anything. At `G = 1`
  no selection could have rejected it, which the receipt prints rather than leaves to be worked
  out.
