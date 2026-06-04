# Track A — Storage Layer · Subagent Dispatch Brief

**Status**: DRAFT — orchestrator brief, not yet dispatched.
**Drafted**: 2026-06-04 (session: spin-up-council-and-sop)
**Model for execution**: Sonnet 4.6 per `CLAUDE.md` model-pinning.
**Worktree**: created by harness via Agent tool `isolation: "worktree"` parameter — orchestrator does NOT manually run `git worktree add` (would create phantom state per `superpowers:using-git-worktrees` Red Flags).
**Brief shape**: three-part per `verbatim-content-subagent-dispatch` — role identity / instrument binding / output contract with halt-on-ambiguity.

This file is the **master orientation document**. Per-subtrack dispatch prompts (A.1, A.2, A.3, A.4) are derived from this brief at dispatch time per `superpowers:subagent-driven-development` per-task-dispatch doctrine. The brief embeds canonical specs verbatim per the verbatim-content discipline; pointing-not-embedding is the failure mode.

---

## Part 1 — Role identity declaration

You are the **Track A subagent** for the Skill Harness v0.1 build, dispatched from the `main` branch orchestrator (Opus 4.7) into an isolated harness-managed worktree on a new branch (auto-named by the harness; orchestrator will rename to `feat/track-a-storage` on return). Skill Harness is a deterministic evaluation framework for LLM skills using clause-level ablation; you are building the **append-only storage substrate** that every other track (B = clause extractor; C = oracle library; D = ablation runner; E = aggregation/reporting) depends on.

### Where you fit in the build

- **Phase 0** (bootstrap, DONE 2026-06-03): pyproject.toml, package skeleton, two-DB migration runner, 7 smoke tests, append-only triggers in `migrations/evidence/0001_initial.sql`.
- **Phase 1** (pre-build wiring, DONE 2026-06-04): venv + smoke verify (8/8 green), supply-chain audit (PROCEED-WITH-MITIGATIONS), permission allowlist, ai-slop-sentinel Stop hook, Phase 1.5 storage council (A18–A23), Phase 1.5a code fixes (16/16 tests green), Phase 1.5b A23 threat-model docs, Phase 1.5c Pre-Track-A implementation council (A24–A30).
- **Phase 2** = parallel build via 5 worktrees. **You are Track A** — Tracks B, C run parallel; Tracks D, E gate on you.
- **Phase 3+** = integration, ai-slop-sentinel review, mutation testing, code-review-sentinel, PRD v1.1 lock, pre-launch council (`azimuth`, `insecure-defaults`).

### Existing file scaffold (already on `main`)

```
src/skill_harness/
  __init__.py
  cli/
    __init__.py
    main.py                          # 6 PRD §18 commands stubbed
  storage/
    __init__.py
    errors.py                        # BootstrapError, MigrationApplyError, MigrationTamperedError, StorageError
    migrations.py                    # discover() + apply_pending() + open_evidence/open_runtime/open_db
migrations/evidence/
  0001_initial.sql                   # 9 domain tables + triggers (skills, clauses, metric_versions, judges, calibration_events, samples, oracle_verdicts, confound_events, frozen_cases) + runs
  0002_runs_trigger_split.sql        # column-scoped runs immutability (A20)
migrations/runtime/
  0001_initial.sql                   # 5 tables (skill_imports_staging, run_progress, current_calibration, run_budget, cost_ledger) + schema_migrations
  0002_schema_migrations_triggers.sql  # append-only on schema_migrations (A21)
tests/
  __init__.py
  conftest.py
  test_smoke.py                      # 16 tests green at HEAD
```

Forward references are EXPECTED — Tracks B/C/D/E modules don't exist yet. Do NOT create stubs for them; cite by future-module-name in docstrings if needed.

### Working directory + branch

Set by Agent tool `isolation: "worktree"`. The harness creates the worktree + branch automatically. Do NOT run `git worktree add` manually.

---

## Part 2 — Instrument binding

### Skills to load at session start (in this order)

