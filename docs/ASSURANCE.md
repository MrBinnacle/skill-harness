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
