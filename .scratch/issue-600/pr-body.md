# Issue #600: Fix flaky test isolation — shared DB files between xdist workers

## What happened

Two tests went red in CI on 2026-09-20 on PRs that could not touch the behaviour under test. Both passed locally and cleared on rerun. The shared shape pointed at state shared between test processes: `table schema_migrations already exists` (MigrationApplyError) and empty CLI output (propagated exception leaves no captured output).

## Root cause

`src/skill_harness/cli/main.py` defaults `--evidence-db` and `--runtime-db` to the relative paths `./evidence.db` and `./runtime.db`. CLI test helpers (`_invoke` wrappers around Click's `CliRunner`) passed neither flag. `CliRunner` does not change the working directory, so every xdist worker wrote the same `./runtime.db` in the repository root. One worker then lost the race to create `schema_migrations`.

## What I built

### Criterion 1: Every CLI test helper passes `--evidence-db` and `--runtime-db`

Modified 11 `_invoke` helpers across 11 test files to pass `--evidence-db` and `--runtime-db` pointing into a per-invocation `tempfile.TemporaryDirectory`. Each helper now:
1. Creates a fresh temp directory per invocation
2. Passes `--evidence-db <tmpdir>/evidence.db --runtime-db <tmpdir>/runtime.db`
3. Places the flags after `args[:2]` (the group + subcommand) so Click binds them to the correct command
4. Skips adding flags if the caller already supplies them (prevents duplicates for commands like `run evaluate-paired` that only take `--evidence-db`)

Files modified:
- `tests/ablation/test_cli_run_ablation.py` — `run ablation` (both flags)
- `tests/ablation/test_cli_ratification_gate.py` — `run ablation` (both flags)
- `tests/ablation/test_cli_d3_fixes.py` — `run ablation` (both flags)
- `tests/ablation/test_subject_model_flag.py` — `run ablation` (both flags)
- `tests/test_ablation_report_verdict_id.py` — `run ablation` (both flags, plus existing `contextlib.chdir` for defence in depth)
- `tests/test_ablation_report_gate2_546.py` — `run ablation` (both flags, plus existing `contextlib.chdir`)
- `tests/test_cli_paired_gate2.py` — `run evaluate-paired` (both flags, with caller-supplied flag detection)
- `tests/test_cli_freeze.py` — `freeze` (both flags)
- `tests/test_cli_evaluate_skill.py` — `run evaluate-skill` (both flags)
- `tests/test_cli_diff_skill.py` — `diff skill` (both flags)
- `tests/test_audit_metric.py` — `audit-metric` (both flags)

Inline `CliRunner().invoke` calls with `--execute` in `tests/test_clause_evidence_audit.py` (line 160) and `tests/extractor/test_cli.py` (line 194) were also updated to pass explicit DB flags.

### Criterion 2: Isolation test proves the fix

Added `TestDbIsolation::test_no_runtime_db_in_working_directory` in `tests/test_ablation_report_verdict_id.py`. This test:
1. Calls `_invoke` with the same arguments one of the report tests uses (`run ablation skill-test` with ratified exec args)
2. Asserts that no `runtime.db` or `evidence.db` appears in `tmp_path` (the test's working directory)

**Observed before the fix (on `main`):** The test FAILS — `runtime.db` is created in `tmp_path` because `_invoke` did not pass `--runtime-db`, and the CLI defaulted to `./runtime.db` in the working directory.

**Observed after the fix:** The test PASSES — `_invoke` passes `--runtime-db` pointing into its private temp directory, so no DB file appears in `tmp_path`.

### Criterion 3: Confirmed failure on `main`

Ran the isolation test on the unmodified `main` branch (commit `d0ff304`). The test fails with:

```
AssertionError: runtime.db leaked into the working directory.
Pass --runtime-db pointing into a per-test tmp_path.
```

This confirms the race condition exists and the fix addresses it.

## Verification

- `ruff check src tests scripts` — all checks passed
- `ruff format --check src tests scripts` — 383 files already formatted
- `mypy --strict src/ tests/` — Success: no issues found in 356 source files
- All 234 tests across the 13 modified test files pass
