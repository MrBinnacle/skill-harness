# Invariant rationale & expanded detail (load on demand)

Pointed to from `CLAUDE.md` "Load-bearing invariants". CLAUDE.md states each rule
tersely; this file holds the *why* and the failure-mode detail. The rule is the
contract — this is the justification you load when you need to reason about an edge
case or defend a review-block.

## What this project is (expanded)

Skill Harness is a deterministic evaluation framework for LLM skills (instruction
files, prompt modules, behavioral overlays) that measures clause-level contribution
via differential ablation rather than output-quality scoring. It never asks "is this
output good?" — it asks "does output A beat output B on the single axis claimed by
clause N?"

## Control-flow ownership
A code path that lets a stochastic model decide what gets **stored, scored, or
aggregated** is broken even if it "works" in a demo — the determinism guarantee is
the product. Models are content generators (subjects, injectors, judges); the Python
layer owns orchestration, sampling, scoring, storage, aggregation.

## Evidence model
- Recomputing admissibility at **read time** would let calibration drift
  retroactively rewrite history. That is why provenance (source, oracle, version,
  admissibility state) is snapshotted at write time and never recomputed.
- **A22 asymmetric durability:** `evidence.db` opens at `PRAGMA synchronous = FULL`
  because committed audit rows must survive power loss. `runtime.db` keeps
  `synchronous = NORMAL` because runtime state can be re-derived from evidence after
  a crash. Code that bypasses `open_db()` and reaches `sqlite3.connect()` directly
  silently degrades durability **and** loses connection-scoped `foreign_keys = ON`
  — review-block any such PR.

## Aggregation rules
Inadmissible and confounded rows are stored for audit but cannot affect results.
"No admissible evidence ⇒ no claim" is why a zero-measurement clause is `UNMEASURED`,
never `PASSED`. Skills are vectors, never a scalar — collapsing to one number
discards the Coverage/Confounded signal that makes the verdict honest.

## Clause discipline
A clause without a constructible falsifying case is **vacuous** — it is metadata, not
a contract, and is excluded from testing. A clause is not "tested" until ≥1 falsifying
case exists in the frozen regression suite.

## Confound handling
Ablating clause N may move axes belonging to other clauses. When that cross-axis
delta exceeds threshold the result is `FLAGGED_CONFOUNDED`, not pass/fail — a
contaminated delta must never be reported as clean evidence.

## Oracle tiering
- Tier 1 (mechanical, deterministic counting) preferred whenever a metric exists.
- Tier 2 (human-calibrated judge) is an **instrument, never the source of truth**;
  inadmissible without a calibrated `(judge_id, axis)` record.
- Tier 3 (real-world consequence) is the terminal oracle, highest authority.
- Calibration is axis-specific. No cross-axis inheritance.

## Explicitly unaudited
Rhythm metrics / sentence-length variance are a known trap, not an oversight: no
frozen cases may be minted from them until validated.

## Pass rule (expanded)
Changing either threshold (the `0.60` win-rate floor or the `0.95` posterior-mass
gate) is a `[values decision]` — surface to the user, never silently retune. Prior is
`Beta(1,1)`; posterior `Beta(1+w, 1+n−w)`; scoring Win=1, Tie=0.5, Loss=0.

## Pipeline safety (expanded)
The frozen regression suite and the evidence table are append-only **by design**. A
script that mutates either in place — even to "clean up" a stale row — violates the
core invariant and corrupts the audit trail.
