# Phase 3.7 — Verification-Before-Completion: v0.1 Tag-Readiness

**Date**: 2026-06-07
**Harness HEAD**: `4583669`
**Branch**: `main` (worktree: `agent-adfee1291e51e194d`)
**Scope**: 10 load-bearing claims from RELEASE-NOTES-v0.1.md + docs/v0-1-tag-readiness.md
**Discipline**: `superpowers:verification-before-completion` — evidence before assertions; behavioral
testing beats self-reporting; "should" is not evidence.

---

## Per-Claim Evidence Table

| # | Claim | Evidence (file:line / SHA) | Verification command run this session | Verdict |
|---|---|---|---|---|
| 1 | "914 tests passing" (gates evidence) | Pytest output: `913 passed, 1 deselected in 63.66s` — run this session on `agent-adfee1291e51e194d` | `python -m pytest -q -m "not live"` (this session) | **PARTIAL** — 913, not 914; count delta from `4583669` commit message ("All 4 gates green: 913 tests pass") is consistent with worktree state; tag-readiness checklist cites 896 (pre-fix-sprint baseline). 913 is the fresh verified count. |
| 2 | "mypy --strict 68 source files clean" | mypy output: `Success: no issues found in 68 source files` — run this session | `python -m mypy --strict src/` (this session) | **VERIFIED** — 68 files, 0 issues, exit 0. |
| 3 | "ruff check + format clean" | ruff check: `All checks passed!`; ruff format: `142 files already formatted` — run this session | `python -m ruff check src/ tests/` + `ruff format --check src/ tests/` (this session) | **VERIFIED** — both clean, exit 0. |
| 4 | "CI green on main" | `docs/v0-1-tag-readiness.md` line 31: "CI green on `main` since `55d7e16`". Post-fix-sprint commit `3f6b0a9` on main. No CI output available in this session (no network call). | CI log inspection (GitHub Actions) — not run this session (out of scope, no live network) | **PARTIAL** — last recorded green at `55d7e16`; `3f6b0a9` and `4583669` land on main after that marker. CI green state is self-reported in the checklist, not freshly observed. Would require GitHub Actions inspection to confirm current state. |
| 5 | "All 5 tracks (A–E) implemented per PRD §18 CLI surface" | RELEASE-NOTES-v0.1.md lines 14-21: 5-track table. RELEASE-NOTES lines 55-66: 6 CLI commands listed. Phase 3.6 verification doc: all §19 criteria exercised via CLI. Commit log: Track A (`722cd2f`), Track E (`32f3ad4`, `722cd2f`), fix-sprint (`3f6b0a9`). | `run evaluate-skill`, `diff skill`, `freeze`, `calibrate` all exercised in Phase 3.6 fixtures (docs/phase-3-6-verification.md). | **VERIFIED** — CLI surface matches §18; exercise confirmed via Phase 3.6 CliRunner tests (913 passing). |
| 6 | "PRD v1.1 doc-lock complete (47 amendments)" | PRD.md header comment: "v1.1 changelog: 47 amendments applied (45 from Phase 3.5 audit + 2 from Appendix G)". Commit `97fd7f2`: "docs(prd): v1.1 doc-lock — 47 amendments applied". | File header inspection (this session) + git log | **VERIFIED** — 47 amendments recorded in PRD.md header, traceable to `97fd7f2`. |
| 7 | "Pre-tag launch council fired (9 seats); 2 BLOCKERs cleared in fix-sprint" | Commit `3f6b0a9` body: closes BLOCKER OPERATOR-DX-1 + full fix-sprint enumeration. `docs/COUNCIL_FINDINGS.md` Appendices cover pre-tag council fires. | Git log + commit body inspection (this session) | **VERIFIED** — `3f6b0a9` commits to clearing both BLOCKER findings; fix-sprint entries named in commit body. |
| 8 | "≥1 PASSED clause demonstrated on a dogfooded skill" (goal exit criterion) | `docs/dogfooding-cross-skill-2026-06-07.md` §2: "Universal outcome: 0 PASSED, 0 FAILED, 62 UNMEASURED." Commit `4583669` body: "NOTE: this rescue does NOT include the scorer-add agent's planned writeup or ablation re-run verification. Goal-screen '≥1 PASSED' remains unverified at v0.1 tag." | No ablation re-run was performed (scorer-add agent hit session limit; rescue commit is partial). | **UNVERIFIED** — No PASSED demonstration on any dogfooded skill exists in evidence. The rescue commit `4583669` broadened the flag-regex for `citation_presence_per_flag` but did NOT execute a re-run or produce verdicts. This is the central gap. |
| 9 | "Cross-skill clause-level signal: distinguish UNMEASURED-with-cited-reason" | `docs/dogfooding-cross-skill-2026-06-07.md` §5: 5 distinct sub-reasons documented (`no_data`, `underpowered`, `falsifying_case_stale`, `tier2_uncalibrated`, `CONFOUNDED`). Phase 3.6 §19 #2 and #5: UNMEASURED vs CONFOUNDED discrimination verified with exit-code semantics. | Phase 3.6 verification doc (prior session) + dogfooding cross-skill writeup (prior session). | **VERIFIED** — discrimination implemented, tested (913 passing), and demonstrated on 62 real extracted clauses. |
| 10 | "Honest oracle-surface limit documentation in RELEASE-NOTES" | RELEASE-NOTES-v0.1.md lines 116-131: "Oracle surface limit" section explicitly states: 5 Tier-1 scorers, named axes, all-UNMEASURED expected when no matcher. Line 127-130: "all three dogfooding runs returned all-UNMEASURED... Path B targets at least one PASSED demonstration before final tag." | File inspection (this session) | **VERIFIED** — RELEASE-NOTES accurately states the oracle-surface limit and explicitly flags ≥1 PASSED as unresolved ("before final tag"). |

