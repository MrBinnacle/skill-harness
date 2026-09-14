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
red-demonstrated in `tests/test_drift_check.py`, landed by #248. AC-2 CONFIGURED:
it is the `AC-2` row in `scripts/drift_check.py`, red-demonstrated in
`tests/test_drift_check.py`, landed by #545. AC-3 CONFIGURED: it is the `AC-3` row,
which delegates to the vacuity scanner in `tests/test_structural_bans.py` rather
than restating its predicates, red-demonstrated in `tests/test_drift_check.py`,
landed by #543. AC-4 CONFIGURED: it is the `AC-4` row, which delegates the
action-pin leg to the release gate's `G5` and the permissions-baseline and trigger
legs to the two predicates in `tests/test_assurance_supply_chain_172.py` rather than
restating any of them, red-demonstrated per leg in `tests/test_drift_check.py`,
landed by #544.

**What the status word means here, corrected.** An earlier revision of this
paragraph said the then-unconfigured candidates "carry no mechanical guard, so drift
in them stays unobserved". That was false for both AC-3 and AC-4 and is withdrawn.
AC-3's invariant was enforced before its row existed, by the public-copy scanner
`.pre-commit-config.yaml` runs as `python tests/test_structural_bans.py` and that
`test_no_banned_copy_on_public_surfaces` runs inside the required `Test` job. AC-4's
three legs were likewise enforced before its row existed, by
`test_workflow_audit_covers_every_workflow_and_records_required_checks` in
`tests/test_assurance_supply_chain_172.py`, also inside that required job, and the
SHA-pin leg additionally by the release gate's `G5`. The status word means one thing
and only one thing: whether the drift-check contract table prints a row for the
candidate. That table states that its coverage is exactly the list it prints, so a
candidate missing from the list was real enforcement that the one listing this
repository publishes did not name. Read the status word as a claim about that
listing. Never as a claim that the invariant is fully guarded.

The `AC-2` row guards the harness sites only, which is what the candidate row
below asks for in its own words: "DC-1 and DC-2 cover production and selected
prose, but not these harness sites." The production constants stay with DC-1 and
DC-2.

**State what CONFIGURED does not mean here.** The row does not redden when a
production value moves and a harness does not follow. That was measured, not
assumed: moving `N_MAX` from 40 to 60 in `src/skill_harness/ablation/stopping.py`
reddens `DC-2` alone, because the harness prose still says 40, the contract table
still expects 40, and the two agree without consulting production. No row of this
shape can close that leg, since every check compares a file against a literal in
the table rather than against another file. #559 carries the check kind that
would. Read `AC-2 CONFIGURED` as covering what the row pins and nothing more.

What the row does cover is guarded by nothing else. The two-arm gate constants
`delta` and `prob_threshold` are recorded in `aggregation/two_arm.py` as the
caller's pre-registered constants, and that module holds no default for either,
so the two harnesses are their only site in the tree.

`test_aggregation_cs_calibration.py` is named in the candidate row and carries no
pinned site. It imports every schedule and threshold constant it uses from
`test_aggregation_calibration.py`, so none of them can drift there independently.
It does state literals of its own, where it asserts the contents of `CS_P_GRID`;
two of those grid points are 0.60 and 0.95. They are rates the calibration sweeps
rather than decision constants, so they are left unpinned for the same reason
`NOMINAL_COVERAGE` is.

**State what the `AC-4` row does not mean.** The `AC-4` row lists the workflow
configuration contract. It did not start the enforcement of that contract, and four
listed rows are four listed rows rather than a settled assurance question. All three
legs were asserted before the row existed, inside the required `Test` job, by the
one-shot test named above. What the row adds is bounded and was measured rather than
assumed. The contract table now names the workflow configuration among the contracts
it checks. `gate_workflows_sha_pinned` now runs behind a required check: branch
protection on `main` requires seven contexts as of 2026-09-14, and `Release gate
(surface lockstep)` is not one of them, so a `G5` failure could stand on a pull
request with the merge button still available. And each leg gains a red
demonstration against a synthetic tree, which the one-shot test cannot have, because
it reads a hardcoded repository root and can therefore only report that the real
tree is clean.

Two instrument gaps stay open behind these four rows, and neither is closed here.
#559 carries the check kind `AC-2` needs, one that reads a value from a producing
file and compares a consuming file against it. #563 records that the drift check,
the structural bans and the release gate all run as jobs branch protection does not
require, so each reaches a merge only where some other required job asserts it.

| Candidate | Invariant | Sites to compare | Why it may be worth pinning |
| --- | --- | --- | --- |
| AC-1 | The production confidence sequence method remains `predictable_plugin_betting_cs_v1`, and the public report leads with `sequential_confidence_sequence_95` rather than the legacy posterior interval. | `aggregation/confidence_sequence.py`, report schema, `calibration-report.md` | Prevents a calibrated interval from being silently replaced or demoted. |
| AC-2 | A/A and calibration harnesses continue to use the production `N_MIN=8`, `N_INC=4`, `N_MAX=40` schedule and 0.60/0.95 decision constants. | `ablation/stopping.py`, `test_aggregation_aa.py`, `test_aggregation_calibration.py`, `test_aggregation_cs_calibration.py` | Prevents the assurance harness from exercising a different procedure. DC-1 and DC-2 cover production and selected prose, but not these harness sites. |
| AC-3 | Public vacuity-flag precision always carries its instrument generation and kind class split; detector recall is UNMEASURED unless quoted with both registered intervals and their sample and skill denominators. | README, calibration registry, public-copy guard | Prevents a flag-precision result from becoming a detector-wide validity claim. |
| AC-4 | Every workflow keeps exact action SHA pins, a workflow-level read-only permission baseline, and no `pull_request_target`. | `.github/workflows/*.yml` and `.yaml` | Extends the one-date workflow audit into a standing configuration contract. |

## Bottom line

The assurance pass found a two-arm A/A false-positive rate of 5.2%, production confidence-sequence coverage of at least 495 / 500 in every registered grid cell, 4,000 / 4,000 differential comparisons within tolerance, 60.1 fuzz minutes with 0 crashes, module mutation scores from 70.1% to 81.7%, seven of twenty measured modules needing attention under the paired static-analysis rule, and no published dependency advisories in the dated audit; these are run-bounded results, not a general correctness claim, and the close-out retains extraction repeat-instability, no assurance-set vacuity recall result, single-maintainer review limits, scoped mutation and fuzz boundaries, the legacy posterior coverage miss, and a missing #173 re-derivation receipt.
