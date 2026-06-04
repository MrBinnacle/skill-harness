# RELIABILITY seat — Phase 1.5 Pre-Track-A Storage Review

**Date**: 2026-06-04
**Fire**: pre-Track-A storage review
**Seat**: RELIABILITY
**Subagent type**: general-purpose
**Brief**: dispositioned four fragility clusters surfaced by `audit-context-building` before Track A code lands

---

Confirmed: partial `executescript` failure leaves successfully-executed prior statements committed. The "killed mid-`executescript`" failure mode is real and observable.

Now I have everything needed. Emitting the disposition.

---

## F1 — Migration apply is NOT atomic; no recovery path defined

- **Severity**: BLOCKER
- **Cluster**: M1
- **Claim**: `apply_pending` in `src/skill_harness/storage/migrations.py:103-108` cannot atomically pair DDL with the `schema_migrations` ledger row because the connection is in autocommit (`isolation_level=None`); a process kill, disk-full, or `executescript` mid-statement failure between line 104 and 108 leaves the database in an unrecoverable state with no automated path back to healthy.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:103-108` (the `with conn:` block under autocommit).
  - `src/skill_harness/storage/migrations.py:119` (`isolation_level=None` set in `open_db`).
  - Python sqlite3 docs: https://docs.python.org/3/library/sqlite3.html#sqlite3-controlling-transactions — "If `isolation_level` is set to `None`, no transactions are opened implicitly... `Connection.__enter__`/`__exit__` will not commit/rollback transactions" (behavior is module-level transaction management; under autocommit there is nothing to commit or roll back).
  - SQLite `executescript` docs: https://www.sqlite.org/c3ref/exec.html and Python `executescript` — issues `COMMIT;` of any pending transaction before running, then runs statements as auto-committed.
  - Empirically reproduced in this session: under `isolation_level=None`, `with conn:` does not roll back an INSERT when an exception fires inside the block; and a malformed `executescript` leaves successfully-run prior statements committed.

**Per failure mode (RELIABILITY owns the recovery semantics call):**

**(1) Process killed between `executescript` (line 104) and `INSERT schema_migrations` (line 105-108).**
- (a) State: DDL fully applied; ledger row absent.
- (b) Next open: `discover()` re-presents the same `Migration`, `applied_records()` does not see it, `apply_pending` calls `executescript` again, fails with `sqlite3.OperationalError: table ... already exists` on the first `CREATE TABLE`.
- (c) Recovery: NONE automated. Operator must hand-craft the missing `schema_migrations` row using the recorded SHA — but the recorded SHA does not exist on disk anywhere because it is computed at runtime. Operator must compute it manually (`hashlib.sha256` of the file) and `INSERT` it. Then re-open. There is no documented runbook for this.
- (d) Observability: NONE. The error surfaces as the generic SQLite "already exists" string — no typed `MigrationApplyFailed`, no log line, no hint that this is a half-apply.

**(2) Process killed mid-`executescript` (some DDL statements committed, others not).**
- (a) State: Partial DDL — `e.g.`, `schema_migrations` and some tables present, others absent. Empirically confirmed above (script halted on syntax error after `CREATE TABLE good; INSERT INTO good VALUES (1);` — `good` survived). For evidence DB the first DDL is `schema_migrations` itself plus its triggers — these will partially exist.
- (b) Next open: re-runs `executescript` from the top; fails on the first already-existing object (`schema_migrations` or `CREATE TRIGGER schema_migrations_no_update`). No partial-completion recovery.
- (c) Recovery: NONE automated. Operator must `DROP` whatever partially-applied tables exist (which is itself blocked by the `_no_delete` triggers if they happened to be created — a DEADLOCK with the append-only invariant — see F5 below), OR delete the entire DB file. For a fresh-bootstrap case the file delete is harmless; for a partial migration applied to a populated DB (future migration 0002+) it is catastrophic.
- (d) Observability: NONE.

**(3) Disk full at the `INSERT schema_migrations` line (105-108).**
- (a) State: DDL applied (it ran first); ledger row failed.
- (b) Next open: identical to failure mode (1).
- (c) Recovery: identical to (1). Worse, because disk-full is recoverable (clear space) but the half-apply is now permanent.
- (d) Observability: the original `sqlite3.OperationalError: database or disk is full` is the only signal, and it's raised from `apply_pending` — caller code in `open_evidence` does not catch it, does not annotate it, does not record it. Next open emits the "already exists" error and the original disk-full context is lost.

**(4) Two processes racing `apply_pending` with `busy_timeout=5000` set.**
- (a) State: SQLite serializes via the file lock. Per https://www.sqlite.org/c3ref/busy_timeout.html, the second process waits up to 5s for the writer lock. If `executescript` runs first in process P1 and is followed by the INSERT, both succeed atomically-enough from P2's perspective (P2 sees the post-INSERT ledger and skips). HOWEVER, under autocommit, each statement in `executescript` is its own transaction — P2 can interleave AFTER P1's `CREATE TABLE schema_migrations` succeeds but BEFORE P1's later DDL completes. In that interleaved window, P2 reads `applied_records()` and sees an empty result (ledger row not yet inserted by P1), starts its own `executescript`, fails on the now-existing `schema_migrations` table from P1's partial work.
- (b) Next open (either process): both processes potentially fail; whichever loses the race gets "already exists." `busy_timeout` does NOT protect against this because the lock is per-statement, not per-script.
- (c) Recovery: NONE automated. The DB may be in a partially-applied state from whichever process advanced further.
- (d) Observability: NONE. Failure looks identical to mode (1)/(2).

**Recommendation**: **fix-pre-Track-A**. Track A code will write evidence rows depending on this being correct; any test populating fixture data hides the half-apply bug because tests start from a fresh `tmp_path`. The exact fix is named below in the recovery semantics.

**Recovery procedure proposal (RELIABILITY owns this call):**
1. Switch `apply_pending` to explicit transaction control that works under autocommit: `conn.execute("BEGIN IMMEDIATE")` before line 104, `conn.execute("COMMIT")` after line 108, `conn.execute("ROLLBACK")` in `except`. This produces a single `IMMEDIATE` write transaction holding the writer lock across both the DDL and the ledger insert. (Note: SQLite DDL is transactional except for certain edge cases — `CREATE TABLE`/`CREATE TRIGGER` ARE rollback-safe.)
2. Replace `conn.executescript(m.sql)` with manual statement-by-statement execution inside the transaction. `executescript` issues an implicit `COMMIT;` before running, which would defeat the explicit transaction. This is the load-bearing fix — `executescript` cannot be used inside a controlled transaction.
3. On startup, if `apply_pending` raises during DDL, the explicit `ROLLBACK` puts the DB back to its pre-migration state; the next open retries cleanly.
4. Add a startup self-check (`PRAGMA integrity_check`) before `apply_pending` runs, and surface an explicit `BootstrapError` if a partially-applied state is detected somehow (e.g., schema objects exist but the ledger row for their migration does not — detectable by name-matching).
5. Emit a structured log line at each migration apply: `migration_applying`, `migration_applied`, `migration_failed` with the migration_id and SHA. This gives observability for failure modes (1)/(3).

**Cross-seat**: SCHEMA's lens on this. SCHEMA will likely demand the explicit transaction preserves the SHA-ledger semantics — confirmed by the proposal above. SCHEMA will probably also flag that DDL containing triggers must be tested for transactional rollback (some SQLite versions had bugs around trigger DDL rollback). I agree with that follow-on.

---

## F2 — Silent empty-DB on wheel install is the worst observability failure in the stack

- **Severity**: BLOCKER
- **Cluster**: M2
- **Claim**: `open_evidence()` returns a connection to an empty SQLite file when `REPO_ROOT = Path(__file__).resolve().parents[3]` does not resolve to the repo root (any non-editable install, packaged binary, or relocated source tree), and no error or warning is raised — all downstream failures present as "no such table" errors that look like data-corruption or query bugs, not like a bootstrap failure.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:24-26` — hard-coded `parents[3]` traversal from package source path.
  - `src/skill_harness/storage/migrations.py:51-52` — `discover()` returns `[]` when the directory does not exist; no error.
  - `src/skill_harness/storage/migrations.py:129` — `open_evidence` calls `apply_pending(conn, discover(...))`; an empty migration list is treated as success (zero migrations applied is indistinguishable from "all up to date").