---

## Gate Evidence (Fresh, This Session)

| Gate | Command run | Output |
|---|---|---|
| `pytest -q -m "not live"` | Run this session | `913 passed, 1 deselected in 63.66s` — exit 0 |
| `mypy --strict src/` | Run this session | `Success: no issues found in 68 source files` — exit 0 |
| `ruff check src/ tests/` | Run this session | `All checks passed!` — exit 0 |
| `ruff format --check src/ tests/` | Run this session | `142 files already formatted` — exit 0 |

---

## Overall Verdict: PARTIAL

The v0.1 harness is well-built and honestly documented. Eight of ten load-bearing claims are either VERIFIED or PARTIAL with stated-scope reasons. The discipline flags exactly one UNVERIFIED claim and one PARTIAL (CI) that require attention before the tag is clean.

**Central gap — Claim 8 (≥1 PASSED)**: The goal exit criterion for v0.1 dogfooding is "≥1 PASSED clause demonstrated on a dogfooded skill." This criterion is **UNVERIFIED**. The Path B scorer-add agent (`4583669`) broadened the `citation_presence_per_flag` regex but hit its session limit before completing the ablation re-run and writeup. No admissible verdict rows have been written to evidence.db for the modified scorer. The RELEASE-NOTES honestly discloses this ("Path B targets at least one PASSED demonstration before final tag"), which is the only thing preventing this from being a misrepresentation claim — but honest disclosure does not satisfy the criterion.

The discipline: "behavioral testing beats self-reporting. The model saying 'Done' is not evidence." A rescue commit that edits a regex is not evidence that the regex produces correct verdicts. A re-run that produces ≥1 PASSED verdict, captured in a dogfooding writeup, is evidence.

**Secondary gap — Claim 1 (test count)**: The claim "914 tests passing" as stated in the briefing does not match the fresh gate result (913). This is a minor count discrepancy, not a suite failure. The checklist's earlier "896" baseline was pre-fix-sprint; 913 is the current verified count.

**CI gap — Claim 4**: CI green is stated in the checklist but not freshly observable in this session (no network). This is a scope gap, not an observed failure.

---

## Recommended Next Verification Action

**To convert Claim 8 UNVERIFIED → VERIFIED:**

1. Run `skill init ~/.claude/skills/ai-slop-sentinel/SKILL.md --execute` in the harness against a fresh evidence.db in the agent-adfee1291e51e194d worktree.
2. Run `run ablation <skill_id> --execute --max-usd 5` — this should now route `citation_presence_per_flag` clauses through the broadened scorer since `4583669` registers it under that exact axis name.
3. Run `run evaluate-skill <skill_id> --format=json` — inspect the vector for ≥1 PASSED clause.
4. If PASSED is observed: write a brief dogfooding writeup (5–10 lines confirming the verdict, clause_id, axis, posterior mean). Update `docs/v0-1-tag-readiness.md` Phase 4.4 checkbox.
5. If still 0 PASSED: the scorer axis name emitted by the extractor may not exactly match the registered name `citation_presence_per_flag`. Run `run evaluate-skill --format=json` and inspect `sub_reason` to confirm whether the gate is still `tier2_uncalibrated` (axis mismatch) or has advanced to `underpowered` (sampling began but N too low).

This is the one action separating "PARTIAL" from "VERIFIED" for the v0.1 tag.

---

## Halt-Triggers Evaluated

- Discipline skill available: YES (`superpowers:verification-before-completion` loaded).
- Claim-set materially complete: YES (10 claims from briefing, all evaluated).
- Live API calls required to verify: Claim 4 (CI) requires GitHub Actions inspection — scoped as PARTIAL, not UNVERIFIED. No live API calls were made or required for the other 9 claims.
- No halt triggered.
