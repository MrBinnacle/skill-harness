---
mirror: MIRROR-0001
source_page: "On Irreducibility"
source_page_id: "3b81351d-6af4-8006-8efa-f5f3a34fdf2c"
source_last_edited: "2026-08-11T17:33:55.553Z"
source_status: Done
source_verdict: HOLDS
ratified_date: "2026-09-13"
status: RATIFIED
---

# MIRROR-0001 — On Irreducibility (schema additions)

This record mirrors the ratified schema additions from the Notion page
"On Irreducibility" (status Done, verdict HOLDS, last edited 2026-08-11).
It is a mirror, not a row-pick: the `RAT-*.md` ledger and its DC-12
parser do not read this file.

## Verdict block (quoted from source)

> - **Claim:** An effective LLM skill implements a model-relative, cue-triggered
>   control relation with an external behavioral effect.
> - **Evidence limit:** The control relation is conceptual. The activation-chain
>   need has one prior zero-invocation result. Alternative realizations remain
>   untested.
> - **Kill criterion:** Controlled tests show reliable value without an
>   identifiable cue, governing distinction, behavioral difference, or external
>   evidence.
> - **Superseded recommendation:** Replace "build the smallest robust
>   realization" with "test local component necessity, then compare robust
>   realizations by declared cost."
> - **Rollback path:** Remove this extension if activation-stage records and cost
>   comparisons do not improve causal diagnosis or design choice.

## Schema additions

Each addition carries a `landed_as:` field naming the SERS schema key or source
symbol that implements it, or the literal `UNLANDED` with a ticket number.

The causal chain is: eligible situation -> availability -> invocation ->
adherence -> outcome. A SERS record should report each stage and name the
stage where the causal chain failed.

### 1. Activation-chain stages and failure location

The causal chain stages: eligible situation, availability, invocation,
adherence, outcome. A failed outcome does not identify a failed skill when
invocation did not occur.

- `landed_as: UNLANDED #514`

### 2. The tested component set

Which components of the skill were under test in this measurement.

- `landed_as: UNLANDED #514`

### 3. The implementation family and alternatives considered

What implementation family the skill belongs to and what alternatives were
considered.

- `landed_as: UNLANDED #514`

### 4. The cost vector and dominance rule

Cost dimensions and the rule for dominance comparison across realizations.

- `landed_as: UNLANDED #514`

### 5. The claim scope and disturbance set

The scope of the behavioral claim and the set of disturbances under which it
holds.

- `landed_as: UNLANDED #514`

### 6. The retest triggers and expiry state

What triggers a retest and the expiry conditions for a result.

- `landed_as: UNLANDED #514`