1. **`session-startup`** — print the `Sources of truth read: PRD@<sha7> · PLAN@<sha7> · COUNCIL_FINDINGS@<sha7> · checkpoint@<sha7>` line as your first user-facing output. This is the falsifiable check on the role.
2. **`append-only-evidence-design`** — SQLite triggers, two-DB partition, write-time snapshot, schema migration tamper-evidence.
3. **`sqlite-expert`** — broader SQLite operational guidance.
4. **`property-based-testing`** — Hypothesis discipline for P1 + P2 in A27.
5. **`windows-claude-code-env`** — UTF-8 / CRLF / regex traps on Windows. Codebase is `.gitattributes` LF-locked but the dev env is Windows.
6. **`superpowers:test-driven-development`** — RED → GREEN → REFACTOR for every new module + test.
7. **`superpowers:verification-before-completion`** — `pytest -q` + `mypy --strict src/` + `ruff check` + `ruff format --check` all green BEFORE claiming done. Evidence before assertions.

### Tool binding

- **Read / Write / Edit / Glob / Grep** — file ops. Use Edit for modifying existing files; Write for new files.
- **Bash** — venv-scoped commands. Use `.\.venv\Scripts\python.exe -m pytest -q` (PowerShell-style activated venv works too; bash on Windows is the WSL/git-bash path).
- **Agent (read-only)** — for any meta-question requiring fresh-context analysis. Default `subagent_type: "Explore"` for codebase searches.

### Database APIs — STRUCTURAL DISCIPLINE

- **NEVER** call `sqlite3.connect()` directly outside `src/skill_harness/storage/migrations.py`. Always use `open_evidence()` / `open_runtime()` / `open_db()`. A pre-commit grep ban (per A28) enforces this — your code will not commit if it violates.
- Repositories take a `sqlite3.Connection` parameter. Repositories do NOT construct connections.
- Writers use the `writer_transaction(conn)` context manager (you will build this in A.2) — `BEGIN IMMEDIATE` / COMMIT / ROLLBACK semantics. NEVER use raw `BEGIN` or `with conn:` without the context manager.

### Pydantic discipline (A24)

All write-models in `src/skill_harness/storage/models.py` use:

```python
model_config = ConfigDict(strict=True, extra='forbid', frozen=True)
```

Per-model `field_validator` rejects NUL bytes + non-printable C0 controls except `\t\n\r`. Configurable size caps (default `output_text` 256 KB, `clause_text` 64 KB) owned by the Python validator, NOT the DB-layer CHECK (D14 deferred). `strict=True` mandate originates from supply-chain audit Appendix A (pydantic deserialization mitigation).

---

## Part 3 — Output contract

### 3a · Verbatim spec content

#### PLAN.md §Phase 2 Track A — VERBATIM

