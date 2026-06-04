# RELIABILITY seat — Pre-Track-A implementation review (2026-06-04)

*Continuity note: this fire is the second RELIABILITY seat in this archive. The prior seat (`docs/council-fires/2026-06-04-pre-track-a-storage/seat-RELIABILITY.md`) produced A18 (apply_pending atomicity) and A22 (synchronous=FULL). Those are LOCKED and realized in `src/skill_harness/storage/migrations.py:138-185` and `:191-213`. This seat reviews the Track A implementation shape that consumes them — not the storage primitives themselves.*

## Q1 — Repository pattern shape
- **Disposition**: MAJOR
- **Claim**: Per-table modules with **functional** writers (`insert_<table>(conn, ...)`) — not class-based repos. Class repos invite hidden per-instance state (connection, batch buffer, cached calibration pointer); a stateful repo across a power-cut window is exactly where "I thought we'd written that row" lives. Functional writers force every call to declare its connection + transaction state at the call site. **The append-only invariant must be reflected in the type signature**: an `EvidenceWriter` Protocol that only exposes `insert_*`, with no `update_*`/`delete_*` methods even nominally — `mypy --strict` then refuses Track D code that tries to mutate evidence even before SQLite does.
- **Evidence**: `migrations.py:191` already follows functional shape — `open_db(path, *, synchronous=...)` returns a `Connection`, caller owns lifecycle. Repo layer should match. `oracle_verdicts` CHECK constraint (`migrations/evidence/0001_initial.sql:133-137`) is intricate enough that I want a Pydantic `OracleVerdictWrite` model with `model_config = ConfigDict(strict=True, frozen=True)` validating the tier-1/tier-2/tier-3 row-shape BEFORE the INSERT.
- **Recommendation**:
  1. `src/skill_harness/storage/repos/{table}.py` — one module per table. Functions only.
  2. Pydantic write-models in `src/skill_harness/storage/models.py`, `strict=True, frozen=True`.
  3. Two Protocols: `EvidenceWriter` (insert-only) and `RuntimeWriter` (insert/update).
  4. **Repo functions take a `Connection`, not a path** — connection lifecycle is the caller's. (Defers to Q5.)
- **What-would-change-it**: if Track A discovers a single-row-update use case in `runs` (`completed_at`) that demands transaction-scoped batching, I'd accept a thin `RunCompleter` class with one `mark_completed(run_id, ts)` method.
- **Cross-seat**: SCHEMA owns the row shape; TEST-ARCH owns whether the Protocol typing catches "code that tries to update evidence" at static-check time.

## Q2 — Dual-DB transaction primitive
- **Disposition**: MAJOR
- **Claim**: **Evidence wins, runtime is reconcilable.** Sequence: BEGIN IMMEDIATE on evidence → INSERT oracle_verdicts → COMMIT evidence → BEGIN IMMEDIATE on runtime → INSERT cost_ledger → COMMIT runtime. If the second COMMIT fails (power loss, full disk on the runtime volume, OS kill), the evidence row stands and the cost ledger has a gap. The reverse ordering (runtime first) is **wrong**: a cost row without a backing verdict is a phantom charge, harder to reconcile than a missing charge. `ATTACH DATABASE` is tempting but defeats A22 — attached DBs share the journal-mode and synchronous settings of the primary, collapsing the FULL/NORMAL split.
- **Evidence**: SQLite WAL durability (sqlite.org/wal.html) — separate WAL files per DB; cross-DB atomicity is not provided. `cost_ledger` has `ledger_id INTEGER PRIMARY KEY AUTOINCREMENT` (`migrations/runtime/0001_initial.sql:63`); a reconciler can scan `evidence.oracle_verdicts WHERE NOT EXISTS (SELECT 1 FROM cost_ledger WHERE ts = verdict.written_at AND run_id = verdict.run_id)` to detect gaps.
- **Recommendation**:
  1. `src/skill_harness/storage/dual_write.py::write_verdict_with_cost(evidence_conn, runtime_conn, verdict, cost_row)` — sequenced, evidence-first.
  2. A `cost_ledger_reconciler` background task spec'd for Track D (but stubbed in Track A) that runs at every `open_runtime()` after BootstrapError-clean: scan evidence for orphan verdicts since `max(cost_ledger.ts)`, log gaps with structured `reconcile_gap` event.
  3. **Budget read-then-check race**: A12's "Budget check inside writer transaction" applies to the *runtime* transaction. Inside `BEGIN IMMEDIATE` on runtime: SELECT usd_spent → check against hard_cap → INSERT cost_ledger → UPDATE run_budget → COMMIT.
