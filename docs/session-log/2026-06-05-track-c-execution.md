# 2026-06-05 · track-c-execution

**Phase**: Phase 2 — Track C dispatch sequence (brief → C.1 → C.2 → C.3 → C.4 → slop review)
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@(post-Appendix-D, refreshed in-session) · checkpoint@(post-Pre-Track-C-fire, local)
**Model**: Opus 4.7 (orchestrator) + Sonnet 4.6 × 4 (Track C subagents) + Sonnet 4.6 (slop reviewer)
**User invocation**: "proeced [sic]" → "Execute as recommended"

## Context

Continuation of the prior session ("SOP → Track B triage → Pre-Track-C council fire") which had closed out at `70680bb` with Pre-Track-C council adopted (A31–A38) and C2 surfaced. User then re-engaged with "Execute as recommended" which the orchestrator interpreted as: proceed with the recommended Track C dispatch sequence per `feedback-non-technical-sme` + `feedback-route-to-most-expert` (C2 default REFUSE operative; Track C subdivided per C.1–C.4 per `superpowers:subagent-driven-development`).

## Decisions made

### Track C brief drafted + committed before any dispatch

Per `verbatim-content-subagent-dispatch` discipline. Embedded:
- PLAN.md §Track C verbatim (post-Pre-Track-C-council expansion)
- COUNCIL_FINDINGS A31–A38 verbatim
- Per-subtrack subdivision with exit criteria + drivers + out-of-scope guard rails
- Halt-on-ambiguity discipline with named ambiguity classes
- Return contract (READY_FOR_COMMIT / NEEDS_CONTEXT / BLOCKED)

Brief at `docs/dispatch/track-c-brief.md`, committed `64896c5`. Analogous to `track-a-brief.md` precedent.

### Subdivision into 4 sequential subtracks

Orchestrator call per `feedback-non-technical-sme` (technical sequencing). Rationale: Track C scope was substantially expanded by Pre-Track-C council (+8 driving findings A31–A38 on top of A5/A6/A7/A14). Subdivision lowered per-subagent context burn + made the cherry-pick + review cycle tractable. Sequential (not parallel) because:
- C.2 + C.3 + C.4 all touch the calibration data model
- C.3 + C.4 both extend `calibrate()` command
- C.4 fits length regression that depends on C.2's JudgeVerdict
- Parallel branches would conflict; sequential cherry-picks compose cleanly

### Subtrack sequencing

- **C.1** (`b1214c6`) — Tier-1 metric registry + 4 honestly-mechanical metrics + offline validity tests. Drivers A14, A33. +67 tests.
- **C.2** (`7774e23`) — Tier-2 judge module + position-swap 9-cell + 7-layer adversarial injection defense. Drivers A31, A32, A35-prompt-half, A38 layers 1–4 + 7. +88 tests.
- **C.3** (`b5a64e9`) — Calibrate command + JSONL strict parser + migration `0200_calibration_event_extensions.sql` (10-column CalibrationEventWrite extension) + Cohen's κ on observed marginals + three-tier admissibility states. Drivers A34, A37, partial A36. +44 tests. Modified 7 existing tests for the model extension.
- **C.4** (`19d9f79`) — Cost projection (A36 formula) + length regression fit (statsmodels OLS) + `_warmup_first_call()` cache discipline + dry-run default + `--max-usd`/`--daily-cap` enforcement + DAILY_CAP_HARD_CEILING_USD=$100 with env override. Drivers A35-observation-half, A36. +71 tests.

Total: 4 commits, +270 tests (baseline 222 → 492), ~25 new modules, 1 new migration, 1 new dev dep (`statsmodels`).

### ai-slop-sentinel review on full Track C diff

