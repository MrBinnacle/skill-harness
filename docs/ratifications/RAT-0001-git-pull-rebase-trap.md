---
rat: RAT-0001
status: RATIFIED
skill_id: git-pull-rebase-trap
task_family: gitpull
estimand: treatment-policy
gate: gate2
n: 32
worst_case_cost_usd: 23.351744
hard_cap_usd: 23.36
cost_provenance: project_pair_usd
sme_status: self-certified
ratified_date: "2026-09-02"
gamma: 0.90
delta_min: 0.20
q_min: 0.70
---

# RAT-0001 — git-pull-rebase-trap row-pick

This record is RATIFIED, signed 2026-09-02 (section 9). Every field below the status line is
filled from Amendment 4 of `docs/findings/v0.2-preregistration.md`, which registered the design,
the grid, the cost basis, the frontier and the conforming rows on 2026-09-01. The signature
authorizes one thing: spending up to `hard_cap_usd` on one sized paired run of this skill. Nothing
in this record was a technical call left to the signer; the technical content is registered
upstream and copied here so the gate and drift row DC-12 can read it.

## 1. Record

- Id: RAT-0001. Ledger position: first record in `docs/ratifications/`.
- Drafted 2026-09-02 from Amendment 4 (commit `9264b0447711733725f2e75649263dba45697009`, landed by
  skill-harness#386). Status history: DRAFT (2026-09-02), RATIFIED (2026-09-02).
- Parent tickets: skill-harness#391 (this record and the sized run), #368 (Amendment 4's items 2
  and 3), #384 (Amendment 3, the exposure ruling the run's ingest applies).

## 2. Scope

- Skill id: `git-pull-rebase-trap` (the collection's card name; the pair receipt
  `docs/sers/receipts/gitpull-paired-k8-2026-09-01-detector-v2.json` records the same card under
  `skill_name` with subject identity sha256 `387989fed2eda3b083ea6ce8094ff0c3685e08e738b6ed58df97da8242dbcb96`).
- Task family: `gitpull` (the micro-run batch this pair belongs to; the sized run declares the
  same slug in its runner config, and the ingest records it in `config_json`).
- Estimand: `treatment-policy` (registered name; Amendment 3 rules treatment is exposure, pi_c a
  recorded stratifier).
- The paired-lane runner sits outside the `run ablation --execute` gate. Per Amendment 4 the
  ratification reference goes into the runner's config and is recorded at ingest; the runner's
  declared `skill_id`, `task_family` and `estimand` must equal the three values above exactly.

## 3. Gate identity + knobs

Gate-2, `Gate2Design(n_pairs=32, gamma=0.90, MMESpec(delta_min=0.20, q_min=0.70))`; three-sided
rule over the discordant lattice; deterministic curtailment on; decision to verdict through
`effect_from_matched_gate2` and `matched_gate2_verdict`, `value_class` supplied by the caller
(`trap-discipline` for this card).

## 4. Registered MME pair

