# Ratification records (RAT)

Forward-looking, append-only decision records: one file per row-pick, named
`RAT-NNNN-<skill-slug>.md` (four-digit numbering, ADR pattern). Ratifications
are decisions, not findings — the backward-looking siblings live in
[`docs/observations/`](../observations/) (OBS records). Location, signatories,
field shape, and the mechanical run binding were ratified on
[#47](https://github.com/MrBinnacle/skill-harness/issues/47); the
historical-classification obligation was added by the
[#41](https://github.com/MrBinnacle/skill-harness/issues/41) amendment.

Start from [`TEMPLATE.md`](TEMPLATE.md) (deliberately named so it never
matches the `RAT-*.md` ledger glob).

## What a record binds (mechanical, #47)

`skill-harness run ablation <skill_id> --execute` refuses to spend unless the
invocation references a record in this directory that:

- (a) exists with status **RATIFIED**;
- (b) states a `hard_cap_usd` exactly equal to the `--max-usd` value the run
  will register through `run_budget.hard_cap_usd` (compared as integer cents;
  caps are the worst-case fixed-N cost rounded **up** to the cent, never over
  the registered $35 per-evaluation ceiling);
- (c) scope-matches the invocation: `skill_id`, `--task-family`, and
  `--estimand` must equal the record's scope fields.

Dry-run stays ungated. The gate lives at the CLI layer
(`src/skill_harness/ratification.py` + `cli/main.py`), never inside the pure
`oc` package. Drift row **DC-12** independently re-checks every record's
internal consistency in CI (`scripts/drift_check.py`), with its own reader —
the two parsers are a deliberate differential pair.

## Record conventions

- **Status line:** `DRAFT` while assembling, flipped to `RATIFIED` by the
  signing flow below. Everything below the status line changes only by
  **dated amendment blocks, never edits** (house convention from
  `docs/findings/v0.2-preregistration.md`).
- **Front-matter:** the machine-parseable mirror of the load-bearing fields —
  exactly what the gate and DC-12 consume. The full eleven-field checklist
  lives as prose sections (see the template). The `cost_provenance` field
  must name the live cost_projection function that produced the cost block:
  `project_pair_usd` for a Gate-2 record, `project_trial_usd` for Gate-1 —
  never hand arithmetic, never a snapshot constant (DC-9 bans those).
- **Signing order (#45 via #47):** SME dispositions first (or the 21-day
  expiry branch), **operator signs LAST, pre-spend**. A self-certified record
  (expiry fired) must carry the verbatim disclosure line
  "internally derived, not externally deliberated" plus the expiry
  arithmetic. The signing commit is the evidence chain — git history is the
  tamper record.
- **Post-launch:** run_id(s) are appended by dated amendment once launched;
  later SME upgrades append the same way.
- **First Gate-1 row-pick obligation (#41):** the first Gate-1 RAT record
  must, in the same motion, classify every `docs/observations/` OBS record
  under the ratified thresholds by dated amendment on each OBS file. Any
  status-weakening reclassification mechanically opens a
  re-screen-eligibility ticket — a ticket, never spend.

## The eleven checklist fields (#47 + #41 amendment)

1. Record id, date, status.
2. Scope: skill id, task family, registered estimand name.
3. Gate identity + knobs.
4. Registered MME pair (delta_min, q_min).
5. Chosen row: n, attained error, power over the registered H1 region.
6. Cost block: worst-case fixed-N cost, pricing snapshot (PRICE_PER_MTOK
   values + calibrated tokens-per-pair + snapshot date), `hard_cap_usd`,
   cost provenance.
7. Frontier provenance: frontier report ref (commit SHA + path) + the green
   drift-check run it shipped under.
8. SME deliberation status (deliberated / self-certified branch).
9. Signature block (order above).
10. Post-launch amendments (run_ids, SME upgrades).
11. Historical-classification obligation (first Gate-1 record only; see
    above).
