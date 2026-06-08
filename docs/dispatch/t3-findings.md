# T3 Tracer Round — Findings

**STATUS: HALTED-AT-SCORER-REGISTRY-DRIFT (PHASE B step 1)**

PHASE B was halted at step 1 (scorer-registry drift check) BEFORE any subject
API call. No `skill init` or `run ablation` invocation occurred against the
OpenRouter-routed GPT-5.5 subject. Total subject API cost: **$0.00**.

---

## Pre-registered vector (verbatim from `t3-pre-registration.md`)

```
Expected vector (byte-stable):
  { passed: 0, failed: 0, confounded: 0,
    unmeasured: 17,
    unmeasured_breakdown: { no_data: 17 },
    coverage: 0.0 }
Expected cost: $0.00 (BLOCKER-1 fires before subject call)
Expected sample count: 0
```

## Observed vector

**Not produced.** PHASE B was halted at the registry-drift pre-flight check
before any extraction or ablation was issued.

---

## Halt reason: scorer registry has drifted since the baseline dogfooding run

Per the dispatch brief PHASE B step 1:

> Verify scorer registry has not drifted since v0.1.0. Compare current Tier-1
> scorer registration count + names against the ai-slop-sentinel dogfooding doc
> (`docs/dogfooding-ai-slop-sentinel-2026-06-07.md` line 76 —
> "verbosity, hedge_index, structure_score, compliance_proxy"). If different,
> HALT and report — the comparison to the case study is no longer valid.

**Comparison result**: the registry HAS changed.

| State | Tier-1 scorer set | Source |
|---|---|---|
| Baseline (dogfooding run, commit `66510f9`, 2026-06-07 15:54 EDT) | `{verbosity, hedge_index, structure_score, compliance_proxy}` (4 scorers) | `docs/dogfooding-ai-slop-sentinel-2026-06-07.md` line 76 |
| v0.1.0 tag (commit `fd782b1`, 2026-06-07 21:47 EDT) | `{verbosity, hedge_index, structure_score, compliance_proxy, citation_presence_per_flag}` (5 scorers) | `git show v0.1.0:src/skill_harness/ablation/confound.py` |
| Current (commit `c8b2e3a`, 2026-06-08) | `{verbosity, hedge_index, structure_score, compliance_proxy, citation_presence_per_flag}` (5 scorers) | `python -c "from skill_harness.ablation.confound import get_default_tier1_scorers; print(sorted(get_default_tier1_scorers().keys()))"` |

The `citation_presence_per_flag` scorer was added between the baseline
dogfooding run (`66510f9` at 15:54 EDT) and the v0.1.0 tag (`fd782b1` at
21:47 EDT) on 2026-06-07. The introducing commits are:

- `3f6b0a9` ("fix(pretag): council BLOCKER + MAJOR + MINOR fix-sprint", 2026-06-07 16:45 EDT)
- `4583669` ("fix(oracles/tier1): rescue scorer-add agent's flag-regex refinement", 2026-06-07 20:48 EDT)

---

## Why this invalidates the pre-registered vector

The pre-registered falsification condition (17 UNMEASURED, all `no_data`,
$0.00 cost) was derived from the Tier-2 EVAL-RESEARCH memo's Q1 prediction.
That prediction was anchored on the dogfooding doc's report that BLOCKER-1
fires for ALL 17 clauses because NONE of the extracted axes match any
registered Tier-1 scorer.

But clause 0's axis (per the dogfooding inventory table) is exactly
`citation_presence_per_flag`. With this scorer NOW registered:

