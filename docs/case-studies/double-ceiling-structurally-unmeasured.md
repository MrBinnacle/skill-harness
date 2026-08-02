# The double-ceiling: when a skill's benefit is structurally unmeasurable

> I built a paired evaluation apparatus to measure whether a skill helps a
> frontier coding agent. The agent passed 14 of 14 no-skill epochs across two
> deliberately-hardened tasks. That null is the finding — and it generalizes
> to most skill benchmarks you will see published this year.

## The question that looked answerable

The primary contrast in this harness's v0.2 pre-registration
([`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md))
is Full-vs-Null: the same pinned agent, same pinned sandbox image, same task,
with exactly one difference — the skill under test is present or absent.
Before spending on any sized run, the registered protocol demands a noise
micro-run: measure the per-epoch discordance rate d (how often the two arms
disagree on a binary outcome oracle), because the locked stopping rule's
power is a function of d. The sizing mathematics is exact — dynamic
programming over the locked Beta-Binomial rule — and it says something
blunt: **at d ≲ 0.5, no effect is detectable inside N_max=40 pairs at any
effect size.** If the arms rarely disagree, there is nothing to measure.

The skill under test was a deliberately thin one (a 29-line SQLite helper,
already a cut-candidate). The subject: Claude Code pinned at 2.1.197 running
`claude-sonnet-5` via direct API, in a digest-pinned network-isolated
sandbox, scored by a pristine-at-score-time oracle the agent can never see.

## Ceiling one

Stage 0 of the registered protocol is a Null-only screen: 3 epochs, no
skill, ≈$0.50. If the stock agent passes 3/3, the task cannot discriminate
and the protocol rejects it before a paired dollar is spent.

Task v1 — implement an FTS5 notes-search module with trigger-sync under
direct SQL writes, literal-phrase escaping, and relevance ranking — was
leak-audited (static grep both directions, fresh-context reviewer) and
oracle-validated (gold implementation GREEN, naive implementation RED).
**Null passed 3/3.** Screen failed. Iterate harder, said the protocol.

## Ceiling two

Task v2 kept the v1 base and added a full boolean query language: quoted
phrases, implicit-AND, uppercase-OR with precedence, `-` exclusions
including phrase exclusion, punctuation-splits-words, unbalanced-quote
recovery, title-weighted frequency ranking with an id tie-break —
34 oracle asserts, each mapped to a numbered prompt rule. The fresh-context
reviewer earned its keep during authoring: it caught my prompt naming the
exact ranking API (a gift to the Null arm) and a placebo tie-break assert
whose expected order coincided with insertion order. Both fixed, gold
re-validated.

**Null passed 3/3 again.**

The protocol said stop after a second failed screen, and I stopped and
reported. The operator approved one more run with its purpose re-registered
BEFORE launch: not a benefit measurement, but an end-to-end apparatus
shakedown plus the d upper bound as a pre-stated NO-GO datum.

## What the paired run measured

Stage 1, paired k=8, one pin fingerprint on all 16 samples, ingested
through the evidence store's write-time admissibility machinery:

| Field | Value |
|---|---|
| Paired epochs | 8 (Full 8/8 pass, Null 8/8 pass) |
| Discordant epochs x | **0** — d̂ = 0.00, Jeffreys 95% CI **[0.00, 0.26]** |
| GO/NO-GO (pre-stated x≥5) | **NO-GO** |
| CV of output tokens | Full 0.134 · Null 0.413 |
| Full-arm input tax | +28k cache-write tokens per epoch ≈ the skill payload, re-paid every epoch |
| Spend | ≈$6.17 (≈$0.77/pair), run total under the $10 cap |

Even the Jeffreys interval's UPPER bound (0.26) sits inside the
structurally-unmeasured region of the sizing table. The apparatus was clean
end-to-end — every number above was verified against the raw `.eval` logs
and the evidence database, not the runner's summary.

So across two screens and one paired run: **14/14 Null epochs at ceiling.**

## The registered finding

On well-specified, self-contained, offline-checkable tasks — which is
precisely the class that leak-auditable, sandbox-scorable benchmarks admit —
a stock frontier agent needs no help. The Null arm sits at ceiling, d → 0,
and Full-vs-Null is **structurally UNMEASURED regardless of budget**. This
is a property of the task class crossed with frontier-model capability, not
an apparatus defect and not a property of the particular skill.

Two consequences, both registered:

1. **The task-sourcing condition.** A sized benefit run under this
   registration launches only from a task source where the Null arm
   demonstrably fails (p0 < 1 on a Stage-0 screen) — in practice,
   real-workload tasks with the ecological context, underspecification, or
   scale that a self-contained synthetic cannot carry.
2. **UNMEASURED is a first-class verdict.** A skill whose home domain only
   presents ceiling-class tasks gets UNMEASURED, published as such — not a
   fabricated win on a task the model didn't need help with.

## Why you should care if you publish skill benchmarks

The failure mode this protects against is not "no result." It is a fake
positive: pick a task the model can ace, observe both arms pass, and report
"no benefit" — or worse, pick a slightly leaky task and report a win that is
really the skill's own text echoing through the prompt (see
[`why-naive-skill-benchmarks-mislead.md`](../findings/why-naive-skill-benchmarks-mislead.md)
for the catalogue, including the oracle that leaked its own gold fix through
a test docstring). The double-ceiling result says the honest default for
most well-specified synthetic tasks against a frontier model is: **the
contrast carries no information either way.** Any benchmark that reports a
skill effect on such a task owes you its Null-arm pass rate first.

That is why the skill collection this harness feeds
([MrBinnacle/skills](https://github.com/MrBinnacle/skills)) carries
per-skill `EVIDENCE.md` records with the Null-arm screen result (p0) as a
required field, UNMEASURED spelled out where it holds, and a re-screen
trigger on each major model release — a trap today's model no longer falls
into gets publicly retired. Model progress becomes collection content
instead of collection rot.

## Provenance

All numbers registered in
[`docs/findings/v0.2-preregistration.md`](../findings/v0.2-preregistration.md)
(results section + Amendment 1). Raw `.eval` logs and the evidence store are
local to the operator (publishing gold implementations would contaminate
future evals — the C3 rule from the findings doc). Runs 2026-07-09/10;
subject `claude-sonnet-5`; agent Claude Code 2.1.197; total arc spend ≈$8.

> **Amendment (2026-08-02).** The Stage-0 screen records behind this case
> study are ledgered per-record in
> [`docs/observations/`](../observations/README.md) with machine-parseable
> front-matter and a classification state of DEFERRED (re-scoping semantics:
> [#41](https://github.com/MrBinnacle/skill-harness/issues/41)). The ledger is
> canonical for per-record counts; the history above is unchanged.
