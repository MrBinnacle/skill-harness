# Extend ruff lint scope to scripts/ (#535)

## Acceptance criteria

### Criterion 1: scripts/ is in the ruff lint scope

**What changed:** Added `scripts` to the ruff path set in three coordinated locations:

1. `.github/workflows/ci.yml` -- `ruff check src tests scripts` and `ruff format --check src tests scripts`
2. `.pre-commit-config.yaml` -- `files: ^(src|tests|scripts)/` on both ruff hooks
3. `pyproject.toml` -- `src = ["src", "tests", "scripts"]` under `[tool.ruff]`

**Test that pins it:** `test_ruff_scope_includes_scripts` in `tests/test_ruff_gate_scope_483.py:116`. Parses the CI workflow regex and both pre-commit `files:` regexes, asserts `scripts` appears in all three path sets.

**Red phase:** Before the change, the test failed with `scripts/ not in ruff CI scope; found ['src', 'tests']` and `scripts/ not in pre-commit ruff scope`.

**Green phase:** After the change, all four tests in `test_ruff_gate_scope_483.py` pass, including the existing `test_ruff_path_set_matches_between_gates` which asserts CI and pre-commit ruff scopes are identical.

### Criterion 2: pyproject.toml ruff src includes scripts

**What changed:** Added `"scripts"` to the `src` list under `[tool.ruff]` in `pyproject.toml`. This tells ruff to resolve first-party imports from `scripts/`, preventing spurious F401 or import-resolution findings.

**Test that pins it:** `test_ruff_src_config_includes_scripts` in `tests/test_ruff_gate_scope_483.py:133`. Parses pyproject.toml and asserts `"scripts"` is in `[tool.ruff] src`.

**Red phase:** Before the change, the test failed with `scripts/ not in [tool.ruff] src; found ['src', 'tests']`.

**Green phase:** After the change, the test passes.

### Criterion 3: scripts/ findings are within a handful

**What was found:** Extending ruff to `scripts/` surfaced 2 lint findings and 2 format findings -- well within a handful, not a sweep:

- 2x `RUF100` (unused `noqa: S310` directive) in `scripts/repo_description_check.py:95` and `scripts/words_to_avoid_drift_check.py:133`
- 1x `I001` (unsorted imports) in `scripts/ebmom_form_b_reproduction.py:52`
- 2x formatting (line length in the two files where noqa directives were removed)

All four were auto-fixable. The ticket's "revisit if" threshold was not triggered: a one-line CI change sufficed with no sweep required.

**Mutation campaign:** Not applicable -- no mutation receipt criterion in this ticket.

## Gate results

- `ruff check src tests scripts` -- pass
- `ruff format --check src tests scripts` -- pass
- `mypy --strict src/ tests/` -- pass (325 source files, no issues)
- `pytest tests/test_ruff_gate_scope_483.py` -- 4/4 pass
- `pytest tests/test_repo_description_check.py tests/test_words_to_avoid_drift_check.py` -- 31/31 pass
- `pytest tests/test_assurance_static_analysis_171.py` -- 3/3 pass

## Files changed

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | Add `scripts` to ruff check and format paths |
| `.pre-commit-config.yaml` | Add `scripts` to ruff hook files regex |
| `pyproject.toml` | Add `"scripts"` to `[tool.ruff] src` |
| `scripts/repo_description_check.py` | Remove unused `noqa: S310` |
| `scripts/words_to_avoid_drift_check.py` | Remove unused `noqa: S310` |
| `scripts/ebmom_form_b_reproduction.py` | Import sorting (ruff auto-fix) |
| `tests/test_ruff_gate_scope_483.py` | Add two acceptance tests for scripts/ scope |
