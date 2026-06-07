# Track E — End-of-Track ai-slop-sentinel Review: Disposition + Fix Brief

3 fresh-context ai-slop-sentinel reviewers (Opus 4.7, read-only) on landed Track E:
E.1 storage + recovery (`94fa15c` — migrations 0400/0401, recovery.py, freeze_verdict
repo, FrozenCaseWrite extensions), E.2 aggregation + status + JSON report
(`11e09cf` — engine/fit/status/report/errors), E.3 CLI integration (`f171512` —
evaluate-skill, diff skill, freeze `<verdict_id>`, ablation report verdict_id column).
Findings synthesized below; the single CRITICAL was **hub-verified by direct code read**
before this disposition.

## Verified CRITICAL (blocks Track E close / blocks v0.1 tag)

### C1 · E.3 `diff skill` `metric_drift` omits two of four A55 divergence axes
`cli/main.py:1316-1331` checks only `metric_id_per_axis`, `metric_version_per_axis`,
`ablation_operator_hash` — three axes. A55 mandates `metric_drift` triggers on ANY of
four: `(metric_id, metric_version)`, `ablation_operator_hash`, `subject_model`,
`user_message_sha256`. The two missing axes are `subject_model` and
`user_message_sha256`. **Hub-verified** by `grep subject_model src/skill_harness/cli/main.py`
returning zero hits and by reading lines 1316-1331 directly — there is no `config_json`
read, no `subject_model` access, no `user_message_sha256` hash. The commit message at
`f171512` explicitly claims `"metric_drift triggers on … (and run-level subject_model /
user_message_sha256 from runs.config_json)"` — the code does not implement the
parenthetical. False-confidence slop: commit message asserts behavior the code does not
deliver. Differential framework that mis-attributes cross-model or cross-prompt deltas
as `regressed`/`improved`/`unchanged` instead of `metric_drift` is broken even with green
gates. Comparability is load-bearing per A55 + Evaluation-shape invariant. **Verified by read.**

**Fix:** Thread `subject_model` + `user_message_sha256` into `ClauseReport` from the
aggregation engine (additive A60 wire-format bump `1.0.0` → `1.1.0`; v0.1 stays in
`1.x` per A60 additive-only contract). Then `diff_skill` adds two more `elif` branches
at `cli/main.py:1331` checking those fields. Inside the engine, when a single
`ClauseReport` aggregates across multiple runs with divergent `subject_model` within
the same skill, that itself is a category error — emit a structured `data-integrity`
warning (A41 reconciler-style anomaly) and set the field to `"MIXED"` so the diff
catches it downstream. **Falsifying test:** `test_diff_skill_subject_model_swap_marks_metric_drift`
— seed skill A with a run on `claude-sonnet-4-6` and skill B otherwise-identical on
`claude-opus-4-7`; assert `cd.delta == "metric_drift"` AND `cd.metric_drift_reason`
mentions `subject_model`. Must go RED against current code, GREEN after the fix.

## Importants (fix in the same loop)

- **I1 · E.2 duplicate SQL execution in `_fetch_completed_ablation_runs`**
  (`aggregation/engine.py:457-483`). Same SELECT runs twice — once for rows, once for
  `cur.description`. Doubles read I/O and is a TOCTOU hazard in principle. **Fix:**
  `cur = conn.execute(<sql>, ...); cols = [d[0] for d in cur.description]; rows = cur.fetchall()`.
  **Test:** count-mock on `Connection.execute`, assert exactly 1 call (currently 2).
- **I3 · E.2 no end-to-end engine test for `UNMEASURED(falsifying_case_stale)` path**.
  status.py covers Rule 5a in isolation, but no engine-level integration seeds an old
  metric_version + a new metric_version + a frozen_case at the old version and asserts
  the engine routes the clause to `UNMEASURED(falsifying_case_stale)`. The whole point
  of E.1's `frozen_cases_with_currency` VIEW feeding E.2 has no integration coverage.
  **Fix:** add a test that inserts metric_version v1 (audited+passed), then v2
  (audited+passed at later registered_at), inserts a frozen_case at v1, seeds verdicts
  driving `p_win ≥ 0.95`, asserts `report.clauses[0].status == "UNMEASURED"` AND
  `report.clauses[0].sub_reason == "falsifying_case_stale"`.

## Test-quality (the project's recurring lesson — fold in)

