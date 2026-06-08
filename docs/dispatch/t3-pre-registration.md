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
| Harness HEAD (PHASE A.5 commit on main) | `9ab3d79` |
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

---

# PHASE B' — RE-PRE-REGISTRATION (2026-06-08)

**STATUS: SUPERSEDES the original "17 UNMEASURED / $0.00" prediction above.**

The original prediction was falsified at the PHASE B pre-flight check by a
scorer-registry drift that occurred BETWEEN the baseline dogfooding run
(`66510f9`, 2026-06-07 15:54 EDT) and the v0.1.0 tag (`fd782b1`, 2026-06-07
21:47 EDT). Full audit trail: `docs/dispatch/t3-findings.md` HALT report
(committed at `b7ba643` per dispatch context; the in-worktree equivalent is
`330bbce`). The original prediction's content is dead; the experimental
SHAPE is preserved here as a re-pre-registration.

## Re-pre-registered prediction (shape-level)

```
V_baseline_claude == V_baseline_gpt5  (byte-stable §16 vector equality)

Where:
  V_baseline_claude  = §16 vector from `run evaluate-skill` after running
                       ablation against claude-sonnet-4-6
  V_baseline_gpt5    = §16 vector from the SAME aggregation against
                       openai/gpt-5.5 (via OpenRouter)
  Run conditions held identical: same skill_id (source-SHA-stable),
                       same extractor (claude-sonnet-4-6),
                       same Tier-1 scorer registry (5-scorer set),
                       same N_min=8, same max_usd=$5, same PYTHONHASHSEED=0.

Pre-registered field-level expectations:
  passed       : V_baseline_claude.passed       == V_baseline_gpt5.passed
  failed       : V_baseline_claude.failed       == V_baseline_gpt5.failed
  confounded   : V_baseline_claude.confounded   == V_baseline_gpt5.confounded
  unmeasured   : V_baseline_claude.unmeasured   == V_baseline_gpt5.unmeasured
  coverage     : V_baseline_claude.coverage     == V_baseline_gpt5.coverage
  unmeasured_breakdown:
                 V_baseline_claude.unmeasured_breakdown
                 == V_baseline_gpt5.unmeasured_breakdown

CONTENT of the vectors is UNKNOWN until PHASE C+D runs; the COMPARISON
(shape-level byte-equality) is the pre-registered prediction. We are not
predicting a specific number; we are predicting that two subjects under
identical (skill, extractor, registry, constraints) produce identical §16
vectors.
```

## Falsification condition

Any field-level inequality between V_baseline_claude and V_baseline_gpt5
falsifies the prediction. Per-mechanism analysis in the findings doc will
distinguish between:

- **Tier-1 path divergence** (mechanical, deterministic; SHOULD be byte-
  stable if confound monitoring + scorer code are subject-invariant).
  Falsification on a Tier-1 clause = framework bug or scorer
  non-determinism.
- **Tier-2 path divergence** (judge-driven; subject-dependent BY DESIGN
  when a calibrated judge is available — though in v0.1 no calibrated
  judge exists for these axes, so Tier-2 clauses currently produce
  `UNMEASURED(tier2_uncalibrated)` regardless of subject).
- **Confound-monitoring divergence** (the Null accumulator's sigma
  depends on subject-model outputs; clauses sitting near the confound
  threshold may flip admissible/inadmissible across subjects). This is
  a known second-order subject-dependence.
- **Sample-count divergence** (sequential stop fires at different N for
  different subjects; this is expected and is NOT a falsifying field
  unless it changes the verdict).

## Confounders to control (PHASE B' re-pre-registration)

Held constant:
- **Extractor model**: `claude-sonnet-4-6` (CRITICAL — extractor is the
  shared input; both subjects evaluate the SAME extracted clause set).
- **Skill source SHA**: `074595b7a618...` (must match for both runs;
  HALT if not).
- **Scorer registry**: 5 scorers
  `{verbosity, hedge_index, structure_score, compliance_proxy,
   citation_presence_per_flag}` (HALT if drift again).
- **PYTHONHASHSEED**: `0`.
- **N_min**: `8`. **N_max**: framework default. **max_usd**: `$5.00`.
- **Harness HEAD**: a single commit (no harness changes between PHASE C
  and PHASE D runs).

Allowed to vary:
- **subject_model**: `claude-sonnet-4-6` (PHASE C) vs `openai/gpt-5.5`
  (PHASE D).
- **cost_source**: `local_estimate` for Anthropic; `openrouter_response`
  for OpenRouter (this is provenance, not a comparison axis).

## Peeking-immunization for PHASE B'

This re-pre-registration commits BEFORE the first PHASE C `skill init`
or `run ablation` invocation. The two ablation runs (PHASE C Claude,
PHASE D GPT-5) will be executed AFTER this commit lands. The §16
vectors will be compared in the findings doc; the COMPARISON itself is
the test.

No subject API call against either subject has been issued at the time
of this commit. The HALT findings doc (committed in PHASE B) reported a
pre-flight check on framework state, not a peek at any result.

The order of operations is locked:
1. This re-pre-registration lands first (this commit).
2. PHASE C runs (Claude baseline at corrected registry).
3. PHASE D runs (GPT-5 cross-vendor).
4. Findings doc appended with both vectors + comparison + disposition.
5. Single cohesive commit for PHASE B' contains: this re-pre-registration
   AS WELL AS the findings-doc updates. (Per dispatch brief: "single
   cohesive commit at end. Subject: `docs(t3-findings): PHASE B' —
   Claude baseline + GPT-5 cross-vendor at corrected registry`.")

That single commit's tree captures the pre-registration BEFORE the
findings, but BOTH ride in one commit. The audit-trail discipline is
preserved by the fact that no subject call could have informed this
re-pre-registration (the pre-flight HALT was structural; no subject
output existed to peek at).
