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

---

Re-pointed from "per CLAUDE.md" to this file: `aggregation/fit.py:11`,
`ablation/stopping.py:22`, `cli/main.py:4`, `ablation/runner.py:1294`. A further 26
"per CLAUDE.md" comments remain elsewhere in `src/` (non-mechanical wording sweep,
out of scope for this pass).
