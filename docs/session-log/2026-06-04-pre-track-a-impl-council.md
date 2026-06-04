# 2026-06-04 · pre-track-a-impl-council

**Phase**: Phase 2 entry — third council fire (Pre-Track-A implementation, PLAN.md row 2 of "Named council fire points")
**Sources of truth read at start**: PRD@7c6f5f9 · PLAN@6443f9d · COUNCIL_FINDINGS@10e4897 · checkpoint@c556a04 (continuation of `2026-06-04-phase-1-closeout.md` session, post-push, user said "Drive on")
**Model**: Opus 4.7 (orchestrator dispatch) + 4 parallel general-purpose / Plan-agent subagent seats

## Context

User said "Drive on" after Phase 1 closeout was committed + pushed. Per the refreshed checkpoint and PLAN.md "Named council fire points" row 2, the next gate was the Pre-Track-A implementation council fire — distinct from the Phase 1.5 fire (which dispositioned audit-context fragility clusters BEFORE storage code was extant). This fire dispositions Track A's implementation DESIGN before the Track A subagent dispatches.

## Council fires this session

- **Fire**: 2026-06-04 Pre-Track-A implementation review
- **Template**: Storage-touching change (per `.claude/skills/dev-team-council/SKILL.md`)
- **Seats**: SCHEMA + RELIABILITY + SECURITY + TEST-ARCH (4 seats, parallel dispatch via Agent tool, single message)
- **Brief**: 7 design questions on Track A implementation shape (repository pattern, dual-DB transaction primitive, single-writer queue, property-based test design, connection lifecycle, admissibility filter on read, migration sequencing across worktrees)
- **Output contract**: per-Q `Disposition / Claim / Evidence / Recommendation / What-would-change-it / Cross-seat` + mandatory `STATUS:` last line per `parallel-review-disposition-schema`. Mandatory cross-talk section per `cross-talk-council-dispatch`.
- **Word cap**: ~1500 words per seat
- **Outcome**: all 4 seats returned `STATUS: BLOCKER-FOUND`
- **Archive**: `docs/council-fires/2026-06-04-pre-track-a-impl/` — 4 raw seat outputs + README + synthesis.md
- **Adopted finding IDs**: A24 (repo pattern), A25 (dual-DB ordering evidence-first), A26 (single-writer via SQLite BEGIN IMMEDIATE), A27 (property test two-property + separate crash-injection), A28 (connection lifecycle + structural enforcement + savepoint fixture), A29 (admissible_verdicts VIEW + repo wrappers), A30 (migration ranges + discover() duplicate-version guard + CODEOWNERS)
- **Deferred IDs**: D10 (db_identity), D11 (multi-process single-writer), D12 (denormalized confound_flagged), D13 (RuleBasedStateMachine cross-write consistency), D14 (DB-layer text-size CHECK). D9 promoted into Track A scope (not deferred).

## Decisions made

- **A25 dual-DB ordering substantive disagreement resolved 3-vs-1 (evidence-first)** over SECURITY's runtime-first framing. Orchestrator decision: PLAN Track D's pre-call budget cap check (per Track D exit criterion "Budget check inside writer transaction") moots SECURITY's budget-bypass premise. A3 (admissibility snapshotted at write time) makes evidence rows fully self-contained for audit; the "phantom cost row" SECURITY warns against is structurally undetectable from evidence, whereas the "orphan verdict" (evidence-first failure mode) is detectable by reconciler query. Detectable > undetectable for v0.1's audit-first design. SECURITY's framing recorded as load-bearing dissent in COUNCIL_FINDINGS §A25 — would re-evaluate if post-call accounting becomes the budget oracle OR cost_ledger becomes part of admissibility.

- **A27 + A28 cross-talk yield convergent finding**: RELIABILITY's "separate test families" framing + TEST-ARCH's "savepoint fixture for Hypothesis" framing + SECURITY's "structural pre-commit grep enforcement" framing combined into a coherent test infrastructure shape that no single seat would have produced. This is the highest-leverage cross-talk yield of the fire. Adopted into A27 + A28.

- **A29 SQL VIEW + repo wrappers adopted as defense-in-depth** over either single-layer recommendation. SECURITY + TEST-ARCH wanted the SQL VIEW (structural enforcement); SCHEMA wanted Python repo functions with `_for_aggregation` / `_for_audit` split (sharp naming); RELIABILITY wanted Python repo functions + Pydantic strict. Adopted both layers: VIEW is the structural defense (ad-hoc sqlite3 queries inherit safe defaults); repo functions provide typed Python API with load-bearing names. CI grep ban on raw `oracle_verdicts` outside `audit/` module.