`delta_min = 0.20`, `q_min = 0.70` (#40).

## 5. Chosen row

The recommended row from Amendment 4, copied without change: `gamma = 0.90`, `n = 32`.
Attained worst-case false-direction rate on the certified Bernstein bound: `alpha[cert] = 0.0161`.
Power at the binding H1 point (0.6, 0.9): `0.826`. `E[N]` under H1: 29.9. Amendment 4's reason for
this row over the others: a three-fold margin under the 0.05 target with eight fewer pairs than
`gamma = 0.95` needs, and $5.84 under that row's cost. The cheapest conforming row is
`gamma = 0.85, n = 26` at $18.97 with `alpha[cert] = 0.043`; it was not chosen because it sits one
grid step from the target. Both are conforming; the recommendation is the registered one.

## 6. Cost block

- Subject model and pricing key: `claude-sonnet-5`, `PRICE_PER_MTOK` input $2.00 / output $10.00
  per MTok, cache write $2.50 / read $0.20 (snapshot 2026-08, `src/skill_harness/ablation/subject.py`).
- Calibrated tokens per pair, both arms, measured on the 2026-09-01 pilot: 353,721 input (all
  classes), 2,230 output.
- `project_pair_usd("claude-sonnet-5", input_tokens_per_pair=353721, output_tokens_per_pair=2230)`
  = $0.729742 per pair, computed live on 2026-09-02 (front-matter `cost_provenance`). Worst-case
  fixed-N cost at n = 32: $23.351744. No cache discount is assumed; the pilot realised $0.26 per
  pair with 86 percent cache reads, and the cap tests the worst case by rule.
- `hard_cap_usd = 23.36`, the worst case rounded UP to the cent, under the registered $35 ceiling.
  Amendment 4 prints the same row as $23.35 (rounded to nearest); the cap is the rounded-up figure
  by README rule.
- Pre-spend re-measurement: if tokens per pair re-measure above **353,850 input** at this pricing
  and output figure, the row breaches the cap and the run does not launch; a dated amendment
  records why (#391 acceptance). Note: this bullet read "above about 470k" until Amendment 1 measured
  the breakeven; see section 10, and note that the true headroom is 129 tokens per pair, not 33
  percent.

## 7. Frontier provenance

- Frontier report: Amendment 4 of `docs/findings/v0.2-preregistration.md` at commit
  `9264b0447711733725f2e75649263dba45697009`, computed with `oc.frontier.frontier_row` (exact
  enumeration, curtailed operating characteristics) on 2026-09-01.
- Green drift-check: the `CI` workflow run on that commit, run id `33560579210`, conclusion
  `success`, 2026-09-01T21:21:02Z, which executes `scripts/drift_check.py`.

## 8. SME deliberation status

Self-certified. The #45 deliberation clock never started (#59 record), so the 21-day expiry branch
applies by construction: frontier tables published 2026-09-01, plus 21 days, expires 2026-09-22;
this record is drafted inside that window and the branch is taken because no engagement exists to
wait for. Verbatim disclosure: **internally derived, not externally deliberated**.

## 9. Signatures

SME dispositions: none (expiry branch, section 8).

Operator signature, LAST, pre-spend: **SIGNED.**

- Signer: MrBinnacle, maintainer.
- Date: 2026-09-02.
- Channel: the maintainer's own session, in reply to the reduction posted on #391, which states
  that saying the sentence in any channel is the signature.
- Words, verbatim: *"ratify RAT-0001 at $23.36"*.

The act this signature performs is one sentence, and it was the only decision in this record that
was the operator's: authorize one sized paired run of git-pull-rebase-trap at up to $23.36.
Everything else in this record was registered before the signature and does not change with it.

What the signature does NOT authorize: a second run, a re-run after a failed ingest, a different
row, or any spend above `hard_cap_usd`. Each of those needs its own dated block or its own record.
The pre-spend token re-measurement still gates the launch: if the recomputed worst case exceeds
`hard_cap_usd`, the run does not launch and a dated amendment in section 10 records why.

## 10. Post-launch amendments

Dated blocks only, appended below this line: run_id(s), any later SME upgrade, and corrections to
the record's own prose. No registered field is edited in place; a change to a registered field is a
new row-pick and a new record.

### Amendment 1 — 2026-09-02: the breach threshold in section 6 was wrong by three orders of magnitude of headroom

Section 6's last bullet says the row "breaches the cap at this pricing" if tokens per pair
re-measure "above about 470k". That figure is wrong, and it is wrong in the unsafe direction: it
tells a reader the cap has roughly 33 percent headroom when it has 0.036 percent.

Measured 2026-09-02 by bisecting `project_pair_usd("claude-sonnet-5", ...,
output_tokens_per_pair=2230)` against `hard_cap_usd` at `n = 32`:

| Input tokens per pair | Worst-case cost at n = 32 | Against the $23.36 cap |
|---|---|---|
| 353,721 (registered) | $23.351744 | within, by $0.008256 |
| **353,850** | **$23.360000** | **the exact breakeven** |
| 353,851 | $23.360064 | breach |
| 400,000 | $26.3136 | breach |
| 470,000 | $30.7936 | breach |

**The breach threshold is 353,850 input tokens per pair, not about 470,000.** The registered
figure sits 129 tokens under it. The arithmetic is not subtle: `hard_cap_usd` was set by rounding
the worst case UP to the cent, so by construction the headroom is at most one cent, and one cent
buys 129 input tokens at $2.00 per MTok across 32 pairs. Any cap derived by rounding up to the
cent has this property; the 470k sentence was a free-hand estimate that no one recomputed.

**What this changes.** Nothing about the signature or any registered field. `gamma`, `n`,
`delta_min`, `q_min`, the cost basis and `hard_cap_usd` are unchanged, and the operator's
authorization still reads as it did. What changes is what the pre-spend check means in practice:
it is knife-edge on the token re-measurement, and a re-measurement that moves at all upward
refuses the launch.

**What this does not mean.** It does not mean the run is likely to cost $23.36. The cap bounds a
worst case computed with no cache discount; the 2026-09-01 pilot realised $0.26 per pair with 86
percent cache reads, about a third of the projected per-pair figure. Actual spend and the cap are
different quantities, and only the projection is knife-edge.

**Pre-spend re-measurement, run 2026-09-02.** Recomputing tokens per pair over the two pilot eval
logs in the batch-1 `gitpull` log directory returns 353,721 input across all classes and 2,230
output — identical to the registered figures, so the projected worst case is $23.351744 and the
launch is within the cap. Read the next sentence before relying on that: this reproduces the
registered figures from **the same source that produced them**. It confirms the arithmetic is
faithful to the pilot; it is not independent evidence that a 32-pair run will use the same tokens
per pair. A genuinely independent
re-measurement requires a run, which is the thing the check gates.

*Revisit if:* `hard_cap_usd` is ever set by a rule other than rounding the worst case up to the
cent, which would give the cap real headroom and make a stated breach threshold meaningful again;
or a later run measures tokens per pair and the projection is rebuilt on that measurement.

### Amendment 2 — 2026-09-03: the authorised run was performed once, its decision is UNRESOLVED, and its measured tokens per pair falsify section 6's projection basis

**The run.** Launched 2026-09-03 02:36:16 UTC from the batch-1 `gitpull` directory by
`stage2_gitpull_sized.py`, after a dry run that resolved the registered figures exactly (n = 32,
gamma = 0.90, worst case $23.351744 against the $23.36 cap). Subject `anthropic/claude-sonnet-5`,
route `anthropic-direct`, sandbox image `aisiuk/inspect-tool-support@sha256:fb045da8…`, pin
fingerprint `706cbaea…cffa1b`. Full arm: 32 of 32 samples, 23 min 25 s. Null arm: 32 of 32
samples, 22 min 30 s. Zero HTTP retries in either arm. Exposure detected in 32 of 32 Full epochs
and 0 of 32 Null epochs; the skill was invoked in 24 of 32 Full epochs.

**Ingest.** The runner refused at ingest with `MetricImplementationDriftError`: the
`subject:command_succeeds` 0.4.0 identity had been registered on 2026-09-02 against
`subject/ingest.py` at 4001686, and #411 and #413 then edited that module (28 insertions, all
imports, signatures, docstrings and config plumbing, including the `runner` block that section 2
of this record requires). The identity was declared anew as 0.4.1 (skill-harness#416) and the
run's own eval logs were ingested from disk under it as run
`0700d089a0275ed27d3e219a680e1959bd69ec11e7841a4280d95a4e17243907`, with the runner block
recorded: `rat_id RAT-0001`, `skill_id git-pull-rebase-trap`, `task_family gitpull`, `estimand
treatment-policy`, `route anthropic-direct`. This was a re-ingest of the authorised run's logs.
No second run was launched; section 9 was not exceeded.

**Decision read.** `run evaluate-paired` first refused the run on `skill_id`, because it compared
this record's card name to the run row's content digest instead of to the runner-declared block
that section 2 names; fixed in skill-harness#417. With that fix the read is:

| Field | Value |
|---|---|
| Discordant lattice | both_pass 32, full_only 0, null_only 0, both_fail 0 |
| Decision | `unresolved` |
| Signed delta | 0.000, 95% CI [-0.107, 0.107] |
| pi_c_hat | 24/32 = 0.7500, 95% CI [0.5660, 0.8854] |
| Verdict (`trap-discipline`) | `CANT_TELL_YET` |

A zero-discordant table is a defined `UNRESOLVED` branch of the registered rule (#37); it
overrides any equivalence mass, so the decision is the rule's output and not an instrument
failure. What the run observed is that under this task the trap did not fire in the Null arm
either: both arms passed every sample, so the instrument saw no contrast to decide on.

**What the transcripts say, read 2026-09-03 from the eval logs (every bash tool call, both
arms, both runs).** The trap this card patches is `git pull` under `pull.rebase=true`, where
`--no-ff` is silently ignored and local SHAs are rewritten. Entering it requires the agent to run
`git pull`. Measured:

| Arm, subject | n | ran `git pull` | ran `git rebase` | ran `fetch` + `merge` | passed oracle |
|---|---|---|---|---|---|
| Pilot Null, `claude-sonnet-4.5` (2026-09-01, same fixture and prompt) | 8 | 3 | 8 | 0 | 0 |
| Pilot Full, `claude-sonnet-4.5` | 8 | 4 | 1 | 4 | 6 |
| This run Null, `claude-sonnet-5` | 32 | 0 | 0 | 32 | 32 |
| This run Full, `claude-sonnet-5` | 32 | 0 | 0 | 32 | 32 |

No Sonnet 5 epoch in either arm ran `git pull`. All 64 fetched and merged, which the ancestry
oracle passes. The armed `pull.rebase=true` config was never exercised, so the run did not test
the trap; it measured whether this model rebases by habit, and it does not. The pilot's contrast
was mostly the other mechanism: Sonnet 4.5 rebased explicitly in 8 of 8 bare epochs, 5 of them
without pulling at all, and the card's description in context talked it into merging. That is
lift for that model on this task, but it is not the `--no-ff` trap the card describes.

**This ceiling was already on record.** OBS-0007, in the maintainer's research ledger of
backward-looking observation records (created 2026-08-04 for a screen of 2026-07-20), ledgers
the stage-0 Null screen on this same fixture with stock `claude-sonnet-5`: 3 of 3 pass, p0 = 1;
its evidence is screen run `dae60c17…` in the private screen store beside this run's logs.
Its disposition says a ceiling on this fixture carries no signal for a trap-discipline skill and
that the honest measurement is hazard-enriched, with the agent placed in front of the hazard.
This run reproduced that ceiling at n = 32.

**The assumptions this exposes, each falsified by a row above.**

1. That the oracle's pass means the trap was avoided. It means ancestry was preserved, which a
   model that never pulls achieves without meeting the trap. The instrument does not record
   whether the trap was entered.
2. That the task elicits the trap-entering action. "Integrate the teammate's changes, then push"
   is satisfied by `fetch` + `merge`; nothing in the prompt makes `git pull` the natural move.
   The de-leaking of 2026-09-01 removed the history-policy signpost and, with it, any reason to
   touch `pull` at all.
3. That the pilot's Null rate transferred to the priced subject. The pilot ran Sonnet 4.5
   because the host had no Anthropic key; the record priced Sonnet 5; nobody re-screened the
   Null arm on Sonnet 5 before sizing, although OBS-0007 had already measured it at the ceiling.

**What follows.** The decision above stands as the rule's output on the data. It is not evidence
about the skill's value for a model that does pull, and the maintainer reports that on
`claude-opus-5` in ordinary work the trap fires routinely; that model has not been measured
here. Before any further row-pick on this family: a task version in which pulling is the
natural move (naming the action is not leaking the rule; the rule is "check `pull.rebase`
first"), oracle re-validation at zero cost, an instrument covariate recording whether each epoch
ran `git pull`, and a Null screen on the priced subject. Filed as a skill-harness ticket from this
amendment. None of that is spend under this record.

**Measured tokens per pair, and what they do to section 6.** Read from the eval logs' usage
totals, both arms, all input classes, divided by 32 pairs:

| Quantity | Registered (section 6) | Measured (this run) |
|---|---|---|
| Input tokens per pair | 353,721 | **539,011** (ratio 1.524) |
| Output tokens per pair | 2,230 | 2,963 |
| Cache-read share of input | not assumed | 98.6 percent |
| No-discount worst case at n = 32 | $23.351744 | **$35.44** |
| Spend at section 6 prices | cap $23.36 | **$4.93** computed from the logs, not read from the billing console |

The cap held in realised dollars by a factor of about 4.7, because 98.6 percent of the input was
served from cache at $0.20 per MTok. The projection basis did not hold: the measured input per
pair is 52 percent above the registered figure and 185,161 tokens above the 353,850 breakeven
that Amendment 1 established. At the measured rate the no-discount worst case exceeds not only
`hard_cap_usd` but the registered $35 ceiling. The pre-spend re-measurement on 2026-09-02 could
not see this, for the reason Amendment 1 stated in advance: it reproduced the registered figures
from the pilot logs that produced them, and the pilot had 8 pairs of a task whose transcripts
grew longer at 32.

**What this changes.** No registered field is edited; `n`, `gamma`, `delta_min`, `q_min`,
`hard_cap_usd` and the cost basis stand as signed, and the authorised run was performed once
within the cap. What changes is the standing of section 6's projection basis for any later
row-pick on this task family: it is falsified in the unsafe direction and must be rebuilt from
the measured 539,011 input tokens per pair, or from a projection that prices cache reads
explicitly, before another cap is set. That rebuild is a new row-pick and a new record, per the
rule at the head of section 10.

**What this does not authorise.** A second run of this design, a re-run under a rebuilt cost
basis, or any spend on this record beyond the one run already performed.

**Pending.** A SERS receipt for run `0700d089…` has not been minted; the collection's card for
`git-pull-rebase-trap` therefore does not yet carry this run. Until it does, this record and the
evidence store are the only places the decision is written.

*Revisit if:* a receipt is minted for this run, which should be recorded here as a dated line; or
a rebuilt cost basis for `gitpull` is registered upstream, which supersedes the table above for
projection purposes but not as the measurement of this run.

2026-09-03 — receipt minted: `docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json` (skill-harness#423).

## 11. Historical-classification obligation

n/a — not the first Gate-1 row-pick (this is a Gate-2 record; the obligation attaches to the first
Gate-1 record only).
