# T3 Tracer Round — Findings

**CURRENT STATUS: HALTED-AT-ENVIRONMENT-COMPOUNDING-MISMATCH (PHASE B' pre-flight).**
**Prior status: HALTED-AT-SCORER-REGISTRY-DRIFT (PHASE B step 1).**

Each phase's HALT is preserved as part of the audit trail; the current
status reflects the most-recent halt (PHASE B'). The earlier HALT (PHASE B
on registry drift) led to a re-pre-registration; the PHASE B' re-pre-
registered experiment then encountered a separate set of pre-flight
mismatches and halted in turn.

Total subject API cost across PHASE A + A.5 + B + B' (all phases of T3
to date): **$0.00**.

---

## PHASE B — registry-drift halt (original; preserved as audit trail)

**STATUS: HALTED-AT-SCORER-REGISTRY-DRIFT (PHASE B step 1)**

PHASE B was halted at step 1 (scorer-registry drift check) BEFORE any subject
API call. No `skill init` or `run ablation` invocation occurred against the
OpenRouter-routed GPT-5.5 subject. Total subject API cost (this phase): **$0.00**.

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

---

# PHASE B' — Re-baseline + cross-vendor attempt (2026-06-08)

**STATUS: HALTED-AT-ENVIRONMENT-COMPOUNDING-MISMATCH (pre-flight before live calls)**

PHASE B' was halted at the environment + harness-state pre-flight check
BEFORE any subject API call. The re-pre-registration commit landed first
(`267858d`), preserving peeking-immunization. No `skill init`, no `run
ablation`, no subject-model output was observed in PHASE B'. Total subject
API cost across PHASE B + PHASE B': **$0.00**.

## Re-pre-registration (verbatim, committed at `267858d`)

```
Predicted shape:
  V_baseline_claude == V_baseline_gpt5  (byte-stable §16 vector equality)

Where V_baseline_claude and V_baseline_gpt5 are §16 vectors from the SAME
aggregation against claude-sonnet-4-6 and openai/gpt-5.5 (via OpenRouter)
respectively, under identical (skill_id, extractor, scorer registry,
N_min=8, max_usd=$5, PYTHONHASHSEED=0).

Falsification: any field-level inequality between the two vectors.
```

Full text at `docs/dispatch/t3-pre-registration.md` under "PHASE B' —
RE-PRE-REGISTRATION (2026-06-08)".

## Halt reason: compounding environment + framework-state mismatches

The dispatch brief's PHASE C+D plan assumed three preconditions that turn
out NOT to hold. Each, in isolation, would be a soft adaptation; together
they exceed the dispatch brief's adaptation budget and require orchestrator
direction.

### Mismatch 1: `ANTHROPIC_API_KEY` is absent; PM has `OPENROUTER_API_KEY` only

```
$ env | grep -iE "ANTHROPIC|OPENROUTER" | head -10
setx=ANTHROPIC_API_KEY                   # malformed entry; literally a name with no value
OPENROUTER_API_KEY=sk-or-v1-...          # the only routable LLM key
```

The PHASE B' dispatch brief's PHASE C step 3 specifies:
```
skill-harness run ablation <skill_id_C> --execute --max-usd 5 --subject-model claude-sonnet-4-6
```
This invokes the direct-Anthropic `AnthropicSubjectClient` path, which
calls `anthropic.Anthropic()` and reads `ANTHROPIC_API_KEY`. With no key,
the SDK constructor raises and the run aborts before any sampling.

PHASE A.5 already authorized OpenRouter routing as a general pivot
("PM has `OPENROUTER_API_KEY` (not OpenAI direct), confirmed SET").
The symmetric move for Claude exists in the harness:
```
make_subject_client("anthropic/claude-sonnet-4.6")
# returns OpenAISubjectClient(model="anthropic/claude-sonnet-4.6",
#                             base_url="https://openrouter.ai/api/v1")
```
This was VERIFIED in the worktree (and the underlying OpenRouter `/models`
query confirms `anthropic/claude-sonnet-4.6` is a registered, pinnable
id with 1M context). Same Anthropic Sonnet 4.6 model identity, different
gateway. Subject-call output equivalence vs the original direct-API
dogfooding has NOT been verified empirically — OpenRouter is intended as
a pass-through proxy but introduces a deterministic-equivalence question
that the original PHASE B' pre-registration did not anticipate.

### Mismatch 2: the CLI does not expose `--subject-model`

```
$ skill-harness run ablation --help | grep -i subject
(no match — flag does not exist)
```

