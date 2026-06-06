# Track D.2 — Parallel Review Seed

Status: PENDING (fires the moment the D.2 implementer reports DONE/DONE_WITH_CONCERNS).
Shape: **parallel cross-talk council**, not the linear spec→quality pair. D.2 crosses
load-bearing storage invariants (append-only writes, `runs.completed_at` single-shot,
cost-from-evidence, idempotency/resume), so it qualifies for the council's
**"Storage-touching change"** template + a spec-compliance seat.

Dispatch per `cross-talk-council-dispatch` (named other seats, predict right/wrong/miss)
and `parallel-review-disposition-schema` (fixed `BLOCKER / MAJOR / MINOR / OBSERVATION`
enum, per-item block, mandatory status line).

## Seats (5, parallel)

| Seat | Lens | Owns these checks |
|---|---|---|
| **SPEC-COMPLIANCE** | Does the code match the D.2 brief exactly — no more, no less? | brief scope adherence; QUAL-1 carry-forward (sub-tolerance clauses flagged length-confounded); A39–A49 coverage; no scope creep beyond runner orchestration |
| **SCHEMA** | Append-only + write-time snapshot | no UPDATE on evidence rows except `runs.completed_at` single-shot (A20); all writes via `open_db()`/helpers, never raw `sqlite3.connect`; cost columns written at write-time not recomputed (A41); idempotency UNIQUE(run_id,clause_id,condition,sample_index) honored (A40) |
| **RELIABILITY** | Crash/resume/partial-run | resume re-derives from evidence, not runtime guesswork; sequential-stopping state machine (A44) has no unbound/None-access paths; single-writer BEGIN IMMEDIATE + busy_timeout (A26); evidence-first dual-write ordering (A25) |
| **SECURITY** | Adversarial subject/judge output | subject outputs are attacker-influenced; injection handling in rendered conditions; API key surface; no eval of model-controlled content |
| **TEST-ARCH** | Falsifiability + confound symmetry | confound monitor (A47) symmetric across conditions; Full/Ablated_k/Null contract correct; multiplicity provenance recorded (A49); warmup/cache-marker placement (A43) doesn't contaminate deltas |

## CONFIRMED defects to hand the council (from live worktree diagnostics — grounded, not speculative)

1. **`OracleAPIError.transient` does not exist** (BLOCKER-candidate). On main,
   `src/skill_harness/oracles/errors.py:17` defines `class OracleAPIError(OracleError)`
   with no `__init__` and no `transient` field. The D.2 worktree constructs
   `OracleAPIError(..., transient=...)` and reads `err.transient` in `runner.py` (~L994/L1004),
   `subject.py` (~L189/L194), and `tests/ablation/test_runner.py`. Either (a) a real bug, or
   (b) an unauthorized cross-module edit into Track-C's oracle layer. Flagged to the live agent;
   council must confirm the resolution stayed inside `ablation/`.
2. **Possibly-unbound locals in `runner.py`** (`full_sample_id` L744, `abl_sample_id` L745) —
   control-flow path leaves them unset before use. RELIABILITY + SPEC own this.
3. **`should_stop` / `stopping_reason` accessed on `None`** (`runner.py` L753/L754) —
   Optional member access; the stopping object may be None on a path. RELIABILITY owns.
4. **Hygiene (MINOR):** unused `math` (confound.py L25), unused `_CONDITION_NULL`/`_CONDITION_FULL`
   (confound.py L42/L43), unused `list_cost_ledger_for_run` import (reconciler.py L26).

> Note: the bulk `reportMissingImports` for `skill_harness.ablation.*` and `anthropic` are the
> known worktree-resolution false positives (validated 5× in Track C, `pyright-stale-diagnostics-in-worktree-dispatch`).
> Confirm against `mypy --strict` run from the worktree, NOT pyright. Do not file these as findings.

## Invariants the council must NOT relitigate (locked)

- Pass rule: `P(win_rate>0.60) ≥ 0.95`, Beta(1,1)→Beta(1+w,1+n−w), Win=1/Tie=0.5/Loss=0.
- Deterministic Python owns all control flow; models generate content only.
- Only admissible AND non-confounded verdicts aggregate; no admissible evidence ⇒ UNMEASURED.
- evidence.db `synchronous=FULL`, runtime.db `NORMAL`.
- CLI command set frozen to PRD §18 (relevant to D.3, not D.2).

## Synthesis → action

Synthesize per disposition schema (group by enum). Any unresolved BLOCKER → fix-loop back to
the D.2 implementer (same agent) → re-review the touched seat only. MAJOR with no clean fix →
carry-forward to D.3 brief with a recorded disposition (per `feedback-disposition-not-prior-pattern`:
per-finding-per-rubric, not per-track-pattern). On clean: cherry-pick to main via
`git -C "C:/Users/mlpgr/2026_Projects/youwontdoit"` (NOT from inside the worktree — cwd hazard),
verify gates on main (pytest + mypy --strict), push, then dispatch D.3.