- BLOCKER-1 (`clause_spec.axis in self._scorers`) will **NOT** fire for clause 0.
- Clause 0 will reach the sampling loop and issue subject API calls (Full,
  Ablated, Null at N_min=8 → at least 24 subject calls if confound monitoring
  doesn't pre-empt).
- The expected vector shifts from `17 UNMEASURED / $0.00` to at-most
  `16 UNMEASURED / clause-0 measured / non-zero cost`.

Running PHASE B with the original pre-registered vector intact would
mechanically falsify the prediction not because of subject-model variance
(the thing the experiment is designed to test) but because of a known
framework change introduced after the baseline run. That is **the
confounder the dispatch brief specifically instructed us to halt on**.

---

## Why this is not a peeking violation

No subject API call was issued. No ablation run was started. No extraction
was performed. The halt-at-pre-flight check is a structural property of the
framework state (the contents of `get_default_tier1_scorers()`) — it is not
a peek at any result.

Peeking-immunization remains intact: the pre-registered vector at
`docs/dispatch/t3-pre-registration.md` (commits `1e09119` + `c8b2e3a`) is
the COMMITTED prediction. This findings doc reports HALT without observing
any subject-model output.

---

## Subject route confirmation (PHASE A.5 wiring verified, not exercised)

The PHASE A.5 OpenRouter routing is built and tested but was not exercised
against a live subject. The configuration that would have been used:

| Field | Value |
|---|---|
| Subject model id | `openai/gpt-5.5` |
| Route | OpenRouter (`https://openrouter.ai/api/v1`) |
| API key env var | `OPENROUTER_API_KEY` (confirmed PRESENT at PHASE B entry) |
| Cost-source provenance field | `cost_source` ∈ {`openrouter_response`, `local_estimate`} (A41) |

OpenRouter `/models` endpoint was queried at PHASE A.5 build time (2026-06-08)
to confirm `openai/gpt-5.5` is a registered, pinnable model id with the
expected pricing card. **No `chat.completions.create` call was issued.**

---

## Disposition: HALTED-AMBIGUITY

Per the dispatch brief output contract: `HALTED-AMBIGUITY`.

The pre-registered prediction is no longer testable against the current
harness state. To proceed with a meaningful tracer round, the orchestrator
must choose one of three paths:

1. **Re-run the baseline dogfooding** at the current harness HEAD (with
   the 5-scorer registry) using Claude as subject. The new baseline will
   produce a vector with at-most 16 UNMEASURED and at-least 1 measured
   clause. Re-pre-register the falsification condition against THAT vector
   before running GPT-5.5 (still subject-invariant by the same Q1 argument).
2. **Pin the harness to commit `66510f9`** (baseline state) for the tracer
   round only, then run the existing pre-registration against GPT-5.5.
   Preserves the original prediction at the cost of running against
   pre-tag code.
3. **Revise the Tier-2 memo Q1** to acknowledge the registry drift and
   adopt a stricter generalization claim ("BLOCKER-1 / meta-skill /
   Tier-2-uncalibrated are subject-invariant FOR clauses whose axis is
   NOT in the registered Tier-1 scorer set"). This is the framework-
   honest claim; the original was framework-state-dependent without
   saying so.

The orchestrator is the appropriate seat to choose among these — each
path has different cost/discipline tradeoffs that are scope/values
decisions, not implementation decisions.

---

## Raw artifacts

### Verification command + output

```
$ PYTHONHASHSEED=0 PYTHONUTF8=1 PYTHONPATH="$PWD/src" python -c "
from skill_harness.ablation.confound import get_default_tier1_scorers
scorers = get_default_tier1_scorers()
names = sorted(scorers.keys())
print('Tier-1 scorers registered:', names)
expected = sorted(['verbosity', 'hedge_index', 'structure_score', 'compliance_proxy'])
print('Expected (from docs/dogfooding-ai-slop-sentinel-2026-06-07.md line 76):', expected)
print('Match:', names == expected)
"
Tier-1 scorers registered: ['citation_presence_per_flag', 'compliance_proxy', 'hedge_index', 'structure_score', 'verbosity']
Expected (from docs/dogfooding-ai-slop-sentinel-2026-06-07.md line 76): ['compliance_proxy', 'hedge_index', 'structure_score', 'verbosity']
Match: False
```

### Git history confirming when the scorer was added

```
$ git log --oneline -- src/skill_harness/oracles/tier1/citation_presence_per_flag.py
4583669 fix(oracles/tier1): rescue scorer-add agent's flag-regex refinement (session-limit recovery)
3f6b0a9 fix(pretag): council BLOCKER + MAJOR + MINOR fix-sprint (cp1252, pythonhashseed, axis-warn, coverage_warnings, sub_reason bridge, wire-version triangulation, docs)

$ git log -1 --format="%H %ai %s" 66510f9
66510f946151571ffe54e17565d281b3401cbddc 2026-06-07 15:54:01 -0400 docs(phase-4-4): dogfood ai-slop-sentinel — [0 passed / 0 failed / 17 unmeasured / cov 0%]

$ git log -1 --format="%H %ai %s" v0.1.0^{}
fd782b1... 2026-06-07 21:47:40 -0400 docs(prd): flip Status Draft -> Ratified for v0.1.0 tag
```

### Pricing card cited at PHASE A.5 build time (not exercised)

```
$ curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/models | jq '.data[] | select(.id == "openai/gpt-5.5") | {id, pricing}'
{
  "id": "openai/gpt-5.5",
  "pricing": {
    "prompt": "0.000005",
    "completion": "0.00003",
    "web_search": "0.01",
    "input_cache_read": "0.0000005"
  }
}
```
