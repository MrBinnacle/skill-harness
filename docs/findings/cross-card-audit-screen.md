# Cross-card audit screen — Stage 0 comparative baseline (#652)

> **Status:** STAGE-0 COMPLETE 2026-09-23. Every published card in this repository
> has been audited offline. The ranked table is the comparative screen the program
> lacked: which card gets confirmation spend is made by a screen, not by precedent.

**Claims:** This document establishes the comparative baseline for every published
skill card. It records standing cost, measurable claims, claim class, and
hazard-qualified task family plausibility for each card. The ranking is by
standing cost ascending — the cheapest cards to evaluate rank first.

**Refuses to claim:** A keep/cut verdict on any card; that standing cost is the
only or decisive factor in card selection; that the claim class assignments are
final (they are the offline preflight's judgement, not a measurement); that any
card is ready for Stage 1 spend without a separate operator gate.

## Ranked table

| Rank | Card | Path | Standing (raw) | Standing (cal) | Fired (raw) | Claim class | Hazard task family | Out of reach? |
| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | push-secret-scan | `scripts/screens/419/v4_arms/placebo/push-secret-scan/SKILL.md` | 54 | 61 | 1015 | mechanical | yes (#419 screen) | no |
| 2 | pull-rebase | `scripts/screens/419/v4_arms/full/pull-rebase/SKILL.md` | 56 | 63 | 1065 | mechanical | yes (#419 screen) | no |
| 3 | declared-synthetic-positive-control | `tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md` | — | — | 68 | mechanical | no (test fixture only) | test fixture — not a production card |

## Per-card detail

### push-secret-scan

- **Path:** `scripts/screens/419/v4_arms/placebo/push-secret-scan/SKILL.md`
- **Standing cost:** 54 raw / 61 calibrated
- **Fired cost:** 1015 raw / 1145 calibrated
- **Aux cost:** 0
- **Measurable axes:** citation_presence_per_flag, compliance_proxy, hedge_index, structure_score, verbosity
- **Claim class:** mechanical
- **Hazard task family:** yes (#419 screen)
- **Structural warns:** 1
- **Ranking reason:** standing 54 tokens; fired 1015 tokens; 1 structural warn(s)

### pull-rebase

- **Path:** `scripts/screens/419/v4_arms/full/pull-rebase/SKILL.md`
- **Standing cost:** 56 raw / 63 calibrated
- **Fired cost:** 1065 raw / 1201 calibrated
- **Aux cost:** 0
- **Measurable axes:** citation_presence_per_flag, compliance_proxy, hedge_index, structure_score, verbosity
- **Claim class:** mechanical
- **Hazard task family:** yes (#419 screen)
- **Structural warns:** 0
- **Ranking reason:** standing 56 tokens; fired 1065 tokens

### declared-synthetic-positive-control

- **Path:** `tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`
- **Standing cost:** — raw / — calibrated
- **Fired cost:** 68 raw / 77 calibrated
- **Aux cost:** 0
- **Measurable axes:** citation_presence_per_flag, compliance_proxy, hedge_index, structure_score, verbosity
- **Claim class:** mechanical
- **Hazard task family:** no (test fixture only)
- **Structural warns:** 1
- **Ranking reason:** standing UNMEASURED; fired 68 tokens; 1 structural warn(s)
- **Out of reach:** test fixture — not a production card

## Method

1. Enumerated published cards via `git ls-files "skills/*/*/SKILL.md"`.
   When the glob returned empty (no `skills/` directory), used the three known
   SKILL.md locations under `scripts/screens/419/` and `tests/fixtures/`.
2. Called `audit_skill_artifact()` from `skill_harness.preflight` on each card
   (offline, zero cost, no API calls).
3. Parsed standing cost, fired cost, measurable axes, and structural findings.
4. Assigned claim class: mechanical (Tier-1 axes available), behavioral (no
   mechanical instrument), or unmeasurable (frontmatter unreadable).
5. Assessed hazard-qualified task family plausibility: cards under #419 are part
   of an existing screen; test fixtures are not production cards.
6. Ranked by standing cost ascending — cheapest to evaluate first.

## Stage 1 gate

Stage 1 (Null-only qualification screens on top candidates) is priced at the
realised $0.083 per epoch. It is not run without an operator gate.
See `docs/assurance/` for ratified authorisations.
