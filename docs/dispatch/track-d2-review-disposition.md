# Track D.2 — Re-Review Disposition (post-fix)

The D.2 fix-loop fix (uncommitted in worktree `agent-a32feff49007d1b7e`) was
re-reviewed by a 4-seat parallel cross-talk council (SPEC-COMPLIANCE, SCHEMA,
RELIABILITY, TEST-ARCH; SECURITY skipped — returned nominal in the prior fire).
Dispatch per `cross-talk-council-dispatch` + `parallel-review-disposition-schema`
(opus, read-only). Disposition enum: `RESOLVED | PARTIALLY-RESOLVED | NOT-RESOLVED
| NEW-FINDING | OBSERVATION`.

## Convergence — all behavior fixes RESOLVED (≥3 seats each, code-cited)

- **ROOT** `_snapshot_admissibility` (runner.py:1083) computes write-time admissibility
  from `(confounded, null_floor_met)`; hardcoded `"admissible"` removed. (SPEC/SCHEMA/REL)
- **BLOCKER-1** Tier-2/unscored-axis gate `_is_tier1_measurable` (runner.py:620) returns
  UNMEASURED `tier2_uncalibrated` before sampling; `_score_primary_axis` (runner.py:1146)
  RAISES instead of verbosity fallback. (SPEC/SCHEMA/REL)
- **BLOCKER-2** `_load_sample` returns real `sample_id`; verdict write raises on blank id
  (runner.py:1025), uses real FK ids; verdict dedup via `_existing_verdict_keys`
  (runner.py:1265) gated at runner.py:843; `comparisons_issued < N_MAX` loop bound. (all)
- **MAJOR-1** only `admissibility_state == "admissible"` advances the stopping posterior
  (runner.py:859). **MAJOR-2** resume re-derives `samples_collected`/`usd_spent` from
  evidence (runner.py:524-538). **MAJOR-3** below-floor → inadmissible/underpowered.
- **MINORs** REL-1 (init sample ids at loop top), REL-7 (A42 docstring), SEC-4 (no
  control-flow branch on `[ABLATED]` in model output) — RESOLVED.
- **Scope** clean: only `ablation/runner.py`, `ablation/confound.py`, `tests/ablation/`.

## TEST-ARCH `status: degraded` — 3 coverage gaps (SCHEMA converged on #3, cross-talk yield)

The BLOCKER fixes were code-correct but **untested** — a regression would have stayed
green (the exact failure mode that caused this fix-loop). Closed in-track (test-only,
`tests/ablation/test_runner.py`), each **verified falsifying** (proved RED under the
regression it guards, then reverted; full gate suite restored green after):

1. **BLOCKER-1 untested** → `TestTier2Unmeasured` (2 tests): Tier-2/axis-registered and
   Tier-1/unknown-axis clauses both yield UNMEASURED, zero samples, zero verdicts.
   RED proof: gate disabled → tier-2 scored on verbosity (samples≠0) / unknown-axis raises.
2. **MAJOR-1 untested** → `test_confounded_comparison_not_added_to_stopping_posterior`:
   confounded clause-1 comparisons keep `acc.n == 0`, stop UNDERPOWERED_NMAX, ≥1 verdict
   written `inadmissible/confounded`. RED proof: unconditional `acc.add` → PASSED at 8.
3. **Resume dedup near-vacuous** (TEST-ARCH PARTIALLY-RESOLVED; SCHEMA: "assert verdict
   COUNT not sample COUNT") → strengthened the resume test to pre-seed a verdict for
   comparison index 0, then assert exactly one verdict post-resume. RED proof: dedup gate
   disabled → index 0 gets 2 verdicts `(0, 2)`.

## Gate result after closure

`579 passed, 1 deselected` · `mypy --strict` clean · `ruff check` + `ruff format --check`
clean. No `TEMP-REGRESSION` markers remain in source (all RED-proof edits reverted).

## Disposition

No unresolved BLOCKER. No carry-forward MAJOR (all fixed or closed). Carry-forwards to
D.3/Track-E remain as recorded in `track-d2-fix-brief.md`: TA-4 (per-verdict family_size
on RunConfig, Track E re-derives) and SEC forward caveat (re-audit subject output_text →
judge-system-prompt interpolation when the Tier-2 judge is wired). Cleared to land on main.
