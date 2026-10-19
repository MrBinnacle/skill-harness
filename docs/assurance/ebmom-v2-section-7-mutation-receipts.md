# The four v2 section 7 mutation receipts, in one place

**Specification:** `docs/assurance/ebmom-peel-preregistration-amendment-v2.md` section 7, FROZEN
2026-09-05 (S414). **Standard:** #341. **Ticket:** #444, under #360.

Section 7 registers four mutants and requires each to be killed by a named assertion. This page
is the index: it says where each receipt is and what it found. It is not itself a receipt and it
measures nothing.

**Why no digests appear here.** Each receipt pins the file it measured in its own
`target_digests`, and two tests in `tests/test_mutation_receipt.py` hold that pin honest —
`test_receipt_still_describes_the_files_it_measured` compares it against the live tree, and
`test_prose_companion_names_the_digest_its_receipt_attests` compares each receipt against its own
prose. A digest copied into this index would be guarded by neither, so it could go stale in
silence while both tests stayed green. The receipts are the authority; this page points at them.

## The four

| v2 mutant | id | receipt (JSON + `.md` beside it) | target | verdict | killed by |
|---|---|---|---|---|---|
| 1. Pooling removed on the refused path | M-V1 | `ebmom-v2-form-b-mutation-receipt` | `src/skill_harness/aggregation/fit.py` | **KILLED** | `tests/test_aggregation_fit_bounded_pooling.py::test_mutant_1_tie_heavy_null_refused_false_fail_rate` |
| 2. Per-path split removed (rows pooled) | M-V2 | `ebmom-v2-per-path-split-mutation-receipt` | `scripts/ebmom_acceptance_matrix.py` | **KILLED** | `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_2_low_heterogeneity_refused_cell_carries_its_own_G` |
| 3. One-per-world selection replaced by all decisions | M-V3 | `ebmom-v2-one-per-world-mutation-receipt` | `scripts/ebmom_acceptance_matrix.py` | **KILLED** | `tests/test_ebmom_acceptance_matrix_v2.py::test_mutant_3_two_correlated_false_decisions_do_not_reject` |
| 4. The admitted-path mechanism removed (plug-in restored) | M-V4 | `ebmom-v2-class2-mutation-receipt` | `src/skill_harness/aggregation/fit.py` | **KILLED** | `tests/test_aggregation_fit_admitted_bootstrap.py::test_mutant_4_low_heterogeneity_admitted_false_fail_rate` |

All four are in `docs/assurance/`. Section 7 conditions the fourth on section 4 freezing a
mechanism, which it did; the receipt exists because that condition was met.

Mutants 2 and 3 carry controls as well as kills, because a kill alone does not show the
assertion is the thing doing the killing. Mutant 2's control requires the pooled cell to be
unchanged under the mutant, and the first version of that control did not survive it — that is
recorded on the receipt rather than repaired away.

## The other receipts in this directory, and what they are not

`docs/assurance/` also holds mutation receipts from earlier repairs — the EB-MoM gate campaign
(`ebmom-gate-mutation-receipt`, obligations A and B under the v1 amendment section 6), and the
#363, #366, #387 and #389 repairs. **None of those is a v2 section 7 mutant.** They are indexed
nowhere on this page beyond this paragraph, and a reader counting "mutation receipts in
`docs/assurance/`" will get a larger number than four for that reason.

The EB-MoM gate receipt records one **SURVIVED** case, M-A3, a tie-blind peel that the
differential suite cannot see because its 1,000 seeded inputs are tie-free. It is preserved
rather than deleted: `SURVIVED` is deliberately not in `INVALID_VERDICTS`, so a survivor is a
finding and not a failure.

## Revisit if

- Section 7 gains or loses a mutant. Then this table is wrong by exactly that row, and nothing
  in the test suite will say so — the suite gates each receipt's currency, not this index's
  completeness.
- A receipt is regenerated and a verdict changes. The verdicts above were true when written and
  are not re-checked by any gate.
