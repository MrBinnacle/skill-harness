# Research track — evaluation-result representation

## Research status

**Question:** What properties must an evaluation-result representation satisfy to preserve the
decision-relevant information and epistemic boundaries of its underlying evidence?

**Status:** OPEN

**Current position:** Unknown.

**Known counterexample:** Existing work already addresses unified, machine-readable AI-evaluation
results. SERS therefore makes no novelty claim based on standardization or JSON representation
alone.

**Next test:** Compare SERS against existing result representations at the semantic and
interoperability levels, using the pairwise collapse test recorded in the pre-registration.

**Exit conditions:**
- FALSIFIED — existing work provides substantially equivalent semantics.
- DISTINCT — SERS represents material information existing systems do not.
- USEFUL — the distinction changes downstream interpretation or interoperability.
- UNRESOLVED — evidence remains insufficient.

## What this track is, and what it is not

```text
docs/sers/     What SERS currently is.
research/      Whether what SERS currently is represents a distinct and useful contribution.
```

This distinction is load-bearing. `docs/sers/` remains the specification. Nothing here revises it
until a dated finding warrants a change, and any such change is traceable to the finding.

SERS is a proposed reporting specification. It is not described as a standard in this repository.

## Pre-registration

The research question, hypotheses, method, falsification criteria and exit conditions were lodged
**before** any comparator was read in depth:

- [`comparative-analysis/sers-falsification.md`](comparative-analysis/sers-falsification.md)

Read it before adding evidence here. Criteria are not edited in place; they are struck and
amended with a date.

## Known counterexamples

Both are output of the EvalEval Coalition, and both are named in the pre-registration so that no
novelty claim can rest on their absence:

- *Every Eval Ever* — arXiv 2606.14516
- *Evaluation Cards* — arXiv 2606.09809

## Planned outputs

- landscape inventory — `standards-landscape/`
- semantic comparison matrix — `comparative-analysis/`
- interoperability analysis
- gap analysis
- dated findings — `findings/`

None of these exist yet. Their absence is the current state of the track, not an oversight.

## Provenance requirement

Every substantive landscape entry records: source · source_type · retrieved · version_or_commit ·
scope_reviewed · claims_verified · classification · notes.

Prefer primary sources. For a repository, record the commit inspected and the files read. A
project's README is not sufficient where the semantics live in its schema or implementation.

## Relationship to the rest of this repository

These are separate propositions and none proves another:

```text
Evaluator validity  ≠  Reporting-representation validity  ≠  Skill efficacy
```

This track concerns the middle one only.
