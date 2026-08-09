<p>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-dark.svg">
    <img alt="skill-harness — the skill eval that refuses to invent a score" src="https://raw.githubusercontent.com/MrBinnacle/skill-harness/main/assets/banner-light.svg" width="680">
  </picture>
</p>

# Skill Harness

[![CI](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MrBinnacle/skill-harness/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/MrBinnacle/skill-harness/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/skill-harness.svg)](https://pypi.org/project/skill-harness/)

*An evaluation harness for reusable AI agent skills. First-class Claude Code
support, built to extend to other agent ecosystems.*

> **Status: v0.2.2 — on PyPI; the keep/cut verdict layer is live; first measured KEEP
> (2026-07-27) is a declared synthetic positive control — zero production-skill KEEPs to date.**
> The tool now answers the slot question with one of three verdicts: **KEEP** (measurably worth
> its slot), **CUT** — either *subsumed* (the model already does the task without the skill) or
> *no-lift* (measured on a task the model needed help with, and it didn't deliver) — or
> **CAN'T-TELL-YET** (the evidence doesn't support a verdict). Screen-path **CUT (subsumed)**
> for an above-bar `p0` fires only when the skill's registered value class is
> `TRANSFORMATIVE_LIFT`; other value classes are routed to **CAN'T-TELL-YET** (wrong instrument)
> by the value-class guard. A made-up score is never emitted in place of CAN'T-TELL-YET.
>
> **Run live, end-to-end** (Inspect + Docker + deterministic oracle, direct Anthropic frontier
> model, 3 epochs each, store-backed): two real skills —
> [`append-only-evidence-design`](https://github.com/MrBinnacle/skills) and a hardened
> `git-pull-rebase-trap` — both returned **CUT (subsumed)** at a bare-arm pass rate of
> 1.00 under the pre-guard mapping (the model passed every no-skill epoch). Those runs are
> preserved as dated historical output of the pre-guard code, not as current verdicts. The
> value-class guard has since reclassified both to
> **CAN'T-TELL-YET**: an above-bar `p0` maps to CUT(subsumed) only for `TRANSFORMATIVE_LIFT`, and
> both skills are registered as other classes (`calibration` and `trap-discipline`).
>
> **Honest maturity.** **Zero production-skill KEEPs exist in the program to date.** The full
> KEEP lane — paired Full-vs-Null writer plus the audited-metric registration act — has fired
> end-to-end exactly once (2026-07-27): a **declared synthetic positive control** (a skill
> carrying an invented fact, so the effect is real by construction) returned a store-backed KEEP
> at Full 8/8 vs Null 0/8, posterior p_win 0.99. That run validates the instrument — the label
> fires when a real effect exists — and is labeled as such; it is not a production skill shown
> to be worth its slot. Before it, one paired k=8
> run (2026-07-09, ≈$6.17) executed as a pre-registered apparatus shakedown and returned a
> NO-GO datum, not a benefit measurement ([the double-ceiling case
> study](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md)). A sized benefit run
> launches only on the first task whose no-skill screen returns a pass rate below 1, and so far
> every screened production skill ceilings at 1. Store-backed coverage is partial: only a handful of the
> program's screen verdicts (a record resting on 26/26 Null epochs across 6 screened tasks)
> derive from an append-only evidence store (the two live runs plus a curated batch-1
> backfill); the rest are prose-backed pending backfill. A tool that says KEEP only for a
> measured effect — and labels its one synthetic-control KEEP as exactly that — is more
> trustworthy than one that manufactures a KEEP to look useful. The
> v0.1→v0.2 re-aim that got us here is pre-registered and published, not papered over:
> [`docs/findings/v0.2-reaim-gate.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/v0.2-reaim-gate.md).
>
> **Named measurement gaps (field-wide; this instrument names them with a pre-registered fix).**
> BetterBench ([arXiv:2411.12990](https://arxiv.org/abs/2411.12990)) found most benchmarks
> report neither extraction repeat-variance nor detector precision. Under the current
> generation this harness names both, and states the figure where one now exists:
> - **Extraction repeat-variance:** MEASURED for one skill under the current generation,
>   and not stable — a 3x repeat returned 29/33/34 clauses (identical-text core 20; the
>   flag decision on that core was 19/20 stable). Clause-level rates remain unquotable as
>   properties of skills-in-general
>   ([#152](https://github.com/MrBinnacle/skill-harness/issues/152), resolution and receipts on the ticket).
> - **Vacuity-flag precision:** UNMEASURED — corpus flags are detector outputs, not
>   validated findings ([#153](https://github.com/MrBinnacle/skill-harness/issues/153)).
>
> **Amendment (2026-08-02).** The historical Stage-0 screen records behind that aggregate now
> live as per-record, machine-parseable entries in the
> [OBS ledger](https://github.com/MrBinnacle/skill-harness/blob/main/docs/observations/README.md),
> which is canonical for per-record counts, evidence basis, and classification state; history is
> annotated there, never rewritten.

## Why this exists

With-vs-without skill benchmarking at 3 runs apiece is now common practice, and it is
trap-laden: run-to-run noise (we measured ±17.6% on agentic tasks in a 60-trial
Opus-class arc — receipt:
[`docs/findings/why-naive-skill-benchmarks-mislead.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/why-naive-skill-benchmarks-mislead.md))
swallows all but huge effects; hand-matched tasks quietly bias the result; pass/fail test
banks price a skill's *cost* while structurally missing its *benefit*; and synthetic test
oracles leak their own answers through docstrings. The measured findings, with evidence
grades, live in that same receipt. The independent literature agrees on the stakes:
low-quality skills don't just fail to help — they actively degrade performance. A tool that
can honestly say "no measurable effect" is the missing instrument.

## The question

**What does this skill cost you, and which parts of it are worth that cost?**

That is the question this harness is built to surface. It does not hand you a verdict in
place of your own value judgement — you decide whether the measured cost is worth paying,
and which pieces of the skill are worth their share. The keep/cut lane exists and is honest when
the evidence supports it; it is not the front-door frame.

Most skill-evaluation tools **score the skill file itself** — lint it, have an LLM judge
grade it, simulate runs against it. That answers *"is this artifact well-made?"* It is a
reasonable question. It is not the install question. The install question needs a control
arm, an honest failure mode, and a paper trail:

1. **A control arm.** Every paid measurement is with-vs-without, not a score in a vacuum.
   Frontier models often ace the task with no skill at all — in our own testing, *"the model
   already does this fine"* has been the most common truthful result. A score-in-a-vacuum
   can't tell you that.
2. **An honest failure mode.** When the evidence doesn't support a call — too noisy, task
   too easy, judge uncalibrated — the answer is `UNMEASURED`, stored and first-class, never
   an estimate that launders noise into a finding.
3. **A paper trail.** Evidence admissibility is checked and snapshotted at write time in an
   append-only store. Every number can show its work; inadmissible data is kept but never
   aggregated.

This harness is also the instrument behind the evidence records in
[MrBinnacle/skills](https://github.com/MrBinnacle/skills) — a living skill collection where
skills are re-screened on each major model release and publicly retired when models stop
needing them.

## Free offline surface: `skill audit`

No API key. No database. No network (the audit path itself never touches the network; the
paid measurement paths fetch tiktoken's `cl100k_base` encoding (~1.7 MB) on first use —
pre-seed `TIKTOKEN_CACHE_DIR` on air-gapped machines).

```bash
pip install skill-harness
skill-harness skill audit path/to/your/SKILL.md
```

`skill audit` is fully offline. It reports three things:

1. **Cost triple** — standing / fired / aux, each as raw tokens and calibrated tokens
   (router listing line charged every turn; body charged when the skill fires; progressive-
   disclosure docs beside the skill). Mechanical arithmetic on text, not a skill-effect claim.
2. **Structural checks** against
   [Anthropic's authoring spec](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).
3. **Evaluability preflight** — what a paid run could measure about this skill today, and
   which claims would come back `UNMEASURED`.

Output (abridged):

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

Evaluability preflight — what a paid run could measure today:
  Tier-1 mechanical axes: citation_presence_per_flag, compliance_proxy,
  hedge_index, structure_score, verbosity (style-shaped only).
  Behavior-shaped claims (correctness, tool use, outcomes): no mechanical
  instrument in v0.1 → verdict would be UNMEASURED, not an estimate.

Summary: 2 pass · 0 warn — UNMEASURED is a verdict, not a failure.
```

When the tool can't read something, it says so and skips the check — it does not pass what
it did not measure. That's the whole design, applied at every layer. `--strict` exits 1 on
warnings for CI use. On Windows terminals, set `PYTHONUTF8=1` first.

## Evidence grades and refusal

The other half of the product is the refusal machinery — co-equal with the cost surface,
not a demoted basement and not the front door.

**Whole-skill keep/cut lane** (live): one of three answers when the evidence supports a
call — **KEEP**, **CUT** (subsumed or no-lift), or **CAN'T-TELL-YET** — with the
value-class guard above. A made-up score is never emitted in place of CAN'T-TELL-YET.

**Claim-level `UNMEASURED`** is first-class and typed. When a clause cannot be measured,
the harness names *why* with one of eight sub-reasons (`no_data`, `inadmissible`,
`underpowered`, `falsifying_case_missing`, `budget_exhausted`, `falsifying_case_stale`,
`fdr_correction_failed`, `mechanical_vacuous`) rather than inventing a score. Full
definitions:
[`docs/concepts/why-unmeasured.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/concepts/why-unmeasured.md).

LLM-judge results count **only** from a calibrated (judge, axis) pair: position-swapped,
length-controlled, injection-defended, with human agreement measured before a single judged
verdict is admitted.

## Measuring for real (API key required)

```bash
skill-harness skill init path/to/SKILL.md --execute   # extract testable claims
skill-harness run ablation <skill_id> --execute        # run the with/without comparison
skill-harness run evaluate-skill <skill_id>            # aggregate verdicts
```

Both `skill init` and `run ablation` accept **either** `ANTHROPIC_API_KEY` (direct) or
`OPENROUTER_API_KEY` (auto-routed). Every command that can spend money is dry-run by default;
`--execute` is required to spend, and per-run/daily budget caps are enforced. Reproduction script and
details: [`examples/`](https://github.com/MrBinnacle/skill-harness/tree/main/examples).

## What it measures today — and what it refuses to

v0.1's honest scope: directional effects on **style** (verbosity, hedging, structure, citation
presence), measured claim by claim with a single-turn subject. Behavior-shaped claims —
correctness, tool use, outcomes — have no mechanical instrument in v0.1 and return
`UNMEASURED`.

The v0.2 re-aim ([gate doc](https://github.com/MrBinnacle/skill-harness/blob/main/docs/findings/v0.2-reaim-gate.md)) landed in v0.2.0: the
whole-skill Stage-0 screen (does the model pass *without* the skill?) is the primary, dominant
contrast, run against an agentic multi-turn subject with deterministic outcome oracles
(`file_contains`, `command_succeeds`), and the harness configuration is captured as an
admissibility field — because published agentic-benchmark experience puts harness-induced
variance at 10–20 points on identical model weights, larger than most skill effects. The
claim-level style path above still exists as the offline/audit surface. What has *not* yet
fired is a paired Full-vs-Null *benefit* run — the one paired execution to date was a
pre-registered apparatus shakedown that returned NO-GO (see the status note at the top):
a sized benefit run launches only when a screen returns a sub-1 pass rate, and none has yet.

## How it compares

|  | **skill-harness** | [skill-eval-harness](https://github.com/adewale/skill-eval-harness) | [promptfoo](https://github.com/promptfoo/promptfoo) | [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) |
|---|---|---|---|---|
| Primary question | is this claim about a skill backed by *admissible* evidence? | did this skill improve outcomes on my cases? | which prompt/config is better/safer? | how does this model/agent score? |
| Unit | claim (v0.1) → whole skill (v0.2) | whole skill, paired with/without + component ablations | prompt/config matrix | task/eval |
| When evidence is weak | **refuses**: `UNMEASURED` verdict; inadmissible rows are stored but never aggregate | flags: oracle tiers, critical-severity veto, audit warnings | — | — |
| LLM judges | admissible only from a calibrated (judge, axis) pair | user-supplied judge command, uncalibrated by design | judge/rubric assertions | model-graded scorers |
| Maturity | 0.x on PyPI (keep/cut layer live, 0 measured KEEPs) | active v0.5.x | mature, 23k+ stars | mature, institutional |

Honest guidance: if you want the most *featureful* skill benchmarking today, use adewale's
skill-eval-harness. Use this harness when what you care about is whether the number deserves to
exist.

### Prior art, named

The instrument upgrade now locked on the
[tracker map](https://github.com/MrBinnacle/skill-harness/issues/35) was designed against a
verified prior-art survey (twelve keystone claims checked against primary sources — which is
why no first-mover or only-tool claim appears in this repo). The three works that matter most:

- **[skill-eval-harness](https://github.com/adewale/skill-eval-harness)** (adewale, MIT,
  provider-agnostic — not Claude-Code-specific): the closest tool twin. Paired with/without
  runs with a sign-flip significance test, removal-only ablation with canonical-hash
  provenance on both arms, explicit tune/holdout/holdback splits, leakage lint, and
  lift-per-dollar telemetry. Several of those disciplines are on our adoption path, with
  attribution.
- **BACKTRACE** ([arXiv:2607.27484](https://arxiv.org/abs/2607.27484), Hu et al.): post-hoc
  skill attribution against a matched no-skill counterfactual — intervening on skill meaning,
  wording, identity, content, and assignment, and eliciting attribution only after the answer
  is committed.
- **ASSAY** ([arXiv:2606.15390](https://arxiv.org/abs/2606.15390), Wang et al.): per-skill
  causal attribution via randomized masking, and the finding that skill libraries show
  pervasive causal heterogeneity — individual skills routinely help on some task types while
  hurting on others, with the opposing effects canceling in aggregate.

### What this harness claims — and what it doesn't

Positioning under the same rules as the verdicts: no first-mover claims (the survey falsified
them); where a neighbor has an adjacent mechanism we name it rather than pretend it doesn't
exist; and the two claims that carry the most weight are visibly status-labeled until external
deliberation has run. Tense matters here: the refusal verdicts are live today, while the
characterized gate and earned-threshold machinery are the registered upgrade contract (locked
decision records on the tracker map above) — claimed as design commitments, not shipped code.

1. **Pre-spend characterized-error eligibility gate.** No paid run launches until the
   decision rule's attained error rates — enumerated on the exact lattice, never quoted
   nominal — are registered and a human has picked a conforming row. Nearest prior art:
   skill-eval-harness's budget pre-projection gate + trigger matrix (adjacent, but without
   attained-error characterization). We have not found this gate in characterized form
   elsewhere.

   > *Claim status: scheduled for external deliberation
   > ([#45](https://github.com/MrBinnacle/skill-harness/issues/45)). Upgrades to "externally
   > reviewed" or degrades to "internally derived, not externally deliberated" by dated
   > amendment — never silently.*

2. **Thresholds are earned, never authored.** Decision thresholds enter the harness only when
   a human picks a row from enumerated frontier tables (configuration → attained errors →
   cost) whose rows already meet registered targets — never by authoring a number free-hand.
   The pick is signed on an append-only ratification record before any paid run.

   > *Claim status: scheduled for external deliberation
   > ([#45](https://github.com/MrBinnacle/skill-harness/issues/45)); same amendment mechanics
   > as above.*

3. **Refusal machinery, live.** `UNMEASURED` and CAN'T-TELL-YET are first-class verdicts
   today; the registered upgrade adds the π_c invocation-rate refusal predicate — a skill
   that never fires gets its availability claim refused, not scored. Prior art flags
   weak-evidence cases (oracle tiers, audit warnings); flagging still emits the number, and
   refusal doesn't.
4. **A receipts ecosystem, not just a meter.** Verdicts bind to a public skills collection
   that executes them — [MrBinnacle/skills](https://github.com/MrBinnacle/skills) retires
   entries into `RETIRED.md` with the evidence linked — and this harness publishes its own
   null results the same way.

## Dig deeper

- [`docs/case-studies/ai-slop-sentinel-under-ablation.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/ai-slop-sentinel-under-ablation.md)
  — the discipline catching its own author three times before a contaminated result could
  ship. The deliverable is the chain of refusals, not a number.
- [`docs/case-studies/double-ceiling-structurally-unmeasured.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/double-ceiling-structurally-unmeasured.md)
  — a frontier agent passed 14/14 no-skill runs on two deliberately hardened tasks: on that
  task class there is nothing for a skill to improve, and any benchmark claiming otherwise owes
  you its no-skill pass rate first.
- [`docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/case-studies/displaced-enforcement-skill-ablation-blind-spot.md)
  — a scope boundary of skill-ablation: when a discipline's real firing lives in a hook, not in
  the model reading the skill, ablating the text measures the wrong layer — so a null there is
  not the discipline's verdict, and to measure the discipline you ablate the hook instead.
- [`docs/PRD.md`](https://github.com/MrBinnacle/skill-harness/blob/main/docs/PRD.md) — full specification: evidence model, oracle tiers,
  admissibility rules, CLI surface.
- Evidence store: `src/skill_harness/storage/migrations_sql/evidence/` (append-only,
  trigger-enforced) + `migrations_sql/runtime/` (mutable operational state).

MIT licensed. Issues and PRs welcome — see
[`CONTRIBUTING.md`](https://github.com/MrBinnacle/skill-harness/blob/main/CONTRIBUTING.md).
