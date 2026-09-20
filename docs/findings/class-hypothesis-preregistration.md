# Class-hypothesis pre-registration — what a `value_class` null may mean (REGISTERED)

> **Reader's note.** This document locks what will be tested, and what each possible answer
> means, *before* the data exists. It was written to discharge one blocker: `skill-harness#104`
> was declined five times because the class hypothesis had never been registered, and Gate 2's
> guardrail forbids running first and deciding afterwards what the result meant. Everything below
> the status line is the registered record and changes only by dated amendment blocks appended at
> the end, never by an edit in place.

**Status:** REGISTERED 2026-09-20, session S465, after a cross-family challenge review that
refuted the first draft's primary contrast. That review and the adjudication of every objection
are recorded in the research repository that governs this work, under
`docs/audit/t1-class-hypothesis-S465/`. Registered **with a pre-stated
NO-GO on the corpus-wide extraction as an instrument for this hypothesis**, and with **no valid
test of the hypothesis itself yet registered**, because the first attempt measured the wrong
quantity and is withdrawn below rather than quietly repaired.

## The hypothesis, stated so it can fail

**H1 (the class hypothesis).** A skill's `value_class` conditions how a null result about that
skill should be interpreted. A null on a `trap-discipline` skill means something different from
a null on a `calibration` skill, and the difference is large enough to change a verdict.

`aggregation/verdict.py` already branches on exactly this. `CUT` is withheld unless the class is
`TRANSFORMATIVE_LIFT`, `TRAP_DISCIPLINE` takes its own path when `outcome_type` is `invariant`,
and `tests/test_value_class_call_sites_static.py` refuses any call site that omits the argument.
So H1 is not a proposal. Shipped code already depends on it, and it has never been tested.

**H0.** `value_class` carries no information a verdict may lean on, and the branches above are
policy rather than measurement.

## The emptiest cell, which is the headline

`value_class` has three permitted values. **`TRANSFORMATIVE_LIFT` has zero members anywhere in
the registry** — not unreachable, not retired, absent. The branch that withholds `CUT` is the
most consequential one in `verdict.py`, and nothing in this corpus can exercise it in principle.

That is a stronger emptiness result than anything about extraction cost, and it does not depend
on any contrast being runnable. It is stated first because the first draft of this document
buried it under a census.

## What was withdrawn, and why it matters more than what replaced it

The first draft registered a primary contrast of **between-class versus within-class spread in
per-skill mechanical measurability**, the fraction of a skill's extracted clauses whose axis
appears in the Tier-1 registry. Two independent non-Anthropic reviewers, prompted to adjudicate
in both directions, converged on the same refutation, and it holds.

Measurability is a property of the extraction pipeline's registry coverage. H1 is a claim about
what a null *means*. Even a clean result on that contrast would establish that skills of
different classes have clauses of differing registry coverage, and would license nothing about
whether `CUT` should be withheld or whether an invariant outcome deserves its own path. The
proxy and the hypothesis are different constructs and the draft never bridged them.

The draft also cited construct validity as the field's nearest cautionary analogue, then
committed that exact error in its own registered contrast. **The contrast is withdrawn. No
substitute is registered in its place, because none that was measured today tests H1.**

## Gate fields

