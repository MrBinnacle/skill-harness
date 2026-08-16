# Assurance close-out

This is the close-out record for the assurance pass begun under issue #160. The
figures below come from checked-in run reports. They describe the recorded runs,
not the absence of defects.

## Recorded results

- **Mutation.** The scoped mutmut run scored aggregation at 81.7% (1,556 killed,
  349 survived), ablation at 76.2% (1,793 killed, 560 survived), extractor at
  70.1% (1,406 killed, 601 survived), and audit at 80.6% (50 killed, 12 survived).
  Ablation also had 27 no-test mutants and extractor had 14; those are not in the
  score denominator (`docs/assurance/mutation-report.md`, #166).
- **A/A false positives.** The two-arm gate made 26 / 500 directional calls on
  identical arms, a 5.2% false-positive rate inside the registered count band
  [16, 35] (`docs/assurance/aa-report.md`, seed `163_2026_08_09`, #163).
- **Calibration coverage.** The production anytime-valid confidence sequence
  covered at least 495 / 500 replications in every cell of the 30-cell grid; the
  registered lower edge was 465 / 500. The retained legacy posterior interval
  covered 470 / 500 at p=0.50, 441 / 500 at p=0.65, and 491 / 500 at p=0.85;
  the latter two missed its two-sided [465, 484] band
  (`docs/assurance/calibration-report.md`, seeds `187_2026_08_09` and
  `164_2026_08_09`, #164 and #187).
- **Differential agreement.** Four audited numerical functions agreed on
  4,000 / 4,000 seeded inputs against independent scipy, statsmodels, or
  published-formula references at the pre-stated tolerances. The maximum
  observed error was zero for three functions and less than 1e-15 for the
  quadrature comparison (`docs/assurance/differential-report.md`, seed
  `165_2026_08_09`, #165).
- **Fuzzing.** Two atheris targets ran for 60.1 minutes in total and found
  0 crashes: 10,375,786 parser executions and 140,340,401 JSON-ingestion
  executions. The JSON target was random-input testing around an uninstrumented
  compiled validation core, not coverage-guided search over that core
  (`docs/assurance/fuzz-report.md`, `fuzz/artifacts/*.json`, #170).
- **Static analysis.** Ruff enables B, PL, and RUF without blanket ignores, and
  CI randomizes test order with a printed reproduction seed. Branch coverage was
  measured for 20 aggregation and ablation modules; the paired coverage/mutation
  attention rule flagged 7 of 20. Four had branch coverage above 80% but mutation
  below 80%, and `aggregation/confidence_sequence.py` had 68.5% branch coverage
  with no mutation result (`docs/assurance/coverage-floors.md`, #171;
  `tests/test_assurance_static_analysis_171.py`).
- **Supply chain.** On 2026-08-15, pip-audit 2.10.1 reported
  `No known vulnerabilities found` for the installed development environment
  and exited 0. A deliberate `jinja2==2.11.3` environment produced four
  advisories and exit 1, showing that the CI command can report findings. All six
  workflow files then present used commit-SHA action pins, explicit
  least-privilege permission baselines, and no `pull_request_target`; neither the
  dependency audit nor Scorecard was made a required check
  (`docs/assurance/dependency-audit.md` and
  `docs/assurance/workflows-audit.md`, #172).
- **Independent re-derivation.** The requested result is missing. No Phase 6 or
  #173 re-derivation report exists under `docs/assurance/` in this worktree, so
  there is no recorded run from which to quote a result. Issue #173 is closed,
  but closure is not a numerical receipt. This close-out does not reconstruct or
  invent that figure.

## Residual risks

- There is no recall claim on the vacuity flag in this close-out: recall is
  UNMEASURED by the assurance report set. The assurance
  report set named by this ticket contains no recall run, and flag precision does
  not establish recall. Calibration records outside `docs/assurance/` — including
  the #189 adjudication receipt, in the tree since 2026-08-09 — are out of this
  close-out's scope rather than later than it.
- Extraction repeat-instability stands: identical runs returned 29/33/34 clauses.
  This is a documented instrument property, not a bug. Clause position is not a
  stable identity (`README.md`, #152).
- The single-maintainer review limits apply. Configuration review, mutation survivor
  classification, and the report synthesis do not provide independent human
  replication. The missing #173 re-derivation receipt leaves that limit unresolved.
- The legacy posterior credible interval still misses the registered frequentist
  coverage band at p=0.65 and p=0.85. It is retained as Bayesian-only; the public
  report surface uses the calibrated anytime-valid confidence sequence
  (`docs/findings/aggregation-ci-coverage-under-sequential-stop.md`).
- The fuzz run does not support a coverage claim over pydantic_core, and neither
  fuzz target was run on Windows (`docs/assurance/fuzz-report.md`).
- Mutation used scoped test selections. It did not mutate the later
  `aggregation/confidence_sequence.py`; 27 ablation and 14 extractor mutants were
  classified as no-tests (`docs/assurance/mutation-report.md` and
  `docs/assurance/coverage-floors.md`).
- Supply-chain results cover published advisories and the workflow files present
  on 2026-08-15. They do not establish absence of vulnerabilities, pin shell
  installs, or observe branch-protection enforcement
  (`docs/assurance/dependency-audit.md` and
  `docs/assurance/workflows-audit.md`).
- Filed open findings: none. The sequential-coverage finding is closed by #187,
  and the store-bricking finding is fully discharged by #169 and #209
  (`docs/findings/aggregation-ci-coverage-under-sequential-stop.md` and
  `docs/findings/store-bricking-deadlock.md`).

## Proposed drift-check candidates

**Row status.** AC-1 CONFIGURED: it is the `AC-1` row in `scripts/drift_check.py`,
red-demonstrated in `tests/test_drift_check.py`, landed by #248. AC-2 NOT
CONFIGURED. AC-3 NOT CONFIGURED. AC-4 NOT CONFIGURED. The #160 close-out ratified
all four; the three unconfigured candidates carry no mechanical guard, so drift in
them stays unobserved until each lands as a row with its own red demonstration
(#248).

| Candidate | Invariant | Sites to compare | Why it may be worth pinning |
| --- | --- | --- | --- |
| AC-1 | The production confidence sequence method remains `predictable_plugin_betting_cs_v1`, and the public report leads with `sequential_confidence_sequence_95` rather than the legacy posterior interval. | `aggregation/confidence_sequence.py`, report schema, `calibration-report.md` | Prevents a calibrated interval from being silently replaced or demoted. |
| AC-2 | A/A and calibration harnesses continue to use the production `N_MIN=8`, `N_INC=4`, `N_MAX=40` schedule and 0.60/0.95 decision constants. | `ablation/stopping.py`, `test_aggregation_aa.py`, `test_aggregation_calibration.py`, `test_aggregation_cs_calibration.py` | Prevents the assurance harness from exercising a different procedure. DC-1 and DC-2 cover production and selected prose, but not these harness sites. |
| AC-3 | Public vacuity-flag precision always carries its instrument generation and kind class split; detector recall is UNMEASURED unless quoted with both registered intervals and their sample and skill denominators. | README, calibration registry, public-copy guard | Prevents a flag-precision result from becoming a detector-wide validity claim. |
| AC-4 | Every workflow keeps exact action SHA pins, a workflow-level read-only permission baseline, and no `pull_request_target`. | `.github/workflows/*.yml` and `.yaml` | Extends the one-date workflow audit into a standing configuration contract. |

## Bottom line

The assurance pass found a two-arm A/A false-positive rate of 5.2%, production confidence-sequence coverage of at least 495 / 500 in every registered grid cell, 4,000 / 4,000 differential comparisons within tolerance, 60.1 fuzz minutes with 0 crashes, module mutation scores from 70.1% to 81.7%, seven of twenty measured modules needing attention under the paired static-analysis rule, and no published dependency advisories in the dated audit; these are run-bounded results, not a general correctness claim, and the close-out retains extraction repeat-instability, no assurance-set vacuity recall result, single-maintainer review limits, scoped mutation and fuzz boundaries, the legacy posterior coverage miss, and a missing #173 re-derivation receipt.
