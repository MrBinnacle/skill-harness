# SECURITY seat — Pre-Track-A implementation review (2026-06-04)

**Threat model default**: local-trust v0.1 per `SECURITY.md:39-46` and A23. Single operator, single host, filesystem integrity assumed. In-scope attackers: accidental developer mutation, dependency-tree compromise (passive), filesystem-adjacent same-UID actor. Out-of-scope: remote network attacker, multi-tenant host, hostile SDK substitution. I flag explicitly where a recommendation would extend the model.

## Q1 — Repository pattern shape
- **Disposition**: MAJOR
- **Claim**: Pydantic `strict=True` at the repository write boundary is non-negotiable per `SECURITY.md:36` and CLAUDE.md §3 "Validate all user input at boundaries." The boundary is the repo function, not the CLI: a verdict's `output_text` (subject model) and judge-prompt-derived fields are attacker-influenced under the prompt-injection-in-judged-outputs surface (`SECURITY.md:48`). NUL bytes in TEXT columns are SQLite-legal but corrupt downstream tooling (sqlite3 CLI truncates at `\x00`); embedded control chars in `clause_text` / `output_text` poison `diff skill` rendering and any future log shipping. Oversized blobs (judge output > 1 MB) bypass any de facto budget assumption — needs a documented cap (proposal: 256 KB per `output_text`, `RAISE` at repo if exceeded). For UPDATE/DELETE prohibition on evidence repos: belt-and-braces (mypy-typed `NoReturn`-style absence at API + DB triggers from A1). Do not rely on mypy alone — A1 already proved application-only contract is bypassable. Per-table modules, functional API (`insert_oracle_verdict(conn, *, ...)`), shared SQL via a small `_sql.py` is fine; query-builder is out-of-scope dependency expansion.
- **Evidence**: `SECURITY.md:36`, `SECURITY.md:48`, `migrations/evidence/0001_initial.sql:103` (`output_text TEXT NOT NULL` — no size CHECK), CLAUDE.md §3 "Validate all user input at boundaries."
- **Recommendation**: Track A spec: (a) every evidence-write function takes a `Pydantic BaseModel` with `model_config = ConfigDict(strict=True, extra='forbid')`; (b) per-model `field_validator` rejects NUL bytes (`'\x00' in s`) and non-printable C0 controls except `\t\n\r`; (c) `output_text` and `clause_text` carry a max-length validator (256 KB / 64 KB respectively, configurable); (d) evidence repos export only `insert_*` and `get_*` — no `update_*`/`delete_*` symbols at all.
- **What-would-change-it**: If `output_text` ever carries large structured artifacts, the size cap moves; flag as a PRD §17 revisit.
- **Cross-seat**: SCHEMA co-owns the size-cap-as-CHECK question; TEST-ARCH owns Q4 fuzzing strategy that exercises these validators.

## Q2 — Dual-DB transaction primitive
- **Disposition**: MAJOR
- **Claim**: No 2PC; the partial-write threat must be bounded by ordering. The asymmetry of failures is the security argument: **evidence-then-runtime ordering** means the worst failure is "verdict recorded, cost ledger missed" — verdicts unaccounted, budget caps bypassable by an attacker that can engineer crashes (`SECURITY.md:48` "Cost overrun via prompt injection"). **Runtime-then-evidence ordering** means worst case is "cost row written, verdict missed" — observable phantom-API-call signal, no evidence-side lie. The latter is the right SECURITY ordering: the evidence DB stays the source of truth and any drift is detectable by audit. A budget bypass via crash-engineered ordering remains bounded because A2's `--max-usd` is checked **before** the API call, not after (per PLAN Track D exit criterion: "Budget check inside writer transaction").
- **Evidence**: A2 (`docs/COUNCIL_FINDINGS.md:22-25`), `SECURITY.md:48`, `migrations/runtime/0001_initial.sql:62-74` (`cost_ledger`).
- **Recommendation**: Track A spec: dual-DB write helper takes `(evidence_conn, runtime_conn, evidence_writes, runtime_writes)`. Order: `runtime BEGIN IMMEDIATE` → runtime writes → `runtime COMMIT` → `evidence BEGIN IMMEDIATE` → evidence writes → `evidence COMMIT`. On evidence-side failure: log structured `dual_db_drift` event.
- **What-would-change-it**: If budget enforcement moves to post-call accounting, ordering flips.
- **Cross-seat**: RELIABILITY co-owns the ordering. I will defer if they show a partition-tolerance argument that overrides the audit-asymmetry one.

