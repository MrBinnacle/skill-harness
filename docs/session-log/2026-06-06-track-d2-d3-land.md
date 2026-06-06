# 2026-06-06 · track-d2-d3-land

**Phase**: Phase 2 — Track D (D.2 landed, D.3 built+reviewed+fixed+landed → Track D COMPLETE)
**Sources of truth read at start**: PRD@7c6f5f9 · PLAN@8006cac · COUNCIL_FINDINGS@8f20fe0 · checkpoint@fccbce5
**Model**: mixed (Opus 4.7 orchestrator + council/review seats; Sonnet 4.6 implementers)

## Council fires this session

- Fire: 2026-06-06 D.3 re-review (post-implementation two-stage) · seats: SPEC-COMPLIANCE, TEST-ARCH, RELIABILITY (opus, isolated, cross-talk + disposition schema) · findings: 2 BLOCKER (A52 double-spend stub, A42 daily-cap unwired) + 4 MAJOR + minors · disposition: `docs/dispatch/track-d3-fix-brief.md`.
- Fire: 2026-06-06 A51 micro-council (ratification) · seats: OPERATOR-DX, RELIABILITY, SECURITY · outcome: **RATIFY-WITH-AMENDMENT, 3-0** — dry-run MAY open evidence.db read-only via a new sanctioned `open_evidence_readonly()` (mode=ro, query_only=ON, no apply_pending, raises-not-creates) · recorded in `track-d3-fix-brief.md`.
- D.3 initial build: no fire (CLI set locked PRD §18 + A51/A52 pre-dispositioned → routine implementation per CLAUDE.md).

## Decisions made

- Landed D.2 as one squashed feat commit + docs (cherry-pick `-n a84fe85 8482f5e`; D.1 trees verified tree-identical `6f32a4c`) · anchors: PLAN "TRACK D", COUNCIL_FINDINGS A39–A52.
- D.3 BLOCKER fixes are real-in-production, verified by reading the new tests UNPATCHED (not trusting the agent's green) — the green-tests-mask-stubbed-branches pattern recurred from D.2 · anchors: CLAUDE.md verification §6, append-only/UNMEASURED invariants.
- A51 "no DB conn" ruled = "no writable conn / no client / no key / no call / no write"; read-only enumeration permitted. Faithful to the brief's own per-clause-table requirement; ratified by micro-council · anchors: COUNCIL_FINDINGS A51/A12/A22/A23/A28, brief §D.3.
- Accepted v0.1 limitation: `_find_incomplete_run` is skill_id-agnostic (no `skill_id` on `run_progress`); conservative (over-warns, never double-spends). Fix deferred as CF-D3-1 · anchors: A25 (no cross-DB join), A40/A52.

## Artifacts produced

- `docs/dispatch/track-d3-fix-brief.md` · D.3 disposition + fix plan + A51 ratification + verification · committed `0c336ac`.
- `src/skill_harness/cli/main.py` (run ablation), `src/skill_harness/storage/migrations.py` (`open_evidence_readonly`), `tests/ablation/test_cli_d3_fixes.py`, `tests/ablation/test_cli_run_ablation.py` · committed `a0bd546`.
- Track D landed on origin: D.2 `cda0f65`+`4535c79`; D.3 `a0bd546`+`0c336ac`. Gates on main: 633 passed / 1 deselected, mypy --strict clean, ruff clean.

## Values decisions queued / resolved

- A51 text amendment ("no DB conn" → "no writable conn / no migration apply; MAY open read-only via sanctioned entry") queued for the doc-lock PR — not applied piecemeal.
- C1 (tie encoding) still data-blocked; C2 (operator-self-label) remains REFUSE. No new values decisions.

## Open questions for next session

- CF-D3-1: make `_find_incomplete_run` skill-accurate (two-step runtime→evidence lookup, no schema change) — owner: track (D follow-up or Track E entry).
- TA-4 (per-verdict family_size on RunConfig, Track E re-derives) + SEC (re-audit output_text→judge-prompt interpolation when Tier-2 judge wired) — owner: Track E / judge-wiring.

## Next gate

Track D end-of-track **ai-slop-sentinel review** (fresh-context, all 3 subtracks) per PLAN.md, then Track E (aggregation/reporting) — now unblocked (A + D green).
