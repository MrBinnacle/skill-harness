# Lazy `jsonschema` for `sitegen`, behind its own `[sitegen]` extra (#415)

## What was true before

`src/skill_harness/sitegen/__init__.py:30` imported `jsonschema` at module top
level; `src/skill_harness/sitegen/__main__.py:19` did the same for
`jsonschema.exceptions`. `jsonschema` was absent from
`[project.dependencies]` — it reached an install only through the `dev` extra
(`jsonschema>=4.26.0`) and transitively through `inspect-ai`
(`jsonschema>3.1.1`). A core install (`pip install skill-harness`, no extras)
therefore raised `ModuleNotFoundError: No module named 'jsonschema'` on
`import skill_harness.sitegen`, and `python -m skill_harness.sitegen` could
not run — not even `--help`, which crashed at import time. CI never saw it:
every job installs `[dev]`, so `jsonschema` is always present on the matrix.

`src/skill_harness/subject/inspect_adapter.py` already solved this exact
problem for `yaml`: a lazy import inside the function, behind a typed error
carrying an install hint (lines 41–56). `sitegen` answered the same question
differently. This PR makes it answer the same way.

## What changed

- `src/skill_harness/sitegen/__init__.py`: the top-level
  `from jsonschema import Draft202012Validator` is gone. A typed seam
  `_validator()` imports `Draft202012Validator` lazily and raises a new
  `SitegenNotInstalledError` carrying the extra's install hint on failure.
  `validate_receipts` and `_parse_schema` go through that seam, so the
  failure is at use time (during a build), not import time. `SitegenNotInstalledError`
  is exported in `__all__`.
- `src/skill_harness/sitegen/__main__.py`: the top-level
  `from jsonschema.exceptions import ValidationError` is gone. `main()`
  catches `SitegenNotInstalledError` first and prints an actionable refusal
  to stderr (exit 1); `ValidationError` joins the refusal tuple only when
  the `[sitegen]` extra is importable (built before the `try` so the
  `except` operand stays a literal tuple of exception classes — mypy checks
  `except` operands statically and does not follow `*` unpacking of a call
  there).
- `pyproject.toml`: a new `sitegen` optional extra declares
  `jsonschema>=4.26.0`, recording where it comes from. The `dev` extra
  re-declares it (mirroring `scipy`/`statsmodels`, which are also runtime
  deps re-declared in `dev` for the test stack) so `pip install -e ".[dev]"`
  alone still lands the full test stack. The mypy override comment added by
  #413 is rewritten to match what lands: both `yaml` and `jsonschema` are now
  imported lazily behind their optional extras' install hints
  (`yaml` behind `[inspect]`; `jsonschema` behind `[sitegen]`), and the
  statement that a core install cannot import `skill_harness.sitegen` is
  removed because it is no longer true.

## Acceptance criteria, addressed in turn

### AC1 — importing the affected module without `jsonschema` succeeds, or fails with a typed error naming the extra; the test asserts its own blocker is effective first

Built: the lazy seam in `__init__.py` and `__main__.py`.

Test that pins it: `tests/sitegen/test_cold_install.py::test_sitegen_imports_without_jsonschema`.

The test installs a `find_spec`-based meta-path finder (`_JsonschemaBlocker`)
whose `find_spec` raises `ImportError` for `jsonschema` and any submodule, after
clearing `jsonschema`/`skill_harness.sitegen` from `sys.modules` so the import
re-executes module top-level code. `find_spec` is the API Python 3.12+
consults; a `find_module`-only finder would be skipped and the import would
succeed, leaving the outcome assertion vacuous — exactly the failure mode the
ticket names. Before asserting the outcome, the test asserts a precondition
(`importlib.util.find_spec("jsonschema") is not None`, checked *before* the
blocker is installed, since `find_spec` consults the same meta-path) and the
blocker's effectiveness (`import jsonschema` raises `ImportError` inside the
blocked context). Then it imports `skill_harness.sitegen` and
`skill_harness.sitegen.__main__` and asserts both succeed.

RED observed: with the source stashed (pre-fix top-level import), all four
cold-install tests failed; this one failed because
`from jsonschema import Draft202012Validator` at module top level hit the
blocker and raised `ImportError` during `import skill_harness.sitegen`.

GREEN observed after the change: `4 passed`.

The build-time typed error is pinned by
`test_build_site_refuses_with_typed_error_naming_the_extra`: with the blocker
active, `build_site(...)` raises `SitegenNotInstalledError` whose message
matches `skill-harness\[sitegen\]`, and the output directory is not created.

### AC2 — `python -m skill_harness.sitegen --help` runs, or refuses with an actionable message naming the extra, from `[project.dependencies]` alone

Built: the lazy import in `__main__.py` lets argparse answer `--help` during
`parse_args`, before any build and before any `jsonschema` import.

Tests that pin it:
- `tests/sitegen/test_cold_install.py::test_module_help_runs_without_jsonschema`
  — with the blocker active, `main(["--help"])` raises `SystemExit(0)` and
  the help text naming `python -m skill_harness.sitegen` is on stdout.
- `tests/sitegen/test_cold_install.py::test_module_entry_point_refuses_with_install_hint_without_extra`
  — the build path (not `--help`) refuses with exit 1 and stderr containing
  both `REFUSED` and `skill-harness[sitegen]`, writing no output. This is the
  "or refuses with an actionable message naming the extra" direction.