## Q3 — Single-writer queue
- **Disposition**: MINOR
- **Claim**: v0.1 threat model bounds this. A "malicious subagent" producing unbounded malformed verdicts is **not in scope** — Track B extractor and Track C judge run in-process under the operator's UID; they are trust-equivalent to the harness. Unbounded queue is a reliability concern (memory exhaustion on long runs), not a security one. Admission-control adds complexity for a v0.1 non-threat. Cross-process compromise (a dep gains code execution and pivots to spam writes) is in-scope per `SECURITY.md:41`, but the attacker already has same-UID write access to the DB files directly — DoS-via-queue is not the weakest link. Recommend `threading.Lock` (in-process), bounded `queue.Queue(maxsize=1024)` with producer-block-on-full as a reliability backstop, NOT admission control.
- **Evidence**: `SECURITY.md:41`, A2 (single-writer per DB).
- **Recommendation**: Track A spec: `threading.Lock` per `Connection`; bounded queue with producer-block; structured-log on queue depth > 75% as observability. No security-motivated rate limiting in v0.1.
- **What-would-change-it**: Multi-process workers, or moving to a server model where Track B/C are network-reachable.
- **Cross-seat**: RELIABILITY owns the queue-shape decision.

## Q4 — Property-based test design
- **Disposition**: MAJOR
- **Claim**: Hypothesis strategies MUST run against an **ephemeral tmp-path DB**, never the operator's real `evidence.db`. A leaked test verdict in the audit trail is itself an integrity attack on the append-only guarantee (and the SHA tamper-evidence ledger has no story for "the row is real but was test data"). Adversarial input strategy must cover: NUL-byte TEXT, surrogate-half UTF-8, CHECK-edge values (`oracle_tier=0`, `oracle_tier=4`, `observation=0.5+ε`, NaN), FK-violating IDs, oversized blobs at the cap boundary, and mixed-CHECK combinations (`oracle_tier=2 AND judge_id IS NULL` — the CHECK at `0001_initial.sql:133-137` should reject; test it). Cleanup: `pytest` `tmp_path` fixture + per-test DB file, never `:memory:` for triggers smoke (WAL pragma interaction).
- **Evidence**: `migrations/evidence/0001_initial.sql:121` (`observation` CHECK), `:133-137` (tier/judge cross-CHECK), `:14-17` (schema_migrations triggers).
- **Recommendation**: Track A spec: `tests/property/conftest.py` provides an `evidence_db_ephemeral` fixture (`tmp_path / "evidence.db"`, full migration apply, teardown unlinks); all property tests use it. Add explicit `@given` strategy `adversarial_text()` exporting the NUL/control/oversized corpus for reuse across repos.
- **What-would-change-it**: Nothing within v0.1 scope.
- **Cross-seat**: TEST-ARCH owns the falsifiability design; SECURITY supplies the adversarial corpus.

## Q5 — Connection lifecycle
- **Disposition**: MAJOR
- **Claim**: A23 noted PR review is the current enforcement — that was acceptable while only `migrations.py` opened connections. **Track A is exactly the moment that breaks.** Per-repo `sqlite3.connect()` bypasses are now plausible developer-error surface, and PR review is a humans-don't-scale defense. The right v0.1 fix is **structural**, not runtime: repositories take a `Connection` parameter; they do NOT call `sqlite3.connect()` themselves. The session/lifecycle owner is a single `with open_evidence(...) as conn` context-manager wrapper in `cli/main.py` (and equivalently in tests via fixture). Add a one-line ruff custom rule or grep-based pre-commit hook: `sqlite3\.connect\(` outside `migrations.py` fails CI. Runtime PRAGMA-check on every repo call is gold-plating.
- **Evidence**: `migrations.py:208-213` (PRAGMA scope), A23 / `SECURITY.md:58-62`, CLAUDE.md "Repository module per table."
- **Recommendation**: Track A spec: (a) all repos take `conn: sqlite3.Connection` as first param; (b) add `open_evidence`/`open_runtime` as `@contextmanager` wrappers; (c) pre-commit `ripgrep -n 'sqlite3\.connect\(' src/ tests/ | grep -v 'storage/migrations.py'` fails non-empty; (d) one smoke test asserting `PRAGMA foreign_keys` returns 1 on a freshly-opened repo connection.
- **What-would-change-it**: If a future Track needs raw `sqlite3.connect`, document the bypass as an explicit `open_audit_readonly()` helper.
- **Cross-seat**: SCHEMA co-owns (their A23 framing); RELIABILITY owns the context-manager-vs-long-lived call.

