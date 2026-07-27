# FAQ

Short answers to the questions this tool provokes. Depth links point into the rest of `docs/`.

## It said `UNMEASURED`. Did it fail?

No. `UNMEASURED` is a verdict, not an error. It means the evidence on the table doesn't support a keep/cut call — the task was too easy to separate the arms, the run was too noisy, or the judge for that axis isn't calibrated. The tool stores that state and reports it plainly instead of rounding noise up into a finding. A benchmark that always prints a number can't tell you when it doesn't actually know. See [concepts/why-unmeasured.md](concepts/why-unmeasured.md).

## Zero production-skill KEEPs so far — is the tool broken?

No — and this is the most useful thing it tells you. On a frontier model, *"the model already does this fine without the skill"* is the most common truthful result. Every production skill screened to date has ceilinged: the model passed the no-skill runs, so there was nothing for the skill to add. Two skills were run live end-to-end (`append-only-evidence-design` and a hardened `git-pull-rebase-trap`); both came back **CUT (subsumed)** at a bare-arm pass rate of 1.00. That's the instrument working. The KEEP path itself is validated, not hypothetical: a declared synthetic positive control — a skill carrying an invented fact, so the effect exists by construction — earned the program's first store-backed KEEP (2026-07-27, Full 8/8 vs Null 0/8), confirming the label fires when a real effect is present. A tool that says KEEP only for a measured effect, and labels its one synthetic-control KEEP as exactly that, is more trustworthy than one that manufactures a KEEP to look useful.

## What's the difference between the CUT verdicts?

- **CUT (subsumed)** — the model already does the task without the skill (bare-arm pass rate is high). The skill isn't adding measurable value because the value is already there.
- **CUT (no-lift)** — the task was one the model genuinely struggled with (bare-arm pass rate is low), the skill was measured against it, and it still didn't move the outcome.

The distinction matters: *subsumed* is about the task being easy for the model now; *no-lift* is about the skill failing on a task that was actually hard.

## Why measure with-vs-without instead of just grading the skill file?

Grading the skill file — linting it, having an LLM judge it — answers *"is this artifact well-made?"* That's a fair question, but it's not the one that decides an install. The install question is *"is my agent measurably better with this than without it?"*, and the only way to answer it is a paired comparison against the no-skill baseline. Frontier models often ace the task with no skill at all; a score-in-a-vacuum can't surface that. See [findings/why-naive-skill-benchmarks-mislead.md](findings/why-naive-skill-benchmarks-mislead.md).

## Making the task harder should create a KEEP eventually — why doesn't it?

It was tried. Across two screens and a paired run, a frontier agent passed 14/14 no-skill epochs on two deliberately hardened tasks — making the traps more naturalistic did not open any headroom for a skill to fill. The pattern holds because a reminder-style skill only helps where the model's baseline behavior actually falls short; when the baseline is already competent, there's nothing to remind. The one hint of headroom was a data-skepticism check the model genuinely sometimes skips — an unpublished dogfooding observation, not a tracked verdict. See [case-studies/double-ceiling-structurally-unmeasured.md](case-studies/double-ceiling-structurally-unmeasured.md).

## Does it only work with Claude?

The paired runs use a frontier model as the subject; you supply either an `ANTHROPIC_API_KEY` (direct) or an `OPENROUTER_API_KEY` (auto-routed to other providers). The offline `skill audit` needs no key at all.

## Can I run it for free, or in CI?

Yes. `skill-harness skill audit path/to/SKILL.md` is fully offline — no API key, no cost. It runs a structural check against Anthropic's authoring spec and previews what a paid run could and couldn't measure about the skill. `--strict` exits non-zero on warnings, so it drops into CI as a gate. The paid `run` commands are dry-run by default; `--execute` is required to spend, with per-run and daily budget caps.

## How is this different from other skill evals?

Three properties the certification-style tools don't have:

1. **A control arm** — every measurement is with-vs-without, not a score in a vacuum.
2. **An honest failure mode** — when the evidence is weak, the answer is `UNMEASURED`, stored and first-class, never an estimate.
3. **A paper trail** — evidence admissibility is checked and snapshotted at write time in an append-only store; inadmissible data is kept but never aggregated.

If you want the most *featureful* skill benchmarking today, other tools have more surface. Use this one when what you care about is whether the number deserves to exist. The full comparison table is in the [README](../README.md#how-it-compares).

## Why should I trust a number from it?

Because the same discipline that produces the number also throws numbers away. Run-to-run noise on agentic tasks was measured at ±17.6% — large enough to swallow most skill effects — so a single lucky run can't become a verdict. LLM-judge results count only from a calibrated (judge, axis) pair: position-swapped, length-controlled, injection-defended, with human agreement measured before any judged verdict is admitted. The tool's own author has been caught by it more than once; those catches are in the [case studies](case-studies/), on purpose.
