# T3 Tracer Round — Pre-Registration

**STATUS: PRE-REGISTERED (PHASE A.5 amendment landed)**

This document is committed BEFORE any GPT-5 subject call has been made.
Peeking-immunization per `bayesian-eval-discipline` skill: PHASE A (and PHASE
A.5) commits must precede PHASE B's first `skill-harness run ablation` call.
This file is the timestamped commitment.

**PHASE A.5 amendment (2026-06-08)**: The subject route changed from direct
OpenAI (`gpt-5.5`) to OpenRouter (`openai/gpt-5.5`) after the PM disclosed
they hold `OPENROUTER_API_KEY`, not `OPENAI_API_KEY`. The OpenAI SDK is reused
as an OpenAI-compatible gateway client — no new SDK to audit; the
PROCEED-WITH-MITIGATIONS supply-chain decision carries. **No live run has
occurred between PHASE A and this amendment; peeking-immunization preserved.**
The falsification condition (below) is unchanged — it predicts a $0.00 / zero-
subject-call outcome that the routing layer cannot affect (BLOCKER-1 fires
before any subject call is issued).

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
| Harness HEAD (PHASE A commit on main) | `2a6141d` |
| Harness HEAD (PHASE A.5 commit on main) | `<to be filled after cherry-pick lands>` |
| Extractor model | `claude-sonnet-4-6` (HELD CONSTANT — subject-invariant requirement) |
| Subject model (gateway id) | `openai/gpt-5.5` (OpenRouter routing; see PHASE A.5 selection below) |
| Subject route | OpenRouter (`https://openrouter.ai/api/v1`); OpenAI SDK as OAI-compatible client |
| API key env var | `OPENROUTER_API_KEY` (PM-confirmed at Windows User scope, inherited at Process scope) |
| Cost-source provenance | Records `cost_source ∈ {openrouter_response, local_estimate}` on every call (A41) |
| PYTHONHASHSEED | `0` |
| PYTHONUTF8 | `1` |
| N_min | `8` |
| max_usd | `$5.00` |
| Baseline (Claude subject) | `docs/dogfooding-ai-slop-sentinel-2026-06-07.md` |

### PHASE A.5 OpenRouter model selection: openai/gpt-5.5

**Discovery method**: queried `GET https://openrouter.ai/api/v1/models` with
the OpenRouter key at 2026-06-08; filtered for `openai/gpt-5*` and sorted by
`created` timestamp (most recent first).

**Available `openai/gpt-5*` ids on OpenRouter (top candidates)**:

| OpenRouter id | name | created (Unix) | context |
|---|---|---|---|
| `openai/gpt-chat-latest` | GPT Chat Latest | 1778000212 | 400000 |
| `openai/gpt-5.5-pro` | GPT-5.5 Pro | 1777051896 | 1050000 |
| `openai/gpt-5.5` | GPT-5.5 | 1777051893 | 1050000 |
| `openai/gpt-5.4` (and -nano/-mini/-pro) | GPT-5.4 series | 177274... | 400000-1050000 |
| `openai/gpt-5.1` (and -codex variants) | GPT-5.1 series | 17630... | 128000-400000 |
| `openai/gpt-5-pro` | GPT-5 Pro | 1759776663 | 400000 |
| `openai/gpt-5` | GPT-5 | 1754587413 | 400000 |

**Selection**: `openai/gpt-5.5`.

**Rationale**:
- `openai/gpt-chat-latest` is a moving alias (rejected: not a stable, pinnable id;
  byte-stable JSON requirement of the pre-registration would be violated by alias
  drift between A.5 commit and PHASE B run).
- `openai/gpt-5.5-pro` is a higher-cost tier of the same generation (rejected:
  cost vs the selected flagship is ~6× input / ~6× output; falsification signal
  is identical at the routing-gate layer because BLOCKER-1 fires before any
  subject call, so the extra cost would buy no information).
- `openai/gpt-5.5` is the most-recent canonical OpenAI flagship and has the
  largest divergence from Claude's post-training stack of any pinnable id —
  the same selection rationale that PHASE A used for direct `gpt-5.5`. This
  preserves the Tier-2 memo's Q4 "most divergent → sharpest falsification
  signal" choice.
- Bare `openai/gpt-5` is older (August 2025) and superseded by gpt-5.5
  (March 2026). Selecting it would weaken the post-training-divergence
  argument relative to the Tier-2 memo's intent.

**Pricing (cited from OpenRouter `models` endpoint, 2026-06-08)**:
- `openai/gpt-5.5`: prompt $5.00/MTok, completion $30.00/MTok, cached input $0.50/MTok.
- Matches the direct-OpenAI pricing card cited in PHASE A's `_PRICE_PER_MTok`
  table; OpenRouter applies a per-provider margin on top. Live `usage.cost`
  from OpenRouter will be the authoritative value (`cost_source="openrouter_response"`).

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
   whether the subject is Claude or `openai/gpt-5.5` (via OpenRouter).

3. **Tier-2 uncalibrated**: per A7, calibration records are `(judge_id, axis)`
   pairs — subject-agnostic by spec. No calibrated judge exists for any of the
   17 axes.

---

## Peeking-immunization statement

This pre-registration commits BEFORE any GPT-5 subject call has been made.
The PHASE A.5 amendment (OpenRouter routing + model id rewrite) was made
BEFORE any GPT-5 subject call has been made. The falsification condition
above is the COMMITTED prediction. If any deviation from the expected vector
is observed in PHASE B, it must be reported verbatim in
`docs/dispatch/t3-findings.md` under "FALSIFIED-AT-<field>" — no post-hoc
reinterpretation of the pre-registered vector is permitted.

Per `bayesian-eval-discipline` skill: peeking at results before pre-registering
(or before pre-registration amendment) and then backdating the pre-registration
is a protocol violation. If that occurs, it must be disclosed in the findings
doc before any result is reported.

No such peeking has occurred at the time of this commit. Specifically:
- PHASE A commit `ed0e004` predated any subject API call.
- PHASE A.5 commit (this doc + code changes) predates any subject API call.
- No `skill-harness run ablation` invocation has been issued against any
  OpenRouter-routed subject between PHASE A and the PHASE A.5 commit.
