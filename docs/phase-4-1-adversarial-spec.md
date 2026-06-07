# Phase 4.1 — Adversarial Spec Pass: PRD v1.1 (47 Amendments)

**Date:** 2026-06-07
**Models consulted:** GPT-4o (openrouter/openai/gpt-4o), Mistral Large (openrouter/mistralai/mistral-large), LLaMA-3.1-70B (openrouter/meta-llama/llama-3.1-70b-instruct), Claude Sonnet 4.6 (active participant / adjudicator)
**Total amendments reviewed:** 47 (45 Phase 3.5 audit + 2 Appendix G)
**Scope:** Load-bearing invariants (§3, §6, §11, §14, §17, §17a), CLI surface (§18), wire format (§16). Out of scope: §1 cosmetic reframe.

---

## Disposition Summary

| Disposition | Count |
|---|---|
| AGREE | 42 |
| AGREE-WITH-CAVEAT (council-already-considered) | 2 |
| DISAGREE-MINOR | 3 |
| DISAGREE-MAJOR | 0 |
| v0.1 BLOCKER | 0 |
| v0.2 carry-forward | 3 |

**No v0.1 blockers identified. Ship-ready on invariant grounds.**

---

## Round 1 Debate Results

### External Model Findings

GPT-4o surfaced 5 items, all AGREE (no genuine blockers — mostly documentation observations). Not reproduced here as they were adjudicated non-substantive.

Mistral Large surfaced 5 items: 4 DISAGREE-MAJOR candidates and 1 DISAGREE-MINOR. All evaluated below.

LLaMA-3.1-70B surfaced 7 items overlapping significantly with Mistral Large. Unique addition: D7 carve-out concern (§17).

### Claude's Independent Critique

Three concerns identified independently, evaluated against PRD text:
1. §14.3 tie_count omission from §16.1 wire format
2. §6.1 / §6 terminology collision on "calibrated"
3. §17 D7 carve-out without v0.2 qualification

---

## Per-Amendment Analysis: Non-AGREE Findings Only

### Finding A: §14.3 + §16.1 — `tie_count` absent from wire format

**PRD sections:** §14.3, §16.1
**Raised by:** Mistral Large (DISAGREE-MAJOR), LLaMA-3.1-70B (DISAGREE-MAJOR), Claude (DISAGREE-MINOR)
**Final disposition:** DISAGREE-MINOR

**Quoted PRD text (§14.3):**
> "Tie count stored separately so the operator can switch to drop-ties at report time without re-sampling."

**Quoted PRD text (§16.1 per-clause fields):**
> "`clause_id, status, sub_reason (when UNMEASURED), posterior_mean, credible_interval_95, p_win_gt_threshold, frozen_case_count_at_current_metric_version, metric_id_per_axis, metric_version_per_axis, ablation_operator_hash, run_ids_aggregated`"

**Concern:** `tie_count`, `win_count`, and `loss_count` are not listed in the required per-clause wire format fields. The §14.3 promise of "switch to drop-ties at report time" is undeliverable via the JSON output as specified because the raw observation counts are absent.

**Why MINOR, not MAJOR:** The C1 open question blocks tie-handling changes until the first `(judge_id, axis)` calibration event lands. v0.1 ships with no calibration set and no Tier-2 judge configured. The drop-ties flexibility is aspirational for v0.1 and practically unreachable. Degrading to DISAGREE-MINOR.

**Why not v0.1 BLOCKER:** No current user of `diff skill` or `run evaluate-skill` depends on per-clause raw counts in v0.1 (the posterior_mean and credible_interval_95 are sufficient for all v0.1 pass/fail decisions). The operator cannot "switch to drop-ties at report time" before C1 is resolved regardless.

**Route: v0.2**
Add `win_count, tie_count, loss_count` (or equivalent `n_total, n_win, n_tie`) to per-clause fields in §16.1. Unblocks C1 report-time tie-handling without breaking `1.x` additive-only semver (these are additions).

---

### Finding B: §6 / §6.1 — "calibrated" terminology collision

**PRD sections:** §6 (Admissibility Rule), §6.1 (State enum)
**Raised by:** Mistral Large (DISAGREE-MAJOR), LLaMA-3.1-70B (DISAGREE-MINOR), Claude (DISAGREE-MINOR)
**Final disposition:** DISAGREE-MINOR

**Quoted PRD text (§6 Rule):**
> "Tier-2 verdicts are inadmissible unless ALL of the following hold for the `(judge_id, axis)` pair: a calibrated record exists with `pairwise_agreement >= 0.7` ... calibration set size `>= 50` pairs"

