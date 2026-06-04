# SCHEMA seat — Phase 1.5 Pre-Track-A Storage Review

**Date**: 2026-06-04
**Fire**: pre-Track-A storage review
**Seat**: SCHEMA
**Subagent type**: general-purpose
**Brief**: dispositioned four fragility clusters surfaced by `audit-context-building` before Track A code lands

---

I have authoritative confirmation from the Python sqlite3 docs and SQLite official docs (verified URLs in citations below). Now I have everything needed to disposition all four clusters with verified citations.

---

## F1 — Migration apply is non-atomic; ledger can lie post-crash

- **Severity**: BLOCKER
- **Cluster**: M1
- **Claim**: With `isolation_level=None` (autocommit), `with conn:` is a no-op and `executescript` performs no implicit transaction wrap; the DDL in `m.sql` and the subsequent `INSERT INTO schema_migrations` are NOT atomic, so a crash between line 104 and line 105-108 leaves DDL committed but unledgered — which silently breaks the SCHEMA-F5 (A4) tamper-evidence promise on next open.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:103-108` (the `with conn:` + `executescript` + separate `execute(INSERT)` block) combined with line 119 (`isolation_level=None`).
  - Python sqlite3 docs (verified): "If there is no open transaction upon leaving the body of the `with` statement, or if `autocommit` is `True`, the context manager does nothing" and on `executescript`: "No other implicit transaction control is performed; any transaction control must be added to *sql_script*." (https://docs.python.org/3/library/sqlite3.html)
  - SQLite docs (verified): DDL and DML may be combined in a single explicit `BEGIN ... COMMIT` (https://www.sqlite.org/lang_transaction.html).
  - Failure mode is doubly compounded: on retry, `discover()` re-feeds the same script; `executescript` will hit "table already exists" on the first `CREATE TABLE schema_migrations`, terminating apply without recovery. The DB is now in a state that neither A4 nor SCHEMA-F5 can describe: schema half-applied, ledger empty, runner stuck.
- **Recommendation**: **fix-pre-Track-A**. The A4 tamper-evidence invariant requires that EITHER "DDL applied + ledger row present" OR "neither applied" — there is no recovery story for the third state, and Track A code will start writing evidence rows on top of this fragile floor. The fix is to wrap the apply in an explicit `BEGIN IMMEDIATE` / `INSERT` / `COMMIT` in Python (not via `with conn:`), AND to append the `INSERT INTO schema_migrations (...)` as the final statement of each migration's `.sql` file so a single `executescript` carries both. Both belt and suspenders, because executescript's own atomicity guarantees are weak under autocommit. The migration_id+sha256 still come from Python (cannot be in the SQL file at author time without templating), so the right shape is: the runner programmatically appends `BEGIN IMMEDIATE; <script>; INSERT INTO schema_migrations VALUES (?, ?); COMMIT;` as a single `executescript` call with the INSERT values bound via string concatenation of the migration_id literal and sha256 literal (both controlled by the runner, never user input — safe). Alternatively, do not call `executescript` at all: parse statements and run them inside an explicit BEGIN/COMMIT via `executemany`/`execute`. The latter is cleaner and is the actual fix I recommend.
- **Cross-seat**: RELIABILITY's lens is dominant here (crash-mid-apply is exactly their beat). I expect them to also call this BLOCKER and to additionally surface a recovery-mode question (manual `--repair` / `--mark-applied` CLI flag) that I'd defer to v0.2. SECURITY's lens secondarily applies: an attacker with FS access could exploit the crash window to leave un-ledgered DDL and then mutate it without tripping SCHEMA-F5.

## F2 — Package-path coupling silently empties migrations under wheel install

- **Severity**: MAJOR
- **Cluster**: M2
- **Claim**: `REPO_ROOT = Path(__file__).resolve().parents[3]` hardcodes a layout that holds under editable install but breaks under any non-editable install (wheel, sdist, pipx, frozen binary); `discover()` then returns `[]`, `apply_pending` is a no-op, and `open_evidence()` hands back an empty DB with no `skills`/`runs`/`oracle_verdicts` tables — and crucially WITHOUT raising. First evidence write fails with `no such table`, which is exactly the kind of error that gets blamed on the writer rather than the runner.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:24-26` (the `parents[3]` constants) and `:51-52` (`if not directory.exists(): return []`).
  - `:127-130` (`open_evidence` returns conn unconditionally after `apply_pending`).
  - No assertion anywhere that the canonical first migration has been applied; nothing checks that `schema_migrations` is populated after open.
