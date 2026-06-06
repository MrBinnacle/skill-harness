# Track D.3 — Re-Review Disposition + Fix Brief

The D.3 CLI deliverable (commit `81580eb`, branch `worktree-agent-a6321f61800e1da3f`)
passed all gates (602 passed, mypy --strict clean, ruff clean) but a 3-seat parallel
re-review (SPEC-COMPLIANCE, TEST-ARCH, RELIABILITY — opus, read-only, isolated; dispatch
per `cross-talk-council-dispatch` + `parallel-review-disposition-schema`) found the green
to be partly hollow: load-bearing spend-safety branches are stubbed but covered only by
tests that patch the stub. This is the same failure mode that triggered the D.2 fix-loop.

## Disposition (convergence ≥2 seats unless noted)

### BLOCKERs
- **B1 — A52 double-spend guard is dead code.** `_find_incomplete_run()` body is
  `return None` (`cli/main.py:387-395`); the bare-rerun guard at `:517-526` never fires in
  production. A bare `run ablation <skill> --execute` against an incomplete prior run mints
  a NEW `run_id` (`runner.py:323-324`) and re-spends the full per-clause budget on top of
  the orphaned partial run. Green test patches the stub to a fake id → false positive.
  (RELIABILITY + TEST-ARCH BLOCKER; SPEC BLOCKER-adjacent.)
- **B2 — A42 `--daily-cap` unenforced on `run ablation`.** `daily_cap` dead-ends at the
  dry-run print (`:295`); never passed into `_execute_ablation_run` (no param at `:398-405`)
  nor the runner; no trailing-24h spend computed anywhere; `_DailyCapExceededError` raised
  nowhere in src (only caught at `:551`, raised by tests as `side_effect`). The flag is
  exposed as functional but does nothing. (`calibrate` DOES enforce it via
  `validate_daily_cap` `:776` — gap is specific to `run ablation`.) (RELIABILITY BLOCKER;
  SPEC MAJOR; TEST-ARCH OBS.)

### MAJORs
- **M1 — Dry-run per-clause table is a static placeholder.** One hardcoded row
  (`axis="—"`, `est_CI_width="~0.55"`, `status="TESTABLE"`) at `:307-326`; status enum
  {VACUOUS-EXCLUDED | NO-FALSIFYING-CASE} never emitted; test asserts header words only.
  (SPEC MAJOR x2, TEST-ARCH MAJOR.) **See A51 ruling below — this is fixable.**
- **M2 — CLI→runner integration untested.** Every `--execute` test patches
  `_execute_ablation_run`; the real wiring (StorageContext open, operator/renderer/subject
  construction, `_load_clauses_from_db`, runner dispatch on `resume_run_id`) is never
  exercised. Signature drift / wrong kwarg / broken clause-load ships green. (TEST-ARCH
  MAJOR; RELIABILITY + SPEC cross-talk.)
- **M3 — `_load_clauses_from_db` zero coverage** (`:458-492`): SQL query, `--clause` filter,
  `ClauseSpec` construction, and the "no testable clauses" ClickException all untested.
- **M4 — `rich.progress` dual-cap footer absent.** §D.3 line 79 + PLAN.md:220 require a
  per-clause bar + live `spent $X / cap $Y (run) · $Z / $W (day)` footer during `--execute`;
  no progress rendering exists. (SPEC MAJOR.)

### MINORs
- **m1 — `--show-rendered` / `_render_conditions_for_clause` emit `[clause: {id}]` stand-in**
  (`:381`), not the real clause text — undermines the inspect-for-trust purpose of the flag.
- **m2 — resume passes `user_message=""`** (`:444,451`), not loaded from `runs.config_json`
  → resumed samples re-render with an empty task prompt, producing incoherent evidence.
- **m3 — no API-key pre-flight on `--execute`** (`SubjectClient()` at `:417`): a missing key
  surfaces deep in the first call AFTER a run row + budget row are written, orphaning a
  `running` run_progress row the (stubbed) finder can't later detect.
- **m4 — exit-code 1 collision** (SPEC/RELIABILITY cross-talk): bare-rerun guard + budget
  abort exit 1, same as click's generic error; A48 reserves non-2 for hard errors. Keep
  UNMEASURED=2 distinct; ensure refusals are intentional exit-1 (acceptable), not accidental.