| Field | Value |
|---|---|
| Pending decision | Whether `aggregation/verdict.py` may keep branching on `value_class`, and whether `#104`'s corpus-wide extraction should be paid for to settle it. |
| Primary contrast | **WITHDRAWN.** The measurability-spread contrast tested registry coverage, not null interpretation. Nothing replaces it here. The next section registers the cheap observation that decides whether H1 is worth testing at all. |
| Task source | The extractor's own corpus enumeration, resolved with `--dry-scope` before any call. Class labels come from `aggregation/value_class_registry.py`, pinned against a fixed triple list (#422). |
| Oracle set | Deterministic and local for the census below. No judge, no LLM in any scoring path. |
| Subject layer | Not applicable. Nothing registered here runs an agent. |
| Harness pin | Extractor model pin `claude-opus-5`, recorded per row in the JSONL header. Clause sets from different pins are not poolable. |
| Differentiation vs field | None claimed. This is a feasibility stop before spend, and the fitting prior art is the registered-reports literature on pre-stated futility, plus variance-components reasoning where a label informs only when between-group spread exceeds within-group. A prior sweep's claim that no literature lets intervention type condition a null's interpretation is **too strong as written** and is not relied on: estimand and endpoint choice do change what a null means, which is why guidance like ICH E9(R1) exists. What the project lacks is warrant for *this* typology, not warrant for the general idea. |
| MDE + sizing | Not computed, and not a virtue. One arm has no reachable live members, so no sample size is defined. |
| Stopping rule | Not applicable to a feasibility stop. |
| Leak audit | Labels are frozen before extraction, and the registry's pinning test holds them. That control stands and should be kept by any later design. |
| Budget | **$0 registered.** This document authorises no spend. |

## The registered next observation, and it costs nothing

Before any contrast is designed, run the observation that decides whether H1 is operationally
live in the shipped instrument.

**Ablate the `value_class` branch in `aggregation/verdict.py` across every verdict already on
disk, and count how many change.** One static run, no network, no model call.

- **If zero verdicts change,** H1 is moot in the deployed instrument. The branches are policy
  with no observed effect, the question is a taxonomy question rather than a measurement one, and
  no corpus spend is justified for it.
- **If verdicts change,** the question is live, the count is the measure of how much rides on it,
  and classifying the currently unclassified live skills becomes the justified next step.

Registered before the result: **both outcomes are published.** A zero is a finding about the
instrument, not an absence of one.

A second observation, equally cheap, bounds the taxonomy directly. **Count how many live skills
could be `trap-discipline` under the written class definition.** If the answer is zero, the class
has no live referents and the branch is dead code regardless of any variance result.

## The census that produced the NO-GO

Every figure was measured on 2026-09-20 by running the command in its own row. None is carried
from a checkpoint, a ticket, or a prior session's summary.

| What was measured | Command | Result |
|---|---|---|
| Corpus size | `extract-corpus-clauses.py --dry-scope` | **82 entries** (73 local, 9 fable), not the 71 carried across `#104`, the S194 facts and the checkpoint. |
| Registry size | parse of `value_class_registry.py` | **12 entries: 9 `trap-discipline`, 3 `calibration`, 0 `transformative-lift`**, not the 11 those surfaces state. |
| Already extracted | `docs/research/corpus-clauses-S184.jsonl` | 6 skills, the first six alphabetically. |
| Reachable classified skills | `--dry-scope --slugs-file` over all 12 registry slugs | **4 of 12 resolve.** Three `calibration`, one `trap-discipline`. |
| Where the unreachable eight live | direct `ls` of each backup root, `find -L` over the plugin trees, and `git ls-files` in the `skills` clone | **Seven exist inside a dated backup directory** and nowhere live. One of those seven, `subagent-research-reliability`, **also** sits in four plugin `_quarantine/` copies (three under the cache, one under `plugins/marketplaces/`), so the backup and quarantine sets overlap rather than partition. **The eighth, `closure-mode-at-boundaries`, is not absent. It was renamed.** |

The one reachable `trap-discipline` skill is `sqlite-tie-break-red-test-trap`, which the registry
marks retired 2026-07-10.

**The registry holds at least one stale key, and that is a better finding than the absence it was
mistaken for.** `closure-mode-at-boundaries` resolves nowhere because `skills#286` (`541522a`,
*"Name each published card after the word a reader reaches for"*) renamed the card to
`closure-mode`. That card is live and published: `skills/engineering/closure-mode/SKILL.md` is
tracked in the collection with frontmatter `name: closure-mode`, its H1 still reads "Closure Mode
at Boundaries", and `find -L` returns it installed in three plugin trees.
`value_class_registry.py:52` still keys the pre-rename string.