- **What-would-change-it**: if Track D's design calls for streaming verdicts at >100/s, the per-write FULL fsync on evidence is too expensive.
- **Cross-seat**: TEST-ARCH owns whether the gap-reconciler is tested with crash injection; SECURITY owns whether the gap itself is an audit-evasion vector (it isn't — evidence still stands).

## Q3 — Single-writer queue
- **Disposition**: BLOCKER
- **Claim**: "Single-writer queue per DB" is currently three things conflated: (a) SQLite's own writer-exclusion via `BEGIN IMMEDIATE` (the DB-level lock), (b) Python-process discipline (one thread holds the write lock), (c) application-layer ordering of writes (so they go in a deterministic order across runs for replay). PLAN.md and A2 do not distinguish. Track A must pick ONE concrete primitive or it ships a contract it cannot honor. **My recommendation: do NOT build an in-process queue for v0.1. Use SQLite's `BEGIN IMMEDIATE` + `busy_timeout=5000` (already set, `migrations.py:212`) as the single-writer mechanism, and constrain Track D to a single sampling thread.** Multi-threaded sampling is a Phase 2 optimization, not v0.1.
- **Evidence**: `migrations.py:212` sets `busy_timeout=5000` — under contention SQLite already blocks the second writer for 5s before raising `SQLITE_BUSY`. Adding a `queue.Queue` + writer thread would duplicate this and introduce a new failure mode: queue-full when the consumer stalls.
- **Recommendation**:
  1. **Document the single-writer mechanism explicitly in `storage/__init__.py` docstring**: "Concurrency model: SQLite `BEGIN IMMEDIATE` + 5s busy_timeout is the writer-exclusion primitive. Application code MUST issue writes from a single thread per DB connection."
  2. **Backpressure under cost_ledger pressure**: at realistic Track D rates (sequential calls, ~2s each), single-writer is comfortable. Document the head-room.
  3. **If Track D ever wants parallel sampling**: it spawns subprocesses (NOT threads) that each open their own runtime.db connection. Evidence writes still serialize at the SQLite level. Defer to v0.2.
- **What-would-change-it**: if a real workload shows `SQLITE_BUSY` raises during a single-thread sampling loop, revisit.
- **Cross-seat**: TEST-ARCH owns the property test under contention; SECURITY owns whether subprocess-per-worker creates a credentials-handling vector.

## Q4 — Property-based test design
- **Disposition**: MAJOR
- **Claim**: Crash injection is a **separate test family** from the append-only property test. Mixing them breaks Hypothesis shrinking — the test framework cannot shrink a counterexample whose minimal repro requires "kill the process between statements X and Y." Two families:
  1. **Property family** (Hypothesis): ∀ valid INSERT, ∄ subsequent UPDATE/DELETE succeeds. No fault injection. Runs fast, shrinks cleanly.
  2. **Crash-injection family** (manual test cases per code path, with `os._exit(1)` between phases, then reopen DB and assert state). Hand-curated; small N; not Hypothesis-driven.
- **Evidence**: `test_migration_apply_is_atomic` (`tests/test_smoke.py:202-238`) is already in the crash-injection family pattern.
- **Recommendation**:
  1. `tests/test_append_only_property.py` — Hypothesis strategy generates random valid `INSERT` payloads per evidence table.
  2. `tests/test_crash_recovery.py` — explicit cases: (a) kill between BEGIN and COMMIT during apply_pending (already covered); (b) kill between evidence COMMIT and runtime BEGIN in dual-write; (c) reopen DB after `*.db-wal` file truncation.
  3. **WAL hygiene between Hypothesis examples**: use `tmp_path` per `@given` example, NOT a session-scoped fixture.
- **What-would-change-it**: if `hypothesis` provides a state-machine mode that handles fault injection cleanly, merge the families. Otherwise keep split.
- **Cross-seat**: TEST-ARCH owns Hypothesis strategy design; I own only the concurrency/WAL implications.

## Q5 — Connection lifecycle
- **Disposition**: MINOR
- **Claim**: Keep the current contract: `open_evidence` / `open_runtime` return a `Connection`; caller owns lifecycle. Repos take a `Connection`. Do **not** introduce per-call open/close — opening a connection costs ~1ms and re-runs apply_pending's no-op-check on every call; that's wasted I/O and re-asks the SHA ledger to verify on every write. **Do** add a `contextlib.contextmanager` helper `writer_transaction(conn)` that yields and BEGIN IMMEDIATE / COMMIT-or-ROLLBACK around the block.
- **Evidence**: `open_db` already sets `journal_mode=WAL` (`migrations.py:209`) and `isolation_level=None` autocommit (`migrations.py:208`). The combination means BEGIN/COMMIT are explicit, which is what we want.
- **Recommendation**:
  1. Add `src/skill_harness/storage/transaction.py::writer_transaction(conn: Connection) -> Iterator[None]` — context manager.
  2. Document in storage module docstring: "Connections are long-lived; use `writer_transaction` for write batches; do not call `conn.close()` from repo code."
  3. `synchronous=FULL` cost at evidence write rate: negligible at v0.1 scale.
- **What-would-change-it**: nothing at v0.1 scale.
- **Cross-seat**: defers to SCHEMA on whether repos need transaction-scoped batching for FK enforcement.

## Q6 — Admissibility filter on read
- **Disposition**: MAJOR
- **Claim**: Filter lives in the **repo read functions** (default-on filtered), with a separate `read_*_for_audit` variant that returns ALL rows including inadmissible + confounded. Aggregation code (Track E) calls the default; audit tooling calls the audit variant. Putting the filter in raw SQL in every aggregation query is exactly the "easy to forget" failure mode — one missed clause and a confounded verdict enters aggregation. **The default must be safe; the audit must be explicit.** Reliability-wise: if a row is corrupted (CHECK violation snuck in via direct sqlite3 CLI bypass — A23's PRAGMA scope concern), the repo's `model_validate` (Pydantic strict) raises at deserialization, the aggregation aborts loudly rather than silently skipping.
- **Evidence**: `idx_verdicts_clause_adm` (`migrations/evidence/0001_initial.sql:215`) already exists for the `(clause_id, admissibility_state)` lookup.
- **Recommendation**:
  1. `repos/oracle_verdicts.py::list_admissible_verdicts(conn, clause_id) -> list[OracleVerdict]`.
  2. `repos/oracle_verdicts.py::list_all_verdicts_for_audit(conn, clause_id) -> list[OracleVerdict]`.
  3. Pydantic `OracleVerdict` model with `model_config = ConfigDict(strict=True)`.
- **What-would-change-it**: if Track E wants a single SQL aggregation query for performance, accept a `views/admissible_verdicts` SQL view materialized in evidence.db.
- **Cross-seat**: SCHEMA owns whether the view belongs in the migration; TEST-ARCH owns the test that corruption surfaces as UNMEASURED.

## Q7 — Migration sequencing across worktrees
- **Disposition**: BLOCKER
- **Claim**: This is a real and certain failure mode. Phase 2 dispatches A + B + C in parallel worktrees. Two worktrees each adding `migrations/evidence/0003_*.sql` will silently merge — `git` will not flag it (different filenames) — and `discover()` will sort glob-output alphabetically, applying both files in whatever order their full names sort to, with the SHA ledger recording both. **There is no corruption here on first apply** (both run, both ledgered). The hazard is: (a) order ambiguity — `0003_alice.sql` runs before `0003_bob.sql`, but a future operator reading the migrations directory has no way to know that order was intended; (b) re-derivation under refactor — if either migration is rebased or renumbered, the SHA ledger fires `MigrationTamperedError` on the next open.
- **Evidence**: `discover()` (`migrations.py:69-88`) sorts via `sorted(directory.glob("*.sql"))` — alphabetical on full filename. No uniqueness check on the integer version.
- **Recommendation**: Track A's exit criteria MUST include both:
  1. **Number range reservation per track**:
     - Track A: 0001-0099 (storage primitives)
     - Track B: 0100-0199 (extractor-emitted runtime tables, if any)
     - Track C: 0200-0299 (oracle / calibration writers)
     - Track D: 0300-0399 (ablation runner / cost ledger extensions)
     - Track E: 0400-0499 (aggregation views, status derivation tables)
  2. **`discover()` raises on duplicate version numbers**: `if len({m.version for m in out}) != len(out): raise BootstrapError(...)`. Catches the worktree-collision case at first open after merge — loud, immediate.
  3. Document the reservation in `migrations/README.md` (new file).
- **What-would-change-it**: if PLAN.md is amended to serialize all migration additions through `main`, the duplicate-version raise becomes belt-and-suspenders rather than load-bearing.
- **Cross-seat**: SCHEMA owns the range allocation; TEST-ARCH owns the duplicate-version test.

## Cross-talk

- **SCHEMA**: RIGHT — Will own Q1's row-shape modeling and approve Pydantic `OracleVerdict` write-model mirroring the CHECK constraints. Will own Q6's view design. Will OBSERVATION-grade Q5. WRONG — Will probably push back on Q7's range-reservation as a "process layer" concern not a schema one — but the load-bearing fix is `discover()`'s duplicate-version raise, which is schema-runner code. MISS — Q3's single-writer mechanism — SCHEMA's lens is invariants, not concurrency; likely won't flag the queue-vs-SQLite-lock conflation.
- **SECURITY**: RIGHT — Will BLOCKER Q7 for a different reason — a malicious or accidentally-duplicated migration file could be a SHA-ledger spoofing vector. WRONG — May propose `runtime.db` adopts `synchronous=FULL` for "symmetry" — that re-litigates A22 (locked). The reconciler from Q2 is the safety net. MISS — Q2's dual-DB sequencing — SECURITY tends to read this as "transaction discipline" not "filesystem boundary."
- **TEST-ARCH**: RIGHT — Will own Q4's Hypothesis strategy design and likely propose the state-machine pattern. Will own the test-shape for Q6's corruption-surfaces-as-UNMEASURED contract. WRONG — May propose folding crash-injection INTO the property test via Hypothesis's `@rule` mechanism. I'm asserting (Q4) that this is the wrong shape — shrinking fails on side-effects across rules. MISS — Q3's backpressure framing — TEST-ARCH thinks in falsifiability, not in queue overflow.

STATUS: BLOCKER-FOUND
