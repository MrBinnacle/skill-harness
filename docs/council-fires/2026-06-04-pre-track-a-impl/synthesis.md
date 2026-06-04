# Synthesis — Pre-Track-A implementation council (2026-06-04)

## Orchestrator disposition (per Q)

All 4 seats returned `STATUS: BLOCKER-FOUND`. Per `parallel-review-disposition-schema` synthesis rule (highest severity present per item) and `cross-talk-council-dispatch` resolution pattern (substantive disagreement resolved on cross-talk-aware grounds, not just headcount).

### Q1 — Repository pattern shape
- **Severity (synthesized)**: MAJOR (unanimous)
- **Convergence**: all 4 seats agreed on functional, per-table modules + Pydantic `strict=True, extra='forbid'` at write boundary + evidence repos export only `insert_*`/`get_*`/`select_*` (no `update_*`/`delete_*`).
- **Adopted scope**:
  - Per-table modules: `src/skill_harness/storage/repositories/evidence/{table}.py` × 10 + `src/skill_harness/storage/repositories/runtime/{table}.py` × 5
  - **Functional API only** (no classes — closes subclass-override escape hatches per TEST-ARCH; closes hidden-per-instance-state hazard per RELIABILITY)
  - Pydantic write-models in `src/skill_harness/storage/models.py`: `model_config = ConfigDict(strict=True, extra='forbid', frozen=True)`
  - Per-model `field_validator` rejects NUL bytes + non-printable C0 (except `\t\n\r`) per SECURITY; size caps configurable (default: `output_text` 256 KB, `clause_text` 64 KB)
  - **AST-walker test** `tests/test_evidence_repo_surface.py`: regex scan over `repositories/evidence/*.py` rejects any function whose name matches `^(update|delete|set|patch|modify|remove)_`. **Defense-in-depth with A1 triggers; NOT a substitute.**
- **Decision-resolution note**: size-cap-source ambiguity between SECURITY (Python validator) and SCHEMA (DB-layer CHECK). Adopted: **Python validator owns the limit** (SECURITY framing). Reason: SCHEMA's instinct toward DB-layer is correct for invariants but a numeric cap is tunable in v0.2 without a migration; Python-layer is the right home. Document `output_text`/`clause_text` caps in `storage/models.py` docstring.
- **Adopted-decision ID**: **A24**

