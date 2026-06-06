# COST seat — Pre-Track-C council (2026-06-05)

**Model**: Opus 4.7 (background subagent, ~238s, 199,044 tokens)
**Skills loaded** (per dispatch): `claude-api`, `bayesian-eval-discipline`, `llm-judge-calibration`

---

### Q1 · Tier-2 judge response shape

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: Of the four options, **tool_use forcing `report_verdict({choice, rationale_brief})`** is the right call on cost-adjusted determinism grounds. JSON mode is next-best alternative. Single-token sampled choice is forbidden under A5 — strips the rationale needed for audit. Plain text + regex is worst: zero deterministic guarantees, unbounded output tokens on judge "thinking out loud," brittle to prompt drift.
**Evidence**: Cost math for typical pair call at Sonnet 4.6:
- Skill text + 2 candidate outputs ≈ 2,000 input tokens (cacheable prefix + per-pair tail)
- Tool schema (~80 tokens) — cached
- Output: `choice` (~3 tokens) + `rationale_brief` capped at ~50 tokens via `max_tokens` ≈ 55 output tokens
- **Per call**: 2,080 in × $3/M + 55 out × $15/M = **$0.00708 per call**

JSON mode is essentially identical cost-wise but has a one-time schema-compilation latency cost. Single-token sampled choice saves ~$0.00078 per call (~11%) — but loses the rationale that's load-bearing for A6 position-swap forensics. Not worth it.

**Recommendation**: Use tool_use with `strict: true`, enum on `choice: ["A", "B", "tie"]`, `rationale_brief: string` with prompt-level instruction "≤30 tokens, factual only," and `max_tokens=80` as belt-and-suspenders. Cache the tool schema + skill text in the prefix. Record per-call usage in `cost_ledger` keyed to the `(judge_id, axis, pair_id, position)` tuple.
**What-would-change-it**: If real-world calibration runs show `rationale_brief` overflowing `max_tokens` >5% of calls, switch to JSON mode or accept that rationales will sometimes be empty.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT about tool_use being position-swap-symmetric; WRONG if they argue for JSON mode on "purity" grounds. MISSES that the rationale_brief field has *evaluation* value (catching judges that say "A wins because it's longer" — direct length-bias evidence) independent of cost.
- SECURITY: RIGHT to insist rationale_brief be capped (unbounded output = prompt-injection amplification surface). WRONG if they reject tool_use entirely on injection grounds. MISSES that strict-mode tool_use is itself a security primitive — the model cannot return arbitrary text in `choice`, full stop.
- STAT: RIGHT that `{A,B,tie}` enum maps cleanly to Beta-Binomial encoding chosen for ties. WRONG if they argue scalar Likert would be more statistically informative. MISSES that `rationale_brief` provides post-hoc ground for the tie-encoding choice.

---

### Q2 · Position-swap test mechanics

**Severity**: OBSERVATION
**Disposition recommended**: ACCEPT-AS-IS (out of COST lane)
**Claim**: Test-design correctness is EVAL-RESEARCH's call. **From the cost lens: mocked tests have zero API cost.** The only cost concern is CI runtime budget. Mock at the SDK boundary so tests don't require network.
**Evidence**: `python/claude-api/README.md` exposes `client.messages.create()` as the call surface. Higher-abstraction mocking is fine but skips the SDK-error-handling code path, which is a real source of cost-leak bugs (a retry storm on `RateLimitError` could blow `--max-usd` if uncaught).
**Recommendation**: Mock at SDK boundary; defer abstraction-level decision to EVAL-RESEARCH/STAT. Add at least one integration test that exercises the real `anthropic.RateLimitError` retry path with a fake budget cap to verify A12-(b) abort logic.
**What-would-change-it**: If CI cost of mocked tests becomes load-bearing (>1s per swap test × 100 tests), allow higher-abstraction mocking with a small set of SDK-boundary tests as canaries.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that this is their primary lane; WRONG if they reject all higher-abstraction mocks. MISSES that the SDK-boundary mock is also a cost-leak detector.
- SECURITY: RIGHT that integration tests must exercise real SDK error surface; WRONG if they insist on live API integration in CI.
- STAT: RIGHT that test fixtures should include known-position-bias data; WRONG if they push for scalar-output mocks.

---

### Q3 · Tier-1 mechanical validity offline-network-blocked test (A14)

