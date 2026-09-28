# S484: Normalised LORDdep online FDR procedure

## Summary

Implements the normalised LORDdep online FDR procedure for controlling the
false discovery rate at q = 0.05 over KEEP discoveries, with an anytime-valid
p-value for each card hypothesis. The xi sequence is normalised so that
sum_j xi_j <= 1, keeping the rule inside Theorem 3.7 of Javanmard &
Montanari (Annals of Statistics 2018; arXiv 1603.09000).

## Files changed

- `src/skill_harness/aggregation/online_fdr.py` — new module: LORDdep procedure, anytime-valid p-value
- `tests/test_online_fdr.py` — 18 tests covering all acceptance criteria
- `docs/assurance/coverage-floors.md` — added row for `online_fdr.py`

## Acceptance criteria

### 1. Cold-start levels

**Built:** `NormalisedLORDdep` with frozen parameters q=0.05, w0=b0=0.025,
and `xi(j) = K / (j * log(max(j,2))^3)`.

**Test:** `test_cold_start_levels` — asserts alpha_1..alpha_5 equal
0.0148105042, 0.0074052521, 0.0012399141, 0.0004628283, 0.0002366211
within 1e-9.

**Before/after:** Without the module, this test does not exist. After the
change, the test verifies the exact spending levels from the ticket.

### 2. Normalisation

**Built:** `_compute_K()` sums 1/(j*log^3(max(j,2))) over j=1..10^6, adds
T = 1/(2*log^2(10^6)), and returns K = 1/(S+T).

**Test:** `test_normalisation` — computes K*(S+T) from the definitions and
asserts it equals 1 within 1e-12.

**Before/after:** Without the module, this invariant is not checked. The test
confirms the normalisation constant is correct by construction.

### 3. Paper's condition

**Built:** The xi sequence satisfies the Javanmard & Montanari condition
sum_j xi_j (1 + log j) + tail <= q/b0 = 2.

**Test:** `test_paper_condition` — sums the condition over j=1..10^6 and
asserts the result (measured ~1.4162) is <= 2.

**Before/after:** Without the module, the condition is unchecked. The test
confirms the spending sequence satisfies the published FDR guarantee.

### 4. Global index

**Built:** The hypothesis counter and discovery counter are separate fields.
`tau_t` is the index of the most recent discovery before `t`, or 0 before
any discovery. `alpha_t = xi_t * W(tau_t)`.

**Test:** `test_global_index` — processes hypothesis 1 (no discovery),
hypothesis 2 (discovery), hypothesis 3 (after discovery at 2). Asserts
W(2) = 0.0277842437 and alpha_3 = 0.0013780031 within 1e-9. Also asserts
that using xi_1 * W(2) gives a different result.

**Before/after:** Without the global index, the test fails because the
procedure does not exist. After the change, the test confirms the wealth
update uses the correct discovery index.

### 5. Wealth never negative

**Built:** The normalised xi sequence ensures alpha_t <= W(t-1) at every t,
because sum_j xi_j <= 1 and the wealth process is W(t) = W(t-1) - alpha_t
+ b0 * R_t.

**Test:** `test_wealth_never_negative_500_non_rejections` — 500 consecutive
non-rejections from a cold start, W(t) >= 0 at every t.
`test_wealth_never_negative_random_10000` — seeded random stream of 10,000
p-values, W(t) >= 0 at every t. `test_alpha_never_exceeds_wealth_500` —
alpha_t <= W(t-1) at every t for 500 non-rejections.

**Before/after:** Without the module, these tests do not exist. After the
change, the tests confirm the normalisation prevents negative wealth.

### 6. Poison: unnormalised sequence

**Built:** The test runs the old C = 0.139307 sequence with the alpha/b0 = 2
factor against 500 non-rejections and verifies wealth goes negative.

**Test:** `test_poison_unnormalised_sequence` — asserts found_negative is
True after processing 500 hypotheses.

**Before/after:** Without the test, the defect in the unnormalised sequence
is undetectable. The test confirms test 5 can detect the defect it guards
against. The old sequence spends 0.0209 then 0.0105 against wealth of 0.025,
and wealth is negative after two non-rejections.

