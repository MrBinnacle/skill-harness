# Phase 4.2 — Azimuth Go/No-Go: v0.1 Tag Readiness

**Date**: 2026-06-07
**Mode**: DEEP (public-facing release, limited reversibility, multiple unknown downstream consumers)
**Domain**: Product launch (Layer 3 path 2 — `product-launch-azimuth.md`)
**Routing basis**: Public GitHub repo + version commitment + oracle-surface gap creates non-trivial adoption-disappointment risk at unknown scale
**M4 pre-check**: The AI assistant built, maintained, and advocated for this release across all sessions. M4 fires on the assistant. Q2 [ACCOUNTABILITY] = assistant bears zero consequences for a bad tag. Q4 [DISSENT] = recommendation has not been challenged by any external human reviewer; all adversarial review was AI-seat council fires. This is a structural YELLOW signal, not RED (multi-model councils, human approval at gate points, systematic cross-checking). Stated per DEEP discipline; does not disqualify the analysis.

---

## Azimuth Verdict

**PROCEED WITH SAFEGUARDS** — the discipline is real, the integrity guarantees are tested, and the oracle-surface limit is honestly documented; but tagging without completing the one-PASSED verification run ships a harness whose primary value claim (clause-level signal on real skills) is asserted, not demonstrated, at time of release.

## Recommended Decision

**PROCEED WITH SAFEGUARDS**

Rationale: v0.1 delivers a complete, tested, fail-closed evidentiary harness with 913 passing tests, 0 blockers across all pre-launch sweeps, and honest RELEASE-NOTES that document the oracle-surface limit. The two required safeguards (ablation re-run confirming >= 1 PASSED + RELEASE-NOTES update) are one short session of work and do not require architectural changes. Shipping without them converts an honest limitation into an undocumented gap — the single structural change that would make the adoption-disappointment risk acute rather than managed.

## Confidence Level

**Medium** — Load-bearing assumption "harness produces demonstrable clause-level signal on real skills" is UNSUPPORTED at current tag state (scorer was added but ablation re-run not executed). Per M10 confidence ceiling rule: UNSUPPORTED load-bearing assumption caps confidence at MEDIUM regardless of all other evidence quality. All other evidence (invariants, tests, security sweep, adversarial spec) is HIGH-confidence.

---

## Critical Risks

**1. Oracle surface + adoption disappointment (SEVERITY: HIGH)**
The 3-skill dogfooding run returned 62 UNMEASURED, 0 PASSED, 0 FAILED. The scorer fix (commit `4583669`) is in the tree but the ablation re-run confirming it produces >= 1 PASSED has not been executed. Every operator who runs `skill init` + `run evaluate-skill` on their own skill will see all-UNMEASURED unless they happen to use one of 5 registered scorer axis names or bring their own calibrated Tier-2 judge. This is documented in RELEASE-NOTES, but documentation of a limitation is not the same as demonstrated mitigations. An operator seeing all-UNMEASURED with no PASSED reference point has no evidence the harness works at all.
Risk grade: HIGH / Pre-tag likelihood: CERTAIN (absent ablation re-run) / CERTAIN (absent scorer expansion).

**2. SCHEMA-7 bypass: `mechanical_validity_test_passed` not enforced by DB trigger (SEVERITY: MEDIUM)**
The pre-tag launch council identified that `mechanical_validity_test_passed = 1` can be set to any value in the schema; the DB trigger enforcing the §12.1 validity gate does not yet exist. An operator registering a custom scorer can set `mechanical_validity_test_passed = 1` without passing the offline test suite, self-certifying a Tier-1 metric. Explicitly deferred to v0.1.x with council agreement; documented in RELEASE-NOTES. Mitigation: local-trust scope (single operator, their own integrity), and the harness is explicit that this path exists. Not a blocker given v0.1 local-trust model, but the deferred trigger migration is load-bearing for v0.1.x.

**3. M4 structural: no external human review of the product claim (SEVERITY: LOW-MEDIUM)**
The EVR-6 claim ("evidentiary discipline as the novel contribution") is well-framed against academic prior art (Sclar et al., Longpre et al., JoPA/Chang). However no independent human practitioner in the eval domain has reviewed the claim or the implementation. All adversarial review was AI-seat council fires. The harness could be correctly implemented against a subtly wrong or over-scoped claim and neither the councils nor the AI sessions would surface it. This is a structural gap, not an evidence gap — it cannot be closed by more AI review.

