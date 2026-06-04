# Synthesis — Phase 1.5 council fire (2026-06-04)

## Orchestrator disposition (per cluster)

All four seats returned `STATUS: BLOCKER-FOUND`. Per `parallel-review-disposition-schema` synthesis rule (highest severity present per item), per-cluster disposition:

### M1 — Migration apply atomicity
- **Severity (synthesized)**: BLOCKER
- **Convergence**: SCHEMA + RELIABILITY both BLOCKER; TEST-ARCH MAJOR ("would not contest BLOCKER upgrade"); SECURITY MAJOR (threat-model-bounded, but agrees the integrity fix is needed pre-Track-A).
- **Adopted fix (per RELIABILITY recovery proposal + SCHEMA fix recommendation)**: replace `with conn:` + `executescript` with explicit `conn.execute("BEGIN IMMEDIATE")` + manual statement-by-statement execution + `INSERT INTO schema_migrations` + `conn.execute("COMMIT")`; `conn.execute("ROLLBACK")` on exception. Add typed `BootstrapError` / `MigrationApplyError`. Add structured logging at apply start/success/failure. Add smoke test for half-applied recovery path.
- **Adopted-decision ID**: **A18**

### M2 — Package-path coupling
- **Severity (synthesized)**: BLOCKER
- **Convergence**: TEST-ARCH + RELIABILITY + SECURITY all BLOCKER (each via a different lens — vacuity / observability / forgery). SCHEMA MAJOR but recommends identical pre-Track-A minimum.
- **Adopted fix (per SCHEMA's pre-Track-A minimum + SECURITY's layered ask)**: `open_evidence()` and `open_runtime()` MUST raise `BootstrapError` (or `MigrationDiscoveryError`) when `discover()` returns `[]` from the configured directory. Invert `test_migration_discover_empty_dir` to assert `open_evidence` raises on empty (the unit test of `discover()` against an empty tmp dir keeps the current shape, but the integration property "open_evidence never returns an unusable DB" gets its own test). Long-term `importlib.resources` packaging deferred to v0.2.
- **Adopted-decision ID**: **A19**

