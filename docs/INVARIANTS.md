# Invariants

Source comments across this codebase cite "CLAUDE.md" as the authority for a set of
locked thresholds and rules the code depends on. `/CLAUDE.md` is a local, gitignored file
(`.gitignore`, `/CLAUDE.md` entry) — it is not tracked, so those citations point at
nothing a reader of this repo can open. This file is the tracked anchor for the
invariants that matter; `docs/PRD.md` remains the full specification.

## 1. Pass rule (locked)

A clause PASSES when `P(win_rate > 0.60) >= 0.95` on the posterior, computed from
a `Beta(1,1)` prior. FAIL when `P(win_rate > 0.60) <= 0.05`. The thresholds are
unchanged and are quoted here verbatim; DC-1 checks that copy against the code.

**What `win_rate` NAMES has changed.** The posterior is now built from the
DISCORDANT TABLE — `Beta(1 + x_f, 1 + x_n)`, where `x_f` is the comparisons Full
won and `x_n` the comparisons the ablated condition won — so `win_rate` denotes
the conditional rate `q = P(Full wins | discordant)`. Ties are recorded and do
not enter it (#368 Path C, landed 2026-09-08; §8).

Until #368 the posterior was `Beta(1+w, 1+n-w)` with `w` the blended
half-update weight (Win = 1.0, Tie = 0.5, Loss = 0.0). **On a clause with no
ties the two are the same arithmetic** — `x_f = w` and `x_n = n - w` — so the
locked thresholds continue to mean what they meant wherever the blended rate
and the conditional rate coincide. They diverge only on clauses that recorded
ties, which is the footprint of the defect §8 records.

**The thresholds above are NOT the whole decision for a tie-bearing clause.**
`0.60/0.95/0.05` were calibrated against the blended rate, and §8 rules that
they do not transfer unexamined to the conditional parameter. A clause carrying
ties is decided by the registered Gate-2 three-sided rule on its realised
discordant table (`ablation/path_c.py`), which reads `gamma`, `delta_min` and
`q_min` from a ratification record rather than from any constant in the tree -
**and only when the run supplies such a record**; without one no Gate-2 decision
is made and the clause result says so in as many words (section 8).
The scalar rule above governs the sequential *stopping schedule*; it is not by
itself a licence to ship a clause whose net lift is below the registered
`delta_min`.

Enforced in:
- `src/skill_harness/aggregation/fit.py::WIN_RATE_THRESHOLD = 0.60` (the
  DIAGNOSTIC clause-aggregation lane, which still uses the blended half-update
  weight — see the scope note in §8)
- `src/skill_harness/ablation/stopping.py::WIN_RATE_THRESHOLD/PASS_PROB_THRESHOLD/FAIL_PROB_THRESHOLD = 0.60/0.95/0.05`
- `src/skill_harness/ablation/path_c.py` (the registered Gate-2 route; holds no
  threshold literals, and `tests/test_ablation_path_c.py` asserts it holds none)
- `src/skill_harness/aggregation/status.py::PASS_PROB_THRESHOLD/FAIL_PROB_THRESHOLD = 0.95/0.05`

Spec: `docs/PRD.md` §14 "Pass Rule"; skill-harness #368.
## 2. Pipeline safety (dry-run default)

Every command that writes to the evidence store or makes an LLM API call defaults to
dry-run, and `--execute` is required before it does either. That set is `run ablation`,
`run pi-paired`, `calibrate` and `freeze`.

The other `run` subcommands do neither, so no `--execute` gate applies to them and none
exists: `run evaluate-skill` opens the evidence database read-only through
`open_evidence_readonly` and aggregates stored verdicts, with an inverted `--dry-run`
opt-out; `run evaluate-paired` declares neither flag and makes no writes and no API calls.
`skill init` is gated differently again — clause extraction is a model call in both modes,
and `--execute` decides only whether the result is persisted.

Stated this way because the previous wording ("every `run` subcommand ... defaults to
dry-run") was false for two of the three, and the drift contract that pins this sentence was
holding the false version in place ([#469](https://github.com/MrBinnacle/skill-harness/issues/469)).

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

## 8. Tie encoding: estimand of record, and the migration that landed it

**The estimand of record is the DISCORDANT TABLE** — the McNemar/sign-test
convention. Concordant pairs carry no directional information about a paired
difference, so conditioning on discordant pairs is the settled answer in the
paired-binary literature, and it is what Gate 2 (`oc/gate2.py`) already requires.
Ruled 2026-08-31 on #368, after items 3 (#345) and 5 (#347) measured the same
deviation from two sides.

**Path C is BUILT (#368, 2026-09-08), and what it does and does not cover is
stated exactly below.** The ablation lane's sequential accumulator conditions on
the discordant table on every run. A Gate-2 decision on the realised table is
computed per clause **when the run supplies a RATIFIED record**, carried on
`ClauseResult.path_c`, with the ratification id recorded in `runs.config_json`.
What follows records the interim heuristic it replaced, because that reasoning
still decides things here and one half of it was wrong.

### What the interim heuristic was, and what it did

Half-update (Win=1.0, Tie=0.5, Loss=0.0, `n += 1`) converged to
`Beta(1+w+t/2, 1+l+t/2)`, pulling the mean toward 0.50 as the tie count grew.
Measured on the win-heavy fixture: `w=8, l=0, t=16` gave `P(rate > 0.60) = 0.726`
(INCONCLUSIVE) where drop-ties gave `0.990` (PASSED); posterior-mean shift up to
0.178.

**The "dilution is always toward 0.5" argument is FALSE, and is recorded here
because the ruling first asserted it.** A sweep over `w, l in [0, 60]`,
`t in [1, 80]` found **80,011 grid points where half-update RAISES**
`P(rate > 0.60)` relative to drop-ties — loss-leaning cases pulled UP toward 0.5.
Worst observed: `w=0, l=2, t=7`, `0.0996` against `0.0640`. The error is not
monotone and must not be described as such.

**What survived was narrower, and it is a receipt rather than an argument:**

| Gate | Measured on the grid above |
|---|---|
| PASS (`P >= 0.95`) | **Zero** grid points where ties push a clause across the gate that drop-ties keeps below it. A false KEEP could not be minted by tie encoding anywhere on that grid. |
| FAIL (`P <= 0.05`) | **Three** grid points where a drop-ties-FAILED clause escapes the gate (first: `w=0, l=3, t=5`, `0.0527` against `0.0256`). All three escape to INCONCLUSIVE, never to PASS. |

That one-sided-safety is why the heuristic was allowed to stand while the
migration was unbuilt. It is not a reason to keep it now that the migration
exists: a delayed verdict is still a cost, and the receipt bounded it only on
the swept grid.

### What Path C actually changed

Two changes, at one seam, and the second is the one that is easy to miss.

**(a) The posterior conditions on the discordant table.**
`BetaBinomialAccumulator` records `(x_f, x_n, ties)` and updates
`Beta(1 + x_f, 1 + x_n)`. `delta_to_observation` is UNCHANGED and still returns
0.5 for a tie: the encoding was never the defect, because a tie is a real,
correctly-labelled outcome. The defect was crediting it to both sides of the
posterior. N_MAX still counts total comparisons, because a tie costs a sample;
N_MIN now counts discordant comparisons, because a tie is not evidence about `q`.

**(b) Conditioning ALONE would have opened a new hole, so it is not the whole
migration.** `q = P(Full wins | discordant)` cannot see how often a direction
occurs at all. A clause that wins 7 of the 8 comparisons it did not tie, having
tied 30, has `Beta(8, 2)` and a net lift of 0.158. The scalar rule passes it.
This is exactly the practical-significance inversion the previous version of
this section named in its Revisit-if clause, and the sizing frontier now reaches
it: at `d = 0.2` the minimum detectable `q` is 0.97, a net lift of 0.188, under
the registered `delta_min` of 0.20.

`ablation/path_c.py` closes it by routing the realised table through
`gate2_decide`. Gate 2's Dirichlet pools the two tie cells, so the tie count
returns as evidence about the discordance rate `d` — which is what it always
was — and the decision is made on the net lift `delta = d(2q - 1)` against the
registered margin. The ablation lane's undifferentiated tie fits that pooling
exactly, because Gate 2 never needs the both-pass / both-fail split.

**The locked 0.60/0.95/0.05 thresholds still do NOT transfer unexamined** to the
conditional parameter, and Path C does not transfer them. It consumes `gamma`,
`delta_min` and `q_min` from a ratification record by reference and holds no
threshold literal of its own.

### What Path C does NOT claim

It takes `n_pairs` from the REALISED comparison count, not from the ratification
record's `n`. The ablation lane is sequential with a variable stopping point, so
it has no fixed N to match a registered one. The consequence is stated rather
than hidden: **the operating characteristics of a registered fixed-N Gate-2
design are not the operating characteristics of this lane.** A clause decided
here inherits the registered thresholds, not the registered design's error
rates. `gate2_oc` describes the fixed-N design; nothing in the ablation lane
does.

### What is wired, and the two places it stops

**Wired on every run:** the accumulator's discordant posterior. It has no
configuration and no opt-out.

**Wired only with a ratification reference:** the Gate-2 decision.
`run ablation --execute --ratification <record>` threads the record the
mechanical preflight already accepted through to the runner, which resolves the
thresholds once before any spend. **Without one there are no registered
thresholds and no decision is made** - `ClauseResult.path_c` is `None` and
`path_c_unavailable_reason` says which of `no_ratification_reference`,
`unregistered_thresholds` or `no_sampling` applies. That absence is a typed
refusal. A reader must not read it as a clause clearing the effect-size floor.

**NOT wired: the report surface.** The rendered ablation report still shows the
scalar `StoppingReason`, so a clause that PASSES the scalar rule and fails the
registered floor prints as PASSED. The Gate-2 decision exists on the result
object and is not yet displayed. Until it is, the rendered report is not a claim
about registered net lift, and this paragraph is the reason.

Enforced in / recorded by:
- `src/skill_harness/ablation/stopping.py` (the discordant accumulator, and
  `legacy_halfupdate_decision`, the superseded arithmetic kept addressable so
  the detector below retains a live subject)
- `src/skill_harness/ablation/path_c.py` (the registered Gate-2 route)
- `src/skill_harness/ablation/runner.py` (`run_ablation(ratification_path=...)`,
  `_decide_path_c`, and the `ratification_id` written into `config_json`)
- `src/skill_harness/cli/main.py` (threads `--ratification` from the preflight
  through to the runner)
- `src/skill_harness/ablation/sizing.py` (the exact DP, moved to the same rule)
- `docs/findings/halfupdate-tie-sensitivity.md` (the finding and its fixtures)
- `tests/test_halfupdate_tie_sensitivity.py` (the seven strict xfails are
  RESOLVED and their marks removed, bounds unchanged; the positive control is
  re-pointed at `legacy_halfupdate_decision` so it still measures a real gap)
- `tests/test_ablation_path_c.py` (thresholds by reference; the refusal when a
  record omits one; the tie-heavy clause held below the floor; and
  `TestRunnerWiring`, which asserts the runner REACHES this module - a code
  review of this migration found the module complete, tested, and called by
  nothing, while this section already claimed otherwise)
- `docs/assurance/path-c-tie-encoding-mutation-receipt.md` (#341 mutation receipt)

Scope: this section governs the production matched-efficacy path and Gate 2. It
does **not** settle what the diagnostic clause-aggregation lane (`fit_skill`,
`aggregation/engine.py`, #360/#405) measures heterogeneity in; that lane keeps
`sum_sq` and the blended half-update weight under its own amendment, and #368
did not touch it.

*Revisit if:* a production design exceeds the swept grid (`w, l > 60` or
`t > 80`) AND the superseded heuristic is being relied on for a comparison, in
which case re-run the sweep; or the ablation lane acquires a fixed-N design, at
which point `n_pairs` should come from the ratification record and this
section's "does not claim" paragraph is what expires.

Spec: skill-harness #368 (ruling, its amendment, and the Path C build), #347
(item 5 detector), #345.
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

## 11. Population integrity for enumeration-driven controls

An enumeration-driven control — one that discovers its own inputs by globbing a
directory, walking a tree, or reading a register — MUST record the cardinality and
the stable identity of the population it actually submitted to its detector, and
MUST fail closed when that population cannot be established as the declared
population.

A population failure is reported as `UNINTERPRETABLE`, never as `PASS` and never as
an ordinary `FAIL`:

```
population_valid = false   ->   verdict = UNINTERPRETABLE     (correct)
population_valid = false   ->   verdict = PASS                (the defect)
population_valid = false   ->   verdict = FAIL                (a false finding)
```

`PASS` and `FAIL` are both object-level claims about the subject, and neither is
available when the analysed universe is unknown. This is the discipline §3 already
applies to inadmissible evidence, one layer down: a detector saying "no defect found
in the cases I received" may not become "no defect exists" unless the system proves
it received the complete declared population.

The rule that generates this: **a downstream result cannot repair an upstream
validity failure.** A perfect assertion cannot repair an incomplete population.

Enforced in:
- `src/skill_harness/population.py` — the record, the digest canonicalisation, the
  verdict, and `require_valid_population`.
- `tests/test_receipts_index.py` — the first consumer, checking the receipt files on
  disk against the receipts `docs/receipts-index.md` declares, in both directions.

The contract is stated here and in code because it was violated by a control that
carried its rule only as a comment. Population metadata is independently testable,
including a negative control in which an expected member is omitted and the CONTROL
fails while the detector correctly passes over what it received.

Spec: skill-harness #453; the instance that produced it is #444.

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
