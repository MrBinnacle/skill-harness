# Dogfooding: verbatim-content-subagent-dispatch — 2026-06-07

## Metadata

| Field | Value |
|---|---|
| skill | verbatim-content-subagent-dispatch |
| skill_id | dd40442f69d3ec38bf7a524e9eebed627f2177fd9197613253d5aed9a196edb0 |
| skill_version | 1.0.0 |
| harness_version | 0.1.0a0 |
| date | 2026-06-07 |
| agent | Sonnet 4.6 (Phase 4.4 dogfooding) |
| worktree | agent-a8f8c5cd9071d7fc9 |

## Pipeline execution

### Step 1: skill init

```
skill init C:\Users\mlpgr\.claude\skills\verbatim-content-subagent-dispatch\SKILL.md --execute
```

Result: **21 clauses extracted and persisted** to evidence.db.

- Clauses 0–4: `sem-vac` (no falsifying case) — problem-statement sentences describing what subagents *currently* do wrong. These are the motivation block, not testable directives.
- Clauses 5–20: `none` vacuity, falsifying case present (FC=Y). 16 testable clauses.

Note: first dry-run attempt (no `--execute`) crashed on Rich table rendering: `UnicodeEncodeError: 'charmap' codec can't encode character '→'` on cp1252 Windows console. Resolved by setting `PYTHONIOENCODING=utf-8` + `[Console]::OutputEncoding = UTF8`. The extraction itself succeeded; only the Rich renderer failed (windows-claude-code-env gotcha confirmed active).

### Step 2: run ablation

```
run ablation <skill_id> --execute --max-usd 5
```

Result: **21 clauses UNMEASURED(tier2_uncalibrated)**. Exit code 2 (UNMEASURED, not hard error).

Budget spent: within $5 cap (all verdicts refused before write — no calibrated `(judge_id, axis)` record for any Tier 2 axis).

### Step 3 + 4: run evaluate-skill

JSON vector:
```json
{
  "passed": 0,
  "failed": 0,
  "confounded": 0,
  "unmeasured": 21,
  "coverage": 0.0,
  "unmeasured_breakdown": {"no_data": 21}
}
```

Rich output: All 21 clauses `UNMEASURED / no_data / posterior_mean=0.500`.

## §16 Skill Vector

| Passed | Failed | Confounded | Unmeasured | Coverage | Contribution |
|--------|--------|------------|------------|----------|-------------|
| 0 | 0 | 0 | 21 | 0.0% | single-clause LOO; lower-bound under redundancy |

**Goal exit check**: 0 PASSED, 0 FAILED — goal exit condition (≥1 PASSED AND ≥1 FAILED-or-UNMEASURED) is **not met** on PASSED side. All 21 clauses are UNMEASURED. The harness ran without hard error; the UNMEASURED result is the honest outcome of a Tier 2-dominant skill with no calibrated judge records.

## Observations

### O1: Tier 2 dominance — full UNMEASURED result expected

15 of 16 testable clauses have oracle_tier=2 (LLM judge required). No `(judge_id, axis)` calibration records exist in evidence.db. The harness correctly halts at `tier2_uncalibrated` before spending tokens on uncalibrated judge calls. This is the correct fail-closed behavior per CLAUDE.md Oracle tiering invariant.

The 1 Tier 3 clause (clause 19, model cost efficiency) also unmeasured — Tier 3 (real-world consequence) has no oracle path in v0.1.

**Implication**: This skill is structurally unmeasurable by the v0.1 harness without a calibration event. The axes (embellishment rate, spec-compliance rate, halt-on-ambiguity rate) require behavioral judgment that is squarely Tier 2.

### O2: Ablation vs. aggregation sub-reason discrepancy

Ablation report showed `UNMEASURED(tier2_uncalibrated)`; aggregation (`evaluate-skill`) showed `sub_reason: no_data`. These are consistent: `tier2_uncalibrated` is the runner-side classification (judged at sampling time); `no_data` is the aggregator-side classification (no verdicts written to the DB because the runner refused to write uncalibrated evidence). This is correct behavior — the two-layer labeling is not a bug, but the discrepancy is worth surfacing for operator clarity. Potential improvement: surface `tier2_uncalibrated` in the aggregation sub_reason when all run evidence was refused on calibration grounds.

