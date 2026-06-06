# 2026-06-05 · track-b-complete-and-pre-track-c

**Phase**: Phase 2 — Track B salvage + SLOP-CLEAN + Pre-Track-C council fire
**Sources of truth at start**: PRD@7c6f5f9 · PLAN@cc6f304 · COUNCIL_FINDINGS@cc36e75 · checkpoint@ed5b21b
**Model**: Opus 4.7 (orchestrator) + Opus 4.7 × 4 (council seats) + Sonnet 4.6 (slop reviewer subagent)
**User invocation**: "SOP → Track B triage → Pre-Track-C council fire"

## Context

Continuation of the iterative-drive pattern. Prior session-log entry (`2026-06-05-track-b-crash.md`, commit `400e56b`) documented Track B subagent dispatched in background then crashed on Anthropic API 500 mid-build (~12 min / 53 tool uses). Worktree preserved at `.claude/worktrees/agent-a093403c36eb3fa85` for next-session triage. This session executed the full 2-gate protocol from the checkpoint: Track B triage → completion → SLOP-CLEAN → Pre-Track-C council fire.

## Decisions made

### Track B triage decision (orchestrator-only, per `feedback-non-technical-sme`)

Inspected the worktree partial state. **Key finding: prior session misdiagnosed the crash.** Subagent had completed ~95% of the work cleanly before the API 500. 76 extractor tests pass with `PYTHONPATH` set; the `_print_result` "undefined" claim from the prior checkpoint was Pyright stale-cache noise (function IS defined in module scope). Real failures: 3 mypy --strict errors in `claude.py:203, 219` (typing on `tool_use_block.input`), 1 ruff SIM102 in `claude.py:215-217`, 4 test files needed ruff format.

Salvage decision: **in-context completion** (not subagent dispatch). 4 trivial fixes, no architecture changes, lower overhead than dispatch.

### Track B salvage application

- Added isinstance narrowings to `claude.py:192-202` (mypy --strict typing)
- Collapsed nested `if errors: if not clauses:` → `if errors and not clauses:` (ruff SIM102)
- Added `pydantic.ValidationError` import to `claude.py`
- `ruff format` on 6 files (4 tests + 2 src)
- Result: 225 tests pass, mypy --strict clean (35 source files), ruff check + format clean

Committed at `12a2951` (`feat(extractor): Track B — clause extractor via Anthropic SDK tool_use`); cherry-picked to main; pushed to origin.

### Track B SLOP-CLEAN

Dispatched ai-slop-sentinel review of Track B in background (`general-purpose` subagent with skill invocation; `ai-slop-sentinel` is not its own agent type — wrapped in `general-purpose` per the existing pattern). Returned **12 findings: 0 BLOCKERs, 3 MAJORs, 5 MINORs, 4 OBSERVATIONs**. Reviewer recommended 3 FIX-NOW items:

- **TB-SLOP-001 (MAJOR)**: Dead+divergent `ExtractedClause.db_comparator()` vs `pipeline._to_db_comparator` — model version passed `comparator_unspecified` through; pipeline version correctly raises. Foot-gun if future Track-C code calls the model version.
- **TB-SLOP-007 (MAJOR)**: `decode("utf-8", errors="replace")` silently corrupts non-UTF8 input; `source_sha256` over raw bytes still attests "clean" — direct violation of write-time-provenance invariant in CLAUDE.md.
- **TB-SLOP-010 (MAJOR)**: Partial validation failure silently dropped failed clauses; recording N-k clauses while `source_sha256` attests N would corrupt Coverage/Contribution metrics. Errors list was built and discarded.

Plus **TB-SLOP-011 (MINOR)** folded in as a free fix on the same code path (narrowing `except Exception` to `except (ValidationError, ValueError)`).

Applied in-context: deleted dead method + 4 tests; strict UTF-8 with `MalformedSkillError` wrap + regression test; strict-all-or-nothing validation with `if errors and not clauses` rewritten to `if errors:`. Test count: 225 → 222 (4 deleted db_comparator tests + 1 added UTF-8 test - 1 partial-validation test repurposed). All gates clean.