- **Recommendation**: **fix-pre-Track-A** (minimal version) + **defer-to-v0.2** (full fix).
  - Pre-Track-A minimum: `open_evidence` and `open_runtime` MUST assert post-apply that at least one row exists in `schema_migrations` AND that the expected canonical table set (e.g., `oracle_verdicts` for evidence, `run_progress` for runtime) was created. Silent-empty-DB is an invariant violation on day one; it must raise `MigrationsNotAppliedError` not return a usable-looking connection. This is a one-screen change and removes the entire class of "wheel install ships an empty DB" failures regardless of how `REPO_ROOT` is resolved.
  - v0.2 proper fix: ship migrations as package data via `importlib.resources` (`importlib.resources.files("skill_harness").joinpath("migrations/evidence")`) and stop relying on filesystem layout. This is the standard Python answer and works under every install mode. Defer the migration-to-package-data refactor only because the assertion-on-open hardening makes the failure loud immediately and unblocks Track A.
- **Cross-seat**: RELIABILITY's "silent failure is the worst failure" beat aligns. SECURITY may surface the related concern that a partial install (or a deliberately stripped wheel) is a tamper-evident gap — and they're right that A4's SHA ledger means nothing if the DB starts empty. TEST-ARCH will likely want a falsifying-case test that proves "no migrations dir ⇒ raise, not silent" — fully agree, add it.

## F3 — `runs_completed_at_once` makes the entire row immutable post-completion; intent was column-level

- **Severity**: MINOR
- **Cluster**: M3
- **Claim**: **The authoring intent was "`completed_at` column immutable once set" (column-level)**, but the implemented trigger semantics are "ANY column on this row is immutable once `completed_at` is set" (row-level). The naming and comment confirm column-level intent; the implementation is over-strict.
- **Evidence**:
  - `migrations/evidence/0001_initial.sql:202` comment: "completed_at is the sole mutable field (set once on completion)" — this asserts `completed_at` is the **only** mutable column on `runs`, which is consistent with column-level scope of the once-only constraint.
  - Trigger name `runs_completed_at_once` — names the single field.
  - The error message `'runs.completed_at is immutable once set'` — names the single field.
  - But the trigger body `WHEN OLD.completed_at IS NOT NULL BEGIN SELECT RAISE(ABORT, ...) END` fires on UPDATE of any column whenever `completed_at` is non-NULL. Row-level scope.
  - The test `test_runs_completed_at_is_set_once` (`tests/test_smoke.py:75-92`) exercises only the column-level case (re-setting `completed_at`), so the over-strictness is undetected by current tests.
- **State of intent** (load-bearing answer per the prompt): **Intent is column-immutable, not row-immutable.** This is consistent with the data model — `runs` is the immutable envelope, but the design needs the freedom to set `completed_at` exactly once and otherwise reject mutations to the columns whose values were frozen at run-start (`run_id`, `skill_id`, `run_kind`, `config_json`, `started_at`). The current trigger does enforce that, but it ALSO blocks future legitimate column additions (e.g., a `final_summary_hash` field added in a future migration that needs to be set after completion). The trigger is doing too much.
- **Recommendation**: **fix-pre-Track-A**. Replace the single row-level trigger with the correct column-level enforcement set:
  ```sql
  CREATE TRIGGER runs_completed_at_set_once BEFORE UPDATE OF completed_at ON runs
      WHEN OLD.completed_at IS NOT NULL
      BEGIN SELECT RAISE(ABORT, 'runs.completed_at is immutable once set'); END;
  CREATE TRIGGER runs_immutable_columns BEFORE UPDATE OF run_id, skill_id, run_kind, config_json, started_at ON runs
      BEGIN SELECT RAISE(ABORT, 'append_only_violation: runs immutable columns'); END;
  ```
  Two triggers, each scoped to the column set they actually govern. `BEFORE UPDATE OF <col_list>` is exactly the SQLite primitive for this. Then extend `test_runs_completed_at_is_set_once` into a pair of tests: one that proves re-setting `completed_at` aborts (existing), one that proves UPDATEing an unrelated nullable column (e.g., a future-added column or a hypothetical second one) is allowed after completion. The second test cannot be written cleanly today because `runs` has no other nullable mutable column — this is a hint that the row-level trigger is currently undetectable as a bug. Fix the trigger now; add the second test when a column lands that exercises it.
