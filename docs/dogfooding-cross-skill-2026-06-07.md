# Cross-Skill Dogfooding Synthesis — 2026-06-07

**Phase**: 4.4 (synthesis)
**Date**: 2026-06-07
**Harness commit at observation time**: `97fd7f2fddaf5ba2a41a22a3eb3f7cbe61e2c4bf`
**Author**: Sonnet 4.6 worker (cross-skill synthesis agent)
**Source writeups**: `docs/dogfooding-ai-slop-sentinel-2026-06-07.md`,
`docs/dogfooding-bayesian-eval-discipline-2026-06-07.md`,
`docs/dogfooding-verbatim-content-subagent-dispatch-2026-06-07.md`
**Supporting context**: `docs/phase-3-6-verification.md`, `docs/phase-4-1-adversarial-spec.md`,
`docs/phase-4-3-insecure-defaults.md`, `PRD.md` §16/§19/§20, `docs/COUNCIL_FINDINGS.md` Appendix G (A62)

---

## 1. Setup

### Three skills dogfooded

| Skill | Shape | Clauses (--execute) | Tier-1 | Tier-2 | Tier-3 |
|---|---|---|---|---|---|
| `ai-slop-sentinel` | Review discipline (checklist + watch-entry protocol) | 17 | 7 | 10 | 0 |
| `bayesian-eval-discipline` | Dense academic (discipline doc + worked examples + citations) | 24 | 11 | 13 | 0 |
| `verbatim-content-subagent-dispatch` | Procedural directive (3-part dispatch contract) | 21 | 4 | 16 | 1 |
| **Total** | | **62** | **22** | **39** | **1** |

### Common pipeline

All three runs used the same pipeline sequence:

1. `skill init <path/SKILL.md> --execute` — import skill artifact, extract clauses via `claude-sonnet-4-6`, persist to `evidence.db`.
2. `run ablation <skill_id> --execute --max-usd 5` — execute single-clause ablation (Full / Ablated_k / Null conditions).
3. `run evaluate-skill <skill_id> --format=json` — aggregate verdicts, emit §16 vector.
4. `run evaluate-skill <skill_id>` (rich) — confirm rich render.

`PYTHONHASHSEED=0` set throughout. Per-run cap $5.00; daily cap $20.00.

---

## 2. Observed Cross-Skill Behavior — The Load-Bearing Findings

### Universal outcome: 0 PASSED, 0 FAILED, 62 UNMEASURED

All three runs produced identical §16 vectors at the aggregation layer:

| Skill | Passed | Failed | Confounded | Unmeasured | Coverage |
|---|---|---|---|---|---|
| ai-slop-sentinel | 0 | 0 | 0 | 17 | 0.0% |
| bayesian-eval-discipline | 0 | 0 | 0 | 24 | 0.0% |
| verbatim-content-subagent-dispatch | 0 | 0 | 0 | 21 | 0.0% |
| **Total** | **0** | **0** | **0** | **62** | **—** |

Per-clause sub-reason at aggregation layer: `no_data` (zero admissible verdicts written to DB).
Per-clause sub-reason at runner layer: `tier2_uncalibrated` (BLOCKER-1 gate fired before any subject calls).

### Root cause (BLOCKER-1): axis-name registration is the actual Tier-1 gate

The runner's `_is_tier1_measurable()` method applies two conditions before issuing subject calls:

1. `oracle_tier == 1` (declared by extractor), AND
2. `clause_spec.axis` is present in `self._scorers` (the registered scorer dict)

The four registered Tier-1 scorers in v0.1 are: `verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`.

Every axis extracted across all three skills is domain-specific:
- ai-slop-sentinel: `citation_presence_per_flag`, `watch_entry_metadata_completeness`, `watch_entry_schema_completeness`, etc.
- bayesian-eval-discipline: `tie_rate_disclosure`, `n_min_constant_in_code`, `stopping_rationale_per_arm`, etc.
- verbatim-content-subagent-dispatch: `verbatim_embedding_rate`, `ai_attribution_trailer_presence`, `fence_collision_prevention`, etc.