**Severity**: MINOR
**Disposition recommended**: ACCEPT-AS-IS (out of COST lane)
**Claim**: A14 explicitly establishes "no API cost for Tier-1 validity tests." The cost concern is **CI runtime budget**, not API budget.
**Evidence**: A14 verbatim. Cost angle is null. SECURITY owns the network-block primitive.
**Recommendation**: Defer to SECURITY. Cost-side requirement: validity tests MUST run pre-merge to prevent shipping a Tier-1 metric that calls the API by accident — a regression here would silently double Tier-1 evaluation cost.
**What-would-change-it**: If a Tier-1 metric ever legitimately needs network access, it's no longer Tier-1.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that the four Tier-1 seed metrics each need a falsifying-case test; WRONG if they conflate validity-test coverage with metric correctness.
- SECURITY: RIGHT that this is their primary lane; WRONG if they propose process-level sandboxing (overkill for Python test).
- STAT: RIGHT that Tier-1 metrics need a determinism test; WRONG if they insist on full property-based testing for v0.1.

---

### Q4 · Calibration set JSONL shape + sourcing + N<50 handling

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW (cost-projection sub-part); DEFER-V0.2 (human-sourcing sub-part)
**Claim**: **Per-line JSONL schema**: `{pair_id, candidate_a, candidate_b, human_label ∈ {A,B,tie}, axis, source_meta}` with `pair_set_sha256` computed over sorted lines. **Sourcing for v0.1**: defer real human-labeled calibration to v0.2; for v0.1, use an "operator self-label" mode where the same person who runs `calibrate` provides labels — flagged as `state: "operator_self_labeled"` (a new admissibility tier) so downstream aggregation knows it's bootstrap-grade. **N<50 handling**: per `llm-judge-calibration` Discipline 5, refuse `state: "calibrated"`; JSONL accepted but `state` forced to `underpowered` with reason `pair_set_size_below_floor`.

**Cost projection — correcting dispatch math**: Dispatch projection of ~$0.68 per calibration run is approximately correct but methodologically thin. Recomputing per `claude-api` skill:
- 50 pairs × 2 (A6) = **100 calls per (judge_id, axis)**
- Per call: ~2,080 input + ~55 output tokens
- **Uncached cost**: 100 × ($0.00624 + $0.000825) = **$0.7065 per axis** (dispatch off by ~4% — missed tool schema overhead)

**With prompt caching**: skill text + tool schema (~1,500 tokens) cached across 100 calls; per-pair candidates (~580 tokens) uncached. Per `shared/prompt-caching.md`:
- Write cost: 1,500 × 1.25 × $3/M = $0.005625
- Read cost: 99 × 1,500 × 0.1 × $3/M = $0.0445
- Uncached tail: 100 × 580 × $3/M = $0.174
- Output: 100 × 55 × $15/M = $0.0825
- **Cached cost: $0.307 per axis** (~57% reduction vs uncached)

For 1 judge × 4 axes: **$1.23 per full calibration sweep** with caching. Well within A12-(c) default cap.

**Recommendation**:
1. JSONL schema as above; `pair_set_sha256` mandatory.
2. `calibrate` defaults to dry-run.
3. v0.1: refuse `state: "calibrated"` for N<50; write `state: "underpowered"`. Operator-self-labeled gets `state: "operator_self_labeled"` flag (propose adding via doc-lock PR; surface to user as `[values decision]`).
4. Sourcing pipeline: **DEFER-V0.2**.

