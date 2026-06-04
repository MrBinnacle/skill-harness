# SECURITY seat — Phase 1.5 Pre-Track-A Storage Review

**Date**: 2026-06-04
**Fire**: pre-Track-A storage review
**Seat**: SECURITY
**Subagent type**: general-purpose
**Brief**: dispositioned four fragility clusters surfaced by `audit-context-building` before Track A code lands

---

Verified. The Python docs are unambiguous: with `isolation_level=None`, the connection is in autocommit mode and Python does not issue implicit BEGIN; `with conn:` only commits/rollbacks an *explicit* transaction. No `BEGIN` was issued → `with conn:` is a no-op. M1 is real.

Now I have enough context to produce the SECURITY disposition.

---

**Scope**: adversarial input handling for storage layer, prompt-injection-adjacent surfaces, supply-chain mitigations, partition trust boundaries. **Anthropic API surface explicitly out of scope per fire prompt.**

**Default threat model for v0.1 (per `SECURITY.md` §"Threat model" + fire prompt)**: **local-trust**. Single-operator, single-host, evidence and runtime DB files live in the operator's filesystem. Out-of-scope for this fire: remote network attacker, multi-tenant DB hosting, hostile model providers replacing the SDK at runtime. In-scope: accidental developer mutation, dependency-tree compromise (passive), filesystem-adjacent attacker with the same UID as the harness process.

---