- **Cross-seat**: TEST-ARCH owns the falsifiability angle: they will likely call this `UNSPECIFIED` (the spec never said "row-immutable" vs "column-immutable" explicitly, so behavior is whatever the trigger says it is). I disagree with treating it as unspecified — the comment + name + error message constitute a textual spec, and the trigger contradicts that spec. RELIABILITY may under-call this as cosmetic; it is not — it forecloses future schema evolution.

## F4 — Runtime DB lacks schema_migrations triggers: INTENTIONAL per trust-partition; must be PRD-anchored

- **Severity**: OBSERVATION (with a doc-anchoring action)
- **Cluster**: M4
- **Claim**: **The omission of append-only triggers on `runtime.schema_migrations` is intentional and correct per the A1/A2 partition** — runtime.db is by definition the mutable half of the two-DB design, and applying evidence-grade append-only triggers to it would contradict that partition. **However**, the trust-boundary needs to be specified more sharply: even though `runtime` is mutable, the `schema_migrations` ledger in it is what feeds the A4 SHA-256 tamper-evidence check on runtime migrations. A mutable ledger trivially defeats tamper-evidence on the runtime side.
- **Evidence**:
  - `migrations/runtime/0001_initial.sql:9-14` — `schema_migrations` table defined, zero triggers.
  - `migrations/evidence/0001_initial.sql:8-17` — same table, `_no_update` + `_no_delete` triggers attached.
  - `migrations/runtime/0001_initial.sql:1-5` header comment: "This DB carries explicitly MUTABLE state: ... Append-only invariants do NOT apply here."
  - But `migrations.py:71-83` (`applied_records`) reads from `schema_migrations` on both DBs and the SHA-256 tamper check at `:95-101` fires on both DBs identically. The tamper-evidence claim therefore applies equally to runtime, despite runtime being declared mutable.
