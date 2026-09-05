# Invariants

Source comments across this codebase cite "CLAUDE.md" as the authority for a set of
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

The half-update encoding is **provisional**, and its measured sensitivity is
recorded in §8. Read the two together: the thresholds above were calibrated against
the blended rate, and §8 records that the blended rate is not the estimand of record.

Spec: `docs/PRD.md` §14 "Pass Rule".

## 2. Pipeline safety (dry-run default)

Every `run` subcommand, plus `calibrate` and `freeze`, defaults to dry-run;
`--execute` is required before the command performs writes or makes LLM API calls.

Enforced in: `src/skill_harness/cli/main.py` (dry-run gating on every mutating command).

Spec: `docs/PRD.md` §18 "CLI" cost discipline.

## 3. Evidence admissibility model

Evidence admissibility is resolved at verdict-write time and never recomputed. Tier-2
(LLM-judge) verdicts are inadmissible without a calibrated `(judge_id, axis)` record
meeting the §6 thresholds; with no admissible evidence, a clause is UNMEASURED — never
PASSED.

Enforced in:
- `src/skill_harness/ablation/runner.py` (evidence admissibility resolved at write)
- `src/skill_harness/oracles/tier2/judge.py` (position-swap + injection defenses gate `admissibility_state`)
- `src/skill_harness/storage/migrations_sql/evidence/0001_initial.sql` (append-only triggers on `oracle_verdicts`)

Spec: `docs/PRD.md` §6 "Evidence Admissibility System".

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

## 7. Task-frontier phase firewall

A task family's phases — calibration, confirmation, matched — are separated at the
**semantic-lineage** level by a **physical partition**, not by a query predicate.
Each phase owns its own append-only table, and an observation's phase is read out of
the frozen manifest and **stamped at write time**, never recomputed at read: a
manifest that later repartitions a lineage cannot move an already-written record.
Calibration data selects a difficulty rung and must therefore stay out of the effect
estimate (split-sample validity — otherwise the rung's winner's curse biases the
effect); the partition is what will keep it out once the estimator is wired. No
public accessor hands calibration or confirmation *observations* to a caller in
**bulk**, and none takes a phase as an argument; a later ticket exposes the selected
rung as a *decision*. This removes the row-leakage bug class — defense in depth, not
a claim that misuse is impossible.

