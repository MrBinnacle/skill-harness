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

## Reproduce the case study (Windows)

```powershell
git clone https://github.com/MrBinnacle/skill-harness
cd skill-harness && git checkout v0.1.0
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

## Case study

[`docs/case-studies/ai-slop-sentinel-under-ablation.md`](docs/case-studies/ai-slop-sentinel-under-ablation.md)
— a real run against a widely-used skill, with 17 UNMEASURED clauses and the explanation
of why that result is honest rather than a failure.

Why UNMEASURED is not a failure:
[`docs/concepts/why-unmeasured.md`](docs/concepts/why-unmeasured.md)

## Full specification

[`PRD.md`](PRD.md) — wire format, oracle tiering, aggregation rules, CLI surface,
and the invariants the framework is built around.

## Architecture and internals

[`docs/internals/README.md`](docs/internals/README.md) — track layout, database
partition, discipline rationale, and development setup.