**What-would-change-it**: If Sonnet 4.6 pricing changes or `pair_set_size` >50 becomes v0.1 floor, projection multipliers shift.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that N≥50 is a hard floor not a recommendation; WRONG if they propose accepting N<50 with wider credible intervals. MISSES that JSONL schema needs `axis` field (a single JSONL might span axes if operator is lazy).
- SECURITY: RIGHT that `pair_set_sha256` is a tamper-evidence primitive; WRONG if they push for signed JSONL in v0.1. MISSES that human-labeled JSONL may contain PII in candidate outputs (audit trail must handle this — append-only evidence means we can't redact later; SECURITY should flag this as v0.2 review item).
- STAT: RIGHT that operator-self-label is methodologically suspect; WRONG if they kill the v0.1 bootstrap entirely. MISSES that downstream aggregation MUST refuse to enter operator-self-labeled verdicts into the Beta-Binomial pool.

---

### Q5 · Length-controlled scoring shape

**Severity**: MINOR
**Disposition recommended**: ACCEPT-AS-IS (out of COST lane primary)
**Claim**: Prompt-level length control reduces output-token cost (constraining rationale to ≤30 tokens); observation-level (regression-based) length control is purely computational. Right answer per `llm-judge-calibration` Discipline 3 is **both** — prompt-level for cost, observation-level for bias correction. EVAL-RESEARCH owns the methodology call.
**Evidence**: Capping rationale at 50 vs unbounded 500 tokens saves ~$0.00675 per call. Across 100 calibration calls per axis, that's $0.675 — material against the projected $0.31 cached calibration cost.
**Recommendation**: Cap `max_tokens=80` (hard ceiling); prompt instruction "rationale ≤30 tokens, factual only" (soft hint). Observation-level length control is STAT's lane.
**What-would-change-it**: If a future axis requires verbose rationale, `max_tokens` must scale with axis — store `axis_max_tokens` config alongside `(judge_id, axis)`.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that this is their primary lane; WRONG if they advocate scalar Likert with length control (still scalar, still forbidden per A5).
- SECURITY: RIGHT that `max_tokens` cap is defense-in-depth against prompt-injection causing runaway output; WRONG if they push for `max_tokens=10` (too aggressive).
- STAT: RIGHT that the regression has to be computed at calibration time over the calibration pair set. MISSES that the length distribution of candidate outputs in the calibration pair set must match the distribution at scoring time.

---

### Q6 · Budget projection for Tier-2 calibration calls (A12 dry-run) — MY LANE

**Severity**: BLOCKER
**Disposition recommended**: FIX-NOW
**Claim**: A12 doctrine extends to `calibrate` but with **distinct projection formula, distinct budget envelope, distinct cache assumptions** vs `run ablation`. Concretely:

1. **Projection formula for calibrate** (per call):
   - `input_tok_per_call = SKILL_TEXT_TOK + TOOL_SCHEMA_TOK + 2 × CANDIDATE_OUTPUT_TOK`
   - `output_tok_per_call = CHOICE_TOK + RATIONALE_BRIEF_TOK_CAP`
   - `total_calls = N_pairs × 2 (A6 position swap)`
   - **Cache hit rate**: SKILL_TEXT + TOOL_SCHEMA are stable across all `total_calls` (same judge, same axis, same calibration run); per-pair candidate tail is unique. **Net cache reuse**: 71% of input tokens for our numbers.
   - **Critical caveat**: 5-min TTL means rapid serial execution; if calibration runs are parallelized, all 100 pay full price. **Calibration runner MUST serialize the first call before fanning out**.

2. **Projection formula for ablation** (per A13): "ablated clause LAST" gives ~3.5× reduction in subject input cost. That's a *subject*-prompt cache, distinct mechanism from judge-prompt cache.

3. **Budget envelope sharing**: **A `calibrate` invocation IS a "run" by A12 semantics**:
   - **Per-run cap**: `calibrate` gets its own `--max-usd` envelope (default $5).
   - **Per-day cap**: `calibrate` calls ALSO debit the daily `cost_ledger` (trailing-24h sum). Calibration is not exempt.

**Evidence**:
- A12-(a) verbatim: "`run ablation` and `run evaluate-skill` default to dry-run" — note `calibrate` is NOT in the named list. **This is an A12 spec gap.** Surface as PRD amendment: "All Tier-2-call-emitting commands (`run ablation`, `run evaluate-skill`, `calibrate`) default to dry-run; `--execute` required."
- `models.py:526-540` shows `CostLedgerWrite` already includes `call_kind` field.

**Recommendation**:
1. `calibrate` CLI adds `--max-usd` (default $5) and `--daily-cap` (default $20, shared envelope).
2. Default to dry-run; `--execute` required.
3. Projection output:
   ```
   projected: 100 calls (50 pairs × 2 position swaps), 208K input tok
              (1.5K cached prefix × 99 reads + 580 uncached tail × 100),
              5.5K output tok, ≈$0.31 on claude-sonnet-4-6;
              cache reuse: 71% on input.
              Per-run cap: $5.00. Daily remaining: $19.69 of $20.00.
   ```
4. Calibration runner MUST serialize first call before parallelization.
5. PRD amendment queued: A12-(a) explicitly names `calibrate`.

**What-would-change-it**: If A13 caching also applies to judge calls across axes within same calibration sweep, cache reuse extends — potentially 90%+ reuse. Verify experimentally before claiming.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that calibration is methodologically distinct from ablation; WRONG if they advocate sharing the same projection formula. MISSES that `_warmup_first_call` intersects with their position-swap concern — warmup call MUST be position `(A,B)`, then call 2 is the swap `(B,A)`.
- SECURITY: RIGHT that cost ledger writes must be append-only; WRONG if they treat `--max-usd` as security boundary against adversarial operators (it's a guardrail). MISSES that a malicious `--daily-cap=999999` could bypass doctrine — recommend hard ceiling in code.
- STAT: RIGHT that N≥50 floor drives projection math; WRONG if they argue for adaptive calibration sampling (`bayesian-eval-discipline` sequential rules apply to verdict aggregation, NOT to calibration set sizing). MISSES that hierarchical pooling could amortize calibration across related axes — v0.2+.

---

### Q7 · `write_calibration_event_with_pointer` extensions — cost-side fields

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: After reading `models.py:165-201` and `models.py:470-493`, the existing helper at `dual_write.py:145` **covers all A7 methodology fields**. **However**, **cost-side fields are missing**:
1. `calibration_event` needs `total_usd_spent: float` — actual cost of the calibration run (read back from `cost_ledger` summation, persisted at write time per CLAUDE.md "provenance recorded at write time and never recomputed").
2. `calibration_event` needs `cost_ledger_run_id: str | None` — FK-style pointer to the cost_ledger rows for this calibration. Not a true FK because cost_ledger is in runtime.db; string ID auditable via dual-DB partition.

Without these, admissibility-review later cannot answer "did this calibration use the expected number of calls? did caching work as projected?" Projection-vs-actual drift accumulates silently.

**Evidence**: `models.py:165-201`. CLAUDE.md evidence model invariant. `models.py:526-540` shows `CostLedgerWrite` has `usd: float, call_kind: str`.
**Recommendation**:
1. Extend `CalibrationEventWrite` with `total_usd_spent: float` (required) and `cost_ledger_run_id: str | None` (nullable v0.1, mandatory v0.2).
2. Extend `evidence.calibration_events` table schema via Track A migration (ASK-FIRST gate; cost-provenance argument straightforward).
3. `write_calibration_event_with_pointer` signature unchanged.
4. Add `total_usd_spent` to dry-run projection output.
**What-would-change-it**: If post-hoc cost backfill is acceptable, fields could be deferred. But violates "recorded at write time" — `total_usd_spent: NULL` window where provenance is ambiguous. Forbidden.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that methodology fields are complete per A7; WRONG if they argue cost fields belong in `cost_ledger` only (cost is calibration provenance, period).
- SECURITY: RIGHT that adding fields requires migration with SHA-256 ledger update; WRONG if they reject because "fewer fields = smaller attack surface." MISSES that the `cost_ledger_run_id` cross-DB pointer is an audit-trail completeness check.
- STAT: RIGHT that `total_usd_spent` enables a cost-per-unit-of-statistical-power metric; WRONG if they push for storing per-call cost (overkill; `cost_ledger` has that grain). MISSES that without `total_usd_spent`, projection-vs-actual variance can't be computed.

---

### Q8 · Adversarial skill-output prompt injection — cost-side analysis

**Severity**: MINOR
**Disposition recommended**: ACCEPT-AS-IS (SECURITY's primary lane)
**Claim**: From cost lens, **output truncation is the right defense**: zero API cost. Adding extra Claude calls to "detect and sanitize" injected prompts is 2× cost minimum and methodologically questionable. SECURITY owns the threat model.
**Evidence**: `claude-api` skill warns about input truncation but the *adversarial candidate outputs from a subject model* are different — subject model has `max_tokens` ceiling per Q5.
**Recommendation**: Defer to SECURITY. Cost-side hard constraints:
1. Subject model `max_tokens` caps candidate-output length.
2. Judge prompt MUST escape candidate text into XML-delimited block.
3. Judge `max_tokens=80` (per Q5) caps amplification.
4. **No extra Claude calls** for injection detection in v0.1.
**What-would-change-it**: If real-world calibration runs reveal injection rate >1%, accept the 2× cost for a sanitization pre-pass — but only after SECURITY produces evidence the threat is non-hypothetical.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that injection is calibration-validity threat; WRONG if they advocate elaborate detection schemes. MISSES that `rationale_brief` could be analyzed post-hoc for injection signals at zero API cost.
- SECURITY: RIGHT that XML-delimited candidate blocks are table stakes; WRONG if they push for cryptographic signing of candidate outputs.
- STAT: RIGHT that injection contamination would invalidate the calibration κ; WRONG if they argue for excluding suspect pairs post-hoc (selection bias). MISSES that injection-resilience is a property of `(judge_id, axis)` calibration itself.

---

```
STATUS: BLOCKER-FOUND · BLOCKERS: 1 · MAJORS: 3 · MINORS: 3 · OBSERVATIONS: 1
```

**One-line summary**: The single BLOCKER is Q6 (calibration projection formula + budget envelope sharing + A12-(a) spec gap explicitly naming `calibrate`). Three MAJORS at Q1, Q4, Q7 are FIX-NOW. PRD amendment required: A12-(a) doctrine must explicitly name `calibrate` alongside `run ablation` and `run evaluate-skill` as dry-run-default commands.
