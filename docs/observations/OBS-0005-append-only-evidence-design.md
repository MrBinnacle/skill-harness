---
obs: OBS-0005
task_family: append-only-evidence-design
subject_skill: append-only-evidence-design
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
evidence_ref: "screen_backfill.BATCH1_MANIFEST — 2026-07-10T13-00-15 .eval log (admissible)"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "Screened out of collection admission 2026-07-10 (batch-1 ceiling; RETIRED.md screened-out table); CUT (subsumed) reaffirmed by the 2026-07-20 live re-screen (store-backed; a separate record outside this ledger); standing"
---

# OBS-0005 — append-only-evidence-design (Stage-0 Null screen, 2026-07-10)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Batch-1 skill 3/4. Registered task (sourced from this repo's evidence-store
domain): build an evidence-store module whose verdict rows are immutable
against the database file itself, then migrate it in place past SQLite's
trigger-dropping table recreation. Oracle validated 7/7 pre-spend under the
module-isolation pattern (subject code only in child processes; probes
module-free) after a fresh-context reviewer confirmed the in-process
weakness with a working exploit. Three Null-arm epochs — stock
`claude-sonnet-5`, no skill — all shipped BEFORE UPDATE/DELETE triggers and a
trigger-recreating migration: **ceiling** (p0 = 1). Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(Amendment 1, batch-1 results), including the registered apparatus rule that
import-the-module oracles are in-process-compromisable by construction.

## Evidence lineage

`store-ref`: the raw `.eval` log is cited and admissibility-ruled in the
committed backfill manifest
(`skill_harness.subject.screen_backfill.BATCH1_MANIFEST`), which
deterministically materializes the screen store (`skill-harness screen
backfill --execute`).

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
screened-out table). A later live re-screen (2026-07-20, natively
store-backed, outside this ledger) returned the same outcome and the
disposition CUT (subsumed) was recorded then. Both dated decisions **stand**
per #41's dispositions-stand rule (E5); any change would be a new dated
decision.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