None of the 62 extracted axes match any registered scorer. Even the 22 extractor-declared `oracle_tier=1` clauses fail the axis-match gate. The `oracle_tier=1` declaration by the extractor is advisory metadata; the scorer registry is the enforcement gate. All 62 clauses hit BLOCKER-1 and return `UNMEASURED(tier2_uncalibrated)` without issuing any subject calls. Total ablation API spend: $0.00 across all three runs.

**Note on verbatim-content-subagent-dispatch Observation 5**: That writeup flagged that Tier-1 clauses were returning `tier2_uncalibrated`, hypothesizing a runner routing bug. The correct explanation is BLOCKER-1: axis-name mismatch, not a routing error. The runner correctly routes Tier-1 clauses through the mechanical oracle path, but refuses because the axis name is not in the scorer registry. The behavior is consistent across all three skills and is not skill-specific.

### The harness behaved correctly

PRD §20 states: "A clause that cannot be falsified is not a contract. It is metadata." The harness extends this principle one layer deeper: a clause whose declared axis has no admissible oracle is also unverifiable at v0.1 oracle surface. Rather than fabricating evidence or silently passing, the harness:

- Refuses to issue subject calls (no API spend on uncalibrated paths)
- Records `UNMEASURED(tier2_uncalibrated)` at the runner layer
- Records `UNMEASURED(no_data)` at the aggregation layer (no verdict rows written)
- Emits exit code 2 (UNMEASURED clauses present)
- Discriminates `no_data` from `underpowered` from `falsifying_case_stale` — three distinct sub-reasons, all present in the codebase, all verified by Phase 3.6 §19 tests

This is the honest outcome, not a regression. The system did not claim PASSED on unmeasured clauses. It did not silently aggregate fabricated signal. It reported exactly what it knew.

---

## 3. Skill-Shape Stress Observations

### ai-slop-sentinel (review-discipline shape)

17 clauses. 7 declared Tier-1 (mechanically countable, per extractor reasoning). 1 `semantic_vacuous_pending_review` (clause 16: "Embody the experienced, tenured senior-dev skeptic..." — a persona instruction with no constructible falsifying case). 0 mechanical-vacuous.

All Tier-1 axes are domain-specific review-quality metrics: `citation_presence_per_flag`, `watch_entry_metadata_completeness`, `flag_severity_classification_and_citation`, `review_gate_enforcement_coverage`, `watch_document_freshness_compliance`, `watch_entry_schema_completeness`, `watch_document_incident_driven_growth`. None match the registered scorer names.

The review-discipline shape is characteristically citation-heavy: almost all measurable axes require either counting structured fields in a watch document (Tier-1 candidate) or judging the quality of a review outcome (Tier-2). This skill has the highest Tier-1 potential of the three — 7 declared Tier-1 axes — and is the primary candidate for the Path B scorer-registration fix (adding `citation_presence_per_flag` or equivalent as a registered scorer should unblock ≥1 clause for ablation).

### bayesian-eval-discipline (dense-academic shape)

24 clauses (--execute). Dry-run produced 20 clauses (+4 / ~17% extractor drift; expected LLM stochasticity). 0 semantic-vacuous in the --execute run (1 in dry-run, borderline: "hierarchical fit is the better answer when arms share meaningful group structure"). 0 mechanical-vacuous.

Key stress observations that did NOT materialize:
- **Citation misclassification**: 5 citation lines in the Sources section were not extracted as clauses. The extractor correctly scoped to directive sections and excluded bibliographic text.
- **Math-claim extraction**: `Beta(1,1)` prior, `P(p > 0.60) >= 0.95` pass-rule, and `N_min` derivations were not extracted as testable behavioral directives. Classified as calibration metadata.
- **Vacuity inflation on academic docs**: 0% semantic-vacuous on --execute. The concern (>40% sem-vac rate on citation-dense content) did not materialize for ##-sectioned, example-rich discipline documents.

