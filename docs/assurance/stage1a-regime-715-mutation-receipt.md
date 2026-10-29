# Mutation receipt: the #715 rebuild-path tests

**Standard:** #341. **Repair:** #715. Three defects in the `--rebuild` path of
the Stage 1A simulator survived the suite before this change. A rebuild could
return 0 unconditionally, read `p_cut` from the `p_pass` column, or ignore
`run_meta.json`, and no test failed. **Generator:**
`scripts/mutation_receipt.py --select 715-stage1a`.
**Machine-readable record:** `docs/assurance/stage1a-regime-715-mutation-receipt.json`.
**Pinned by content, not by commit:** `scripts/screens/419/simulate_stage1a_regime_685.py` at
`sha256:ddf29746026bcd6bde8435fd0f0cc12aa1e6942b5ed65235f39f033313e62429`.
**Commit at generation:** `663ed72e95acdbe47357d10e3e4504c4993d516b` —
informational only; currency is checked against the digest above by
`tests/test_mutation_receipt.py`. **Python:** 3.13.1.

Each case runs in its own git worktree at a fixed commit. Production is never
mutated in place. All three cases resolved `simulate_stage1a_regime_685` inside
their own worktree, every clean baseline passed first with nonzero collection,
every mutant imported, and the production digest was identical before and
after.

## Results

| mutant | obligation | mutation | verdict | killing test |
|---|---|---|---|---|
| M-S1A-22 | 715-stage1a-rebuild-exit-zero | the `--rebuild` branch returns 0 unconditionally | **KILLED** | `test_rebuild_of_measured_fixture_writes_its_summary_and_exits_one` |
| M-S1A-23 | 715-stage1a-rebuild-p-cut-from-p-pass | `results_from_output_dir` reads `p_cut` from the `p_pass` column | **KILLED** | `test_rebuild_of_measured_fixture_writes_its_summary_and_exits_one` |
| M-S1A-24 | 715-stage1a-rebuild-ignores-run-meta | the `--rebuild` branch sets `meta = None`, ignoring `run_meta.json` | **KILLED** | `test_rebuild_of_measured_fixture_writes_its_summary_and_exits_one`, `test_rebuild_reports_the_run_meta_seed_and_replicates` |

Three hand-chosen mutants. **No mutation score is reported**, because three
cases cannot support one; each case is a named obligation, not a sample.

The killing fixture is written by hand through the simulator's own
`per_look_tsv` and `terminal_tsv`, with no simulation. It holds one 400-pair
union family over the nine baselines at d = 0.10, 0.20 and 0.30. Its rebuilt
summary carries measured values in the headline, the target check, the
calibration column and the sensitivity table. P(CUT) differs from P(PASS) in
every row, and the d = 0.20 cell at (0.35, 0.35) has P(CUT) = 0.20, so
calibration fails and the expected exit code is 1. Its `run_meta.json` sets
seed 4242, which differs from the `--seed` default of 685.

## Companion campaigns

The same simulator digest is pinned by three earlier receipts, regenerated in
this change because the subject moved:

- `docs/assurance/stage1a-regime-685-mutation-receipt.json` (obligation prefix
  `695-stage1a`).
- `docs/assurance/stage1a-regime-708-mutation-receipt.json` (obligation prefix
  `708-stage1a`).
- `docs/assurance/stage1a-regime-712-mutation-receipt.json` (obligation prefix
  `712-stage1a`).

## What this receipt refuses to claim

It does not claim a mutation score, adequacy of the Stage 1A suite as a whole,
or that any surviving mutant outside the three named cases is safe. It does not
claim anything about the committed full-grid data. It says three specific
defects are detected, in isolated worktrees, against baselines that passed
first, and that the production tree was byte-unchanged throughout.

*Revisit if:* the simulator's rebuild path is removed, or the #715 deliverable
changes. Then regenerate with `scripts/mutation_receipt.py --select 715-stage1a`;
the currency gate reddens automatically the moment the simulator's bytes move.