### Confirmed-good (NOMINAL — do not touch)
Per-run `--max-usd` wired + enforced in runner (`:448-453` → `runner.py:711-720/899-920`);
`--resume` reaches real `resume_ablation` set-difference (re-derives from evidence);
exit codes 0/2; A50 contribution + absence caveats real (`:626-655`); `--max-usd` error
naming real (`:545-550`); no scope creep, command set matches PRD §18.

## Orchestrator ruling — A51 dry-run / DB-read clarification

`run ablation` takes a **`skill_id`** (DB-resident clauses), not a path; the per-clause
projection table therefore requires reading evidence.db, which conflicts with the brief's
"constructs no DB conn." The brief demands BOTH the table-with-status-enum AND "no DB conn",
so "no DB conn" is read as shorthand for **no API client / no API key / no spend / no
writes** — NOT "zero DB handles." **Ruling: dry-run MAY open evidence.db READ-ONLY**
(`mode=ro` / immutable URI) to enumerate clauses and render the real projection; it still
constructs no SDK client, requires no `ANTHROPIC_API_KEY`, makes no API calls, and performs
no writes. **Flip condition:** if dry-run must run with zero local state (fresh checkout /
skill not yet imported), revert to the generic projection and amend the brief to drop the
per-clause table for the `skill_id` form. Queued as an A51 clarification for the doc-lock PR.

## A51 micro-council ratification (2026-06-06) — RATIFY-WITH-AMENDMENT (3–0 on substance)