54% Tier-2 dominance (13/24) is expected for a meta-skill: directives like "always document which multiplicity correction is in effect" require behavioral judgment, not mechanical counting. The 46% Tier-1 rate (11/24) is the highest of the three skills by percentage, though all are blocked by axis-name mismatch.

### verbatim-content-subagent-dispatch (procedural-directive shape)

21 clauses. 5 `semantic_vacuous_pending_review` (clauses 0-4: problem-statement sentences describing what subagents currently do wrong — motivation block, not testable directives). 16 testable clauses (vacuity_flag=none).

The three-part dispatch structure (role identity / instrument binding / output contract) was preserved as distinct clause families, not collapsed. Multi-clause compound sentences were split atomically: "verbatim AND halt-on-ambiguity AND output contract" distributed across distinct clauses (8, 11, 12). No multi-clause sentence collapse observed.

15 of 16 testable clauses are Tier-2. 4 Tier-1 clauses present (`verbatim_embedding_rate` / `ai_attribution_trailer_presence` / `fence_collision_prevention` / `ai_attribution_in_commits`) — all blocked by axis-name mismatch. 1 Tier-3 clause (clause 19: model cost efficiency via real-world consequence) — no oracle path in v0.1.

---

## 4. Cross-Cutting Gotchas Surfaced

All three gotchas were independently observed across multiple agents on the same day, confirming systemic scope.

### Gotcha 1 — Windows cp1252 crash in Rich legacy renderer (ALL THREE SKILLS)

All three dogfooding agents independently hit `UnicodeEncodeError: 'charmap' codec can't encode character` on Windows cp1252 console. Characters affected: `⚠` (U+26A0), `→` (U+2192), `≠` (U+2260). The crash occurs in Rich's Windows legacy console renderer (`_win32_console.py`) after the ablation table renders successfully; it is render-only and does not corrupt data.

Workaround: `PYTHONIOENCODING=utf-8` (bash) or `[Console]::OutputEncoding = UTF8` + `$env:PYTHONUTF8=1` (PowerShell). Fix options: (a) replace Unicode symbols with ASCII fallbacks (`[!]`, `->`, `!=`) in the warning/footer print calls, or (b) force UTF-8 console mode at CLI startup.

**Doc gap**: `windows-claude-code-env` skill does not yet have an entry for this pattern. Carry-forward: add an entry to `~/.claude/skills/windows-claude-code-env/gotchas.md`.

### Gotcha 2 — Clause count non-determinism between dry-run and --execute (bayesian-eval-discipline)

The dry-run (`skill init` without `--execute`) produced 20 clauses; the `--execute` run produced 24 clauses (+4, ~17% drift). Root cause: the extractor is stochastic (LLM with no seed). Both clause counts are defensible; the --execute run is canonical (persisted to evidence.db).

Implication: the `skill init` call should be treated as a one-time import operation. SHA-gated re-import (refuse to re-extract if source SHA is unchanged) would prevent unintentional clause set drift across sessions.

### Gotcha 3 — Ablation vs. aggregation sub-reason discrepancy (operator-confusing, not a bug)

Runner layer reports `UNMEASURED(tier2_uncalibrated)`. Aggregation layer (`run evaluate-skill`) reports `sub_reason: no_data`. Both are correct:
- `tier2_uncalibrated`: runner refused to write uncalibrated verdict evidence.
- `no_data`: aggregator sees zero verdict rows in evidence.db.

The two-layer labeling is consistent by design but confusing to operators who expect the runner-layer reason to surface in the report. Carry-forward: surface `tier2_uncalibrated` as the aggregation sub-reason when all run evidence for a clause was refused on calibration grounds (rather than overriding with `no_data`).

---

## 5. Goal Exit Framing — What the Screen Tells Us

### The goal frame and what it was testing

The Phase 4.4 goal criterion was: "≥1 PASSED AND ≥1 FAILED-or-UNMEASURED on each skill." This was a discrimination test — does the harness correctly classify distinct clause outcomes, and can it produce at least one measured result on a real skill?

