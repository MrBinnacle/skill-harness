# T3 Tracer Round — Pre-Registration

**STATUS: PRE-REGISTERED (PHASE A)**

This document is committed BEFORE any GPT-5 subject call has been made.
Peeking-immunization per `bayesian-eval-discipline` skill: PHASE A commit
must precede PHASE B's first `skill-harness run ablation` call. This file
is the timestamped commitment.

---

## Falsification condition (verbatim from Tier-2 EVAL-RESEARCH memo)

```
Expected vector (byte-stable):
  { passed: 0, failed: 0, confounded: 0,
    unmeasured: 17,
    unmeasured_breakdown: { no_data: 17 },
    coverage: 0.0 }
Expected cost: $0.00 (BLOCKER-1 fires before subject call)
Expected sample count: 0

Falsification (any of):
  - any non-zero PASSED/FAILED/CONFOUNDED
  - different unmeasured count (16, 18, etc.)
  - sub_reason other than no_data on any clause
  - any cost incurred (means a subject call escaped the gate)
  - different clause count from extractor (extractor variance, not subject variance)
  - non-byte-stable JSON across re-runs
```

---

## Run configuration

| Field | Value |
|---|---|
| Skill | `ai-slop-sentinel` |
| Skill source SHA | `074595b7a61821d4f0b80bf870b680d49326b27aab51e32e844d4e141607170b` (first 16: `074595b7a618...`) |
| Harness HEAD (PHASE A commit) | `<PLACEHOLDER — to be filled after commit>` |
| Extractor model | `claude-sonnet-4-6` (HELD CONSTANT — subject-invariant requirement) |
| Subject model | `gpt-5.5` (see disambiguation note below) |
| PYTHONHASHSEED | `0` |
| PYTHONUTF8 | `1` |
| N_min | `8` |
| max_usd | `$5.00` |
| Baseline (Claude subject) | `docs/dogfooding-ai-slop-sentinel-2026-06-07.md` |

### Model disambiguation: "gpt-5" -> gpt-5.5

The Tier-2 EVAL-RESEARCH memo specified "GPT-5" as the subject model. As of
2026-06-08 (this pre-registration date), OpenAI's production model portfolio
shows `gpt-5.5` as the current flagship model (API identifier: `gpt-5.5`).
There is no bare `gpt-5` identifier available in the API.

Per the dispatch brief "Halt-on-ambiguity" rule:

> If GPT-5 isn't the available model identifier, use the closest production
> OpenAI model and DOCUMENT which one in the findings doc + the pre-registration
> doc. Don't substitute models silently.

Selection rationale: `gpt-5.5` is documented as "A new class of intelligence
for coding and professional work" — the most recent flagship production model
with the most divergent post-training stack from Claude (OpenAI RLHF + DPO +
reasoning post-training). This satisfies the Tier-2 memo's Q4 rationale:
"most divergent post-training stack from Claude → sharpest falsification signal."

Alternative models considered: `gpt-5.4` (more affordable tier), `gpt-5.4-mini`
(smallest). These were not selected because `gpt-5.5` is the direct analog of
the "GPT-5" description in the Tier-2 memo.

---

## Generalization predictions (from Tier-2 memo Q1)

All three UNMEASURED mechanisms are subject-invariant by construction:

1. **BLOCKER-1 axis-mismatch**: fires before any subject call (framework property,
   independent of subject model). The check is `clause_spec.axis in self._scorers`
   — this is a lookup in the registered Tier-1 scorer dict, which does not vary
   with subject model.

2. **Meta-skill**: a property of the skill artifact, not the subject model.
   `ai-slop-sentinel` clauses are review directives, not behavioral instructions
   that produce subject-model-observable outputs. This is true regardless of
   whether the subject is Claude or GPT-5.5.

3. **Tier-2 uncalibrated**: per A7, calibration records are `(judge_id, axis)`
   pairs — subject-agnostic by spec. No calibrated judge exists for any of the
   17 axes.

---

## Peeking-immunization statement

This pre-registration commits BEFORE any GPT-5 subject call has been made.
The falsification condition above is the COMMITTED prediction. If any deviation
from the expected vector is observed in PHASE B, it must be reported verbatim
in `docs/dispatch/t3-findings.md` under "FALSIFIED-AT-<field>" — no post-hoc
reinterpretation of the pre-registered vector is permitted.

Per `bayesian-eval-discipline` skill: peeking at results before pre-registering
and then backdating the pre-registration is a protocol violation. If that
occurs, it must be disclosed in the findings doc before any result is reported.

No such peeking has occurred at the time of this commit.
