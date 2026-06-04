# TEST-ARCH seat — Phase 1.5 Pre-Track-A Storage Review

**Date**: 2026-06-04
**Fire**: pre-Track-A storage review
**Seat**: TEST-ARCH
**Subagent type**: Plan
**Brief**: dispositioned four fragility clusters surfaced by `audit-context-building` before Track A code lands

---

Scope per `.claude/skills/dev-team-council/SKILL.md`: falsifiability gate, vacuity detection, confound symmetry, clause status state machine. Owns PRD §3.4, §7, §8, §11, §15, §20. I read the four cited artifacts plus `tests/test_smoke.py`, `tests/conftest.py`, `docs/COUNCIL_FINDINGS.md`, `PLAN.md`, and the relevant PRD sections.

---

### F1 — M1: Crash-mid-migration leaves DB in a state no test can reach via fixtures

- **Severity**: MAJOR
- **Cluster**: M1
- **Claim**: With `isolation_level=None` and `with conn: conn.executescript(m.sql); conn.execute(INSERT schema_migrations…)`, the DDL block and the ledger INSERT are NOT a single atomic transaction; a process kill between line 104 and line 105-108 leaves DDL applied but unrecorded, so re-open raises a NON-`MigrationTamperedError` `OperationalError` ("table … already exists") from `executescript` on retry — a third failure mode not asserted by any current test.
- **Evidence**: `src/skill_harness/storage/migrations.py:103-108` (the `with conn:` block); line 119 `isolation_level=None`; CPython sqlite3 docs (`with conn` is a transaction context **only** outside autocommit). `tests/conftest.py:14-21` builds each DB on `tmp_path` from scratch — no fixture covers "stale half-applied evidence.db on next open." `tests/test_smoke.py` has zero crash-recovery test.
- **Recommendation**: **fix-pre-Track-A** — Track A's Hypothesis property "∀ valid INSERT, ∄ subsequent UPDATE/DELETE that succeeds" (PLAN §TRACK A exit criteria) assumes a known-state DB; a half-applied DB silently violates this precondition and the property test will produce false negatives or `OperationalError` flakes. The fix is small and bounded (explicit `BEGIN IMMEDIATE` / `COMMIT` around the executescript + ledger INSERT, or drop `isolation_level=None`); doing it pre-Track-A protects every downstream property-based test from a confound.
- **Cross-seat**: RELIABILITY owns this from the crash-safety angle. I expect them to call it BLOCKER; from a test-architecture lens I call it MAJOR because the testability damage (fixtures never reach this state) is real but downstream — single-developer v0.1 has low base rate of `kill -9` mid-migration. RELIABILITY's higher severity is defensible; I will not contest a BLOCKER upgrade.

---

### F2 — M2: Silent zero-migration mode under wheel install is the canonical "test passes; production broken" vacuity hazard

- **Severity**: BLOCKER
- **Cluster**: M2
- **Claim**: `discover()` early-returns `[]` on missing migrations dir (line 51-52); `apply_pending([])` is a no-op; `open_evidence()` returns a connection to an empty DB and raises nothing — so under wheel install (`parents[3]` no longer points at repo root) the entire smoke test suite would pass in editable-install dev mode while production install silently has zero schema, with the first signal being a downstream `no such table` from `repository` writes. This is the exact vacuity pattern PRD §7 names: a test ("DB opened OK") whose passing carries no information about the property the test purports to verify.
- **Evidence**: `src/skill_harness/storage/migrations.py:24-26` (`parents[3]` hard-coded depth); `migrations.py:49-52` (silent empty return on missing dir); `tests/conftest.py:11` imports `open_evidence` from package; `tests/test_smoke.py:26-44` `test_evidence_db_creates_tables` runs under editable install only — there is no test that calls `open_evidence()` from a wheel-installed environment, and there is no test that asserts `discover()` raises (or even warns) on a missing migrations dir. The current smoke `test_migration_discover_empty_dir` (line 22) *passes* on the silent-empty case — which is the inverted invariant.
- **Recommendation**: **fix-pre-Track-A** — two compounding reasons make this a hard block: (1) it falsifies the PRD §7 vacuity discipline at the bootstrap layer (we ship a "test" that passes regardless of whether migrations exist), (2) Track A's property-based append-only tests will produce VACUOUSLY-PASSING results on a zero-table DB (∀ x ∈ ∅, P(x) is trivially true). Fix: package migrations as `importlib.resources` data inside `src/skill_harness/migrations/` (or equivalent), make `discover()` raise on empty/missing, and invert `test_migration_discover_empty_dir` to assert the bootstrap can't silently come up empty.
- **Cross-seat**: RELIABILITY shares this concern from the observability angle (no signal at open time). I expect strong agreement. SECURITY may also surface it as a supply-chain-integrity concern (an attacker who removes the migrations dir gets a working empty DB). My TEST-ARCH framing is the strongest single lens: this is textbook vacuity-by-empty-quantifier.

