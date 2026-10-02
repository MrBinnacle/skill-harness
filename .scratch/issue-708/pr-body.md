# #708: diagonal target check, broader calibration read, constant pin, replicate-count model statement

This PR fixes three defects in `scripts/screens/419/simulate_stage1a_regime_685.py` and its
tests, plus one smaller summary defect. The aggregation rule is the #696 ruling
(issue comment 5944534509) and is non-negotiable: a design meets the target at effect d
when both halves hold in every cell where both true contrasts equal d. On this grid that is
the diagonal p_P = p_N (0.30, 0.35, 0.40). Off-diagonal cells are sensitivity.

Nothing outside this worktree was touched. No model calls, no network calls, no spend.
`v5_cue_stage1a.py`, `BOUNDARY`, `PASS_ALPHA`, `FUTILITY_ALPHA`, `ALPHA`,
`LEDGER_PASS_ALPHA`, `EFFECTS`, `BASELINES`, and `POWER_TARGETS` are unedited.

## Criterion 1 — `target_check_rows` and the stage-2 trigger use the diagonal minimum

**Built.** `_design_family_meets_target` now aggregates over `diagonal_cells()`
(p_P = p_N ∈ {0.30, 0.35, 0.40}) only. The minimum of P(PASS) at d = 0.30 and the minimum
of P(CUT) at d = 0.10 over those three cells must each be at or above the target.
`target_check_rows` and therefore `stage2_trigger_fires` inherit that verdict. The summary's
"Target check" prose names the diagonal in words and no longer says "all nine".

**Pinned by.** `tests/test_simulate_stage1a_regime_685.py::test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum`
and `::test_summary_target_check_text_says_diagonal_not_all_nine`.

**Before/after.** On `main`, `_design_family_meets_target` took the minimum over all nine
(p_P, p_N) cells. The unequal fixture's diagonal minimum P(PASS) is 0.85; the nine-cell
minimum is 0.50. Before the change the test reported 0.5 (nine-cell min) and failed with
`assert 0.5 == 0.85`. After the change it reports 0.85 and passes. The summary-text test
failed on `assert "diagonal" in summary` because the old prose said "all nine"; after the
change the prose names the diagonal and "all nine" is gone from the target-check section.

## Criterion 1b — the six off-diagonal cells appear as sensitivity beside the target check

**Built.** `sensitivity_rows(results, target=...)` reports, per design family per declared
budget, the minimum P(PASS) at d = 0.30 and the minimum P(CUT) at d = 0.10 over the six
off-diagonal cells. `summary_md` renders them under `## Sensitivity (off-diagonal cells)`
with prose that states they are never the target.

**Pinned by.** `::test_summary_reports_off_diagonal_cells_as_sensitivity`.

**Before/after.** Before the change the summary had no sensitivity section
(`assert "sensitivity" in summary.lower()` failed). After the change the section is present,
carries the off-diagonal minima, and is labelled sensitivity.

## Criterion 2 — unequal nine-cell fixture; three aggregation mutants fail the diagonal test

**Built.** `_results_with_per_cell_rates` builds a design family whose nine (p_P, p_N) cells
carry unequal P(PASS) and P(CUT) at d = 0.30 and d = 0.10. The fixture is chosen so four
readings disagree:

| reading | P(PASS) min at d=0.30 | P(CUT) min at d=0.10 | meets 0.80? |
| --- | --- | --- | --- |
| diagonal minimum | 0.85 | 0.84 | yes |
| nine-cell minimum | 0.50 | 0.50 | no |
| diagonal maximum | 0.92 | 0.88 | yes |
| single cell (0.35, 0.35) | 0.88 | 0.86 | yes |

The test asserts the diagonal pair (0.85, 0.84) and `reached is True`.

**Pinned by.** `::test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum`.

**Mutation campaign (named in the ticket).** Each mutant was applied to a private copy of
`simulate_stage1a_regime_685.py` and the test run against it:

| mutant | applied change | killing assertion | observed |
| --- | --- | --- | --- |
| min → max | `min(pass_vals)`/`min(cut_vals)` → `max` in `_design_family_meets_target` | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum` | reports (0.92, 0.88); test red |
| diagonal → all nine cells | `diag = diagonal_cells()` → all (p_P, p_N) pairs | same test | reports (0.50, 0.50), `reached=False`; test red |
| diagonal → single cell (0.35, 0.35) | `diag = diagonal_cells()` → `((0.35, 0.35),)` | same test | reports (0.88, 0.86); test red |

The clean tree reports (0.85, 0.84) and the test is green. The same three mutants are
recorded in the mechanized receipt `docs/assurance/stage1a-regime-708-mutation-receipt.md`
(M-S1A-13, M-S1A-14, M-S1A-15), each KILLED by that named assertion in an isolated worktree.

## Criterion 3 — the calibration read covers every PASS and CUT error cell

**Built.** New predicates and checks in `simulate_stage1a_regime_685.py`:

- `true_fp_diff` / `true_fn_diff` — the cell's true contrasts.
- `is_pass_calibration_cell` — True where true F − P ≤ BOUNDARY **or** true F − N ≤ BOUNDARY.
- `is_cut_calibration_cell` — True where true F − P ≥ BOUNDARY.
- `pass_calibration_holds` — P(PASS) at the cap ≤ PASS_ALPHA + 3 MC SE.
- `cut_calibration_holds` — P(CUT) at the cap ≤ FUTILITY_ALPHA + 3 MC SE.
- `calibration_holds` — both halves that apply to the cell, at the cap look.
- `main` selects cells with `is_calibration_cell` and returns 1 when any covered cell fails.

The F − N margin cell (p_P 0.30, p_N 0.40) at d = 0.30 has true F − N = 0.20 and is a
PASS-calibration cell. The exit path now includes it.

**Pinned by.**

- `::test_calibration_covers_the_fn_margin_cell_at_d030`
- `::test_calibration_set_includes_every_pass_and_cut_error_cell`
- `::test_cut_calibration_uses_the_futility_nominal_level`
- `::test_main_exits_non_zero_when_the_fn_margin_cell_fails_pass_calibration`

**Before/after.** Before the change the module had no `true_fn_diff`,
`is_pass_calibration_cell`, or `cut_calibration_holds`; the new tests failed with
`AttributeError`. `main` filtered on `role(r.cell.d) == "calibration"` (d = 0.20 only), so
`test_main_exits_non_zero_when_the_fn_margin_cell_fails_pass_calibration` observed exit
code 0 (the F − N margin cell was invisible) and failed `assert 0 == 1`. After the change
the cell is in the calibration set, a loosened pass alpha at 600 replicates drives
P(PASS) over the limit, and the exit code is 1. The set-membership test asserts the full
expected PASS and CUT cell sets against the stated rule; M-S1A-16 in the 708 receipt drops
the F − N half and is killed by all three calibration tests plus the exit test.

Existing calibration tests still pass: `test_calibration_holds_reads_the_cap_look_not_look_one`,
`test_main_exits_zero_when_calibration_holds`, `test_main_exits_non_zero_when_calibration_fails`,
and `test_calibration_holds_for_every_stage1_design_at_boundary`.

## Criterion 4 — one test pins the simulator constants to the launcher's

**Built.** `tests/test_v5_cue_stage1a.py::test_simulator_constants_pin_to_the_registered_launcher`
loads `simulate_a_design` and `v5_cue_stage1a` and asserts
`BOUNDARY == BOUNDARY`, `PASS_ALPHA == LEDGER_PASS_ALPHA`, `FUTILITY_ALPHA == ALPHA`.

**Pinned by.** That test. Recommended shape followed: the pin lives in the file that already
loads the launcher.

**Before/after.** The test is new; on `main` no test imported both modules, so one side
could move alone. The test passes on the current tree.

**Record: changing any one of the six values makes it fail.** A one-off script loaded both
modules, set each attribute in turn, and re-ran the three equalities:

| value moved | equality that breaks |
| --- | --- |
| `simulate_a_design.BOUNDARY` → 0.21 | `BOUNDARY == BOUNDARY` |
| `v5_cue_stage1a.BOUNDARY` → 0.21 | `BOUNDARY == BOUNDARY` |
| `simulate_a_design.PASS_ALPHA` → 0.03 | `PASS_ALPHA == LEDGER_PASS_ALPHA` |
| `v5_cue_stage1a.LEDGER_PASS_ALPHA` → 0.03 | `PASS_ALPHA == LEDGER_PASS_ALPHA` |
| `simulate_a_design.FUTILITY_ALPHA` → 0.06 | `FUTILITY_ALPHA == ALPHA` |
| `v5_cue_stage1a.ALPHA` → 0.06 | `FUTILITY_ALPHA == ALPHA` |

Baseline: no equality breaks. Each single move breaks exactly its pair. The constants
themselves were not edited in this PR.

## Criterion 5 — the model statement reads the replicate count

**Built.** `summary_md` compares `replicates` with the script's `REPLICATES` default
(2,000). Below that count it prints the smoke schema sentence. At or above it, it states
what the simulation establishes under the declared independent-Bernoulli model and what it
does not establish (real Claude Code epoch counts; any subject model other than the
stand-in).

**Pinned by.** `::test_summary_marks_smoke_output_as_schema_evidence`, extended per the
ticket to cover both the smoke count (20) and the full count (`REPLICATES`), plus a
just-below count (`REPLICATES - 1`).

**Before/after.** Before the change the test's full-run assertion failed:
`assert "establish only the output schema" not in full` — the old summary printed the smoke
sentence whatever the replicate count. After the change the smoke sentence appears only
below `REPLICATES`, and the full-run summary carries the operating-characteristics statement
with its refusals. The committed smoke `summary.md` (20 replicates) still carries the smoke
sentence; `test_committed_smoke_summary_reports_the_target_check` continues to pass.

## Criterion 6 — re-derived target check against the #696 output

**Status: NOT TICKED.** The #696 full-grid files live on the operator's host at
`C:/Users/mlpgr/wt-696-out/full`. This container is a Linux worktree with no route to that
path and no network access to the operator's machine. The files are not in the repository.
Per the ticket, the committed smoke data was **not** substituted.

What can be checked from inside the repo: the re-derived target check on the committed
20-replicate smoke data reports diagonal minima (for example, best diagonal P(PASS) at
d = 0.30 is 0.2000 at 1,200 epochs, null_per_pair 2.0, direct; best diagonal P(CUT) at
d = 0.10 is 0.5000 at 1,200 epochs, null_per_pair 1.0, union/direct). Those numbers are
smoke-scale and are not the #696 2,000-replicate figures (0.2335 and 0.5070). The code path
is the diagonal minimum the ruling requires; reproducing the #696 table needs the host files.

## Criterion 7 — gate

Ran and green at the branch tip:

- `pytest tests/test_simulate_stage1a_regime_685.py tests/test_simulate_stage1a_regime_684.py tests/test_v5_cue_stage1a.py`
- `ruff check src tests scripts`
- `ruff format --check src tests scripts`
- `mypy --strict src/ tests/ scripts/drift_check.py scripts/release_gate.py scripts/check_dependency_anchor.py`
- `python scripts/drift_check.py`
- `pytest tests/test_receipts_index.py tests/test_mutation_receipt.py`

## Which test covers which criterion

| criterion | test(s) |
| --- | --- |
| 1 diagonal aggregation + summary text | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum`, `test_summary_target_check_text_says_diagonal_not_all_nine` |
| 1b sensitivity section | `test_summary_reports_off_diagonal_cells_as_sensitivity` |
| 2 unequal fixture + three mutants | `test_target_check_uses_the_diagonal_minimum_not_the_nine_cell_minimum` (mutants M-S1A-13/14/15 in the 708 receipt) |
| 3 calibration read + exit code | `test_calibration_covers_the_fn_margin_cell_at_d030`, `test_calibration_set_includes_every_pass_and_cut_error_cell`, `test_cut_calibration_uses_the_futility_nominal_level`, `test_main_exits_non_zero_when_the_fn_margin_cell_fails_pass_calibration` |
| 4 constant pin | `test_v5_cue_stage1a.py::test_simulator_constants_pin_to_the_registered_launcher` |
| 5 model statement | `test_summary_marks_smoke_output_as_schema_evidence` (extended) |
| 6 #696 reproduction | **unticked** — host files unreachable |
| 7 gate | the commands listed above |

