# A widely-used LLM review skill, evaluated honestly: 17 UNMEASURED, 0 PASSED

**A reproducible case study from Skill Harness v0.1.0.**

This is what happens when you try to actually measure whether the clauses in a popular AI review skill are doing what they claim. It is not a flattering result. It is the first one most LLM eval frameworks would have hidden behind a number.

## Setup

`ai-slop-sentinel` is a Claude Code skill that asks the assistant to review AI-generated code against a curated "watch" of AI-slop anti-patterns, citing the watch by entry for each flag. It is in active use. It has been refined over multiple sessions. By any conventional rubric it is "a good prompt."

We ran it through `skill-harness run evaluate-skill` on v0.1.0 with `claude-sonnet-4-6` as the subject model. The harness extracted 17 testable clauses, of which the extractor declared 7 as Tier-1 (mechanically scorable) and 10 as Tier-2 (judge-required). The full per-clause inventory and run metadata is in `docs/dogfooding-ai-slop-sentinel-2026-06-07.md`.

The Tier-1 axes declared by the extractor included things like `citation_presence_per_flag`, `watch_entry_metadata_completeness`, `flag_severity_classification_and_citation`, `review_gate_enforcement_coverage`. These are concrete, countable properties of a review output — exactly what you'd want a deterministic scorer to verify.

## What a conventional LLM eval framework would have reported

If you fed `ai-slop-sentinel` into the current generation of LLM eval tooling — pairwise preference judges, LMArena-style ELO, MT-Bench, G-Eval scalar scoring, or any number of "we asked GPT-4 to grade it" frameworks — you would get back a number. Probably something between 6.4 and 8.7 out of 10. The exact value would depend on the judge prompt, the rubric, and the eval framework's particular calibration choices. The number would feel real. It would be cited in a deck. Some of those frameworks would even attach a confidence interval.

None of those numbers would mean what they appear to mean.

The unstated assumption behind every scalar quality score is that the rater (whether human or LLM judge) was actually able to verify that the skill's clauses did the thing the clauses claim. For a skill like `ai-slop-sentinel`, where the clauses are domain-specific assertions about citation presence, severity classification, watch-entry currency, gate enforcement coverage — verifying any of these requires a mechanical procedure that can count, parse, or check the relevant property in the output. The judge LLM does not run that procedure. It pattern-matches. The resulting score is a function of how plausible the output looks, not whether the clauses are load-bearing.

This is a known problem in the LLM eval literature. It is rarely surfaced as the headline result.

## What Skill Harness reported

```json
{
  "passed": 0,
  "failed": 0,
  "confounded": 0,
  "unmeasured": 17,
  "unmeasured_breakdown": {"no_data": 17},
  "coverage": 0.0
}
```

Zero clauses passed. Zero failed. Zero confounded. **All 17 clauses came back UNMEASURED with sub_reason `no_data`.**

The run made zero subject-model API calls. Cost: $0.00. The harness refused to ablate any clause because none of the extracted axes matched a registered Tier-1 mechanical scorer. The four currently-registered Tier-1 scorers are `verbosity`, `hedge_index`, `structure_score`, and `compliance_proxy`. None of them are valid instruments for measuring `citation_presence_per_flag` or `flag_severity_classification_and_citation`. The harness recognized this, gated the run, and reported the result that was actually available to report: nothing.

## Why this is the honest answer

The honest answer to "does `ai-slop-sentinel` clause-by-clause do what it claims?" — given the current Tier-1 scorer registry — is "we don't know." Not "8/10." Not "67% confidence interval." We do not know, because we do not have the mechanical instruments to measure the things the clauses are actually claiming.

UNMEASURED is a first-class verdict in Skill Harness. It is not a synonym for failure. It is the verdict that means: the test that would discriminate between "this clause is load-bearing" and "this clause is decoration" was not run, because the necessary instrument does not exist in this version of the framework. Producing a number anyway — by handing the question to an LLM judge and asking for a vibe-score — would be lying about what was measured.