## Weak Assumptions

- **"Harness produces demonstrable clause-level signal on real skills"**: UNSUPPORTED at current tag state. Scorer was added (`citation_presence_per_flag`, commit `4583669`) but the ablation re-run confirming it produces >= 1 PASSED/FAILED on ai-slop-sentinel has not been executed. The 3-skill dogfooding run established 0 PASSED / 62 UNMEASURED as the baseline. This assumption is the central claim of a v0.1 evaluation framework.

- **"RELEASE-NOTES documentation is sufficient to set operator expectations"**: PARTIAL. RELEASE-NOTES honestly documents the oracle-surface limit and workaround. But documentation-of-limitation is weaker than demonstration-of-limitation-plus-path-forward. An operator who reads the RELEASE-NOTES will understand the constraint; an operator who does not may conclude the harness is broken.

## Falsifiers

- **"Oracle-surface limit is manageable"**: falsifier = any two of the three dogfooded skills return all-UNMEASURED after the v0.1.x scorer expansion. If both ai-slop-sentinel and bayesian-eval-discipline remain at 0 PASSED after targeted scorer registration, the claim that the limit is addressable by extension (not architecture) is falsified.

- **"EVR-6 evidentiary discipline claim is defensible against public scrutiny"**: falsifier = an independent practitioner in the LLM eval domain identifies a published system that provides the same three disciplines (directional-only, admissibility-gated, append-only provenance) predating the P4 search. This would not invalidate the implementation, but would invalidate the "zero hits" claim in PRD §1.

## Likely Failure Paths

**Chain 1: Adoption-disappointment → reputational damage**
Trigger: Operator runs `skill init + run evaluate-skill` on any skill whose axes do not match the 5 registered scorers.
Cascade: All-UNMEASURED result with no PASSED reference. Operator concludes "harness doesn't work" — does not read RELEASE-NOTES oracle-surface-limit section.
Visible failure: GitHub issue "why are all clauses UNMEASURED?" or "this doesn't work on real skills."
Business cost: Early adopters form a "doesn't work" prior that is hard to reverse; chills future adoption; damages credibility of the evidentiary-discipline claim.

**Chain 2: SCHEMA-7 bypass + operator self-certification**
Trigger: An operator (or downstream tool) registers a custom scorer by directly writing `mechanical_validity_test_passed = 1` without running the offline test suite.
Cascade: A non-mechanical scorer (e.g., one making network calls) enters Tier-1 with no guard; verdicts based on it are treated as admissible.
Visible failure: Silent PASSED verdicts on non-deterministic evidence; replication fails.
Business cost: Invalidates the append-only audit trail's guarantees; undermines the "evidentiary discipline" claim if a published consumer demonstrates non-reproducibility.

**Chain 3: No PASSED demonstration + EVR-3/EVR-7 honest carry-forward = "this is theory, not practice"**
Trigger: v0.1 ships with 0 demonstrated PASSED verdicts + EVR-3/EVR-7 oracle surface admitted as limitations.
Cascade: External reviewer concludes the framework exists only at the abstraction layer and does not produce measurable signal on any real skill in the library.
Visible failure: "The harness has no proven examples" critique in public forum or blog post.
Business cost: Reputational ceiling on the EVR-6 claim; converts a "novel evidentiary discipline" claim into a "promising but undemonstrated approach."

## Interaction Effects

**Chain 1 + Chain 3**: Adoption disappointment fires AND no PASSED demonstration exists in the release. The recovery path for Chain 1 ("read the RELEASE-NOTES workaround") is weakened when there is no positive example to point to. If the operator can see "ai-slop-sentinel clause 0 = PASSED" in the repo, they have a reference point. Without it, the workaround is theoretical.

## Highest-Leverage Fixes

**Safeguard 1 (REQUIRED before tag)**: Execute ablation re-run on ai-slop-sentinel with the `citation_presence_per_flag` scorer in place. Confirm >= 1 clause reaches PASSED or FAILED. Update RELEASE-NOTES with the actual result. This converts the central claim from asserted to demonstrated, and converts Chain 1/Chain 3 from probable to unlikely.
- Estimated effort: 1 session (scorer is already in tree; requires `run ablation --execute` + `run evaluate-skill` + writeup)
- Blocks if: scorer produces all-UNMEASURED due to axis-name mismatch at registration or runtime — which would be a BLOCKER-level finding requiring scorer alignment fix first

