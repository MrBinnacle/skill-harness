---
obs: OBS-0004
task_family: bayesian-eval-discipline
subject_skill: bayesian-eval-discipline
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
evidence_ref: "screen_backfill.BATCH1_MANIFEST — 2026-07-10T12-12-20 .eval log (admissible)"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "Screened out of collection admission 2026-07-10 (batch-1 ceiling; RETIRED.md screened-out table); standing"
---

# OBS-0004 — bayesian-eval-discipline (Stage-0 Null screen, 2026-07-10)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Batch-1 skill 2/4. Registered task (sourced from this harness's own
aggregation workload): implement PASS/FAIL aggregation — Beta(1,1) posterior
tails at threshold 0.6 / confidence 0.95 over 25 engineered clauses with ties
— with the defensibility requirements stated as spec (reachability bound
reported as UNMEASURED(underpowered) with precedence over FAILED; family-wide
FDR control). Oracle validated 11/11 pre-spend, verdicts engineered invariant
across honest policy choices. Three Null-arm epochs — stock
`claude-sonnet-5`, no skill — all ORACLE-PASS: **ceiling** (p0 = 1).
Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(Amendment 1, batch-1 results), including the registered instrument note that
screens of discipline-shaped skills must check the *reporting* discipline,
not just decision outcomes.

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

Screened out of collection admission 2026-07-10 (ceiling). The dated decision
**stands**; any change would be a new dated decision.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