### M3 — `runs` trigger scope
- **Severity (synthesized)**: MAJOR
- **Convergence**: SCHEMA MINOR (column-immutable is the intent — load-bearing answer); TEST-ARCH MAJOR (spec contradiction itself is the issue); RELIABILITY MAJOR (blocks legitimate recovery + missing `terminal_state`); SECURITY OBSERVATION (defers to SCHEMA).
- **Adopted intent statement (per SCHEMA — load-bearing)**: the intent IS column-immutable, NOT row-immutable. The trigger contradicts its own comment + name + error message; this is implementation drift, not design intent.
- **Adopted fix (per SCHEMA's named-trigger split)**:
  ```sql
  CREATE TRIGGER runs_completed_at_set_once BEFORE UPDATE OF completed_at ON runs
      WHEN OLD.completed_at IS NOT NULL
      BEGIN SELECT RAISE(ABORT, 'runs.completed_at is immutable once set'); END;
  CREATE TRIGGER runs_immutable_columns BEFORE UPDATE OF run_id, skill_id, run_kind, config_json, started_at ON runs
      BEGIN SELECT RAISE(ABORT, 'append_only_violation: runs immutable columns'); END;
  ```
  RELIABILITY's `terminal_state` column proposal defers to a separate v0.2 decision (D5 below) — it is a meaningful expansion but not blocking for Track A.
- **Adopted-decision ID**: **A20**

### M4 — Runtime ledger triggers
- **Severity (synthesized)**: MAJOR
- **Convergence**: SCHEMA OBSERVATION ("intentional per partition; doc-anchor needed"); TEST-ARCH MAJOR + SECURITY MAJOR + RELIABILITY MAJOR (META vs DOMAIN framing — `schema_migrations` is a meta-bookkeeping table whose append-only nature is independent of the operational mutability of the rest of the runtime DB).
- **Architectural decision**: ADOPT the META-vs-DOMAIN framing (3 seats vs 1). The partition is about operational tables (`run_progress`, `current_calibration`, `cost_ledger`); the meta-ledger sits outside it. SCHEMA's "uniformity" concern is noted but does not outweigh the audit-integrity loss.
- **Adopted fix**: add `BEFORE UPDATE` / `BEFORE DELETE` triggers to `runtime.schema_migrations` only (NOT to other runtime tables — those remain mutable per A2). Add a smoke test mirroring `test_evidence_append_only_skills`.
- **Adopted-decision ID**: **A21**

### Additional findings (beyond the 4 clusters)

#### RELIABILITY F5 — `synchronous=NORMAL` durability gap on evidence DB
- **Severity**: MAJOR
- **Adopted fix**: `evidence.db` opens with `PRAGMA synchronous = FULL`; `runtime.db` keeps `NORMAL`. Document the asymmetry. Requires splitting `open_db()` to per-DB pragma sets OR adding a parameter.
- **Adopted-decision ID**: **A22**

#### SECURITY F5 — Trust partition + tamper-evidence threat model documentation
- **Severity**: MAJOR
- **Adopted fix**: documentation-only. Add to `SECURITY.md` "Threat model" section: (1) trust partition clause, (2) filesystem-substitution boundary, (3) PRAGMA scope clause. Mirror (1) + (2) as a "Trust partition" subsection under `docs/COUNCIL_FINDINGS.md` §A4.
- **Adopted-decision ID**: **A23**

## Deferred to v0.2

- **D5** — `evidence.runs.terminal_state` enum column (RELIABILITY F3 expansion). Requires a follow-up migration that does not break A1 (append-only for the column itself with a single-shot trigger).
- **D6** — `db_identity` row + cross-DB identity check for restore-from-backup detection (RELIABILITY F4 sub-finding).
- **D7** — `skill audit` CLI command implementing cross-DB calibration-event resolution chain audit (SECURITY F4 sub-finding).
- **D8** — `importlib.resources` migration packaging (M2 long-term fix replacing `parents[3]` resolution entirely).

## PRD v1.1 amendments queued

In addition to the 16 amendments listed in `docs/COUNCIL_FINDINGS.md § PRD amendments required`:

- **§17** — state trust partition between `evidence.db` (append-only, audited, load-bearing) and `runtime.db` (mutable by design)
- **§17** — state PRAGMA scope: `open_db()` is the sanctioned connection entry; FK enforcement is connection-scoped
- **§17** — state `synchronous = FULL` for evidence, `NORMAL` for runtime
- **New threat-model section** (§17 supplement or new §17a) — name the filesystem-substitution boundary; tamper-evidence is in-process, not file-replacement-resistant

## PLAN.md amendments

Insert a new Phase 1.5a (code fixes) and Phase 1.5b (documentation updates) before Phase 2 begins:

- **Phase 1.5a** — apply A18, A19, A20, A21, A22 code fixes pre-Track-A. Estimated scope: ~150 lines of changes to `src/skill_harness/storage/migrations.py`, one new migration file `migrations/evidence/0002_runs_trigger_split.sql`, one new migration file `migrations/runtime/0002_schema_migrations_triggers.sql`, three new smoke tests, one typed exception module.
- **Phase 1.5b** — apply A23 documentation: `SECURITY.md` threat-model expansion + `COUNCIL_FINDINGS.md` A4 mirror of trust-partition clause.

Phase 1.5a is the new blocker before Track A. Phase 1.5b is documentation and can land in parallel.

## Cross-talk validation

The cross-talk discipline is intended as a check on the council's coherence: did seats correctly predict each other's findings? Quick scoring:

- TEST-ARCH predicted SCHEMA would catch F3 column-vs-row → ✓ correct
- TEST-ARCH predicted SECURITY would BLOCKER M4 → ✗ (SECURITY MAJOR; SECURITY bounded the threat to local-trust)
- SCHEMA predicted RELIABILITY would BLOCKER M1 + propose explicit BEGIN → ✓ correct
- SCHEMA predicted SECURITY would BLOCKER F4 → ✗ (SECURITY MAJOR with explicit A3-bound)
- RELIABILITY predicted TEST-ARCH would call M3 falsifiability → ✓ correct (TEST-ARCH F3 MAJOR for spec vacuity)
- RELIABILITY predicted SCHEMA would NOT propose runtime-wide hardening → ✓ correct (SCHEMA F4 explicitly recommended NOT adding triggers to other runtime tables)
- SECURITY predicted SCHEMA would own M3 → ✓ correct
- SECURITY predicted RELIABILITY would call M1 BLOCKER + explicit BEGIN → ✓ correct

7/8 predictions accurate. The one substantive miss (SCHEMA + TEST-ARCH expecting SECURITY to BLOCKER F4) is healthy disagreement-discovery: SECURITY's explicit A3-bound is a sharper threat-model statement than the other seats anticipated. The council pattern surfaced this; the synthesis adopts SECURITY's framing (MAJOR not BLOCKER) for F4 while still requiring the trigger fix.

## Citation verification

Per `subagent-research-reliability` discipline, external citations adopted into synthesis were verified against canonical sources already in `docs/COUNCIL_FINDINGS.md § Verified external citations`:

- Python sqlite3 docs (autocommit + `with conn:`): https://docs.python.org/3/library/sqlite3.html — canonical
- SQLite WAL durability + synchronous: https://www.sqlite.org/wal.html — already in COUNCIL_FINDINGS verified list
- SQLite PRAGMA semantics: https://www.sqlite.org/pragma.html — already verified
- SQLite transaction docs: https://www.sqlite.org/lang_transaction.html — already verified
- SQLite `executescript` semantics: https://www.sqlite.org/c3ref/exec.html — newly cited, valid SQLite docs URL