**Safeguard 2 (REQUIRED before tag)**: Phase 3.7 (`superpowers:verification-before-completion`) gate — marked PENDING in `docs/v0-1-tag-readiness.md`. The checklist item reads "(Pending — fires after Path B scorer outcome resolved.)" Tag must not cut before this fires and clears.

**Safeguard 3 (STRONG RECOMMENDATION, not hard blocker)**: Add one sentence to RELEASE-NOTES under "Oracle surface limit": "The `citation_presence_per_flag` scorer added in v0.1 (commit 4583669) was designed to produce a demonstrable PASSED result on ai-slop-sentinel clause 0; the ablation run confirming this is at `docs/[ablation-writeup].md`." This closes the documentation gap regardless of the result.

## Early Warning Indicators

- First GitHub issue about "all UNMEASURED" within 7 days of tag: indicates RELEASE-NOTES is not surfacing the oracle-surface-limit explanation effectively at operator first contact. Response: add a prominent Quick Start FAQ section.
- No community scorer registrations within 30 days of tag: indicates the operator-extension path is more friction than expected. Response: ship v0.1.x with 2-3 additional registered scorers targeting common axis names.

## Structural Strengths

- **913 tests pass, 0 new regressions** since pre-tag fix-sprint. The test suite exercises all 8 load-bearing invariants with property-based, unit, and integration tests. This is a genuine structural strength — failures in the core evidentiary guarantees would surface here.
- **0 blockers across all pre-launch sweeps**: adversarial-spec (47 amendments, 0 DISAGREE-MAJOR), insecure-defaults (5 findings, all PRE-DEFERRED), pre-tag launch council (0 unresolved BLOCKERs). The integrity guarantees are as complete as a v0.1 can be.
- **Honest RELEASE-NOTES**: the oracle-surface limit, Windows cp1252 workaround, extractor stochasticity, and `--daily-cap` scope are all documented. Operators who read the RELEASE-NOTES will not be surprised. This reduces Chain 1 severity from "harness is broken" to "harness requires scorer setup" — which is a manageable operator expectation.
- **Fail-closed behavior is the correct thesis**: 0 fabricated PASSED results in 62 UNMEASURED runs is the right behavior for an adversarial audit system. This is a strength to lead with publicly, not a limitation to apologize for.

---

## Reversibility Analysis

A git tag on a public GitHub repo is limited-reversibility: the tag can be deleted, but:
- GitHub stars, forks, and watchers will have seen v0.1 at tag time
- Any downstream tooling that pins to the tag will need to update
- Search results and cached references persist

**v0.1.0a0 (alpha pre-release designation)** is partially protective: the `a0` suffix signals "not stable/production" to Python tooling and semver-aware consumers. This reduces the reversal cost relative to `v0.1.0` proper. The release is correctly staged as alpha.

**Tag yanking scenario**: if a critical issue surfaces post-tag (e.g., the `citation_presence_per_flag` scorer produces false PASSED verdicts on real content), the tag can be yanked and replaced with `v0.1.0a1`. This is the right escape path, and the cost is proportional to how many consumers have pinned `v0.1.0a0` in the days between tag and yank.

---

## Pre-Commitment Analysis

| Assumption | Classification | Notes |
|---|---|---|
| v0.1 ships complete harness scaffolding (5 tracks, all §19 success criteria verified) | SUPPORTED | 913 tests, 5 PASS + 1 PARTIAL on §19 criteria (Phase 3.6) |
| EVR-6 "evidentiary discipline" claim is defensible | PARTIAL | PRD §1 cites prior art correctly; no independent human practitioner review |
| Harness produces demonstrable clause-level signal on real skills | UNSUPPORTED at tag | Scorer added but ablation re-run not executed; 0 PASSED across 3 dogfooded skills at synthesis writeup time |
| Oracle-surface limit is honestly documented | SUPPORTED | RELEASE-NOTES §"Known limitations" section is accurate and specific |
| SCHEMA-7 bypass is acceptable for local-trust v0.1 | SUPPORTED (scoped) | Explicitly council-approved deferral; local-trust model is honest scope statement |
| All security and invariant guarantees hold | SUPPORTED | Phase 4.3: 0 CRITICAL/HIGH; all MEDIUM PRE-DEFERRED |

