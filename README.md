# skill-harness

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/MrBinnacle/skill-harness/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/skill-harness.svg)](https://pypi.org/project/skill-harness/)

**Does the skill actually change anything?**

`skill-harness` is an evaluation harness for testing Claude Code skills with controlled with/without comparisons.

The question is not whether a skill looks well written.

The question is whether using it changes the outcome of a task enough to justify its cost.

A task can succeed without the skill. Two runs can differ without the skill causing the difference. A score can be precise without measuring the thing you care about.

This repository is an attempt to separate those cases.

## Try the free audit

You can inspect a skill without an API key, database, or network connection.

```bash
pip install skill-harness

skill-harness skill audit path/to/SKILL.md
```

The offline audit reports:

* the skill's mechanical text cost;
* structural checks against Anthropic's skill-authoring guidance;
* an evaluability preflight showing what a paid evaluation could and could not establish.

The audit also reports when it cannot parse something it was asked to inspect.

`UNMEASURED` is a recorded state, not a pass.

## The question has two parts

A skill has a **cost** whether or not it helps.

It consumes context when it is loaded, and additional context when it fires or uses supporting material. Those costs are mechanical and can be measured without running a task.

A skill may also provide a **benefit**.

That requires a comparison.

The core evaluation therefore runs the same task with the skill and without it.

The two quantities are kept separate. A lower cost does not imply a benefit. A successful task does not imply that the skill caused the success.

## When a comparison is worth running

A benefit run is not useful when the model already passes the task without the skill.

The harness therefore screens the no-skill condition first.

**A sized benefit run launches only on the first task whose no-skill screen returns a pass rate below 1.**

This creates an important result that a conventional benchmark can hide:

> If the model already completes the task without the skill, there may be no remaining failure for the skill to correct.

That does not prove the skill is useless in other contexts. It means the evaluation did not establish a lift on this task.

## What happens when the evidence is not enough

The harness does not require every run to end in a positive or negative verdict.

It can return `UNMEASURED` with a specific reason:

* `no_data`
* `inadmissible`
* `underpowered`
* `falsifying_case_missing`
* `budget_exhausted`
* `falsifying_case_stale`
* `fdr_correction_failed`
* `mechanical_vacuous`

The reason matters.

`underpowered` and `no_data` are not the same problem. Neither should be silently converted into zero.

A missing figure is therefore a typed result rather than an empty field.

## Run an evaluation

```bash
skill-harness skill init path/to/SKILL.md --execute
skill-harness run ablation <skill_id> --execute
skill-harness run evaluate-skill <skill_id>
```

Commands that can spend money are dry-run by default.

`--execute` is required to spend.

Per-run and daily limits are enforced.

`ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` are supported.

Reproduction material is available in [`examples/`](examples/).

On Windows terminals, set `PYTHONUTF8=1` when required:

```powershell
$env:PYTHONUTF8=1
```

## What the current record says

The current record does not establish that the production skills evaluated so far provide a measurable benefit.

The harness has produced a declared synthetic positive control. Its expected effect was constructed into the test, so the result demonstrates that the keep path can fire when a real effect is present by construction.

It does not establish that a production skill is effective.

The more common result so far has been that the model already passes the task without the skill.

On two deliberately hardened tasks, a frontier agent passed every no-skill attempt. There was therefore no remaining lift to measure.

One paired run in July 2026 cost about $6.17 and returned a pre-registered `NO-GO`. It was an apparatus check, not a benefit measurement.

The current measurement record is indexed in the [measurement receipts index](docs/receipts-index.md).

## Some results changed the instrument

The evaluation work has produced findings about the evaluation itself.

### Run-to-run variation exists

In a 60-trial agentic-task arc, run-to-run variation reached ±17.6% with the other conditions held constant.

A small difference between two runs is therefore not automatically an effect.

See [Why naive skill benchmarks mislead](docs/findings/why-naive-skill-benchmarks-mislead.md).

### Repeatability does not establish validity

A Figma pilot produced byte-identical repeat exports and still failed the evaluation stack.

A result can be repeatable and still fail to establish that the measurement is valid.

### Judge results require calibration

Judge-graded results are admitted only after calibration against the specific axis being judged, including controls for answer order, length, injection, and agreement with human assessments.

The calibration record is separate from the result being judged.

### The instrument changed its own classification rules

Two skills previously received `CUT (subsumed)` results.

A later value-class guard changed their current classification to `CAN'T-TELL-YET` because a no-skill success does not establish that every kind of skill is unnecessary.

The earlier results remain in the historical record.

They were not rewritten to match the current rule.

## Reporting is separate from the implementation

The reporting vocabulary is defined in the **Skill Efficacy Reporting Standard (SERS)**.

SERS defines the report structure, verdict vocabulary, refusal states, cost representation, and instrumentation metadata used to identify the model and prompt generation associated with a result.

The schema and documentation are in [`docs/sers/`](docs/sers/).

The harness validates its own receipts against the schema.

SERS is separate from this implementation. Another evaluation harness can emit conforming reports without using this codebase.

Model generations change.

Results from different generations are therefore not silently treated as interchangeable. Instrument identity is recorded with each result.

## What the harness does not establish

This repository implements an evaluation procedure.

That does not establish that the procedure is valid for every question one might ask about a skill.

Open questions include the validity and calibration of the task-selection procedure, statistical power, judge behavior, confound handling, and generalization beyond the evaluated task and model configuration.

Those questions are part of the project.

The existence of the harness does not answer them.

## Current conclusions

So far, the strongest conclusions are methodological rather than about skill efficacy:

* a task can succeed without a skill;
* a difference between runs is not automatically an effect;
* a repeatable measurement is not automatically a valid measurement;
* some evaluation questions cannot currently be answered from the available evidence;
* an evaluator can require changes to its own rules when its current rules produce an invalid classification.

The production-skill efficacy question remains open for most of the collection.

## The other repository

I also maintain [`MrBinnacle/skills`](https://github.com/MrBinnacle/skills), a small collection of Claude Code skills developed from problems encountered in actual use.

The two repositories were developed concurrently.

The skills are the artifacts being evaluated.

`skill-harness` is the attempt to evaluate them.

Whether the harness provides valid evidence about skill efficacy, and what that evidence says about any particular skill, remain empirical questions.

## Related work

This is not the only project concerned with evaluating models, agents, or skills.

The adjacent tools are useful for different questions. For example:

* [`adewale/skill-eval-harness`](https://github.com/adewale/skill-eval-harness) — another project focused on skill evaluation.
* [`promptfoo`](https://github.com/promptfoo/promptfoo) — broader evaluation tooling for prompts and LLM applications.
* [`Inspect AI`](https://github.com/UKGovernmentBEIS/inspect_ai) — a broader framework for evaluating models and agents.

These links are here to help locate adjacent work, not to establish a ranking.

## Documentation

* [Documentation map](docs/README.md)
* [Why this exists](docs/why-this-exists.md)
* [Measurement receipts index](docs/receipts-index.md)
* [Assurance](docs/ASSURANCE.md)
* [Invariants](docs/INVARIANTS.md)
* [Case studies](docs/case-studies/)
* [Findings](docs/findings/)
* [Concepts](docs/concepts/)
* [SERS](docs/sers/)
* [Examples](examples/)

## License

MIT.