### F1 — Migration apply is not atomic; partial-DDL state widens an exploit window
- **Severity**: MAJOR
- **Cluster**: M1
- **Threat model**: Filesystem-adjacent attacker with same UID as the harness process (or root). NOT remote. Requires (a) the ability to write to `migrations/evidence/` or `migrations/runtime/` between the crash and the next `open_evidence()` call, AND (b) a prior crash that left a DDL half-applied (no `schema_migrations` row recorded). Independently exploitable by a developer-error variant: an honest dev "fixing" a half-applied migration by re-editing the SQL file, which then permanently locks the DB on the next open via `MigrationTamperedError` because the SHA recorded post-recovery no longer matches a never-recorded SHA.
- **Claim**: Because `sqlite3.connect(path, isolation_level=None)` puts the connection in autocommit mode and does not issue implicit `BEGIN`, the `with conn:` context manager at `migrations.py:103` is a no-op (it only commits/rollbacks explicit transactions). `executescript` + the subsequent `INSERT INTO schema_migrations` are therefore two independent autocommits. A crash between them leaves DDL applied with no ledger row. On the next `open_evidence()`, `apply_pending` re-runs the migration, every `CREATE TABLE` raises `sqlite3.OperationalError: table X already exists`, and the DB is bricked. There is no documented recovery path; an ad-hoc "drop tables and retry" recovery would let an attacker who controls a migration file substitute malicious DDL during the recovery window.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:103-108` — the `with conn:` block under `isolation_level=None` (line 119).
  - Python stdlib docs on `sqlite3.Connection` autocommit + `__enter__/__exit__` semantics — verified locally: `sqlite3.sqlite_version = 3.45.3`, behavior matches.
  - `migrations/evidence/0001_initial.sql:14-17` — once a partial-apply leaves `schema_migrations` extant with no row, BEFORE-DELETE triggers ALSO block "wipe and retry" recovery on the ledger itself.
- **Recommendation**: **fix-pre-Track-A**. Two-line fix: wrap the DDL+INSERT in an explicit `conn.execute("BEGIN")` / `conn.execute("COMMIT")` (or switch `open_db` to `isolation_level=""` for migration application only). Document the recovery story: "if the SHA ledger row is missing but the DDL is partly applied, delete the entire `evidence.db` file and re-run from a known-good source." (`evidence.db` is rebuildable from raw artifacts in v0.1 — there is no production data yet — so the recovery story is "blow it away.") Defer attacker-during-recovery hardening to v0.2 since v0.1 ships pre-data.
- **Cross-seat**: **RELIABILITY** primarily (crash safety + recovery). SECURITY interest is the recovery-window substitution attack, which is local-trust-bounded and therefore minor; the real argument for fixing is reliability + tamper-evidence integrity (a half-applied state silently breaks A4's "SHA-256 mismatch = abort" guarantee because the row was never written).

---

### F2 — `parents[3]` migration discovery silently degrades to empty DB under wheel install; weaponizable as a "no findings" forge
- **Severity**: BLOCKER
- **Cluster**: M2
- **Threat model**: Two layered models:
  - **(a) Local supply-chain / install-layer attacker**: any actor who can influence which copy of the `skill_harness` package is imported (PYTHONPATH manipulation, malicious wheel substitution, `pip install --user` shadow-install, editable-install path confusion, conda-env pollution). Requires write access to one of these resolution paths. Common on shared CI runners and dev hosts.
  - **(b) Honest-operator self-foot-gunning**: an operator who `pip install`s the harness into a venv expecting an installed-package workflow, then runs `skill-harness run evaluate-skill` and gets a silent empty DB report.
- **Claim**: `REPO_ROOT = Path(__file__).resolve().parents[3]` is computed from the **installed** location of `migrations.py`. Under `pip install` (wheel or sdist) the package lives at `site-packages/skill_harness/storage/migrations.py`, so `parents[3]` resolves to a directory NEAR `site-packages` that has no `migrations/` subtree. `discover()` returns `[]` without raising, `apply_pending()` returns `[]` without raising, and `open_evidence()` returns a connection to an EMPTY DB containing no tables. The next call to `INSERT INTO oracle_verdicts` fails with `OperationalError: no such table`, but a Track E aggregator that defensively wraps reads in `try/except` (a likely-future code shape) would see "0 admissible verdicts" and report `UNMEASURED` for every clause — **operationally indistinguishable from "the harness ran and found nothing concerning."** Per PRD §6 `no admissible evidence ⇒ no claim`, this is technically invariant-compliant; per PRD §19 criterion (3) "reject uncalibrated judges automatically" and the harness's own value proposition ("measure clause contribution"), silently degrading the entire output to UNMEASURED is a soundness failure that produces a forgeable clean-bill-of-health.
- **Evidence**:
  - `src/skill_harness/storage/migrations.py:24-26` — repo-root anchored to `parents[3]`.
  - `discover()` at `migrations.py:49-52` — `if not directory.exists(): return []` is the silent-no-op gate.
  - `apply_pending()` at `migrations.py:86-110` — iterates an empty list, returns `[]` without warning.
  - `open_evidence()` at `migrations.py:127-130` — returns a usable `Connection` to an empty DB.
  - No test in `tests/test_smoke.py` exercises the wheel-install path or asserts that a fresh `open_evidence()` produces non-empty tables; the smoke tests run against the in-repo path so the failure mode is invisible to CI.
  - `pyproject.toml` package layout (verified-by-context: standard `src/` layout per CLAUDE.md "Greenfield. The target stack per PRD §17 is a Python deterministic runner") — `migrations/` directory is at repo root, NOT inside the importable package.
- **Recommendation**: **fix-pre-Track-A**. Two hardening steps, both required:
  1. **Refuse to return an unusable connection**: at the end of `open_evidence()` and `open_runtime()`, assert that `schema_migrations` exists and contains ≥1 row. If not, raise a new `MigrationDiscoveryError` naming the directory that was searched. This makes the failure mode loud.
  2. **Package the migration SQL as package data**: move `migrations/{evidence,runtime}/` under `src/skill_harness/storage/migrations/` and resolve via `importlib.resources` (Python 3.9+ `files()` API). This eliminates `parents[3]` brittleness, makes the wheel installable, and removes the install-path attacker surface entirely.
  - Either step alone is insufficient: step (1) without (2) keeps the wheel install broken-but-loud; step (2) without (1) leaves a future operator who deletes a migration file with a silent fallback.
- **Cross-seat**: **RELIABILITY** (silent-degradation is the canonical reliability anti-pattern) and **TEST-ARCH** (the property "open_evidence() never returns an unusable DB" is exactly the kind of falsifiable invariant TEST-ARCH should be spec'ing and the smoke suite should be checking).

---

### F3 — `runs.completed_at` immutability trigger over-fires; not security-relevant
- **Severity**: OBSERVATION
- **Cluster**: M3
- **Threat model**: None applicable. No attacker capability gains anything from the over-strict trigger; the worst case is a legitimate writer cannot record an `error` column or a derived field on a completed run. The integrity property the trigger is trying to enforce (`completed_at` set-once) is correctly enforced; the side effect (no column on a completed `runs` row can be updated) is broader than stated intent but does not create exploit surface.
- **Claim**: SECURITY has no objection to M3. The over-strict scope might prevent future legitimate writes (e.g., setting `aborted_at` or adding a `final_state` field in v0.2), but no confidentiality, integrity, or availability property is degraded relative to a column-scoped trigger.
- **Evidence**: `migrations/evidence/0001_initial.sql:203-205` — `WHEN OLD.completed_at IS NOT NULL` fires on UPDATE of ANY column. The integrity property "no second `completed_at` write" is preserved.
- **Recommendation**: **defer-to-SCHEMA-seat**. SECURITY explicitly declines to disposition; SCHEMA owns the design intent of the `runs` table and whether the over-broad lockout is intentional or scope creep. SECURITY's only ask: if SCHEMA scopes the trigger to the `completed_at` column specifically, ensure the scoped trigger still raises on the case "`completed_at` is updated by a statement that ALSO updates another column" (a SQL technicality — SQLite column-scoped triggers fire if the column is named in the SET list, so this is naturally handled, but it should be tested).
- **Cross-seat**: **SCHEMA** owns this entirely. SECURITY position: deferred.

---

### F4 — Runtime ledger lacks append-only triggers; `current_calibration` pointer is the actual security-relevant target
- **Severity**: MAJOR
- **Cluster**: M4
- **Threat model**: **SQL-write attacker on `runtime.db`** — any actor with write access to the runtime DB file (which under the local-trust model is "same UID as harness process", i.e. accidental developer with a sqlite3 REPL, a misconfigured `chmod`, or a compromised dev-dependency that gains code execution at test time and pivots to filesystem writes). Crucially NOT a remote network attacker (out of scope per fire prompt).
- **Claim**: Three sub-findings rolled up because they share a threat model:
  1. **`current_calibration` rewrite is the real attack, and it is correctly bounded by A3.** An attacker with SQL write on `runtime.db` can `UPDATE current_calibration SET calibration_event_id = '<expired_or_fabricated_event_id>' WHERE judge_id=X AND axis=Y`. The next `oracle_verdicts` write that resolves `(judge_id, axis)` against the runtime pointer will snapshot the attacker-chosen `calibration_event_id` into the evidence row's `calibration_event_id` FK. **A3 correctly bounds this: only FUTURE verdicts are affected; past verdicts already snapshotted their `admissibility_state` at write time and the BEFORE-UPDATE triggers on `oracle_verdicts` prevent rewriting them.** The bound is real and SECURITY confirms it. However: the attacker can flip a judge from inadmissible→admissible for the next run, which propagates a calibration lie into permanent evidence rows. The lie is contained (the snapshotted FK still points at the fabricated `calibration_event_id`, which itself is in append-only `evidence.calibration_events` — so an auditor reading the evidence DB can spot the lie by checking whether the referenced calibration event was ever validly registered). This is a **detectable** attack, not a **silent** one, but only if a follow-up audit step exists.
  2. **`runtime.schema_migrations` lacks BEFORE UPDATE/DELETE triggers**, asymmetric with `evidence.schema_migrations` (which has them at `evidence/0001_initial.sql:14-17`). Concretely: an attacker who controls `runtime.db` AND a malicious migration file can forge `(migration_id, file_sha256)` rows to mask a schema modification. **The blast radius is structurally smaller than the evidence DB** because (a) the runtime DB's tables are intentionally permissive with no critical CHECK constraints, and (b) a schema modification to runtime tables cannot rewrite already-snapshotted admissibility on evidence rows. Still: the SHA-mismatch tamper-evidence (A4) is **silently weakened** on the runtime DB. A developer who reads A4 will reasonably assume the same guarantee holds on both DBs. It does not.
  3. **The asymmetry is undocumented.** PRD §17 says "SQLite. Append-only evidence model." It does not say "runtime DB has weaker tamper-evidence." `docs/COUNCIL_FINDINGS.md` A4 says "Numbered SQL files in `migrations/{evidence,runtime}/`" and "On startup, file SHA mismatch against recorded SHA aborts with `MigrationTamperedError`" — this is true (the runner's check works on both), but the **DB-side defense** (triggers preventing forged records via direct SQL write) exists on evidence and is absent on runtime.
- **Evidence**:
  - `migrations/runtime/0001_initial.sql:9-14` — `schema_migrations` table with NO triggers.
  - `migrations/evidence/0001_initial.sql:14-17` — same table with BEFORE UPDATE/DELETE triggers.
  - `migrations/runtime/0001_initial.sql:26-36` — `current_calibration` table is the mutable pointer A3 names.
  - `docs/COUNCIL_FINDINGS.md` §A3 — "Never recomputed from 'current' calibration on read. The `current_calibration` pointer in runtime.db is *only* used at write time to resolve which calibration_event to snapshot." Confirms the A3 bound and identifies `current_calibration` as the trust-pivot target.
  - `docs/COUNCIL_FINDINGS.md` §A4 — does not mention the asymmetry.
- **Recommendation**: **fix-pre-Track-A** for the symmetry; **log-as-OBSERVED + document** for the `current_calibration` audit story.
  - **(symmetry fix)**: add BEFORE UPDATE/DELETE triggers to `runtime.schema_migrations`. This is consistent with A4's intent (DB-layer tamper-evidence), costs one line per trigger, and prevents the "silent weaker guarantee on runtime DB" surprise.
  - **(documentation)**: add an explicit clause to `docs/COUNCIL_FINDINGS.md` §A3 stating: "A3's bound — `current_calibration` rewrites affect only FUTURE verdicts — is the load-bearing guarantee. Detection of a lying `current_calibration` requires an auditor to verify that every `oracle_verdicts.calibration_event_id` resolves to a `calibration_events` row whose `validated_at` ≤ verdict's `written_at` AND whose `expires_at` > verdict's `written_at`. v0.2 ships a `skill audit` CLI command implementing this check." File the v0.2 audit-command requirement.
  - **DO NOT** add BEFORE UPDATE triggers to `current_calibration`, `run_progress`, `run_budget`, or `cost_ledger`. These are intentionally mutable per A2 and any "hardening" that makes them immutable breaks the runtime DB's design. The SCHEMA seat should reject any proposal of this shape; SECURITY flags it as the obvious wrong fix.
- **Cross-seat**: **SCHEMA** (partition design intent + whether `runtime.schema_migrations` symmetry is a SCHEMA-owned decision). **TEST-ARCH** (the cross-DB audit invariant in v0.2 — "every verdict's calibration_event resolves to a valid event at write_at" — is a falsifiable spec they should own).

---

### F5 (addendum) — Trust partition and tamper-evidence threat model must be written down; SECURITY.md is the right home
- **Severity**: MAJOR
- **Cluster**: cross-cutting (M2, M4, and undocumented threat model)
- **Threat model**: Documentation-debt finding. The threat model named here is the one already implicit in the design — local-trust, single-operator, single-host, evidence integrity ≫ runtime integrity. The vulnerability is that the design is correct but not legible, and a future contributor (or a future Phase-2 track) will silently violate it.
- **Claim**: Three documentation gaps that together constitute a load-bearing-but-implicit-only-contract:
  1. **Trust partition between evidence.db and runtime.db is not specified.** PRD §17 calls out "SQLite. Append-only evidence model." but does not state that runtime.db is intentionally outside the append-only envelope, why, and what guarantees survive a runtime.db compromise. A Track A or Track D developer reading PRD §17 + COUNCIL_FINDINGS A2 today could reasonably propose "harden runtime.db with triggers for symmetry" — which is the wrong direction (per F4 last paragraph).
  2. **Tamper-evidence threat model is undocumented.** The audit context flags: "SHA ledger does NOT survive direct DB-file replacement at filesystem layer." This is true (an attacker with `rm evidence.db && cp attacker_evidence.db evidence.db` defeats SHA ledger entirely; the SHA ledger checks file vs. recorded-in-DB, but if the whole DB is replaced, the "recorded" baseline is also attacker-supplied). The current `SECURITY.md` threat model (line 41-46) lists "Evidence tampering — addressed by append-only triggers + SHA-256 migration ledger" without naming the filesystem-substitution boundary. This is misleading: the triggers and SHA ledger defend against in-process SQL-injection-style mutation, not against file-replacement.
  3. **PRAGMA scoping is connection-local.** `migrations.py:119-123` sets `foreign_keys = ON`, `journal_mode = WAL`, `synchronous = NORMAL`, `busy_timeout = 5000` per connection. `journal_mode = WAL` is **persistent** at the DB-file level (SQLite docs: "WAL mode... is persistent across connections") so this one survives. The other three — including `foreign_keys = ON` — are **connection-scoped**. Any future caller that opens a `sqlite3.Connection` bypassing `open_db()` (e.g., a Track A repository that does `sqlite3.connect(path)` directly, or a test fixture, or a future audit tool) silently loses FK enforcement.
- **Evidence**:
  - `SECURITY.md:41-46` — informal threat model omits filesystem-substitution and runtime/evidence asymmetry.
  - `docs/COUNCIL_FINDINGS.md` §A1, A2, A3, A4 — do not state the partition's defensive boundaries.
  - `PRD.md` §17 — single-line architecture statement, does not name the partition.
  - SQLite docs (verified by SECURITY against the project's own canonical citations in COUNCIL_FINDINGS §"Verified external citations": `https://www.sqlite.org/pragma.html`) — `PRAGMA foreign_keys` is connection-scoped, `PRAGMA journal_mode=WAL` is persistent.
  - `migrations.py:113-124` — `open_db()` is the only sanctioned entry; nothing prevents a future writer from bypassing it.