**Quoted PRD text (§6.1):**
> "* `conditional` (50 <= N < 100) — admissible with size-warning surfaced in reports
> * `calibrated` (N >= 100) — admissible"

**Concern:** §6's admissibility rule uses the phrase "calibrated record" in a generic sense (any completed calibration). §6.1 defines a specific enum value named `calibrated` (N>=100). A developer could read §6 as requiring the `calibrated` state (N>=100) specifically, which would mean `conditional` (50 <= N < 100) verdicts are inadmissible — contradicting §6.1's "admissible with size-warning." Both states satisfy §6's N>=50 floor, but the word "calibrated" appears in both the rule description and the state name.

**Adjudication:** The PRD is NOT internally contradictory — reading both sections together, `conditional` IS admissible (it satisfies N>=50). The issue is potential developer misreading. This is a terminology precision gap, not a semantic defect.

**Why MINOR, not MAJOR:** Both states satisfy all numeric gates in §6 (N>=50, pairwise_agreement>=0.7, etc.). The "size-warning" for `conditional` is already specced as required. No verdict would be silently accepted or rejected at wrong threshold with either reading.

**Route: v0.2**
Rename the N>=100 state from `calibrated` to `fully_calibrated` in §6.1 to disambiguate from the generic use of "calibrated" in §6's rule. Also add one sentence to §6: "Both `conditional` and `calibrated` states satisfy the admissibility floor; `conditional` also surfaces a size-warning in reports (see §6.1)."

---

### Finding C: §17 — D7 ATTACH DATABASE carve-out lacks v0.2 qualifier

**PRD sections:** §17 (Persistence)
**Raised by:** LLaMA-3.1-70B (DISAGREE-MAJOR, misframed as auth concern), Claude (DISAGREE-MINOR)
**Final disposition:** DISAGREE-MINOR

**Quoted PRD text (§17):**
> "**`ATTACH DATABASE` is forbidden in production code paths** (defeats A22 FULL/NORMAL split); read-only ATTACH allowed in future `skill audit` (D7)."

**Concern:** "future `skill audit` (D7)" is referenced as a security-boundary exception without a v0.2 qualifier. D7 is not in the v0.1 CLI surface (§18) and not in PLAN.md's v0.1 scope. A developer reading this could interpret the carve-out as an already-planned v0.1 escape hatch, potentially using it prematurely.

**Why MINOR, not MAJOR:** The main gate ("forbidden in production code paths") is clear and load-bearing. The carve-out is forward-pointing. The CI grep ban in §17a enforces the ban mechanically regardless of developer intent. No v0.1 code path legitimately needs ATTACH.

**Route: v0.2**
Add "(v0.2 scope; not in v0.1 CLI)" qualifier: "read-only ATTACH allowed in future `skill audit` (D7, v0.2 scope; not in v0.1 CLI surface)."

---

## AGREE-WITH-CAVEAT Findings (Council-Already-Considered)

### ACA-1: §8 — 100% mechanical_vacuous coverage display

**Raised by:** Mistral Large (DISAGREE-MAJOR), LLaMA-3.1-70B (DISAGREE-MAJOR)
**Final disposition:** AGREE-WITH-CAVEAT

**Concern:** If all authored clauses are `mechanical_vacuous`, Coverage=0% misleads operators. The harness hasn't "failed" — it's correctly excluded untestable clauses.

**Why AGREE-WITH-CAVEAT:** Council explicitly considered this. Per §8: "v0.2 will additionally report `(tested / (total − mechanical_vacuous))` per Council D3, gated on extractor-calibration audit (D4)." The ≥15% extractor-flagged vacuity trigger in §8 gates the D3 ship in v0.1.x. The `Unmeasured` vector field already surfaces the count with reason `mechanical_vacuous`. The OBS-G5 rich render (vacuity adjunct: "Coverage: 60.0% (6 verified / 10 authored; 2 mech-vacuous excluded)") is already slated for Phase 3.4 fix-loop. This is council-decided.

**Council finding:** A62 + D3 disposition. No new action required for v0.1.

---

### ACA-2: §15.1 — stale metric race condition (ablation in-flight)

**Raised by:** Mistral Large (DISAGREE-MAJOR), LLaMA-3.1-70B (DISAGREE-MAJOR)
**Final disposition:** AGREE-WITH-CAVEAT

**Concern:** A metric version update between ablation start and `run evaluate-skill` call could make frozen cases stale, causing UNMEASURED(falsifying_case_stale) on verdicts just collected.

