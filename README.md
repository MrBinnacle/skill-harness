<p>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-dark.svg">
    <img alt="skill-harness — the skill eval that refuses to invent a score" src="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-light.svg" width="680">
  </picture>
</p>

# skill-harness

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/MrBinnacle/skill-harness/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/skill-harness.svg)](https://pypi.org/project/skill-harness/)

## Why this exists

I wanted to know if you could tell if a skill was any good.

That sentence is the owner's, and it is the question this repository was built to answer. The
longer account, and the two commands that re-derive how much machinery the question cost, are
in [docs/why-this-exists.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md).

A skill is a file an agent loads. Search for one that makes AI writing read less like AI
writing and a dozen come back. Each costs context in every conversation, whether or not it
fires. Reading the file tells you how it reads. It does not tell you whether it changes an
outcome.

skill-harness runs the same task with the skill and without it, and reports what the evidence
supports about the difference. The most common report is "not enough to call it."

The skills it screens live in [MrBinnacle/skills](https://github.com/MrBinnacle/skills). Claude
Code skills are the first-class subject; the subject layer is built to take other agent
ecosystems.

## What does this skill cost you, and which parts of it are worth that cost?

That is the ratified wording. "Is this skill good" hides two questions. A skill has a
**price**, paid in every conversation whether or not it fires. It has a **benefit** that may
or may not appear when it does. The price is arithmetic on text and costs nothing to report.
The benefit needs a paid comparison, and the evidence for it usually stops short of a call.

The two are measured differently, refused differently, and reported in separate fields. The
instrument does not collapse them into one score.

## Try the free offline skill audit

`skill audit` runs offline. No API key, no database, no network.

```bash
pip install skill-harness
skill-harness skill audit path/to/your/SKILL.md
```

It reports three things. The **cost triple**: what the skill costs standing, fired, and in its
side docs (aux), as arithmetic on text. A set of **structural checks** against
[Anthropic's authoring spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
An **evaluability preflight**: what a paid run could and could not measure about this skill
today.

The output below is from that command on the committed fixture
`tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`, run on 2026-08-30 at
v0.2.3, with the table columns abridged:

```text
OFFLINE AUDIT — no API calls, no cost
  skill:  declared-synthetic-positive-control
  body:   9 lines / 41 words · frontmatter keys: description, name

  PASS  name                        name 'declared-synthetic-positive-control' meets spec
  INFO  description-unparsed-block-scalar
                                    description uses a multi-line YAML block scalar, which
                                    this audit's minimal frontmatter parser cannot read —
                                    description content checks skipped (UNMEASURED, not passed)
  PASS  body-length                 body 9 lines (budget 500)
  WARN  standing-cost-unparseable   standing cost UNMEASURED (no number; a silent default
                                    would understate the per-turn tax)

  Standing cost (mechanical): UNMEASURED
  Fired cost (mechanical):    raw 68 tokens · calibrated 77 tokens
  Aux cost (mechanical):      raw 0 tokens · calibrated 0 tokens

Summary: 2 pass · 1 warn — UNMEASURED is a recorded state, not a failure.
```

The parser could not read the description, so the audit says so and skips the check. It does
not pass a field it never read. The standing cost has no number for the same reason, and the
audit prints `UNMEASURED` rather than a default.

`--strict` exits 1 on warnings, for CI. On Windows terminals, set `PYTHONUTF8=1` first.

## What it has found so far

**Zero production-skill KEEPs.** The full keep lane has fired end to end once, on 2026-07-27.
The subject was a *declared synthetic positive control*: a skill written to carry an invented
fact, so the effect exists by construction. It returned KEEP at 8/8 with the skill against 0/8 without,
posterior probability of a win 0.99
([SERS receipt, 2026-07-27](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/synthetic-control-keep-2026-07-27.json)).
That run shows the instrument fires when an effect is present. It says nothing about whether
any real skill is worth its slot.

The most common result is that the model already does the task without a skill. On two
deliberately hardened tasks a frontier agent passed 14 of 14 no-skill runs. Nothing was left
for a skill to improve, so nothing could be measured. That is a finding about the task, and it
is written up in
[the double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md).

The paired run in that study, July 2026, cost about $6.17 and returned the pre-registered
NO-GO: an apparatus check, not a measurement of benefit. The receipt records it as one
([`double-ceiling-nogo-2026-07-09.json`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/double-ceiling-nogo-2026-07-09.json)).

None of that is a scheduling accident. A sized benefit run launches only on the first task
whose no-skill screen returns a pass rate below 1. Every production skill screened so far
ceilings at 1: the model passes every attempt without it
([observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md)).

## Why it refuses

Comparing a skill against nothing is noisier than it looks. On a 60-trial arc of identical
agentic coding tasks, run-to-run output-token variation measured CV ≈ 17.6% (RMS across
cells; mean-of-cells 14.6%, median 10.4%) on an Opus-class model
([findings record](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/why-naive-skill-benchmarks-mislead.md)).
At that coefficient of variation, a three-runs-a-side comparison cannot separate differences
under roughly 30–40% from noise, and three runs a side is what most published skill
comparisons use. Hand-picked tasks tilt the result before anything runs. Pass/fail test banks
price what a skill *costs* and skip what it *does*. The findings record carries an evidence
grade on each claim.

The design rule follows from that. **A figure that is not there is stated as a typed refusal,
never filled in.** No placeholder zero, no free-typed excuse, no estimate standing in for a
measurement.

Three things follow from the rule.

**One.** Every paid comparison has a control arm. With and without, never a score in a vacuum,
because a score in a vacuum cannot show that the model did not need the skill.

**Two.** When the evidence cannot carry a call, the answer is `UNMEASURED` with a reason from a
fixed list of eight: `no_data`, `inadmissible`, `underpowered`, `falsifying_case_missing`,
`budget_exhausted`, `falsifying_case_stale`, `fdr_correction_failed`, `mechanical_vacuous`
(`src/skill_harness/aggregation/status.py`). Which kind of not-knowing is more information
than not-knowing alone. Definitions:
[`docs/concepts/why-unmeasured.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md).

**Three.** Evidence passes a gate before it enters an aggregate, and the gate result is
snapshotted at write time in an append-only store. Data that fails the evidence-admissibility
gate is kept and never counted. A judge-graded result counts only where that judge has been
calibrated on that axis first. Calibration swaps answer order to cancel position bias,
controls for length, defends against injection, and measures agreement with a human.

The same rule points inward. Two of the instrument's own weak points are measured, and both
numbers stay on the front page:

**Extraction repeat-variance:** MEASURED for one skill — three repeat extractions of the same
`SKILL.md` returned 29/33/34 clauses, so clause counts are **not stable** run to run and
nothing downstream is allowed to key on clause position
([#152](https://github.com/MrBinnacle/skill-harness/issues/152)).

**Vacuity-flag precision:** MEASURED at 0.972 by blind cross-family adjudication over 106
adjudicated rows, and that figure is **flag-level only**
([#153](https://github.com/MrBinnacle/skill-harness/issues/153)). When the adjudicators also
had to agree on *which kind* of vacuity, kind-precision 0.835: `not_a_directive` matched 77/77,
while `weak_directive` matched 4/20. The vacuity-flag detector's recall is UNMEASURED: the
unflagged clauses were never adjudicated.

## What it measures, and what it refuses to

The answer comes back as one of three verdicts: **KEEP**, **CUT**, or **CAN'T-TELL-YET**.
Which of those a skill is eligible for depends on its registered value class, not on the
numbers alone. A CUT says why: `subsumed` (the model was already doing it), `no_lift` (the
model needed help and the skill did not deliver it), or `harmful`.

The **value-class guard** sits on that. Some skills exist to stop one specific wrong move. A
model that passes without such a skill has not shown the skill is useless; it has shown the
trap did not come up. So `subsumed` is a CUT only for skills registered as
`TRANSFORMATIVE_LIFT`, the class whose whole claim is lift above the bar. Every other class
reclassifies to CAN'T-TELL-YET, because this is the wrong instrument for that kind of skill,
not a verdict on it.

Two skills from the collection moved that way when the guard landed: `append-only-evidence-design`
(calibration) and a hardened `git-pull-rebase-trap` (trap-discipline). Under the pre-guard rule
both returned **CUT (subsumed)**, each at a no-skill pass rate of 1.00; the value-class guard
reclassified both to CAN'T-TELL-YET
([receipts](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/receipts/)). The
pre-guard CUTs stay in the record as dated output, not edited into agreement.

The other half has never fired: a paired run sizing how much a skill helps once the model is
known to need help. By design, a sized benefit run launches only when a screen returns a
sub-1 pass rate, and none has.

## Measuring for real

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable claims
skill-harness run ablation <skill_id> --execute       # the with/without comparison
skill-harness run evaluate-skill <skill_id>           # aggregate to a verdict
```

`ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`. Every command that can spend money is
dry-run by default; `--execute` is required to spend, and a per-run cap and a daily
cap sit on top.
Reproduction scripts:
[`examples/`](https://github.com/MrBinnacle/skill-harness/tree/main/examples/).

## The reporting vocabulary is a published standard

The **Skill Efficacy Reporting Standard (SERS)** fixes the vocabulary: verdicts, refusal
reasons, the cost triple, the evidence-admissibility statuses, and the instrument identity.
Instrument identity is the model pin and prompt fingerprint that stamp *which generation*
produced a figure. SERS is a JSON Schema plus a prose companion, in
[`docs/sers/`](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/).

SERS is separate from this tool's internals on purpose. Another harness can emit conforming
reports without adopting anything here. CI checks that this repository's own receipts validate
against the schema, that the schema's enums match the code's, and that deliberately poisoned
receipts are rejected.

Models change underneath every figure, so every figure has a shelf life. Instrument identity is
a required field: two numbers from two generations are visibly non-comparable rather than
averaged.

## What this isn't

It is not the most featureful skill benchmarker available.
If you want the most *featureful* skill benchmarking today,
[adewale's skill-eval-harness](https://github.com/adewale/skill-eval-harness) is the closest
neighbour and is further along on several axes. Some of its disciplines are on the adoption
list, with attribution. For comparing prompts and configurations rather than skills,
[promptfoo](https://github.com/promptfoo/promptfoo) is the mature choice. For evaluating models
and agents, [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) is the institutional one.

Reach for this one when the question is whether the number deserves to exist at all.

This repository makes no first-mover claim. The positioning was checked against primary sources
before it was written, and the first-or-only claims failed that check
([#39](https://github.com/MrBinnacle/skill-harness/issues/39)). Two claims carry the most
weight: the pre-spend eligibility gate, and the rule that thresholds are ratified from
enumerated tables rather than authored by hand. Both carry claim-status labels tied to an
external review plan ([#45](https://github.com/MrBinnacle/skill-harness/issues/45)). They
change by dated amendment, never silently.

## The other half

The verdicts land in a second repository:
[MrBinnacle/skills](https://github.com/MrBinnacle/skills), a small collection. There, each skill
carries its own dated evidence record and controlled results are read from that skill's record,
not a front-page roll-up. Skills are re-screened when a major model ships and publicly retired,
with the record intact, once the model no longer needs them or a platform change meets a
pre-registered trigger. Each retirement is made against its stated criterion.

The two repositories run on one rule, pointed at two different things. This one does not state
a number the evidence does not support. That one does not keep a skill the evidence no longer
supports.

## Dig deeper

- [The receipts, rendered](https://mrbinnacle.github.io/skill-harness/) — the SERS receipts as a
  browsable site, one page per screened skill, cost triple beside the evidence grade. It renders
  the SERS instances only; the Markdown index below is the citable surface for every kind.
- [Measurement receipts index](https://github.com/MrBinnacle/skill-harness/blob/main/docs/receipts-index.md)
  — every case study, finding, observation, assurance report, ratification, SERS instance, and
  the `skill audit --extraction` join surface: what each claims and what each refuses to claim.
- [Why this exists](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md)
  — how a non-specialist ends up building a measurement instrument, and the loop that made it
  possible.
- [The double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md)
  — the run where there was nothing left to measure.
- [The ablation that caught its own author](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/ai-slop-sentinel-under-ablation.md)
  — three pre-spend catches before a contaminated result could ship.
- [When ablation measures the wrong layer](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md)
  — if a discipline fires in a hook, ablating the skill text says nothing about the discipline.
- [`docs/PRD.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/PRD.md) — the full
  specification: evidence model, oracle tiers, gate rules, CLI surface.
- [The observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md)
  — per-record screen history, annotated rather than rewritten.

Status: v0.2.3 on PyPI. Some older screen records are not yet in the evidence store; the
observation ledger shows the evidence behind each record.

MIT licensed. Issues and PRs welcome:
[`CONTRIBUTING.md`](https://github.com/MrBinnacle/skill-harness/blob/main/CONTRIBUTING.md).
