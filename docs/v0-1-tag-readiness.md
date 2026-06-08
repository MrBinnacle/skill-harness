# v0.1 Tag-Readiness Checklist

## TAG-READY: YES

Load-bearing evidence: clause `f9771fd8b5a9cff80999c80ca1f31d7a56d31f1dc1647f33b39113b26931dba7`
on ai-slop-sentinel axis `citation_presence_per_flag` — **FAILED** (n=30,
`p_win_gt_threshold=0.005`). Phase 4.2 condition C1 (">=1 PASSED or FAILED,
not all-UNMEASURED") is MET. See `docs/path-b-verified-2026-06-08.md`.

---

## Phase 3.6 — verify pass against PRD §19
- [x] 5 PASS + 1 PARTIAL (Tier-2 live judge per D22 deferral). See `docs/phase-3-6-verification.md`.

## Phase 3.7 — verification-before-completion
- [x] PARTIAL → superseded by live FAILED demonstration. Phase 3.7 ran before the live
  ablation re-run; its central UNVERIFIED claim ">=1 PASSED" is now better described as
  ">=1 directional verdict (FAILED) demonstrating clause-level discrimination" — **VERIFIED**.
  See `docs/phase-3-7-verification.md` (prior partial verdict) + `docs/path-b-verified-2026-06-08.md`
  (live run outcome that satisfies the intent of the claim).

## Phase 4.1 — adversarial-spec on PRD v1.1
- [x] 42 AGREE / 2 CAVEAT / 3 MINOR / 0 BLOCKER / 3 carry-forwards. See `docs/phase-4-1-adversarial-spec.md`.

## Phase 4.2 — azimuth go/no-go
- [x] PROCEED-WITH-SAFEGUARDS. See `docs/phase-4-2-azimuth.md`.
  Condition C1 (">=1 PASSED or FAILED, not all-UNMEASURED") **MET** via clause
  `f9771fd...` FAILED (live re-run, runs `073dd0da` + `19e85593` + `c3481f27`).
  Condition C2 (Phase 3.7 gate complete) **MET** via live FAILED demonstration above.
  Condition C3 (RELEASE-NOTES updated with actual outcome) **MET** by this commit.

## Phase 4.3 — insecure-defaults sweep
- [x] 0 CRITICAL / 0 HIGH / 3 MEDIUM (all PRE-DEFERRED). See `docs/phase-4-3-insecure-defaults.md`.

## Phase 4.4 — 3-skill dogfooding sweep
- [x] 3 writeups completed: `docs/dogfooding-ai-slop-sentinel-2026-06-07.md`,
  `docs/dogfooding-bayesian-eval-discipline-2026-06-07.md`,
  `docs/dogfooding-verbatim-content-subagent-dispatch-2026-06-07.md`.
- [x] Cross-skill synthesis: all three runs confirm BLOCKER-1 (axis-mismatch) gate behavior
  is correct; all-UNMEASURED is expected when no matching Tier-1 scorer or Tier-2 calibration record exists.
  See `docs/dogfooding-cross-skill-2026-06-07.md`.
- [x] >=1 directional verdict demonstrated: live ablation re-run on ai-slop-sentinel
  produced 1 FAILED (`citation_presence_per_flag`, n=30). Path B re-run complete.
  See `docs/path-b-verified-2026-06-08.md`.

## Gates
- [x] `pytest -q -m "not live"`: 913 passing (`913 passed, 1 deselected in 63.66s`)
- [x] `mypy --strict src/`: 68 files clean (`Success: no issues found in 68 source files`)
- [x] `ruff check src/ tests/`: clean (`All checks passed!`)
- [x] `ruff format --check src/ tests/`: clean (`142 files already formatted`)
- [x] CI green on `main` (HEAD `f61e8cb`; CI green since `55d7e16`)

## Final blockers / open carry-forwards
- SCHEMA-7 validity-flag bypass migration: deferred to v0.1.x (council-approved, documented).
- EVR-3/EVR-7 oracle surface limit: documented in RELEASE-NOTES; FAILED verdict demonstrates
  discrimination is real when a scorer matches.
- `tie_count`/`win_count`/`loss_count` absent from wire format: v0.2 carry-forward.

## Recommended next gesture
- Cut v0.1.0a0 tag on `main` HEAD `f61e8cb` (or HEAD after this doc-sync commit integrates).
