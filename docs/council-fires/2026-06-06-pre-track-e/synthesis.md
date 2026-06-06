# Pre-Track-E council synthesis — 2026-06-06

**Template:** Custom (orchestrator-led) — 6 seats, parallel, Opus 4.7, read-only.

**Seats:** STAT + TEST-ARCH + SCHEMA + OPERATOR-DX + RELIABILITY + EVAL-RESEARCH

**Trigger:** Track E dispatch readiness. PLAN.md lines 223-238 + 4 checkpoint carry-forwards (CF-D3-1, A51 amendment, TA-4, SEC judge-injection).

**Outcome:** 9 findings adopted (A53–A61); 2 BLOCKERs (A56 freeze schema gap, A57 stale-frozen-case rule); 4 MAJORs cleanly resolved; 2 OBSERVATION/MINOR. 1 Track D bug surfaced. 0 unresolved BLOCKER.

**Raw seat outputs:** `raw-outputs.md` (verbatim from each agent).

---

## Question disposition summary

| Q | STAT | TEST-ARCH | SCHEMA | OPERATOR-DX | RELIABILITY | EVAL-RESEARCH | Synthesized | Adopted |
|---|---|---|---|---|---|---|---|---|
| Q1 Hierarchical BB | MAJOR (lead) | — | — | NMyL | — | MAJOR (co) | **MAJOR** | **A53** |
| Q2 evaluate-skill orch | OBS (co) | MAJOR (lead) | — | MAJOR (co) | MAJOR (co) | NMyL | **MAJOR** | **A54** |
| Q3 diff skill semantics | — | MAJOR (lead) | MAJOR (co) | NMyL | — | MAJOR (co) | **MAJOR** | **A55** |
| Q4 freeze contract | — | MAJOR (co) | **BLOCKER** (lead) | MAJOR (co) | (cross-talk) | NMyL | **BLOCKER** | **A56** |
| Q5 stale-frozen rule | MAJOR (co) | **BLOCKER** (lead) | MAJOR (co) | NMyL | — | NMyL | **BLOCKER** | **A57** |
| Q6 exit codes | — | MINOR (co) | — | MAJOR (lead) | (cross-talk) | NMyL | **MAJOR** | **A58** |
| Q7 family-size + TA-4 | OBS (lead) | — | OBS (co) | — | OBS (co) | NMyL | **OBSERVATION** | **A59** |
| Q8 report format | — | MINOR (co) | — | MAJOR (lead) | — | MAJOR (co) | **MAJOR** | **A60** |
| Q9 CF-D3-1 scope | — | — | MAJOR (co) | MAJOR (co) | MAJOR (lead) | NMyL | **MAJOR** | **A61** |

---

## Adopted findings (A53–A61) — see COUNCIL_FINDINGS.md Appendix F

Full text + drivers + falsifiable tests live in `docs/COUNCIL_FINDINGS.md` Appendix F. This file is the dispatch + cross-talk archive.

## Substantive disagreements resolved

1. **STAT EB-MoM vs EVAL-RESEARCH PyMC NUTS** (Q1) — Adopted EB-MoM as v0.1 default (no new dep, deterministic, closed-form). PyMC MCMC deferred to D21. Flip condition: K<10 sparse-data noise empirically distorts PASSED rates in dogfooding.
2. **STAT exit 3 vs OPERATOR-DX uniform exit 2** (Q5/Q6 interaction) — Adopted OPERATOR-DX uniform exit 2 (A48 clean-shape preserved). STAT's stale-vs-underpowered operator-action discrimination lives in stderr + `report.sub_reason`. STAT framing recorded for v0.2 reconsideration if dogfooding shows operators conflate the two error classes.
3. **TEST-ARCH `audited+validity_passed` filter vs SCHEMA raw `registered_at`** (Q5) — Adopted TEST-ARCH's filter. A metric_version that failed mechanical validity (A14/A33) MUST NOT be "current"; raw-registered_at "current" would create a regression where a failed metric upgrade silently invalidates all prior frozen cases.

