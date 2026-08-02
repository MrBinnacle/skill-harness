# Invariants

Source comments across this codebase cite "CLAUDE.md" as the authority for several
locked, load-bearing thresholds and rules. `/CLAUDE.md` is a local, gitignored file
(`.gitignore`, `/CLAUDE.md` entry) — it is not tracked, so those citations point at
nothing a reader of this repo can open. This file is the tracked anchor for the
invariants that matter; `docs/PRD.md` remains the full specification.

## 1. Pass rule (locked)

A clause PASSES when `P(win_rate > 0.60) >= 0.95` on the posterior, computed from a
`Beta(1,1)` prior updated to `Beta(1+w, 1+n-w)` (Win = 1.0, Tie = 0.5, Loss = 0.0
half-update encoding). FAIL when `P(win_rate > 0.60) <= 0.05`.

Enforced in:
- `src/skill_harness/aggregation/fit.py::WIN_RATE_THRESHOLD = 0.60`
- `src/skill_harness/ablation/stopping.py::WIN_RATE_THRESHOLD/PASS_PROB_THRESHOLD/FAIL_PROB_THRESHOLD = 0.60/0.95/0.05`
- `src/skill_harness/aggregation/status.py::PASS_PROB_THRESHOLD/FAIL_PROB_THRESHOLD = 0.95/0.05`

Spec: `docs/PRD.md` §14 "Pass Rule".

## 2. Pipeline safety (dry-run default)

Every `run` subcommand, plus `calibrate` and `freeze`, defaults to dry-run;
`--execute` is required before the command performs writes or makes LLM API calls.

Enforced in: `src/skill_harness/cli/main.py` (dry-run gating on every mutating command).

Spec: `docs/PRD.md` §18 "CLI" cost discipline.

## 3. Evidence admissibility model

Admissibility is resolved at verdict-write time and never recomputed. Tier-2
(LLM-judge) verdicts are inadmissible without a calibrated `(judge_id, axis)` record
meeting the §6 thresholds; with no admissible evidence, a clause is UNMEASURED — never
PASSED.

Enforced in:
- `src/skill_harness/ablation/runner.py` (admissibility resolved at write)
- `src/skill_harness/oracles/tier2/judge.py` (position-swap + injection defenses gate `admissibility_state`)
- `src/skill_harness/storage/migrations_sql/evidence/0001_initial.sql` (append-only triggers on `oracle_verdicts`)

Spec: `docs/PRD.md` §6 "Admissibility System".

## 4. OC enumeration grid (locked)

The `skill_harness.oc` engine enumerates the full integer grid `n = 6-40`
(`GRID_N_MIN = 6` / `GRID_N_MAX = 40`). The 12-24-pair band is a presentation
highlight, never a grid bound. Ratified in decision #40: the floor is the smallest
n where a Gate-2 call is mathematically reachable in the locked gamma range; the
ceiling reconciles with the legacy instrument's `N_MAX` by ratified decision, not
by import — `oc` registers its own constants (#42 convention 2).

Enforced in:
- `src/skill_harness/oc/conventions.py::GRID_N_MIN/GRID_N_MAX = 6/40` (with the
  #40-provenance comment; deliberately not imported from `ablation/stopping.py`)

Spec: skill-harness #40 + #42 resolution records; drift-check row DC-7.

## 5. Budget ceilings (locked)

Spend on any one skill-task evaluation is capped at $35 per skill-task evaluation
(ratified in decision #40 — an operator-picked values decision). The cap tests the
worst-case fixed-N projected cost pre-spend: curtailment savings are displayed as
expectation, never assumed by the cap, and over-cap frontier rows render
visible-but-infeasible, never hidden. The value is registered through the existing
`runtime.run_budget.hard_cap_usd` per-run surface; the frontier (#56) marks
feasibility pre-spend and the RAT preflight gate (#57) binds record cap == passed
budget mechanically at `--execute` time. The daily calibration ceiling is unchanged:
`DAILY_CAP_HARD_CEILING_USD = 100.0`.

Enforced in:
- `src/skill_harness/oracles/calibration/cost_projection.py::EVALUATION_HARD_CAP_USD = 35.0`
- `src/skill_harness/oracles/calibration/cost_projection.py::DAILY_CAP_HARD_CEILING_USD = 100.0`
- `src/skill_harness/oc/frontier.py` (over-cap rows assembled with `feasible=False`)

Spec: skill-harness #40 resolution record; drift-check row DC-10.

## 6. Ratification binding (locked)

Un-ratified spend is mechanically impossible: `run ablation --execute` refuses to
proceed unless the invocation references a `docs/ratifications/RAT-*.md` record
that (a) has status RATIFIED, (b) states a `hard_cap_usd` exactly equal to the
`--max-usd` value registered through `run_budget.hard_cap_usd` (compared as
integer cents), and (c) scope-matches the invocation (skill id + `--task-family`
+ `--estimand`). Dry-run stays ungated. Ratified in decision #47 (operator-picked
mechanical binding, stronger than recommended); the eleven-field record checklist
and signing order live in `docs/ratifications/README.md`.

Enforced in:
- `src/skill_harness/ratification.py::check_execute_ratification` (pure decision)
- `src/skill_harness/cli/main.py` (`run ablation` --execute preflight)

Spec: skill-harness #47 resolution record + #41 amendment; drift-check row DC-12
(ledger internal consistency, independent reader).

---

Re-pointed from "CLAUDE.md" to this file across `src/` and `tests/` (F5, then the
F5b mechanical follow-up sweep): `aggregation/fit.py`, `aggregation/status.py`,
`ablation/stopping.py`, `ablation/runner.py`, `ablation/render.py`,
`ablation/subject.py`, `ablation/operator.py`, `cli/main.py`, `extractor/pipeline.py`,
`extractor/claude.py`, `oracles/__init__.py`, `oracles/errors.py`,
`oracles/tier1/hedge_index.py`, `oracles/tier2/judge.py`,
`oracles/tier2/injection_guard.py`, `oracles/calibration/command.py`,
`storage/migrations_sql/evidence/0400_freeze_provenance.sql`, and the corresponding
test files under `tests/`. One site is deliberately left alone:
`oracles/tier1/fixtures/hedge_wordlist.json`'s `_meta.description` field carries its
own "DO NOT EDIT without updating the metric version" invariant, so its "per
CLAUDE.md" mention is untouched rather than risk drifting the fixture's SHA-256
implementation_hash out from under that guard.
