# #483: Exclude prototypes/ from ruff; scope both gates identically

## What happened

On `main` at `2691596`, `pre-commit run --all-files` fails with three ruff findings in
`prototypes/PROTOTYPE_firewall_walkthrough.py` (S608, E501 x2), while CI's lint job
(`ruff check src tests`) is green. The file is byte-identical to `main`; the failure is
not carried in by any working-tree change. The two gates disagree about what is linted,
and only one is enforced.

## The fix

**Option 2 from the ticket: exclude `prototypes/`**, consistent with the existing
exclusions for `fuzz/corpus`, `fuzz/crashes`, and `fuzz/artifacts`.

Three changes, each small and reversible:

### 1. `pyproject.toml` — add `prototypes` to `extend-exclude`

```toml
extend-exclude = ["fuzz/corpus", "fuzz/crashes", "fuzz/artifacts", "prototypes"]
```

This tells ruff to skip `prototypes/` regardless of how it is invoked (CI, pre-commit,
or direct). Throwaway walkthrough scripts are not held to production lint.

### 2. `.pre-commit-config.yaml` — add `files: ^(src|tests)/` to both ruff hooks

```yaml
- id: ruff
  files: ^(src|tests)/
  args: [--fix, --exit-non-zero-on-fix]
- id: ruff-format
  files: ^(src|tests)/
```

This scopes the pre-commit ruff hooks to `src/` and `tests/` only, matching CI's
`ruff check src tests` and `ruff format --check src tests`. Without this, the pre-commit
hooks lint everything ruff discovers (including any future non-`src`/`tests` Python
files), while CI stays scoped to `src` and `tests` — the exact divergence this ticket
exists to close.

### 3. `tests/test_ruff_gate_scope_483.py` — control test

Two assertions that fail when the two gates disagree:

- **`test_ruff_path_set_matches_between_gates`**: parses `.github/workflows/ci.yml` for
  the path arguments in `ruff check` and `ruff format --check`, parses
  `.pre-commit-config.yaml` for the `files:` regex on the ruff hook, and asserts the two
  sets are equal. Does not assert a literal value — survives legitimate changes to what is
  linted as long as both configs change together.

- **`test_extend_exclude_includes_prototypes`**: asserts `prototypes` is in
  `[tool.ruff] extend-exclude`, pinning the exclusion that the first test depends on.

## Evidence per acceptance criterion

### Criterion 1: The two gates scope ruff identically

**Before the fix:**
- CI ran `ruff check src tests` (two directories).
- Pre-commit ran ruff with no `files:` restriction (all files).
- `test_ruff_path_set_matches_between_gates` failed with:
  `ruff path sets disagree: CI=['src', 'tests'], pre-commit=['<no files: restriction>']`.

**After the fix:**
- CI runs `ruff check src tests`.
- Pre-commit runs ruff with `files: ^(src|tests)/`.
- `test_ruff_path_set_matches_between_gates` passes.
- `pre-commit run ruff --all-files` passes (was the original failure).
- `pre-commit run ruff-format --all-files` passes.

### Criterion 2: `prototypes/` is excluded from ruff

**Before the fix:**
- `ruff check prototypes/PROTOTYPE_firewall_walkthrough.py` found 3 errors (S608, E501 x2).
- `test_extend_exclude_includes_prototypes` failed with:
  `prototypes/ not in extend-exclude; found ['fuzz/artifacts', 'fuzz/corpus', 'fuzz/crashes']`.

**After the fix:**
- `ruff check prototypes/PROTOTYPE_firewall_walkthrough.py` still finds 3 errors (ruff
  respects `extend-exclude` only when discovering files, not when a file is passed
  explicitly), but pre-commit's `files: ^(src|tests)/` prevents it from ever receiving
  `prototypes/` files.
- `test_extend_exclude_includes_prototypes` passes.

### Criterion 3: Gate green

- `ruff check src tests` — All checks passed.
- `ruff format --check src tests` — 315 files already formatted.
- `mypy --strict src/ tests/` — Success: no issues found in 311 source files.
- `pre-commit run ruff --all-files` — Passed.
- `pre-commit run ruff-format --all-files` — Passed.
- `pytest tests/test_ruff_gate_scope_483.py tests/test_structural_bans.py` — 29 passed.

## What this does NOT do

- Does not delete `prototypes/`. That is a separate question (#483 does not prejudge it).
- Does not change CI's ruff scope. CI already lints `src tests`; the fix brings
  pre-commit into alignment, not the other way around.
- Does not fix the three ruff findings in `prototypes/`. They are now latent (nothing
  lints the directory) rather than blocking, which is the correct state for throwaway code.

## Revisit if

- A file under `prototypes/` is imported by `src/` or `tests/`, which would make it
  shipped code under a misleading directory name and reopen option 1 (lint it).
- `prototypes/` is deleted, which dissolves the question.
- CI is changed to lint `prototypes/`, which settles the fork toward option 1 and makes
  the three findings blocking rather than latent.
