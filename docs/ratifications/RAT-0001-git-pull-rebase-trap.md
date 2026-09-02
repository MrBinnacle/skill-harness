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
  records why (#391 acceptance). ⚠ This bullet read "above about 470k" until Amendment 1 measured
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
launch is within the cap. ⚠ This reproduces the registered figures from **the same source that
produced them**. It confirms the arithmetic is faithful to the pilot; it is not independent
evidence that a 32-pair run will use the same tokens per pair. A genuinely independent
re-measurement requires a run, which is the thing the check gates.

*Revisit if:* `hard_cap_usd` is ever set by a rule other than rounding the worst case up to the
cent, which would give the cap real headroom and make a stated breach threshold meaningful again;
or a later run measures tokens per pair and the projection is rebuilt on that measurement.

## 11. Historical-classification obligation

n/a — not the first Gate-1 row-pick (this is a Gate-2 record; the obligation attaches to the first
Gate-1 record only).
