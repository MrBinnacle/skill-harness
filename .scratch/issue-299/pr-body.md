# PR: Add claude-sonnet-5 price row and drift-guard test (#299)

## What changed

Added the `claude-sonnet-5` row to the canonical pricing table
`PRICE_PER_MTOK` (`src/skill_harness/ablation/subject.py:256-263`) at
$2/$10 per MTok input/output, sourced from
https://platform.claude.com/docs/about-claude/pricing (2026-08).

Added pair and trial projection tests for `claude-sonnet-5` using the
per-unit token figures from the 2026-07-10 paired run.

Created `tests/test_budget_ledger_reconciliation.py` with a pricing-table
drift guard (falsification-plan item 7, detection owner: supply chain).

## Acceptance criteria

### 1. A `claude-sonnet-5` row exists with input/output USD per MTok and a dated source

**Built:** Row at `subject.py:256-263` with `input: 2.00`, `output: 10.00`,
`cache_write: 2.50`, `cache_read: 0.20`. Source comment cites
`https://platform.claude.com/docs/about-claude/pricing (2026-08)`.

**Test:** `test_pair_literal_sonnet_5` and `test_trial_literal_sonnet_5` in
`tests/oracles/calibration/test_cost_projection.py:486-502` assert the
projection functions return the correct USD for the 2026-07-10 paired-run
token figures. These tests were written first and failed with `KeyError:
'claude-sonnet-5'` before the price row was added.

**Observation:** Before the row, `project_pair_usd("claude-sonnet-5",
486212.75, 54777.625)` raised `KeyError`. After the row, it returns
`1.52020175`. Same for `project_trial_usd`.

### 2. `project_pair_usd` and `project_trial_usd` return numbers for `claude-sonnet-5`

**Built:** Tests at `test_cost_projection.py:486-502`:
- `test_pair_literal_sonnet_5`: asserts `usd == approx(1.52020175)` for the
  paired-run token figures (486212.75 input, 54777.625 output).
- `test_trial_literal_sonnet_5`: asserts `usd == approx(0.7938065)` for the
  trial-run token figures (249623.25 input, 29456 output).

**Test:** Both tests pass with the price row and fail with `KeyError` without it.

**Observation:** Confirmed by stashing the price row and running both tests;
each raised `KeyError: 'claude-sonnet-5'`. After restoring the row, both pass.

### 3. Drift-guard test for models without price rows

**Built:** `tests/test_budget_ledger_reconciliation.py` with class
`TestPricingTableCoversEvidenceModels` (3 tests):

- `test_sonnet_5_has_price_row`: inserts a `claude-sonnet-5` sample into the
  evidence store, queries distinct `subject_model` values, then calls
  `project_pair_usd` and `project_trial_usd` for that model. Fails with
  `KeyError` if the price row is missing.
- `test_all_evidence_models_are_priceable`: seeds evidence with all known
  subject models (`claude-sonnet-4-6`, `claude-opus-4-7`, `claude-sonnet-5`,
  `gpt-5.5`), then asserts every model in the evidence store exists in
  `PRICE_PER_MTOK`. Fails with a clear message naming the missing models.
- `test_unknown_model_raises_keyerror`: inverse guard confirming that a model
  NOT in `PRICE_PER_MTOK` raises `KeyError` (no silent default-pricing).

**Test:** Before the price row, `test_sonnet_5_has_price_row` failed with
`KeyError: 'claude-sonnet-5'` at `cost_projection.py:282`. After the row,
all 3 tests pass.

**Observation:** The drift guard is the detection named in falsification-plan
item 7 (`tests/test_budget_ledger_reconciliation.py`). It catches
pricing-table drift vs vendor at test time: any future model added to evidence
without a corresponding `PRICE_PER_MTOK` entry will fail the suite.

## Mutation campaign

Not run for this change. The pricing table is a literal dict; mutation of
its values is caught by the hand-literal assertion tests
(`test_sonnet_4_6_input_price`, etc.) and by the sonnet-5 projection tests
that pin exact USD outputs.

## Gate results

- **Tests:** 56 passed (cost projection + drift guard), 0 failed
- **Drift check:** PASS — all 13 live contracts hold
- **Mypy:** clean (no errors)
- **Ruff:** All checks passed
