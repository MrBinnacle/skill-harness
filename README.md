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

## The question I started with

I wanted to know whether a skill was any good.

Not "is this file well written" — whether it changes anything. Search for a skill that makes
AI writing sound less like AI writing and you get a dozen of them. Each one costs you context
in every conversation you have. So how do you tell one from another in a way that actually
means something? I assumed plenty of people had already asked that and that an answer was
sitting somewhere. I went looking for it, didn't find one I trusted, and ended up building
this instead.

skill-harness runs the same task with a skill and without it, and reports what can honestly be
said about the difference. Often what can honestly be said is "not enough to call it." That
turned out to be the useful part, and it took me a while to accept it.

It has first-class support for Claude Code skills and is built to extend to other agent
ecosystems.

## What it has found so far

Plainly, because this is the part a README usually hides:

**No production skill has come back KEEP.** Not one. The full keep lane has fired end to end
exactly once, on 27 July 2026, and that run was a *declared synthetic positive control* — a
skill I built to carry an invented fact, so the effect was real by construction. It returned
KEEP at 8/8 with the skill against 0/8 without, posterior probability of a win 0.99. That
tells you the instrument fires when a real effect is there. It does not tell you a single
real skill is worth its slot, and I am not going to let it be read that way.

The most common honest result, by a wide margin, is that the model already does the task fine
without any skill at all. On two deliberately hardened tasks a frontier agent passed 14 out of
14 runs with no skill present — there was nothing left for a skill to improve, so there was
nothing to measure. That is a real finding about the task, not a failure of the tool, and it
is written up in full: [the double-ceiling case
study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md).

One paired run before that, in July 2026, cost about $6.17 and returned a pre-registered NO-GO
— an apparatus check, not a measurement of benefit. I published it as such.

If you came here for a number that says your skill is good, this tool will disappoint you on
purpose.

## Why it refuses

Comparing a skill against nothing is noisier than it looks. In a 60-trial arc on agentic tasks
I measured run-to-run swings of ±17.6% with everything held constant. An effect smaller than
that is invisible at three runs a side, which is roughly what most published skill comparisons
do. Hand-picked tasks tilt the result before anything runs. Pass/fail test banks price what a
skill *costs* and quietly skip what it *does*. The write-up, with the evidence grade attached
to each finding, is [here](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/why-naive-skill-benchmarks-mislead.md).

So the design rule is the one I'd want from anyone reporting a number to me: **a figure that
isn't there is stated as a typed refusal, never filled in.** There is no third option — no
placeholder zero, no free-typed excuse, no estimate standing in for a measurement.

Three things follow from that.

**One.** Every paid comparison has a control arm. With and without, never a score in a vacuum,
because a score in a vacuum cannot tell you the model didn't need your skill.