## Q6 — Admissibility filter on read
- **Disposition**: BLOCKER
- **Claim**: This is the F2-shaped trap from Phase 1.5: a silent default that makes inadmissible evidence indistinguishable from clean output. The default MUST be **filtered**, and the filter MUST live at the **SQL layer**, not Python. Two reasons. First: a Python-layer filter requires every caller to remember to call it; a missed filter call in Track E produces a forgeable clean-bill-of-health — same threat shape as F2/A23. Second: aggregation queries in Track E will be authored as raw SQL (`SELECT ... GROUP BY clause_id`); the Python wrapper is not in the call path of an analyst running an ad-hoc `sqlite3` query. SQL-layer enforcement via a **VIEW** (`CREATE VIEW admissible_verdicts AS SELECT * FROM oracle_verdicts WHERE admissibility_state = 'admissible' AND verdict_id NOT IN (SELECT ... FROM confound_events WHERE delta_kind='confound_flagged')`) makes the default safe and the bypass loud.
- **Evidence**: CLAUDE.md "Aggregation rules"; my F2 from Phase 1.5.
- **Recommendation**: Track A spec: new migration `0003_admissible_verdicts_view.sql` creates `admissible_verdicts` VIEW joining the confound-exclusion. Track E aggregation queries MUST query the VIEW. Repository APIs expose `get_admissible_verdicts(run_id)` (filtered, default) and `audit_all_verdicts(run_id)` (unfiltered, named loudly). A grep rule: any code outside `audit/` that uses raw `oracle_verdicts` in a `SELECT` fails CI.
- **What-would-change-it**: If the confound-non-confound state is determined at read time from `confound_events` joins that become too expensive, the VIEW becomes a materialized concept — but that violates A3's "never recomputed" intent.
- **Cross-seat**: SCHEMA co-owns the VIEW vs denormalized-column choice; TEST-ARCH owns the falsifying test.

## Q7 — Migration sequencing across worktrees
- **Disposition**: MAJOR
- **Claim**: Two threats. (1) **Merge collision** is process — number-the-migration-on-merge is a known git pattern and not security-load-bearing. (2) **Malicious `0003_attack.sql`** is the real concern. The SHA tamper-evidence ledger (A4) catches **modifications** to recorded migrations but explicitly does NOT catch **new** migrations — a new file applies on next open. This is structurally a supply-chain-via-PR threat. The defense already exists in `PLAN.md:218`: "Pre-merge for any PR touching `migrations/` — Storage-touching change | SCHEMA + RELIABILITY + SECURITY + TEST-ARCH." This is process, but it is the right process and must be a **CODEOWNERS-enforced required review**, not a discretionary council fire that gets skipped under deadline pressure.
- **Evidence**: `PLAN.md:218`, A4, `dev-team-council` SKILL.md "Pre-merge for any PR touching migrations/."
- **Recommendation**: Track A spec: ship `.github/CODEOWNERS` with `migrations/* @<security-seat-owner> @<schema-seat-owner>` and configure branch protection. Add `docs/council-fires/_TEMPLATE_pre-merge-migrations.md` referencing the four required seats.
- **What-would-change-it**: A move to a single-maintainer model downgrades to MINOR; an open-source release of v0.1 escalates to BLOCKER.
- **Cross-seat**: This is a process / governance call. SCHEMA co-owns migration review.

## Cross-talk

- **SCHEMA**: RIGHT — will spec Q1's per-table repo modules cleanly and align Q6's admissibility VIEW with A3's "never recompute" framing. WRONG — likely to propose adding a `text_length` CHECK constraint on `output_text` at the SQL layer, which interacts badly with my Q1 Pydantic-layer cap (two sources of truth). Push for ONE owner of the limit. MISS — Q3's queue-as-supply-chain-DoS frame is not their lens.
- **RELIABILITY**: RIGHT — will own Q2 ordering with a durability argument and will likely propose evidence-first (durability-of-the-canonical-record), which conflicts with my audit-asymmetry argument. Expect productive disagreement. WRONG — likely to propose a runtime PRAGMA-check on every repo connection (Q5) as a "defense-in-depth" measure. Structural enforcement is stronger. MISS — Q7's CODEOWNERS frame is process-level governance; RELIABILITY's lens is structurally weak there.
- **TEST-ARCH**: RIGHT — will own Q4 falsifiability design and produce a strong adversarial-input fixture spec. WRONG — likely to propose Hypothesis as the falsifying-case mechanism for Q6 admissibility filter. Good intent, but a Hypothesis test only validates the queries you wrote; the SQL-layer VIEW is the structural defense. MISS — Q2 dual-DB ordering's threat-asymmetry argument is a security frame, not a falsifiability frame.

STATUS: BLOCKER-FOUND