RED observed (pre-fix, source stashed): `test_module_help_runs_without_jsonschema`
failed because importing `skill_harness.sitegen.__main__` re-executed the
top-level `from jsonschema.exceptions import ValidationError`, which the blocker
raised — `--help` never reached argparse.

### AC3 — `pyproject.toml` records where `jsonschema` comes from, and the #413 mypy override comment is updated to match what lands

Built: the new `sitegen` extra; the rewritten `dev` comment; the rewritten
mypy override comment. No new runtime dependency was added to
`[project.dependencies]` (the ticket's "declare `jsonschema` a core dep"
alternative was considered and rejected for the reasons in the ticket).

Pinned indirectly by the cold-install tests (the install hint string
`skill-harness[sitegen]` is asserted in two tests and must name a real
extra), and by the existing `tests/test_receipts_index.py` /
`scripts/drift_check.py` / `scripts/release_gate.py` gates, which still pass.
No test enumerates a docs registry that `.scratch/` or the `pyproject.toml`
extra list belongs to; the receipts-index test gates `docs/` receipt
directories only, which this change does not touch.

### AC4 — `mypy --strict src/ tests/` passes on a cold cache

Built: `return None` in the test finder's `find_spec` is annotated
`-> importlib.machinery.ModuleSpec | None` (the base signature); the
`except refusal as exc` operand is a literal tuple of exception classes
built before the `try`. The `# type: ignore[override]` that the original
signature needed is removed because the `| None` return makes the override
LSP-compatible.

Observed: `rm -rf .mypy_cache && mypy --strict src tests` →
`Success: no issues found in 291 source files` (exit 0) on a cold cache.
`ruff check src tests` and `ruff format --check src tests` both pass. The
pre-commit hook (which runs ruff + mypy among other checks) passed on the
implementation commit.

## Mutation campaign

Each mutant was applied to the committed green tree, the named test was run,
and the mutant was reverted with `git checkout --`. Every mutant was killed
by the named assertion (the test went RED); the tree was restored to green
after each.

| Mutant | Change | Killing test | Failure mode |
| --- | --- | --- | --- |
| M1 | Re-add `from jsonschema import Draft202012Validator` at module top level in `sitegen/__init__.py` (undo the lazy seam) | `test_sitegen_imports_without_jsonschema` | `import skill_harness.sitegen` re-executes the top-level import, the blocker raises `ImportError` during import |
| M2 | In `_validator()`, `except ImportError: raise` (bare re-raise) instead of `raise SitegenNotInstalledError(_INSTALL_HINT)` | `test_build_site_refuses_with_typed_error_naming_the_extra` | bare `ImportError` propagates instead of the typed error; the `SitegenNotInstalledError` match fails |
| M3 | Delete the `except SitegenNotInstalledError` handler in `main()` | `test_module_entry_point_refuses_with_install_hint_without_extra` | `SitegenNotInstalledError` propagates uncaught out of `main`; no exit-1 / no `REFUSED` on stderr |
| M4 | Re-add `from jsonschema.exceptions import ValidationError` at module top level in `sitegen/__main__.py` | `test_module_help_runs_without_jsonschema` | importing `skill_harness.sitegen.__main__` re-executes the top-level import, the blocker raises `ImportError`; `--help` never reaches argparse |

A blocker that did nothing (M0, not shown) is ruled out by the
`_assert_blocker_effective` precondition-and-effectiveness assertion that
every cold-install test runs before its outcome: `import jsonschema` must
raise `ImportError` inside the blocked context, and `jsonschema` must be
genuinely `find_spec`-importable before the blocker is installed — so the
probe cannot pass vacuously in CI where `jsonschema` is always installed.

## Gate

- `rm -rf .mypy_cache && mypy --strict src tests` → Success, 0 errors (cold cache).
- `ruff check src tests` → All checks passed.
- `ruff format --check src tests` → 295 files already formatted.
- `python scripts/drift_check.py` → `DRIFT CHECK: PASS - all 13 live contracts hold.`
- `python scripts/release_gate.py` → `RELEASE GATE: PASS — public surfaces in lockstep at version 0.2.3.`
- `pytest tests/sitegen/ tests/test_sers_conformance.py tests/test_delivery.py tests/test_sitegen_delivery.py` → 77 passed.
- `pytest tests/sitegen/test_cold_install.py` → 4 passed (the new contract).

A broad `pytest -q -n auto -p no:randomly -m "not live and not calibration and not assurance"` sweep showed 16 failures; all 16 reproduce on the clean tree with this branch's changes stashed (verified by `git stash` + re-run), they pass in isolation, and none touch `sitegen`/`jsonschema`. They are pre-existing `pytest-xdist` ordering artifacts in unrelated CLI/ablation/audit modules, not regressions from this change. CI runs `pytest -q` (no `-n`), the configuration under which those modules pass.

## Scope

No existing test was edited, weakened, skipped, or xfailed. The two repo
seams the ticket names (the `sitegen/__init__.py` top-level import and the
`sitegen/__main__.py` top-level import) are implemented in the form the
ticket decides: a lazy import behind a typed error carrying the extra's
install hint, mirroring `subject/inspect_adapter._yaml`. No issue was
changed.
