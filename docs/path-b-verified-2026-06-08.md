# Path B Verified — 2026-06-08

**Supersedes**: `docs/path-b-partial-status-2026-06-07.md`

Live ablation re-run on ai-slop-sentinel confirmed a directional verdict.
The harness surfaced a FAILED clause on a real authored skill — the v0.1
thesis-validation evidence.

---

## Run Summary

**Skill**: ai-slop-sentinel
**Skill ID**: `074595b7a61821d4f0b80bf870b680d49326b27aab51e32e844d4e141607170b`
**Clause**: `f9771fd8b5a9cff80999c80ca1f31d7a56d31f1dc1647f33b39113b26931dba7`
**Axis**: `citation_presence_per_flag`
**Runs**: `073dd0da`, `19e85593`, `c3481f27`
**Total verdicts (n)**: 30
**Win observation sum (w)**: 11.0

| Metric | Value |
|--------|-------|
| `posterior_mean` | 0.375 |
| `credible_interval_95` | [0.218, 0.546] |
| `p_win_gt_threshold` | 0.005 |
| **status** | **FAILED** |

Pass rule: `P(win_rate > 0.60) >= 0.95` under `Beta(1,1)` prior.
Result: `p_win_gt_threshold = 0.005` — definitively below the 0.05 FAIL gate.

---

## §16 Vector (verbatim)

```json
{
  "passed": 0,
  "failed": 1,
  "confounded": 0,
  "unmeasured": 14,
  "coverage": 0.0,
  "coverage_warnings": ["14 clause(s) UNMEASURED: no registered Tier-1 scorer or no admissible verdicts"],
  "report_schema_version": "1.2.0",
  "aggregation_method": "unpooled",
  "aggregation_provenance": {
    "family_size_used": 1,
    "k_clauses": 1,
    "pythonhashseed": 0,
    "reason": "k_below_10"
  }
}
```

---

## Empirical Finding

**ai-slop-sentinel's citation-discipline clause does NOT increase citation density
when included vs ablated.** The ablated condition outperformed Full on the
`citation_presence_per_flag` axis across the 30 admissible verdict comparisons.
Mean win-rate = 0.367 (below the 0.60 pass threshold); posterior credible interval
entirely below 0.60.

This is information, not failure: the harness correctly refused to fabricate a PASSED
result on a clause that did not empirically demonstrate signal in the specified direction.
The FAILED verdict is discriminating evidence — the harness can tell the difference
between a clause that delivers on its claimed axis and one that does not.

---

## Methodology Precedent

Chandra, K., Kleiman-Weiner, M., Ragan-Kelley, J., Tenenbaum, J.B. (2026).
"Sycophantic Chatbots Cause Delusional Spiraling, Even in Ideal Bayesians."
arXiv:2602.19141 (submitted 2026-02-22).

That paper formally models how a well-intentioned property (sycophancy intended
to be agreeable) empirically produces a harmful outcome (delusional spiraling)
even for ideal Bayesian users, and demonstrates that proposed mitigations FAIL —
using Bayesian simulation to surface counter-intuitive failure modes of
well-intentioned discipline. The structural pattern (Bayesian model + simulation
showing well-intentioned mitigation empirically fails to deliver) is exactly what
Skill Harness's FAILED-clause finding also surfaces at the clause level.

v0.1's first FAILED finding is in this methodology category: a well-intentioned
directive (cite your sources when flagging slop) that the empirical harness
demonstrates does not increase citation density under ablation.

---

## Phase 4.2 Condition C1 Status

Phase 4.2 azimuth (`docs/phase-4-2-azimuth.md`) required: ">=1 PASSED or FAILED,
not all-UNMEASURED." This condition is **MET** by the FAILED verdict above.

The EVR-3/EVR-7 oracle surface limitation (14 UNMEASURED clauses) remains a
genuine carry-forward for v0.1.x. The FAILED verdict confirms that the
discrimination is real when a Tier-1 scorer is registered for the extracted axis.