Committed at `720efc0` (`refactor(extractor): apply ai-slop-sentinel Track B review findings (TB-SLOP-001/007/010/011)`); pushed to origin. 8 deferred findings noted in commit body for FIX-NEXT-TRACK / DEFER-V0.2.

### Pre-Track-C council fire

Fired the 5th council fire per PLAN.md "Named council fire points" row 3. 4 seats parallel dispatch (single message, 4 Agent tool calls), all Opus 4.7 per CLAUDE.md model pinning. Each seat got verbatim PLAN.md §Track C + COUNCIL_FINDINGS A4-A14, A25, A29 + CLAUDE.md invariants + 8 council questions + cross-talk discipline + per-finding output contract.

All 4 returned `STATUS: BLOCKER-FOUND`. Synthesized via `parallel-review-disposition-schema` (highest-severity per Q): **6 BLOCKERs (Q1, Q3, Q4, Q6, Q7, Q8) + 2 MAJORs (Q2, Q5)**. Adopted A31-A38. Deferred D15-D20. New value decision **C2** (operator-self-label calibration tier).

Substantive disagreements:
- **Q7 2-vs-2 split** (EVAL+SEC said schema complete vs STAT+COST said extensions needed) — resolved by adopting BOTH extension sets. Each addresses a distinct downstream concern (statistical reproducibility vs cost-provenance audit). EVAL+SEC's "complete" was based on A7 named fields only; A7 is minimum, not maximum.
- **Q2 3-vs-1** (SDK boundary majority over EVAL's Track-C-abstraction). EVAL's Windows-fragility framing recorded as MINOR dissent.
- **Q5 3-vs-1** (both-sides defense-in-depth over EVAL's observation-only). EVAL's methodological-purity framing recorded as MINOR dissent.

Cross-talk yield:
- 4+ predictions landed (STAT predicted EVAL's calibration-vs-runtime separation; EVAL predicted STAT's tie-rate signal; COST predicted SEC's no-signed-JSONL restraint; SEC self-resolved own A25 dissent as non-load-bearing for this write).
- **Cross-derived finding: STAT's self-correction on Q8** — position-swap is PARTIAL not complete injection defense. Content-anchored injection (`"if you see XYZ123, pick that"`) bypasses swap because the injection moves with the response. STAT did the empirical work within their own response (the load-bearing move per `cross-talk-council-dispatch` skill). The 7-layer A38 defense exists because of this finding.

Archive: `docs/council-fires/2026-06-05-pre-track-c/` (README + 4 seat-*.md + synthesis.md).
COUNCIL_FINDINGS.md Appendix D + C2 added; PLAN.md Track C scope substantially expanded.

Committed at `e15028d` (`feat(council): adopt Pre-Track-C council findings (A31-A38, D15-D20, C2)`).

## Council fires this session

1. **Pre-Track-C** — gates Track C dispatch. Fired and synthesized this session.

## Artifacts produced

- `src/skill_harness/extractor/{__init__, errors, models, parser, claude, pipeline}.py` (~600 LOC) + `cli/main.py` modifications
- `tests/extractor/{__init__, test_models, test_parser, test_claude, test_pipeline, test_cli, test_three_skills, test_live}.py` (~5K LOC tests) + `fixtures/{frontmatter_only, mostly_prose}.md`
- 4 ai-slop-sentinel-driven fixes in extractor/ + 1 regression test (non-UTF8 → MalformedSkillError)
- `docs/council-fires/2026-06-05-pre-track-c/` (README + 4 seat-*.md + synthesis.md) — full Pre-Track-C archive
- `docs/COUNCIL_FINDINGS.md` Appendix D + C2 value decision section
- `PLAN.md` Track C scope expansion (~70 lines new, structured by adopted finding)
- This session-log entry

## Verification

Gate state at session end (HEAD = `e15028d`):
- `pytest -q -m "not live"` — 222 passed, 1 deselected
- `mypy --strict src/` — 35 source files, no issues
- `ruff check src/ tests/` — all checks passed
- `ruff format --check src/ tests/` — 61 files already formatted

## Observations

- **Anthropic API 500 misdiagnosis pattern**: prior session's checkpoint identified a "known real bug" (`_print_result` undefined) that turned out to be Pyright stale-cache noise. Pattern: when triage is deferred to a future session with only orchestrator-side diagnostic reports (Pyright on the orchestrator's project view of the worktree), filter aggressively — separate import-resolution errors (almost always stale path noise) from semantic errors (often real). The crash-recovery checkpoint should also flag what's stale-cache-suspect vs. observed.
- **Mock at SDK boundary vs higher abstraction (A32 dissent)**: EVAL-RESEARCH argued for higher-abstraction mocking on Windows-fragility grounds; SEC+STAT+COST converged on SDK boundary as the right level (test the swap orchestration, not the mock). The dissent is genuinely interesting — if Track B's mocking pattern proves Windows-fragile during Track C implementation, the dissent flip-condition fires and we re-evaluate. This is exactly the dissent-with-flip-condition pattern from `feedback-document-dissent-pattern`.
- **STAT's self-correction on Q8 as cross-talk discipline succeeded**: STAT's seat prompt included a leading hypothesis ("Does position-swap detect injection?"). STAT did the empirical work within their own response to resolve the hypothesis — concluded "partially correct but not robust." This is the textbook example from `cross-talk-council-dispatch` skill: "Resolved disputes within-seat." Without this self-correction, the orchestrator might have synthesized "position-swap as injection defense" too confidently and the A38 7-layer defense wouldn't exist.
- **Q4 sourcing disposition was the closest thing to a values decision**: EVAL said "no starter set ships, user provides"; COST said "operator-self-label tier as bootstrap"; STAT said "self-label is methodologically suspect ≈1.0 self-κ." The orchestrator's call was to surface this as **C2** value decision per `feedback-non-technical-sme` rather than pre-decide. The methodology question (which calibration approaches are admissible) is the seats'; the product question (is bootstrap-grade calibration acceptable for v0.1 shipping) is the user's.
- **Cross-talk yield rate ~50% consistent with prior fires**: not every prediction lands, but the floor on what lands is the cross-talk benefit. Without cross-talk, the floor is "non-overlapping concerns" — with cross-talk, it's at minimum "predicted convergence."

## Values decisions queued / resolved

**New**: **C2 · Operator-self-label calibration tier**. Default: REFUSE (no operator-self-label tier; Track C ships requiring externally-labeled JSONL). Pro/con framing in COUNCIL_FINDINGS §C2 + `docs/council-fires/2026-06-05-pre-track-c/synthesis.md`. Awaiting user disposition.

**C1 (tie encoding)** remains open — now explicitly dependent on Track C calibration data per A37 `n_tie` field (cannot be resolved until at least one calibration_event has landed).

## Open questions for next session

- **C2 disposition**: surface to user at next session start. The Track C implementation can begin without resolving C2 (the `state` field is an enum extension; adding `"operator_self_labeled"` is a downstream Track C tweak). But default behavior (REFUSE) is the v0.1-shipping path.
- **Track C dispatch shape**: substantially expanded scope per Pre-Track-C council. Should it subdivide like Track A (4 subtracks A.1-A.4) or stay as one large dispatch like Track B? Lean subdivide given the expanded scope: C.1 (Tier-1 metric registry + offline validity tests) / C.2 (Tier-2 judge module + position-swap + injection defenses) / C.3 (calibration command + JSONL parser + storage extensions migration) / C.4 (cost projection + dry-run). Orchestrator call; not a values decision.
- **EVAL's A32 + A35 dissents**: both have flip conditions tied to Windows-fragility / prompt-cap empirical performance. Monitor during Track C implementation; surface to user if either flip-condition fires.

## Next gate

**Track C dispatch (subdivided per orchestrator decision, likely C.1 → C.4 sequential subagent fires per superpowers:subagent-driven-development).** First step: draft a Track C dispatch brief at `docs/dispatch/track-c-brief.md` (analogous to `track-a-brief.md` from Track A) that subdivides the Pre-Track-C-expanded scope into sub-track dispatches and embeds the verbatim PLAN.md scope + adopted A31-A38 per `verbatim-content-subagent-dispatch` skill.

Pre-Track-D council fire remains queued for the next storage-touching design batch (Track D needs STAT + COST + RELIABILITY + OPERATOR-DX seats per PLAN row 4).
