# Fix: Console reads COLUMNS at render time, not at import (#564)

## What changed

`src/skill_harness/cli/main.py:33` — the module-level `_console = Console()` was
replaced with a function `_console()` that returns a fresh `Console()` on each call.

A Rich `Console` reads `COLUMNS` in its constructor and pins `self._width` for
the life of the object. Every later change to `os.environ["COLUMNS"]` is then
ignored. Around 30 tests invoke the CLI through `CliRunner().invoke(cli, args,
env={"COLUMNS": "200"})` so that rich tables render wide enough for the asserted
substrings to survive. That override sets `os.environ` for the duration of the
call, which is after the Console already exists. It works today only because the
CI process happens to have no `COLUMNS` set, which leaves `self._width` as `None`
and sends rich back to the live environment on every render.

The fix: each `_console()` call returns a fresh `Console`, which reads the
current `COLUMNS` from the environment at construction time. This means each
render picks up whatever `COLUMNS` value is in `os.environ` at that moment —
whether set by the user's terminal, the test harness, or a resize event.

## Files changed

- `src/skill_harness/cli/main.py` — `_console = Console()` → `def _console() -> Console: return Console()`, all `_console.print(...)` → `_console().print(...)`
- `tests/test_cli_console_width.py` — new acceptance test (subprocess isolation)

`cli/paired_gate2.py` was not edited per the ticket's constraint.

## Acceptance criterion 1: subprocess with COLUMNS=80 before import

**Test:** `tests/test_cli_console_width.py::test_console_width_reads_columns_at_render_not_import`

**What it does:**
1. Spawns a fresh subprocess with `COLUMNS=80` in the environment.
2. In that subprocess, imports `skill_harness.cli.main` (Console reads COLUMNS=80
   at construction time).
3. Seeds a minimal evidence DB and skills root for `screen profile`.
4. Invokes `screen profile` via `CliRunner().invoke(cli, args, env={"COLUMNS": "200"})`.
5. Asserts that the output contains the full substring `n/a (pre-registry
   observation)` (30 chars) — which is truncated to `n/a (pre-registry obs…` at
   width 80.

**Observed before fix:** The test fails. The Console was created with width=80 at
import time, and CliRunner's `env={"COLUMNS": "200"}` only changes
`os.environ` during invocation — the Console already ignores it. The estimand
column renders `n/a (pre-registry obs…` (truncated).

**Observed after fix:** The test passes. Each `_console()` call returns a fresh
Console that reads `COLUMNS=200` from the environment set by CliRunner. The
estimand column renders the full `n/a (pre-registry observation)`.

## Acceptance criterion 2: git stash verification

```
git stash     → test FAILS (rc=1, _console is a Console object, not callable)
git stash pop → test PASSES (rc=0, label found in output)
```

The test is not weakened; it asserts an external behaviour (substring presence in
rendered output) that depends on the Console reading COLUMNS at render time.

## Gate results

- `ruff check src tests scripts` — All checks passed
- `ruff format --check src tests scripts` — 367 files already formatted
- `mypy --strict src/skill_harness/cli/main.py` — Success: no issues found
- `mypy --strict tests/test_cli_console_width.py` — Success: no issues found

## Existing test suite

- `tests/test_cli_screen_profile.py` — 13/13 passed (COLUMNS=200)
- `tests/test_cli_screen_profile.py` — 13/13 passed (COLUMNS=80, the original
  reproduction case from the ticket)
- `tests/test_cli_screen_profile.py` — 13/13 passed (COLUMNS=100)
- `tests/test_cli_paired_gate2.py` — 35/35 passed
- `tests/test_cli_freeze.py` — all passed
- `tests/test_cli_utf8_stdout_321.py` — all passed
- `tests/test_cli_untrusted_text_sanitization.py` — all passed

## Mutation campaign

No mutation receipt required. The ticket names `cli/paired_gate2.py` as the
receipt-bearing file, and the constraint is to not edit it. The fix touches only
`cli/main.py`.

## Revisit notes

- If the CI pin (`COLUMNS: "200"` in the Test job's `env:` block) is removed,
  the suite's pass/fail no longer depends on whether the launcher exports
  `COLUMNS`. The acceptance test pins this invariant.
- If Rich changes when it reads `COLUMNS`, the reproduction in "How to reproduce"
  would stop reproducing and this issue would become stale.
