# STAT seat — Pre-Track-C council (2026-06-05)

**Model**: Opus 4.7 (background subagent, ~179s, 198,454 tokens)
**Skills loaded** (per dispatch): `bayesian-eval-discipline`, `llm-judge-calibration`, `claude-api`

---

### Q1 · Tier-2 judge response shape

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: tool_use with `strict: true` enforces the `{A, B, tie}` schema at the API contract level, eliminating parsing-failure variance from contaminating verdict counts. Plain-text + regex adds a parse-failure mode that competes with the verdict distribution — a malformed JSON-ish response becomes an inadmissible verdict for a *non-statistical* reason, polluting the position_swap_agreement denominator. From STAT's seat, parse failure is **noise mixed into signal** and cannot be cleanly separated from genuine judge instability post-hoc.
**Evidence**: `claude-api` skill (Strict Tool Use). `llm-judge-calibration` Discipline 7. Plain-text+regex is what G-Eval-style harnesses do; published κ deltas confirm format-sensitivity bias.
**Recommendation**: Single tool `record_verdict` with `input_schema = {verdict: {type: string, enum: ["A","B","tie"]}, rationale: {type: string}}`, `strict: true`, `tool_choice: {type: "tool", name: "record_verdict"}`. Pin model `claude-sonnet-4-6` (cost), `thinking: {"type": "disabled"}` (calibration determinism > reasoning depth), no sampling params. Store `judge_id = sha256(model_id || system_prompt_sha256 || tool_schema_sha256)` per `llm-judge-calibration` Discipline 7 — the tool schema is part of the calibration variable.
**What-would-change-it**: Anthropic releases a constrained-decoding API that beats tool_use on determinism benchmarks (unlikely in v0.1 horizon).

