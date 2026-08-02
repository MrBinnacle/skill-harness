# OBS ledger — historical Stage-0 observation records

This directory is the **observation ledger**: one machine-parseable record per
historical Stage-0 screen in the program's registered record. It mirrors the
(planned) `docs/ratifications/` pattern: **RAT = forward-looking ratifications,
OBS = backward-looking observations** — symmetric, consistency-checkable.

The ledger exists so a future auditor can read each historical record as a
standalone entry — counts, scope pins, evidence basis, classification state —
without reverse-engineering them from prose. **The ledger is canonical for
per-record counts.** Prose surfaces (README, PRD, the v0.2 pre-registration,
case studies) each carry exactly one dated pointer here and do not restate
counts. History is annotated, never rewritten (re-scoping semantics ratified
in [#41](https://github.com/MrBinnacle/skill-harness/issues/41); spec
[#49](https://github.com/MrBinnacle/skill-harness/issues/49); ticket
[#50](https://github.com/MrBinnacle/skill-harness/issues/50)).

## Scope: the six records behind the 26/26 Null aggregate

This ledger covers the registered 26/26 Null-epoch record — the double-ceiling
aggregate registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(results section + Amendment 1). Reconciled decomposition, verified against the
registration and the retained raw evidence at ledger-authoring time
(2026-08-02):

| Record | Task family | Screen date | Stage-0 Null | Other Null epochs in the aggregate |
|---|---|---|---|---|
| [OBS-0001](OBS-0001-fts5-notes-search-v1.md) | fts5-notes-search-v1 | 2026-07-09 | 3/3 | — |
| [OBS-0002](OBS-0002-fts5-notes-search-v2.md) | fts5-notes-search-v2 | 2026-07-09 | 3/3 | 8/8 (Stage-1 Null arm, store-backed) |
| [OBS-0003](OBS-0003-sqlite-tie-break-red-test-trap.md) | sqlite-tie-break-red-test-trap | 2026-07-10 | 3/3 | — |
| [OBS-0004](OBS-0004-bayesian-eval-discipline.md) | bayesian-eval-discipline | 2026-07-10 | 3/3 | — |
| [OBS-0005](OBS-0005-append-only-evidence-design.md) | append-only-evidence-design | 2026-07-10 | 3/3 | — |
| [OBS-0006](OBS-0006-llm-judge-calibration.md) | llm-judge-calibration | 2026-07-10 | 3/3 | — |

Total: 18/18 Stage-0 Null epochs + 8/8 Stage-1 Null epochs = **26/26 Null
epochs across 6 independently-authored tasks**, exactly as registered.

**Reconciliation note.** The "6 task families" figure circulating in prose is
prose-derived; the reconciled referent is the registration's *6
independently-authored tasks* above (the two FTS5 task versions are distinct
tasks sharing one subject skill). Screens run *after* this registration lineage
— including the two live store-backed runs named in the repo README — are
separate records **outside** this ledger; they are natively store-audited and
enter the ledger only via a follow-up re-scoping. *Revisit if:* the Gate-1
classification obligation ([#47](https://github.com/MrBinnacle/skill-harness/issues/47))
is read to require ledger coverage of every pre-registry screen — then add OBS
entries for the post-registration screens by the same template.

## Front-matter contract

Every record carries YAML front-matter with exactly these fields (the parse
target for the planned DC-13 consistency check, registered on
[#43](https://github.com/MrBinnacle/skill-harness/issues/43)):

| Field | Meaning / allowed values |
|---|---|
| `obs` | `OBS-NNNN`, matches the filename |
| `task_family` | slug, matches the filename |
| `subject_skill` | the skill whose home task the screen exercised |
| `arm` | `null-only-stage0` (all records in this ledger) |
| `counts` | `epochs`, `passes` — Stage-0 Null epochs only |
| `model` | subject model id |
| `date` | screen date (UTC) |
| `scope_pins` | `agent`, `harness_pin_fingerprint`, `sandbox` |
| `evidence` | `store-ref` (raw `.eval` log in the committed `screen_backfill` lineage) \| `prose-backed` (registration prose is the citable basis) — honest split, no mixed canon |
| `evidence_ref` | the specific lineage or prose citation |
| `pi_c` | `not-instrumented` — the historical instrument did not measure compliance |
| `estimand` | `n/a` — pre-registry observation, no registered estimand |
| `classification` | `DEFERRED` until the first Gate-1 row-pick ratification (#47), which is obligated to classify all OBS records in the same motion; recorded then as a dated amendment with the attained posterior |
| `disposition_of_record` | the dated historical decision, standing; tense-marked. Keep/cut vocabulary appears **only** in this field — observation records assert counts, never skill verdicts |

Records are append-only: corrections and classification events land as dated
amendment blocks, never edits.
