# Phase 3.4 — code-review-sentinel Disposition + Fix Brief

Single Opus 4.7 code-review-sentinel reviewer (fresh context, read-only) on the
cumulative diff `dbcbc91..32f3ad4` (Track E.1+E.2+E.3 + Phase 3.2 ai-slop fix-loop
+ Phase 3.3 mutation-testing fix-loop + Phase 3.5 audit doc + CF-E3-1 + T8). 7
commits, ~9000 line diff (audit doc excluded from review scope).

**STATUS: FINDINGS-NEEDS-FIX. 0 hub-verified CRITICALs at the load-bearing
invariant level. 4 IMPORTANTs (1 security, 3 correctness/integration). 7 MINORs
(4 cosmetic, 3 uncertain). 1 finding is a CARRYOVER from a prior orchestrator
drafting error — disclosed below.**

The 2 strongest IMPORTANTs (S1 fail-open precondition, I1 NaN-in-JSON) were
**hub-verified by direct code read + grep** before this disposition.

## Verified IMPORTANTs (block v0.1 tag)

### S1 · `recovery.py:54-55, 74-75` fail-open on bare `Exception` (precondition bypass risk)
`find_incomplete_runs` has TWO `except Exception: return []` blocks (runtime query
at L54-55 + evidence query at L74-75). Both fail-open. Hub-verified by direct
read.

Downstream callers (`aggregate_skill` at `engine.py:75-82`; `cli/main.py:1029-1040`
evaluate-skill; `cli/main.py:1211-1219` diff_skill) treat an empty list from
`find_incomplete_runs` as "no incomplete runs → proceed to aggregate." A
corrupted DB, missing `run_progress` table, or any other `sqlite3.OperationalError`
silently bypasses the A52/A54 precondition. CLAUDE.md "fail closed on
admissibility" applies — the precondition check is admissibility-equivalent
(gates aggregation eligibility). Asymmetric with `run_is_complete` (L115-116)
which DOES fail closed (`return False` — refuses freeze if it can't verify
completion); the asymmetry confirms `find_incomplete_runs` is the slip.

**Fix:** narrow both `except Exception` blocks to `except sqlite3.Error as exc:`
and either re-raise wrapped as `PreconditionError("recovery_query_failed", ...) from exc`,
or let `sqlite3.Error` propagate to the CLI's `click.ClickException` handler. Do
not silently return `[]`. **Falsifying test:** drop the `run_progress` table on a
test runtime DB, call `find_incomplete_runs(...)`; current code returns `[]`,
correct code raises.

### I1 · `aggregation_provenance.attempted` may contain NaN floats → invalid JSON (RFC 8259 violation)
`fit.py:291-298` raises `ConvergenceFailure(alpha_hat=float("nan"), beta_hat=float("nan"), ...)`
on `var_below_threshold`. `fit.py:224-229` packs those NaN floats into the
`attempted` dict. `engine.py` propagates them into `SkillReport.aggregation_provenance`.
`report.py:178` calls `json.dumps(d, sort_keys=True, separators=(",", ":"))` with
**default `allow_nan=True`** — emits literal `NaN` in the byte stream. Hub-verified
by direct read.

A60 invariant says "JSON byte-stable + schema version" — bytes ARE stable across
runs (NaN literal string matches), but the output fails strict RFC 8259 parsers
(jq, Postgres jsonb, Node strict, schema validators). Any downstream consumer
doing strict JSON validation will reject the report when the BH-FDR fallback
triggers with `var_below_threshold`. Phase 3.3 fix-loop's M10/M11 verified
`fallback_reason` + `attempted` are populated but did NOT verify strict JSON
roundtrip.

**Fix:** replace NaN with `None` at the raise site in `fit.py:291-298` (the
provenance use case doesn't need NaN sentinel — `None` is the correct
"not-computable" value), AND set `to_json_bytes` to `json.dumps(..., allow_nan=False)`
so future NaN regressions surface loudly at write time. **Falsifying test:**
construct a 10-clause input where all clauses share `w/n` → `sample_var = 0 <
VAR_FLOOR`. Run `fit_skill`; call `to_json_bytes(report)`; parse with
`json.loads(bytes, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))`.
RED on current code; GREEN on fix.

### I2 · `engine.py:204-213` silently drops intra-skill `ablation_operator_hash` divergence (asymmetric with subject_model)
`op_hash` is captured per run from `runs.config_json` via
`clause_axis_operator_hash.setdefault(key, op_hash)` — **first-write-wins** per
`(clause_id, axis)`, silently discarding divergent values from subsequent runs.
Compare to `_derive_a55_fields` (engine.py:558-602) which DOES detect
subject_model divergence and sets `"MIXED"` with a warning per the Phase 3.2 C1
fix.

A55 lists `ablation_operator_hash` as one of the 4 axes that should trigger
`metric_drift`. Cross-skill (diff_skill) works, but within a single skill's
aggregated runs, divergence is invisible. If a re-run of a skill uses a
refactored ablation operator (different hash), the aggregated report
under-reports the discrepancy. Cross-pool comparability is silently broken.