The CLI hard-codes `SubjectClient()` (= `AnthropicSubjectClient`) inside
`src/skill_harness/cli/main.py:_execute_ablation_run`. The library-level
`AblationRunner` and `make_subject_client` factory DO accept a `subject_model`
parameter (PHASE A wired this), so a driver script that invokes
`AblationRunner.run_ablation(subject_model=...)` directly works around the
CLI surface gap. This is the dispatch brief's implicit assumption (the
brief command requires a flag that doesn't exist on the CLI surface).

Writing a driver script is using the library as-intended (not adding new
surface), so this mismatch alone is within docs-only adaptation budget.

### Mismatch 3: pre-existing `evidence.db` state blocks `aggregate_skill`

A pre-existing `evidence.db` exists in the main checkout (`./evidence.db`)
that holds the ai-slop-sentinel skill_id `074595b7a61821d4...` with **15
clauses** (note: the dogfooding doc reported 17; the extractor is stochastic
on the same source SHA per its own footnote). It also holds **8 prior
ablation runs**, of which **5 are incomplete** (`completed_at IS NULL`)
and 3 are completed.

```
=== runs ===
incomplete (5): 9b6a4700, 079486b3, 87d4d01b, 6827b0b2, de2c037e
completed  (3): 19e85593, c3481f27, 073dd0da
```

`aggregate_skill` (`src/skill_harness/aggregation/engine.py:54`) enforces:

> "any incomplete runs for skill_id → PreconditionError('incomplete_runs',
>  [run_ids])"

So `skill-harness run evaluate-skill <skill_id>` will raise on this
evidence.db until the 5 incomplete runs are resolved (either completed
via resume, or excluded via a hypothetical filter that does not exist).
Aggregation across runs is also skill-wide — there's no built-in
per-run_id aggregation, contrary to the dispatch brief's suggestion
("query the runs table for the GPT-5 run_id specifically and aggregate
over just that run"). Doing this cleanly requires a custom aggregator,
which is code work, not docs work.

The alternative — starting fresh with an empty evidence.db — requires
`skill init` (extraction), which requires `ANTHROPIC_API_KEY` (Mismatch 1).
There is no extractor route through OpenRouter; the extractor uses
Anthropic's tool-calling API path directly.

## Net: PHASE C cannot be executed under the dispatch brief's parameters without:

1. Either an `ANTHROPIC_API_KEY` (orchestrator-provided), OR explicit
   authorization to route Claude via OpenRouter (`anthropic/claude-sonnet-4.6`)
   on the assumption it's a deterministic pass-through (load-bearing
   assumption that has not been verified).
2. A driver script bypassing the missing CLI flag (within docs-only adaptation
   budget; can write).