- **T1 · E.1 heartbeat-DESC ordering contract has zero coverage**
  (`tests/test_storage_recovery.py:314-330`). `find_resumable_run_for_skill`'s "most-recently-heartbeated"
  contract isn't asserted — both test runs share the same `_TS`. Reversing the sort
  flag at `recovery.py:100` (`reverse=True` → `reverse=False`) would pass current tests.
  **Fix:** add a case with distinct heartbeats `_TS < _TS2`, assert `find_resumable_run_for_skill == "run2"`.
- **T2 · E.1 UNIQUE-collision test does not pin failure to the index**
  (`tests/test_freeze_verdict_repo.py:296-302`). Asserts only `sqlite3.IntegrityError` —
  any constraint failure (FK, NOT NULL, trigger, future CHECK) would also satisfy. A56
  pins idempotency to `idx_frozen_unique(clause_id, axis, failing_input_sha256)`.
  **Fix:** `pytest.raises(sqlite3.IntegrityError, match="UNIQUE")` + assert
  `len(list_frozen_cases_for_clause(...)) == 1` after the second call.
- **T3 · E.2 BH-FDR fallback test cannot exercise BH selection logic**
  (`tests/test_aggregation_fit.py:259-272`). Test asserts only
  `isinstance(result.bh_fdr_passes, frozenset)` — satisfied by `frozenset()`. Author's
  own comment flags "separately test BH logic" as a TODO that was never written. `_bh_fdr`
  helper has zero direct unit tests. **Fix:** (a) hand-computed `_bh_fdr` test with
  known input → known output set; (b) fit-level test with 9 degenerate + 1 obvious winner,
  assert fallback fires AND the winner's `clause_id` IS in `bh_fdr_passes`.
- **T4 · E.2 "byte-stable" test does not trap engine wall-clock reads**
  (`tests/test_aggregation_report.py:196-201` + `test_aggregation_engine.py:685-707`).
  Both tests pass the same `generated_at_utc` literal into both calls — only test the
  report module's serializer, not that nothing inside `aggregate_skill()` reads
  `datetime.now()` or `time.time()`. Session-log claim "byte-stability PASSED via
  datetime class patching" overstates the proof. **Fix:** patch `datetime.datetime.utcnow`
  / `time.time` to raise inside the engine module path; assert `aggregate_skill` does not
  raise. Catches future drift where a maintainer adds `datetime.now()` to engine.py.
- **T5 · E.2 `family_size_used` mismatch warning path is dead code from coverage**
  (`aggregation/engine.py:521-538`). Per A59 + A41 the warning IS the audit signal for
  config drift between aggregated runs. **Fix:** caplog-based test with two runs at
  different family_size; assert warning emitted; assert first-run value used.
- **T6 · E.2 `family_size` malformed-type path untested**
  (`aggregation/engine.py:517`). `isinstance(int)` check exists but tests only exercise
  `family_size=0`. **Fix:** parameterize for `(0, -1, "2", None, 1.5)` — all should raise
  `MalformedRunConfig`.
- **T7 · E.3 `test_ablation_report_verdict_id.py` is testing the mock, not the integration**.
  **Hub-verified**: `ClauseResult` (`ablation/runner.py:204-219`) has no `verdict_id`
  field — fields are `clause_id, stopping_reason, stop_decision, samples_collected,
  length_confounded, unmeasured_reason`. Tests at `tests/test_ablation_report_verdict_id.py:37-47`
  build `MagicMock` with `.verdict_id = "verdict-abc-123"` manually. Test names read
  end-to-end ("test_verdict_id_appears_in_passed_result") but only prove "if the mock
  has the attribute, _render includes it." Real ablation runs render `—` via the
  `getattr(result, "verdict_id", None) or "—"` fallback. **Fix path A (test honesty,
  E.3-scope):** module-level docstring stating "Asserts rendering shape, NOT real-run
  behavior; see Phase 3 follow-up" + a test that constructs a real `ClauseResult` (not
  a Mock) and asserts the row renders `—`. **Fix path B (proper, Phase 3 follow-up
  already noted):** thread `verdict_id: str | None = None` through `ClauseResult` from
  `runner.py:1056-1065` where the UUID is already generated. Path A is in-loop for the
  fix brief; Path B stays on the Phase 3 punch list (CF-E3-1).