So the slug does not resolve and the skill is alive. Reading `tests/test_value_class_registry.py`
in full, its seven tests pin the `(skill_name, value_class, retired_on)` triples, assert the
`transformative-lift` class is empty, assert an unregistered name returns `None`, and check the
ceiling behaviour for named records. None of them resolves a key against a skill on disk, which is
consistent with what the file was built to do and is why a rename can pass it. Filed as `#601`; a
registry that can silently stop pointing at its subject is a defect in the instrument rather than
a fact about this hypothesis.

`4 of 12 resolve` is unaffected, because the slug genuinely does not resolve in the extractor's
corpus under either name.

## What the census licenses, stated narrowly

**It licenses refusing `#104`'s corpus-wide extraction as an instrument for H1.** The skills that
run would not include the missing eight, because seven are backup copies the enumeration does not
walk and the eighth is keyed under a name that no longer exists. Paying for 76 more does not fill
the arm.

**It does not license treating H1 as tested.** An empty cell is an empty cell. A blocked design
is not a result about the hypothesis, and this refusal leaves the shipped branches in exactly the
state they were in before: depended upon, unexamined.

**It supports preferring classification over extraction, on a weaker claim than the first draft
made.** Every `calibration` entry is a live card. Seven of the nine `trap-discipline` entries are
backup copies and nowhere live, one is live but retired, and one is live and published under a
name the registry does not use. So class as currently assigned is **correlated** with liveness
rather than collinear with it, and the correction matters: the confound is real enough to prefer
classification, and not so total that a later reader should treat `trap-discipline` as a synonym
for dead. Any comparison run on this registry as it stands would still separate live from
not-live at least as well as it separated classes. Classifying live skills is free and removes the
confound at its source; enumerating the backup roots through `--extra-root` would make a contrast
runnable while baking the confound in, which is why it is the worse of the two routes.

## Quarantined, and not part of any outcome rule

The first draft cited a 6.4x within-class measurability spread at Fisher two-sided p = 0.041 from
a prior fact sheet, and called it the outcome currently favoured by the only data that exists. It
is withdrawn from the registered rules. The sample is six skills chosen as the first six
alphabetically, only two carry a class, and both are the same class. A p-value on that table
cannot bear directional weight, and quoting it as a pre-registered expectation would have locked
in a peek. It is recorded here as anecdote so that a later reader can see it was considered and
set aside, and it must not be cited as support for any result.

## What is refused, and what stays open

**Refused: the corpus-wide extraction as an instrument for H1.** It cannot reach the missing arm.

**Released: the extraction as a means to other ends.** `#104`'s own Revisit-if anticipated this:
*"a means-to-an-end run is a different authorisation than a census, and it may not need the same
pre-registration."* Anything needing more clauses for a reason unrelated to `value_class` is
governed by its own ticket.

**Open, and belonging to `#104` rather than to this document:** whether `verdict.py` should stop
branching on `value_class` while H1 is untested. That is a behaviour change with its own blast
radius. The ablation count registered above is the input that decision needs.

**Time-limited, not permanent.** If classification coverage grows and both arms gain live
members, this refusal should be re-derived rather than assumed. A refusal that survives its own
stated remedy was momentum rather than structure.

## Provenance

Written at session S465 from a direct read of `skill-harness#104` and its resolution comment, the
S194 fact sheet's facts 13 through 17, `aggregation/value_class_registry.py`,
`tests/test_value_class_call_sites_static.py`, and the zero-spend measurements in the census
table. House format follows `docs/findings/v0.2-preregistration.md`, including its amendment
rule: append a dated block, never edit registered text.

The first draft was reviewed before registration by two non-Anthropic models prompted to
adjudicate in both directions. Both returned PARTLY SOUND and converged on the proxy mismatch,
the unsupportable p-value, and the buried `TRANSFORMATIVE_LIFT` emptiness. Each is corrected
above. The review is the reason this document registers no test rather than a wrong one.