**Fix:** mirror the subject_model `MIXED` pattern. Collect ALL op_hashes per
`(clause_id, axis)` set; if `len(distinct) > 1`, emit a structured
`data-integrity` warning and set the field to `"MIXED"`. Same shape as Phase
3.2 C1's subject_model fix. **Falsifying test:** seed two completed runs for
skill X with different `ablation_operator_hash` values; assert
`report.clauses[0].ablation_operator_hash == "MIXED"` and a warning was logged.

### I4 · `freeze` opens evidence DB in writable mode even for dry-run (least-privilege violation)
`cli/main.py:1450-1453` — `ev_conn = open_evidence(evidence_db)` unconditionally,
even on the dry-run default path that returns at `:1515` without writing. Compare
`run evaluate-skill` (`main.py:1014`) which uses `open_evidence_readonly` correctly.

On systems with strict FS perms, dry-run could fail with "permission denied"
when read-only access would suffice. Per CLAUDE.md Pipeline-safety: dry-run is
the default — the default should require minimum privilege.

**Fix:** branch the DB open: `open_evidence_readonly(evidence_db)` for dry-run
path, `open_evidence(evidence_db)` only when `execute=True`. **Falsifying test:**
`chmod 444 evidence.db` (or Windows equivalent); invoke `freeze <verdict_id>`
without `--execute`; currently fails with permission error; correct behavior
succeeds.

## MINORs (cheap cleanups; fold in)

- **M4 · `cli/main.py:879-881` outdated comment post-CF-E3-1.** Comment says
  "ClauseResult doesn't carry verdict_id in v0.1" — false after `32f3ad4` added
  the field. `getattr` defensive default still works but is no longer needed.
  **Fix:** delete the obsolete comment; consider removing the `getattr` fallback
  (the real ClauseResult now reliably has `verdict_id: str | None`).
- **M5 (CARRYOVER) · `cli/main.py:573, 1452` redundant `(BootstrapError, Exception)` tuple.**
  `BootstrapError` is a subclass of `Exception`; the tuple catches the same set
  as bare `Exception`. **This was a finding from Track E.1 ai-slop reviewer (their
  M3)** that I — the orchestrator — incorrectly consolidated OUT when writing
  the Track E ai-slop fix-brief (I kept E.1's M4 "aliased re-import" under the
  name M3, dropping the BootstrapError-tuple finding). Phase 3.4 reviewer
  re-surfaced it; this is the disclosed orchestrator error.
  **Fix:** `except Exception` with an inline comment `# includes BootstrapError
  when DB not yet bootstrapped` OR split into `except BootstrapError: ... except
  Exception: ...` if separate handling is desired (current code does the same
  thing for both — bare `except Exception` is the minimal fix).
- **M6 · `cli/main.py:1266` dead-assigned `key` variable in diff_skill.** Built but
  never read; line 1273 builds a different key and uses that. Leftover from a
  refactor. **Fix:** delete L1266.

## MINORs (uncertain — surface or defer)

- **M3-r · `fit.py:213` public-API n>0 guard absent [uncertain].** `fit_skill` is
  exported but not reachable from engine without `n≥1`. v0.1 has one consumer
  (engine). NO-ACTION; if the public API gains other consumers in v0.2, add a
  validator at the `ClauseObservations` dataclass.
- **M2-r · `_derive_a55_fields` treats `subject_model=None` as "not present" [uncertain].**
  The walrus filter `if v is not None` excludes None from the divergence set.
  Borderline: missing model could be a data-integrity issue (warrants MIXED) OR
  it's "no signal" (no comparison possible). NO-ACTION for v0.1; dogfooding will
  surface if operators see misleading reports.
- **M7-r · 0401 `current_metric_versions` VIEW millisecond-tie collision [uncertain].**
  If two metric_versions register in the same millisecond for the same metric_id,
  the VIEW returns multiple rows and `frozen_cases_with_currency` over-counts.
  Vanishingly rare in production; tests use explicit `registered_at` strings
  which could trigger but the suite catches none. NO-ACTION for v0.1; v0.2 add a
  tiebreaker (e.g., `ORDER BY registered_at DESC, version DESC LIMIT 1`).

## Values decision (single ambiguity worth surfacing to user)

- **M1-r [values decision] · Coverage Law denominator: include vacuous clauses?**
  CLAUDE.md + PRD §8 both state `Coverage = tested_clauses / total_clauses`
  without disambiguating whether `total_clauses` includes mechanically-vacuous
  clauses (clauses with no constructible falsifying case). PRD §7 says vacuous
  is "excluded from testing." Two readings:
  - **Reading A (include in denominator)**: Coverage is "how much of the authored
    clause set has been verified." A 100% vacuous skill has 0% coverage. Honest;
    discourages skills with un-testable clauses.
  - **Reading B (exclude from denominator)**: Coverage is "how much of the
    TESTABLE clause set has been verified." A 100% vacuous skill has undefined
    coverage. Aligns with "excluded from testing" phrasing.
  Engine currently implements Reading A (`engine.py:94-95`: total_clause_count =
  all_clauses). **This is a real values-debate**; PRD ambiguous. Defer to user
  decision in fix-brief disposition turn OR Phase 3.5 PRD v1.1 doc-lock (add a
  disambiguating sentence under §8).