## C3 candidate (retracted, not added to §C)

STAT-surfaced: "PASSED gate evaluation on shrunken (post-EB-MoM) vs unpooled posterior" — should the user pick? Retracted per `feedback-route-to-most-expert`: this is calibration methodology, not user values. STAT SME default holds (shrunken posterior is primary; unpooled persisted in `aggregation_provenance` for audit). Surfaced as an `[values decision]` only if post-v0.1 dogfooding shows user dissatisfaction with shrunken-by-default; flip condition is explicit user request for unpooled-primary.

## Track D bug surfaced (fold into E.3)

- CLI signature `freeze <sample_id>` at `src/skill_harness/cli/main.py:983` must rename to `<verdict_id>`. Existing Track-D stub bug; correct argument name is `verdict_id` (a verdict is the unit promoted; a sample is sub-unit).
- Ablation report rendering at `main.py:899-948` does not surface `verdict_id` to the operator — `freeze` has no discoverability path. Add a `verdict_id` column to the report (cheap CLI change; not a new command per PRD §18 lock).

## Cross-talk validation

- **Predictions landed (10+)**: STAT→TEST-ARCH on PASSED→UNMEASURED transition (correct); STAT→OPERATOR-DX on exit-2 collapse of stale-vs-underpowered (correct + resolved); STAT→EVAL-RESEARCH K<10 hyperprior under-weight (correct, EVAL-RESEARCH did not address); TEST-ARCH→OPERATOR-DX sub-reason distinctness under-weighting (correct); SCHEMA→RELIABILITY conservative over-warn defense (correct); SCHEMA→EVAL-RESEARCH metric_version literature citation (correct); EVAL-RESEARCH→TEST-ARCH metric_drift first-class status (partial — same concept under different name).
- **Wrong predictions (useful adversarial tests)**: OPERATOR-DX→TEST-ARCH wrapping prediction (TEST-ARCH adopted pure aggregator); SCHEMA→TEST-ARCH freeze auto-trigger prediction (TEST-ARCH framed operator-driven correctly).
- **Cross-derived findings (2)**: (i) stale-vs-underpowered action discrimination tension (STAT↔OPERATOR-DX); (ii) freeze discoverability gap → ablation report `verdict_id` column extension (OPERATOR-DX↔SCHEMA).
- **Lens distinctness**: high. RELIABILITY + OPERATOR-DX overlap on CF-D3-1 warning UX (complementary, not redundant). EVAL-RESEARCH net-new contribution: 4 verified citations + `metric_drift` term + `report_schema_version` semver discipline rooted in HELM open issues.

## PRD v1.1 amendments queued (this fire)

10 amendments. Total queue: 44 (34 prior + 10 from this fire). See COUNCIL_FINDINGS.md Appendix F for the table.

## Track E sub-track dispatch plan

Per `superpowers:subagent-driven-development` + `superpowers:using-git-worktrees`:

- **E.1 Storage + recovery** (Sonnet 4.6, worktree `feat/track-e-1-storage`). Migrations 0400 + 0401. `freeze_verdict` repo. `storage/recovery.py` (lift from `cli/main.py`). Smoke + property tests. DEPENDS: none.
- **E.2 Aggregation engine + JSON serialization** (Sonnet 4.6, worktree `feat/track-e-2-aggregation`). EB-MoM hierarchical fit + BH-FDR fallback + status state machine + UNMEASURED sub-reason enum + JSON `report_schema_version 1.0.0`. DEPENDS: E.1 (storage primitives + recovery helper).
- **E.3 CLI integration** (Sonnet 4.6, worktree `feat/track-e-3-cli`). `run evaluate-skill` + `diff skill` + `freeze` (rename `<sample_id>` → `<verdict_id>`) + ablation report `verdict_id` column + exit code wiring per A58. DEPENDS: E.1 + E.2.

Serial — file dependencies. Mirror of Pre-Track-D pattern (D.1 → D.2 → D.3, all subsumed into main).