Enforced in:
- `src/skill_harness/task_frontier/` (`load_manifest`, `admit`, `matched_evidence`,
  `audit_observation`; spec #89's fourth call `calibration_rung` is not built)
- `src/skill_harness/storage/migrations_sql/evidence/0700_task_frontier.sql`
  (three tables, per-table `phase` CHECK, `append_only_violation` triggers)
- `tests/task_frontier/test_tracer.py` (pins the exported surface so a bulk
  convenience accessor cannot reopen the leak path; proves the stamp is a snapshot)
- `tests/storage/test_task_frontier_store.py` (proves the triggers and the
  per-table phase CHECKs actually fire)

Scope: #90 built the tracer. Total refusing manifest validation (#92), the
matched-phase feed into `oc/gate2` (#91), confirmation-attempt accounting (#93) and
the synthetic no-leak proof (#94) are **not yet built**.

Spec: skill-harness #89 (task-frontier MVP), spine #84 unit 2.

## 8. Tie encoding: estimand of record, and the measured error of the interim heuristic

**The estimand of record is the DISCORDANT TABLE** — the McNemar/sign-test
convention. Concordant pairs carry no directional information about a paired
difference, so conditioning on discordant pairs is the settled answer in the
paired-binary literature, and it is what Gate 2 (`oc/gate2.py`) already requires.
Ruled 2026-08-31 on #368, after items 3 (#345) and 5 (#347) measured the same
deviation from two sides.

**Half-update (Win=1.0, Tie=0.5, Loss=0.0, `n += 1`) remains the operational
stopping heuristic in the interim.** Under it the posterior converges to
`Beta(1+w+t/2, 1+l+t/2)`, so the mean is pulled toward 0.50 as the tie count grows.
Measured on the win-heavy fixture: `w=8, l=0, t=16` gives `P(rate > 0.60) = 0.726`
(INCONCLUSIVE) where drop-ties gives `0.990` (PASSED); posterior-mean shift up to
0.178.

**The "dilution is always toward 0.5" argument is FALSE, and is recorded here
because the ruling first asserted it.** A sweep over `w, l in [0, 60]`,
`t in [1, 80]` found **80,011 grid points where half-update RAISES**
`P(rate > 0.60)` relative to drop-ties — loss-leaning cases pulled UP toward 0.5.
Worst observed: `w=0, l=2, t=7`, `0.0996` against `0.0640`. The error is not
monotone and must not be described as such.

**What survives is narrower, and it is a receipt rather than an argument:**

| Gate | Measured on the grid above |
|---|---|
| PASS (`P >= 0.95`) | **Zero** grid points where ties push a clause across the gate that drop-ties keeps below it. A false KEEP cannot be minted by tie encoding anywhere on that grid. |
| FAIL (`P <= 0.05`) | **Three** grid points where a drop-ties-FAILED clause escapes the gate (first: `w=0, l=3, t=5`, `0.0527` against `0.0256`). All three escape to INCONCLUSIVE, never to PASS. |

So the cost is a **delayed** verdict — a measurement-time cost — and not a
claim-integrity cost. That asymmetry is the entire justification for keeping the
interim heuristic, and it is bounded by the grid, not proven in general.

**The locked 0.60/0.95/0.05 thresholds do NOT transfer unexamined** to the
conditional parameter `P(full wins | discordant)`. They were calibrated against the
blended rate. Re-deriving them is part of the migration and must be pre-registered
before any production run consumes the result.

**Path C migration (landed #368).** The ablation lane now routes tie-heavy clause
decisions through the Gate-2 discordant machinery (`ablation/gate2_stopping.py`),
consuming the registered design form and thresholds from Amendment 4 of
`docs/findings/v0.2-preregistration.md` (gamma=0.90, delta_min=0.20, q_min=0.70,
PR #386, RAT-0001 #391). When ties are present, the decision comes from Gate-2's
three-sided rule; when Gate-2 returns UNRESOLVED, the scalar thresholds on the
discordant-only `Beta(1+w, 1+l)` determine the stop decision. This produces a
`StopDecision` compatible with the ablation runner and ensures the production path
matches the drop-ties recompute on the registered fixture scenarios.

The seven strict xfails in `tests/test_halfupdate_tie_sensitivity.py` that marked the
former sensitivity between half-update and drop-ties have been removed: the production
path and the drop-ties oracle now agree on every fixture scenario (divergence = 0).

Enforced in / recorded by:
- `src/skill_harness/ablation/gate2_stopping.py` (the Gate-2 discordant stopping
  wrapper for the ablation lane)
- `src/skill_harness/aggregation/fit.py`, `ablation/stopping.py` (the half-update
  encoding this section qualifies; `stopping.py` is the legacy scalar artifact)
- `docs/findings/halfupdate-tie-sensitivity.md` (the finding and its fixtures)
- `tests/test_halfupdate_tie_sensitivity.py` (xfails removed; production path and
  drop-ties agree on all scenarios)
- `docs/assurance/halfupdate-tie-migration-mutation-receipt.md` (mutation receipt
  for the migration)

Scope: the Path C migration is landed. The scalar `BetaBinomialAccumulator` in
`stopping.py` remains as the legacy artifact for zero-tie cases and is NOT modified
(#42: parallel machinery, not a refactor). The diagnostic clause-aggregation lane
(`fit_skill`, #360/#405) keeps `sum_sq` and its own amendment (scope boundary per
maintainer correction on #360).

*Revisit if:* a production design exceeds the swept grid (`w, l > 60` or `t > 80`),
in which case re-run the sweep before relying on the PASS-gate zero; or a tie-heavy
axis shows the practical-significance inversion, where rare-but-real wins are drowned
by ties in a way that matters operationally — that is an effect-size floor question
for the Gate-2 net-lift bounds, not a reason to resurrect the blended rate; or #420's
re-pick changes gamma or the MME, which it is not expected to.

Spec: skill-harness #368 (ruling, amendment, and Path C migration), #347 (item 5
detector), #345.

## 9. The model pin is provenance, not a staleness badge

Every newly-minted verdict carries an `ArticleFingerprint` — `mint_oracle_verdict`
requires one — so **no cell floats free of the model it was measured on**. That is
the pin's whole job, and it is discharged at write time.

**Verdicts are NOT badged stale against fleet-model drift**, and this is a decision
rather than an omission (#337).

`is_stale_vs_fleet(stored_drift_fingerprint, current_fleet_model)` exists in
`storage/article_fingerprint.py` and is unit-tested. It has **no production caller**,
because there is nothing in this repository that can supply its second argument:
`subject_model` is a **per-run parameter** of `run_ablation` (default
`claude-sonnet-4-6`), so different runs legitimately carry different models and no
designated "current fleet model" exists to compare against. A badge would first
require designating one.

The staleness axis that DOES gate a claim is a different one, and it is already
enforced: `frozen_cases_with_currency` labels a frozen case `current` only when its
`metric_version` AND `implementation_hash` match the current audited metric version,
and `derive_clause_status` requires `current_frozen_case_count >= 1` for PASSED
(A15/A57, §1 and §3). That axis is the **measuring code**, which can invalidate a
number. Fleet-model drift is the **subject**: a verdict measured on an older model is
not wrong, it is a claim about that model, and re-reading it as a claim about today's
model is the error a reader must not make.

So the pin answers *what was this measured on*, and the currency gate answers *is this
still computable the same way*. Neither is a substitute for the other.

Enforced in:
- `src/skill_harness/storage/article_fingerprint.py` (the pin, and the unused comparison)
- `src/skill_harness/storage/repositories/evidence/oracle_verdicts.py::mint_oracle_verdict`
  (structurally requires the pin)
- `tests/test_article_fingerprint.py::test_fleet_staleness_comparison_has_no_production_caller`
  (pins this decision: wiring a caller turns it red and forces this section to be revisited)

*Revisit if:* a current-fleet-model pointer is designated — a config key, a registry
row, anything a reader can name. At that point the comparison has a target, the badge
becomes buildable, and the argument above expires on its own terms. Also revisit if a
verdict is ever re-read as a claim about a model other than its own `model_snapshot`,
which is the failure this section exists to make visible.

Spec: skill-harness #337, #75/#81 (the pin), #352 (the no-caller verification).

## 10. Treatment = exposure; invocation is a recorded stratifier

**The treatment is exposure** — the skill's description present in the agent's
context — **not** invocation (Skill tool call). Exposure is measured per epoch by a
channel-(c) detector (v2): the card's description text, read from the pinned
`SKILL.md` frontmatter (single-line or folded block scalar), present in the
transcript's skill listing. `exposed_skill` is `bool | None`: `True`/`False` are
measured verdicts; `None` is typed "not computed" (screen lane) and is never stored
as `False`. Under the `inspect_swe.claude_code` solver the first user message
carries Claude Code's skill listing and the card's frontmatter description appears
in it verbatim (8 of 8 Full epochs and 0 of 8 Null epochs, measured 2026-09-01).

**π_c is a mandatory recorded stratifier**, not an admission gate. Zero invocations
with full exposure is ADMISSIBLE — the write proceeds and the verdict line carries
pi_c = 0/n. At pi_c = 0 the CACE secondary is stated as not identified, never
computed.

**Two refusal predicates enforce treatment fidelity:**

(a) A Full-arm epoch with exposure not detected refuses as `UnexposedFullEpochError`
(treatment not delivered). The skill's description was not present in the transcript —
this is an apparatus error, not evidence.

(b) A Null-arm epoch with exposure or invocation detected refuses as
`NullArmContaminationError` (control-arm contamination, widened from the #46
invocation-only check to include channel c). The Skill tool is structurally not
launchable in the Null arm and the skill's description is not mounted, so either
detection means mislabelled arms or a misconfigured harness.

Enforced in:
- `src/skill_harness/subject/ingest.py::_validate_pair` (the two refusal predicates,
  lines 848–890)
- `src/skill_harness/subject/ingest.py::detect_skill_exposure` (v2 channel-c detector)
- `src/skill_harness/subject/ingest.py::detect_skill_invocation` (v1 Skill tool-call
  detector, unchanged)
- `tests/test_subject_ingest.py::test_full_arm_unexposed_refuses` (predicate (a))
- `tests/test_subject_ingest.py::test_null_arm_exposed_refuses` (predicate (b), channel c)
- `tests/test_subject_ingest.py::test_null_arm_invoked_still_refuses` (predicate (b),
  channel b — the 0/22 fixture from #46)
- `docs/assurance/exposure-refusal-mutation-receipt.md` (#341 mutation receipt: M-X1
  kills predicate (a), M-X2 kills the channel-c half of predicate (b))

*Revisit if:* a non-`claude_code` solver whose transcript lacks the skill listing
enters production — the v2 detector would fire False on every Full epoch, refusing
every pair as unexposed. The detector version constant (`EXPOSURE_DETECTOR_VERSION`)
and the `_extract_skill_description` path would need a new channel for that solver.

Spec: skill-harness #384 (the ruling, Amendment 3 of v0.2-preregistration.md,
landed by #386).

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
