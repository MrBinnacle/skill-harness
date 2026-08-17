# CONTEXT.md — skill-harness

Glossary only. Implementation detail lives in the PRD, SERS docs, and code.

**Skill**:
A user-authored instruction artifact (markdown instruction file, prompt module, behavioral overlay, Claude skill). The unit the instrument is pointed at.

**Clause**:
An atomic directional contract extracted from a skill — one axis, one comparator (e.g. axis `citation_support`, comparator `increase`).

**Condition**:
One of the three execution arms of a test: **Full** (complete skill), **Ablated** (exactly one clause removed), **Null** (no skill).

**Measurement**:
Directional, never absolute: `Full beats Ablated` or `Full beats Null` on a specific axis. An output by itself is not a measurement.
_Avoid_: "score" — the instrument refuses to collapse price and benefit into one number.

**Price / benefit**:
The ratified framing: a skill has a **price** paid in every conversation whether or not it fires (arithmetic on text, reportable for free) and a **benefit** that needs a paid comparison. Measured differently, refused differently, reported separately.

**Oracle**:
The thing that grades an arm's output. Three tiers: Tier 1 mechanical, Tier 2 human-calibrated judge, Tier 3 real-world consequence.

**Evidence admissibility**:
The gate deciding whether an observation may feed aggregation at all. Always written with the qualifier — the bare word is ambiguous and the public-copy guard enforces the qualified form.

**Verdict**:
`KEEP`, `CUT`, or `CANT_TELL_YET` — exactly the members of the code enum. `CUT` carries a mandatory sub-reason (`subsumed`, `no_lift`, `harmful`); a non-`CUT` verdict carries none. A verdict is measured or refused, never manufactured.
_Avoid_: the retired KEEP/CUT/UNMEASURED marketing frame — claim states are broader than that triad.

**Typed refusal**:
The core rule of the reporting standard: **a missing number is a typed refusal, never an invented score.** Every numeric field is a measured value or a refusal object with a closed vocabulary; there is no third path.

**Receipt**:
A SERS-conforming record of one result — schema-validated, enum-drift-checked against the code, comparable only within the same `sers_version`.

**SERS**:
Skill Efficacy Reporting Standard — the machine-readable vocabulary receipts conform to, so third parties can validate shape and results stay comparable.

**Unmeasured**:
A typed outcome, not an absence: the sub-reason vocabulary is fixed in the code enum and mirrored in SERS. Do not invent, rename, or subset it.

**Vacuity flag**:
An extraction-time exclusion mechanism: a flagged clause is excluded from scoring. It is not a quality verdict about the skill, and rates about it must be measured against the exclusion job it actually performs.

**Declared synthetic control**:
A synthetic positive result run through the full apparatus to prove the instrument can detect an effect. Marked `declared_synthetic_control: true`: instrument validation, never a product claim.

**Matched-evidence bridge**:
The pure-function seam from stored matched evidence to a Gate-2 verdict on well-formed evidence, or a typed refusal with an exclusion ledger on malformed evidence. No writes, no defaults; same records in, same result out.

**Evidence grade**:
The strength label attached to a published finding — `MEASURED` (pre-registered/audited conditions), `MECHANISM` (argument at mechanism level plus independent expert concurrence), `DIRECTIONAL` (trust the direction, not the magnitude), `EXPLORATORY` (from a construct-invalid instrument; illustrates, never decides). Distinct from **evidence admissibility** (whether an observation may feed aggregation) and from an **Oracle** grading an arm.

**Admission state vs measurement state**:
Two separate facts about a skill: whether the collection admits it (the library's decision) and what the instrument has measured about it (this repo's decision). A kept skill is not thereby empirically proven; the two states never collapse into one label.

## Relationships

- A **Skill** decomposes into **Clauses**; each test runs the three **Conditions** and yields directional **Measurements** graded by an **Oracle**.
- Only observations passing **evidence admissibility** feed aggregation; aggregation yields a **Verdict** or a **typed refusal**, recorded as a **Receipt** under **SERS**.
- The **declared synthetic control** validates the apparatus that produces those verdicts; the **matched-evidence bridge** is the seam that turns stored evidence into them.
