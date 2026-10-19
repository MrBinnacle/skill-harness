# The reader-facing record is cost, evidence grade and a scoped verdict

Status: accepted, 2026-09-22. Operator ruling on the board gate `destination`, carried into this
repository by session S477.

## The drift this record closes

On 2026-08-04 the operator ratified #96: show each skill's exact token cost beside an honest
evidence grade, and no verdict; the reader decides. Since then the instrument became a verdict
producer (`KEEP` / `CUT(subsumed | no_lift | harmful)` / `CANT_TELL_YET`), and nothing recorded
how that squares with #96. A cross-family framing audit on 2026-09-22 (two non-Anthropic
reviewers; recorded in the operator's research notes as `framing-audit-S476.md` and the
`t1-framing-S476` review receipt) found the two can coexist, and that the defect was the
unrecorded drift, not the verdict. This is the written reconciliation the audit asked for.

## The ruling

> #96 remains the reader-facing principle: every skill exposes its exact token cost and evidence
> grade, and the reader makes the deployment decision. Where a preregistered causal test has been
> completed, its scoped verdict is published as an additional evidence row, not as a replacement
> for cost, evidence grade, or reader judgment.

Two options were declined. "Verdicts are the product; #96 is superseded" claims more than the
record supports, since no supersession was ever written. "Verdicts stay internal" withholds the
most decision-relevant evidence from the artifact whose purpose is to help the reader decide.

## What a reader sees, per published skill

| Field | Public | What it answers |
|---|---|---|
| Exact token cost | yes | What the skill consumes from the model-visible context, every session |
| Evidence grade | yes | How strong and how complete the evidence for the skill's claimed behaviour is |
| Evidence status | yes | What has been established, and under what scope |
| Verdict | yes, when tested | What the preregistered causal test returned, scoped to its model, task family and world |
| Untested status | yes | States plainly that no causal verdict exists |
| Scope | yes | Model and version, task family, world, the Full / Null / Placebo result, the decision rule |
| Receipt link | yes | Lets the reader inspect the basis |

Cost, evidence grade and verdict are three axes. Cost answers what the skill consumes. Evidence
grade answers how strong the evidence is overall. The verdict answers what one preregistered
experiment established. A page that shows a verdict alone collapses the three into one and
invites the reader to infer worth from a scoped result.

## What a verdict means, and does not

`KEEP` means: under the declared experimental scope, the preregistered KEEP criterion was
satisfied. It does not mean "keep this skill". `CUT(subsumed)` means: under the tested model and
task scope, the target behaviour was produced without the card. It does not mean the skill is
useless. Skill value is model-relative; the collection already holds a card whose hazard one
model entered 8 times in 8 and its successor 0 times in 32 (the pull-rebase card's evidence
record in the skills repository).

Scope is therefore a first-class field, and the rendered verdict line always carries it. The
scope-line wording and the currentness mark (`VALIDATED` / `CARRIED_FORWARD` / `STALE`) are
#643's, built by #654 and #655.

## What this changes in the instrument

- The public render (`src/skill_harness/sitegen/`) prints the seven fields above for every card,
  with `Untested` and `Scope` as rows of their own rather than absence.
- An evidence grade is not yet a field in SERS or the render. It is opened as its own ticket, with
  its rule stated before any grade is printed; a grade that a reader cannot trace to a rule is a
  manufactured number.
- The free comparative screen across every published card (#652) proceeds first. It serves this
  record under any framing: it supplies comparative costs and grades, it identifies which cards
  deserve confirmatory testing, and it is the collection-level evidence the hybrid record needs.

*Revisit if:* the operator names a different reader-facing principle, or a reader test shows the
scoped verdict row is read as a universal claim despite the scope line.