- **Recommendation**: **fix-pre-Track-A** (documentation-only; no code change required). Add to `SECURITY.md` under "Threat model (informal)":
  1. **Trust partition clause**: "`evidence.db` is append-only, audited, and load-bearing. `runtime.db` is mutable by design (in-flight progress, current calibration pointer, cost ledger). Compromise of `runtime.db` affects only FUTURE evidence rows via `current_calibration` snapshot at verdict write time; past evidence rows are bounded by A3. Symmetry between the two databases is NOT a design goal."
  2. **Filesystem substitution boundary**: "The append-only triggers and SHA-256 migration ledger defend against in-process unauthorized writes (developer error, SQL injection, library bug). They do NOT defend against an attacker who replaces the entire `evidence.db` file at the filesystem layer. v0.1 threat model assumes filesystem integrity (local-trust)."
  3. **PRAGMA scope clause**: "Connections to evidence.db and runtime.db MUST go through `skill_harness.storage.migrations.open_db()`. Direct `sqlite3.connect()` bypasses connection-scoped pragmas including `foreign_keys = ON`. Repository APIs in `src/skill_harness/storage/` enforce this in code review."
  - Mirror items (1) and (2) as a short "Trust partition" subsection in `docs/COUNCIL_FINDINGS.md` §A4 (where the tamper-evidence story lives) so the architectural decision log is self-contained.
