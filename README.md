<p>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-dark.svg">
    <img alt="skill-harness. Compares one task with a skill and without it." src="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-light.svg" width="680">
  </picture>
</p>

# skill-harness

`skill-harness` is a measurement instrument for controlled skill-vs-no-skill comparisons. It
measures what a skill changes, what the skill costs, and whether the evidence is strong enough to
justify a claim.

One line carries the design:

> **skill exists ≠ skill was delivered ≠ model used skill**

A skill **exists** when the file is present, which says almost nothing about what the model
received. It was **delivered** when the runtime put its description into the model's context, which
this instrument calls **exposure** and treats as the treatment condition. The model **used** it when
it loaded the body, which is **invocation**, a downstream behavior the instrument records rather
than the treatment. In a 32-epoch paired run on `git-pull-rebase-trap`, exposure held at 32 of 32
while the body was invoked in 24 of 32
([receipt](https://github.com/MrBinnacle/skill-harness/blob/main/docs/sers/receipts/gitpull-paired-n32-2026-09-03-sized.json)).
Reading delivery as use would have been wrong about a quarter of the treated arm.

## Why this exists

I wanted to know if you could tell if a skill was any good.

That sentence is the owner's. The long account:
[docs/why-this-exists.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/why-this-exists.md).

## 1. What problem does this solve?

A skill costs context in every conversation, whether or not it fires, and that cost is arithmetic
on text. The benefit is conditional and hard to establish.

Suppose you run a task with a skill and score 85, and without it you score 75. The naive conclusion
is that the skill improved performance by 10 points. You have not established that. Maybe the skill
was never delivered, or was delivered differently between runs. Maybe the environment changed, or
the model changed, or the evaluator behaved differently, or one run was contaminated. Put the new
tire on one car and the old tire on another and you learn nothing about the tire.

The ratified question splits that in two:

> What does this skill cost you, and which parts of it are worth that cost?

## 2. What does the instrument do?

It constructs controlled comparisons where the treatment can be independently verified, records
runtime and evidence provenance, refuses inadmissible results, and reports only what the experiment
establishes.

Cost and benefit never collapse into one score. Cost is mechanical, measurable with no model spend.
Benefit needs a controlled comparison, and the question there is not whether the subject can do the
task but whether the skill changes performance against an otherwise comparable condition. That
separation is why a skill's benefit can be `UNMEASURED` without the skill being useless.

Four layers do the work: **subject execution** under a controlled Full or Null condition,
**evidence normalization** of runtime-native records into one representation that keeps their
provenance, a **scientific decision layer** holding the registered treatment definition, the
evidence-admissibility rules, the oracle and the statistics, and **reporting** of what survived
them. They are separate so that **the runtime does not get to define what counts as scientific
evidence.**

A screen returns one of three verdicts: **KEEP**, **CUT** with a named reason (`subsumed`, meaning
the model was already doing it; `no_lift`; or `harmful`), or **CAN'T-TELL-YET**. Which verdict a
skill is eligible for depends on its registered value class, not the numbers alone, and the
**value-class guard** enforces that: `subsumed` is a CUT only for skills registered
`TRANSFORMATIVE_LIFT`, the class whose whole claim is lift above the bar.
`append-only-evidence-design` and a hardened `git-pull-rebase-trap` both returned **CUT (subsumed)**
under the pre-guard rule, each at a no-skill pass rate of 1.00; the guard reclassified both to
CAN'T-TELL-YET, and the pre-guard results stay in the record as dated output.

## 3. What does it refuse to claim?

The governing rule: **where no measurement exists, record the absence of measurement rather than
inventing a number or a verdict.** `UNMEASURED` is never bare. Which kind of not-knowing applies is
more information than not-knowing alone, so it carries one of eight registered sub-reasons:
`no_data`, `inadmissible`, `underpowered`, `falsifying_case_missing`, `budget_exhausted`,
`falsifying_case_stale`, `fdr_correction_failed`, `mechanical_vacuous`
(`src/skill_harness/aggregation/status.py`, defined in
[docs/concepts/why-unmeasured.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md)).

**The oracle only sees the final filesystem.** The registered oracle runs against the isolated
final filesystem, so it measures task outcome only. It cannot observe program design, coupling,
scope creep, or test quality. A skill can therefore raise the oracle result while degrading the
codebase, and the instrument will correctly report KEEP. **Maintainability effect is `UNMEASURED`
for every skill result produced to date.** No existing claim is retracted. The scope is now stated.

**The runtime is part of the apparatus.** Cross-runtime pooling is not automatic and is not
permitted without a separate equivalence measurement. The Pi 0.85.1 subject adapter is implemented
and apparatus-verified, validation battery green. **No sized Pi measurement has run, so no Pi skill
effect is admissible yet.** Apparatus compatibility is established and nothing more.

**Zero production-skill KEEPs.** The one KEEP on record is a declared synthetic positive control,
8 of 8 with the skill against 0 of 8 without: the instrument fires when an effect is present, and
that says nothing about any real skill. A sized benefit run launches only on the first task whose
no-skill screen returns a pass rate below 1, and the production screens ceiling at 1. Every verdict,
with its receipt:
[what the instrument has found](https://github.com/MrBinnacle/skill-harness/blob/main/docs/what-the-instrument-has-found.md).

The rule points inward; both figures stay here.

**Extraction repeat-variance:** MEASURED for one skill. Three repeat extractions of the same
`SKILL.md` returned 29/33/34 clauses, so clause counts are **not stable** run to run, and nothing
downstream keys on clause position
([#152](https://github.com/MrBinnacle/skill-harness/issues/152)).

**Vacuity-flag precision:** MEASURED at 0.972 by blind cross-family adjudication over 106
adjudicated rows, **flag-level only**
([#153](https://github.com/MrBinnacle/skill-harness/issues/153), receipt
`docs/calibration/vacuity-flag-calibration-2026-08-08.json`). When the adjudicators also had to
agree on *which kind* of vacuity, kind-precision 0.835: `not_a_directive` matched 77/77, while
`weak_directive` matched 4/20. The vacuity-flag detector's recall is UNMEASURED: the unflagged
clauses were never adjudicated.

## 4. How does it keep the comparison honest?

Six properties are explicit. Each is a way a comparison goes wrong when left implicit.

- **Treatment delivery.** The ingest path checks exposure per epoch on both arms before it writes
  evidence. A Full epoch with no exposure raises `UnexposedFullEpochError`, a Null epoch with
  exposure raises `NullArmContaminationError` (`src/skill_harness/subject/ingest.py`), and both are
  recorded as apparatus errors, not evidence.
- **Subject and runtime identity.** Every receipt pins the subject, the harness version, the metric
  version and an implementation hash.
- **Evidence admissibility.** Evidence passes a gate before it enters an aggregate, and the
  append-only store snapshots the gate result at write time. It keeps what fails the gate and never
  counts it, so an auditor can check the gate.
- **Oracle identity.** The outcome rule is registered and versioned with the result, and a
  judge-graded result counts only where that judge was calibrated on that axis first.
- **Ratification.** A paid run binds to a decision record before it spends.
- **Provenance.** Every figure carries instrument identity, the model pin and prompt fingerprint
  that stamp which generation produced it. Models change underneath a figure, so two numbers from
  two generations are visibly non-comparable rather than averaged.

The **Skill Efficacy Reporting Standard (SERS)** fixes that vocabulary, as a JSON Schema plus a
prose companion in
[docs/sers/](https://github.com/MrBinnacle/skill-harness/tree/main/docs/sers/). CI checks that this
repository's own receipts validate against it, that its enums match the code's, and that
deliberately poisoned receipts are rejected.

## 5. How do I use it?

Start with the zero-cost offline audit. Move to a ratified paid comparison only when the evidence
path justifies it.

```bash
pip install skill-harness                              # Python 3.12 or later
skill-harness skill audit path/to/your/SKILL.md
```

The audit makes no API call, needs no key, and touches no network. It reports the cost triple
(standing, fired, aux) as arithmetic on text, checks structure against
[Anthropic's authoring spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices),
and states what a paid run could measure today.

Read the gaps it reports. Run on 2026-09-13 from a clean v0.3.0 install against the fixture
`tests/fixtures/sers/declared-synthetic-positive-control/SKILL.md`, the audit printed
`Standing cost (mechanical): UNMEASURED` and the check name `standing-cost-unparseable`, because
its minimal parser could not read that card's description. A default there would have understated
the per-turn tax. That whole run is in
[docs/offline-audit-example.md](https://github.com/MrBinnacle/skill-harness/blob/main/docs/offline-audit-example.md).
`--strict` exits 1 on warnings, for CI.

A paid comparison:

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable claims
skill-harness run ablation <skill_id>                 # dry-run: no calls, no cost
skill-harness run ablation <skill_id> --execute \
  --ratification docs/ratifications/RAT-NNNN-<skill-slug>.md \
  --task-family <family> --estimand <treatment-policy|hypothetical>
skill-harness run evaluate-skill <skill_id>           # aggregate to a verdict
```

Set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`. Spending is a per-subcommand property.

| Command | Default behaviour | What changes it |
| --- | --- | --- |
| `skill init` | clause extraction is a model call in both modes | `--execute` persists the result, and creates `evidence.db` and `runtime.db` in the current directory before the API-key check |
| `run ablation` | dry-run: no calls, no cost | `--execute` opts in to spending, under a per-run cap and a daily cap |
| `run evaluate-skill` | aggregates stored evidence, makes no model call | `--dry-run` reports what it would aggregate, then stops |
| `run evaluate-paired` | read-only: no writes and no API calls | nothing; it declares neither flag |
| `run pi-paired` | dry-run: the pre-spend gate only, no epoch | `--execute` runs the Full and Null epochs and writes the pair |

`run ablation` and `run pi-paired` are the subcommands that spend. `run ablation` and
`run evaluate-skill` read those same two database paths; pass `--evidence-db` or `--runtime-db` to
put them elsewhere. The three flags on `run ablation --execute` must match the scope fields of a
record in
[docs/ratifications/](https://github.com/MrBinnacle/skill-harness/tree/main/docs/ratifications/)
([#47](https://github.com/MrBinnacle/skill-harness/issues/47)), and that preflight runs before any
model call and before the API-key check, so a run without one exits 1:

```text
Error: ratification preflight refused --execute [record-missing]: no ratification record referenced; pass --ratification docs/ratifications/RAT-NNNN-<skill-slug>.md (see that dir's README)
```

## The other half

The verdicts land in [MrBinnacle/skills](https://github.com/MrBinnacle/skills). There, each skill
carries its own dated evidence record, and controlled results are read from that skill's record,
not a front-page roll-up. Skills are re-screened when a major model ships and publicly retired,
with the record intact, once the model no longer needs them or a platform change meets a
pre-registered trigger. Each retirement is made against its stated criterion.

## Where the rest is

- [What the instrument has found](https://github.com/MrBinnacle/skill-harness/blob/main/docs/what-the-instrument-has-found.md):
  every verdict to date, with its receipt.
- [Run-to-run noise](https://github.com/MrBinnacle/skill-harness/blob/main/docs/run-to-run-noise.md):
  why a three-runs-a-side comparison cannot settle this.
- [Other tools in this area](https://github.com/MrBinnacle/skill-harness/blob/main/docs/other-tools-in-this-area.md),
  and what this repository does not claim.
- [Reading guide](https://github.com/MrBinnacle/skill-harness/blob/main/docs/reading-guide.md): the
  case studies, the receipts index and `docs/PRD.md`.

Status: v0.3.0 is the latest published release, on
[PyPI](https://pypi.org/project/skill-harness/). The published package and the current development
tree are distinct states. Not every older screen record is in the evidence store yet. Work is
prioritised correctness first, then evidence integrity, runtime portability, measurement breadth
and presentation.

MIT licensed. Issues and PRs welcome:
[CONTRIBUTING.md](https://github.com/MrBinnacle/skill-harness/blob/main/CONTRIBUTING.md).
