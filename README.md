# Skill Harness

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Know whether your Claude Code skill actually does anything — a measured effect, or an
honest `UNMEASURED`. Never a guess.**

Most skill "benchmarks" produce a number no matter what. This harness refuses: when no
admissible instrument exists for the claim being tested, the verdict is `UNMEASURED` —
first-class, stored, and legible — instead of an estimate that launders noise into a
finding. That refusal is the product.

> **Status: pre-alpha, honestly.** v0.1 measures clause-level *style* effects with a
> single-turn subject. Our own published findings say that aim is wrong for the question
> most people have ("does this skill earn its slot?") — the correction is pre-registered
> in [`docs/findings/v0.2-reaim-gate.md`](docs/findings/v0.2-reaim-gate.md). This repo
> practices what it measures: the findings that invalidated our own v0.1 design are
> published, not papered over.

## Who this is for

You run Claude Code (or another agent) with a folder of `SKILL.md` files, and you want
to know which of them are load-bearing, which are dead weight riding your context
window, and which *can't currently be measured at all* — stated as exactly that.

## 60-second start — no API key, no cost

```bash
pip install git+https://github.com/MrBinnacle/skill-harness
skill-harness skill audit path/to/your/SKILL.md
```

Two commands to your first verdict. `skill audit` is fully offline: structural lint
against [Anthropic's authoring spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
plus an evaluability preflight — what a paid run could measure about this skill today,
and which claims would come back `UNMEASURED`. Real output:

```text
OFFLINE AUDIT — no API calls, no cost
  skill:  caveman
  body:   41 lines / 233 words

  PASS  name            name 'caveman' meets spec
  PASS  body-length     body 41 lines (budget 500)
  INFO  description-unparsed-block-scalar
        description uses a multi-line YAML block scalar, which this audit's
        minimal frontmatter parser cannot read — checks skipped
        (UNMEASURED, not passed)

Evaluability preflight — what a paid run could measure today:
  Tier-1 mechanical axes: citation_presence_per_flag, compliance_proxy,
  hedge_index, structure_score, verbosity (style-shaped only).
  Behavior-shaped claims (correctness, tool use, outcomes): no mechanical
  instrument in v0.1 → verdict would be UNMEASURED, not an estimate.

Summary: 3 pass · 0 warn — UNMEASURED is a verdict, not a failure.
```

Note the third line of that report: when the tool can't read something, it says so and
skips the check — it does not pass what it did not measure. That is the whole design,
applied at every layer. `--strict` exits 1 on warnings for CI use. On Windows
terminals, set `PYTHONUTF8=1` first.

## Measuring for real (API key required)

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable clauses
skill-harness run ablation <skill_id> --execute        # run the differential
skill-harness run evaluate-skill <skill_id>            # aggregate verdicts
```

Both `skill init` and `run ablation` accept **either** `ANTHROPIC_API_KEY` (direct) or
`OPENROUTER_API_KEY` (auto-routed). Every `run` command is dry-run by default;
`--execute` is required to spend money, and per-run/daily budget caps are enforced.
Reproduction script and details: [`examples/`](examples/).

## What it measures today — and what it refuses to

v0.1's honest scope: clause-level directional effects on **style axes** (verbosity,
hedging, structure, citation presence) with a single-turn subject. Behavior-shaped
claims — correctness, tool use, outcomes — have no mechanical instrument in v0.1 and
return `UNMEASURED`. LLM-judge verdicts are admissible **only** from a calibrated
(judge, axis) pair: position-swapped, length-controlled, injection-defended, with
human-agreement measured before a single judged verdict counts
([`docs/concepts/why-unmeasured.md`](docs/concepts/why-unmeasured.md)).

The pre-registered v0.2 re-aim ([gate doc](docs/findings/v0.2-reaim-gate.md)):
whole-skill Full-vs-Null becomes the primary contrast, an agentic multi-turn subject
joins the single-turn adapter, transcript-derived outcome oracles (tests-pass, lint
delta, diff size, turns, cost) join the mechanical set, and the subject harness
configuration itself becomes an admissibility condition — published agentic-benchmark
experience puts harness-induced variance at 10–20 points on identical model weights,
larger than most skill effects.

## How it compares

|  | **skill-harness** | [skill-eval-harness](https://github.com/adewale/skill-eval-harness) | [promptfoo](https://github.com/promptfoo/promptfoo) | [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) |
|---|---|---|---|---|
| Primary question | is this claim about a skill backed by *admissible* evidence? | did this skill improve outcomes on my cases? | which prompt/config is better/safer? | how does this model/agent score? |
| Unit | clause (v0.1) → whole skill (v0.2) | whole skill, paired with/without + component ablations | prompt/config matrix | task/eval |
| When evidence is weak | **refuses**: `UNMEASURED` verdict; inadmissible rows are stored but never aggregate | flags: oracle tiers, critical-severity veto, audit warnings | — | — |
| LLM judges | admissible only from a calibrated (judge, axis) pair | user-supplied judge command, uncalibrated by design | judge/rubric assertions | model-graded scorers |
| Maturity | pre-alpha | active v0.5.x | mature, 23k+ stars | mature, institutional |

Honest guidance: if you want the most *featureful* skill benchmarking today, use
adewale's skill-eval-harness. Use this harness when what you care about is whether the
number deserves to exist — evidence admissibility snapshotted at write time in an
append-only store, and refusal as a first-class outcome.

## Why this exists

With-skill vs without-skill benchmarking at k≈3 is now common practice, and it is
trap-laden: run-to-run noise (measured CV ≈ 17.6% on agentic tasks) swallows all but
huge effects, matched tasks sample on the dependent variable, deterministic pass/fail
banks price a skill's standing *cost* while structurally missing its *benefit*, and
synthetic oracles leak their own answers through test-hygiene docstrings. Measured
findings with evidence grades:
[`docs/findings/why-naive-skill-benchmarks-mislead.md`](docs/findings/why-naive-skill-benchmarks-mislead.md).
The independent literature agrees on the demand side: low-quality skills don't just
fail to help — they actively degrade performance. A tool that can honestly say "no
measurable effect" is the missing instrument.

## Dig deeper

- [`docs/case-studies/ai-slop-sentinel-under-ablation.md`](docs/case-studies/ai-slop-sentinel-under-ablation.md)
  — the discipline catching its own author three times before a contaminated result
  could ship. The deliverable is the chain of refusals, not a number.
- [`docs/PRD.md`](docs/PRD.md) — full specification: evidence model, oracle tiers,
  admissibility rules, CLI surface.
- [`docs/PLAN.md`](docs/PLAN.md) — v0.1 build tracks and architecture.
- Evidence store: `src/skill_harness/storage/migrations_sql/evidence/` (append-only,
  trigger-enforced) + `migrations_sql/runtime/` (mutable operational state).

MIT licensed. Issues and PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).