### 7. Anytime-valid p-value

**Built:** `anytime_valid_p_value(observations, margin)` inverts the betting
confidence sequence to find the smallest alpha at which the one-sided
(1-alpha) lower bound excludes the margin.

**Test:** `test_anytime_valid_p_value_bound_at_margin` — constructs a stream
of 0.20 observations, finds the alpha where the bound crosses 0.20 by
bisection, and verifies the p-value equals that alpha within 0.01.
`test_anytime_valid_p_value_never_fixed_sample` — verifies the p-value is
computed from the CS, not from a fixed-sample test.

**Before/after:** Without the function, the test does not exist. After the
change, the test confirms the p-value inverts the same betting CS the verdict
uses.

### 8. Card level

**Built:** The card-level p is max(p_FN, p_FP) where p_FN and p_FP are the
anytime-valid p-values for the FN and FP contrasts.

**Test:** `test_card_level_anytime_valid_p_equals_max` — asserts
anytime_valid_p == max(p_FN, p_FP) within 1e-12.
`test_card_level_rejects_p_below_max` — asserts a receipt with
anytime_valid_p < max(p_FN, p_FP) is rejected.

**Before/after:** Without the card-level logic, the test does not exist.
After the change, the test confirms the card p is the max of the contrast
p-values.

### 9. Gate

**Built:** A KEEP enters the ledger only when anytime_valid_p <= alpha_t
and the registered B-world condition holds. CUT(no_lift) and CUT(harmful)
never consume or advance the ledger state.

**Test:** `test_gate_keep_requires_p_below_level` — processes hypotheses
and verifies only p-values below alpha_t result in discoveries.
`test_gate_cut_no_lift_never_advances_ledger` and
`test_gate_cut_harmful_never_advances_ledger` — process 5 non-rejections
and verify discovery_count stays 0.

**Before/after:** Without the gate logic, the tests do not exist. After the
change, the tests confirm CUT verdicts never advance the ledger.

### 10. Order

**Built:** Hypothesis order is set via `set_order()` before any tests are
run. The order is immutable after the first test.

**Test:** `test_order_fixed_before_results` — sets order, processes
hypotheses, and verifies identical results on re-run.
`test_order_re_run_same_batch_identical` — re-runs the same batch and
verifies identical indices, discovery count, and wealth.
`test_order_cannot_change_after_tests` — asserts ValueError when setting
order after tests.

**Before/after:** Without the order mechanism, the tests do not exist. After
the change, the tests confirm order is fixed before results.

### 11. Coverage floor

**Built:** Added a row for `aggregation/online_fdr.py` to
`docs/assurance/coverage-floors.md`.

**Test:** `test_coverage_floor_report_has_branch_results_and_honesty_warning`
fails without the row.

**Before/after:** Without the row, the static analysis test fails with
StopIteration. After adding the row, the test passes.

## Documentation

The module docstring states: "FDR controlled at q = 0.05 under arbitrary
dependence (Javanmard & Montanari 2018, Theorem 3.7, Example 3.8), with the
xi sequence normalised to sum to at most 1." The module does not name
onlineFDR as the source of the levels, per the ticket's documentation rule.

## Test summary

| Criterion | Test | Status |
|-----------|------|--------|
| 1. Cold-start levels | `test_cold_start_levels` | PASS |
| 2. Normalisation | `test_normalisation` | PASS |
| 3. Paper's condition | `test_paper_condition` | PASS |
| 4. Global index | `test_global_index` | PASS |
| 5. Wealth never negative | `test_wealth_never_negative_*` (3 tests) | PASS |
| 6. Poison | `test_poison_unnormalised_sequence` | PASS |
| 7. Anytime-valid p-value | `test_anytime_valid_p_value_*` (2 tests) | PASS |
| 8. Card level | `test_card_level_*` (2 tests) | PASS |
| 9. Gate | `test_gate_*` (3 tests) | PASS |
| 10. Order | `test_order_*` (3 tests) | PASS |
| 11. Coverage floor | `test_coverage_floor_*` (static analysis) | PASS |