3. EITHER a clean `evidence.db` (requires extractor, requires ANTHROPIC_API_KEY)
   OR completion/exclusion of the 5 incomplete prior runs in
   `evidence.db` (requires a NON-trivial framework decision —
   `aggregate_skill`'s precondition is load-bearing per A50/A53)
   OR a custom per-run_id aggregator (code work, outside docs-only scope).

Each path has a different load-bearing assumption the orchestrator has
explicit authority over. None can be silently chosen.

## Subject route confirmation (PHASE A.5 wiring still verified, not exercised)

PHASE A.5 OpenRouter routing remains built and tested. No subject call
has been issued at any point in T3 (PHASE A → PHASE A.5 → PHASE B HALT
→ PHASE B' re-pre-registration → PHASE B' HALT). Total subject API
cost across all phases: **$0.00**.

`anthropic/claude-sonnet-4.6` factory dispatch verified in-worktree:
```
$ PYTHONHASHSEED=0 PYTHONPATH="$PWD/src" python -c "
from skill_harness.ablation.subject import make_subject_client
c = make_subject_client('anthropic/claude-sonnet-4.6')
print('class:', type(c).__name__)
print('model:', c._model)
print('base_url:', c._base_url)
"
class: OpenAISubjectClient
model: anthropic/claude-sonnet-4.6
base_url: https://openrouter.ai/api/v1
```

OpenRouter `/models` listing for the two pre-registered subject IDs:
```
openai/gpt-5.5            created=1777051893 ctx=1050000  prompt $5.00/MTok  completion $30.00/MTok
anthropic/claude-sonnet-4.6 created=1771342990 ctx=1000000 (pricing not queried; live cost will record via cost_source)
```

## PHASE C results — Claude baseline at corrected registry

**Not produced.** PHASE B' halted at pre-flight before any extraction or
ablation could run.

## PHASE D results — GPT-5 cross-vendor

**Not produced.** PHASE B' halted at pre-flight before any extraction or
ablation could run.

## Comparison

Not applicable.

## Disposition

**HALTED-AT-ENVIRONMENT-COMPOUNDING-MISMATCH.**

## Recommended forward paths (research-and-recommend; final call belongs to orchestrator)

These are surfaced for orchestrator decision, ranked by minimum framework
risk:

### Path R1 — Route Claude via OpenRouter, write a driver script, use a fresh evidence.db (requires extractor work)

- Authorize `anthropic/claude-sonnet-4.6` (via OpenRouter) as the PHASE C
  subject. Document the assumption "OpenRouter is a deterministic
  pass-through for Anthropic models" with a one-off byte-equivalence
  spot-check against a single known direct-Anthropic call IF an
  ANTHROPIC_API_KEY can be borrowed for the spot-check (otherwise this
  assumption rides as an explicit limitation in the findings).
- Write a driver script that calls `AblationRunner.run_ablation(
  subject_model=...)` directly (library use; not new surface).
- Use a fresh evidence.db (no pre-existing run pollution). REQUIRES
  extractor → requires ANTHROPIC_API_KEY → so this path needs orchestrator
  to provide an ANTHROPIC_API_KEY for the extractor step ONLY. The two
  subject ablation runs themselves stay on OpenRouter.

**Pro**: cleanest experimental state; honors the re-pre-registration
shape literally. **Con**: requires orchestrator to provide
ANTHROPIC_API_KEY for one extractor call.

### Path R2 — Route Claude via OpenRouter, reuse the existing skill_id, complete or filter incomplete runs

- Authorize OpenRouter for Claude (same as R1).
- Reuse the existing skill_id `074595b7a618...` (15 clauses) from the
  main checkout's evidence.db (copied into the worktree).
- Resolve the 5 incomplete prior runs by either: (a) running `resume`
  on each until completion, or (b) marking them as aborted in a
  documented one-off mutation.

**Pro**: no ANTHROPIC_API_KEY required (since OpenRouter routes both
subjects). **Con**: the prior 3 completed runs ALSO get aggregated
into the §16 vector, contaminating the per-subject comparison unless
a custom per-run_id aggregator is built. Building that aggregator is
code work, not docs work.

### Path R3 — Provide ANTHROPIC_API_KEY, re-fire the original PHASE B' dispatch

- PM exports `ANTHROPIC_API_KEY` to env.
- Original PHASE B' dispatch runs as-written, hitting direct Anthropic
  for Claude and OpenRouter for GPT-5. Asymmetric routing (different
  gateway per subject) is the only methodological note.

**Pro**: matches the dispatch brief literally; minimal adaptation.
**Con**: asymmetric gateway is a less-controlled experiment than R1
(adds OpenRouter-as-confounder for GPT-5 only). And requires PM to
expose a key the worktree currently sees as ABSENT.

### Path R4 — Park PHASE B'; the registry-drift HALT discovery (PHASE B) stands as the headline

- Treat the registry-drift HALT as the deliverable; the PM has already
  authorized that the HALT discovery is the case study's headline (per
  the orchestrator's dispatch context).
- Skip PHASE C+D entirely. Future cross-vendor tracer rounds run with
  intact preconditions on a different experimental cycle.

**Pro**: zero additional adaptation; aligns with the orchestrator's
explicit framing ("the HALT discovery is the most interesting finding
of T3 so far"). **Con**: leaves the subject-invariance claim
empirically unverified; the next tracer round must re-establish it.

## Honest caveats

- The PHASE B' re-pre-registration's "byte-stable §16 vector equality"
  claim was always a strong prediction (Tier-1 mechanical scores are
  deterministic, but confound-monitoring + Null-accumulator interactions
  introduce subject-output-dependence). A byte-stable match would be
  STRONG evidence of subject-invariance; a non-match would still be
  diagnostic (per the falsification taxonomy in the re-pre-registration).
- The dispatch brief's per-run_id aggregation suggestion does not match
  the actual `aggregate_skill` API (which is skill-wide with an incomplete-
  run precondition). This is a discrepancy between the brief and the
  framework that the orchestrator may want to surface as a separate
  finding regardless of which forward path is chosen.

## Peeking-immunization confirmation

- PHASE A commit `ed0e004` — predated any subject API call (Anthropic
  or OpenAI/OpenRouter).
- PHASE A.5 commit `1e09119` — predated any subject API call.
- PHASE B HALT findings `330bbce` — pre-flight check on framework state;
  no subject output observed.
- PHASE B' re-pre-registration `267858d` — predates any subject API call.
- This PHASE B' findings update — written before any subject API call,
  predicts no further subject calls until orchestrator chooses a
  forward path.

The two pre-registrations (original at `ed0e004`/`1e09119`; revised at
`267858d`) and this HALT findings doc together preserve the audit trail
required to ratify a future PHASE C+D run under any chosen path.
