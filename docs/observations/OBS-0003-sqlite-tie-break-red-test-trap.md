---
obs: OBS-0003
task_family: sqlite-tie-break-red-test-trap
subject_skill: sqlite-tie-break-red-test-trap
arm: null-only-stage0
counts:
  epochs: 3
  passes: 3
model: anthropic/claude-sonnet-5
date: "2026-07-10"
scope_pins:
  agent: claude-code-2.1.197
  harness_pin_fingerprint: "2f76c933"
  sandbox: docker-image-digest-pinned
evidence: store-ref
evidence_ref: "screen_backfill.BATCH1_MANIFEST — 2026-07-10T11-21-00 .eval log (admissible); the 11-10-33 twin log is ingested INADMISSIBLE (apparatus_void: grading harness crashed, not the subject)"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "Screened out of collection admission 2026-07-10 (batch-1 ceiling; RETIRED.md screened-out table); retained in the author's private library on documented non-screen grounds (RETIRED.md footnote); standing"
---

# OBS-0003 — sqlite-tie-break-red-test-trap (Stage-0 Null screen, 2026-07-10)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Batch-1 skill 1/4. Registered task (sourced from the skill's documented
origin failure): a fixture repo whose `ORDER BY … DESC LIMIT ?` lacks its
documented id tie-break; the agent must author a regression test that is RED
at unfixed HEAD (naive insertion order yields a passing placebo). Oracle
validated 13/13 pre-spend. Three Null-arm epochs — stock `claude-sonnet-5`,
no skill — all produced genuinely verified regression tests: **ceiling**
(p0 = 1). Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(Amendment 1, batch-1 results).

## Evidence lineage

This record is `store-ref`: its raw `.eval` log is cited, sha-pinned, and
admissibility-ruled in the committed backfill manifest
(`skill_harness.subject.screen_backfill.BATCH1_MANIFEST`), which
deterministically materializes the screen store (`skill-harness screen
backfill --execute`). The manifest also carries this task's twin log
(11-10-33, identical task input and harness pin) ingested **inadmissible** as
an apparatus void — append-only keeps the evidence while p0 excludes it; a
naive ingest-both would have derived p0 = 3/6 and manufactured a spurious
below-ceiling signal.

## What this record does not assert

- No skill verdict; disposition lives only in `disposition_of_record`.
- No compliance measurement (`pi_c: not-instrumented`), no registered estimand
  (`estimand: n/a`).
- No classification — **DEFERRED** to the first Gate-1 row-pick ratification
  ([#47](https://github.com/MrBinnacle/skill-harness/issues/47)), to be
  appended here as a dated amendment with the attained posterior.

## Disposition of record

Screened out of collection admission 2026-07-10 (ceiling; recorded in the
collection's
[RETIRED.md](https://github.com/MrBinnacle/skills/blob/main/RETIRED.md)
screened-out table). Separately, the skill is retained in the author's
private library on documented non-screen grounds (two saves in a different
setting than the screen measures — RETIRED.md footnote). Both dated decisions
**stand** per #41's dispositions-stand rule (E5); any change would be a new
dated decision.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