- **State of intent** (load-bearing answer per the prompt): **Trust-partition intentional, not oversight** — the partition declares that runtime is the mutable side and most tables there genuinely should accept UPDATE/DELETE. The `schema_migrations` table is a special case: its rows happen to be append-only by NATURE (you don't un-apply a migration; you write a new migration that reverses it), but the design declined to enforce that via trigger because the partition is supposed to be uniform. This is the correct call structurally, BUT it leaves a documentation gap: A4 (schema migration SHA-256 tamper-evidence) is now asymmetrically strong on evidence and weak on runtime.
- **Recommendation**: **accept-as-intentional** for the trigger asymmetry itself, paired with a **fix-pre-Track-A** doc anchor: PRD §17 (or the COUNCIL_FINDINGS A4 entry) must explicitly note that A4's tamper-evidence guarantee on `runtime.schema_migrations` is detection-only at next-open, not enforcement-at-write — and that the trust model assumes the runtime DB file is mutable by the operator. Anyone reading the schema today would reasonably assume the partition is the only reason for the asymmetry; that's not the whole story. Adding one explicit sentence to A4 closes the gap without changing any code.

  Defer to v0.2: a separate decision on whether to add the two triggers on runtime.schema_migrations only (not on the rest of runtime). The argument for adding them is that nothing in the system legitimately rewrites migration ledger rows, and the trust-partition is about run state and budget bookkeeping, not the ledger. The argument against is uniformity. I lean toward adding them in v0.2 — the partition is conceptually about data, not about meta-schema — but pre-Track-A this is a doc question, not a code question.
- **Cross-seat**: SECURITY will likely call this MAJOR or even BLOCKER because their threat model assumes the runtime DB is reachable by less-trusted code paths (CLI ops, recovery scripts) that legitimately mutate other runtime tables and could collaterally touch the ledger. I think SECURITY will be RIGHT that this is a real attack surface and WRONG that it requires a pre-Track-A code change — the doc anchor + a v0.2 decision is the right pacing. RELIABILITY likely won't surface this at all; their lens is crash safety, not adversarial schema mutation, and the runtime ledger crash-recovery story is identical to the evidence one (covered under F1).

---

## Cross-talk block

### TEST-ARCH (falsifiability, vacuity, status state machine)

- **RIGHT**: I expect TEST-ARCH to surface that the `test_runs_completed_at_is_set_once` test name is ambiguous, only exercises the column case, and does not actually falsify the row-immutable over-strictness — i.e., the trigger's actual contract is currently UNSPECIFIED and the test does not distinguish column-level from row-level enforcement. That's correct and pairs with my F3.
- **WRONG**: I expect TEST-ARCH to argue that F4 should be UNMEASURED until a falsifying case exists ("show me the attack that mutates runtime.schema_migrations and I'll call it a finding"). That's the wrong frame here — F4 is a documentation contract question, not a measurement question. The disposition lives in PRD §17 / A4 wording, not in a frozen case.
- **MISS**: TEST-ARCH's lens is structurally weak at seeing operational consequences of correctness gaps that don't manifest as test failures. F1's "ledger lies post-crash" is detectable only by crashing the process and re-opening — not naturally a falsifying-case shape. They may under-rate F1 because it doesn't fit the clause-ablation model of evidence.

### RELIABILITY (crash safety, recovery, single-writer, retry, idempotency)

- **RIGHT**: I expect RELIABILITY to call F1 BLOCKER on essentially identical grounds — non-atomic apply leaves an unrecoverable state — and to additionally propose a `--repair` or `--reconcile-ledger` operational tool. They'll also surface that `apply_pending` has no rollback path when `executescript` fails partway through a multi-statement script. Both correct; I'd accept the rollback observation as a sub-finding under F1.
- **WRONG**: I expect RELIABILITY to over-call F2 as BLOCKER on the strength of "silent failures are crashes you can't debug." MAJOR is correct; BLOCKER overstates because the failure mode (empty DB) manifests on the very first evidence write with a loud `no such table` — it's not a silent-corruption failure mode, it's a delayed-loud failure mode. The fix-pre-Track-A assertion shrinks the delay to open-time, which is the right size of fix.
- **MISS**: RELIABILITY's lens is structurally weak at seeing schema-evolution consequences of over-strict triggers. F3's row-immutable trigger does not affect crash safety, single-writer correctness, or recovery — so they'll likely call it MINOR or OBSERVATION and move on. They may miss that the trigger forecloses a class of legitimate future migrations.

### SECURITY (attacker model, adversarial input, tamper-evidence)

- **RIGHT**: I expect SECURITY to surface F1 as a tamper-evidence integrity gap — "the A4 ledger can be in a state that is neither valid nor invalid" is exactly the shape of finding that breaks adversarial reasoning about the ledger. They'll likely also raise F4 as a real attack surface ("an attacker with SQL write access to runtime.db can rewrite migration history and the runner will accept the rewritten state on next open as the new ground truth"). Both correct; F4 in particular needs SECURITY's voice on the record.
- **WRONG**: I expect SECURITY to extend F2 into a supply-chain tampering scenario ("attacker ships a wheel without migrations dir; runner silently runs against an empty DB; first write fails noisily but evidence was never going to be written in the first place; attack succeeds at causing the evaluation to produce false UNMEASURED outcomes"). That's a real concern but it's the same attack as "attacker delivers a broken install" and the mitigation is the same as F2's pre-Track-A fix — assert-non-empty-on-open. They may over-call this as a separate security finding when it collapses into F2.
- **MISS**: SECURITY's lens is structurally weak at seeing benign schema-evolution and operator-ergonomics consequences. F3 (over-strict trigger forecloses legitimate future column additions) is not adversarial and they'll likely skip it entirely, or worse, argue the over-strictness is a feature ("more immutability is better"). The right disposition is column-level enforcement, not maximum lockdown.

STATUS: BLOCKER-FOUND
