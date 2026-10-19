---
obs: OBS-0001
task_family: fts5-notes-search-v1
subject_skill: sqlite-expert
arm: null-only-stage0
counts:
  epochs: 3
  passes: 3
model: anthropic/claude-sonnet-5
date: "2026-07-09"
scope_pins:
  agent: claude-code-2.1.197
  harness_pin_fingerprint: "2f76c933"
  sandbox: docker-image-digest-pinned
evidence: prose-backed
evidence_ref: "v0.2 pre-registration, noise micro-run results (Stage 0, task v1); raw .eval log retained locally (unpublished), consistent with the registered counts"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "CUT — subject skill sqlite-expert was archived from the operator's live library 2026-07-10 on this registration's null result (pre-registration Amendment 1, reproducibility note); standing"
---

# OBS-0001 — fts5-notes-search-v1 (Stage-0 Null screen, 2026-07-09)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Task v1 of the noise micro-run's FTS5 notes-search domain (trigger-sync +
phrase-escaping + ranking; SQLite FTS5, stdlib-only, deterministic pytest
oracle). Three Null-arm epochs — stock `claude-sonnet-5` with no skill
installed — all passed. Per the registered protocol this was a **ceiling**: the
screen FAILED the task-qualification gate and the task was rejected for
hardening. Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(noise micro-run results, Stage 0 task v1).

## What this record does not assert

- No skill verdict. This is a task-family observation with counts and scope
  pins; the subject skill's disposition lives only in `disposition_of_record`.
- No compliance measurement (`pi_c: not-instrumented`) and no registered
  estimand (`estimand: n/a`) — the historical instrument predates both.
- No classification. A 3-trial Null screen can only reject a task or supply
  subsumption evidence; classification under the ratified thresholds is
  **DEFERRED** to the first Gate-1 row-pick ratification
  ([#47](https://github.com/MrBinnacle/skill-harness/issues/47)), which will
  append it here as a dated amendment with the attained posterior.

## Disposition of record

The subject skill `sqlite-expert` was archived (cut) from the live library on
2026-07-10 on this registration's own null result. That dated decision
**stands** per #41's dispositions-stand rule (E5): re-scoping annotates the
evidence and never reverses a decision. Any change of disposition would be a
new dated decision.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
