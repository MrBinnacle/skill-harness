---
obs: OBS-0006
task_family: llm-judge-calibration
subject_skill: llm-judge-calibration
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
evidence: prose-backed
evidence_ref: "v0.2 pre-registration, Amendment 1 (skill 4/4 blocks, incl. the same-day completion block); the canonical 3/3 is assembled across four partial .eval logs over the registered credit-exhaustion incident — store backfill DEFERRED pending per-trial cross-log assembly (screen_backfill docstring)"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "Screened out of collection admission 2026-07-10 (batch-1 ceiling; RETIRED.md screened-out table); standing"
---

# OBS-0006 — llm-judge-calibration (Stage-0 Null screen, 2026-07-10)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Batch-1 skill 4/4. Registered task (sourced from the Phase-B judge workload):
implement the judge admissibility gate — prompt-hash-inclusive judge_id,
position-swap double call, pairwise-not-scalar schema, calibration floors
with exact boundary probes. Oracle validated 12/12 pre-spend, hardened with a
sentinel gate after a fresh-context reviewer found the exit-code-only pass
hole. Three Null-arm epochs — stock `claude-sonnet-5`, no skill — all
ORACLE-PASS: **ceiling** (p0 = 1). The third epoch ran after a mid-screen
account-credit exhaustion (an apparatus incident, registered honestly at the
time — 2/2 scored epochs first, the owed epoch completed same day on the
identical registered apparatus). Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(Amendment 1, skill 4/4 blocks). This screen completed batch-1: all four
screens ceilinged, zero paired runs launched, zero BH-FDR primary tests
consumed.

## Evidence lineage

`prose-backed`: the canonical 3/3 is assembled across four partial `.eval`
logs spanning the credit-exhaustion incident (admissible epochs split across
logs, voided epochs between). Log-level backfill cannot represent that
assembly, so store backfill for this record is explicitly **deferred** —
tracked in the backfill module's scope note — and the registration prose is
the citable basis until a per-trial cross-log ingest exists. Honest split: no
mixed canon.

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
screened-out table). The dated decision **stands** per #41's
dispositions-stand rule (E5); any change would be a new dated decision.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
