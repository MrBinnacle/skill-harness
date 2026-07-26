# Catching myself: a case study in AI agent self-audit infrastructure

> What if most of the LLM-prompted skills you use today can't be honestly
> evaluated by any framework you're using today?

## I built the framework. I built the skill. The framework refused to validate the skill. Twice.

I am the author of Skill Harness — a deterministic evaluation framework
for LLM skills. I am also the author of three of the most heavily-dogfooded
skills the harness was built to evaluate (`ai-slop-sentinel`,
`bayesian-eval-discipline`, `verbatim-content-subagent-dispatch`).

When I tried to publish a reproducible cross-vendor result on one of those
skills, the framework I built refused to run — twice in a row, for two
different classes of inconsistency in my own setup, before any subject
model was called and before any number could be shipped. A third class was
caught upstream of that by another seat in the dev-team-council process I
run on this repo.

This case study is the audit trail of that catching. It is the deliverable
because the catching is the demonstration. The original deliverable — a
cross-vendor measurement — was less informative than what replaced it.

## What I was trying to do

`ai-slop-sentinel` is one of the active Claude Code skills I author. It
asks the assistant to review AI-generated code against a curated "watch"
of slop anti-patterns, citing the watch by entry for each flag. Phase 4.4
of this project dogfooded it through the harness against
`claude-sonnet-4-6`. The harness reported a vector. The vector showed all
clauses came back **UNMEASURED**: no registered Tier-1 mechanical scorer
matched the extracted axes, no calibrated Tier-2 judge existed for them,
so the discipline refused to fabricate a contribution metric. Cost: $0.00.

I wanted to confirm that result was subject-invariant: that running the
same skill against a different vendor's model (`openai/gpt-5.5` via
OpenRouter) would produce the same vector, because the UNMEASURED verdict
arises from framework state, not subject behavior. Pre-registered the
prediction with peeking-immunization, committed the prediction before
any subject call, hardened the audit trail. Standard
`bayesian-eval-discipline` pattern.

The experiment never ran. The framework caught the setup twice instead.

## HALT 1 — documentation drift in my own work

The first pre-flight check inside the tracer dispatch compares the
currently-registered Tier-1 scorer set against the scorer set cited in
the dogfooding doc the case study was anchored to. The dogfooding doc
(commit `66510f9`, 2026-06-07 15:54 EDT) cites four scorers:
`verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`. The
v0.1.0 tag (commit `fd782b1`, 2026-06-07 21:47 EDT) and current main
register **five** — the same four plus `citation_presence_per_flag`,
added in the pretag fix-sprint at `3f6b0a9` and `4583669` between the
dogfooding run and the tag.

That single added scorer happens to match clause 0's extracted axis. At
the v0.1.0 tag the case study cites for reproducibility, the headline
"17 UNMEASURED / 0 PASSED" is no longer recoverable — at-least one
clause now reaches the sampling loop and produces a measured result. The
framework noticed. The pre-flight gate refused to issue any subject call.

I had drifted my own published number against my own tagged framework
between writing it down and shipping it. The discipline I built — to
catch exactly this class of error — caught me.

Audit trail in public history: pre-registration `1e09119`, PHASE A.5
amendment `9ab3d79`, HALT findings doc `b7ba643`. Zero subject calls,
$0.00 cost.

The engineer reflex is to silently re-baseline at HEAD, quietly correct
the case study, re-run the experiment, ship the corrected number. That
is what most teams will do when this happens to them. I have to assume
that's what most LLM evaluation results in circulation today are — a
silently-corrected version of an original miss that didn't survive
contact with the framework's own discipline. The corrected number leaves
no trail.

I committed the HALT instead and re-pre-registered at the shape level.

## HALT 2 — operational state mismatch (three compounding)

The re-pre-registration was tighter: rather than predicting a specific
17-element vector, predict only that the same skill, evaluated under
identical conditions against two different subjects, would yield
byte-stable equal §16 result vectors. Field-level equality. No specific
number claimed.

The framework refused to run again. This time the pre-flight check
caught three operational mismatches stacking:

1. **`ANTHROPIC_API_KEY` is absent** because Claude Code (my dev
   environment) authenticates by subscription, not API key. The CLI's
   default subject path (`AnthropicSubjectClient`) constructs
   `anthropic.Anthropic()` which fails without the env var.
2. **The CLI does not expose `--subject-model`.** A factory
   `make_subject_client(model)` exists at the library layer (added in
   PHASE A.5 for OpenRouter routing) but is unreachable from
   `run ablation`. The dispatch brief assumed a flag that doesn't exist
   on the CLI surface.
3. **The pre-existing `evidence.db` has five incomplete prior runs.**
   `aggregate_skill` enforces "no incomplete runs per skill_id" as a
   precondition (invariant A50/A53). Any new evaluation aggregates the
   wrong evidence set unless those rows are resolved.

**I had built a framework whose default subject client couldn't run on
the machine I built it on.**