- **Cross-seat**: **SCHEMA** owns the partition design and should ratify the documentation. **TEST-ARCH** should add a regression test that asserts `open_db()`-opened connections have `PRAGMA foreign_keys = 1` (one-line test, makes the scope-bug detectable if any future change weakens the helper).

---

## Cross-talk block

### TEST-ARCH
- **RIGHT**: I expect TEST-ARCH to surface M2 as a falsifiability failure — specifically that `tests/test_smoke.py` does not exercise the wheel-install path, so the property "fresh open_evidence() yields a usable DB" has no falsifying-case test. They'll likely propose a test fixture that runs `pip install -e .` into a tmp-venv and asserts non-empty `schema_migrations`. This is the right shape and aligns with my F2 recommendation.
- **WRONG**: I expect TEST-ARCH to over-call M3 as a falsifiability problem because the trigger's scope ("on UPDATE of any column when completed_at is set") is broader than the spec ("completed_at is immutable once set") and the gap is testable. They are correct that it's testable — but the over-broadness is design-intent territory (SCHEMA owns), not falsifiability territory. Calling it a TEST-ARCH MAJOR overweights process over substance.
- **MISS**: TEST-ARCH's lens is structurally weak at runtime/install-time threat models. They will likely treat M2 as a unit-test gap rather than a soundness-of-output forge. The fact that a silent empty DB produces an indistinguishable-from-clean-eval report is a semantic property the test seat may not name without prompting from SECURITY.

