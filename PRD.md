# Product Requirements Document

## Product Name

Skill Harness: Clause-Ablation Differential Testing for LLM Skills

Version: 1.0
Status: Draft
Author: TBD

---

# 1. Executive Summary

Skill Harness is a deterministic evaluation framework for testing LLM skills (instruction files, prompt modules, behavioral overlays, and similar artifacts) using falsifiable contracts rather than output inspection.

Traditional software testing assumes:

* deterministic execution
* explicit output oracles
* stable function boundaries

Skills possess none of these properties.

Skill Harness introduces four manufactured primitives that replace those assumptions:

1. Oracle → Directional Pairing
2. Isolation → Clause Ablation
3. Determinism → Variance Budgeting
4. Trust → Admissible Oracles

The system evaluates whether a skill clause produces a measurable directional effect when present versus absent.

The harness never asks:

> "Is this output good?"

Instead it asks:

> "Does output A outperform output B on the single axis claimed by clause N?"

The resulting system produces empirical evidence for or against individual skill contracts and supports regression testing across skill revisions.

---

# 2. Problem Statement

Skills are increasingly used as reusable behavioral modules.

Unlike software:

* Skills do not have deterministic outputs.
* Skills rarely have ground-truth answers.
* Skills often make behavioral claims that are difficult to verify.
* Existing evaluation systems frequently rely on LLM self-grading.

Current evaluation methods hide uncertainty behind subjective judgments and aggregate confidence without validating the source of that confidence.

The result is a system that can report improvement while remaining unable to prove that any specific instruction contributed to that improvement.

Skill Harness exists to measure clause-level contribution.

---

# 3. Design Principles

## 3.1 Directional Evaluation

All evaluation is comparative.

Forbidden:

* quality scoring
* holistic grading
* "is this good?"

Required:

* A beats B on axis X

---

## 3.2 Clause Isolation

Every skill is decomposed into atomic contracts.

A clause is tested through:

* Full skill
* Clause removed
* Null skill

Measurements are based on deltas between conditions.

---

## 3.3 Admissible Evidence Only

Evidence enters aggregation only if admissibility requirements are satisfied.

No component may self-certify its own reliability.

---

## 3.4 Falsifiability First

A clause is not considered tested until it has at least one falsifying case.

A clause without a possible failure mode is metadata, not a contract.

---

## 3.5 Provenance Preservation

Every measurement must retain:

* source
* oracle
* version
* admissibility state

Historical evidence is append-only.

---

# 4. Core Evaluation Model

## 4.1 Skill

A skill is a user-authored instruction artifact.

Examples:

* Markdown instruction files
* Prompt modules
* Behavioral overlays
* Claude skills

---

## 4.2 Clause

An atomic directional contract.

Example:

> Require citations for factual claims.

Becomes:

Axis: `citation_support`
Comparator: `increase`

---

## 4.3 Conditions

Each test executes three conditions.

### Full

Complete skill.

### Ablated

Skill with exactly one clause removed.

### Null

No skill.

---

## 4.4 Measurement

The measurement unit is not an output.

The measurement unit is:

`Full beats Ablated`

or

`Full beats Null`

on a specific axis.

---

# 5. Oracle Model

## Tier 1: Mechanical

Deterministic counting procedures.

Examples:

* unsupported claim ratio
* hedge frequency
* citation density
* bullet ratio

Preferred whenever possible.

---

## Tier 2: Human-Calibrated Judge

Used only when no reliable mechanical metric exists.

Requirements:

* human-labeled calibration set
* tracked agreement score
* admissibility enforcement

The judge is an instrument.
It is never the source of truth.

---

## Tier 3: Real-World Consequence

Terminal oracle.

Examples:

* issue closure rate
* contributor time-to-PR
* production incident reduction

Highest authority when available.

---

# 6. Admissibility System

## Purpose

Prevent unvalidated judges from entering scoring.

---

## Rule

Tier-2 verdicts are inadmissible unless:

`(judge_id, axis)`

has a calibrated record.

---

## Storage

Admissibility is recorded at write time.
It is never recomputed.

---

## States

### Admissible

May enter aggregation.

### Inadmissible

Stored for audit only.
Cannot affect results.

---

## Principle

No admissible evidence ⇒ no claim.

---

# 7. Clause Extraction

## Goal

Convert prose instructions into atomic directional contracts.

---

## Output Schema

Each clause contains:

* clause text
* axis
* comparator
* oracle tier
* vacuity flag

---

## Vacuity Detection

A clause is vacuous if:

* no observable delta can be defined
* no falsifying case can be constructed
* no measurable axis exists

Vacuous clauses are excluded from testing.

---

# 8. Coverage Law