**Two.** When the evidence won't carry a call, the answer is `UNMEASURED` with a reason
attached from a fixed list of eight — `no_data`, `inadmissible`, `underpowered`,
`falsifying_case_missing`, `budget_exhausted`, `falsifying_case_stale`,
`fdr_correction_failed`, `mechanical_vacuous`. "I don't know" is information; which flavour of
not-knowing is more information still. Definitions:
[`docs/concepts/why-unmeasured.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md).

**Three.** Evidence is checked against a gate before it can enter an aggregate, and the check
is snapshotted at write time in an append-only store. Data that fails the
evidence-admissibility gate is kept — never deleted — and never counted. Judge-graded results
count only where that judge has been calibrated against that specific axis first — swapping
answer order to cancel position bias, controlling for length, defending against injection, and
measuring agreement with a human before any judged verdict is allowed to count.

## Try it without spending anything

`skill audit` is fully offline. No API key, no database, no network.

```bash
pip install skill-harness
skill-harness skill audit path/to/your/SKILL.md
```

It reports three things: the **cost triple** (what the skill costs you standing, when it
fires, and in its side docs — plain arithmetic on text, not a claim about effect), a set of
**structural checks** against [Anthropic's authoring
spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices), and
an **evaluability preflight** telling you what a paid run could and could not measure about
this skill today.

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

  Standing cost (mechanical): raw … tokens · calibrated … tokens
  Fired cost (mechanical):    raw … tokens · calibrated … tokens
  Aux cost (mechanical):      raw … tokens · calibrated … tokens

Summary: 2 pass · 0 warn — UNMEASURED is a verdict, not a failure.
```

Note what it does in the middle there. It couldn't parse the description, so it says so and
skips the check rather than passing something it never read. That behaviour is the whole
design, repeated at every layer.

`--strict` exits 1 on warnings, for CI. On Windows terminals, set `PYTHONUTF8=1` first.

## Measuring for real

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable claims
skill-harness run ablation <skill_id> --execute       # the with/without comparison
skill-harness run evaluate-skill <skill_id>           # aggregate to a verdict
```

Either `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` works. Anything that can spend money is
dry-run by default — `--execute` is required, and per-run and daily caps are enforced.
Reproduction scripts: [`examples/`](https://github.com/MrBinnacle/skill-harness/tree/main/examples/).

The answer comes back as **KEEP**, **CUT**, or **CAN'T-TELL-YET**. A CUT says why: `subsumed`
(the model was already doing it), `no_lift` (you needed the help and the skill didn't deliver
it), or `harmful`.

There's a guard on that. Some skills exist to stop one specific wrong move, and a model that
passes without the skill hasn't proved the skill is useless — it has proved the trap didn't
come up. So a CUT for `subsumed` is only allowed for skills registered as
`transformative-lift`. Everything else routes to CAN'T-TELL-YET, on the grounds that this is
the wrong instrument for that kind of skill rather than a verdict on it. Two of my own skills
moved that way when the guard landed — `append-only-evidence-design` (calibration) and a
hardened `git-pull-rebase-trap` (trap-discipline), both of which the model had passed without
help at a rate of 1.00. Their earlier CUTs are preserved as dated historical output rather
than quietly edited into agreement.

## The reporting vocabulary is a published standard

Everything above — verdicts, refusal reasons, the cost triple, the evidence-admissibility
statuses, and the model pin and prompt fingerprint that stamp *which generation* produced a
figure — is fixed by the **Skill Efficacy Reporting Standard (SERS)**, a JSON Schema plus a
prose companion: [`docs/sers/`](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/).

It's separate from this tool's internals on purpose. If you build your own harness, you can
emit conforming reports without adopting anything of mine. CI checks that this repo's own
receipts validate against it, that the schema's enums match the code's, and that deliberately
poisoned receipts get rejected — a guard that can't fail isn't guarding anything.

Models change underneath all of this, which means every figure has a shelf life. That's why
instrument identity is a required field and not a nicety: two numbers from two generations are
visibly non-comparable rather than silently averaged.

## What this isn't

It is not the most featureful skill benchmarker available, and I'd rather say so than let you
find out. If you want breadth today, [adewale's
skill-eval-harness](https://github.com/adewale/skill-eval-harness) is the closest neighbour
and is further along on several axes; some of its disciplines are on my adoption list, with
attribution. If you're comparing prompts and configurations rather than skills,
[promptfoo](https://github.com/promptfoo/promptfoo) is the mature choice. If you're evaluating
models and agents, [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) is the
institutional one.

Reach for this one when your question is whether the number deserves to exist at all.

I make no first-mover claims anywhere in this repo. I checked twelve of them against primary
sources before writing any positioning, and enough of them were wrong that I stopped making
them. The two claims carrying the most weight — the pre-spend eligibility gate and the rule
that thresholds are ratified from enumerated tables rather than authored by hand — are
labelled as scheduled for external review until that review has actually happened. They'll be
upgraded or downgraded by a dated amendment, never silently.

Citations belong in the methods paper I'm writing, not on a front page.

## The other half

Verdicts that nobody acts on aren't worth producing, so there's a second repo where they land:
[MrBinnacle/skills](https://github.com/MrBinnacle/skills), a small collection where each skill
carries a dated evidence record, and where skills are re-screened when a major model ships and
publicly retired — with the record intact — once the model no longer needs them.

The two repos run on one rule, pointed at two different things. This one won't state a number
the evidence doesn't support. That one won't keep a skill the evidence no longer supports.
Same refusal, different end of the pipe.

## Dig deeper

- [Why this exists](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md) — how a non-specialist ends up building a
  measurement instrument, and the loop that made it possible.
- [The double-ceiling case study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md)
  — the run where there was nothing left to measure. Ask any skill benchmark what its
  without-the-skill pass rate was before you believe the rest of it.
- [The ablation that caught its own author](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/ai-slop-sentinel-under-ablation.md)
  — three times, before a contaminated result could ship. The chain of refusals is the
  deliverable.
- [When ablation measures the wrong layer](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md)
  — if a discipline really fires in a hook, ablating the skill text tells you nothing about
  the discipline.
- [`docs/PRD.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/PRD.md) — the full specification: evidence model, oracle tiers, gate
  rules, CLI surface.
- [The observation ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md) — per-record screen history, annotated
  rather than rewritten.

Status: v0.2.2 on PyPI. The keep/cut layer is live; store-backed coverage of the older screen
records is partial and being backfilled, and the ledger above says which is which.

MIT licensed. Issues and PRs welcome —
[`CONTRIBUTING.md`](https://github.com/MrBinnacle/skill-harness/blob/main/CONTRIBUTING.md).
