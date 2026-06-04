# Council Fires — Archive

This directory holds the raw outputs of every council fire. Each fire produces
N parallel seat outputs (one per dispatched reviewer). Synthesized digests
land in `docs/COUNCIL_FINDINGS.md`; the raw outputs land here.

Without this archive, the synthesis cannot be audited and a council cannot be
re-fired against the same brief.

## Layout

```
docs/council-fires/
  <YYYY-MM-DD>-<reason-slug>/
    README.md         — brief: what was asked, which template, which seats
    seat-<NAME>.md    — one file per dispatched seat, raw output
    synthesis.md      — short pointer to the COUNCIL_FINDINGS section that
                        consumes these findings (so future readers can navigate
                        from raw output → adopted decision)
```

## Naming

- Date is the fire date, not the dispatch session date if they differ.
- Reason slug is short kebab-case: `prd-pressure-test`, `pre-track-a`,
  `pre-tag-launch`, `migrations-pr-gate`, etc.
- Seat names match the dev-team-council roster: `TEST-ARCH`, `STAT`, `SCHEMA`,
  `EVAL-RESEARCH`, `COST`, `SECURITY`, `RELIABILITY`, `OPERATOR-DX`, `DOCS-DX`.

## What each seat file MUST contain

Per `parallel-review-disposition-schema` output contract:

- The brief embedded verbatim at the top
- Per-finding blocks: `ID / Title / Severity / PRD anchor / Claim / Evidence /
  Recommendation / Cross-seat`
- Cross-talk block (per `cross-talk-council-dispatch`): what each other seat
  is predicted to get RIGHT / WRONG / MISS
- A final status line: `STATUS: <BLOCKER|MAJOR|MINOR|OBSERVATION>-FOUND` or
  `STATUS: NO-FINDINGS`

## What synthesis.md MUST link

- The COUNCIL_FINDINGS section consuming these findings (anchor like
  `COUNCIL_FINDINGS.md § A18` or `§ B2`, depending on adoption status)
- The PRD amendments queued (if any)
- The PLAN edits queued (if any)

## First fire

The first fire (2026-06-03 PRD pressure-test, 5 seats, 31 findings) pre-dates
this archive convention. Its synthesis lives at `docs/COUNCIL_FINDINGS.md` § A
without a raw-output archive. Phase 1.5 will be the first fire to land here
in full.

## Discipline

- Archive is append-only. Do not edit prior seat outputs. Corrections happen
  through a follow-up fire, not in-place rewriting.
- One directory per fire, even if the same template fires twice in one day
  (use `-2` suffix).
- The orchestrator role owns dispatch and archive writes. Seats themselves
  return findings; the orchestrator persists them.