- **A28 PRAGMA scope enforcement upgraded from PR review to CI-enforced grep ban**. A23 left this as "PR review is the current enforcement"; A28 makes it structural via pre-commit hook. Track A is the moment this becomes necessary (first non-migration code that opens DBs).

- **Confound JOIN directionality flagged for next council**: A29's VIEW uses `c.primary_clause_id = v.clause_id`. EVAL-RESEARCH should confirm at Track-D-prep council whether the AFFECTED clause should also be marked confounded — if so, VIEW EXISTS subquery changes. Logged as open question (not values decision).

- **Phase 1.5c gate added to PLAN.md** documenting this fire's outcome. Track A scope + exit criteria expanded substantially (~7 new test families, 3 new code modules, 1 new migration, 2 new docs). Phase 1.5c does not produce code on its own — Track A subagent dispatches against the amended spec.

## Artifacts produced

- `docs/council-fires/2026-06-04-pre-track-a-impl/seat-SCHEMA.md` — raw SCHEMA output (~1500 words)
- `docs/council-fires/2026-06-04-pre-track-a-impl/seat-RELIABILITY.md` — raw RELIABILITY output (~1500 words)
- `docs/council-fires/2026-06-04-pre-track-a-impl/seat-SECURITY.md` — raw SECURITY output (~1500 words)
- `docs/council-fires/2026-06-04-pre-track-a-impl/seat-TEST-ARCH.md` — raw TEST-ARCH output (~1500 words)
- `docs/council-fires/2026-06-04-pre-track-a-impl/README.md` — fire overview + 4-seat synthesis matrix
- `docs/council-fires/2026-06-04-pre-track-a-impl/synthesis.md` — orchestrator synthesis: per-Q disposition, A24–A30 adoption, D9–D14 deferrals, PRD amendments, cross-talk validation (6/12 prediction targets landed)
- `docs/COUNCIL_FINDINGS.md` — Appendix C added: A24–A30 verbose entries + D9–D14 deferrals + 6 new PRD §17 amendments queued + cross-talk validation note
- `PLAN.md` — Phase 1.5c gate inserted (council fire row); Track A scope + exit criteria substantially expanded; council-fire-points table updated

## Values decisions queued / resolved

No new values decisions this session. C1 (tie encoding) remains open per `COUNCIL_FINDINGS.md § C`.

## Open questions for next session

- **Confound JOIN directionality** (A29) — VIEW currently uses `c.primary_clause_id = v.clause_id` to exclude verdicts on the ablated clause. Whether the AFFECTED clause should also be marked confounded is an EVAL-RESEARCH question; should be answered at the Pre-Track-D council fire (which already has EVAL-RESEARCH in the seat roster). — owner: EVAL-RESEARCH (next council fire)

- **Track A worktree dispatch shape** — the amended spec is substantial enough (~7 test families, ~3 modules, 1 migration, 2 docs) that single-subagent execution may exceed reasonable context. Consider sub-tracking inside Track A: A.1 = repository modules + Pydantic models + AST-walker test; A.2 = transaction.py + dual_write.py + context.py + crash-recovery tests; A.3 = admissibility VIEW migration + tests; A.4 = discover() duplicate guard + migrations/README.md + CODEOWNERS. Each is committable as its own commit; the worktree can carry all 4. — owner: orchestrator (before dispatch)

- **CODEOWNERS file format** — A30 requires `.github/CODEOWNERS` with `migrations/* @<owner>`. The repo currently has CODEOWNERS scaffolding from the devops-closeout side-quest (commit `2cc95a8`); confirm what's there and amend to include the migrations gate. — owner: Track A subagent

- **Pre-Track A council fire status in PLAN's row 2** — historically this row referenced "the" pre-Track-A council; now there have been two (Phase 1.5 + Phase 1.5c). Both are documented. The PLAN row 2 has been updated to mark FIRED with the impl-council archive path; the table now has two rows for 2026-06-04 fires. — owner: status updated

## Next gate

**Phase 2 — worktree dispatch for Track A** (now unblocked, with substantially-expanded scope per A24–A30). Per PLAN.md §2:

1. `superpowers:using-git-worktrees` setup: `git worktree add ../youwontdoit-track-a feat/track-a-storage`. (Tracks B and C can also worktree but depend less on this council's findings; their gating councils are Pre-Track C — Custom EVAL-RESEARCH + SECURITY + COST + STAT — not yet fired.)

2. `superpowers:subagent-driven-development` dispatch Track A subagent against the amended scope. Skills loaded per PLAN.md TRACK A section + windows-claude-code-env.

3. Track A subagent reports back with exit criteria status; orchestrator adjudicates per A18-style "tests green, gates pass" rule.

Or: stop here, push the council artifacts to origin, and dispatch Track A in a fresh session.