3-seat fire (OPERATOR-DX, RELIABILITY, SECURITY; opus, read-only; cross-talk + disposition
schema). Votes: ODX RATIFY-WITH-AMENDMENT · SECURITY RATIFY-WITH-AMENDMENT · RELIABILITY
REJECT-as-written → flips to RATIFY once a sanctioned read-only helper exists (its own flip
condition == the others' precondition, so the substantive consensus is unanimous).

**Load-bearing cross-talk yield:** SECURITY verified the TC-SLOP-001/002 origin
(`docs/reviews/2026-06-05-track-c-slop-review.md:22-26`) is a *cost/offline-ergonomics*
finding, NOT a state-isolation guarantee — so "no DB conn" carries no load-bearing security
weight, and a read-only read does not breach the A23 trust partition (which binds write /
admissibility integrity, not read isolation) under the v0.1 local-trust model
(`SECURITY.md:41`). RELIABILITY verified no sanctioned read-only entry exists today
(`storage/migrations.py`: `open_evidence` calls `apply_pending`; `open_db` hard-codes WAL +
`synchronous=FULL`, no `mode=ro`), so the read-only read is unimplementable without a new
helper and must NOT be hand-rolled via raw `sqlite3.connect()` (forbidden by A23 §3).

**Ratified amendment (union of all three seats' guardrails) — supersedes the earlier ruling:**
1. **Formal text amendment (not silent reinterpretation).** Amend A51 / PLAN.md:208 / brief
   §D.3 wording from "no DB conn" → **"no *writable* DB conn, no migration-apply, no client,
   no API key, no API call, no write; MAY open `evidence.db` READ-ONLY via the sanctioned
   storage entry to enumerate imported clauses."** Queue as an A51 clarification for the
   doc-lock PR (do not edit PRD piecemeal); the brief + PLAN exit-criteria line update is
   needed now for the test wording ("no writable conn / no migration apply", not "no conn").
2. **New sanctioned helper `open_evidence_readonly()`** in the storage layer (this is the
   council-blessed storage change): opens `file:…?mode=ro` (NOT `immutable=1` — that assumes
   the file won't change under a concurrent `--execute`; `mode=ro` is correct for a possibly-
   concurrent WAL DB) **through `open_db`**; sets `PRAGMA query_only = ON`; does **NOT** call
   `apply_pending`; **raises `BootstrapError` (does NOT create) when the file is absent**.
3. **DB path from sanctioned config only**; `skill_id` used solely as a parameterized query
   value — no path component, no string-built SQL (closes path-traversal / malicious-skill_id).
4. **Output-side sanitization** of `clause_text` on render (assert NUL/control-free per A24 at
   read + escape on display) — defense-in-depth, since the file is filesystem-substitutable.
5. **Zero-state default is non-conditional**: skill not imported / db missing / migration-stale
   → clear message `skill not imported — run 'skill init <path>' first`, never a silent empty
   table or a stack trace; the read path must not be mistaken by the crash-reconciler as a run
   touch.
6. Keep the real invariants intact: NO `JudgeClient`, NO API key, NO API call, NO write, and
   the terminal line `NO CALLS MADE — re-run with --execute`.

**Flip-to-REJECT condition (SECURITY):** if dry-run ever resolves `evidence.db` from an
attacker-influenced path (env/arg) rather than sanctioned config, or v0.2 promotes the threat
model beyond local-trust. **Moot-the-framing condition (ODX):** if clause inventory does not
live in `evidence.db`.

> **M1 is re-scoped by this ratification** — see revised item 3 below. The storage-helper
> addition is council-blessed (RELIABILITY specified the contract, SECURITY the guardrails);
> SCHEMA's lens is not implicated (no schema/migration change, read-only connection only).

## Fix plan (TDD: write the falsifying test first, prove RED, then GREEN)

1. **B1** — implement `_find_incomplete_run`: query `runtime.run_progress` for this skill_id
   where `state NOT IN ('completed','failed','aborted_budget')`; return its `run_id` (or None).
   Bare `--execute` with an incomplete run → WARN + name run_id + refuse (point at `--resume`).
   Test (UNPATCHED): seed a `state='running'` run_progress row, assert the real function
   returns it; integration test that bare rerun warns + names id + does not start a fresh run.
2. **B2** — compute trailing-24h `SUM(usd)` from `runtime.cost_ledger`; refuse run start if it
   would exceed `--daily-cap`; raise `_DailyCapExceededError` from production. Wire `daily_cap`
   into the pre-run path. Test (UNPATCHED): seed cost_ledger near cap, assert refusal naming
   `--daily-cap`. (Confirm cost_ledger has a timestamp column; if not, flag — do NOT alter the
   migration/schema, that is a SCHEMA-council change.)
3. **M1 (RE-SCOPED by the A51 ratification above)** — two parts:
   (a) **Add the council-blessed storage helper** `open_evidence_readonly(path)` (in
   `storage/migrations.py` alongside `open_evidence`): opens `file:<path>?mode=ro` THROUGH
   `open_db` (reuse its pragma/FK discipline; `mode=ro`, NOT `immutable=1`); sets
   `PRAGMA query_only = ON`; does NOT call `apply_pending`; raises `BootstrapError` (does NOT
   create) when the file is absent. Unit-test it: read-only open of a seeded DB succeeds and
   reads committed rows; an attempted write raises; a missing file raises `BootstrapError`
   (not create). This is the ONLY sanctioned storage change; do not touch schema/migrations.
   (b) **Build the real dry-run table** using that helper: enumerate the skill's clauses,
   render columns clause# / axis / conditions / N_proj(min..max) / est_CI_width / status with
   status from `vacuity_flag` + falsifying-case presence → {TESTABLE | VACUOUS-EXCLUDED |
   NO-FALSIFYING-CASE}. DB path from sanctioned config only; `skill_id` as a parameterized
   query value (no path component, no string SQL). Output-side-sanitize `clause_text`
   (NUL/control-free assert + escape). Keep NO client/key/call/write + terminal
   `NO CALLS MADE — re-run with --execute`. **Zero-state default (non-conditional):** skill
   not imported / db missing / migration-stale → print `skill not imported — run 'skill init
   <path>' first`, never a silent empty table or stack trace. Tests (UNPATCHED dry-run):
   mixed-vacuity clauses → real rows + correct statuses; skill_id absent → the clean
   not-imported message (not a crash, not an empty table).
4. **M2 + M3** — add an end-to-end execute test that monkeypatches ONLY `SubjectClient` (the
   sole network surface) to a canned sampler, seeds evidence.db via the skill-init fixture,
   runs `run ablation <skill_id> --execute`, and asserts a real `ClauseResult` table renders.
   Do NOT patch `_execute_ablation_run` or `_find_incomplete_run`. Add a direct
   `_load_clauses_from_db` test (all + `--clause` filter + no-testable-clauses error).
5. **M4** — render `rich.progress` per-clause + the live dual-cap footer during `--execute`,
   emitted from the deterministic CLI orchestrator. If a runner hook is needed, the ONE
   permitted touch to `ablation/runner.py` is an ADDITIVE optional `progress_callback=None`
   param (no behavior change when None) — flag it loudly for re-review. Test asserts the
   footer format appears.
6. **m1** — load real clause text (read-only DB) for `--show-rendered` instead of the
   placeholder; test asserts non-placeholder verbatim text.
7. **m2** — load `user_message`/task prompt from `runs.config_json` on resume.
8. **m3** — pre-flight `ANTHROPIC_API_KEY` presence before the first DB write on `--execute`;
   clean refusal, no orphan row.
9. **m4** — keep UNMEASURED=2 distinct; ensure exit-1 paths are intentional refusals.

## Re-review verification (2026-06-06) — fix-loop CLEARED to land

Fix-loop commits on `worktree-agent-a6321f61800e1da3f`: `00e3008` (fixes) + `8641485`
(repo-wide ruff lint, applied by orchestrator). Orchestrator hub-verified (not seat-fanned —
the fixes were council-blessed and the BLOCKER tests are directly readable as unpatched):
- **Gates (independently re-run on the worktree):** 633 passed / 1 deselected · `mypy
  --strict` clean (59 files) · `ruff check src/ tests/` clean · `ruff format --check` clean.
- **B1 (A52) genuinely closed:** `_find_incomplete_run` queries real `runtime.run_progress`;
  new tests seed a real row and call it UNPATCHED (`test_cli_d3_fixes.py:194-245`); the
  bare-rerun integration test leaves it unpatched and only spies `_execute_ablation_run`.
- **B2 (A42) closed:** `_check_daily_cap` computes trailing-24h `SUM(usd)` from real
  `cost_ledger` (`ts` column, indexed), refuses before any write; tested unpatched.
- **M1:** `open_evidence_readonly` (`migrations.py:280-309`) matches the ratified contract
  exactly (`mode=ro` via `open_db`, `query_only=ON`, no `apply_pending`, raises not creates);
  real per-clause table renders all three statuses; zero-state prints the not-imported line.
- **M2/M3/M4/m1-m4:** integration test patches ONLY `SubjectClient`; `_load_clauses_from_db`,
  `_load_user_message_from_run`, API-key pre-flight (no orphan row), exit-code distinctness
  (refusals=1, UNMEASURED=2) all covered unpatched. `runner.py` NOT touched.
- **Orchestrator caught:** agent ran `ruff check src/` only (missed 2 trivial lint issues in
  the new test file) — fixed in `8641485`.

**Accepted v0.1 limitation (carry-forward, not a blocker):** `_find_incomplete_run` returns
the first non-terminal `run_progress` row regardless of `skill_id` (no `skill_id` column on
`run_progress`; cross-DB join forbidden by A25). It is CONSERVATIVE — over-warns, never
under-warns, so it can never silently double-spend. Cheap skill-accurate fix (carry-forward):
fetch non-terminal run_ids from `runtime.run_progress`, resolve each via `evidence.runs.skill_id`
in Python (two-step, no schema change). Same class as TA-4 / the SEC judge-injection caveat.

## Carry-forwards into Track E / later
- **CF-D3-1**: skill-accurate `_find_incomplete_run` (two-step runtime→evidence lookup).
- **A51 text amendment** (doc-lock queue): "no DB conn" → "no writable conn / no migration
  apply; MAY open evidence.db read-only via sanctioned entry" in A51 / PLAN.md:208 / brief §D.3.
- **TA-4** (from D.2): per-verdict family_size on RunConfig; Track E re-derives.
- **SEC**: re-audit subject output_text → judge-system-prompt interpolation when Tier-2 judge wired.

### Invariants (unchanged — review-block any violation)
Deterministic Python owns control flow; dry-run makes no API call + needs no key + no writes;
UNMEASURED never PASSED/FAILED; append-only evidence, never raw `sqlite3.connect()`; CLI set
locked (flags only). Gates per subtrack: `pytest -q -m "not live"` green · `mypy --strict`
clean · `ruff check` + `ruff format --check` clean. Do NOT modify `migrations/` or storage
schema; if the fix seems to need that, STOP and return.