### Q2 — Dual-DB transaction primitive
- **Severity (synthesized)**: BLOCKER (SCHEMA blocks; others MAJOR)
- **Convergence + substantive disagreement**: SCHEMA + RELIABILITY + TEST-ARCH = **evidence-first ordering** (evidence is source of truth; runtime gaps are reconcilable from evidence). SECURITY = **runtime-first ordering** (worst-case "phantom API call" is observable, vs. evidence-first's "verdict unaccounted = budget bypass").
- **Decision-resolution note**: adopted **evidence-first** (3-vs-1) on cross-talk-aware grounds:
  - SECURITY's budget-bypass concern is moot in v0.1 because PLAN Track D exit criterion specifies "Budget check inside writer transaction (no read-then-write race); abort with `aborted_budget` state if `--max-usd` exceeded." The cap check happens **before the API call**, not after the verdict write. An attacker engineering a crash mid-dual-write cannot bypass a pre-call cap check.
  - A3 (admissibility snapshotted at write time on `oracle_verdicts`) makes evidence rows fully self-contained for audit purposes — the calibration event ID is frozen in the verdict, so the verdict is a sound audit-trail unit on its own.
  - The "phantom cost row" SECURITY warns against (runtime-first failure mode) is structurally undetectable from evidence; the "orphan verdict" (evidence-first failure mode) is detectable by a reconciler query against `evidence.oracle_verdicts WHERE NOT EXISTS (SELECT 1 FROM runtime.cost_ledger WHERE ...)`. Detectable > undetectable for v0.1's audit-first design.
  - SECURITY's framing is recorded as load-bearing dissent. The threat model would force ordering re-evaluation if (a) post-call accounting becomes the budget oracle, or (b) cost_ledger becomes part of admissibility.
- **Adopted scope**:
  - `src/skill_harness/storage/dual_write.py::write_verdict_with_cost(evidence_conn, runtime_conn, verdict_row, cost_row)`
  - Inside: `BEGIN IMMEDIATE` on evidence → INSERT verdict → COMMIT evidence → `BEGIN IMMEDIATE` on runtime → INSERT cost_ledger → COMMIT runtime
  - On runtime COMMIT failure: log structured `dual_write_partial` event; the gap is reconciler-eligible (do NOT auto-insert phantom cost; operator sees the gap; budget enforcement stays conservative)
  - **`ATTACH DATABASE` is forbidden in production code paths** (SCHEMA's framing) — attached DBs share journal-mode / synchronous settings, defeating A22's FULL/NORMAL split. ATTACH allowed READ-ONLY in future `skill audit` (D7).
  - `tests/test_dual_write_partial.py` — `unittest.mock.patch` fault injection on each known dual-write call site (verdict+cost, run-start+budget, calibration_event+current_calibration pointer)
- **Adopted-decision ID**: **A25**

### Q3 — Single-writer queue
- **Severity (synthesized)**: BLOCKER (RELIABILITY blocks)
- **Convergence**: all 4 seats agreed the term "single-writer queue" conflates 3 distinct things (SQLite-level lock + Python-process discipline + application-ordering). RELIABILITY's load-bearing framing: **do NOT build an in-process queue for v0.1; use SQLite's `BEGIN IMMEDIATE` + `busy_timeout=5000` as THE writer-exclusion mechanism**. SCHEMA + TEST-ARCH + SECURITY concur (SECURITY downgrades to MINOR because v0.1 threat model bounds the DoS concern; the others MAJOR/BLOCKER on disambiguation grounds).
- **Adopted scope**:
  - **v0.1 single-writer mechanism = SQLite `BEGIN IMMEDIATE` + 5s `busy_timeout`** (already set in `migrations.py:212`). No `queue.Queue` + writer thread.
  - Application discipline: writes from a single thread per DB connection. Document explicitly in `storage/__init__.py` module docstring.
  - **`threading.Lock` per `Connection` is OPTIONAL belt-and-braces**: adopted IF Track A's repo functions use it as a context manager wrapper around `BEGIN IMMEDIATE`. Recommended NOT bottoming-out at a `queue.Queue` — keep the writer's "single" property as the SQLite-level lock + thread discipline, not a Python queue.
  - Track D constraint: single sampling thread for v0.1; subprocess workers are v0.2 (D11 deferred).
  - `tests/test_concurrent_writers_serialize.py` — 2-thread interleave test asserting both writes succeed via SQLite's lock + `busy_timeout`. Documents the failure mode if `SQLITE_BUSY` raises (would indicate a missing sync somewhere).
- **Adopted-decision ID**: **A26**

### Q4 — Property-based test design (TEST-ARCH owned)
- **Severity (synthesized)**: BLOCKER (TEST-ARCH blocks)
- **Convergence**: all 4 seats agreed on the property-test design's load-bearing role. TEST-ARCH's framing adopted in full (their owned scope). RELIABILITY's "crash injection is a separate test family from the property test" is a structural correction adopted into the design (Hypothesis shrinking fails with side-effects-across-rules).
- **Adopted scope**:
  - `tests/property/test_evidence_append_only.py` — two properties:
    - **P1** (generic, all tables except `runs`): `∀ valid r drawn from row_strategy(table), [INSERT r; UPDATE table SET <any_col>=<any_val> WHERE pk=r.pk] raises sqlite3.IntegrityError matching r'append_only_violation: ' + table`. DELETE analogue.
    - **P2** (runs-specific carve-out per A20): `∀ valid r, INSERT then UPDATE of skill_id|run_kind|config_json|started_at aborts; INSERT then single UPDATE of completed_at succeeds; INSERT then second UPDATE of completed_at aborts`.
  - FK closure via **schema introspection** (`PRAGMA foreign_key_list(<table>)`) — NOT hand-coded (drifts when schema migrates). SCHEMA's lens owns this.
  - `@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])`
  - **Savepoint per example** (NOT fresh DB per example) — see A28
  - `tests/test_crash_recovery.py` — separate test family with hand-curated cases: (a) kill between BEGIN and COMMIT during apply_pending (already covered as smoke); (b) kill between evidence COMMIT and runtime BEGIN in dual-write (new); (c) reopen DB after WAL truncation (new)
  - SECURITY's adversarial-corpus strategy (`adversarial_text()` exporting NUL/control/oversized) imports into both families
- **Decision-resolution note**: SCHEMA proposed `RuleBasedStateMachine` for FK closure; RELIABILITY + TEST-ARCH preferred `@composite` + introspection. Adopted: **`@composite` + introspection** for P1/P2 (cleaner shrinking, less flake). State-machine pattern reserved for a future "consistency-across-writes" test (deferred).
- **Adopted-decision ID**: **A27**

### Q5 — Connection lifecycle
- **Severity (synthesized)**: MAJOR (SECURITY + TEST-ARCH MAJOR; SCHEMA + RELIABILITY MINOR)
- **Convergence**: SCHEMA + RELIABILITY = "long-lived per-process is fine, MINOR" (lens: PRAGMAs set on open; per-call open re-pays cost). SECURITY + TEST-ARCH = "structural enforcement is the load-bearing concern, MAJOR" (lens: PR review doesn't scale; Hypothesis-fixture interaction has a real trap). Adopted: **MAJOR** — the structural concerns are real and TEST-ARCH named a specific Hypothesis trap that SCHEMA/RELIABILITY missed.
- **Adopted scope**:
  - **Long-lived per-process connection** (SCHEMA + RELIABILITY framing): `open_evidence`/`open_runtime` return a `Connection`; caller owns lifecycle. Repos take a `Connection` parameter.
  - `src/skill_harness/storage/context.py::StorageContext` dataclass + `__enter__`/`__exit__` for CLI entry use (`with StorageContext() as ctx: ctx.evidence_conn ...`)
  - `src/skill_harness/storage/transaction.py::writer_transaction(conn) -> Iterator[None]` context manager (`BEGIN IMMEDIATE` on enter, COMMIT on clean exit, ROLLBACK on exception via `contextlib.suppress(sqlite3.Error)`)
  - **Structural enforcement of A23 PRAGMA scope** (SECURITY framing): pre-commit grep ban — `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` MUST be empty. Repos do NOT call `sqlite3.connect()`.
  - **Hypothesis savepoint fixture** (TEST-ARCH framing): new fixture `evidence_db_savepoint` wraps each `@given` example in `SAVEPOINT hyp_example; ...; ROLLBACK TO hyp_example;`. Property tests MUST use this fixture; smoke tests use the existing `evidence_db`. Add `tests/test_hypothesis_savepoint_isolation` to verify isolation between examples.
  - One smoke test: assert `PRAGMA foreign_keys` returns 1 on a freshly-opened repo connection (defense check that `open_db` PRAGMAs landed)
- **Adopted-decision ID**: **A28**

### Q6 — Admissibility filter on read
- **Severity (synthesized)**: BLOCKER (SCHEMA + SECURITY + TEST-ARCH block; RELIABILITY MAJOR)
- **Convergence**: SECURITY + TEST-ARCH = **SQL VIEW** (structural enforcement). SCHEMA = Python repo functions with `_for_aggregation` / `_for_audit` split (sharp naming). RELIABILITY = Python repo functions + Pydantic strict.
- **Decision-resolution note**: adopted **SQL VIEW + repo-function wrappers** (both layers, defense-in-depth):
  - SQL VIEW is the structural defense (an analyst running ad-hoc `sqlite3 evidence.db "SELECT * FROM admissible_verdicts"` gets safe defaults)
  - Repo functions provide the typed Python API and load-bearing naming (`get_admissible_verdicts(run_id)` vs. `audit_all_verdicts(run_id)`)
  - Internal Python aggregation uses the repo functions; ad-hoc inspection uses the VIEW directly
- **Adopted scope**:
  - **New migration `migrations/evidence/0003_admissible_verdicts_view.sql`** — Track A authors:
    ```sql
    CREATE VIEW admissible_verdicts AS
    SELECT v.*
    FROM oracle_verdicts v
    WHERE v.admissibility_state = 'admissible'
      AND NOT EXISTS (
        SELECT 1 FROM confound_events c
        WHERE c.run_id = v.run_id
          AND c.primary_clause_id = v.clause_id
          AND c.delta_kind = 'confound_flagged'
      );
    ```
  - Repo functions: `get_admissible_verdicts(conn, run_id)` reads the VIEW; `audit_all_verdicts(conn, run_id)` reads raw `oracle_verdicts`. Names are load-bearing.
  - **CI grep ban**: any code outside `src/skill_harness/audit/` (future module, may be empty stub at Track A) that references raw `oracle_verdicts` in a `SELECT` fails CI. Track A authors the grep check.
  - Tests: `test_admissible_view_excludes_inadmissible`, `test_admissible_view_excludes_confounded`, `test_admissible_view_includes_clean_verdicts`. Plus a falsifying-case for A3: insert verdict; flip `runtime.current_calibration` post-write; assert the verdict's `admissibility_state` is unchanged (proves write-time snapshot survives runtime tampering). This test moves from D7 audit territory into Track A (TEST-ARCH framing).
  - **Confound JOIN directionality clarification**: A11 marks PRIMARY clause (the one being ablated). The EXISTS subquery uses `c.primary_clause_id = v.clause_id`. EVAL-RESEARCH should confirm at first Track-D-prep council fire whether the AFFECTED clause should also be marked confounded — if so, VIEW changes.
- **Adopted-decision ID**: **A29**

### Q7 — Migration sequencing across worktrees
- **Severity (synthesized)**: BLOCKER (RELIABILITY blocks)
- **Convergence**: all 4 seats agreed on number-range reservation + `discover()` duplicate-version guard. SECURITY added CODEOWNERS-enforced migrations/ pre-merge review.
- **Adopted scope**:
  - **Per-track migration number ranges** (PLAN.md amendment, applies before Phase 2 dispatch):
    - Track A: `0001-0099` (storage primitives — `0001`, `0002`, and now `0003` admissible_verdicts VIEW will be authored under Track A)
    - Track B: `0100-0199` (extractor-emitted runtime tables, if any)
    - Track C: `0200-0299` (oracle / calibration writers)
    - Track D: `0300-0399` (ablation runner / cost ledger extensions)
    - Track E: `0400-0499` (aggregation views, status derivation tables)
  - **`discover()` raises `BootstrapError` on duplicate version numbers**: Track A adds the guard to `src/skill_harness/storage/migrations.py::discover()`:
    ```python
    seen: dict[int, str] = {}
    for m in out:
        if m.version in seen:
            raise BootstrapError(
                f"duplicate migration version {m.version} in {directory}: "
                f"{seen[m.version]} vs {m.name}"
            )
        seen[m.version] = m.name
    ```
    Plus smoke test `test_discover_rejects_duplicate_versions`.
  - **`migrations/README.md`** authored by Track A documenting the range reservation
  - **`.github/CODEOWNERS`** authored by Track A (or as a parallel commit) with `migrations/* @<owner>` and branch protection requiring review on the owned path
- **Adopted-decision ID**: **A30**

## Deferred to v0.2

- **D9** — `current_calibration` rewrite + verdict admissibility falsifying-case (TEST-ARCH proposed in Q6 cross-talk). Adopted into Track A scope per A29 (NOT deferred). *Removed from deferral list.*
- **D10** — `db_identity` row + cross-DB identity check for restore-from-backup detection (carry-forward from Phase 1.5 D6; SECURITY F2 in this fire reinforced)
- **D11** — Multi-process single-writer (subprocess workers per Track D); requires queue.Queue + writer thread OR shared FIFO
- **D12** — Denormalized `confound_flagged` boolean on `oracle_verdicts` IF the EXISTS subquery in A29's VIEW becomes performance-pathological at Track E scale
- **D13** — `RuleBasedStateMachine` consistency-across-writes property test (Hypothesis stateful pattern, for cross-write invariants)
- **D14** — `output_text`/`clause_text` size cap as DB-layer CHECK (if Python-layer enforcement proves insufficient under real-world adversarial input)

## PRD v1.1 amendments queued

In addition to the **20 amendments** queued before this fire (16 original council + 4 Phase 1.5):

- **§17** — declare per-track migration number ranges (Track A 0001-0099, B 0100-0199, C 0200-0299, D 0300-0399, E 0400-0499)
- **§17** — declare `admissible_verdicts` SQL VIEW as the canonical aggregation surface; raw `oracle_verdicts` access restricted to `audit/` module
- **§17** — declare SQLite `BEGIN IMMEDIATE` + 5s `busy_timeout` as the writer-exclusion mechanism for v0.1; in-process `queue.Queue` not adopted in v0.1
- **§17** — declare dual-DB write ordering: evidence-first; runtime gaps are reconcilable from evidence; ATTACH forbidden in production paths
- **§17** — declare PRAGMA scope enforcement as STRUCTURAL (pre-commit grep ban on raw `sqlite3.connect` outside `migrations.py`), upgrading A23's "PR review" to a CI-enforced check
- **§17** — declare repository surface restriction (evidence repos export `insert_*`/`get_*`/`select_*` only; AST-walker test) as defense-in-depth over A1 triggers

Total PRD v1.1 amendments queued: **26**.

## PLAN.md amendments

Insert into PLAN.md after Phase 1.5b and before Phase 2:

- **Phase 1.5c** (new gate) — adopt A24–A30 into Track A scope BEFORE worktree dispatch. Does not produce code on its own; this is the spec-amendment moment. Outputs:
  - Track A scope expanded with: `repositories/evidence/` + `repositories/runtime/` modules per A24; `storage/transaction.py`, `storage/dual_write.py`, `storage/context.py` per A25/A28; new migration `0003_admissible_verdicts_view.sql` per A29
  - Track A exit criteria expanded with: AST-walker test green; admissible_verdicts VIEW tests (3) green; A3 write-time-snapshot falsifying-case test green; `discover()` duplicate-version guard test green; two-property Hypothesis test (P1 generic + P2 runs) green; savepoint fixture in conftest
  - PLAN's "Named council fire points" row 2 marked ✅ FIRED 2026-06-04 (this fire)
  - PLAN's `migrations/README.md` requirement noted as Track A deliverable
  - PLAN's `.github/CODEOWNERS` requirement noted as Track A or parallel deliverable

## Cross-talk validation

Per `cross-talk-council-dispatch` synthesis pass: did cross-predictions land?

### Score: 6/12 prediction targets landed, 4 missed, 2 inverted

1. **SCHEMA predicted RELIABILITY will surface Q2 "evidence first" + reconciler shape** → ✅ landed (RELIABILITY Q2: "Evidence wins, runtime is reconcilable")
2. **SCHEMA predicted SECURITY will sharpen Q6 (admissibility filter) as security-critical** → ✅ landed (SECURITY Q6 BLOCKER, "F2-shaped trap")
3. **SCHEMA predicted TEST-ARCH will catch the `runs.completed_at` exemption trap in Q4** → ✅ landed (TEST-ARCH Q4: "the runs.completed_at single-shot allowed transition" carved into P2)
4. **SCHEMA predicted SECURITY will under-name the ATTACH boundary** → ✗ MISSED (SECURITY did not raise ATTACH at all; SCHEMA's framing stands unchallenged)
5. **RELIABILITY predicted SECURITY will re-litigate A22's synchronous=FULL/NORMAL split** → ✗ MISSED (SECURITY did NOT re-litigate; locked decisions held)
6. **RELIABILITY predicted SCHEMA will own Q1 row-shape modeling** → ✅ landed (SCHEMA Q1 was the most detailed on row shape)
7. **RELIABILITY predicted TEST-ARCH will fold crash-injection INTO Hypothesis** → ✗ INVERTED (TEST-ARCH explicitly separated families, mirroring RELIABILITY's framing)
8. **SECURITY predicted SCHEMA will propose DB-layer CHECK for `output_text` size** → ✗ MISSED (SCHEMA did not raise size limits)
9. **SECURITY predicted RELIABILITY will propose runtime PRAGMA-check on every repo connection** → ✗ MISSED (RELIABILITY did not propose this)
10. **SECURITY predicted TEST-ARCH will over-trust Hypothesis as Q6 defense** → ✗ INVERTED (TEST-ARCH explicitly proposed the SQL VIEW as the structural defense, with Hypothesis as a falsifying-case mechanism — same as SECURITY's framing)
11. **TEST-ARCH predicted SCHEMA will push back on `runs` carve-out as "ugly"** → ✗ MISSED (SCHEMA proposed the same carve-out independently, Q4 description)
12. **TEST-ARCH predicted SECURITY will name Q4 gap-list (confound, calibration drift, cross-DB) as untestable** → ✗ MISSED (SECURITY did not enumerate)

Cross-talk yield analysis:

- **Convergence robustness**: 5 of 7 questions had unanimous severity-direction agreement (Q1, Q3, Q5, Q6, Q7 all agreed on disposition direction; severity-magnitude varied). That's healthy convergence.
- **Substantive disagreement surfaced cleanly**: Q2 ordering dispute was the dispatch's highest-value output — orchestrator resolved by citing PRD Track D's pre-call cap check, which mooted SECURITY's premise without dismissing the framing. That's exactly the cross-talk-dispatch use case.
- **Cross-prediction quality was middling**: 6/12 hits is below the 7/8 from the Phase 1.5 fire. Lower lens-distinctness this round (RELIABILITY + TEST-ARCH overlap on test discipline; SCHEMA + RELIABILITY overlap on durability framing). For the next storage-touching fire, consider firing only 3 seats (drop one of the overlapping pair) OR sharpen the seat briefs to emphasize lens distinctness.

### Substantive convergent finding (cross-talk yield)

**RELIABILITY's "separate test families" framing for Q4** combined with **TEST-ARCH's "savepoint fixture for Hypothesis" framing for Q5** combined with **SECURITY's "structural pre-commit grep enforcement" framing for Q5** = a coherent test infrastructure shape that no single seat would have produced. Adopted into A27 + A28.

## Citation verification

Per `subagent-research-reliability`, external citations adopted into synthesis verified against canonical sources already in `docs/COUNCIL_FINDINGS.md § Verified external citations`:

- SQLite WAL semantics + ATTACH interaction (https://www.sqlite.org/wal.html) — already verified
- SQLite `BEGIN IMMEDIATE` + `busy_timeout` (https://www.sqlite.org/lang_transaction.html, https://www.sqlite.org/pragma.html) — already verified
- Python `sqlite3.complete_statement` semantics (already verified Phase 1.5)
- Hypothesis `@settings`, `@composite`, `RuleBasedStateMachine` (https://hypothesis.readthedocs.io/) — new canonical source for this fire; no novel claims made

No external citations required additional verification this fire.