---

## Incentive Alignment Scan

| Actor | Incentive | Aligned with Release Readiness? |
|---|---|---|
| AI assistant (all sessions) | Ship what was built; complete the arc | YELLOW — bears zero consequences for poor reception; no external correction; systematic AI councils mitigate but do not eliminate |
| Human operator (project owner) | Complete v0.1 milestone; public artifact | ALIGNED conditionally — owner was in-loop at all gate points; approved all major decisions |
| Downstream consumers (unknown) | Working harness for their skills | NOT ALIGNED with current state — no demonstrated PASSED verdict to establish harness capability |

Deadline politics: no external deadline pressure detected. The tag is self-imposed and can be delayed without external cost. This is structurally good — the conditions for PROCEED WITH SAFEGUARDS are met (specific, actionable, bounded scope).

---

## Readiness Assessment (Product Launch Template)

| Gate | Status | Notes |
|---|---|---|
| Feature functionally complete | READY | All 5 tracks, all 6 CLI commands, full wire format |
| Performance tested at launch spike | N/A | Local-trust, single-operator; no scale concern |
| Security review complete | READY | Phase 4.3: 0 CRITICAL/0 HIGH; all findings PRE-DEFERRED |
| Legal/compliance reviewed | N/A | Open-source; no regulatory scope |
| Support docs complete | PARTIAL | RELEASE-NOTES honest; no PASSED demo example yet |
| Rollback procedure defined | READY | Tag yanking + alpha designation provides escape path |
| Launch metrics configured | N/A | No telemetry in v0.1 (single operator) |
| Communication plan finalized | N/A | No press/marketing |
| Phase 3.7 verification gate | NOT READY | Explicitly marked PENDING in tag-readiness checklist |

---

## Conditions (PROCEED WITH SAFEGUARDS requires all 3)

1. **[REQUIRED]** Execute `run ablation --execute` + `run evaluate-skill` on ai-slop-sentinel with the `citation_presence_per_flag` scorer registered. Confirm the ablation re-run completes and produces >= 1 PASSED or FAILED verdict (not all-UNMEASURED). Document the result. Update RELEASE-NOTES with the actual outcome. If the result is all-UNMEASURED, diagnose the axis-name alignment gap and fix before tagging.

2. **[REQUIRED]** Complete Phase 3.7 (`superpowers:verification-before-completion` gate). This is explicitly marked PENDING in `docs/v0-1-tag-readiness.md`. Tag must not cut before this fires and clears.

3. **[STRONGLY RECOMMENDED]** Update RELEASE-NOTES to reference the ablation re-run writeup by path (doc artifact, not just a prose claim). This closes the documentation gap created by the session-limit recovery of the Path B scorer-add agent and ensures the oracle-surface limit section points to a positive example, not just a workaround recipe.

---

## Recommended Next Gesture

Run `run ablation --execute` on ai-slop-sentinel with the clause scorer now in tree, confirm >= 1 clause reaches PASSED, add the writeup to `docs/`, complete Phase 3.7, then cut the tag — the evidence record and the claimed evidentiary discipline will then be aligned.

---

## Gate Evidence

| Gate | Result |
|---|---|
| `pytest -q -m "not live"` | **913 passed, 1 deselected** (74.52s) |
| `mypy --strict src/` | **68 files, 0 issues** |
| `ruff check src/ tests/` | **All checks passed** |
| `ruff format --check src/ tests/` | **142 files already formatted** |

Worktree: `C:\Users\mlpgr\2026_Projects\youwontdoit\.claude\worktrees\agent-a212fa3d71914f7e1`
Branch: `main`
HEAD at analysis time: `4583669`

---

## Halt Triggers Evaluated

- Azimuth skill available: YES
- Evidence materially sufficient for verdict: YES (all source documents read in full)
- Verdict is NO-GO: NO (verdict is PROCEED WITH SAFEGUARDS; no orchestrator adjudication required)
- None of the halt conditions apply. Analysis complete.