Each in isolation is fixable. Together they exceed any sensible
"adaptation budget" for an experimental dispatch and require explicit
orchestrator direction to resolve. The pre-flight gate refused to
proceed.

Audit trail in public history: re-pre-registration `205fef9`, HALT
findings doc `703f40d`. Zero subject calls, $0.00 cost.

Items 1 and 2 are real product gaps in the harness — engineering work
queued for a follow-on dispatch. They are gaps I built into my own
framework and only surfaced by trying to evaluate my own skill on my
own machine. The framework caught them in front of me.

## HALT 3 — orchestrator precondition gap (upstream of HALTs 1 and 2)

The original tracer dispatch assumed I had an `ANTHROPIC_API_KEY`
available. I do not, and the orchestration layer (a separate skill,
`dev-team-council`, which runs the dev-team-style council fires that
gate architectural decisions on this repo) had no pre-flight step
asking. A subject-matter agent (the supply-chain auditor and the
EVAL-RESEARCH single-seat) was dispatched on the assumption of a
resource I cannot in fact provide.

This is orchestrator error. I surfaced it as a user with skin in the
game, not as the framework author — the same person, two hats. The
council SOP gained a new pre-fire step the same session
(commit `62391eb`): "verify all required external resources are
PM-confirmed available, in writing, before any subject-matter seat is
dispatched."

A new template, "External-vendor / API-surface change," was added. The
amendment is small and was small to write. The point is: the same
discipline that caught HALTs 1 and 2 — refusal to proceed when the
state is inconsistent — was extended one level upstream the moment we
noticed it was missing there.

Three HALTs. Three different layers (documentation drift; operational
state; orchestrator preconditions). All three caught in public history
before any contaminated result shipped.

## What three HALTs amount to

I tried to publish a confident cross-vendor result. The framework caught
me drifting at the documentation layer. The framework caught me drifting
at the operational layer. My own user-feedback caught my orchestrator
drifting at the precondition layer.

Zero subject calls. $0.00 in vendor spend. Zero confident-false numbers
shipped. Three commits worth of audit trail in public git history before
this case study was rewritten.

Compare against the cost of shipping the wrong number to a customer, a
board, a regulator, a user.

This is what doing this honestly looks like. It does not look like a
table of numbers. It looks like a stack of caught mistakes, all caught
by the discipline they were claims about, all caught in front of an
audience.

That is the artifact.

You are reading what the discipline produces when it has nothing honest
to say. Anyone running the same discipline against their own AI agents
would catch a different set of mistakes. They would catch some, because
most setups have some.

## The category I am claiming

`ai-slop-sentinel` and the other dogfooded skills will not be in any
LLM-eval leaderboard. They cannot be: there is no MMLU-style benchmark
for "did the skill's clauses do what they claim." LMArena and MT-Bench
and G-Eval and pairwise-preference judges measure something else
entirely — they measure whether the output looks plausible to a rater
with a rubric. That is not the question.

The question Skill Harness asks is: when this clause is removed, does
the subject's behavior on the axis the clause claims to govern actually
change? Differential ablation. A is compared against B on axis X. No
holistic grade. No vibe score. No LLM judge as a source of truth.

The relevant category is not "LLM eval framework." It is
**AI agent self-audit infrastructure**: tooling whose job is to let a
team running production AI agents audit, in a falsifiable way, whether
the prompts/skills/system messages in the loop are load-bearing. The
audit can produce a measurement. It can also refuse to produce one and
publish the refusal. Both are valid outcomes; the second is what most
of the field cannot represent in their data model.

I am the only thing in the category, today, because the category did
not exist as a named thing before this artifact. I expect that to
change. When it does, the category will exist as a named thing — which
is itself a more useful contribution than a number on a leaderboard.

## The asymmetric attack

The argument I am making is not "Skill Harness is more honest than
other frameworks." That argument requires the reader to admit Skill
Harness is better, which is a high psychological cost and they will
default to disagreement.

The argument I am making is: **other LLM-eval frameworks are dishonest
by construction.** A holistic LLM judge cannot verify a clause-level
claim it cannot mechanically check. A pairwise-preference judge can
tell you which response is preferred; it cannot tell you whether the
specific clause "cite the watch entry for each flagged finding" is
load-bearing in producing the preferred response. The conflation
between those two questions is structural. It is in the framework, not
the user.

The reader does not have to like Skill Harness to agree with that
sentence. They only have to admit the field has a representation gap.
Anyone numerate who reads the literature already half-believes it.

## What you'd see if you tried to reproduce this

You don't reproduce the original experiment — there isn't one. The
discipline refused to run it. What you reproduce is the audit trail:

```bash
git clone https://github.com/MrBinnacle/skill-harness
cd skill-harness
git checkout v0.1.0

# Read the audit trail in order:
git show 2a6141d   # T3 PHASE A — openai adapter + initial pre-registration
git show 62391eb   # SOP amendment — precondition-check pre-fire step
git show 9ab3d79   # PHASE A.5 amendment — OpenRouter routing
git show b7ba643   # HALT 1 — scorer registry drift findings
git show 43432b7   # PHASE A.5 SHA fill on main after cherry-pick
git show 205fef9   # PHASE B' re-pre-registration (shape-level)
git show 703f40d   # HALT 2 — environment + CLI + persistence findings
```

Each commit shows a specific decision, with the framework state at the
time, with no peeking at a result that wasn't there to peek at. The
sequence is the artifact. Anyone running the same discipline against
their own setup would have caught the same classes of inconsistency in
their own setup — or, if they were lucky enough to have a clean setup
on the first try, would not have needed to.

The reproducibility claim Skill Harness makes is that the discipline
can be applied to any AI-agent skill artifact a team is running in
production. The case study is not the experiment; the case study is
the discipline catching its own author.

The framework state needed to apply the discipline to your own skills
is on `main`. The two engineering gaps surfaced by HALT 2 (`--subject-
model` CLI flag, ANTHROPIC fallback path for `run ablation`) landed in
commits `a9bdacc` and `f6201a8` on 2026-06-09 — the audit trail of the
fixes is itself part of the discipline-catching-itself arc this case
study describes. One adjacent gap remained at the time of writing: the
extractor on `skill init` was still Anthropic-direct, with no OpenRouter
fallback, so operators on Claude Code subscription auth without a direct
Anthropic key could not run `skill init` end-to-end. That gap closed on
`main` on 2026-06-09 (`b5b9fe6`) as the symmetric follow-on to the W2
work — `skill init` now accepts either key.

## What this case study does not claim

It does not claim `ai-slop-sentinel` is a bad skill. It does not claim
the harness measured that. The harness explicitly refused to measure
that with the current scorer registry and the current set of calibrated
Tier-2 judges (none). The asymmetry between "we cannot prove it works"
and "it does not work" is preserved. Most LLM evaluation frameworks
erase that asymmetry by producing a confident number anyway. Skill
Harness's discipline is to preserve it. Live with the discomfort, extend
the Tier-1 scorer registry, or calibrate a Tier-2 judge. All three are
legitimate moves. Producing the number anyway is not.

It also does not claim author-of-discipline + author-of-skill +
author-of-orchestrator is the only honest way to run a framework like
this. It is what made the catching uncopyable in this specific case.
Other teams will have weaker skin-in-the-game alignment and different
catches. That is fine. The discipline is what generalizes; the
particulars of who got caught are not.

## What would change this result

Three classes of move would each produce a different deliverable:

1. **Extend the Tier-1 scorer registry.** A mechanical scorer for
   `citation_presence_per_flag` already landed pre-tag (and triggered
   HALT 1 by doing so). Scorers for the other 16 axes are finite,
   well-defined pieces of code. Each registered scorer opens one more
   clause to honest measurement. Producing a vector of mostly-measured
   clauses for `ai-slop-sentinel` is straightforward engineering once
   the registry is extended; it is a deliberate choice to ship v0.1.0
   without that work done, because the discipline of refusing to
   measure without a registered scorer is the load-bearing claim.
2. **Calibrate a Tier-2 LLM judge for the relevant axes.** Per
   framework discipline, a Tier-2 judge is admissible only after it
   passes position-swap and length-control calibration on a labeled
   set (≥50 pairs per axis, observed Cohen's κ on three-class
   marginals). No calibrated judge exists today. One could exist; it
   is a labeling project, not a prompting project.
3. **Catch more of my own work publicly.** The HALT pattern catches
   author drift; the more the framework catches, in public, the more
   credible the discipline becomes. The next tracer round may catch a
   different class. That is the point. The compounding audit trail is
   what generalizes.

The fourth move — handing the question to an uncalibrated judge and
reporting the number as if it were evidence — is the path the field is
on. It is not a path Skill Harness takes. The discipline of refusing
that path is the artifact.

---

*Reproducible artifact: Skill Harness on `main` at HEAD `f3a1fd1`. Tag
`v0.1.0` (commit `fd782b1`). Audit-trail commits cited inline above; HALT
findings at `docs/dispatch/t3-findings.md` and pre-registrations at
`docs/dispatch/t3-pre-registration.md` (internal process records,
maintained privately and not published in this repository — see the
provenance note in `docs/PLAN.md`); SOP amendment in
`.claude/skills/dev-team-council/SKILL.md` at `62391eb` (local, not
published). PRD specification at `docs/PRD.md` v1.1. Council-adopted
invariants at the internal council findings log A1-A62 (not published).
The dogfooding result that triggered this story is at
`docs/dogfooding-ai-slop-sentinel-2026-06-07.md` (baseline-state,
pre-registry-expansion; not published). Citations are retained as
provenance markers.*

*The discipline this case study describes is falsifiable by construction.
The audit trail is the test.*
