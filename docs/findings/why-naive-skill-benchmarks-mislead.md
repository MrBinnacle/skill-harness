# Why naive skill benchmarks mislead

**Status:** findings record, 2026-07. Empirical basis: a five-day measurement arc run by
this repo's author against a live 75-skill Claude Code setup — a 4-arm configuration
ablation (full setup / skills-only / CLAUDE.md-only / blank) over deterministic
pass/fail coding tasks (60 pre-registered trials + a 16-trial follow-up, Opus-class
subject model), plus an expert-council methodology review. Each claim below carries its
evidence grade. This document exists because the failure modes it records are now
common practice: with-skill vs without-skill benchmarking is widely recommended, usually
at k≈3 repetitions, with none of the traps below controlled.

**Grades:** `MEASURED` = produced under pre-registered/audited conditions ·
`MECHANISM` = verified by argument at mechanism level + independent expert concurrence ·
`DIRECTIONAL` = trust the direction, not the magnitude · `EXPLORATORY` = from a
construct-invalid instrument; illustrates, never decides.

---

## 1. The noise floor: what k=3 can actually detect  `MEASURED`

Run-to-run output-token variation on *identical* agentic coding tasks measured
**CV ≈ 17.6% (RMS across cells; mean-of-cells 14.6%, median 10.4%)** on an Opus-class
model, 60 trials. Two consequences:

- **A k=3 with/without comparison can only detect very large effects.** At CV 17.6%, a
  paired design's detectable effect scales as `t · CV·√2/√k / √n` — with k=3 and one task,
  differences under ~30–40% are indistinguishable from noise. Most published guides
  recommend exactly this design and then read small deltas as findings.
- **Beware pooled CV.** Pooling across tasks of different output scale produced an
  apparent 60% CV that was really between-task variance — the wrong input for a paired
  design (where task-mix variance cancels). Compute noise per (task, condition) cell.

Sizing rule of thumb from the measured CV: driving minimum-detectable-effect down to ~8%
(the size of real published skill effects) needs on the order of **n=20 tasks × k=5
repeats (~400 trials)** — not 3 runs. If you can't afford that, report direction and
abstain from magnitude claims.

## 2. Deterministic pass/fail tasks price the TAX, not the benefit  `MECHANISM` + `MEASURED` cost

The standing **cost** of always-loaded configuration is cheap to measure and real: in the
ablation, the full setup carried **≈ +17.8k prefix tokens into every turn** vs blank
(CLAUDE.md-only +6k, skills-only +7.4k; ~30% spread → `DIRECTIONAL` magnitude, ordering
reproduced on every run). Per-trial dollar cost ordered the same way on identical tasks.

The **benefit** is a different story. Knowledge-layer machinery (skills, memory, context
files) exists mostly for knowledge/orchestration work; deterministic bug-fix benchmarks
under-activate it. Across all 60 trials the hooks fired but no skill was invoked and
memory was never touched — the layers idled while their tax ran. A benchmark of this
shape therefore measures overhead and reports it as the verdict. An expert methodology
council reviewing the arc was unanimous: **no deterministic task bank can broadly price
the benefit of knowledge-layer configuration — only its cost.** Independent
corroboration from the positive side: skill benefit does appear on judge-graded,
long-horizon subjective tasks (LH-Bench, arXiv 2603.22744) — i.e., where the task class
actually exercises the layers.

## 3. Task–skill matching is sampling on the dependent variable  `MECHANISM`

The obvious fix — "pick a task the skill addresses, then compare with/without" — selects
the task *because* the treatment matches it. A positive result measures the planting, not
the skill. This is a common-cause confound built into the design, and it cannot be
patched by more repetitions.

## 4. Synthetic oracles self-leak their answers  `MEASURED` (transcript-verified)

The arc tested the matched-task design anyway, at its best: a real latent bug class,
hand-built into a real codebase, with a skill in the treatment arm that directly
addresses it. The run degenerated, and the transcript audit shows exactly how: **the
failing test's own docstring stated the gold fix verbatim** (good regression-test hygiene
documents the fix — which is answer-in-task for an eval). Every arm, including the
no-configuration control, read the test file before editing; all arms passed identically
at ~equal cost. The numbers are `EXPLORATORY` by construction — the durable finding is
the failure mode:

> **Oracle-authoring rule: an eval task's visible artifacts must never document their own
> fix.** Strip failing-test files to assertion-minimum — no design notes, no fix
> statements, no tool/skill names the subject can read. Verify with a transcript grep
> that the answer string does not appear in anything the subject opened.

This is why the harness in this repository requires falsifying cases and treats
"UNMEASURED" as the honest default rather than letting convenient tasks produce
convenient passes.

## 5. What actually works

- **Measure the cost side deterministically** — it's cheap, stable, and decision-relevant
  (prefix tokens/turn per configuration layer; reproducible with a 4-arm config ablation).
- **Measure the benefit side only with instruments that reach it:** judge-graded
  realistic tasks (pairwise, position-swapped, calibrated — see this repo's Tier-2
  design) or longitudinal observation of real usage. Pre-register the contrast, MDE,
  stopping rule, and task source before spending.
- **Gate the instrument like you'd gate a skill:** before building any harness/metric/
  oracle, run a prior-art sweep, confirm the question recurs, and name the pending
  decision the output would change. Every instrument in the source arc that skipped this
  gate was superseded or degenerated; every one that passed it survived.

## Provenance

Findings extracted from the author's skills-research project (private research repo;
graded ledger maintained there). The 4-arm ablation apparatus, pre-registration
discipline, and council-review records exist and are summarized here without private
identifiers. External replication is invited — the cost-side measurement (§2) is
reproducible for ~$70 of API spend on any Claude Code setup via `CLAUDE_CONFIG_DIR`
config roots.