### SCHEMA
- **RIGHT**: I expect SCHEMA to fully own M3 (it is theirs to disposition) and to disposition it as a scope-creep fix — either tighten the trigger to column-scoped or adopt the over-broad version intentionally. Either is defensible; they should pick one and document the reasoning. They will also correctly identify F4's "add triggers to `runtime.schema_migrations`" as a symmetry fix consistent with their A2 design.
- **WRONG**: I expect SCHEMA may over-propose hardening on `runtime.db` tables generally — particularly tempted to add triggers on `current_calibration` or `cost_ledger` "for safety." This breaks the runtime DB's design (intentionally mutable per A2). My F4 final paragraph names this trap; if SCHEMA goes there, the council needs to push back.
- **MISS**: SCHEMA's lens is structurally weak at the partition's threat-model implications. They specified the partition correctly but may not have internalized that the partition is itself a security boundary that needs to be named in `SECURITY.md`. They may see F5 as "documentation polish" rather than "load-bearing-but-implicit contract that will be silently violated."

### RELIABILITY
- **RIGHT**: I expect RELIABILITY to fully own M1 as their primary finding — atomicity gap under autocommit, crash leaving partial-DDL state, no recovery story. They will likely propose the same explicit-BEGIN fix I named in F1, and they may go further and propose `PRAGMA journal_mode = WAL` ordering checks (WAL is set after `connect()`, which under autocommit is itself nontrivial — but the pragma is persistent on first WAL open so it works out). They will also catch the F2 silent-empty-DB story as a reliability anti-pattern even if they don't name the security-forge angle.
- **WRONG**: I expect RELIABILITY to over-call F4's runtime symmetry as a reliability concern rather than a tamper-evidence concern. The runtime DB's lack of triggers does not affect crash safety or recovery; it affects defense-in-depth against in-process unauthorized writes. If RELIABILITY proposes adding `journal_mode = WAL` symmetry between the two DBs as a reliability fix that's reasonable; if they propose adding append-only triggers to runtime tables as a reliability fix, that's the same wrong direction I flagged for SCHEMA.
- **MISS**: RELIABILITY's lens is structurally weak at attacker-during-recovery-window threats. The F1 recovery story — "blow away `evidence.db` and re-run" — is a clean reliability solution that incidentally widens an attack window if a malicious migration file is present. RELIABILITY will rightly call this out-of-scope for v0.1 (pre-data); SECURITY agrees. But the lens of "recovery as exploit window" is a SECURITY-native frame that RELIABILITY may not surface.

---

**Summary by cluster**:
- **M1** → F1 MAJOR (atomicity; primarily reliability, security tail risk in recovery window)
- **M2** → F2 BLOCKER (silent empty DB is forgeable as a clean-eval; install-path attacker surface)
- **M3** → F3 OBSERVATION (SECURITY defers to SCHEMA)
- **M4** → F4 MAJOR (runtime ledger symmetry + `current_calibration` audit story bounded by A3)
- **Cross-cutting** → F5 MAJOR (trust partition + tamper-evidence boundary + PRAGMA scope must be documented in SECURITY.md and COUNCIL_FINDINGS §A4)

STATUS: BLOCKER-FOUND
