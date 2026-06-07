# Dogfooding Run: ai-slop-sentinel — 2026-06-07

## Header

| Field | Value |
|---|---|
| skill_id | `074595b7a61821d4f0b80bf870b680d49326b27aab51e32e844d4e141607170b` |
| skill name | ai-slop-sentinel |
| source sha256 | `074595b7a61821d4...` (first 16 chars) |
| timestamp (UTC) | 2026-06-07T19:50:57 |
| harness HEAD | `97fd7f2fddaf5ba2a41a22a3eb3f7cbe61e2c4bf` |
| extractor model | claude-sonnet-4-6 |
| subject model | claude-sonnet-4-6 |

---

## Clause Inventory

Total clauses extracted: **17**
- Tier-1 (oracle_tier=1): 7 clauses
- Tier-2 (oracle_tier=2): 10 clauses
- Semantic vacuous (vacuity_flag=semantic_vacuous_pending_review): 1 (clause index 16)
- Non-vacuous (vacuity_flag=none): 16
- All 17 clauses have falsifying cases or vacuity flag; none mechanically vacuous.

### Per-clause inventory table

| # | Axis | Cmp | Tier | Vacuity | FC |
|---|---|---|---|---|---|
| 0 | citation_presence_per_flag | increase | 1 | none | Y |
| 1 | watch_entry_metadata_completeness | increase | 1 | none | Y |
| 2 | watch_entry_currency | increase | 2 | none | Y |
| 3 | temporal_caveat_disclosure | increase | 2 | none | Y |
| 4 | structural_vs_stylistic_criterion_weight | increase | 2 | none | Y |
| 5 | watch_document_freshness_compliance | increase | 1 | none | Y |
| 6 | watch_entry_schema_completeness | increase | 1 | none | Y |
| 7 | reviewer_independence_from_author_session | increase | 2 | none | Y |
| 8 | flag_severity_classification_and_citation | increase | 1 | none | Y |
| 9 | ai_pathology_flag_coverage | increase | 2 | none | Y |
| 10 | scope_deduplication_with_other_sentinels | decrease | 2 | none | Y |
| 11 | review_gate_enforcement_coverage | increase | 1 | none | Y |
| 12 | watch_document_incident_driven_growth | increase | 1 | none | Y |
| 13 | graduation_selectivity_to_structural_patterns | increase | 2 | none | Y |
| 14 | mechanical_gate_pre_emptive_creation | decrease | 2 | none | Y |
| 15 | invented_criterion_rate | decrease | 2 | none | Y |
| 16 | opinion_grounding_in_external_authority | increase | 2 | sem-vac | - |

**Vacuity breakdown:**
- `mechanical_vacuous`: 0
- `semantic_vacuous_pending_review`: 1 (clause 16: "Embody the experienced, tenured senior-dev skeptic...")
- `none` (testable): 16

---

## Ablation Run

| Field | Value |
|---|---|
| run_id | `e3672fac-c9fe-49...` |
| N_min | 8 |
| N_max | 40 |
| Calls per clause (min..max) | 24..120 |
| Conditions | Full / Ablated_k / Null |
| Per-run cap | $5.00 |
| Daily cap | $20.00 |
| **Samples collected** | **0** (BLOCKER-1 gate fired for all clauses) |
| **Actual API cost (ablation)** | **$0.00** |
| **API cost (skill init extraction)** | ~$0.01 (single extraction call to claude-sonnet-4-6; not tracked in cost_ledger) |

### Root cause: BLOCKER-1 axis mismatch

The harness gates clauses via `_is_tier1_measurable()` which requires:
1. `oracle_tier == 1`, AND
2. `clause_spec.axis` is registered in `self._scorers` (the 4 Tier-1 scorers)

The 4 registered Tier-1 scorers are: `verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`.

All 17 extracted axes (e.g. `citation_presence_per_flag`, `watch_entry_metadata_completeness`, etc.) are **custom axes specific to this skill** and do not match any registered scorer. Even the 7 extractor-declared `oracle_tier=1` clauses fail the axis-match gate. All 17 clauses hit BLOCKER-1 and return `UNMEASURED(tier2_uncalibrated)` without any subject calls.