---

### F3 — M3: `runs_completed_at_once` trigger is "tested" but the spec it tests against is not written down

- **Severity**: MAJOR
- **Cluster**: M3
- **Claim**: `tests/test_smoke.py:75-92` (`test_runs_completed_at_is_set_once`) asserts that a second UPDATE setting `completed_at` aborts — but neither PRD nor `COUNCIL_FINDINGS.md §A1` states whether the intended invariant is **column-immutable-once-set** (only `completed_at` mutations after set are forbidden) or **row-immutable-post-completion** (any UPDATE after `completed_at` is set is forbidden). The trigger at `migrations/evidence/0001_initial.sql:203-205` implements the latter (no `WHEN NEW.completed_at IS DISTINCT FROM OLD.completed_at` guard); the test cannot distinguish the two. This is a PRD §7 vacuity-of-spec hazard: a passing test that does not falsify either interpretation.
- **Evidence**: PRD has no `runs.completed_at` section that names the invariant. `COUNCIL_FINDINGS.md:19` says "Runs has a single-shot `completed_at` trigger" — ambiguous between the two readings. `migrations/evidence/0001_initial.sql:202` comment is `"runs.completed_at is the sole mutable field (set once on completion)"`, which implies COLUMN-immutable. The trigger at line 203-205 fires on `WHEN OLD.completed_at IS NOT NULL` regardless of which column NEW changes — implementing ROW-immutable. **The implementation contradicts its own comment.** `test_runs_completed_at_is_set_once` does not catch this because it only tries to mutate the same column.
- **Recommendation**: **fix-pre-Track-A** — write the spec down BEFORE Track A binds repositories to it. Two concrete moves: (1) PRD §17 or `COUNCIL_FINDINGS.md §A1` records the chosen semantic in one sentence, (2) add a smoke test that falsifies the loser — if column-immutable is chosen, add a test `update_runs_set_other_column_after_completion_succeeds`; if row-immutable, rename trigger to `runs_no_update_after_completion` and add a test that catches the comment contradiction. Until the spec is written, Track E's PASSED/FAILED/CONFOUNDED state machine (PRD §15) cannot safely set post-completion annotations because nobody knows whether the trigger will block them.
- **Cross-seat**: SCHEMA owns the schema-semantic disposition. I expect SCHEMA to land on column-immutable (less restrictive, matches comment) and recommend a guard column. I agree. SECURITY's lens is structurally weaker here — this is a spec-clarity issue, not an attacker-input issue.

---

### F4 — M4: "Runtime ledger is append-only" is not specified anywhere, so the trigger asymmetry is neither right nor wrong yet — but it is UNTESTABLE

