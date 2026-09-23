# Cross-card audit screen - Stage 0 comparative baseline (#652)

> **Status:** STAGE-0 COMPLETE 2026-09-23. The declared population is
> `git ls-files "skills/*/*/SKILL.md"`: 0 published card(s).

**Claims:** This document records the published-card population and runs the
public `skill-harness skill audit` command on each member. The table reports
standing cost and the Tier-1 axes available to the instrument. Rank is a
reproducible cost order, not a confirmation-spend recommendation.

**Refuses to claim:** A claim class, because skill audit does not extract a
card's claims; hazard-qualified task-family plausibility or existence, because
the repository supplies no card-to-task-family evidence register; a keep/cut
verdict; or any card's readiness for Stage 1 spend.

## Ranked table

| Rank | Card | Path | Standing (raw) | Measurable claims | Available Tier-1 axes | Claim class | Hazard family plausible? | Hazard family exists? | Out of reach, because |
| ---: | --- | --- | ---: | --- | --- | --- | --- | --- | --- |

No published cards matched `git ls-files "skills/*/*/SKILL.md"`.
No card can be ranked for confirmation spend from this repository state.

## Method

1. Enumerated the declared population via `git ls-files "skills/*/*/SKILL.md"`.
   The screen refuses to substitute fixtures or screen copies when that set is empty.
2. Ran `python -m skill_harness skill audit <card>` on each member, then used
   its `audit_skill_artifact()` report to render the table (offline, zero cost).
3. Reported Tier-1 axis availability, but refused measurable claims and a claim
   class because the audit does not parse claims from a card.
4. Refused the hazard-family questions because no evidence register maps cards to
   task families.
5. Sorted readable standing costs ascending only for stable display order.