---

## §16 Vector

```json
{
  "passed": 0,
  "failed": 0,
  "confounded": 0,
  "unmeasured": 17,
  "unmeasured_breakdown": {"no_data": 17},
  "coverage": 0.0,
  "contribution": {
    "full_vs_null_delta": null,
    "label": "single-clause LOO; lower-bound under redundancy"
  }
}
```

**Note:** `unmeasured.sub_reason = "no_data"` at the aggregation layer (no oracle_verdicts rows). The runner-layer sub_reason is `tier2_uncalibrated` (BLOCKER-1 gate, no samples issued).

---

## Per-clause status table

All 17 clauses: **UNMEASURED** / sub_reason: `no_data` / posterior_mean: 0.500 / n_verdicts: 0

---

## Clause-level signal check

**HALT — all UNMEASURED**

Goal criterion (≥1 PASSED AND ≥1 FAILED-or-UNMEASURED) is not met because 0 clauses reached sampling.

Per HALT conditions in the task spec: "all UNMEASURED" triggers HALT.

---

## Observed gotchas (claudeception input)

1. **Windows Rich UnicodeEncodeError on ⚠ (U+26A0)**: The ablation report's "⚠ One or more clauses are UNMEASURED" message crashed with `charmap codec can't encode character '⚠'` on Windows cp1252 terminal. The report table rendered correctly; only the footer `print()` call failed. Requires `PYTHONIOENCODING=utf-8` or an ASCII-safe fallback for the warning symbol on Windows. (See `windows-claude-code-env` skill.)

2. **Skill init transient failure (first call)**: The first `skill init` call returned `"Claude returned 'clauses' field of unexpected type: str"` — a transient tool-use response anomaly. The second identical call succeeded with 17 clauses. No retry logic in the extractor; callers must retry manually on transient failures.

3. **Extractor oracle_tier=1 declaration does not imply axis registration**: The extractor assigns `oracle_tier=1` for mechanically-countable axes (e.g. citation counts). But BLOCKER-1 checks axis-name presence in `_scorers`, not tier number. Any skill whose behavioral axes are domain-specific (not `verbosity`/`hedge_index`/`structure_score`/`compliance_proxy`) will be fully UNMEASURED until those axes are registered as Tier-1 scorers.

4. **cost_ledger records 0 for ablation-only runs where BLOCKER-1 fires before all subject calls**: No rows written because no API calls were made to the subject model. The `skill init` extraction cost (~$0.01) is not tracked in cost_ledger (it goes through `call_extract_clauses` directly, not through the AblationRunner's cost-tracking path).

---

## Cross-skill sniff

The `code-review-sentinel` skill shares the "review + cite watch entry + severity classification" structure. The same axis-mismatch problem would apply — domain-specific axes like `flag_severity_classification` would not match the 4 registered Tier-1 scorers. Both code-review-sentinel and ai-slop-sentinel need custom Tier-1 scorers (e.g. citation presence count, severity label parser) registered before ablation can proceed.

---

## Reproducibility

Byte-stable JSON re-run: **yes** — `PYTHONHASHSEED=0` was set; all 17 clauses hit BLOCKER-1 deterministically (no sampling randomness involved). Re-run `skill init` against the same source SHA (`074595b7a618...`) with the same extractor model to reproduce the clause set (note: extractor is stochastic; clause count may vary slightly).

---

## Halt triggers fired

- **All UNMEASURED** — 17/17 clauses returned `tier2_uncalibrated` via BLOCKER-1 (axis not in registered Tier-1 scorers). No admissible evidence produced.
- **Root cause**: ai-slop-sentinel axes are all domain-specific; none match the 4 currently registered Tier-1 scorers (`verbosity`, `hedge_index`, `structure_score`, `compliance_proxy`).
- **Fix path**: Register custom Tier-1 scorers for at least one of the 7 Tier-1-declared axes (e.g. `citation_presence_per_flag` → a mechanical citation-presence counter).