- **Recommendation**: **fix-pre-Track-A**. Add an assertion in `open_evidence`/`open_runtime`:
  ```python
  migrations = discover(EVIDENCE_MIGRATIONS_DIR)
  if not migrations:
      raise BootstrapError(
          f"no migrations discovered at {EVIDENCE_MIGRATIONS_DIR}. "
          f"REPO_ROOT={REPO_ROOT} resolved from __file__={__file__}. "
          f"This typically indicates a non-editable install or relocated source tree. "
          f"Set SKILL_HARNESS_MIGRATIONS_DIR env var or use editable install."
      )
  ```
  Also raise on `apply_pending` returning `[]` for a connection that has no `schema_migrations` table yet — that case is "we opened a brand-new DB and applied zero migrations to it" which is the silent-empty-DB scenario in disguise.
  Long-term, package the migrations directory as package data (`importlib.resources`) and stop relying on filesystem traversal entirely. Mark that for v0.2.
- **Cross-seat**: SCHEMA will agree (a DB with no append-only triggers fails the SCHEMA invariant — any caller who manages to write to it has bypassed the entire append-only discipline). SECURITY will note that a silent empty DB is a downgrade vector — if an attacker can convince a user to install a non-editable copy, they get a DB with no triggers and can mutate evidence. I agree both lenses converge on "this is a BLOCKER, not a polish item."