Per PLAN.md Phase 3.2 + Track A precedent. Dispatched as `general-purpose` subagent with skill invocation (subagent_type `ai-slop-sentinel` doesn't exist; same pattern as Track B review).

**Disposition: 0 FIX-NOW.** 15 findings: 0 BLOCKERs, 7 MAJORs, 6 MINORs, 2 OBSERVATIONs — all dispositioned FIX-NEXT-TRACK / DEFER-V0.2 / ACCEPT. Reviewer's load-bearing-axes verdict: clean on invariants (no migration UPDATE/DELETE, no silent data corruption, no rationale-as-signal, append-only respected, κ formula correct, injection regex matches A38 verbatim).

Track A (4 findings, all FIX-NOW) and Track B (12 findings, 3 FIX-NOW + 1 free fold-in) had FIX-NOW items because their findings were load-bearing invariant violations. Track C's findings were quality-of-implementation only. Per `parallel-review-disposition-schema`: trust the reviewer's dispositions unless principled override applies. The load-bearing distinction held; no override.

Slop review archive at `docs/reviews/2026-06-05-track-c-slop-review.md`, committed `d4d6178`.

## Council fires this session

None new. Pre-Track-C council (from prior session segment `70680bb`) was the architectural fire that gated Track C. This extension was pure implementation following already-decided invariants per CLAUDE.md "Do NOT fire for routine implementation following an already-decided invariant" — C.3 touched `migrations/` + `storage/models.py` but was verbatim per A30/A37.

## Artifacts produced

- `docs/dispatch/track-c-brief.md` (503 lines) — master orientation per `verbatim-content-subagent-dispatch`
- `src/skill_harness/oracles/` package + 3 sub-packages (tier1/, tier2/, calibration/) + errors.py
- `src/skill_harness/oracles/tier1/` — 4 metrics + registry + frozen wordlist (51 phrases)
- `src/skill_harness/oracles/tier2/` — JudgeClient + JudgeVerdict + injection_guard
- `src/skill_harness/oracles/calibration/` — jsonl_parser + command + cost_projection + length_regression
- `migrations/evidence/0200_calibration_event_extensions.sql` — first Track C migration per A30 range
- `tests/oracles/` — 4 sub-package test dirs + fixtures (hedge_wordlist.json + injection_positive.txt + injection_negative.txt)
- `tests/test_calibrate_cli.py` (note: flagged TC-SLOP-012 for FIX-NEXT-TRACK)
- Migrations + storage model extensions + CLI wiring
- `docs/reviews/2026-06-05-track-c-slop-review.md` — full slop review archive
- This session-log entry

## Verification

Gate state at session end (HEAD = `d4d6178`):
- `PYTHONHASHSEED=0 pytest -q -m "not live"` — 492 passed, 1 deselected
- `mypy --strict src/` — 51 source files, no issues
- `ruff check src/ tests/` — all checks passed
- `ruff format --check src/ tests/` — 103 files already formatted

All gates ran clean continuously across 4 cherry-picks. No regression introduced by any subtrack.

## Observations

- **Pyright v1.1 skill validated 5× in this extension**. Every subtrack cherry-pick produced a Pyright diagnostic flood from the orchestrator's view of the worktree. All correctly discriminated as stale-cache per the discrimination rule. Pattern reinforcement: import-resolution failures (almost always stale path), `reportAttributeAccessIssue` on fixture-return types (collapse to `object` because orchestrator's Pyright can't see worktree modules), `reportCallIssue` on Pydantic model parameters from the C.3 extension (orchestrator's LSP holds pre-cherry-pick type even after the cherry-pick). The v1.1 PYTHONPATH variant did not fire (worktree never lacked a venv in this extension; all subagents inherited the orchestrator's venv with proper editable install on cherry-pick).
- **SLOP-CLEAN cleanup-or-not is a reviewer call**, not an orchestrator default. Track A and Track B precedents (4 and 3+1 FIX-NOW) created an implicit expectation that every track has a cleanup commit. Track C's review broke that pattern correctly: when the rubric returns no invariant violations, no cleanup commit is needed. The orchestrator must trust the disposition vocabulary per `parallel-review-disposition-schema`. Track-specific cleanup batches (Pre-Track-D housekeeping, Track E batch, polish batch) are the right shape for FIX-NEXT-TRACK items — not a forced same-session cleanup.
- **Subagent commit-vs-stage pattern varies**. C.1, C.2, C.3 staged-without-commit (orchestrator commits in worktree); C.4 committed in worktree. Cherry-pick works identically either way. Worth noting but not constraining — subagents make this call freely.
- **C.3 was the riskiest subtrack** (touched `migrations/` + `storage/models.py` + extended downstream tests). Subagent completed cleanly without halt-on-ambiguity, demonstrating that a verbatim-spec brief with explicit ambiguity classes is sufficient for storage-touching work. Per CLAUDE.md the change was "routine implementation following already-decided invariant" (A37 verbatim) so no council fire was needed.
- **Brief-vs-formula CI discrepancy** caught by C.4 subagent: dispatch brief showed `est_CI_95_width: 0.127` (one-sided half-width) but the formula `2*1.96*est_se ≈ 0.254` (full two-sided width) is what the subagent implemented. The subagent correctly followed the canonical formula and flagged the brief's example as wrong. This is exactly the halt-on-ambiguity discipline working — subagent identified the inconsistency rather than guessing.

## Values decisions queued / resolved

- **C2 (operator-self-label calibration tier)**: default REFUSE remained operative throughout Track C. No `"operator_self_labeled"` state shipped. State enum extension in `CalibrationEventWrite` (per A37) excluded the operator-self-label value. C2 still open at end-of-session; surfaces to user at next session start.
- **C1 (tie encoding)**: provisional `0.5` half-update remained operative. Track C's `JudgeVerdict.raw_observation = 0.5` for tie pairs honors this. C1 still dispositionable per A37 `n_tie/N` fields — needs Track D ablation data to inform the flip.

## Open questions for next session

- **C2 disposition** — value decision still open. Default REFUSE is shipping per Track C. User can flip to admit operator-self-label tier as bootstrap-grade calibration, requires `CalibrationEventWrite.state` enum extension to add `"operator_self_labeled"`. Recommendation if asked: keep REFUSE for v0.1; defer to D16 if v0.2 needs bootstrap mode.
- **Pre-Track-D council fire seats** — PLAN.md row 4 says `STAT + COST + RELIABILITY + OPERATOR-DX`. The OPERATOR-DX seat hasn't been fired yet in this project. Need to ensure the orchestrator brief for that seat lens is clearly stated (likely: dry-run UX, projection output formatting, error messaging quality, operator-recovery affordances).
- **TC-SLOP queue housekeeping batch** — when does the orchestrator dispatch the FIX-NEXT-TRACK batch? Three options: (a) before Pre-Track-D council fire (clears the surface for fresh review), (b) after Track D ships (batched with Track D housekeeping), (c) at Track E (read-models batch absorbs TB + TC test discipline items together). Lean (a) for the CLI/packaging items (TC-SLOP-001/002/003/012) since they affect first-user-experience; (c) for the rest.
- **Migration `0200` triggers test** — C.3 added migration with whole-row RAISE(ABORT) trigger coverage. The append-only invariant test (`tests/property/test_evidence_append_only.py`) was updated to include new fields but the trigger interaction with ALTER TABLE could use a property-test verification in Track D or as housekeeping (P1 generic property already covers it structurally, but explicit migration-trigger interaction test would be cleaner).

## Next gate

**Pre-Track-D council fire** before Track D dispatch per PLAN.md "Named council fire points" row 4.

Seats: STAT + COST + RELIABILITY + OPERATOR-DX (Custom template). Rationale per PLAN: "Ablation runner is the cost-hot-path and the user-visible long-running operation; dry-run UX is OPERATOR-DX's lane."

Track D scope per PLAN: Full / Ablated_k / Null orchestration; clause rendering reorder for cache reuse (A13); sequential stopping rule (A8); confound monitoring on all metric_library axes (A11); budget enforcement (A12).

Track D driving findings: A8, A11, A12, A13. Likely expansion by Pre-Track-D council based on the precedent (Pre-Track-A: +A24-A30 = 7 additional; Pre-Track-C: +A31-A38 = 8 additional). Expect adopted A39+ to come from the fire.

Pre-Track-D council fire question draft (to refine before firing):
1. Sequential stopping rule edge case: what if N_max is hit without stop_pass or stop_fail? Per A8 the default is keep-adding-batches — but at what point does the operator get a "stopping with insufficient evidence" signal?
2. Confound detection across ALL metric_library axes (A11): how does the ablation runner read all 4 Tier-1 metrics (plus eventual Tier-2 axes) per sample without exploding sample storage?
3. Prompt cache breakpoint placement (A13): `cache_control: ephemeral` at end of system block + end of skill prefix. How is this expressed in the Anthropic SDK call? Validate against `claude-api` skill latest guidance.
4. Budget check inside writer transaction (A12): the per-call budget cap check happens BEFORE the API call but AFTER prior in-flight calls. Is this race-condition-safe with the single-writer discipline (A26)?
5. `runs.completed_at` single-shot vs ablation orchestration: the orchestration produces many samples per (skill, run, condition) — what's the transactional shape that ensures `runs.completed_at` writes exactly once at end of orchestration?
6. Confound flagging vs aggregation: per A29 only admissible + non-confounded enter aggregation. How does the runner tell the storage layer "this verdict is confounded" at write-time vs leaving it for Track E read-models to filter?
7. OPERATOR-DX questions: dry-run output shape; progress reporting during long runs; error recovery when an API call fails partway through; resumability semantics.
8. Cost ledger atomic write: A12 `runtime.cost_ledger` writes happen per-call. With N=8-40 calls per condition pair × K conditions × multiple skills, the ledger fills fast. Indexing strategy? Reconciler discipline?

Refine before firing. Orchestrator pin: Opus 4.7 per CLAUDE.md model pinning.

Phase 2 status after this session: Tracks A + B + C COMPLETE + SLOP-CLEAN. Tracks D + E remain (D first; E gates on D + C; D gates on Pre-Track-D council).