## Defer to v0.2 (already on the deferred list)

- **I3 (this review) ≡ Phase 3.2 fix-brief's deferred I2 · `engine.py:166-202` N+1
  confound query.** Already deferred to v0.2. No new action; confirm alignment.

## Clean (explicitly verified by reviewer)

- migration `0400_freeze_provenance.sql` (BEFORE INSERT trigger correct; ALTER
  TABLE ADD COLUMN does not bypass existing append-only triggers)
- `aggregation/status.py` (state machine pure function; `WIN_RATE_THRESHOLD`
  deletion verified clean via grep)
- `aggregation/fit.py` constant deletion (`PASS_PROB_THRESHOLD` + `FAIL_PROB_THRESHOLD`
  verified zero references in `src/` via grep)
- `repositories/evidence/frozen_cases.py::freeze_verdict` (all 4 A56 eligibility
  gates present at Python layer)
- `ablation/runner.py` CF-E3-1 threading (verdict_id on both write path L874 +
  resume path L900; loop-exit ClauseResult constructor at L933 wires the field;
  `_load_persisted_verdict` 3-tuple consistent with its single caller)
- `cli/main.py` evaluate-skill exit codes (A58 verified: L1040 incomplete → 1,
  L1086 precondition → 1, L1107 → 2, default → 0)
- `cli/diff_report.py::status_delta` (ordering FAILED < CONFOUNDED < UNMEASURED
  < PASSED; rank-collision returns `unchanged`)
- All parameterized queries (recovery.py L71, engine.py L139-202, frozen_cases.py
  throughout, diff_skill L1250-1253) — no f-string SQL with user input; safe
  `placeholders = ",".join("?" for ...)` patterns

## Method + gates

TDD: write the falsifying test FIRST for S1, I1, I2, I4 (M4/M5/M6 are
deletion-only — gates ARE the test). Prove RED by manually applying the bug
pattern; remove; prove GREEN.

Touches:
- `src/skill_harness/storage/recovery.py` (S1 narrow except)
- `src/skill_harness/aggregation/fit.py` (I1 NaN → None at raise sites)
- `src/skill_harness/aggregation/report.py` (I1 `allow_nan=False`)
- `src/skill_harness/aggregation/engine.py` (I2 op_hash MIXED pattern)
- `src/skill_harness/cli/main.py` (I4 dry-run readonly + M4 obsolete comment + M5 exception tuple + M6 dead key)
- tests in `tests/test_storage_recovery.py`, `tests/test_aggregation_fit.py`,
  `tests/test_aggregation_engine.py`, `tests/test_aggregation_report.py`,
  `tests/test_cli_freeze.py`

Do NOT touch `migrations/`, `aggregation/status.py`, `ablation/runner.py`,
`storage/repositories/`, or any aggregation/fit.py code beyond the NaN sentinel
sites + the `engine.py` op_hash collection logic.

Gates: `pytest -q -m "not live"` green (target 884+N) · `mypy --strict src/`
clean · `ruff check src/ tests/` + `ruff format --check src/ tests/` clean.
Single cohesive commit per project memory `feedback-commit-shape`.

New worktree off current `main` (`32f3ad4`).

## Carry-forwards (Phase 4 punch list)

- **CF-Phase-3-4-1**: PRD v1.1 doc-lock should add a §8 disambiguating sentence
  on Coverage denominator behavior (driven by M1-r values decision). Surface to
  Phase 3.5 audit's queue when user resolves the M1-r values question.
- **CF-Phase-3-4-2**: v0.2 confound query GROUP BY rewrite (engine.py:166-202).
  Already on the deferred list; re-confirmed by this review.
- Aggregation `subject_model=None` handling (M2-r) and millisecond-tie VIEW
  collision (M7-r) — dogfooding triggers.

## Orchestrator disclosure

This fix-brief discloses an orchestrator drafting error in the prior Track E
ai-slop fix-brief: E.1 reviewer's M3 (`(BootstrapError, Exception)` redundant
tuple) was silently dropped when I consolidated findings into the fix-brief.
The pattern persisted at `cli/main.py:573` and `:1452` through 4 commits.
Phase 3.4 reviewer (independent fresh-context) caught it as their M5. Logged
here as M5 (CARRYOVER) so the audit trail is honest. The error pattern:
consolidation under per-reviewer ID labels (M1, M2, M3 …) can silently lose
findings when reviewer-specific M-IDs collide across reviewers; future fix-brief
consolidations should use globally-unique IDs (e.g., E1-M3, E2-M2) or explicit
cross-reviewer rollup.
