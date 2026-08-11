# Finding: store-bricking deadlock (comment-only edit permanently locks evidence stores)

**Severity:** `CORRUPTION`
**Ticket:** #168 (evidence-store stateful machine + deadlock reproduction); fix owned by #169
**Status:** open — **reproduced**, characterised, and pinned. No production code changed by this ticket.
**Harness:** `tests/test_store_bricking_deadlock.py` (reproduction) + `tests/test_evidence_store_stateful.py` (`ledger_row_cannot_be_corrected` rule)
**Reproduction:** deterministic — **no seed required.** See "Seed" below.

---

## Summary

Two integrity safeguards deadlock. Stated once, because both instances are the
same shape:

> **Safeguard A detects that a shipped file changed. Safeguard B forbids
> correcting the record that would clear safeguard A.**

Both safeguards hash **raw file bytes**, so the trigger does not require a schema
change — or any semantic change at all. Editing a single comment in a shipped
file permanently locks every evidence store that was created before the edit.
The product ships no repair path.

The maintainer's workspace log (2026-07-26) recorded the shape; this ticket
reproduces it and confirms **two independent instances** rather than one.

## Instance 6a — migration sha ledger x `schema_migrations` append-only

| Half | Mechanism | Location |
| --- | --- | --- |
| A (detect) | `discover()` hashes the whole migration file text; `apply_pending()` raises `MigrationTamperedError` on mismatch | `src/skill_harness/storage/migrations.py` |
| B (forbid repair) | the recorded sha lives in `schema_migrations`, which carries `BEFORE UPDATE` and `BEFORE DELETE` triggers raising `append_only_violation` | `src/skill_harness/storage/migrations_sql/evidence/0001_initial.sql` |

The two halves are created **in the same file**: `0001_initial.sql` creates
`schema_migrations` and its own append-only triggers, and its sha is the first
row written into the table it just created.

`src/` contains a `SELECT` and an `INSERT` against `schema_migrations` and **no
`UPDATE` path at all** — asserted by `test_no_restamp_path_exists_in_src`, which
is written as an assertion about absence so that #169's fix makes it fail.

## Instance 6b — `subject/ingest.py` self-hash x `metric_versions` append-only

| Half | Mechanism |
| --- | --- |
| A (detect) | `_oracle_implementation_hash()` hashes its own module's bytes (`Path(__file__).read_bytes()`); the fail-closed re-check compares against a stored row |
| B (forbid repair) | that row lives in `metric_versions`, which is append-only |

The documented escape — bumping `ORACLE_METRIC_VERSION` — is **not a repair**.
It clears the refusal by declaring a *new metric identity*, so evidence recorded
before and after the bump are no longer the same measurement. Pinned by
`test_the_named_escape_mints_a_new_measurement_identity` precisely because it is
easy to mistake for a fix.

## The minimal edit

Reword one comment line. No schema change, no semantic change:

```diff
-- a comment that carries no schema meaning whatsoever
+-- the same comment, reworded, with no schema meaning either
 CREATE TABLE schema_migrations (
```

`test_sha_covers_comments_not_just_schema` asserts the digest moves under exactly
this edit. That test is the trigger condition: if it ever fails, the deadlock has
narrowed and the rest of the module should be revisited.

## Seed

**None.** The reproduction is deterministic, not a search — a fixed edit against a
fixed migration produces the lock every time, so there is no seed to record and
recording one would imply a randomised hunt that did not happen.

The stateful machine that holds the shape under arbitrary interleavings is
Hypothesis-driven and does carry configuration; the deadlock rule
(`ledger_row_cannot_be_corrected`) is unconditional within it and does not depend
on the draw. Settings: default lane `max_examples=25, stateful_step_count=25`
(~6s); assurance lane `max_examples=400, stateful_step_count=120` (~168s measured,
linux, py3.13).

## The one escape hatch, and why it is not relief

`open_evidence_readonly()` deliberately skips `apply_pending`, so a bricked store
can still be **read**. It sets `PRAGMA query_only = ON`, so it cannot be used to
write — including to repair. Asserted behaviourally in
`test_readonly_access_survives_and_is_not_a_repair`.

Net operator position: after a comment-only edit to a shipped file, historical
evidence is readable and permanently unwritable.

## What this ticket did NOT do

Per #168's scope, the fix is out of scope and belongs to #169. No storage
production code changed. The requirement #169 has to satisfy is stated as a
`strict=True` xfail, `test_a_comment_only_edit_should_not_brick_the_store` —
when the fix lands, that test XPASSes and `strict=True` fails the suite, so the
deadlock cannot be closed silently.

## Note on the reproduction's own defects

The reproduction file was written but **never executed** before this ticket.
On first run, 3 of its 10 tests failed:

- the synthetic migration omitted `schema_migrations`, so `apply_pending` could
  not write its ledger row and no store could be built (2 tests);
- the read-only assertion scanned `migrations.py` for the string `apply_pending`
  and matched the docstring sentence stating it does **not** call it — a source
  scan cannot distinguish a call from a mention of one (1 test);
- and `test_the_ledger_row_cannot_be_corrected` targeted a column named `sha256`
  when the column is `file_sha256`, so it errored on name resolution and never
  reached the trigger it claimed to assert.

All four are corrected. The last is worth stating plainly: that test would have
been read as evidence the append-only trigger fires, while never having reached
it.
