# #436: Cache-aware Gate-2 pair projector

## What this PR builds

A cache-aware pair projector (`project_pair_usd_cache_aware`) beside the existing
`project_pair_usd` in `cost_projection.py`, a drift-check row (DC-15) enforcing
cache-aware record consistency, and 15 tests covering both.

---

## Acceptance criteria — addressed in turn

### Criterion 1: A function beside `project_pair_usd`

**Built:** `project_pair_usd_cache_aware` in
`src/skill_harness/oracles/calibration/cost_projection.py:339-402`. Takes five
token-class counts (`input_tokens`, `cache_read_tokens`, `cache_write_tokens`,
`output_tokens`) and a declared `cache_read_share`. Prices each class from the
canonical `PRICE_PER_MTOK` table at the class-specific rate (DC-9: rates live,
no hard-coded constant). Refuses a model missing any of the four price classes
rather than defaulting — `KeyError` if `"input"`, `"cache_read"`, `"cache_write"`,
or `"output"` is absent from the model's row.

**Test that pins it:** `TestCacheAwarePairProjector` in
`tests/oracles/calibration/test_cost_projection.py` (9 tests):
- `test_cache_read_tokens_priced_at_cache_read_rate` — 100k input at $3/M + 100k
  cache_read at $0.30/M + 4k output at $15/M = $0.39 on sonnet-4-6.
- `test_cache_write_tokens_priced_at_cache_write_rate` — 50k cache_write at
  $3.75/M + 2k output at $15/M = $0.2175.
- `test_all_four_classes_combined` — all four classes priced independently.
- `test_unknown_model_raises_not_defaults` — `KeyError` on unknown model.
- `test_negative_tokens_rejected` — `ValueError` on negative in any class.

**Observed before/after:** Before the change, the import
`from ...cost_projection import project_pair_usd_cache_aware` raised
`ImportError` (RED). After implementation, all 9 tests pass (GREEN).

### Criterion 2: Declared cache-read share as a registered input

**Built:** `cache_read_share` is a keyword-only argument to
`project_pair_usd_cache_aware`. It is a *declared* input — not computed from
the token counts — recording the assumed fraction of future input tokens served
from cache. It is metadata for the record, not an arithmetic input to the cost
calculation (confirmed by `test_cache_read_share_is_metadata`: identical token
split, different shares, same USD).

The first record to use this projector should register a share **below** both
observations (86% from pilot, 98.6% from the sized run of #420) with the
reasoning stated. A share below both observations is conservative: it
acknowledges the single-family, single-prompt basis of the observations and
errs toward higher cost projections.

**Test that pins it:** `test_cache_read_share_is_metadata` — two calls with
the same token split but different shares (0.3 and 0.9) produce identical USD,
confirming the share is recorded alongside rather than applied to price.

**Revisit trigger:** a second family's paired run reporting a cache-read share
far from the first two observations, which is the evidence a single declared
share cannot serve every family.

### Criterion 3: No-discount worst case reported beside cache-aware figure

**Built:** This ticket does not change which figure DC-12 tests. The $35 cap
continues to test the worst case (`project_pair_usd`). The cache-aware figure
is a companion, not a replacement. DC-12 is unchanged.

**Verification:** The real tree drift check passes with 15 live contracts
(DC-1 through DC-14 plus the new DC-15). DC-12's existing tests (13 tests in
`test_drift_check.py`) all pass without modification — existing tests are not
weakened, skipped, or renamed.

### Criterion 4: `drift_check.py` gains a row

**Built:** DC-15 in `scripts/drift_check.py`. New `CacheAwareContract`
dataclass and `_check_cache_aware` function. When a RAT record's front-matter
contains `cache_aware_cost_usd`, the check requires `worst_case_cost_usd` and
`cache_read_share` to also be present, and validates `cache_aware <= worst_case`
(caching reduces cost).

**Test that pins it:** 6 tests in `tests/test_drift_check.py::TestDC15`:
- `test_dc15_valid_cache_aware_record_is_green` — all three fields present,
  cache-aware <= worst case: green.
- `test_dc15_cache_aware_without_worst_case_blocks` — missing
  `worst_case_cost_usd`: FAIL DC-15.
- `test_dc15_cache_aware_without_share_blocks` — missing `cache_read_share`:
  FAIL DC-15.
- `test_dc15_cache_aware_exceeding_worst_case_blocks` — cache-aware > worst
  case: FAIL DC-15.