**Cross-talk**:
- EVAL-RESEARCH: RIGHT about pairwise-only and forbidding rationale-first scalars; WRONG if they push for "give the judge the option to abstain via `tie`" as primary lever (tie semantics are STAT's lane per C1). MISSES that the tool schema hash feeds into `judge_id` and therefore into calibration scope.
- SECURITY: RIGHT that tool_use also denies the judge an avenue for prompt-injected free text in the verdict field; WRONG if they argue rationale must be removed entirely (rationale aids audit without entering scoring). MISSES that A8's stopping rule depends on parse-success rate being ~100%.
- COST: RIGHT that tool_use adds ~20-50 input tokens; WRONG if they propose plain-text to save those tokens (savings is rounding error vs. one re-call on parse failure). MISSES that `record_verdict` is identical across all axes — perfect prompt-cache prefix candidate.

---

### Q2 · Position-swap test mechanics

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: The test fixture must exercise BOTH branches of `position_swap_agreement`: (a) `(A,B)→A` + `(B,A)→B` ⇒ swap_agreement=1, admissible; (b) `(A,B)→A` + `(B,A)→A` ⇒ swap_disagreement=0, inadmissible with `inadmissibility_reason = "position_disagreement"`. Plus a third case for tie symmetry: `(A,B)→tie` + `(B,A)→tie` ⇒ swap_agreement=1 (ties flip to themselves per `llm-judge-calibration` Discipline 2: `flip("tie") ≡ "tie"`).
**Evidence**: `llm-judge-calibration` Discipline 2 verbatim. The `OracleVerdictWrite` model in `src/skill_harness/storage/models.py:272-323` already carries `position_swap_agreement: int | None` and `admissibility_state: str`.
**Recommendation**: Mock the Anthropic SDK at `client.messages.create` boundary (or wrap in a `JudgeClient` Protocol — preferred for testability). Three RED tests: `test_swap_consistent_a`, `test_swap_disagreement_inadmissible`, `test_swap_consistent_tie`. The mock returns deterministic tool_use blocks keyed on `(prompt_position, swap_iteration)`. Verify `admissibility_state` is written at write-time and never recomputed.
**What-would-change-it**: A future tier-2 protocol that uses N>2 invocations per pair (e.g., 3-way self-consistency) — would expand the swap_agreement encoding from binary to fractional.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that the mock must produce the verdict, NOT compute admissibility (admissibility is the deterministic layer's call); WRONG if they propose mocking at HTTP layer (over-tested, brittle to SDK changes). MISSES the tie-symmetry test as a separate case.
- SECURITY: RIGHT that the mock should be a Protocol/ABC, not monkeypatch (avoids SDK-import-time network calls); WRONG if they require the mock fixture to also test injection. MISSES that the test should assert `inadmissibility_reason` is a finite enum string.
- COST: RIGHT that the test must NOT call live Anthropic; WRONG if they propose recording real fixtures (calibration brittleness). MISSES that prompt-cache hits make swap pairs cheaper at runtime.

---

### Q3 · Tier-1 mechanical validity offline-network-blocked test (A14)

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: A14 requires "deterministic-output test" — bit-equality on two invocations with the same input is the structurally strong primitive (verifies determinism, the property that makes Tier-1 admissible without calibration). Hypothesis-style invariance is a complementary property test but is NOT what A14's exit criteria demand for the auto-downgrade gate. Bit-equality is the gate; invariance properties are nice-to-have hardening.
**Evidence**: `bayesian-eval-discipline` Discipline 1 (by analogy). CLAUDE.md "Metric provenance" invariant: "Every frozen case stores metric identity, version, and implementation hash so re-audit is possible when a metric changes" — implementation_hash is meaningless if the metric is non-deterministic.
**Recommendation**: Test primitive = `assert metric(input) == metric(input)` over a small fixed input corpus (3-5 inputs per metric), with `socket.socket = _raise_offline()` monkeypatched at module level. Add a meta-test ensuring the network-block test itself fires by hitting any networked call. Hypothesis property tests as **additional** suite, not gating — flagged as `@hypothesis_optional` with separate CI lane.
**What-would-change-it**: A Tier-1 metric that intentionally uses non-determinism (e.g., a sampled estimator) — would require recasting validity test as "convergence to expected value within tolerance" and re-classifying.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that the test must be offline-only; WRONG if they push Hypothesis as the primary gate (over-engineered for v0.1). MISSES that bit-equality also catches floating-point non-determinism that would otherwise pollute confound thresholds (A11).
- SECURITY: RIGHT about socket-blocking via monkeypatch; WRONG if they require namespace isolation (subprocess) — overkill. MISSES that the test must lock filesystem reads to fixed corpus dir to prevent metric-under-test from reading non-deterministic /dev/urandom or similar.
- COST: RIGHT that Tier-1 tests should be free and fast; WRONG if they argue against Hypothesis on cost grounds (Hypothesis is CPU-local, free).

---

### Q4 · Calibration set JSONL shape + sourcing — STAT LANE

**Severity**: BLOCKER
**Disposition recommended**: FIX-NOW
**Claim**: This is the lane question. Per-line schema `{prompt: str, response_a: str, response_b: str, human_preference: "A"|"B"|"tie", pair_id: str}` is correct; `pair_id` is essential so calibration_events can re-derive results without re-reading the JSONL. **N=50 is the published-literature floor but is statistically thin at threshold=0.7**: SE of `pairwise_agreement` ≈ `sqrt(0.7×0.3/50) ≈ 0.065`, 95% CI ≈ `0.7 ± 0.127`. A judge at the threshold has a 95% CI of `[0.573, 0.827]` — at the lower bound it's only 7pp above the chance line (~0.5 for binary; ~0.33 for 3-class). **N=100 is the operational target**; N=50 is the minimum-to-attempt gate. For Cohen's κ on 3-class: chance baseline = `Σ p(rater1=c)·p(rater2=c)` (NOT 1/3 uniform — uses observed marginals). Standard formula `κ = (p_o − p_e) / (1 − p_e)` per Cohen 1960.
**Evidence**: `llm-judge-calibration` Discipline 5 explicitly confirms STAT's concern. Cohen 1960. `bayesian-eval-discipline` Discipline 1.
**Recommendation**:
1. JSONL schema: `{pair_id: str, prompt: str, response_a: str, response_b: str, human_preference: "A"|"B"|"tie", labeler_id: str, labeled_at: str}`. The `labeler_id` matters for κ if multiple labelers.
2. N<50: command rejects with `INSUFFICIENT_CALIBRATION_DATA`; calibration_event is NOT written.
3. 50 ≤ N < 100: write calibration_event with `state = "conditional"`; system MAY produce verdicts but aggregation applies a credible-interval-widening penalty.
4. N ≥ 100: `state = "calibrated"` if all four thresholds pass.
5. Humans for v0.1: orchestrator hand-labels. For public roadmap, recommend `--seed-from-public {chatbot-arena, alpacaeval}` flag in v0.2. **Do not auto-generate human preferences via another LLM** (calibration becomes self-referential).
6. Cohen's κ for 3-class with tie: implement against observed marginals per Cohen 1960. Store κ alongside p_o and p_e separately (audit can re-derive κ if formula changes). Threshold 0.4 = Landis-Koch "fair/moderate" boundary — MINIMUM secondary; should NOT be primary gate.

**What-would-change-it**: v0.2 publishes empirical SE bounds from real calibration runs showing N=50 produces tighter CIs than theoretical bound (unlikely).

**Cross-talk**:
- EVAL-RESEARCH: RIGHT about JSONL shape being preference-pair-centric, RIGHT about needing `labeler_id`; WRONG if they propose synthetic LLM-generated preferences for v0.1. MISSES the chance-baseline-with-marginals nuance and the `state="conditional"` bridge for 50≤N<100.
- SECURITY: RIGHT that JSONL files are user-controlled input and must be parsed defensively (Pydantic validation, line-length caps, total-size caps); WRONG if they require signed JSONL. MISSES that `pair_set_sha256` (already at models.py:178) is the tamper-evidence layer.
- COST: RIGHT that N=100 doubles calibration cost vs N=50; WRONG if they argue to lower N below 50. MISSES that human-label generation, not API calls, is the dominant cost at calibration time.

---

### Q5 · Length-controlled scoring shape

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: AlpacaEval-2 (Dubois et al. 2024) uses a generalized linear model with logit link: `logit(P(verdict_A)) = β_0 + β_1 · (len_A − len_B) + β_2 · pair_features`. The coefficient `β_1` is estimated at **calibration time** over the human-preference set; at **verdict time**, the raw verdict is adjusted by subtracting `β_1 · Δlen` from the logit. The `length_controlled_agreement` is the agreement metric computed AFTER this adjustment. A6 conflates two things STAT needs to disentangle: (a) fitting β_1 → stored in `calibration_events`, used to adjust verdicts at runtime; (b) reporting `length_controlled_agreement` → also stored, used in admissibility gate.
**Evidence**: `llm-judge-calibration` Discipline 3 calibration record schema explicitly lists `length_controlled_agreement`. AlpacaEval-2 paper section 3.2.
**Recommendation**:
1. At `calibrate` time: fit `β_1` over JSONL pair set using statsmodels or scipy. Compute `length_controlled_agreement`. Store BOTH `β_1` (as `length_regression_coefficient`) AND `length_controlled_agreement` in `calibration_events` — see Q7.
2. At `record verdict` time: deterministic Python layer applies `adjusted_logit = raw_logit − β_1 · Δlen`. Store both `raw_observation` and `length_adjusted_observation`. Aggregation reads adjusted; audit can re-derive.
3. Threshold: `length_controlled_agreement ≥ 0.65` per `llm-judge-calibration` Discipline 4.
**What-would-change-it**: AlpacaEval-3 publishes different correction (e.g., orthogonalization rather than regression) — would replace β_1 with orthogonal projection but storage shape generalizes.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT about AlpacaEval-2 being source-of-truth pattern; WRONG if they propose applying length correction at aggregation time instead of verdict-write time (violates "no recomputation"). MISSES that storing `β_1` separately enables re-audit when sklearn/statsmodels version bumps.
- SECURITY: RIGHT that regression coefficient must be deterministic-given-input (no stochastic optimizer); WRONG if they require custom impl. MISSES that the regression input (response lengths) must be tokenizer-version-locked.
- COST: RIGHT that adding length-control adds zero per-verdict API cost; WRONG if they argue for skipping it to save calibration complexity. MISSES that without length-control, longer-output skills get a free win-rate boost.

---

### Q6 · Budget projection for Tier-2 calibration calls (A12 dry-run)

**Severity**: MINOR
**Disposition recommended**: FIX-NOW
**Claim**: At N=50, 2 calls per pair (swap), 5 axes = 500 calls per calibration cycle; 4×/year minimum = 2000 calls/year baseline. At N=100 (STAT's recommended target): 4000 calls/year. Sonnet 4.6 input is ~1-2K tokens × output ~50 tokens → ~$0.005-0.01 per pair. Per-axis calibration ≈ $0.50-$2 at N=100. **The cost is negligible; the dry-run is about preventing accidental large-N runs, not restricting normal calibration.**
**Evidence**: `claude-api` skill pricing table. Prompt caching could cut input cost by 90%. `bayesian-eval-discipline` Discipline 4.
**Recommendation**:
1. Dry-run output includes: `pairs=N, calls=N×2, est_input_tokens=N×2×avg, est_cost_USD=<float>, est_SE_pairwise_agreement=<float>, est_CI_95_width=<float>`.
2. Hard cap: `--max-calibration-cost=10.00` USD default; refuse to run if estimate exceeds.
3. Cache: system prompt + tool schema cached (prefix), only the pair content varies.
4. Multi-axis calibration: serial, not parallel (avoids cache invalidation across axes).
**What-would-change-it**: User flips C1 to "drop ties" — slightly changes variance equation for `pairwise_agreement` but cost projection unchanged.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that variance-budgeting at calibration matters; WRONG if they advocate adaptive calibration sample sizing.
- SECURITY: RIGHT that dry-run must default-on; WRONG if they require operator confirmation modal. MISSES that cost projection is a leak signal: if it suddenly spikes, prompt cache has been invalidated by silent system-prompt change.
- COST (their own lane): RIGHT that this is mostly their lane; WRONG if they propose three-layer cost cap WITHOUT SE projection. MISSES that calibration is per-(judge_id, axis), and judge_id includes system_prompt_sha256 — silent prompt changes force re-calibration.

---

### Q7 · `write_calibration_event_with_pointer` shape — extensions

**Severity**: BLOCKER
**Disposition recommended**: FIX-NOW
**Claim**: Current `CalibrationEventWrite` at `src/skill_harness/storage/models.py:165-201` carries the A7 fields but is **missing** STAT-essential reproducibility fields: (1) `n_a, n_b, n_tie` — per-class counts in the calibration set, required for re-deriving Cohen's κ and computing tie-rate (the C1 disposition input); (2) `length_regression_coefficient: float | None` — separate from `length_controlled_agreement`, required to re-apply length-correction without re-fitting; (3) `chance_baseline: float | None` — observed-marginal p_e from κ formula, stored separately so audit can re-derive κ if Cohen formula updates. The C1 tie-encoding flip decision **DEPENDS ON** observed tie rates from real calibration sets — without `n_tie/N`, the user cannot make C1.
**Evidence**: `bayesian-eval-discipline` Discipline 1: "Always report tie rate alongside posterior summaries. A 30% tie rate means the 'win rate' the posterior is estimating is half hallucination." CLAUDE.md "Append-only evidence": "Provenance recorded at write time and never recomputed." A10 in COUNCIL_FINDINGS: "DEPENDS ON Track C calibration data."
**Recommendation** (extends `CalibrationEventWrite` at models.py:165):
```python
class CalibrationEventWrite(BaseModel):
    # existing fields ...
    n_a: int                                  # human-pref A count
    n_b: int                                  # human-pref B count
    n_tie: int                                # human-pref tie count
    judge_n_a: int                            # judge verdict A count
    judge_n_b: int                            # judge verdict B count
    judge_n_tie: int                          # judge verdict tie count
    length_regression_coefficient: float | None
    chance_baseline: float | None             # p_e from κ formula
    # state field already exists; add enum: "calibrated" | "conditional" | "expired" | "uncalibrated" | "rejected"
```
Plus a migration to add columns to `evidence.calibration_events`. Migration must preserve A22 asymmetric durability (FULL on evidence.db).
**What-would-change-it**: User flips C1 to "drop ties" — the `n_tie` field becomes the dispositive read at next calibration; once flipped, schema unchanged.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that calibration must carry per-class counts; WRONG if they propose storing the full JSONL inside calibration_events (`pair_set_sha256` already provides the link). MISSES that `judge_n_*` is separable from `n_*` (human) and both are needed for κ.
- SECURITY: RIGHT that adding columns requires migration with append-only triggers preserved; WRONG if they propose JSON blob columns for forward-compat. MISSES that `chance_baseline` recording closes a re-audit vulnerability where future κ formula changes would be untraceable.
- COST: RIGHT that storage cost is negligible; WRONG if they argue against schema growth on cost grounds. MISSES that storing `n_tie` separately enables low-cost C1 dashboard query without parsing JSONL.

---

### Q8 · Adversarial skill-output prompt injection

**Severity**: MAJOR
**Disposition recommended**: FIX-NOW
**Claim**: STAT's hypothesis in the question is **partially correct but not robust**. Position-swap detects injection ONLY when the injection biases position-relative (e.g., "always pick the first one") — then `(A,B)→A` and `(B,A)→B` differ; swap_agreement=0, inadmissible. BUT position-swap FAILS to detect content-anchored injection (e.g., "if you see the string XYZ123, pick that one") — the injection moves WITH the response, so both `(A,B)→A` and `(B,A)→A` are consistent and the verdict passes admissibility while being attacker-controlled. Position-swap is a partial defense, not a complete one.
**Evidence**: `llm-judge-calibration` Discipline 2 covers position bias mitigation but does NOT claim it defends against prompt injection. CLAUDE.md "Aggregation rules" invariant: only admissible+non-confounded verdicts aggregate. `bayesian-eval-discipline` Discipline 3.
**Recommendation**:
1. Position-swap stays as primary defense for **position-anchored** injection.
2. Add `n_calibrated_axis_baseline` check: if judge's verdict distribution on a held-out null pair set (where neither output should win on axis X) deviates from expected ~33/33/33 by more than threshold k_inject·σ, flag the entire run as `JUDGE_DRIFT_SUSPECTED`. This is a Tier-1.5 health check.
3. Defer to SECURITY for input-sanitization patterns on skill output before it hits judge prompt.
4. Document position-swap-as-injection-defense as **partial, not complete** in skill docs.
**What-would-change-it**: Anthropic releases prompt-injection-resistant judging mode. Or: a published attack demonstrates content-anchored injection bypassing position swap at scale.

**Cross-talk**:
- EVAL-RESEARCH: RIGHT that position-swap is doctrine; WRONG if they overclaim it as injection defense (STAT's correction). MISSES the null-baseline distributional check as complementary signal.
- SECURITY (their own lane): RIGHT that input sanitization belongs here; WRONG if they propose sanitization that strips legitimate skill content (false positives degrade verdict quality). MISSES that null-baseline statistic is a SECURITY-relevant signal because it detects compromise even without knowing the attack vector.
- COST: RIGHT that null-baseline check adds calibration cost (N null pairs per judge); WRONG if they argue against on cost grounds (N=30 per `bayesian-eval-discipline` A11 already required for confound detection — reusable). MISSES that null-baseline pairs CAN be the same null pairs used for confound detection, amortizing cost.

---

```
STATUS: BLOCKER-FOUND · BLOCKERS: 2 · MAJORS: 5 · MINORS: 1 · OBSERVATIONS: 0
```

**Summary of blockers for synthesis**:
- **Q4**: N=50 SE is too wide at the threshold; need three-tier admissibility (`rejected` / `conditional` / `calibrated`) at `<50` / `50-99` / `≥100`, plus `pair_id` and `labeler_id` in JSONL shape, plus marginal-based Cohen's κ baseline.
- **Q7**: Current `CalibrationEventWrite` is missing fields required for C1 disposition (`n_a, n_b, n_tie`, `judge_n_*`), reproducibility (`length_regression_coefficient` separate from `length_controlled_agreement`), and re-audit (`chance_baseline` for κ). Migration must preserve A22 + append-only invariant.

Five MAJORs are all FIX-NOW and well-scoped for Track C implementation. One MINOR (Q6) is dial-tweaks on COST's lane.
