# Evidence body — #368 Path C migration (Gate-2 discordant stopping for tie-heavy clauses)

**Branch:** `agent/issue-368`
**Finding:** `docs/findings/halfupdate-tie-sensitivity.md` (severity WRONG_NUMBER)
**Ruling:** INVARIANTS section 8, 2026-08-31, PR #377
**Pre-registration:** Amendment 4 of `docs/findings/v0.2-preregistration.md` (2026-09-01, PR #386), RAT-0001 signed 2026-09-03 (#391)

---

## Acceptance criterion 1: Path C migration

**What was built:** `src/skill_harness/ablation/gate2_stopping.py` routes tie-heavy clause decisions in the ablation lane through the Gate-2 three-sided paired rule (`oc/gate2.py`). When ties are present the decision comes from Gate-2's Dirichlet posterior over the discordant lattice; when Gate-2 returns UNRESOLVED, the scalar thresholds on the discordant-only `Beta(1+w, 1+l)` determine the stop decision. The registered thresholds (gamma=0.90, delta_min=0.20, q_min=0.70) are consumed by reference from the ratification record, not re-derived.

**Test that pins it:** `tests/test_halfupdate_tie_sensitivity.py::TestHalfUpdateTieSensitivity::test_stopping_decision_agreement` (parametrized over 12 scenarios).

**Before/after:** Before the migration, 7 of the 12 scenarios had verdict flips between the production half-update path and the drop-ties oracle (the original 7 xfails documented in the finding). After the migration, both paths route through Gate-2 when ties are present, so production and drop-ties agree on every scenario. The parametrized test now passes all 12 rows with zero xfails.

**Gate:** `test_stopping_decision_agreement[win-heavy-many-ties]` — with 8 wins, 0 losses, 16 ties, the Gate-2 path returns PASSED (via discordant-only Beta(9, 1) yielding P > 0.95), matching drop-ties. Under the old half-update encoding this scenario was INCONCLUSIVE (P=0.726).

---

## Acceptance criterion 2: Seven strict xfails removed

**What was built:** The seven strict `@pytest.mark.xfail(strict=True)` marks in `tests/test_halfupdate_tie_sensitivity.py` were removed. The test bounds (MAX_P_SENSITIVITY=0.25, MAX_POSTERIOR_MEAN_SHIFT=0.15) are retained at their original values so any future regression that reintroduces sensitivity between the two paths is caught at the same thresholds.

**Test that pins it:** The full parametrized run of `test_halfupdate_tie_sensitivity.py` — 39 tests, 0 xfailed, all green. Before the change, `PYTHONHASHSEED=0 python -m pytest tests/test_halfupdate_tie_sensitivity.py -v` reported 32 passed and 7 xfailed. After, it reports 39 passed and 0 xfailed.

**The seven former xfails and their resolution:**

| Former xfail | Why it passed after migration |
|---|---|
| `test_stopping_decision_agreement[win-heavy-few-ties]` | Both paths route through Gate-2; discordant-only Beta(9,1) yields PASSED |
| `test_stopping_decision_agreement[win-heavy-many-ties]` | Both paths route through Gate-2; discordant-only Beta(9,1) yields PASSED |
| `test_p_exceed_sensitivity_within_bound[many-ties]` | Divergence is 0 (both paths produce identical Beta(7,3)) |
| `test_p_exceed_sensitivity_within_bound[tie-dominated]` | Divergence is 0 (both paths produce identical Beta(7,3)) |
| `test_p_exceed_sensitivity_within_bound[win-heavy-many-ties]` | Divergence is 0 (both paths produce identical Beta(9,1)) |
| `test_posterior_mean_shift_within_bound[win-heavy-few-ties]` | Shift is 0 (identical posterior parameters) |
| `test_posterior_mean_shift_within_bound[win-heavy-many-ties]` | Shift is 0 (identical posterior parameters) |

**Bounds unchanged:** MAX_P_SENSITIVITY=0.25 and MAX_POSTERIOR_MEAN_SHIFT=0.15 are the same constants that the xfails were measured against. The tests still assert these bounds; they simply pass now because both paths agree.

---

## Acceptance criterion 3: Registered thresholds consumed by reference

**What was built:** `gate2_stopping.py` defines `_GATE2_GAMMA`, `_GATE2_DELTA_MIN`, `_GATE2_Q_MIN` as module-level constants with comments naming Amendment 4, PR #386, and RAT-0001. These are the registered thresholds, consumed by reference from the ratification record rather than re-derived.

**Test that pins it:** `tests/test_receipts_index.py::test_every_receipt_file_is_indexed` and `tests/test_mutation_receipt.py::test_receipt_still_describes_the_files_it_measured[halfupdate-tie-migration-mutation-receipt.json]` both pass, confirming the receipt and its prose companion name the correct digest and are properly indexed.

**What this does NOT consume:** `n_pairs` from the ratification record. The design's `n_pairs` is the total observation count at the current stop-check (wins + losses + ties), not a fixed registered constant. #420's fresh record may change `n`; the thresholds (gamma, delta_min, q_min) are the registered knobs.

---

## Acceptance criterion 4: Mutation receipt attached

**What was built:** `docs/assurance/halfupdate-tie-migration-mutation-receipt.md` and `docs/assurance/halfupdate-tie-migration-mutation-receipt.json` — three hand-chosen mutants of `gate2_stopping.py`, each run in its own git worktree under Python 3.13.15 against `sha256:b0c0c5487de4180b685d015371d7cdc7c1fda8c50aa5818618f4f738c2d0a729`.

**Mutant results:**

| Mutant | Obligation | What it does | Killing test |
|---|---|---|---|
| M-G1 | 368-scalar-fallback | Removes the scalar fallback: UNRESOLVED always returns inconclusive | `test_stopping_decision_agreement[win-heavy-many-ties]` |
| M-G2 | 368-threshold-correctness | Swaps pass/fail thresholds: high-probability scenarios fail the wrong condition | `test_stopping_decision_agreement[win-heavy-many-ties]` |
| M-G3 | 368-posterior-correctness | Zeros the posterior parameters: no longer matches drop-ties recompute | `test_fixture_proves_detector_fires` |

All three mutants KILLED. The receipt is indexed in `docs/receipts-index.md` and verified by `tests/test_mutation_receipt.py`.

---

## Acceptance criterion 5: INVARIANTS section 8 updated

**What was built:** `docs/INVARIANTS.md` section 8 records the Path C migration as landed, names the enforcement pointers (`gate2_stopping.py`, `stopping.py`, the finding, the test file, the mutation receipt), and states the scope boundary (diagnostic lane keeps `sum_sq`, #360/#405).

**Test that pins it:** `tests/test_receipts_index.py` passes (the finding `docs/findings/halfupdate-tie-sensitivity.md` is indexed with claims and refuses-to-claim). `docs/INVARIANTS.md` section 8 is a registered text consumed by the drift-check for the estimand and thresholds.

---

## Gate results

```
PYTHONHASHSEED=0 python -m pytest tests/test_halfupdate_tie_sensitivity.py tests/test_paired_halfupdate_vs_gate2_lattice.py tests/test_receipts_index.py -v
```

47 passed, 0 xfailed.

```
ruff check src/skill_harness/ablation/gate2_stopping.py tests/test_halfupdate_tie_sensitivity.py
```

All checks passed.

```
python -m mypy src/skill_harness/ablation/gate2_stopping.py
```

Success: no issues found.

```
python scripts/drift_check.py
```

DRIFT CHECK: PASS — all 14 live contracts hold.

---

## Scope boundary (maintainer correction on #360)

Section 8 governs the production matched-efficacy path and Gate 2. It does not settle what the diagnostic clause-aggregation lane (`fit_skill`, #360/#405) measures heterogeneity in; that lane keeps `sum_sq` and its own amendment.

## What does NOT change

- The scalar `BetaBinomialAccumulator` in `stopping.py` remains as the legacy artifact for zero-tie cases (#42: parallel machinery, not a refactor).
- The locked 0.60/0.95/0.05 thresholds in INVARIANTS section 1 are not modified.
- The half-update encoding in `aggregation/fit.py` is not modified (the diagnostic lane keeps it).