- **T8 · E.3 `test_json_output_to_stdout_warnings_to_stderr` does not verify separation**
  (`tests/test_cli_evaluate_skill.py:528-554`). Default `CliRunner()` has
  `mix_stderr=True`; `result.output` is merged. No path in the test emits stderr
  chatter alongside `--format=json`, so the test cannot distinguish "warnings to stderr"
  from "warnings to stdout." Name promises shell-pipeline safety; assertion only proves
  happy-path JSON parses. **Fix:** `CliRunner(mix_stderr=False)`, emit a warning via a
  patched logger during a `--format=json` invocation, assert `result.stdout` is
  byte-equal to `to_json_bytes(report)` AND `result.stderr` contains the warning.
- **T9 · E.3 zero-axis alignment collapse not pinned**
  (`cli/main.py:1269,1275`). `axis_key = next(iter(cr.metric_id_per_axis.keys()), "")` —
  when a clause has zero admissible verdicts, `metric_id_per_axis == {}`, `axis_key == ""`.
  Multiple zero-verdict clauses with the same `(clause_text_sha256)` collapse to one
  `("", sha)` bucket. Session-log marked as v0.2 work but no comment at the call site;
  no test pins current behavior. **Fix:** inline comment + a regression-pinning test
  asserting `axis_key == ""` and `delta == "unchanged"` for the zero-verdict case.

## Minors (cheap cleanups; fold in if touching the same files)
- **M1 · E.1 dead defensive code** (`storage/recovery.py:63,100`): `len(row) > 2` and
  `or ""` on schema-NOT-NULL `last_heartbeat` (`migrations/runtime/0001_initial.sql:22`).
  Replace with positional unpack + drop the `or ""` fallback.
- **M2 · E.1 unreachable early-return** (`storage/recovery.py:66-67`): map is non-empty
  by construction at this point. Delete.
- **M3 · E.1 aliased re-import** (`cli/main.py:1431`): `import sqlite3 as _sqlite3` inside
  the freeze function, used only at `:1526`. `sqlite3` already imported at top-level.
  Delete the alias, rename the usage site.
- **M4 · E.2 bare `except Exception` swallows lookup errors** (`aggregation/engine.py:551-552`,
  `_fetch_run_state`). Silent `return None` bypasses `budget_exhausted` detection if the
  table is missing. **Fix:** narrow to `except sqlite3.Error as exc: logger.warning(...)`.
- **M5 · E.2 type-degradation + lazy import** (`aggregation/engine.py:261,289-291`):
  `posteriors_by_key: dict[..., object]` then `ClausePosterior` imported inside a loop.
  Move import to module top; type the dict as `dict[..., ClausePosterior]`.
- **M6 · E.3 no test for `--format=csv|md` rejection** (A60 explicit ban).
  `click.Choice(["rich", "json"])` rejects automatically with exit 2; add 3-line
  assertion in both `test_cli_evaluate_skill.py` and `test_cli_diff_skill.py`.

## Defer to v0.2 (logged, not fixed in this loop)
- **I2 · E.2 N+1 query in per-run confound-counting** (`aggregation/engine.py:166-196`).
  O(C·R) extra queries; correct, just inefficient. v0.1 has no scale that matters.
  Single-query GROUP-BY rewrite is a v0.2 task; logged here so it isn't lost.
- **D26 · `posteriors_by_key` implicit ordering contract** (`engine.py:260-266`, E.2 M1).
  Today fit.py preserves input order; engine.py zip-by-index works. Future fit.py
  refactor could silently corrupt. **v0.2:** add `clause_id -> posterior` map to
  `FitResult` (additive, no engine wire change).
- **D27 · M5 `evidence_conn_ro` parameter name not enforced** (E.1 M5 [uncertain]).
  Docstring documents the contract; call sites verified to use `open_evidence_readonly`.
  Acceptable as-is; v0.2 could add `PRAGMA query_only` check.

## Clean (no action) — explicitly verified by the reviewers
- migration `0400_freeze_provenance.sql` (A1 + A20 + A30 + A4 ledger compatibility);
  migration `0401_stale_frozen_view.sql` (A57 literal column filter `audited=1 AND
  mechanical_validity_test_passed=1`; correct VIEW join on `metric_version AND
  implementation_hash`); A29 admissible_verdicts VIEW not shadowed.
- `storage/recovery.py` three signatures per A61; Python-side runtime→evidence join
  (no ATTACH per A25); `IncompleteRun` frozen dataclass.
- `repositories/evidence/frozen_cases.py::freeze_verdict` — all four A56 eligibility
  gates present; provenance auto-fill from verdict's stored `(metric_id, metric_version)`
  (write-time snapshot per A3, not joined to a "current" pointer).
