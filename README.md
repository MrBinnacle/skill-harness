# Skill Harness

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Skill Harness refuses to produce a confidence number when no admissible evidence exists
for the axis being claimed. UNMEASURED is the first-class verdict that makes this
refusal legible.

## What is different from existing LLM eval frameworks

Pairwise judges, scalar rubrics, and holistic LLM-as-judge approaches all produce
numbers. Skill Harness produces UNMEASURED when the framework does not have the
instrument to verify the clause being claimed. Where G-Eval asks a judge to score an
output, Skill Harness asks whether a specific clause — when removed — produces a
measurable directional change on its claimed axis. When no mechanical scorer exists
for the axis, the result is UNMEASURED, not an estimated score. The case study below
shows this distinction on a real, widely-used skill.

## Why this exists

Naive with-skill vs without-skill benchmarking — now common practice at k≈3 repetitions —
is trap-laden: run-to-run noise (measured CV ≈ 17.6% on agentic tasks) swallows all but
huge effects, matched tasks sample on the dependent variable, deterministic pass/fail
banks price a skill's standing *cost* while structurally missing its *benefit*, and
synthetic oracles leak their own answers through test-hygiene docstrings. The measured
findings behind each of those claims, with evidence grades:
[`docs/findings/why-naive-skill-benchmarks-mislead.md`](docs/findings/why-naive-skill-benchmarks-mislead.md).
This harness is the counter-design: directional verdicts, calibrated judges, admissibility
gating, and UNMEASURED as the honest default.

**v0.2 direction (locked, pre-registered gate):** whole-skill Full-vs-Null becomes the
primary contrast (clause ablation demotes to drill-down on signal), an agentic multi-turn
subject layer joins the single-turn adapter, and transcript-derived outcome oracles
(tests-pass, lint delta, diff size, turns, cost) join the stylometric Tier-1 set. Entry
conditions and pre-registration fields:
[`docs/findings/v0.2-reaim-gate.md`](docs/findings/v0.2-reaim-gate.md).

## Reproduce the case study (Windows)

```powershell
git clone https://github.com/MrBinnacle/skill-harness
cd skill-harness && git checkout main   # see "Why not v0.1.0?" below
python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"

# Required on Windows to avoid encoding errors and non-deterministic hashes
$env:PYTHONUTF8 = "1"; $env:PYTHONHASHSEED = "0"; $env:PYTHONPATH = "src"

$py = ".venv\Scripts\python.exe"
& $py -m skill_harness skill init <path-to-ai-slop-sentinel-SKILL.md> --execute
& $py -m skill_harness run ablation <skill_id> --execute
& $py -m skill_harness run evaluate-skill <skill_id>
```

`PYTHONUTF8=1` prevents cp1252 encoding errors on Windows terminals.
`PYTHONHASHSEED=0` makes JSON output byte-stable across re-runs.
See [`docs/concepts/why-pythonutf8-on-windows.md`](docs/concepts/why-pythonutf8-on-windows.md)
for detail. For `<path-to-ai-slop-sentinel-SKILL.md>` and a one-shot reproduction
script, see [`examples/`](examples/).

### API-key requirements (current state, honest)

Two API surfaces, two requirements:

- **`skill init`** calls the Claude API to extract clauses from your skill artifact. It
  accepts EITHER `ANTHROPIC_API_KEY` (direct Anthropic) OR `OPENROUTER_API_KEY`
  (auto-routed via OpenRouter's Anthropic-compatible endpoint) — the fallback landed
  on `main` 2026-06-09 (`b5b9fe6`). Operators on Claude Code subscription auth with
  only an OpenRouter key can now run `skill init` end-to-end against `main`
  (not against the `v0.1.0` tag, which predates the fallback).
- **`run ablation --execute`** calls the subject model. It accepts EITHER
  `ANTHROPIC_API_KEY` (direct Anthropic) OR `OPENROUTER_API_KEY` (auto-routed via
  OpenRouter with a stderr warning). The `--subject-model` flag selects the model id;
  see `--help` for the matrix of direct vs OpenRouter forms.

The case study's own author hit this exact asymmetry in real time — see the case
study's HALT 2 narrative for the audit trail.

### Why not `git checkout v0.1.0`?

The case-study reproduction recipe used to pin `v0.1.0` (commit `fd782b1`). The
v0.1.0 tag is the harness state the case study was written against, but it predates
the W2 CLI engineering work (commits `a9bdacc` + `f6201a8`) that added
`--subject-model` and the OpenRouter fallback for `run ablation`. Operators on
direct Anthropic API can reproduce at either tag; operators on OpenRouter-only
environments need `main` (or a future v0.1.1 tag) for the `run ablation` step.

## Case study

[`docs/case-studies/ai-slop-sentinel-under-ablation.md`](docs/case-studies/ai-slop-sentinel-under-ablation.md)
— a real audit trail of the discipline catching its own author across three classes
of inconsistency (documentation drift, operational state, orchestrator precondition
gap) before any contaminated result shipped. The deliverable is the chain of
refusals, not a number.

Why UNMEASURED is not a failure:
[`docs/concepts/why-unmeasured.md`](docs/concepts/why-unmeasured.md)

## Full specification

[`PRD.md`](PRD.md) — wire format, oracle tiering, aggregation rules, CLI surface,
and the invariants the framework is built around.

## Architecture and internals

[`PLAN.md`](PLAN.md) — track layout (A–E) and the locked v0.1 implementation plan.
[`PRD.md`](PRD.md) — the evidence model, oracle tiers, and discipline rationale.
Database partition: `migrations/evidence/` (append-only, trigger-enforced) +
`migrations/runtime/` (mutable operational state).
