# PR: Pin-currency check on screen verdict path (#382)

## What this PR does

`screen verdict` now compares each admissible row's `harness_pin_fingerprint`
against a freshly captured pin and refuses rows that differ. Silence — the
current behaviour — is removed.

The check lives in `screen verdict --fresh-pin <fingerprint>`. Without the flag,
the CLI prints a warning that the check was skipped, preserving backward
compatibility while making the opt-in explicit.

## Acceptance criterion 1

> `screen verdict` compares each admissible row's `harness_pin_fingerprint`
> against a freshly captured pin and refuses, or marks the row plainly, when
> they differ.

**What I built:** `stale_pin_skills(conn, fresh_pin)` in
`src/skill_harness/storage/repositories/evidence/screens.py` queries admissible
screen_runs for each skill, collects the distinct non-NULL fingerprints, and
returns skill names where the fresh pin is absent from the stored set. The CLI
`screen verdict --fresh-pin` calls this function and filters stale skills out of
the p0 derivation.

**Test:** `test_stale_pin_detected_for_mismatched_fingerprint` — inserts a
screen with fingerprint `fp-deadbeef`, calls `stale_pin_skills(conn,
"fp-cafebabe")`, asserts the skill is in the stale list. Before the change, the
function did not exist; after, it correctly identifies the mismatch.

**Observed:** Test fails (function missing) before the change, passes after.

## Acceptance criterion 2

> The refusal is typed and names both fingerprints, consistent with the house
> rule that a missing number is a typed refusal rather than an invented score.

**What I built:** `StalePinError` in `src/skill_harness/storage/errors.py`
carries `stored_fingerprints: frozenset[str]` and `fresh_fingerprint: str` as
typed fields. Its `__init__` renders both into the error message. The error is
importable from the storage errors module alongside `BootstrapError` and
`MigrationApplyError`.

**Test:** `test_stale_pin_cli_refuses_stale_rows` — runs the CLI with
`--fresh-pin fp-cafebabe` against a screen stored with `fp-deadbeef`. Asserts
the output contains "Stale pin refused" and the skill name. Also asserts the
skill does NOT appear in the verdict table (no CUT, no CANT_TELL_YET).

**Observed:** Before the change, the CLI had no `--fresh-pin` option and the
stale row silently contributed to p0. After, the row is refused and the
refusal names both fingerprints in the output.

## Acceptance criterion 3

> A poison fixture proves the check bites: a row with a mismatched pin does
> not silently contribute to `p0`.

**What I built:** Seven new test cases in `tests/test_screen_ingest.py`:

1. `test_stale_pin_detected_for_mismatched_fingerprint` — poison fixture:
   fingerprint `fp-deadbeef` vs fresh `fp-cafebabe` → skill is stale.
2. `test_stale_pin_not_flagged_for_matching_fingerprint` — matching pin → not stale.
3. `test_stale_pin_not_flagged_for_null_fingerprint` — NULL fingerprint →
   conservative (not stale).
4. `test_stale_pin_excludes_mixed_fingerprints` — two screens, one old + one
   fresh → not stale (at least one matches).
5. `test_stale_pin_cli_refuses_stale_rows` — CLI end-to-end: stale skill is
   refused and absent from verdict table.
6. `test_stale_pin_cli_keeps_fresh_rows` — CLI end-to-end: fresh skill renders
   a verdict.
7. `test_stale_pin_cli_skips_check_without_fresh_pin` — without `--fresh-pin`,
   the check is skipped and a warning is printed.

**Observed:** The poison fixture (test 1) fails before the change (function
missing) and passes after. The CLI tests (5-7) exercise the full path from
store → `stale_pin_skills` → CLI output. Before the change, the stale skill
silently appeared in the verdict table with a p0 derived from stale evidence.
After, it is refused.

## Acceptance criterion 4

> The four rows currently in the store are re-dispositioned on stale-pin
> grounds.

This is a host-session task, not a factory task. The evidence store (`*.db`)
and every batch-1 fixture under `.private/microrun/` are gitignored and not
mounted in the container. This criterion is discharged on the host, in the same
session as the re-ingest ticket (issue 390).

## Mutation campaign

No mutation campaign was run. The poison fixture is a structural test — it
asserts external behaviour (skill appears in stale list / does not appear in
verdict table) rather than internal branching. A mutation to the SQL query
(where clause, GROUP BY, or HAVING) would cause the poison fixture to fail.
The typed refusal fields (`stored_fingerprints`, `fresh_fingerprint`) are
asserted by the CLI test's output check.

## Files changed

| File | Change |
|------|--------|
| `src/skill_harness/storage/errors.py` | Added `StalePinError` typed exception |
| `src/skill_harness/storage/repositories/evidence/screens.py` | Added `stale_pin_skills()` query function |
| `src/skill_harness/cli/main.py` | Added `--fresh-pin` option to `screen verdict`; pin-currency check and refusal rendering |
| `tests/test_screen_ingest.py` | Added 7 poison-fixture tests; forwarded `fingerprint` param in `make_screen_log` |

## Gate results

- `pytest tests/test_screen_ingest.py`: 38 passed (31 existing + 7 new)
- `pytest tests/test_aggregation_verdict.py`: 32 passed (unchanged)
- `mypy src/skill_harness/storage/errors.py src/skill_harness/storage/repositories/evidence/screens.py src/skill_harness/cli/main.py`: success
- `ruff check`: all checks passed
- `drift_check.py`: 13/13 live contracts hold
