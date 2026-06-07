# v0.1 Tag-Readiness Checklist

## Phase 3.6 — verify pass against PRD §19
- [x] 5 PASS + 1 PARTIAL (Tier-2 live judge per D22 deferral). See `docs/phase-3-6-verification.md`.

## Phase 3.7 — verification-before-completion
- [ ] (Pending — fires after Path B scorer outcome resolved.)

## Phase 4.1 — adversarial-spec on PRD v1.1
- [x] 42 AGREE / 2 CAVEAT / 3 MINOR / 0 BLOCKER / 3 carry-forwards. See `docs/phase-4-1-adversarial-spec.md`.

## Phase 4.2 — preliminary azimuth
- [ ] (Pending — fires after 3.7 + cross-skill synthesis + scorer outcome.)

## Phase 4.3 — insecure-defaults sweep
- [x] 0 CRITICAL / 0 HIGH / 3 MEDIUM (all PRE-DEFERRED). See `docs/phase-4-3-insecure-defaults.md`.

## Phase 4.4 — 3-skill dogfooding sweep
- [x] 3 writeups completed: `docs/dogfooding-ai-slop-sentinel-2026-06-07.md`,
  `docs/dogfooding-bayesian-eval-discipline-2026-06-07.md`,
  `docs/dogfooding-verbatim-content-subagent-dispatch-2026-06-07.md`.
- [x] Cross-skill synthesis: all three runs confirm BLOCKER-1 (axis-mismatch) gate behavior
  is correct; all-UNMEASURED is expected when no matching Tier-1 scorer or Tier-2 calibration record exists.
- [ ] ≥1 PASSED demonstration: (Pending — Path B scorer-add agent in flight.)

## Gates
- [x] `pytest -q -m "not live"`: 896 passing (last run: `896 passed, 1 deselected in 50.50s`)
- [x] `mypy --strict src/`: 67 files clean (`Success: no issues found in 67 source files`)
- [x] `ruff check src/ tests/`: clean (`All checks passed!`)
- [x] `ruff format --check src/ tests/`: clean (`140 files already formatted`)
- [x] CI green on `main` since `55d7e16` (ci.yml alignment fix)

## Final blockers / open carry-forwards
- (Filled by Phase 4.2 azimuth.)

## Recommended next gesture
- (Filled by Phase 4.2 azimuth.)
