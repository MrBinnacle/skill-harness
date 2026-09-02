---
rat: RAT-0001
status: DRAFT
skill_id: git-pull-rebase-trap
task_family: gitpull
estimand: treatment-policy
gate: gate2
n: 32
worst_case_cost_usd: 23.351744
hard_cap_usd: 23.36
cost_provenance: project_pair_usd
sme_status: self-certified
ratified_date: "unsigned"
gamma: 0.90
delta_min: 0.20
q_min: 0.70
---

# RAT-0001 — git-pull-rebase-trap row-pick

This record is DRAFT. Every field below the status line is filled from Amendment 4 of
`docs/findings/v0.2-preregistration.md`, which registered the design, the grid, the cost basis,
the frontier and the conforming rows on 2026-09-01. The one act that flips it to RATIFIED is the
operator's signature in section 9, and that signature authorizes one thing: spending up to
`hard_cap_usd` on one sized paired run of this skill. Nothing in this record is a technical call
left to the signer; the technical content is registered upstream and copied here so the gate and
drift row DC-12 can read it.

## 1. Record

- Id: RAT-0001. Ledger position: first record in `docs/ratifications/`.
- Drafted 2026-09-02 from Amendment 4 (commit `9264b0447711733725f2e75649263dba45697009`, landed by
  skill-harness#386). Status history: DRAFT (2026-09-02).
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
- Pre-spend re-measurement: if tokens per pair re-measure above about 470k the row breaches the
  cap at this pricing and the run does not launch; a dated amendment records why (#391 acceptance).

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

Operator signature, LAST, pre-spend: **unsigned.** The act this signature performs is one
sentence, and it is the only decision in this record that is the operator's: *authorize one sized
paired run of git-pull-rebase-trap at up to $23.36.* The signing commit flips the status line to
RATIFIED, fills `ratified_date`, and records the signer's name and date here. Everything else in
this record was registered before the signature and does not change with it.

## 10. Post-launch amendments

None. Dated blocks only, appended below this line after launch: run_id(s), any later SME upgrade.

## 11. Historical-classification obligation

n/a — not the first Gate-1 row-pick (this is a Gate-2 record; the obligation attaches to the first
Gate-1 record only).