## Committed smoke summary: what changed and what did not

The ticket's recommended shape says the committed smoke `summary.md` under
`docs/findings/data/stage1a-regime-685/` is regenerated because its target-check text
changes, and to stop and report if regeneration changes any number other than the
target-check section.

A full regeneration from the committed TSVs was attempted
(`.scratch/issue-708/regen_smoke_summary.py`). Two differences outside the target-check
section appeared, so the PR does **not** ship that full regeneration:

1. **Terminal-state table.** `terminal_states.tsv` in the repository contains only the
   six 300-epoch-budget designs (n_pairs 120/100/75). The summary's terminal section is the
   subset n_pairs = 400, null_per_pair = 1.0, union. Those 400-pair terminal rows are not
   in the committed TSV, so a TSV-driven regeneration zeroes that table. The committed
   terminal numbers are left as they stand.
2. **Surface-table calibration cell.** Under the broader calibration read (criterion 3),
   the surface row for (p_P 0.40, p_N 0.40, d = 0.20) flips its `cal` cell from `yes` to
   `NO`: P(CUT) = 0.2000 exceeds FUTILITY_ALPHA + 3 SE ≈ 0.196 at 20 replicates. That is a
   real consequence of criterion 3, not a rounding artifact. The committed surface table is
   left as it stands; a future full re-run of the smoke grid at the registered seed would
   write the `NO`.