- `storage/models.py` `FrozenCaseWrite` extensions (per A24 functional + strict Pydantic).
- `aggregation/fit.py` — EB-MoM formula correct against canonical Method-of-Moments;
  convergence guard ordering correct (var-floor first); K<10 gate uses `<` per A53;
  BH-FDR step-up matches textbook; no `random.*` / `np.random.*` calls.
- `aggregation/status.py` — `UnmeasuredSubReason` enum exact match to A57 6-value list;
  state-machine ordering correct (FAIL gate before PASS gate; stale/missing only after
  FAIL); pure function.
- `aggregation/report.py` — `REPORT_SCHEMA_VERSION = "1.0.0"` literal; `to_json_bytes`
  uses `sort_keys=True, separators=(",", ":")`; no internal `datetime.now()` /
  `time.time()` / `random` calls.
- `aggregation/errors.py` — typed exceptions per A24.
- `cli/main.py` — `_find_incomplete_run` shim DELETED per A61 (verified by grep);
  `freeze <verdict_id>` rename complete; A48 idempotent "already frozen" message
  implemented at `cli/main.py:1526-1536`; `evaluate-skill` exit codes 0/1/2 per A58;
  JSON output bytes-only via `sys.stdout.buffer.write`; `REPORT_SCHEMA_VERSION == "1.0.0"`
  explicitly tested.
- `cli/diff_report.py` — clean `DiffReport` + frozen `ClauseDiff`; status_delta
  ordering FAILED < CONFOUNDED < UNMEASURED < PASSED; byte-stable `to_json_bytes`.
- self-diff falsifiability test present (`test_diff_skill.py:345-391`); test_cli_d3_fixes
  migration is mechanical 1:1.

## Method + gates
TDD: write the falsifying test FIRST for C1, I1, I3, T1–T9; prove RED; then GREEN.
Touches `cli/main.py`, `aggregation/engine.py`, `aggregation/report.py` (A60 minor
bump to `1.1.0`), `aggregation/__init__.py`, `aggregation/fit.py` (defensive narrowing
of `_fetch_run_state` `except`), `storage/recovery.py` (M1, M2), tests across
`tests/test_*_aggregation_*.py`, `tests/test_cli_*.py`, `tests/test_storage_recovery.py`,
`tests/test_freeze_verdict_repo.py`, `tests/test_ablation_report_verdict_id.py`.

Do NOT modify `migrations/` (E.1 schema is clean). Do NOT thread `verdict_id` through
`ClauseResult` (Phase 3 follow-up CF-E3-1; out of fix-brief scope).

Gates: `pytest -q -m "not live"` green · `mypy --strict src/` clean · `ruff check
src/ tests/` + `ruff format --check src/ tests/` clean. Invariants unchanged
(deterministic control flow; append-only evidence; never-recompute-provenance; A55
metric_drift comparability strengthened; A60 wire format extended additively).

New worktree off current `main` (`dbcbc91`). Single cohesive commit per project
feedback ("single cohesive commit per phase, not per finding"); finding IDs
traceable via this brief.

## Carry-forwards (Phase 3 punch list, NOT in this fix-brief)
- **CF-E3-1** · Thread `verdict_id: str | None` through `ClauseResult` at
  `ablation/runner.py:204` so real ablation runs render the UUID (currently `—` via
  getattr fallback). UUID is already generated at `runner.py:1056` — just needs threading.
  Required for `freeze <verdict_id>` to be discoverable from a real ablation run.
- **A57 stale-write refusal at freeze time** (E.3 M2 [uncertain]). A56/A57 do not
  mandate write-time refusal of stale verdicts; aggregation auto-flips to
  UNMEASURED(falsifying_case_stale) at read time. Acceptable as-is for v0.1; revisit
  if dogfooding shows operators freeze stale verdicts and are confused when the
  PASSED gate doesn't fire.
- **Aggregation subject_model homogeneity check** (surfaced while sizing C1 fix).
  `evaluate-skill` aggregates across all completed ablation runs for a skill_id
  without checking that they share `subject_model`. If a skill is run once on Sonnet
  and once on Opus, the pool mixes incompatible measurements silently. C1 fix path
  emits `subject_model = "MIXED"` warning when this happens; tighten to refuse-to-aggregate
  in v0.2 if dogfooding surfaces incidents.
