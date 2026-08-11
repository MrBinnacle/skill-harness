# Finding: store-bricking deadlock (comment-only edit permanently locks evidence stores)

**Severity:** `CORRUPTION`
**Ticket:** #168 (evidence-store stateful machine + deadlock reproduction); fix owned by #169
**Status:** **half discharged.** Instance 6a is FIXED (#169). Instance 6b stands, tracked as #209.
The finding stays open until 6b is ruled on — a CORRUPTION finding with one live instance is not closed.
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

## The repair (6a only) — #169

Fixed by adding a **second question** rather than by weakening either safeguard.

`discover()` now computes a **semantic digest** alongside the raw one: the same file
with `--` comments stripped and whitespace collapsed, by a string-literal-aware
scanner rather than a regex (the trigger bodies carry literals such as
`'append_only_violation: schema_migrations'`, and `--` may legally appear inside
one). On a raw-digest mismatch, `apply_pending()` asks whether the semantic digest
recorded against the digest in force still matches the file on disk:

- **it matches** → the edit changed no schema. A compensating **restamp** row is
  appended, recording the superseded digest, the new one and a reason. Resolution
  is *latest restamp wins, else the ledger row*, which makes acceptance idempotent.
- **it differs, or was never recorded** → `MigrationTamperedError`, as before.

Nothing is ever rewritten or removed. Both safeguards remain in force: the raw
digest is still the tamper detector, the ledger row is still immutable, and a real
schema change still locks the store
(`tests/test_store_bricking_deadlock.py::TestMigrationLedgerDeadlock::test_schema_edit_locks_an_existing_store`).

Three properties worth stating, because they decided the shape:

- **No shipped `.sql` was edited.** Editing one is the trigger condition for this
  very bug, so a repair delivered that way would brick every existing store on the
  way to fixing bricking. The bookkeeping tables are runner-owned
  (`CREATE TABLE IF NOT EXISTS` inside `apply_pending`), and carry their own
  append-only triggers.
- **Stores created before the fix are healed on their first open after upgrading**,
  before any edit, by a backfill that runs exactly when the raw digest matches — the
  one moment the current file is provably the recorded one.
- **A store already bricked before upgrading is still refused**, deliberately: it
  holds no evidence that the edit was harmless, and trusting the file on disk would
  delete safeguard A rather than repair it. The remedy is to restore the original
  bytes, which the raw digest makes exact.

`test_no_restamp_path_exists_in_src` **stays green**, contrary to what #169
anticipated. The repair adds no mutating path against the ledger at all, so the
assertion about absence still holds — a better outcome than the one the ticket
predicted, and the test keeps its value as a guard against trading safeguard B away.

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

Per #168's scope, the fix was out of scope and belonged to #169. No storage
production code changed *by #168*. The requirement #169 had to satisfy was stated as
a `strict=True` xfail, `test_a_comment_only_edit_should_not_brick_the_store` — so
that when the fix landed the test would XPASS and `strict=True` would fail the
suite, and the deadlock could not be closed silently. #169 landed the fix and
removed the marker; the test is now a plain regression test under the same name.

## Why 6b was not fixed alongside 6a — tracked as #209

The two instances share a shape but not a remedy, and #169 fixed only 6a. Stated
here so the split is a recorded decision rather than an omission:

1. #169's own acceptance criteria require the change to be *"minimal and confined to
   the storage layer."* `src/skill_harness/subject/ingest.py` is the subject layer.
2. **The remedies genuinely differ.** 6a's normalisation is sound because SQL `--`
   comments cannot carry behaviour. Python docstrings can: they are live module data,
   so a digest that ignored them would report a changed threshold or rubric as "no
   behaviour change". That is a hole in the tamper detector, not a repair of it — the
   same error as normalising 6a's raw hash, which
   `test_sha_covers_comments_not_just_schema` exists to catch.
3. **The severities differ.** 6a left historical evidence readable and permanently
   unwritable, with no exit. 6b refuses to mint *new* verdicts under the registered
   identity; the store stays open and writable, and a named — though
   identity-forking — exit exists.

#209 carries the open design question (what a sound implementation-identity digest
for a Python module is) and is labelled for a maintainer ruling before any code.

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
