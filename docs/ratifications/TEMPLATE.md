---
rat: RAT-0000
status: DRAFT
skill_id: <skill-id-as-passed-to-run-ablation>
task_family: <task-family-slug>
estimand: treatment-policy
gate: gate2
n: 0
worst_case_cost_usd: 0.00
hard_cap_usd: 0.00
cost_provenance: project_pair_usd
sme_status: deliberated
ratified_date: "YYYY-MM-DD"
gamma: 0.90
delta_min: 0.20
q_min: 0.70
---

# RAT-0000 — <skill-slug> row-pick

Copy this file to `RAT-NNNN-<skill-slug>.md` (next free number) and fill every
section. The front-matter above is the machine-parseable mirror of the
load-bearing fields — the gate and drift row DC-12 consume it; keep it in
lock-step with the prose. The `estimand` value must be a registered name
(`treatment-policy` or `hypothetical`, per the semantics registry). For a
Gate-1 record set `gate: gate1` and `cost_provenance: project_trial_usd`.
Status flips DRAFT -> RATIFIED only via the signing flow (README); below the
status line, dated amendment blocks only — never edits.

## 1. Record

Id, date, status history.

## 2. Scope

Skill id, task family, registered estimand name — must equal the front-matter
and the eventual `run ablation --execute` invocation exactly.

## 3. Gate identity + knobs

Gate-1 (theta_lo, theta_hi, gamma_q, gamma_r, extension floor, outer batch
cap) or Gate-2 (gamma).

## 4. Registered MME pair

delta_min, q_min (#40).

## 5. Chosen row

n, attained error (Gate-1 zone-edge pair / Gate-2 worst-case false-direction
bounds pair), power over the registered H1 region.

## 6. Cost block

Worst-case fixed-N cost; pricing snapshot: PRICE_PER_MTOK values used,
calibrated tokens-per-pair, snapshot date; `hard_cap_usd` = worst-case cost
rounded up to the cent, never above the registered $35 ceiling; provenance:
which live projection function produced these numbers (front-matter
`cost_provenance`).

## 7. Frontier provenance

Frontier report ref (commit SHA + path) and the green drift-check run it
shipped under.

## 8. SME deliberation status

Deliberated: engagement refs + per-charge-question disposition summary.
Self-certified (21-day expiry fired): the verbatim line
"internally derived, not externally deliberated" + the expiry arithmetic
(frontier-tables publication date + 21 days).

## 9. Signatures

SME dispositions (or expiry branch) first; operator signs LAST, pre-spend.
Name + date; the signing commit is the evidence chain.

## 10. Post-launch amendments

Dated amendment blocks appending run_id(s) and any later SME upgrades.

## 11. Historical-classification obligation

First Gate-1 row-pick record ONLY: classify every docs/observations/ OBS
record under the ratified thresholds by dated amendment on each OBS file,
recording the attained posterior. Status-weakening reclassifications open a
re-screen-eligibility ticket (ticket only, never spend). Other records state
"n/a — not the first Gate-1 row-pick".
