# Architecture is admitted only when a downstream decision demonstrably requires it

Status: accepted, 2026-08-28.

This repository admits a structure -- a state, a field, a registry, a composition mechanism, an
epistemic distinction -- only after some downstream decision has been shown to require it. The
rule, stated by the operator on 2026-08-28:

> *"Do not let the architecture manufacture epistemic distinctions or causal claims that the
> experiment has not established a need for."*

The order matters and it is one-way. Establish that a decision needs the distinction, then build
the thing that carries it. A structure introduced because it sounds useful arrives carrying an
implied claim -- that something downstream turns on it -- and nothing has established that claim.
The harness exists to refuse unestablished claims about skills. It has no standing to make them
about itself.

## Why this record exists

The rule was already governing. It had decided at least four questions before it was written
down anywhere. Three of those four decisions had no durable record in this repository or its
siblings: not in a commit subject, not in an ADR, not in a checkpoint band, not in any file
under `docs/`. They were made in conversation and kept there.

That is a failure with a known shape. A decision held only in a channel the next session cannot
read is absent at the moment it is needed, and the work either stalls or re-derives it wrongly.
The three decisions below are therefore recorded here with their provenance stated plainly:
**conversation-derived, ratified 2026-08-28.** They are not presented as if a contemporaneous
written record existed. It did not, and concealing that would repeat the defect this record
corrects.

A content search of `docs/`, `src/` and `scripts/` at commit `9d145de` found no surviving trace
of any of the three -- no residue of the removed registry, no vocabulary from the composition
proposal, no statement of the artifact durability split. The absence is total, which is why the
record has to reconstruct rather than cite.

## The ratified applications

### 1. The cryptographic registry is removed

**Decided:** the payload-hashing, SLSA-provenance and cryptographic-registry machinery is not
part of this instrument and is not to be reintroduced.

**Ground:** the measurement problem does not require it. That machinery answers a question about
custody under an adversary -- who could have altered this record, and can we prove they did not.
No decision the harness makes turns on that answer. The evidence store is append-only and git
history is the tamper record; adding cryptographic authority on top asserts a threat model the
project has never established.

**Provenance:** conversation-derived, ratified 2026-08-28. Cited on 2026-08-28 as the precedent
for a separate ruling, which is the only reason its existence is recoverable at all.

*Revisit if:* the harness begins accepting evidence records produced by a party the operator does
not control, at which point custody stops being hypothetical and the threat model is established
rather than assumed.

### 2. Dynamic evaluator composition is rejected

**Decided:** evaluators are declared statically and frozen. An evaluator is not assembled at
runtime from smaller parts chosen by the caller.

**Ground:** composition manufactures evaluator identities that no decision required. It also
breaks the property receipts depend on. A receipt cites an evaluator; if the evaluator's identity
can be constructed or altered after the fact, the citation names nothing fixed. This is not
theoretical -- the executable-evaluator work (see
[`../design/executable-evaluators.md`](../design/executable-evaluators.md)) carried a protocol
declaring `spec` mutable, which meant no frozen implementation could satisfy it and a caller
could swap an evaluator's identity after a receipt had cited it. That was corrected before merge.

**Provenance:** conversation-derived, ratified 2026-08-28.

*Revisit if:* a specific measurement is blocked by static declaration and the blocking is
demonstrated on a real case, not projected from a general preference for flexibility.

### 3. Raw artifacts are durable; observations are disposable views

**Decided:** the raw artifact is the durable source of truth. An observation derived from it is a
view and may be discarded and recomputed.

**Ground:** the alternative promotes a derived representation to a record, and a derived record
carries the implicit claim that its derivation was correct and complete at the time it was
written. Nothing establishes that claim, and once the raw artifact is gone it cannot be checked.
Keeping the raw artifact durable keeps every derived question re-answerable.

**Provenance:** conversation-derived, ratified 2026-08-28.

*Revisit if:* a raw artifact class is found that cannot be retained -- for size, licence, or
privacy -- in which case the derived view becomes the only record and its adequacy has to be
argued explicitly rather than inherited from this rule.

### 4. `KEEP` / `CUT` / `CANT_TELL_YET` is untouched

The verdict vocabulary was tested against the rule and needed no change. It is recorded here as
the fourth application because a rule that only ever deletes things is being applied selectively.
This one survived: each of the three verdicts is required by a decision the operator actually
makes about a skill, and `CANT_TELL_YET` in particular is a refusal state that exists because the
alternative is an invented number.

*Revisit if:* a proposed fourth verdict is shown to be required by a decision the existing three
cannot express.

## Considered options

**File these under `docs/ratifications/`.** This is the alternative that will be proposed again,
because the directory's name fits. It is wrong on mechanism. A RAT record is a spend gate:
`skill-harness run ablation <skill_id> --execute` refuses to spend unless a RATIFIED record
scope-matches the invocation on `skill_id`, task family and estimand and states a `hard_cap_usd`
equal to the registered cap, and drift row DC-12 re-parses every record in CI with a second,
deliberately independent reader. See [`../ratifications/README.md`](../ratifications/README.md).
An architectural principle has no `skill_id`, no cost block and gates no spend. Filing it there
puts a file two parsers cannot read into the directory those parsers own.

**Leave the three decisions unrecorded and rely on the rule alone.** Rejected. The rule is
general and the applications are not derivable from it -- a later session applying the same rule
to the same question could reasonably decide the other way, and would have no way to know the
question had already been settled.

**Record the three without marking their provenance.** Rejected. It would read as though the
decisions had always been documented, which is the specific thing that was not true and the
specific reason this record was needed.

## Consequences

- A proposal that adds a state, a field, or a distinction now owes a named downstream decision
  that requires it. "It would be useful" is not that.
- This rule is upstream of the evidence and receipt schema work. It is the general form of the
  ruling that gates the schema freeze on the decision-set elicitation: establish the decision
  requires the distinction before introducing a state to carry it.
- This record does not say anything about whether the current evidence representation preserves
  the distinctions the harness's decisions require. That question is open and belongs to the
  decision-set elicitation, which has not run. Asserting it here would be the manufactured claim
  this ADR refuses.
- This is the repository's first ADR. `docs/adr/` is created by it, following the convention
  already in use in the two sibling repositories.

*Revisit if:* the rule is found to be blocking a measurement that the project needs and cannot
obtain another way. That is a change to what the instrument is willing to assert, and it is the
operator's call.
