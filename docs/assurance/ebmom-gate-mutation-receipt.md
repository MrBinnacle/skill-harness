# Mutation receipt: the #360 heterogeneity gate and peel

**Standard:** #341. **Specification:** `docs/assurance/ebmom-peel-preregistration-amendment.md`.
**Run:** hand-run campaign, 2026-09-01, six mutants, on `agent/issue-360`.
**Discharges:** amendment section 6, which requires a receipt naming the obligation each kill
belongs to.

Amendment section 6 splits the differential test into two obligations:

- **Obligation A — the numerics of the selected method.** Cross-checked by
  `tests/test_aggregation_differential.py`, whose reference re-derives the estimator from the
  specification rather than by calling production.
- **Obligation B — the method selection itself.** The differential test may branch on the method
  production selected, so it structurally cannot see a wrong selection. Obligation B is carried
  by independent admission tests in `tests/test_aggregation_fit.py` and by acceptance-matrix
  rows 1 and 2.

Every mutant below was confirmed to **import successfully** before its test selection ran. A
mutant that fails to compile is stillborn and is not a kill. Kills are attributed to the
**named failing assertion**, never to an exit code.

## Results

| mutant | obligation | mutation | verdict | killing assertion |
|---|---|---|---|---|
| M-A1 | A | revert the finite-K correction: `/(k-1)` becomes `/k` | **KILLED** | `test_aggregation_differential.py::TestFitSkillDifferential::test_1000_seeded_inputs_match_reference` |
| M-A2 | A | wrong peel denominator: `(n-1)*n` becomes `n*n` | **KILLED** | same assertion |
| M-A3 | A | tie-blind peel: ignore `sum_sq`, use the Bernoulli form | **SURVIVED the differential suite**; killed by acceptance-matrix row 3 on `tie_heavy_signal` | see below |
| M-B1 | B | remove the gate: always admit | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_marginal_heterogeneity_is_refused_not_fitted` |
| M-B2 | B | seed from a constant rather than from the data | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_seed_covers_sum_sq_not_just_w_and_n` |
| M-B3 | B | drop the `+1` finite-bootstrap correction | **KILLED** | `test_aggregation_fit.py::TestFitSkillEbmom::test_marginal_heterogeneity_is_refused_not_fitted` |

Production bytes were restored after each mutant and the restore was verified byte-identical
against the pre-campaign snapshot. Restores use `write_bytes`, never `write_text`: newline
translation on this host CRLF-corrupts files and silently changes byte-hashed identities.

## The survivor is the finding, and it is why the tie regimes exist

**M-A3 is invisible to the entire differential suite.** Its 1,000 seeded inputs are tie-free, and
on tie-free data `sum_sq == w`, so the sufficient-statistic peel and the Bernoulli peel are
algebraically identical. The reference and production agree because on that data they are the
same function. No amount of additional tie-free inputs would change this.

It is caught by the registered tie regime instead:

| code | `tie_heavy_signal` relative bias of `latent_raw` | within the 10 percent bound | admission rate |
|---|---|---|---|
| clean | **+0.0420** | yes | 1.00 |
| M-A3 | **-0.9281** | no | 0.25 |

(Root seed `SMOKE_NOT_CONFIRMATORY`, R=20. These are **development numbers from a smoke
configuration**, run to establish that the mutant is detectable at all. They are not a
confirmatory result and R=20 is not the registered R=1000.)

The mutant understates the latent variance by 93 percent, because a tie-heavy clause has less
within-clause variance than the Bernoulli formula assumes, so it is over-peeled. Admission then
collapses from 1.00 to 0.25: the gate correctly refuses to fit a hyperprior it can no longer
identify, which means the defect partly hides behind an honest refusal rather than announcing
itself.

**Consequence for the acceptance matrix:** `tie_heavy_signal` is load-bearing, not decorative. A
confirmatory run that omitted it would ship a tie-blind peel with a green differential suite.
This is the concrete justification for the amendment's rule that a run reporting only the
tie-free regimes is not a confirmatory run.

## What this receipt does not claim

- It does not claim the mutant set is exhaustive. Six mutants were chosen to probe the specific
  seams the amendment freezes; they are not a saturating campaign, and no mutation score is
  reported because a hand-run campaign cannot support one.
- It does not claim the candidate passes the acceptance matrix. **No confirmatory run has been
  performed.** The smoke numbers above exist only to show a mutant is detectable.
- It does not claim obligation B is fully covered by three mutants. Rows 1 and 2 of the
  acceptance matrix bound the selection's error rate, and those rows have not yet been run at
  the registered replication.