- **Severity**: MAJOR
- **Cluster**: M4
- **Claim**: `migrations/runtime/0001_initial.sql:9-14` (`schema_migrations`) carries NO `BEFORE UPDATE` / `BEFORE DELETE` triggers; `migrations/evidence/0001_initial.sql:14-17` does. The PRD does not specify whether the runtime DB's migration ledger is intended to be append-only, mutable, or "trust the application." `COUNCIL_FINDINGS.md §A4` describes "append-only `schema_migrations`" without partitioning evidence vs runtime — implying both, but not stating it. Per PRD §7 / §20, an unspecified invariant is non-falsifiable: there is no test you can write that distinguishes "intentional (trust-boundary partition)" from "oversight (forgot the triggers)."
- **Evidence**: `migrations/runtime/0001_initial.sql:9-14` is six lines, zero triggers; the COMMENT at line 4-5 says "Append-only invariants do NOT apply here" — but that comment is about *operational* tables (run_progress, current_calibration, etc.), and `schema_migrations` is a *meta* table on which the SHA-256 tamper-evidence (§A4) depends. `apply_pending()` at `migrations.py:97-101` raises `MigrationTamperedError` ONLY when the FILE SHA differs from the RECORDED SHA — so if an attacker can `UPDATE runtime.db.schema_migrations SET file_sha256='<new>'`, the tamper check is silently defeated for the runtime DB. No test asserts this is OK; no test asserts it's not OK.
- **Recommendation**: **fix-pre-Track-A** — pick a discipline and write it down. The principled choice from a TEST-ARCH lens is: `schema_migrations` is a META table, not a DOMAIN table; its append-only status is independent of the evidence-vs-runtime partition. Add the same two triggers to runtime's `schema_migrations` (4 lines of SQL), then add a smoke test `test_runtime_schema_migrations_append_only` mirroring `test_evidence_append_only_skills`. This eliminates an entire class of unspecified-invariant findings before Track A locks the runtime repository contracts.
- **Cross-seat**: SECURITY will likely call this BLOCKER and frame it as a tamper-evidence threat. From my lens it's MAJOR because the immediate exploit (SQL write access to runtime.db) requires already-elevated capability. SCHEMA will likely agree with the META-vs-DOMAIN framing. RELIABILITY's lens is structurally weaker here. If SECURITY upgrades to BLOCKER on attacker-model grounds, I do not contest.

---

## Cross-talk block

### SCHEMA
- **RIGHT**: SCHEMA will catch F3 immediately and disposition it as column-vs-row-immutable; they will likely propose `WHEN OLD.completed_at IS NOT NULL AND NEW.completed_at IS NOT OLD.completed_at` or a deletion of the trigger in favor of a generated-column / CHECK pattern. I agree column-immutable is the right reading because §A17's UNMEASURED sub-reasons may eventually want a post-completion annotation column.
- **WRONG**: SCHEMA may over-call M4 as "intentional partition — runtime is permissive by design" and miss that `schema_migrations` is a meta-table whose integrity props are orthogonal to the runtime/evidence partition. Their lens treats partition boundaries as load-bearing; that framing breaks down for meta-tables.
- **MISS**: SCHEMA is structurally weak at seeing M2 as a vacuity hazard. Their lens sees "broken bootstrap" (a category error / install problem); they will not naturally see that a smoke test passing on a zero-migration DB is the canonical empty-quantifier-vacuous-pass. They may rate M2 lower than I do.

### RELIABILITY
- **RIGHT**: RELIABILITY will catch M1 as BLOCKER on crash-safety grounds and will propose `BEGIN IMMEDIATE` / explicit COMMIT. They will also catch M2 as MAJOR on the "no signal at open time" angle — silent failure modes are their core lens.
- **WRONG**: RELIABILITY may over-call M3 as a state-machine-recovery issue ("what happens if `completed_at` is set twice during retry?") and miss that the underlying disposition is a spec-clarity issue, not a recovery issue. The trigger does its job; the question is whether it does the *right* job.
- **MISS**: RELIABILITY's lens does not naturally see F3 / F4 as falsifiability hazards. They will see them as "the trigger works; ship it" — they are structurally bad at noticing that a test passing without a written spec is a PRD §7 violation regardless of crash-safety.

### SECURITY
- **RIGHT**: SECURITY will land hard on M4 — the tamper-evidence check is partially defeated for runtime.db if `schema_migrations` is mutable, and they will frame this as a threat-model finding (attacker with SQL write access to runtime.db can rewrite ledger). I expect them to upgrade my MAJOR to BLOCKER on attacker-model grounds; I do not contest.
- **WRONG**: SECURITY may over-call M2 as a supply-chain hazard (wheel-install path manipulation as attack surface) when the immediate exploit is much smaller — the realistic failure is `pip install` from PyPI in v0.2 silently producing an empty DB, not a malicious wheel. The fix is the same regardless, but the framing risks bloating the disposition.
- **MISS**: SECURITY is structurally weak at seeing M3 (spec-clarity is not their lens) and weak at seeing M1's *testing-confound* angle (they will see M1 as a crash-safety issue, not as something that pollutes the Track A property-test preconditions).

STATUS: BLOCKER-FOUND