---

## F3 — Over-strict immutability trigger blocks legitimate recovery paths

- **Severity**: MAJOR
- **Cluster**: M3
- **Claim**: `runs_completed_at_once` trigger at `migrations/evidence/0001_initial.sql:203-205` fires on UPDATE of ANY column when `completed_at` is set, which prevents a legitimate recovery path: marking a run as `completed_at = <timestamp>` after the fact when the process died mid-run with `runtime.run_progress.state = 'running'` but `evidence.runs.completed_at IS NULL`.
- **Evidence**:
  - `migrations/evidence/0001_initial.sql:203-205` — trigger `WHEN OLD.completed_at IS NOT NULL` blocks any further UPDATE, regardless of column.
  - `migrations/runtime/0001_initial.sql:17-24` — `run_progress` has a `state IN ('pending','running','draining','completed','failed','aborted_budget')` enum but `evidence.runs` has only `completed_at NULL/NOT NULL`.
- **Recovery story (what's missing):** A crashed run leaves `runtime.run_progress.state = 'running'` (or stale `last_heartbeat`) and `evidence.runs.completed_at IS NULL`. The intended reconciliation is presumably: a separate process detects stale heartbeats, sets `evidence.runs.completed_at` to mark the run terminated (with what terminal status? `'failed'`? `'aborted_unknown'`?). The current schema does NOT model this — there is no `terminal_state` column on `evidence.runs`, only `completed_at`. So "completed" is conflated with "succeeded." A reconciler that wants to record "this run died mid-flight" has no admissible column to write to. The trigger then also blocks any later legitimate update (e.g., post-mortem annotation, "archived" status, "reconciled-by-operator" marker).
- **Recommendation**: **fix-pre-Track-A**. Two changes:
  1. Add `terminal_state TEXT CHECK (terminal_state IN ('completed','failed','aborted_budget','crashed_reconciled'))` to `evidence.runs`, NULL until set, IMMUTABLE once set (separate single-shot trigger). This makes "why did the run end" admissible evidence rather than implicit.
  2. Loosen the trigger to: `BEFORE UPDATE OF completed_at, terminal_state ... WHEN OLD.completed_at IS NOT NULL OR OLD.terminal_state IS NOT NULL` — only fire on the two named columns. Leaves room for explicit "annotation" columns in v0.2 if needed.
  Alternative (less invasive): accept the constraint as-is, but document the runbook for crashed-run reconciliation explicitly — the reconciler writes `completed_at = <crash_detected_at>` as the single permitted post-crash write, and the harness reports such runs as `UNMEASURED(no_data)` because there are no admissible verdicts. This is acceptable if it's WRITTEN DOWN.
- **Cross-seat**: TEST-ARCH owns the state-machine call here — they will probably demand a named terminal_state enum to make falsifiability testable. I agree. SECURITY may flag that loosening triggers introduces attack surface; I would respond that loosening to "only fire on named columns" is tighter than the current "fire on any column" rule because the latter is over-permissive about what cannot be modified — it's not actually a security strengthener, it's just a bug.

---

## F4 — Runtime ledger lacks tamper-evidence; corruption is silently recoverable into a wrong-state DB

- **Severity**: MAJOR
- **Cluster**: M4
- **Claim**: `runtime.db.schema_migrations` at `migrations/runtime/0001_initial.sql:9-14` has no `BEFORE UPDATE`/`BEFORE DELETE` triggers; the SHA-256 ledger that gates `MigrationTamperedError` for the evidence DB has no equivalent protection in the runtime DB, so an attacker (or a buggy migration tool) that mutates the runtime ledger to "make a migration look re-runnable" can re-run DDL silently, including destructive DDL — and the runtime DB also has no asymmetric integrity check at startup distinct from evidence's tamper-evidence detection.
- **Evidence**:
  - `migrations/runtime/0001_initial.sql:9-14` — runtime `schema_migrations` table is created with no triggers attached.
  - `migrations/evidence/0001_initial.sql:8-17` — evidence `schema_migrations` has both triggers and `RAISE(ABORT)`.
  - `src/skill_harness/storage/migrations.py:86-110` — `apply_pending` uses identical logic for both DBs; the only enforcement difference is the trigger asymmetry above.
- **Recovery & detection story:**
  - Evidence DB corruption → `MigrationTamperedError` raised on next open. Detectable, typed, fails loudly.
  - Runtime DB corruption → silent. If a row is altered, `applied_records()` returns the new (wrong) SHA, `apply_pending` either skips a migration that wasn't actually applied OR re-runs a migration it thinks wasn't applied; either way the DB is in an inconsistent state and the only signal is whatever downstream constraint check happens to fail. There is no "this DB has rolled back state" signal.
  - "Silent rollback" risk: if the cost ledger DB is restored from an older backup (e.g., after disk failure), the system reads `cost_ledger` as up-to-date but the trailing-24h sum may now exclude calls that were actually made — meaning the daily-cap check is bypassed. A12 daily-cap enforcement depends on the runtime DB being authoritative for the trailing-24h window; if the runtime DB silently rolls back, the cap is silently violated.
- **Recommendation**: **fix-pre-Track-A**. Two layers:
  1. Add the same BEFORE UPDATE / BEFORE DELETE triggers on `runtime.schema_migrations` only. The runtime DB MAY be mutable for operational state (`run_progress`, `current_calibration`, `cost_ledger`) but the migration ledger itself MUST be append-only for the same reason the evidence one is.
  2. Add a `db_id TEXT NOT NULL` column (UUID generated at first open and stored in a `db_identity` single-row table) so the harness can detect "this runtime.db is not the one we last saw" on startup. Cross-reference against an identity record in a config file or `evidence.runs` (last known runtime_db_id). Mismatch raises a typed `RuntimeDBIdentityChanged` warning, surfaces explicitly to the operator. This is the "silent rollback detection" layer; absent it, restore-from-backup is invisible.
- **Cross-seat**: SCHEMA will likely propose option (1) (trigger symmetry). SECURITY will likely propose option (2) (identity record). I think both are needed, not either-or — option (1) protects against in-place tampering, option (2) protects against restore-from-backup. TEST-ARCH's lens is weakest here because it's an operational concern, not a falsifiability concern, but they may flag that the test fixture in `tests/conftest.py` should add a test that mutating `runtime.schema_migrations` raises.

---

## F5 — (Beyond the 4 clusters) `WAL + synchronous=NORMAL` semantics not documented; partial-DDL deadlock with append-only triggers

- **Severity**: MAJOR
- **Cluster**: M1 (extension)
- **Claim**: `PRAGMA synchronous = NORMAL` at `src/skill_harness/storage/migrations.py:122` combined with `journal_mode=WAL` at line 120 yields a documented SQLite guarantee where committed transactions survive application crashes but MAY be lost on power loss / OS crash; this is acceptable for the runtime DB but is a silent invariant violation for the evidence DB (which the harness markets as append-only / audit-trail-grade) and is undocumented in CLAUDE.md or PRD §17. Additionally, the partial-DDL state from F1 mode (2) can land in a state where `_no_delete` triggers exist on table X but the ledger row is missing — recovery requires DELETE, but the trigger blocks it. Deadlock against the append-only invariant.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:120-122` — pragmas set.
  - SQLite WAL docs: https://www.sqlite.org/wal.html — "PRAGMA synchronous=NORMAL ... transactions committed in WAL mode with synchronous=NORMAL might roll back following a power loss or system crash."
  - SQLite PRAGMA docs: https://www.sqlite.org/pragma.html#pragma_synchronous — confirms NORMAL is faster but loses durability against power loss while preserving it against application crash.
  - The CLAUDE.md "Evidence model" invariant states "Persistence is SQLite, **append-only**" with no carve-out for power-loss durability. The harness's audit-grade claim is silently weaker than advertised.
- **Recommendation**: **fix-pre-Track-A** (two parts).
  1. For `evidence.db`: switch to `PRAGMA synchronous = FULL`. The harness writes ~thousands of verdicts per run, not millions; the throughput cost is negligible compared to model API latency. The audit-trail invariant requires it.
  2. For `runtime.db`: keep `NORMAL`; in-flight state can tolerate replay-on-restart.
  3. Document the asymmetry in CLAUDE.md "Evidence model" section.
  4. For the partial-DDL deadlock: the F1 fix (explicit BEGIN IMMEDIATE / ROLLBACK) eliminates this scenario at the source. No separate fix needed beyond F1.
- **Cross-seat**: SECURITY will almost certainly call out the NORMAL→FULL gap for evidence DB (audit-trail invariant). SCHEMA will agree. TEST-ARCH will probably not surface this because durability is operational, not falsifiability. I am confident this is a real finding the council should adopt.

---

## Cross-talk block

**TEST-ARCH**:
- **RIGHT**: They will surface that the `runs` table lacks a `terminal_state` enum, mirroring the `runtime.run_progress.state` enum, and that the absence makes "did this run end normally?" untestable from evidence alone. I agree — that's F3's structural finding articulated through their lens. They will probably also call out that the existing `tests/test_smoke.py` does not exercise migration-failure paths AT ALL (no half-apply test, no tampered-SHA test, no concurrent-open test), which is a falsifiability gap directly downstream of M1.
- **WRONG**: They may over-call by demanding a full state machine for `evidence.runs` (multiple intermediate states stored). That would violate append-only — `runs` is supposed to be an envelope, the live state machine lives in `runtime.run_progress`. The right answer is single terminal_state, not a state history. I'd push back on any proposal that puts more than one state column on evidence.runs.
- **MISS**: Their lens is structurally bad at seeing concurrent-process race conditions (M1 mode 4) because there is no obvious "test" for it without a fault-injection harness. They will probably not propose a fix for the two-process race against `busy_timeout`.

**SCHEMA**:
- **RIGHT**: They will own the call that `runtime.schema_migrations` needs append-only triggers symmetrically with the evidence ledger (F4 part 1). They will probably also notice that the F1 fix (BEGIN IMMEDIATE + manual statement execution) requires their sign-off because `executescript` was load-bearing for the multi-statement DDL convenience, and switching to manual parsing risks parse-order bugs. They are right to require careful review.
- **WRONG**: They may over-call by demanding the trigger asymmetry between evidence and runtime DBs is itself a bug — wanting to push append-only enforcement onto `run_progress`, `current_calibration`, etc. That would defeat the entire two-DB partition. I'd push back: append-only is for evidence and the ledgers (migration + cost). Operational state must remain mutable.
- **MISS**: Their lens is structurally bad at seeing observability gaps (F2 silent-empty-DB). They will probably treat F2 as "an install-bug" rather than "an evidence-model integrity violation" — but a DB without triggers is a DB without the append-only invariant, which IS a schema-level violation. I will need to frame F2 in their vocabulary explicitly: "the silent-empty-DB scenario produces an evidence.db that does not satisfy SCHEMA-F1."

**SECURITY**:
- **RIGHT**: They will catch the silent-empty-DB as an attacker-controllable downgrade path (F2) and the silent-rollback-of-runtime-DB as a cost-cap-bypass vector (F4). They will also probably flag that `MigrationTamperedError` is raised but never actively responded to in any startup code path — what does the CLI do when this is raised? Tracebacks the user back into a prompt? They will want a documented incident-response runbook.
- **WRONG**: They may over-call by demanding that all recovery procedures be removed because "any auto-heal mechanism is an attacker primitive." That's correct in spirit but the F1 fix (explicit transaction with ROLLBACK) is NOT an auto-heal mechanism — it's atomic-or-not, which is the safest possible behavior. I'll push back on any blanket "no recovery code" stance.
- **MISS**: Their lens is structurally bad at seeing operational durability concerns like `synchronous=NORMAL` (F5) — they will frame it as "data integrity" but underweight the throughput tradeoff calculus. They may demand `synchronous=EXTRA` (full + checkpoint), which is overkill. The right answer is `FULL` for evidence, `NORMAL` for runtime — a calibrated answer that requires the operational lens, not the pure-security lens.

STATUS: BLOCKER-FOUND
