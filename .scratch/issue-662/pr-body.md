# #662: Re-register Stage 1A with --epochs-per-arm, Null-A arm, sequential reads, and dry-run price line

## What changed

Four changes to `scripts/screens/419/v5_cue_stage1a.py` and its tests, per the re-registration
in #641 S478 comment and #651 section 4.

### 1. `--epochs-per-arm N` replaces the constant (commit `3328f70`)

- Added `--epochs-per-arm` CLI argument, default 16 (unchanged behaviour when absent).
- `HARD_CAP_USD` formula: `(3*N - n_reused) * PER_SAMPLE_CAP`, where `n_reused` is the valid
  Null-A count in `--null-readout`.
- `stage1a_tasks` accepts an `epochs` parameter and passes it to `build_cells`.
- `render_table` accepts a `n` parameter instead of reading the module constant.
- Added `_hard_cap(n, n_reused)` helper.
- **Test:** `test_epochs_per_arm_flag_replaces_constant` — table at N=10 has 121 cells;
  `test_default_epochs_per_arm_reproduces_289_cell_table` — default N=16 is byte-identical;
  `test_hard_cap_formula` — cap at N=97 is $85.20; `test_render_table_uses_n_not_constant`.

### 2. Null-A arm (commit `86e7bab`)

- `build_cells` already builds the `null` cell for world A. `stage1a_tasks` now returns all
  three cells: Full, Placebo, Null.
- `main()` runs Null-A for `N - n_reused` new epochs (via a separate `inspect_ai.eval` call),
  then `read_stage1a` combines the reused epochs from `--null-readout` with the new ones in
  launch order (reused first, then new).
- `read_stage1a` computes `ub_n` from the combined stream instead of from the readout alone.
- **Test:** `test_null_a_reused_then_new_order_changes_bound` — verifies the betting bound
  depends on observation order (predictable plug-in lambdas), so reused-first gives a different
  UB than all-1s-first for the same multiset.

### 3. Sequential reads (commit `4ea25ef`)

- Added `sequential_evaluate(full_outcomes, placebo_outcomes, null_outcomes_combined, *, n,
  pass_alpha)` — evaluates the stop rule after every completed epoch index i. The bounds are
  `one_sided_betting_bound`, which is anytime-valid (Waudby-Smith & Ramdas, 2024), so a look
  after every epoch spends no extra level.
- Returns `(outcome, fired_at)` where `fired_at` is the epoch index at which the rule first
  fires, or `(UNRESOLVED_CONTINUE, None)` if no rule fires by epoch n.
- Stop rules unchanged: `CUT_NO_LIFT` when UB(F-P) < 0.20 at alpha 0.05; `A_PASSES_EARLY`
  when LB(F-P) >= 0.20 and LB(F-N) >= 0.20 at --pass-alpha; otherwise continue.
- **Test:** `test_sequential_stops_at_first_firing_look` — stops at first firing;
  `test_sequential_never_fires_ends_at_n` — tied stream ends unresolved;
  `test_sequential_stops_never_later_than_first_firing` — Full=0, Placebo=1 fires CUT_NO_LIFT
  immediately.

### 4. `--dry-run` price line (commit `4fbe87a`)

- `dry_run()` now prints the smallest look at which each outcome can fire, at both pass-alpha
  0.05 and 0.0209.
- Added `smallest_look(cells, *, n)` — for each outcome, the smallest epoch index at which it
  first appears in the table.
- Price line: new epochs `3N - n_reused`, cap at `PER_SAMPLE_CAP`.
- Moved `_model_cost` import after the dry-run early return (no `inspect_ai` needed for dry run).
- **Test:** `test_smallest_look_finds_first_firing_epoch` — CUT_NO_LIFT and UNRESOLVED_CONTINUE
  fire at specific looks; `test_dry_run_price_line_at_n97` — N=97 gives 284 new epochs and
  $85.20 cap; `test_dry_run_at_n97_prints_new_epochs_and_cap` (marked slow) — full dry-run
  output verification.

## Tests added

| Test | Criterion | What it pins |
|------|-----------|--------------|
| `test_epochs_per_arm_flag_replaces_constant` | 1 | Table size changes with N |
| `test_default_epochs_per_arm_reproduces_289_cell_table` | 1 | Default N=16 is byte-identical |
| `test_hard_cap_formula` | 1 | Cap = (3*N - n_reused) * PER_SAMPLE_CAP |
| `test_render_table_uses_n_not_constant` | 1 | render_table accepts n parameter |
| `test_null_a_reused_then_new_order_changes_bound` | 2 | Order of Null-A observations matters |
| `test_sequential_stops_at_first_firing_look` | 3 | Stops at first firing epoch |
| `test_sequential_never_fires_ends_at_n` | 3 | Tied stream ends unresolved |
| `test_sequential_stops_never_later_than_first_firing` | 3 | CUT_NO_LIFT fires immediately |
| `test_smallest_look_finds_first_firing_epoch` | 4 | smallest_look returns correct values |
| `test_dry_run_price_line_at_n97` | 4 | N=97: 284 new epochs, $85.20 |
| `test_dry_run_at_n97_prints_new_epochs_and_cap` | 4 | Full dry-run output (slow) |

## What did NOT change

- `simulate_a_design.py`, the aggregation engine, SERS.
- Card texts and the placebo.
- The stop rule logic (`stop_rule()` function).
- The `operating_table` function signature (already accepted `n`).

## Evidence

No mutation receipt is required by this ticket's acceptance criteria. The ticket names no
mutation receipt obligation prefix.

## Gate

- `ruff check src tests scripts` — clean.
- `ruff format --check src tests scripts` — clean.
- `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py` — clean (fixed two mypy issues: removed unused `type: ignore` comment, replaced direct module attribute assignment with `monkeypatch.setattr`).
- `pytest tests/test_v5_cue_stage1a.py -m "not slow"` — 32 passed, 1 skipped (fixture absent).