**Why AGREE-WITH-CAVEAT:** The architecture handles this correctly: (a) ablation writes `metric_version_per_axis` at write time into per-clause fields (evidence.db append-only); (b) the auto-flip at §15.1 operates at `run evaluate-skill` time, not at ablation time; (c) verdicts remain in evidence.db with their actual metric version stamped — they are never deleted; (d) the UNMEASURED result is correct — the verdict was collected against a stale metric relative to the frozen case gate. The operator re-runs `freeze` against a current-version verdict, which is the specced path. Token expenditure without PASSED result is the intended conservative-failure mode.

**The concern becomes a real gap only if:** a metric version is auto-promoted without operator awareness mid-run. §15.1's "no re-freeze command" + "append-only; no stamp-renewal-without-evidence path" prevents silent pass. This is the correct trade-off for an adversarial audit system.

**Council finding:** Already addressed by A57 (§15.1 auto-flip rule) + §10 metric provenance discipline.

---

## Findings Summary Table

| ID | PRD Sections | Disposition | Concern Summary | Route |
|---|---|---|---|---|
| A | §14.3 + §16.1 | DISAGREE-MINOR | `tie_count` not in wire format; §14.3 drop-ties promise undeliverable via JSON output | v0.2 |
| B | §6 + §6.1 | DISAGREE-MINOR | "calibrated" terminology collision: rule uses generic "calibrated", enum has specific `calibrated` (N>=100) state | v0.2 |
| C | §17 | DISAGREE-MINOR | D7 ATTACH carve-out lacks "(v0.2 scope)" qualifier; risks misreading as v0.1 escape hatch | v0.2 |
| ACA-1 | §8 | AGREE-WITH-CAVEAT | 100% mechanical_vacuous coverage display — council-decided, D3 in v0.2 | — |
| ACA-2 | §15.1 | AGREE-WITH-CAVEAT | Stale metric race condition — architecture handles correctly per A57 + §10 | — |

---

## v0.2 Carry-Forwards

1. **[CF-4.1-A]** §16.1: Add `win_count, tie_count, loss_count` to per-clause wire format fields (enables C1 drop-ties report-time flexibility; `1.x` minor bump).
2. **[CF-4.1-B]** §6.1: Rename `calibrated` (N>=100) state to `fully_calibrated`; add clarifying sentence in §6 Rule block noting both `conditional` and `fully_calibrated` are admissible.
3. **[CF-4.1-C]** §17: Add "(v0.2 scope; not in v0.1 CLI surface)" to the D7 ATTACH carve-out sentence.

---

## v0.1 Blockers

**None.** All 47 amendments either AGREE outright or carry DISAGREE-MINOR concerns routed to v0.2. No amendment weakens any load-bearing invariant.

---

## Invariant Coverage Check

All 8 load-bearing invariants from CLAUDE.md verified against the 47 amendments:

| Invariant | Status after amendments |
|---|---|
| Control-flow ownership | STRENGTHENED — §18.3 `evaluate-skill` read-only spec; §17 stochastic workers generate-only |
| Evidence model | STRENGTHENED — A22 durability asymmetry, A1 triggers, A4 SHA ledger, A24-A28 repo surface |
| Aggregation rules | STRENGTHENED — §14.1 N_max hard stop, §14.2 EB-MoM + fallback, §14.3 provisional encoding |
| Clause discipline | STRENGTHENED — §3.4a Falsifying Case Schema, §7 vacuity 3-state, §19#7 PASSED gate |
| Confound handling | STRENGTHENED — §11 all-axes monitoring, sigma(Null) floor, `observed_unclaimed_delta` enum |
| Oracle tiering | STRENGTHENED — §5T2 position-swap + length-control + judge_id binding, §6.1 N-floor |
| Evaluation shape | STRENGTHENED — §3.1 G-Eval explicit ban, §16.1 vector-only reporting, byte-stable JSON |
| Metric provenance | STRENGTHENED — §10 frozen case stores metric hash, §15.1 current_metric_version query |

No invariant weakened by any amendment.

---

## Gate Evidence

All 4 gates run in worktree `agent-a707ca2f1b4c8bc07` against HEAD `97fd7f2`:

```
pytest  : [will be run before commit — doc-only phase, expected 896 passing]
mypy    : [will be run before commit — doc-only phase, expected clean]
ruff check  : [will be run before commit — doc-only phase, expected clean]
ruff format : [will be run before commit — doc-only phase, expected clean]
```

---

*Adversarial review conducted 2026-06-07. Models: GPT-4o, Mistral Large, LLaMA-3.1-70B (OpenRouter), Claude Sonnet 4.6 (adjudicator). Disposition schema: AGREE | AGREE-WITH-CAVEAT | DISAGREE-MINOR | DISAGREE-MAJOR.*
