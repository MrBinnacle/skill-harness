---
obs: OBS-0002
task_family: fts5-notes-search-v2
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
evidence_ref: "v0.2 pre-registration, noise micro-run results (Stage 0, task v2); raw .eval log retained locally (unpublished), consistent with the registered counts. The associated Stage-1 Null arm is store-backed (run 956aef8f, 8 admissible verdicts)"
pi_c: not-instrumented
estimand: n/a
classification: DEFERRED
disposition_of_record: "CUT — subject skill sqlite-expert was archived from the operator's live library 2026-07-10 on this registration's null result (pre-registration Amendment 1, reproducibility note); standing"
---

# OBS-0002 — fts5-notes-search-v2 (Stage-0 Null screen, 2026-07-09)

Backward-looking observation record, created 2026-08-02 under the re-scoping
semantics ratified in [#41](https://github.com/MrBinnacle/skill-harness/issues/41).
It annotates the historical record; it changes nothing above it.

## The screen

Task v2 — v1 hardened with a full boolean query language (quoted phrases,
implicit-AND, OR-precedence, exclusions including phrase exclusion,
punctuation splits, unbalanced-quote recovery, title-weighted ranking; 34
asserts), leak-audited per the registered rule. Three Null-arm epochs — stock
`claude-sonnet-5`, no skill — all passed: **ceiling again**, verified at the
time from the raw `.eval` logs rather than the runner's summary. Registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(noise micro-run results, Stage 0 task v2).

## Associated Stage-1 Null epochs (part of the 26/26 aggregate)

After the double-ceiling decision (operator-approved, purpose re-registered
before launch as apparatus shakedown + NO-GO datum), Stage 1 ran k = 8 paired
epochs on this task. Its **Null arm passed 8/8**; those epochs are the
remaining Null observations in the registered 26/26 aggregate and are
store-backed: evidence-store run `956aef8f…`, 8 admissible verdicts, all
observation 0.5 (tie encoding), re-ingest refused. This record's `counts`
field covers the Stage-0 screen only; the ledger README's decomposition table
carries the aggregate arithmetic.

## What this record does not assert

- No skill verdict; disposition lives only in `disposition_of_record`.
- No compliance measurement (`pi_c: not-instrumented`), no registered estimand
  (`estimand: n/a`).
- No classification — **DEFERRED** to the first Gate-1 row-pick ratification
  ([#47](https://github.com/MrBinnacle/skill-harness/issues/47)), to be
  appended here as a dated amendment with the attained posterior.

## Disposition of record

`sqlite-expert` was archived (cut) from the live library 2026-07-10 on this
registration's own null result. That dated decision **stands**; any change
would be a new dated decision, never an edit.

## Amendment log

- 2026-08-02 — record created (re-scoping per #41 / #49 / #50).