A clause is untested until at least one falsifying case exists.

Coverage is measured by:

`tested_clauses / total_clauses`

where:

`tested_clause = clause with ≥1 falsifying case`

---

# 9. Frozen Regression Suite

## Purpose

Capture failures permanently.

Every adversarial input that defeats a skill becomes a regression case.
The suite only grows.

---

## Oracle Provenance

Every frozen case stores:

* oracle source
* attribution
* timestamp
* metric provenance

---

## Oracle Sources

### Human

Requires:

* `labeled_by`
* `labeled_at`

### Mechanical

Requires:

* metric version

### Real World

Requires source attribution.

---

# 10. Metric Provenance

Mechanical oracles are versioned artifacts.

A frozen case must record:

* metric identity
* metric version
* implementation hash

Purpose:
Allow re-audit when metrics change.

---

# 11. Interaction Confounds

## Problem

Clauses interact.

Example:
`verbosity ↔ structure`

Removing one clause may unintentionally alter another axis.

---

## Detection

During ablation:
all clause metrics are monitored.

If removal of clause N causes a different clause axis to move beyond threshold:
confound event is recorded.

---

## Result

The clause outcome becomes:

`FLAGGED_CONFOUNDED`

instead of pass or fail.

---

## Principle

A contaminated delta must never be reported as clean evidence.

---

# 12. Mechanical Metric Library (Initial)

## Supported

### Assertion Density

`factual_claims / sentences`

---

### Unsupported Claim Ratio

`unsupported_claims / claims`

---

### Hedge Index

`hedge_tokens / sentences`

---

### Compliance Proxy

`directive_sentences / total_sentences`

---

### Verbosity

`tokens / instruction_units`

---

### Structure Score

Derived from:

* header ratio
* bullet ratio
* section balance

---

## Unsupported

Rhythm metrics.

Sentence-length variance is not considered a valid structure proxy.

Status: Unaudited.
No frozen cases may be minted from it.

---

# 13. Calibration System

## Calibration Unit

`(judge_id, axis)`

---

## Calibration Inputs

Human-labeled frozen pair set.

---

## Outputs

* agreement score
* calibration state
* validation timestamp

---

## Rule

Calibration is axis-specific.
No cross-axis inheritance allowed.

---

# 14. Aggregation Model

## Inputs

Only verdicts satisfying:

* admissible
* non-confounded

---

## Observation Encoding

Win = 1
Tie = 0.5
Loss = 0

---

## Posterior

`Beta(1,1)` prior

Posterior:
`Beta(1+w, 1+n−w)`

---

## Reporting

For every clause:

* posterior mean
* credible interval
* pass probability

---

## Pass Rule

Clause passes when:

`P(win_rate > threshold) ≥ confidence_requirement`

Default:

* `threshold = 0.60`
* `confidence_requirement = 0.95`

---

# 15. Clause Status Model

A clause may be:

### PASSED

Evidence exceeds threshold.

### FAILED

Evidence falls below threshold.

### CONFOUNDED

Interaction contamination detected.

### UNMEASURED

No admissible evidence exists.

---

# 16. Skill-Level Reporting

Skills are reported as vectors.
Never as a scalar score.

---

## Required Output

* Passed Clauses
* Failed Clauses
* Confounded Clauses
* Unmeasured Clauses
* Coverage
* Full-vs-Null Contribution

---

## Example

```
Passed: 7
Failed: 1
Confounded: 2
Unmeasured: 3
Coverage: 81%
Skill Contribution: +22%
```

---

# 17. System Architecture

## Deterministic Layer

Python runner.

Responsibilities:

* orchestration
* sampling
* scoring
* storage
* aggregation

---

## Stochastic Layer

Model workers.

Roles:

* subject
* injector
* calibrated judge

Models generate content only.
They never own control flow.

---

## Persistence

SQLite.
Append-only evidence model.

---

# 18. CLI

## `skill init`

Import and extract clauses.

---

## `skill clauses`

Inspect clause inventory.

---

## `run ablation`

Execute single-clause ablation.

---

## `run evaluate-skill`

Run full suite.

---

## `diff skill`

Compare skill revisions.

---

## `freeze`

Promote failure into regression suite.

---

# 19. Success Criteria

The system succeeds if it can:

1. Detect clause regressions caused by skill edits.
2. Distinguish failed clauses from unmeasured clauses.
3. Reject uncalibrated judges automatically.
4. Preserve oracle and metric provenance.
5. Surface confounded measurements instead of silently aggregating them.
6. Produce reproducible clause-level evidence across skill versions.

---

# 20. Core Invariant

A clause that cannot be falsified is not a contract.
It is metadata.

The harness exists to measure contracts, not intentions.