A third difference (surface SE 0.1067 → 0.1066 on two rows) is a float-rounding artifact of
re-parsing the four-decimal TSV and is not carried.

What the PR **does** change in the committed summary: the Target-check prose and table
(diagonal language; diagonal minima from the smoke data instead of the ill-posed nine-cell
minima, which were pinned at 0.0000 by the F − N margin cell), a new
`## Sensitivity (off-diagonal cells)` section, and nothing else. The model statement stays
the smoke sentence because the committed run is 20 replicates, below `REPLICATES`.

## Companion artifacts

- `docs/assurance/stage1a-regime-685-mutation-receipt.{json,md}` — regenerated against the
  #708 tree; all twelve 695-stage1a mutants KILLED. Prose companion names the new digest
  `49b0576185f11964372036c14a8b0ab6b424c11e0208a32ec73252ccc05ded9b`.
- `docs/assurance/stage1a-regime-708-mutation-receipt.{json,md}` — new; five 708-stage1a
  mutants, all KILLED. Indexed in `docs/receipts-index.md`.
- `docs/findings/data/stage1a-regime-685/summary.md` — target-check section and sensitivity
  section updated as described above.
- The #696 full-grid files at `C:/Users/mlpgr/wt-696-out/full` do **not** exist in this
  repository and could not be read from this container.
- The ruling record in the owner's private research repository, audit document
  `stage1a-drift-audit-S501.md` sections 5.1, 7 and 8, lives outside this repository and
  was not read; the ruling is taken from the ticket text, which quotes the owner's issue
  comment.
