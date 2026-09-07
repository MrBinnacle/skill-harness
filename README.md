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

A skill is a file an agent loads as instructions. Search for one that makes AI writing read less
like AI writing and a dozen come back. Each costs context in every conversation, whether or not it
fires. Reading the file tells you how it reads; it tells you nothing about whether it changes an
outcome.

`skill-harness` runs one task twice, once with the skill and once without it, and reports what the
evidence supports about the difference. The most common report is "not enough to call it."

```bash
pip install skill-harness
skill-harness skill audit path/to/your/SKILL.md
```

That command runs offline. It makes no API call, needs no key, and touches no network.

## Why this exists

I wanted to know if you could tell if a skill was any good.

That sentence is the owner's, and it is the question this repository was built to answer. The
longer account, and the two commands that re-derive how much machinery the question cost, are in
[docs/why-this-exists.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md).

The skills it screens live in [MrBinnacle/skills](https://github.com/MrBinnacle/skills). Claude
Code skills are the first-class subject, and the subject layer is built to take other agent
ecosystems.

## The question

> What does this skill cost you, and which parts of it are worth that cost?

That is the ratified wording, and it splits a question that "is this skill good" hides. A skill has
a **price**, paid in every conversation whether or not it fires. It has a **benefit** that may or
may not appear when it does. The price is arithmetic on text and costs nothing to report. The
benefit needs a paid comparison, and the evidence for one usually stops short of a call.

Price and benefit are measured differently, reported in separate fields, and never combined into a
single score.

## The free offline audit

`skill audit` reports three properties of a `SKILL.md`, with no API key, no database, and no
network.

- **The cost triple.** What the skill costs standing, fired, and in its side docs (aux), as
  arithmetic on text.
- **Structural checks** against
  [Anthropic's authoring spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
- **An evaluability preflight.** What a paid run could and could not measure about this skill
  today.

The output below comes from that command on the committed fixture
`tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`, run on 2026-09-06 at v0.3.0 in
a 100-column terminal. Two lines are removed: `source:` (a local absolute path) and `sha256:`. The
Summary line's trailing pointer to `docs/concepts/why-unmeasured.md` is dropped so the line renders
whole. Everything else is verbatim.

```text
OFFLINE AUDIT — no API calls, no cost
  skill:  declared-synthetic-positive-control
  body:   9 lines / 41 words · frontmatter keys: description, name
                               Structure (Anthropic authoring spec)
┌────────┬───────────────────────────────────┬────────────────────────────────────────────────────┐
│ Level  │ Check                             │ Finding                                            │
├────────┼───────────────────────────────────┼────────────────────────────────────────────────────┤
│ PASS   │ name                              │ name 'declared-synthetic-positive-control' meets   │
│        │                                   │ spec                                               │
│ INFO   │ description-unparsed-block-scalar │ description uses a multi-line YAML block scalar,   │
│        │                                   │ which this audit's minimal frontmatter parser      │
│        │                                   │ cannot read — description content checks skipped   │
│        │                                   │ (UNMEASURED, not passed)                           │
│ PASS   │ body-length                       │ body 9 lines (budget 500)                          │
│ WARN   │ standing-cost-unparseable         │ router listing line (frontmatter name +            │
│        │                                   │ description) is not readable as a single-line pair │
│        │                                   │ — standing cost UNMEASURED (no number; a silent    │
│        │                                   │ default would understate the per-turn tax)         │
└────────┴───────────────────────────────────┴────────────────────────────────────────────────────┘
Evaluability preflight — what a paid run could measure today:
  Tier-1 mechanical axes: citation_presence_per_flag, compliance_proxy, hedge_index,
structure_score, verbosity (style-shaped only).
  Behavior-shaped claims (correctness, tool use, outcomes): no mechanical instrument in v0.1 → the
recorded state would be UNMEASURED, not an estimate.
  Judge-graded axes: require a calibrated (judge, axis) pair — none exists in a fresh install →
UNMEASURED until you run `calibrate`.
  Standing cost (mechanical): UNMEASURED — frontmatter could not be parsed well enough to count the
router listing line (see standing-cost-unparseable).
  Fired cost (mechanical): raw 68 tokens · calibrated 77 tokens (x1.128, measured range
1.084-1.179) -- skill body charged when the skill runs and its body is read.
  Aux cost (mechanical): raw 0 tokens · calibrated 0 tokens (x1.128, measured range 1.084-1.179) --
other documentation files beside the skill (progressive disclosure); 0 when the skill directory has
none.

Summary: 2 pass · 1 warn — UNMEASURED is a recorded state, not a failure.
Clause evidence: UNMEASURED (no_extraction: clause evidence requires an extraction output; produce
one with skill init --out <file>)
```

Read the two gaps in that output, because they are the point. The parser could not read the
description, so the audit names the check it skipped and marks the result `UNMEASURED` rather than
passing a field it never read. The standing cost has no number for the same reason, and the audit
prints `UNMEASURED` where a silent default would have understated the per-turn tax.

`--strict` exits 1 on warnings, for CI. From v0.3.0 the CLI sets UTF-8 on its own output streams;
on v0.2.3 a Windows console needs `PYTHONUTF8=1` set first, or the command exits 1 with
`UnicodeEncodeError`.

## What it has found so far

**Zero production-skill KEEPs.** What the keep lane has returned, once, end to end, is a KEEP on a
*declared synthetic positive control*: a skill written on 2026-07-27 to carry an invented fact, so
the effect exists by construction. It scored 8/8 with the skill against 0/8 without, posterior
probability of a win 0.99
([SERS receipt, 2026-07-27](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/synthetic-control-keep-2026-07-27.json)).
That run shows the instrument fires when an effect is present. It says nothing about whether any
real skill is worth its slot.

The usual outcome is that the model already does the task without a skill. On two deliberately
hardened tasks a frontier agent passed 14 of 14 no-skill runs, which left nothing for a skill to
improve and so nothing to measure. That is a finding about the task, written up in
[the double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md).

The paired run in that study, July 2026, cost about $6.17 and returned the pre-registered NO-GO: an
apparatus check, not a measurement of benefit. The receipt records it as one
([`double-ceiling-nogo-2026-07-09.json`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/double-ceiling-nogo-2026-07-09.json)).

Scheduling explains none of that. A sized benefit run launches only on the first task whose
no-skill screen returns a pass rate below 1, and every production skill screened so far ceilings at
1: the model passes every attempt without it
([observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md)).

## Run-to-run noise, and the rule it produced

Comparing a skill against nothing is noisier than it looks. On a 60-trial arc of identical agentic
coding tasks, run-to-run output-token variation measured CV about 17.6% (RMS across cells;
mean-of-cells 14.6%, median 10.4%) on an Opus-class model
([findings record](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/why-naive-skill-benchmarks-mislead.md)).
At that coefficient of variation, a three-runs-a-side comparison cannot separate differences under
roughly 30% to 40% from noise, and three runs a side is what most published skill comparisons use.
Hand-picked tasks tilt the result before anything runs. Pass/fail test banks price what a skill
*costs* and skip what it *does*. Each claim in the findings record carries its own evidence grade.

The design rule follows from that. **Where no measurement exists, the field prints `UNMEASURED`.**
No placeholder zero, no free-typed excuse, no estimate standing in for a measurement.

Three consequences follow from the rule.

- Every paid comparison has a control arm: with the skill and without it, never a score in a
  vacuum, because a score in a vacuum cannot show that the model did not need the skill.
- Where the evidence cannot carry a call, the recorded state is `UNMEASURED` with a reason drawn
  from a fixed list of eight: `no_data`, `inadmissible`, `underpowered`,
  `falsifying_case_missing`, `budget_exhausted`, `falsifying_case_stale`, `fdr_correction_failed`,
  `mechanical_vacuous` (`src/skill_harness/aggregation/status.py`). Which kind of not-knowing
  applies is more information than not-knowing alone. Definitions:
  [`docs/concepts/why-unmeasured.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md).
- Evidence passes a gate before it enters an aggregate, and the append-only store snapshots the
  gate result at write time. The store keeps data that fails the evidence-admissibility gate and
  never counts it. A judge-graded result counts only where that judge has been calibrated on that
  axis first. Calibration swaps answer order to cancel position bias, controls for length, defends
  against injection, and measures agreement with a human.

## Where the instrument is weak

The same rule points inward. Two of the instrument's own weak points are measured, and both numbers
stay on the front page.

**Extraction repeat-variance:** MEASURED for one skill. Three repeat extractions of the same
`SKILL.md` returned 29/33/34 clauses, so clause counts are **not stable** run to run, and nothing
downstream is allowed to key on clause position
([#152](https://github.com/MrBinnacle/skill-harness/issues/152)).

**Vacuity-flag precision:** MEASURED at 0.972 by blind cross-family adjudication over 106
adjudicated rows, and that figure is **flag-level only**
([#153](https://github.com/MrBinnacle/skill-harness/issues/153)). When the adjudicators also
had to agree on *which kind* of vacuity, kind-precision 0.835: `not_a_directive` matched 77/77,
while `weak_directive` matched 4/20. The vacuity-flag detector's recall is UNMEASURED: the
unflagged clauses were never adjudicated.

## What it measures

A screen comes back as one of three verdicts: **KEEP**, **CUT**, or **CAN'T-TELL-YET**. A CUT says
why, from three reasons: `subsumed` (the model was already doing it), `no_lift` (the model needed
help and the skill did not deliver it), or `harmful`. Which verdict a skill is eligible for depends
on its registered value class, not on the numbers alone.

The **value-class guard** sits on that. A skill can exist to stop one specific wrong move. A model
that passes without such a skill has shown that the trap did not come up, which is a different
finding from the skill being useless. So `subsumed` is a CUT only for skills registered as
`TRANSFORMATIVE_LIFT`, the class whose whole claim is lift above the bar. Every other class
reclassifies to CAN'T-TELL-YET, on the ground that this is the wrong instrument for that kind of
skill rather than a verdict on it.

Two skills from the collection moved that way when the guard landed: `append-only-evidence-design`
(calibration) and a hardened `git-pull-rebase-trap` (trap-discipline). Under the pre-guard rule
both returned **CUT (subsumed)**, each at a no-skill pass rate of 1.00; the value-class guard
reclassified both to CAN'T-TELL-YET
([receipts](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/receipts/)). The
pre-guard CUTs stay in the record as dated output, not edited into agreement.

The other half of the lane has never run: a paired run sizing how much a skill helps once the model
is known to need help. By design a sized benefit run launches only when a screen returns a sub-1
pass rate, and none has.

## Running a paid measurement

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable claims
skill-harness run ablation <skill_id>                 # dry-run first: no calls, no cost
skill-harness run ablation <skill_id> --execute \
  --ratification docs/ratifications/RAT-NNNN-<skill-slug>.md \
  --task-family <family> --estimand <treatment-policy|hypothetical>
skill-harness run evaluate-skill <skill_id>           # aggregate to a verdict
```

Set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`. Which command spends is a per-subcommand property,
not a blanket one:

| Command | Default behaviour | What changes it |
| --- | --- | --- |
| `skill init` | clause extraction is a model call in both modes | `--execute` changes only whether the result is persisted to the evidence DB. Without a key it exits 1 before any call. |
| `run ablation` | dry-run: no calls, no cost | `--execute` opts in to spending, under a per-run cap and a daily cap |
| `run evaluate-skill` | aggregates stored evidence and makes no model call | `--dry-run` reports what it would aggregate and stops |
| `run evaluate-paired` | read-only: no writes and no API calls | nothing; it declares neither flag |

`run ablation` is the only subcommand that spends.

The snippet also writes into the directory you run it from. `skill init` creates `evidence.db` and
`runtime.db` in your current directory, and it creates them before the API-key check, so they
appear even on the run that exits 1 with no key, in both dry-run and `--execute` mode. `run
ablation` and `run evaluate-skill` default to those same two paths (`--evidence-db` and
`--runtime-db`, both shown in `--help`). Pass either flag to put the databases somewhere else.

`run ablation --execute` additionally requires `--ratification`, `--task-family`, and `--estimand`:
a RATIFIED decision record in
[`docs/ratifications/`](https://github.com/MrBinnacle/skill-harness/tree/main/docs/ratifications/)
that pre-authorizes the spend, the task family the run evaluates, and the registered estimand, all
of which must match the record's own scope fields
([#47](https://github.com/MrBinnacle/skill-harness/issues/47)). That preflight runs before any
model call and before the API-key check, so a run with no `--ratification` exits with
`ratification preflight refused --execute [record-missing]` rather than a key error. Dry-run is
exempt, and the ratification directory's own
[README](https://github.com/MrBinnacle/skill-harness/blob/main/docs/ratifications/README.md)
documents the record shape. Reproduction scripts:
[`examples/`](https://github.com/MrBinnacle/skill-harness/tree/main/examples/).

## The reporting standard

The **Skill Efficacy Reporting Standard (SERS)** fixes the vocabulary: verdicts, refusal reasons,
the cost triple, the evidence-admissibility statuses, and the instrument identity. Instrument
identity is the model pin and prompt fingerprint that stamp *which generation* produced a figure.
SERS is a JSON Schema plus a prose companion, in
[`docs/sers/`](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/).

SERS sits apart from this tool's internals on purpose. Another tool can emit conforming reports
without adopting anything here. CI checks that this repository's own receipts validate against the
schema, that the schema's enums match the code's, and that deliberately poisoned receipts are
rejected.

Models change underneath every figure, so every figure has a shelf life. Instrument identity is a
required field, which makes two numbers from two generations visibly non-comparable rather than
averaged.

## Other tools in this area

If you want the most *featureful* skill benchmarking today,
[adewale's skill-eval-harness](https://github.com/adewale/skill-eval-harness) is the closest
neighbour and is further along on more axes. A few of its disciplines are on the adoption list
here, with attribution. For comparing prompts and configurations rather than skills,
[promptfoo](https://github.com/promptfoo/promptfoo) is the mature choice. For evaluating models and
agents, [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) is the institutional one. Reach
for this one when the question is whether a figure should be stated at all.

This repository makes no first-mover claim, and the positioning was checked against primary sources
before it was written: the first-or-only claims failed that check
([#39](https://github.com/MrBinnacle/skill-harness/issues/39)). Two claims carry the most weight
instead: the pre-spend eligibility gate, and the rule that thresholds are ratified from enumerated
tables rather than authored by hand. Both carry claim-status labels tied to an external review plan
([#45](https://github.com/MrBinnacle/skill-harness/issues/45)), and both change by dated amendment
rather than silently.

## The other half

The verdicts land in a second repository:
[MrBinnacle/skills](https://github.com/MrBinnacle/skills), a small collection. There, each skill
carries its own dated evidence record and controlled results are read from that skill's record,
not a front-page roll-up. Skills are re-screened when a major model ships and publicly retired,
with the record intact, once the model no longer needs them or a platform change meets a
pre-registered trigger. Each retirement is made against its stated criterion.

## Further reading

- [The receipts, rendered](https://mrbinnacle.github.io/skill-harness/) is the SERS receipts as a
  browsable site, one page per screened skill, cost triple beside the evidence grade. It renders
  the SERS instances only; the Markdown index below is the citable surface for every kind.
- [Measurement receipts index](https://github.com/MrBinnacle/skill-harness/blob/main/docs/receipts-index.md)
  lists every case study, finding, observation, assurance report, ratification, SERS instance, and
  the `skill audit --extraction` join surface, with what each one claims and where each one stops.
- [Why this exists](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md)
  covers how a non-specialist ends up building a measurement instrument, and the loop that made it
  possible.
- [The double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md)
  is the run where there was nothing left to measure.
- [The ablation that caught its own author](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/ai-slop-sentinel-under-ablation.md)
  records three pre-spend catches before a contaminated result could ship.
- [When ablation measures the wrong layer](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md)
  shows that if a discipline fires in a hook, ablating the skill text says nothing about the
  discipline.
- [`docs/PRD.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/PRD.md) is the full
  specification: evidence model, oracle tiers, gate rules, CLI reference.
- [The observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md)
  carries per-record screen history, annotated rather than rewritten.

Status: v0.3.0 on PyPI. Not every older screen record is yet in the evidence store; the observation
ledger shows the evidence behind each record.

MIT licensed. Issues and PRs welcome:
[`CONTRIBUTING.md`](https://github.com/MrBinnacle/skill-harness/blob/main/CONTRIBUTING.md).