### O3: sem-vac cluster — problem-statement sentences extracted as clauses

5 of 21 clauses (0–4) are the "Subagents frequently do X" problem-statement sentences. The extractor classified them as `sem-vac` correctly — they describe the failure mode this skill addresses, not behavioral directives that can be ablated. This is expected extractor behavior for a skill that opens with a problem statement. The extractor correctly separated motivation from directive content.

### O4: Three-part dispatch structure — preserved as distinct clause groups

The skill's three-part structure (role identity + instrument binding + output contract) was preserved as distinct clause families in the extraction:

- Part 1 (role identity): clauses 5, 17 (role identity declaration completeness; role context completeness for role-shaped dispatches)
- Part 2 (instrument binding): clause 7 (tool selection improvisation)
- Part 3 (output contract): clauses 8–16 (verbatim content embedding, verification specificity, AI-attribution, halt-on-ambiguity, report completeness, spec compliance, fence collision, forward-reference blockers, wrong-but-shipped output)

No multi-clause sentence collapse observed. The "verbatim AND halt AND output contract" conjunction was split across distinct clauses (8, 11, 12) — atomic split confirmed.

### O5: Tier 1 clauses identified but blocked by calibration dependency

Clauses 8 (verbatim content embedding, Tier 1), 10 (AI-attribution trailer, Tier 1), 11 (unsanctioned output modification, Tier 2), 16 (fence collision, Tier 1), and 14 (AI-attribution in commits, Tier 1) are Tier 1. These should be measurable without judge calibration. However all returned `tier2_uncalibrated` — suggesting the runner applies a blanket calibration check before any verdict, even for Tier 1 clauses. This is a potential harness issue: Tier 1 clauses should be admissible without a calibration record. Worth investigating whether the v0.1 runner correctly differentiates Tier 1 (mechanical oracle) from Tier 2 (judge) paths before refusing evidence.

**Correction note**: The ablation result `tier2_uncalibrated` applies to the judge oracle path. If the Tier 1 clauses also returned `tier2_uncalibrated`, the runner may be defaulting all clauses to the Tier 2 path regardless of oracle_tier. This would be a runner classification bug — the mechanical oracle (Tier 1) should be invoked for Tier 1 clauses without requiring a calibration record.

### O6: Cross-skill comparison vs. ai-slop-sentinel

`ai-slop-sentinel` is also a discipline/directive-heavy skill. Prior dogfooding result for that skill is not available in this worktree, but structurally:

- Both skills are directive-heavy with behavioral axes.
- `ai-slop-sentinel` likely has similar Tier 2 dominance.
- `verbatim-content-subagent-dispatch` has a higher proportion of Tier 1 clauses (AI-attribution trailer presence, fence collision, report structure) — making it a better candidate for partial Tier 1 measurement once oracle wiring is confirmed.
- Multi-clause sentence density: this skill has more compound-behavioral clauses ("verbatim AND halt-on-ambiguity AND output contract") than a sentinel-style checklist. The extractor handled these well with atomic splitting.

## Windows environment findings

- cp1252 console encoding crash on Rich table render with `→` (U+2192). Fix: `PYTHONIOENCODING=utf-8` + `[Console]::OutputEncoding = UTF8`. Matches windows-claude-code-env gotcha pattern.
- Skill extraction itself completed successfully before the crash; the crash was render-only.

## Identified harness improvement candidates

1. **O2**: Surface `tier2_uncalibrated` (vs `no_data`) in aggregation sub_reason for operator clarity.
2. **O5**: Verify Tier 1 clauses use mechanical oracle path, not judge calibration path. If Tier 1 clauses are routed through the judge path, this is a runner classification bug — `tier2_uncalibrated` on a Tier 1 clause is incorrect.

## Commit

This writeup is the Phase 4.4 dogfooding artifact for verbatim-content-subagent-dispatch.