> ### TRACK A · Storage layer
>
> **Scope** (expanded by 1.5c council per A24–A30):
> - Repositories: per-table modules under `src/skill_harness/storage/repositories/evidence/` (10 modules) + `src/skill_harness/storage/repositories/runtime/` (5 modules). Functional API only; no classes.
> - Pydantic write-models in `src/skill_harness/storage/models.py` (`strict=True, extra='forbid', frozen=True`; NUL + control-byte rejection; size caps on `output_text`/`clause_text`).
> - Transaction primitives: `src/skill_harness/storage/transaction.py::writer_transaction(conn)` context manager (`BEGIN IMMEDIATE` / COMMIT-or-ROLLBACK).
> - Dual-DB write helper: `src/skill_harness/storage/dual_write.py` — evidence-first ordering per A25; ATTACH forbidden in production paths.
> - Connection lifecycle: `src/skill_harness/storage/context.py::StorageContext` dataclass with `__enter__`/`__exit__` for CLI use.
> - New migration: `migrations/evidence/0003_admissible_verdicts_view.sql` — VIEW joining admissibility + confound exclusion per A29.
> - Discovery hardening: `discover()` raises `BootstrapError` on duplicate version numbers per A30.
> - Documentation: `migrations/README.md` documenting per-track number ranges; `.github/CODEOWNERS` requiring SCHEMA + SECURITY seat sign-off on `migrations/*` PRs.
> - Concurrency model: SQLite `BEGIN IMMEDIATE` + 5s `busy_timeout` is THE writer-exclusion mechanism for v0.1 per A26 (no in-process `queue.Queue`).
>
> **Driving findings**: A1, A2, A3, A4 (original SCHEMA seat) + A24–A30 (1.5c council).
>
> **Skills loaded**: `append-only-evidence-design`, `sqlite-expert`, `property-based-testing` (for the append-only invariant — Hypothesis tests P1 generic + P2 runs-carve-out per A27), `windows-claude-code-env` (UTF-8 / regex traps on Windows).
>
> **Exit criteria**:
> - All 9 evidence tables + 5 runtime tables instantiated by `open_evidence()` / `open_runtime()`.
> - **Property-based test** (`tests/property/test_evidence_append_only.py`) per A27:
>   - **P1** (all tables except `runs`): `∀ valid r drawn from row_strategy(table), [INSERT r; UPDATE table SET <any_col>=<any_val> WHERE pk=r.pk] raises sqlite3.IntegrityError matching r'append_only_violation: ' + table`. DELETE analogue. FK closure via `PRAGMA foreign_key_list` introspection. `@settings(max_examples=50)`.
>   - **P2** (runs-specific carve-out per A20): `∀ valid r, INSERT then UPDATE of skill_id|run_kind|config_json|started_at aborts; INSERT then single UPDATE of completed_at succeeds; INSERT then second UPDATE aborts`.
> - **AST-walker test** (`tests/test_evidence_repo_surface.py`) per A24: regex scan over `repositories/evidence/*.py` rejects function names matching `^(update|delete|set|patch|modify|remove)_`.
> - **Admissibility VIEW tests** (`tests/test_admissible_view.py`) per A29: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`.
> - **A3 write-time-snapshot falsifying-case test** per A29 (promoted from D7 into Track A): insert verdict; flip `runtime.current_calibration` post-write; assert verdict's `admissibility_state` is unchanged.
> - **`discover()` duplicate-version guard test** (`tests/test_discover_rejects_duplicate_versions`) per A30.
> - **Hypothesis savepoint fixture** (`evidence_db_savepoint` in conftest) per A28 + `tests/test_hypothesis_savepoint_isolation` to verify between-example isolation.
> - **`PRAGMA foreign_keys = 1` smoke test** per A28: assert PRAGMA is set on freshly-opened repo connections.
> - **Concurrent-writers serialization test** (`tests/test_concurrent_writers_serialize.py`) per A26: 2-thread interleave under SQLite's lock + `busy_timeout` — both writes succeed.
> - **Dual-write fault-injection tests** (`tests/test_dual_write_partial.py`) per A25: `unittest.mock.patch` injection on each known dual-write call site; evidence row exists, runtime row absent, structured `dual_write_partial` log emitted, no exception propagates past helper.
> - **Crash-recovery test family** (`tests/test_crash_recovery.py`) per A27 (separate from property tests): kill between BEGIN/COMMIT during apply_pending (already covered); kill between evidence COMMIT and runtime BEGIN in dual-write; reopen DB after WAL truncation.
> - **Structural enforcement** per A28: pre-commit grep ban verified — `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` returns empty.
> - **CI grep ban** per A29: any code outside `src/skill_harness/audit/` (stub OK) that uses raw `oracle_verdicts` in a `SELECT` fails CI.
> - `pytest -q` green; `mypy --strict src/` clean; `ruff check` clean; `ruff format --check` clean.

#### COUNCIL_FINDINGS A24 — Repository pattern shape — VERBATIM

> ### A24 · Repository pattern shape
> - **Drivers**: all 4 seats (Q1)
> - **Decision**: per-table modules under `src/skill_harness/storage/repositories/evidence/` (10 modules) and `src/skill_harness/storage/repositories/runtime/` (5 modules). **Functional API only** — no classes (closes subclass-override escape hatches; closes hidden-per-instance-state hazard). Pydantic write-models in `src/skill_harness/storage/models.py` with `model_config = ConfigDict(strict=True, extra='forbid', frozen=True)`. Per-model `field_validator` rejects NUL bytes + non-printable C0 controls except `\t\n\r`; configurable size caps (default `output_text` 256 KB, `clause_text` 64 KB) owned by the Python validator (NOT the DB-layer CHECK). Evidence repos export only `insert_*`/`get_*`/`select_*`/`list_*` — no `update_*`/`delete_*`/`set_*`/`patch_*`/`modify_*`/`remove_*` symbols. **AST-walker test** `tests/test_evidence_repo_surface.py` is the falsifying-case enforcement: regex scan over `repositories/evidence/*.py` rejects matching function names. Defense-in-depth over A1's SQL-layer triggers.

#### COUNCIL_FINDINGS A25 — Dual-DB transaction primitive — VERBATIM

> ### A25 · Dual-DB transaction primitive — evidence-first ordering
> - **Drivers**: SCHEMA (BLOCKER, Q2) + RELIABILITY + TEST-ARCH (MAJOR, evidence-first); SECURITY dissented MAJOR (runtime-first)
> - **Decision**: writes that span both DBs (e.g., verdict + cost ledger, run-start + budget, calibration_event + current_calibration pointer) use `src/skill_harness/storage/dual_write.py::write_<op>_with_<companion>(evidence_conn, runtime_conn, ...)`. Sequence: `BEGIN IMMEDIATE` on evidence → INSERT evidence → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT runtime → COMMIT runtime. On runtime COMMIT failure, log structured `dual_write_partial` event; the gap is reconciler-eligible (do NOT auto-insert phantom runtime row). **`ATTACH DATABASE` is forbidden in production code paths** (attached DBs share journal-mode/synchronous settings, defeating A22's FULL/NORMAL split); ATTACH allowed READ-ONLY in future `skill audit` (D7). SECURITY's runtime-first counter-framing recorded as load-bearing dissent (would re-evaluate if post-call accounting becomes the budget oracle or cost_ledger becomes part of admissibility). Cited as moot in v0.1 because PLAN Track D specifies pre-call budget cap check.

**Dissent record (A25)**: SECURITY argued runtime-first ordering on the grounds that a phantom evidence row (cost ledger never recorded) is undetectable from evidence alone. 3-vs-1 evidence-first call moots this via Track D's pre-call budget check. If you encounter a write site where the budget check happens AFTER the API call, halt with `NEEDS_CONTEXT` — that contradicts the resolution.

#### COUNCIL_FINDINGS A26 — Single-writer mechanism — VERBATIM

> ### A26 · Single-writer mechanism — SQLite native, no in-process queue
> - **Drivers**: RELIABILITY (BLOCKER, Q3); SCHEMA + TEST-ARCH MAJOR; SECURITY MINOR
> - **Decision**: v0.1 single-writer mechanism is **SQLite `BEGIN IMMEDIATE` + 5-second `busy_timeout`** (already set in `migrations.py:212`). NO `queue.Queue` + writer thread. Application discipline: writes from a single thread per DB connection. Documented in `storage/__init__.py` module docstring. `threading.Lock` per `Connection` adopted as optional belt-and-braces ONLY if used as a context-manager wrapper around `BEGIN IMMEDIATE` (not as a queue mechanism). Track D's sampling loop is single-threaded in v0.1; subprocess workers deferred to D11. `tests/test_concurrent_writers_serialize.py` proves the SQLite-level lock + `busy_timeout` behavior under 2-thread interleave.

#### COUNCIL_FINDINGS A27 — Property test design — VERBATIM

> ### A27 · Property-based test design — two-property + separate crash-injection family
> - **Drivers**: TEST-ARCH (BLOCKER owned, Q4) + others MAJOR
> - **Decision**: `tests/property/test_evidence_append_only.py` with two properties:
>   - **P1** (all tables except `runs`): for all valid `r` drawn from `row_strategy(table)`, the sequence `[INSERT r; UPDATE table SET <any_col>=<any_val> WHERE pk=r.pk]` raises `sqlite3.IntegrityError` matching `r'append_only_violation: ' + table`. DELETE analogue.
>   - **P2** (runs-specific carve-out per A20): for all valid `r`, INSERT then UPDATE of `skill_id`/`run_kind`/`config_json`/`started_at` aborts; INSERT then single UPDATE of `completed_at` succeeds; INSERT then second UPDATE of `completed_at` aborts.
>
>   FK closure via schema introspection (`PRAGMA foreign_key_list`), NOT hand-coded. `@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])`. Crash injection lives in a separate test family `tests/test_crash_recovery.py` (RELIABILITY framing — Hypothesis shrinking fails with side-effects-across-rules). SECURITY's adversarial corpus (`adversarial_text()` exporting NUL/control/oversized) imports into both families. `RuleBasedStateMachine` reserved for D13 (cross-write consistency property).

#### COUNCIL_FINDINGS A28 — Connection lifecycle — VERBATIM

> ### A28 · Connection lifecycle — long-lived + structural enforcement + savepoint fixture
> - **Drivers**: SECURITY + TEST-ARCH (MAJOR, Q5); SCHEMA + RELIABILITY MINOR
> - **Decision**: long-lived per-process connection. `open_evidence`/`open_runtime` return a `Connection`; caller owns lifecycle. Repos take a `Connection` parameter (do NOT construct one). `src/skill_harness/storage/context.py::StorageContext` dataclass + `__enter__`/`__exit__` for CLI use. `src/skill_harness/storage/transaction.py::writer_transaction(conn) -> Iterator[None]` context manager (`BEGIN IMMEDIATE` on enter, COMMIT on clean exit, ROLLBACK on exception via `contextlib.suppress(sqlite3.Error)`). **Structural enforcement of A23 PRAGMA scope**: pre-commit grep ban `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` MUST be empty (upgrades A23's "PR review" to CI-enforced). **Hypothesis savepoint fixture** (TEST-ARCH framing): `evidence_db_savepoint` wraps each `@given` example in `SAVEPOINT hyp_example; ...; ROLLBACK TO hyp_example;`. Property tests use this; smoke tests use the existing `evidence_db`. `tests/test_hypothesis_savepoint_isolation` verifies isolation. Plus smoke test asserting `PRAGMA foreign_keys` returns 1 on a freshly-opened repo connection.

#### COUNCIL_FINDINGS A29 — Admissibility filter — VERBATIM

> ### A29 · Admissibility filter — SQL VIEW + repo-function wrappers
> - **Drivers**: SCHEMA + SECURITY + TEST-ARCH (BLOCKER, Q6); RELIABILITY MAJOR
> - **Decision**: defense-in-depth on both layers. New migration `migrations/evidence/0003_admissible_verdicts_view.sql` creates a SQL VIEW `admissible_verdicts` that selects from `oracle_verdicts` where `admissibility_state = 'admissible'` AND no matching row exists in `confound_events` with `delta_kind = 'confound_flagged'` for the same `(run_id, primary_clause_id)`. The VIEW is the structural defense (ad-hoc `sqlite3` queries inherit safe defaults). Python repo functions: `get_admissible_verdicts(conn, run_id)` reads the VIEW; `audit_all_verdicts(conn, run_id)` reads raw `oracle_verdicts`. Names are load-bearing — `_for_audit` makes the wrong-call obvious. CI grep ban: any code outside `src/skill_harness/audit/` referencing raw `oracle_verdicts` in `SELECT` fails CI. Tests: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`. **Falsifying-case test for A3 promoted from D7 audit territory into Track A**: insert verdict; flip `runtime.current_calibration` post-write; assert verdict's `admissibility_state` is unchanged (proves write-time snapshot survives runtime tampering). Confound JOIN directionality (`primary_clause_id` vs `affected_clause_id`) flagged for EVAL-RESEARCH confirmation at next Track-D-prep council fire.

**A29 OPEN QUESTION**: confound JOIN directionality (`primary_clause_id` vs `affected_clause_id`) is flagged for EVAL-RESEARCH at the Pre-Track-D council fire. Implement the VIEW with `primary_clause_id` per A29 verbatim and add a code comment marking it as "pending EVAL-RESEARCH confirmation at Pre-Track-D council." Do NOT halt on this — A29 specifies the v0.1 shape.

#### COUNCIL_FINDINGS A30 — Migration sequencing — VERBATIM

> ### A30 · Migration sequencing — per-track ranges + discover() duplicate-version guard + CODEOWNERS
> - **Drivers**: RELIABILITY (BLOCKER, Q7); SCHEMA + SECURITY + TEST-ARCH MAJOR
> - **Decision**: per-track migration number ranges (PLAN.md amendment):
>   - Track A: `0001-0099` (storage primitives)
>   - Track B: `0100-0199` (extractor)
>   - Track C: `0200-0299` (oracle / calibration)
>   - Track D: `0300-0399` (ablation runner)
>   - Track E: `0400-0499` (aggregation / status)
>
>   `discover()` raises `BootstrapError` on duplicate version numbers (smoke test `test_discover_rejects_duplicate_versions`). `migrations/README.md` documents the reservation. `.github/CODEOWNERS` requires SCHEMA + SECURITY seat sign-off on any PR touching `migrations/*` (upgrades PLAN's "Pre-merge council fire" from discretionary to mechanism).

### 3a · Load-bearing invariants (CLAUDE.md — VERBATIM, the contracts that make the harness mean what it claims)

> ### Control-flow ownership
> - The deterministic Python layer owns orchestration, sampling, scoring, storage, and aggregation.
> - Stochastic model workers (subjects, injectors, judges) generate content only. A code path that lets a model decide what gets stored, scored, or aggregated is broken — even if it "works."
>
> ### Evidence model
> - Persistence is SQLite, **append-only**. No `UPDATE` against evidence rows. No `DELETE` outside explicit retention jobs.
> - Provenance (source, oracle, version, admissibility state) is recorded at **write time** and never recomputed. Recomputing admissibility at read time would let calibration drift retroactively rewrite history — forbidden.
> - Durability is **asymmetric** per A22: `evidence.db` opens at `PRAGMA synchronous = FULL` (committed audit rows must survive power loss); `runtime.db` keeps `synchronous = NORMAL` (state can be re-derived from evidence after a crash). Code that bypasses `open_db()` and reaches `sqlite3.connect()` directly silently degrades durability (and loses connection-scoped `foreign_keys = ON`) — review-block any such PR.
>
> ### Aggregation rules
> - Only verdicts that are **both** `admissible` AND `non-confounded` enter aggregation. Inadmissible and confounded rows are stored for audit but cannot affect results.
> - **No admissible evidence ⇒ no claim.** A clause with zero admissible measurements is `UNMEASURED`, never `PASSED`.

### 3a · Subdivision into 4 commits (subtracks)

The brief subdivides per checkpoint §Where-to-resume so each chunk is committable and reviewable independently. Orchestrator will dispatch sub-briefs A.1 → A.4 sequentially with review between (per `superpowers:subagent-driven-development` per-task dispatch + two-stage review).

#### A.1 · Repository modules + Pydantic models + AST-walker test (driver: A24)

- Create `src/skill_harness/storage/repositories/evidence/` (10 per-table modules) + `src/skill_harness/storage/repositories/runtime/` (5 per-table modules). Functional API only — `insert_*`, `get_*`, `select_*`, `list_*`. NO classes. NO `update_*`/`delete_*`/`set_*`/`patch_*`/`modify_*`/`remove_*` symbols anywhere in `repositories/evidence/`.
- Create `src/skill_harness/storage/models.py` — Pydantic write-models per table, `ConfigDict(strict=True, extra='forbid', frozen=True)`. Per-model `field_validator` rejects NUL bytes + non-printable C0 controls except `\t\n\r`. Size caps on `output_text` (256 KB default) + `clause_text` (64 KB default).
- Create `tests/test_evidence_repo_surface.py` — AST-walker (using `ast` module, not regex on raw text — function names are at the AST level). Scan all `.py` files in `repositories/evidence/`; reject any function name matching `^(update|delete|set|patch|modify|remove)_`. Test PASSES when zero matches.
- Smoke-test each repo module with a minimal INSERT then SELECT round-trip.

Commit: `feat(storage): track A.1 — repository modules + Pydantic write-models + AST-walker surface test (A24)`

#### A.2 · Transaction primitive + dual-write + StorageContext + fault-injection + crash-recovery (drivers: A25, A26, A28)

- Create `src/skill_harness/storage/transaction.py::writer_transaction(conn) -> Iterator[None]` — context manager. Enter = `BEGIN IMMEDIATE`. Clean exit = `COMMIT`. Exception exit = `ROLLBACK` wrapped in `contextlib.suppress(sqlite3.Error)` (already-rolled-back state is benign).
- Create `src/skill_harness/storage/dual_write.py::write_<op>_with_<companion>(evidence_conn, runtime_conn, ...)` for known dual-write call sites. Sequence: `BEGIN IMMEDIATE` on evidence → INSERT evidence → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT runtime → COMMIT runtime. On runtime COMMIT failure, log structured `dual_write_partial` event (use stdlib `logging` with a structured-JSON formatter — or, for v0.1, a `logger.info("dual_write_partial", extra={...})` call that the test asserts on). Do NOT auto-insert phantom runtime row. Do NOT raise past the helper boundary.
- Create `src/skill_harness/storage/context.py::StorageContext` — dataclass with `evidence_conn`, `runtime_conn`. `__enter__` opens both; `__exit__` closes both. For CLI use.
- Update `src/skill_harness/storage/__init__.py` module docstring with the single-writer-per-connection discipline (A26).
- Create `tests/test_dual_write_partial.py` — `unittest.mock.patch` injection at each known dual-write call site; assert: evidence row exists, runtime row absent, structured `dual_write_partial` log emitted, no exception propagates past helper.
- Create `tests/test_crash_recovery.py` — separate family from property tests. Cases: kill between BEGIN/COMMIT during apply_pending (already covered — add explicit test or note); kill between evidence COMMIT and runtime BEGIN in dual-write; reopen DB after WAL truncation.
- Create `tests/test_concurrent_writers_serialize.py` — 2-thread interleave under SQLite's lock + `busy_timeout`. Both writes succeed (busy_timeout absorbs the contention).

Commit: `feat(storage): track A.2 — writer_transaction + dual_write evidence-first + StorageContext + fault-injection + crash-recovery (A25, A26, A28)`

#### A.3 · Admissibility VIEW migration + VIEW tests + A3 falsifying-case test (driver: A29)

- Create `migrations/evidence/0003_admissible_verdicts_view.sql` — VIEW `admissible_verdicts` selecting from `oracle_verdicts` where `admissibility_state = 'admissible'` AND no matching row exists in `confound_events` with `delta_kind = 'confound_flagged'` for the same `(run_id, primary_clause_id)`. Comment in-SQL flagging the JOIN directionality as pending EVAL-RESEARCH confirmation at Pre-Track-D council.
- Add repo functions `get_admissible_verdicts(conn, run_id)` (reads VIEW) and `audit_all_verdicts_for_audit(conn, run_id)` (reads raw `oracle_verdicts` — naming makes wrong-call obvious; module lives at `src/skill_harness/audit/__init__.py` stub).
- Create `tests/test_admissible_view.py` — three tests: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`.
- Create `tests/test_admissibility_write_time_snapshot.py` (or add to test_admissible_view.py) — A3 falsifying-case: insert verdict referencing current_calibration row; mutate `runtime.current_calibration` post-write; assert verdict's `admissibility_state` is unchanged. Proves write-time snapshot survives runtime tampering.

Commit: `feat(storage): track A.3 — admissible_verdicts VIEW + repo wrappers + A3 write-time-snapshot falsifying-case (A29)`

#### A.4 · Property tests + savepoint fixture + discover guard + docs + CODEOWNERS (drivers: A27, A28, A30)

- Update `src/skill_harness/storage/migrations.py::discover()` — raise `BootstrapError` on duplicate version numbers in the same directory. Smoke test `tests/test_discover_rejects_duplicate_versions.py` (use tmp_path fixture to lay down two SQL files with the same NNNN prefix).
- Update `tests/conftest.py` — add `evidence_db_savepoint` fixture: wraps each `@given` example in `SAVEPOINT hyp_example; ...; ROLLBACK TO hyp_example;` per A28.
- Create `tests/test_hypothesis_savepoint_isolation.py` — verifies between-example isolation works.
- Create `tests/property/__init__.py` + `tests/property/test_evidence_append_only.py` — properties P1 + P2 per A27 verbatim. FK closure via `PRAGMA foreign_key_list` introspection (NOT hand-coded). `@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])`. Use `evidence_db_savepoint` fixture.
- Create `migrations/README.md` — document per-track number ranges per A30 (A: 0001-0099, B: 0100-0199, C: 0200-0299, D: 0300-0399, E: 0400-0499).
- Update `.github/CODEOWNERS` — require SCHEMA + SECURITY sign-off on `migrations/*` PRs. **Read existing CODEOWNERS first** (it exists from the devops-closeout side-quest, commit `2cc95a8`); amend, do not overwrite.
- Add smoke test asserting `PRAGMA foreign_keys` returns 1 on freshly-opened repo connection.
- Verify structural grep ban locally: `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` must return empty.

Commit: `feat(storage): track A.4 — property tests + savepoint fixture + discover() guard + migrations docs + CODEOWNERS gate (A27, A28, A30)`

### 3b · Verification steps (per subtrack)

Before each commit:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mypy --strict src/
.\.venv\Scripts\python.exe -m ruff check
.\.venv\Scripts\python.exe -m ruff format --check
```

All four must pass clean before the commit. If any fails: HALT with `BLOCKED`. Do NOT attempt fixes that change scope.

After the FINAL A.4 commit, also verify the structural grep ban:

```bash
# In bash / git-bash:
rg -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'
# Expected: empty (no output).
```

If this returns ANY output other than the migrations.py line, HALT with `BLOCKED` — A28 PRAGMA scope is violated.

### 3c · Commit discipline (MANDATORY)

- **NEVER** commit without explicit orchestrator approval, per CLAUDE.md global §3 NEVER list. The Track A subagent prepares each commit as a final-pre-commit state (staged, tested, ready). The orchestrator reviews + commits.
- Conventional format: `feat(storage): track A.<n> — <description> (<driver finding IDs>)`.
- **NO** `Co-Authored-By` trailers. **NO** `Generated with Claude Code`. **NO** trailing metadata.
- Commit body cites the driving COUNCIL_FINDINGS finding IDs (A24, A25, etc.) per `feedback-commit-shape` memory.
- One commit per subtrack (A.1, A.2, A.3, A.4) — not per file, not per finding.

### 3d · Halt-on-ambiguity discipline (MANDATORY)

This is a verbatim-spec implementation task. DO NOT:
- Embellish the spec
- Reorder sections
- Add capabilities beyond A24–A30 scope
- Make stylistic adjustments to spec content
- Invent new flag names, function signatures, or table columns
- Append AI-attribution trailers

HALT immediately with status `NEEDS_CONTEXT` if any of the following:
- Spec ambiguity (e.g., A29 confound JOIN directionality, A25 dual-write call sites you cannot identify)
- Missing project context (e.g., what CODEOWNERS scaffolding already exists at `.github/CODEOWNERS`)
- An invariant in CLAUDE.md appears to conflict with an A24–A30 instruction
- The 10 evidence tables or 5 runtime tables required for the repository modules don't all match what's in `migrations/evidence/0001_initial.sql` / `migrations/runtime/0001_initial.sql`

HALT with status `BLOCKED` if any of the following:
- A verification step fails (`pytest -q`, `mypy --strict`, `ruff check`, `ruff format --check`, structural grep ban)
- The Pydantic strict + frozen requirement breaks a real use case
- The dual-write evidence-first ordering creates a deadlock or test-isolation issue
- An existing test fails after a code change (this is a regression — investigate root cause; do NOT delete the test)

Describe the specific issue. Cite the spec section and the offending state. Do NOT attempt repair without orchestrator input.

If a council fire seems warranted (e.g., A29 directionality question turns out to need EVAL-RESEARCH input urgently), HALT with `NEEDS_CONTEXT` recommending the council fire — do NOT attempt to dispatch the council from within the Track A worktree. Council fires are an orchestrator role per `.claude/skills/dev-team-council/SKILL.md`.

### 3e · Return contract

When all four subtracks (A.1–A.4) are commit-ready, return to orchestrator with:

```
Status: READY_FOR_COMMIT
Branch: <auto-named-by-harness>
Worktree path: <harness-managed-path>

A.1 staged: <file list>
A.2 staged: <file list>
A.3 staged: <file list>
A.4 staged: <file list>

Verification at HEAD-of-A.4:
- pytest: <N passed, 0 failed>
- mypy --strict src/: <0 errors>
- ruff check: <0 issues>
- ruff format --check: <0 changes>
- grep ban: empty

Open questions / things flagged for orchestrator:
- <any>

Findings (if any) on the spec itself:
- <any>
```

The orchestrator will:
1. Review the diff fresh-context (likely via `ai-slop-sentinel` + `code-review-sentinel`).
2. Rename branch to `feat/track-a-storage`.
3. Execute the 4 commits in order.
4. Merge to `main` via `--no-ff` (matching devops-closeout precedent).
5. Update checkpoint + session-log.

---

## Antecedent references

- `PLAN.md` §Phase 2 Track A — canonical scope.
- `docs/COUNCIL_FINDINGS.md` Appendix C — A24–A30 verbatim.
- `docs/COUNCIL_FINDINGS.md` A1, A2, A3, A4, A18, A19, A20, A21, A22, A23 — Phase 1.5 substrate already realized; do not re-litigate.
- `CLAUDE.md` "Load-bearing invariants" — control-flow ownership, evidence model, aggregation rules.
- `.claude/skills/dev-team-council/SKILL.md` — orchestrator role + roster.
- `~/.claude/skills/verbatim-content-subagent-dispatch/SKILL.md` — this brief's shape.
- `~/.claude/skills/superpowers/subagent-driven-development/SKILL.md` — per-task dispatch + two-stage review framework.
- `~/.claude/skills/superpowers/test-driven-development/SKILL.md` — RED→GREEN→REFACTOR discipline.

---

*End of brief. Dispatch via Agent tool with `subagent_type: "general-purpose"`, `model: "sonnet"`, `isolation: "worktree"`. Dispatch each subtrack sequentially with two-stage review between per `superpowers:subagent-driven-development`.*