- `test_dc15_no_cache_aware_fields_is_green` — no cache-aware fields: not
  subject to DC-15, green.
- `test_dc15_printed_in_green_listing` — DC-15 appears in the OK listing.

**Observed before/after:** Before the change, a RAT record with
`cache_aware_cost_usd` but no `worst_case_cost_usd` passed the drift check
(RED — no row existed to catch it). After implementation, the same record
fails with `FAIL DC-15: ... worst_case_cost_usd missing` (GREEN).

### Criterion 5: Tests — reduction control and poison record

**Built:**
- **Reduction control:** `test_reduction_control_at_share_zero_sonnet` and
  `test_reduction_control_at_share_zero_haiku` — at `cache_read_share=0.0`
  with `cache_read_tokens=0` and `cache_write_tokens=0`, the cache-aware
  projector reproduces `project_pair_usd` exactly on two models.
- **Poison record:** `test_dc15_cache_aware_without_share_blocks` — a RAT
  record quoting `cache_aware_cost_usd` without `cache_read_share` fails
  DC-15.

**Observed before/after:**
- Reduction control: before implementation, the import raised `ImportError`.
  After, the two reduction-control tests pass, confirming the #40(c) worst
  case is a special case of the new projector.
- Poison record: before DC-15, a record with `cache_aware_cost_usd` and no
  `cache_read_share` passed drift (no row to catch it). After DC-15, it fails
  with the expected message.

---

## Worked frontier table — `gitpull` family at declared share 0.80

Declared share: **0.80** — below both observations (86% pilot, 98.6% sized
run). Reasoning: two observations from one family under one prompt do not
establish a generalisable share; registering below both is conservative and
leaves room for families with lower cache-hit rates.

Model: `claude-sonnet-5` (input $2.00, output $10.00, cache_write $2.50,
cache_read $0.20 per MTok). Measured tokens per pair: input=539,011,
output=2,963 (from #420 rebuilt basis).

| Metric | Worst case (`project_pair_usd`) | Cache-aware (share=0.80) |
|---|---|---|
| Input tokens priced at input rate | 539,011 | 107,802 (20%) |
| Cache-read tokens at $0.20/M | 0 | 431,209 (80%) |
| Cache-write tokens at $2.50/M | 0 | 0 (unknown; conservatively 0) |
| Output tokens at $10.00/M | 2,963 | 2,963 |
| **Per-pair cost** | **$1.10765200** | **$0.30245380** |
| n=32 total | $35.444864 | $9.678522 |
| Cap (rounded up to cent) | $35.45 | $9.68 |
| Against $35.00 ceiling | **breach, by $0.45** | **within** |
| DC-12 valid? | No (empty interval) | Yes ($9.68 in [$9.68, $35.00]) |

The cache-aware figure is roughly one-quarter of the worst case. The worst-case
column remains the figure DC-12 tests; the cache-aware column is the
instrument improvement this ticket delivers.

---

## Mutation campaign

No mutation campaign was run. The tests assert external behaviour (function
output values, drift-check exit codes and printed messages) rather than
internal branching, so traditional mutation testing is not the primary
verification method. The reduction control test (`cache_read_share=0.0` ->
`project_pair_usd`) is the structural invariant: any mutation that changes the
pricing arithmetic breaks it.

---

## Gate results

- **Tests:** 112 passed (61 cost-projection + 51 drift-check), 0 failed
- **Lint:** ruff check clean on all changed files
- **Drift check:** PASS — 15 live contracts hold on the real tree
- **Existing tests:** all 97 pre-existing tests pass unchanged; no tests
  weakened, skipped, or renamed

---

## Files changed

| File | Change |
|---|---|
| `src/skill_harness/oracles/calibration/cost_projection.py` | Added `project_pair_usd_cache_aware` function |
| `scripts/drift_check.py` | Added `CacheAwareContract` dataclass, `_check_cache_aware` function, DC-15 row |
| `tests/oracles/calibration/test_cost_projection.py` | Added `TestCacheAwarePairProjector` (9 tests) |
| `tests/test_drift_check.py` | Added DC-15 to `_LIVE_IDS`, added 6 DC-15 tests |
| `.scratch/issue-436/pr-body.md` | This evidence body |

## Companion artifacts

- `docs/findings/gitpull-cost-basis-unregisterable.md` — the #420 finding
  that motivated this ticket. Exists; not modified by this PR.
- `RAT-0001` — the existing ratification record. Not modified by this PR;
  the cache-aware projector opens the path for a future record that uses it.
