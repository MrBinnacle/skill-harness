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

- `landed_as: UNLANDED #520`

### 2. The tested component set — Declined

Which components of the skill were under test in this measurement.

**Declined:** a costing pass found no enumeration of a skill's components
anywhere in `src/`. The nearest neighbour is `delivery.channel`, which names
which product carried the value, a different question. Landing the key before
the vocabulary exists produces a list whose members nobody can validate.

Revisit if a component vocabulary is decided anywhere, which makes this
addition ordinary schema plumbing and lapses the decline immediately.

- `landed_as: UNLANDED #520`

### 3. The implementation family and alternatives considered

What implementation family the skill belongs to and what alternatives were
considered.

- `landed_as: UNLANDED #520`

### 4. The cost vector and dominance rule — Declined

Cost dimensions and the rule for dominance comparison across realizations.

**Declined:** the ratifying document gives this one sentence, listing no cost
dimensions and no dominance rule. `git grep -niE "dominance|pareto|cost_vector|cost dimension" -- src/`
returns nothing. The schema's existing `cost` object is a fixed token triple
with no comparison logic. A schema shell could be added cheaply and would ship
with every leg permanently refused, which is a place to put a rule rather than
a rule.

Revisit if cost dimensions and a dominance rule are specified, which lapses
the decline.

- `landed_as: UNLANDED #520`

### 5. The claim scope and disturbance set

The scope of the behavioral claim and the set of disturbances under which it
holds.

- `landed_as: UNLANDED #520`

### 6. The retest triggers and expiry state

What triggers a retest and the expiry conditions for a result.

- `landed_as: UNLANDED #520`
