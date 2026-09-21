# The gate chain: one instrument behind #611, #612, #613 and #614

**Status:** design, 2026-09-21 (S471). Nothing here is registered and nothing here authorises
spend. It sets the shape the four tickets build toward and the order they build in. The tickets
stay the record of each part; this file is the record of how the parts fit.

**Read this if** you are about to build any of the four tickets, or about to file a fifth that
touches activation, classification, cost or interaction. The first question for a new ticket is
which link of the chain it changes.

## The claim in one paragraph

The four tickets are four views of one redesign. Today the instrument answers one question, "did
the pass rate move between the Full and Null arms", and reports every other situation as one of
ten typed refusals. That question is only meaningful when four things hold, and the instrument
checks one of them. The redesign makes each precondition an explicit **gate**, runs the gates in
order, and types every verdict and every refusal by the gate that produced it. Everything the
tickets ask for is either a gate, the read a gate protects, or the report that lays the gates
out.

## What already exists, and is reused without change

Read before building. Each row was checked at source on 2026-09-21.

| Piece | Where | What it already does |
|---|---|---|
| Exposure gate | `ratification.py` `hazard_floor` (line 203, validated 329-372); `cli/paired_gate2.py` refuses `HAZARD_NOT_RECORDED` (exit 1), `HAZARD_UNDECIDED` (exit 1), `HAZARD_NOT_MET` (exit 2) | Gate G1 for one task family, in gate form. The floor lives on the RAT record. |
| Hazard entry read | `subject/paired_launch.py:422-467` `hazard_entry_counts`, returns `HazardEntry(pattern, epochs, entered, undecided)` | The first process predicate over a trace. Every proximal assertion in #612 generalises this function. |
| Verdict vocabulary | `aggregation/verdict.py:125-134`: `KEEP`, `CUT`, `CANT_TELL_YET`; `CutSubReason` `subsumed`, `no_lift`, `harmful`; `VerdictResult.wrong_instrument` | The output alphabet. It does not change. |
| Typed refusals | `docs/sers/sers.schema.json:42-58`, ten `unmeasured_sub_reason` values | The refusal alphabet. The chain adds gate-named reasons to it. |
| Class field | SERS `value_class`: `transformative-lift`, `trap-discipline`, `calibration`; `aggregation/value_class_registry.py` | A classification that already conditions a verdict, and is untested (`docs/findings/class-hypothesis-preregistration.md`). |
| Standing cost | SERS `cost.standing_tokens`, `fired_tokens`, `aux_tokens`, each a measured integer or a typed refusal; `skill audit` measures them offline | The cost row of #613, already in the receipt. |
| Declared arms | `ablation/arms.py` (`#554`, merged as PR #615, `9d956e8`): an arm is a named whole prompt assembly; `subject_identity.arms` carries the set | The cells of any factorial in #614. |
| Exposed against invoked | RAT-0001 Amendment 2: 32 of 32 exposed, 24 of 32 invoked | The trigger-reliability row of #613, already measured once. |
| Pre-registration house format | `docs/findings/v0.2-preregistration.md`, `class-hypothesis-preregistration.md` | Registered text changes only by dated amendment. |
| Ceiling finding | OBS-0007; RAT-0001 Amendment 2, both arms 32 of 32 | The reason G2 exists. |

So the redesign builds two new things and generalises two existing ones. New: process predicates
beyond hazard entry, and the listing-layer screen. Generalised: the exposure gate becomes a
per-task activation contract, and the ten refusals gain the gate that refused.

## The chain

```
G0 VISIBILITY    Is the skill's description in the listing at all?
                 No model run. Listing arithmetic against the budget.
                 Refusal: UNMEASURED(not_visible)

G1 ACTIVATION    (a) Does the untreated agent enter the hazard on this task?
                     Null entry rate >= the task's floor. This is #419.
                 (b) When the hazard is met, does the skill fire?
                     exposed vs invoked, missed triggers counted.
                 Refusals: HAZARD_NOT_MET, HAZARD_NOT_RECORDED (exist)

G2 SENSITIVITY   Can the Null arm fail the task, and does the bad state
                 follow the target action?  P(bad state | action) >= threshold.
                 Refusal: UNMEASURED(ceiling), UNMEASURED(no_consequence)

G3 EFFECT        The reads, each reported alone, never pooled:
                   process delta   proximal assertions over the trace
                   outcome delta   the existing paired read
                   artifact delta  the artifact, then the same downstream agent on both
                 Which read is PRIMARY is decided by the skill's claim type (below).

G4 INTERACTION   Does pairing with another skill change G3?
                 Listing layer first (a G0 question at collection scale),
                 then a sparse pairwise screen with a token-matched inert control.

PROFILE          One row per gate and per read, each typed
                 measured / unmeasured(reason) / not applicable,
                 plus standing cost and trigger reliability.
                 Recommendation: standing | on-demand | cut | cannot recommend.
```

A gate that refuses stops the chain, and the receipt names the gate. A verdict that reaches the
end carries every gate it passed. That is the whole design; the tickets are its parts.

**The router.** Where a skill's claim acts (#612) decides which G3 read is primary and which
refusal applies when that read is out of reach:

| Claim type | Primary read | Out of reach means |
|---|---|---|
| I, the outcome | outcome delta | the existing verdict path |
| II, the decision process | process delta, with the action and resulting state beside it | `UNMEASURED(no_process_predicate)` until one is written |
| III, an artifact for a later stage | artifact delta, then carry-through | `UNMEASURED(no_artifact_route)` |
| IV, behaviour over many tasks | none in this instrument | `UNMEASURED(longitudinal)`, a typed refusal that is correct, not a deficiency |

The claim type is declared per card, pinned in a registry the way `value_class` is, and frozen
before any run. Until its own pre-registered test passes, it is **reporting vocabulary only**: it
chooses what gets reported first and how a refusal is worded, and it conditions no verdict. That
is the lesson of `class-hypothesis-preregistration.md`, where a taxonomy shipped into `verdict.py`
before anyone tested it and one of its three classes has no members.

**One taxonomy, not two.** `value_class` and claim type overlap: `trap-discipline` is claim type
I with an invariant outcome under a hazard; `calibration` is claim type II; `transformative-lift`
is claim type I on pass rate. The recommended end state is that claim type subsumes `value_class`,
with that mapping recorded, and `verdict.py` branches on one field or on none. The decision
between "one field" and "none" is the zero-cost observation `class-hypothesis-preregistration.md`
already registered: ablate the `value_class` branch across every verdict on disk and count the
changes. Run that first. It is the cheapest thing in this document.

## Corrections carried in from the adjudication, so nobody re-derives them

- A Claude Code skill's body already loads on demand. Only the description stands, and `skill
  audit` measured it at 60 raw / 68 calibrated tokens for `git-pull-rebase-trap`. So for a skill,
  `V_on_demand` is the default architecture and the profile's live cost terms are the description
  and the trigger's reliability. The large standing items are the always-loaded files, which are
  out of this instrument's scope.
- A full listing drops descriptions and keeps names, so G0 is visibility, and adding skill B can
  silence skill A with no model run involved. This is the cheapest non-additivity there is, and it
  is screened before any body-layer pair. **Its documented mechanism is cited from memory and is
  being verified** (the research repository that governs this work,
  `docs/research/citation-verification-S471.md`, row 15).
  Build the G0 screen only against the verified text.
- A factorial on a ceilinged task measures nothing, so G4 waits on G2, which waits on G1, which
  is #419. The order is forced, not chosen.
- Loss needs a unit the operator sets. Until then the profile reports probabilities, counts and
  tokens, and its recommendation row says `cannot recommend` whenever a required row is
  unmeasured. No dollar figure appears in a profile.

## Build order

Ordered by what each step unblocks and what it costs. A step's cost is stated so that a session
can tell a build from a spend decision.

| # | Step | Cost | Ticket | Unblocks |
|---|---|---|---|---|
| 0a | Run the registered `value_class` ablation count over every verdict on disk. Publish the number either way. | $0, one static run | new, filed from this doc | whether one taxonomy or none conditions verdicts |
| 0b | Declare a claim type for every published card, in a pinned registry, as reporting vocabulary. Include the `value_class` mapping. | $0 | #612 item 1 | the profile's primary-read row; Type IV cards get their typed refusal immediately |
| 0c | Write the activation contract format and retrofit it to gitpull v3a from the #419 finding: target action, hazard preconditions, observable, consequence, mode (natural / decision-point / forced), floor, minimum P(bad state \| action), maximum leakage. The paired launch refuses a task without one. | $0 | #611 item 1 | #419 becomes the first contract's G1 measurement |
| 0d | The G0 listing-layer screen over the installed collection, once row 15 of the citation file verifies the mechanism. | $0 | #614 item 1 | the interaction ticket's cheap half; a drop is a finding on its own |
| 1 | The #419 Null qualification screen, k = 8, on the operator's typed go. | $0.60 expected, $5.00 cap, authorised | #419 | G1 for the only task family with a card behind it; the floor RAT-0001 Amendment 5 is waiting for |
| 2 | On a qualifying screen: consequence validation and the hazard-inactive twin on v3a, then a new row-pick on the rebuilt 539,011-token basis. | twin screen about the screen's cost; the paired run needs its own RAT | #611 items 2-3, then a RAT-0002 | the first real verdict on a published card, with a process row beside it |
| 3 | `proximal_assertions` on a task, generalising `hazard_entry_counts`, and the artifact route. | $0 to build; each use rides an existing run | #612 items 2-3, after #555 | claim types II and III get a primary read |
| 4 | The profile as a report over SERS: add `trigger_reliability`, `process_effect`, `recommendation`; render it for the one real verdict first. | $0 | #613 | the collection's cards carry a status a stranger can read |
| 5 | The body-layer pairwise screen. | about $127 at 211 cells x 8 replicates on the #420 basis; a spend decision with the amount in it | #614 items 2-5 | the compatibility graph |

Steps 0a to 0d run now and in parallel. Step 1 waits for one typed word. Steps 2 to 5 wait on
the screen's result, and step 5 also waits on a yes to its amount.

## The tension #611 names, settled by the cost basis

The outside answer wants pilots of 50 to 100 runs at a 70 percent baseline exposure. The
registered screen is k = 8 with 4 or more qualifying. These are two stages, not a disagreement.
The k = 8 screen is a **futility stop**: at $0.60 expected it decides whether the sized run's
32 Null epochs (about $2.40 realised, $17.70 no-discount) are worth buying. The sized run is the
pilot. A 100-run pilot on this family costs about $7.40 realised and $55 no-discount, and buys a
tighter floor, not a different decision. The floor itself stays where RAT-0001's frontier puts it,
at the H1 point's Null rate of 0.4, unless the screen forces the frontier re-run its read-out
already provides for.

## Completion criterion for this design

The design is built when a receipt for one published card carries a gate for each of G0 through
G3, each typed measured or refused with its gate named, a claim type, a standing cost and a
recommendation row, and every number on it was produced by a run or a static measurement named
on the receipt. G4 is complete when one pair has a four-cell comparison and an inert control on
record. Until the first receipt exists, no card's public text claims more than "in the chain at
gate Gn".

## Revisit if

- The #419 screen returns 0 of 8. Then no task in the collection's only priced family activates,
  and step 0c's contract format gets its second task from #611 item 6 (scenario search) before
  anything else in steps 2 to 5 runs.
- The `value_class` ablation count is zero. Then no field conditions a verdict, claim type stays
  reporting vocabulary permanently, and the "one taxonomy" recommendation reduces to renaming.
- Row 15 of the citation file fails to verify the listing budget. Then G0 is a documented
  hypothesis, not a mechanism, and step 0d is a measurement of whether descriptions drop at all.
- The operator names a loss unit. Then the profile's recommendation row can carry an expected
  loss, and #613's out-of-scope line lifts.
