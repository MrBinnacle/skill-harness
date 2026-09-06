# Reproduction receipt: mechanism class 2 from production, R = 40, `SMOKE_NOT_CONFIRMATORY`

**Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md` section 4, FROZEN
2026-09-05 (S414). **Ticket:** #442, under #360.
**Generator:** `scripts/ebmom_form_b_reproduction.py --column cand_pb`.
**Machine-readable records:** `docs/assurance/ebmom-class2-reproduction-R40-SMOKE_NO.json`
(production) and `docs/assurance/ebmom-class2-reproduction-R40-SMOKE_NO-prototype-seed.json`
(diagnostic).
**Compared against:** `proto-pb-all-R40-SMOKE_NO.json` in the steering repository, column
`cand_pb`, SHA-256 recorded in both JSON records.

NOT CONFIRMATORY. Root `SMOKE_NOT_CONFIRMATORY`, R = 40, a development smoke. No confirmatory run
has been performed and v2 section 5 keeps this branch unmerged until one is.

## The result, stated before the explanation

Twenty cells are compared: five regimes, two paths, rows 5c and 6c. **Fifteen agree with the
prototype and five do not.** Every disagreement is on the ADMITTED path, in two regimes:

| regime | path | cell | built | prototype |
|---|---|---|---|---|
| `small_n_bite` | admitted | 6c `of` | 9 | 8 |
| `small_n_bite` | admitted | 6c `worlds` | 6 | 5 |
| `tie_heavy_signal` | admitted | 5c `count` | 7 | 6 |
| `tie_heavy_signal` | admitted | 5c `of` | 864 | 854 |
| `tie_heavy_signal` | admitted | 5c `false_worlds` | 6 | 5 |

`low_heterogeneity`, `benign_large_n` and `tie_heavy_null` agree in every cell on both paths, and
**every refused-path cell in every regime agrees**, which is the whole of the refused path at
R = 40: `tie_heavy_null` refuses all 40 replicates and reproduces cell for cell.

## Why the five differ, measured rather than argued

The prototype seeds its draws from the world it drew, `<root>|<regime>|<world>|pb`, because a
harness knows which world that is. `fit_skill` does not: it sees clauses and nothing else, so v2
section 4 and the ticket both derive its seed from the canonical clause encoding under v1
section 3's frozen procedure, with the label `pb`. **The two are different integers and draw
different streams**, so the mechanism's Monte Carlo average lands in a slightly different place
even when the arithmetic is identical, and a clause sitting near the 0.95 or 0.05 boundary can
cross it.

That leaves a question the table above cannot answer on its own: is a differing cell the seed, or
the port? The generator has a diagnostic mode that makes production consume the prototype's
stream and changes nothing else. Under it, **production reproduces `cand_pb` in all twenty cells,
all five regimes, exit code 0** — the second JSON record beside this file. The seed is therefore
the whole of the difference, and the mechanism as built is the mechanism v2 measured.

The bit-level identity is pinned separately and does not depend on this run:
`tests/test_aggregation_fit_admitted_bootstrap.py` drives the built mechanism with the
prototype's seed on the four named worlds of v2 section 0.5 and requires the prototype's
probabilities to four decimal places, `P = 0.0429` on world 783 among them.

## What was compared

Per regime, per path, the false-PASS (5c) and false-FAIL (6c) cells: the false count, the
decision count, the cluster count `G` and the false-bearing world count `g`. Truth is the true
encoded clause mean the generator returns and the v1 harness discards. The decision rule and the
regimes are imported from `scripts/ebmom_acceptance_matrix.py` rather than restated, so a drift
between harness and reproduction fails here instead of producing two implementations that agree
with themselves.

## What this receipt claims and does not claim

- **Claims:** that the refused path is untouched by the admitted-path work at R = 40, cell for
  cell; that the admitted-path mechanism as built is the prototype's arithmetic, shown by an
  exact reproduction under the prototype's seed; and that under the seed production is obliged to
  use, five of twenty cells move by one or two decisions.
- **Does not claim** that the built candidate reproduces `cand_pb` under its own seed. It does
  not, in two regimes, and the acceptance criterion that asked for it is recorded as NOT MET as
  written on #442 rather than reinterpreted here.
- **Does not claim** anything about R = 1000 or R = 4000. The harness ticket owns those, and a
  cell that moves by one decision at R = 40 may or may not move at R = 1000.
- **Does not claim** that any cell passes or fails the kill criterion. This receipt compares
  counts against a prototype; the kill rows are v2 section 5's and need a confirmatory run.