The harness was designed to refuse this lie. The Phase 4.4 dogfooding result is the first time it has refused it on a real, popular, actively-used skill. The result is exactly the result the discipline was built to produce. It is also exactly the result that would never appear in a conventional eval framework's output, because conventional eval frameworks have no representation for "we don't know."

## What this implies about the rest of the field

`ai-slop-sentinel` is not unusual. Most LLM-prompted skills currently deployed in production carry domain-specific axes (citation correctness, claim grounding, severity classification, rubric adherence) that are not measurable by any registered mechanical scorer in any current eval framework. The standard pattern is to score them anyway — with a holistic judge, a pairwise preference, or a scalar rubric — and report the number as if it were evidence about the clauses.

Under Skill Harness's discipline, most of those numbers should be UNMEASURED. The fact that they are not is a property of the framework producing them, not the artifact being measured.

This is not a claim that other eval frameworks are useless. They measure something. The honest thing to say is that what they measure is "does the output look plausible to a judge with this rubric." That is not "do the clauses contribute load-bearing structure." The two questions can produce wildly different answers on the same artifact. The field has not been careful about distinguishing them.

Skill Harness's contribution is the refusal to conflate them.

## Reproducibility

This case study is reproducible by anyone with the v0.1.0 tag. The full instructions are in the project README. The summary:

```bash
git clone https://github.com/MrBinnacle/skill-harness
cd skill-harness && git checkout v0.1.0
# install per README env recipe
$py = ".venv/Scripts/python.exe"
$env:PYTHONHASHSEED = 0; $env:PYTHONUTF8 = 1
$env:PYTHONPATH = "src"
& $py -m skill_harness init <path-to-ai-slop-sentinel-SKILL.md>
& $py -m skill_harness run ablation <skill_id> --execute
& $py -m skill_harness run evaluate-skill <skill_id>
```

You will get the same vector. `PYTHONHASHSEED=0` plus the BLOCKER-1 gate firing on all clauses means there is no sampling randomness in this particular run. Byte-stable JSON output is verified across re-runs.

The 17 axes the extractor produced are stochastic — re-extraction with the same source SHA may shift the clause count by 1-2. The UNMEASURED result is not stochastic.

## What this does not show

This case study does not show that `ai-slop-sentinel` is a bad skill. It might be a very effective skill. It almost certainly has clauses that meaningfully shape the output. We cannot prove that one way or the other without the Tier-1 scorers that would let us run the differential-ablation test honestly.

That asymmetry — between "we cannot prove it works" and "it does not work" — is exactly the asymmetry conventional eval frameworks erase. Skill Harness preserves it. Live with the discomfort or extend the scorer registry. Both are valid moves. Pretending the number is the answer is not.

## What would change this result

The result would change in one of two ways:

1. **Extend the Tier-1 scorer registry.** Implement mechanical scorers for the specific axes the extractor produces — `citation_presence_per_flag` is a counted property of the output; `watch_entry_metadata_completeness` is a schema check; `flag_severity_classification_and_citation` is a label parser. Each of these is a finite, well-defined piece of code. Once a scorer is registered, the gate opens and the harness will run the ablation honestly.
2. **Calibrate a Tier-2 judge for the relevant axes.** Per the framework's discipline, a Tier-2 LLM judge is admissible only after it passes a calibration audit against a labeled set: position-swap agreement ≥0.7, position consistency ≥0.8, on ≥50 pairs per axis. No calibrated judge exists for these axes today. One could exist.

The first move is faster and produces more durable infrastructure. The second move scales to axes that resist mechanical scoring. Both are legitimate paths.

What is not a legitimate path: handing the question to an uncalibrated judge and reporting the number as if it were evidence. That is the path the field is currently on.

---

*Reproducible artifact: Skill Harness v0.1.0 · tag `v0.1.0` · `f99649d` · 2026-06-07. Raw run metadata at `docs/dogfooding-ai-slop-sentinel-2026-06-07.md`. PRD specification at `PRD.md` v1.1. Council-adopted invariants at `docs/COUNCIL_FINDINGS.md` A1-A62.*

*Questions, reactions, refutations welcome. The discipline this case study describes is falsifiable by construction; the artifact is the test.*