The screen result — 0 PASSED, 62 UNMEASURED — did not meet the criterion. It revealed a real v0.1 scope limit: the oracle surface is 4 Tier-1 scorers (`verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`) plus Tier-2 deferred (D22, no live calibration in v0.1). No behavioral skill currently in the skill library uses an axis that matches these 4 names. The dogfooded skills express domain-specific axes that are mechanically countable in principle but not yet registered.

### What A62 says about UNMEASURED discrimination

Per Appendix G (A62) and PRD §8 v1.1: "discriminate UNMEASURED-with-cited-reason" is itself a form of clause-level signal. The harness currently discriminates:

- `UNMEASURED(no_data)` — aggregation layer: zero admissible verdict rows
- `UNMEASURED(underpowered)` — N < N_min floor (verified in Phase 3.6 §19 #2)
- `UNMEASURED(falsifying_case_stale)` — §15.1 auto-flip on metric version change (verified in Phase 3.6 §19 #7)
- `UNMEASURED(tier2_uncalibrated)` — runner layer: axis not in scorer registry OR no calibration record
- `CONFOUNDED` — distinct from UNMEASURED; confound events exclude verdicts from aggregation (verified in Phase 3.6 §19 #5)

This discrimination IS the PRD §19 #2 success criterion, which Phase 3.6 verified with green gates. The harness refuses to conflate "not enough samples" with "axis has no oracle" with "evidence was confounded" — three operationally different conditions requiring different operator responses.

### Path B (in flight at time of this writeup)

A parallel agent is working on adding `citation_presence_per_flag` (or a compatible named scorer) to the scorer registry, specifically to align at least one of ai-slop-sentinel's 7 Tier-1-declared axes with the registry. If that scorer lands and is registered under the exact axis name the extractor produces, ≥1 clause on ai-slop-sentinel should reach sampling and potentially produce PASSED or FAILED. This writeup does not block on that outcome.

---

## 6. Carry-Forwards for v0.2

### Tier-1 scorer registry expansion

The 3 dogfooding runs surfaced the following candidate Tier-1 axis names that could be registered as mechanical scorers in v0.1.x or v0.2:

| Skill | Candidate axis | Measurement approach |
|---|---|---|
| ai-slop-sentinel | `citation_presence_per_flag` | Count citations in output per flagged item; compare Full vs Ablated |
| ai-slop-sentinel | `flag_severity_classification_and_citation` | Parse severity label + presence of citation link; binary per flag |
| ai-slop-sentinel | `review_gate_enforcement_coverage` | Count gate-check assertions vs expected gates; ratio |
| bayesian-eval-discipline | `tie_rate_disclosure` | Regex for tie-count field in output; binary presence |
| bayesian-eval-discipline | `n_min_constant_in_code` | AST/regex scan for N_min numeric constant in generated code |
| verbatim-content-subagent-dispatch | `ai_attribution_trailer_presence` | String match for `Co-Authored-By` or equivalent; binary |
| verbatim-content-subagent-dispatch | `fence_collision_prevention` | Detect nested code fence in output; binary absence |

Extractor↔registry coupling question: should the extractor consult registered scorer names when emitting axis names? If yes, the extractor could prefer registered names when a clause is mechanically countable (e.g., emit `citation_presence_per_flag` only if that scorer is registered, otherwise emit a canonical variant). Risk: couples extractor to scorer registry surface, complicates the extractor prompt. Alternative: a post-extraction normalization step maps extractor-emitted names to registered names via a declared alias table.

### Clause count determinism

Extractor is stochastic; dry-run vs --execute count diverged by 17% on bayesian-eval-discipline. Two options: (a) SHA-gated re-import (refuse re-extraction if source SHA unchanged; operator must force-reimport explicitly), or (b) extractor seeding (if/when the Anthropic API supports reproducible sampling). Option (a) is implementable now.

### Windows cp1252 Rich-render guard

Replace Unicode symbols in ablation/evaluate-skill warning footer strings (`⚠`, `→`, `≠`) with ASCII fallbacks, or add a UTF-8 console mode flag at CLI startup (e.g., `reconfigure_for_utf8()` called in `cli/main.py` before any Rich output). Document in `windows-claude-code-env` skill gotchas regardless of fix path.

### Aggregation sub-reason surfacing

Surface `tier2_uncalibrated` in the aggregation report sub-reason when all verdicts for a clause were refused at the runner layer on calibration grounds, rather than overriding to `no_data`. This makes the operator-visible report consistent with the runner-layer classification.

### Tier-2 live calibration ship (D22)

All 39 Tier-2 clauses and the 1 Tier-3 clause across the three skills are structurally unmeasurable without calibrated `(judge_id, axis)` records. D22 (live Tier-2 calibration) resolves this for the behavioral-judgment axes. PRD §19 #3 is currently PARTIAL (verified via fixture, not live judge wiring). D22 is the primary unlocker for skills with >50% Tier-2 clause density.

---

## 7. Verdict — What Does v0.1 Demonstrate?

### The discipline is demonstrated

Phase 3.6 verified all 6 §19 success criteria (5 PASS, 1 PARTIAL). The admissibility gate (A29 VIEW), append-only evidence model, confound handling, provenance fields (A60), byte-stable JSON, and PASSED/UNMEASURED/CONFOUNDED status discrimination all work correctly. 896 tests pass under `pytest -q -m "not live"`. Phase 4.1 found 0 v0.1 blockers across 47 PRD amendments. Phase 4.3 found 0 new security findings; 5 total findings, all PRE-DEFERRED.

The falsifiable-directional-contract discipline (A beats B on axis X; admissibility-gated, append-only evidence; fail-closed via UNMEASURED with cited sub-reason) is implemented, tested, and verified.

### The mechanical discriminator is gated by oracle surface

The PASSED/FAILED discrimination on real extracted skill clauses — the PRD §19 #7 gate — requires at least one axis name that matches a registered Tier-1 scorer. No skill in the current library produces an axis that matches the 4 registered scorer names. This is a v0.1 oracle-surface limit, not a harness defect. The harness correctly refuses to fabricate signal when no scorer can be applied.

The fix is scorer registration, not harness architecture. Adding one scorer (e.g., `citation_presence_per_flag`) under the name the extractor emits should produce ≥1 PASSED or FAILED on ai-slop-sentinel and unblock the Phase 4.4 discrimination criterion.

### v0.1 ships as "harness scaffolding with documented oracle-surface limit"

The v0.1 position: harness scaffolding with correct fail-closed behavior, verified §19 success criteria, and a documented oracle-surface limit (4 Tier-1 scorers, Tier-2 deferred via D22). The limit is honest — surfaced as UNMEASURED with cited reason rather than hidden behind fabricated signal. The architecture is ready for scorer expansion (v0.1.x) and Tier-2 calibration (v0.2 D22) without structural changes.

The 3-skill dogfooding run demonstrated:

1. The pipeline executes end-to-end without hard errors on real skills.
2. BLOCKER-1 correctly fires and refuses to spend budget on unmeasurable axes.
3. The UNMEASURED discrimination (5 sub-reasons) works and is non-trivial.
4. The extractor handles review-discipline, dense-academic, and procedural-directive shapes without vacuity inflation, citation misclassification, or math-claim extraction.
5. The fail-closed behavior (no fabricated PASSED) is the correct thesis for an adversarial evaluation system.

---

## Current State at Writeup (Path B in Flight)

A parallel agent is working on an axis-name gate fix (Path B) to register at least one custom scorer that matches an extracted axis from ai-slop-sentinel. If the scorer lands:
- ai-slop-sentinel should produce ≥1 PASSED or FAILED, satisfying the Phase 4.4 discrimination criterion.
- The cross-skill synthesis above remains valid regardless of that outcome: the root cause (axis-name registration gap) is correctly diagnosed, and the 62-UNMEASURED result is the correct v0.1 outcome given the current oracle surface.

This document does not depend on Path B landing. The synthesis stands on its own as a record of what the v0.1 harness demonstrated against 3 real dogfooded skills.
