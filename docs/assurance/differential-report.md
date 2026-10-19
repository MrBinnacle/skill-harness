# Assurance pass — aggregation differential report (#165)

Parent: assurance-pass spec (#160). Sibling baseline: Phase 0 falsification
plan (#162). Dependency surface: #161 (`numpy` / `scipy` / `statsmodels` on
the dev extra).

This document records **per-function agreement** between
`src/skill_harness/aggregation/` numerical surfaces and independent
`scipy.stats` / `statsmodels` references, as exercised by
`tests/test_aggregation_differential.py`.

Hard constraint (work order): **any disagreement is a finding, not a
tolerance to widen.** No atol/rtol was widened to make a check pass. No
findings were opened for this landing — every audited function agreed within
its pre-stated tolerance on all 1,000 seeded inputs.

---

## Method

| Item | Value |
| --- | --- |
| Inputs per audited function | **1,000** |
| Master seed | `165_2026_08_09` (function streams offset by +0..+3) |
| Comparison | `numpy.testing.assert_allclose(..., rtol=0.0, atol=<per-function>)` |
| Network | Fully offline (local numpy/scipy/statsmodels only) |
| Reference stack | `scipy==1.18.0`, `numpy==2.5.1`, `statsmodels==0.14.6` (dev env at landing) |

Enumeration of audited functions and one-line exclusions lives in the test
module docstring (acceptance criterion: walk of `engine.py`, `fit.py`,
`two_arm.py`, `status.py`, `report.py`, `profile.py`, `verdict.py`).

---

## Per-function results

| Function | Module | Quantity | Reference | atol (rtol=0) | N | Max \|err\| observed | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fit_skill` | `fit.py` | posterior α/β, mean, 95% CI (`ppf`), `P(rate>0.60)` (`sf`); EB-MoM `(α̂,β̂)`; empirical rates `w/n`; BH-FDR pass set | `scipy.stats.beta`; MoM closed form; `statsmodels.stats.multitest.multipletests(method='fdr_bh')` | **1e-12** (`TOL_FIT_SKILL`) | 1000 (stratified: unpooled / EB-MoM / BH-FDR) | **0** (bit-equal within float path) | **AGREE** |
| `two_arm_gate` | `two_arm.py` | arm Beta params; `P(p_t−p_c>δ)` and reverse | Independent `scipy.integrate.quad` of `pdf·cdf` (`epsabs=1e-14`, `limit=500`) | **1e-10** (`TOL_TWO_ARM`) | 1000 | **< 1e-15** (≪ atol; residual is quadrature order) | **AGREE** |
| `effect_from_matched_gate2` | `profile.py` | signed paired rate `(x_f−x_n)/n`; Newcombe (1998) method-10 95% CI | Independent published Newcombe formula (`statistics.NormalDist` quantile + Wilson square-and-add) | **1e-12** (`TOL_EFFECT_MATCHED`) | 1000 | **0** | **AGREE** |
| `effect_per_cost` | `profile.py` | `effect.mean / desc_token_cost` when defined; else `None` | Direct float division / definedness rules | **1e-15** (`TOL_EFFECT_PER_COST`) | 1000 | **0** | **AGREE** |

### Stratification notes (`fit_skill`)

Random inputs alone rarely hit BH-FDR fallback (near-zero sample variance is
rare under continuous rates). The 1,000-draw generator is **stratified** by
`seed_index % 3`:

1. `K < 10` → unpooled path  
2. `K ≥ 10` with heterogeneous rates in `(0.15, 0.85)` → EB-MoM hierarchical  
3. `K ≥ 10` with identical clause rates → `sample_var = 0` → BH-FDR fallback  

All three `aggregation_method` values are therefore exercised inside the
1,000-input budget.

---

## Exclusions (mirrored from the test docstring)

| Public surface | Reason |
| --- | --- |
| `aggregate_skill` | DB orchestrator; interval/rate numerics delegated to `fit_skill` (coverage and mean-delta are trivial ratios). |
| `derive_clause_status` | Discrete threshold state machine; no interval/rate computation. |
| `screen_verdict` / `paired_verdict` / `matched_gate2_verdict` / `harmful_verdict_supported` | Discrete KEEP/CUT maps; consume rates/intervals, do not compute them. |
| `to_json_dict` / `to_json_bytes` / `skill_report_from_dict` | Serialisation only. |
| `disposition_from_verdict` / `evidence_quality_from_screen` / `build_skill_profile` | Enum mappers / row assembly; rate arithmetic is only `effect_per_cost` (audited). |

---

## Findings

None. Zero disagreements on the 4 × 1,000 input grid. No `xfail` markers
were required. No production tolerances were changed.

If a future run disagrees, the procedure is:

1. Do **not** widen `TOL_*`.  
2. File a finding under `docs/findings/` with the failing `seed_index`, master
   `SEED`, inputs, production value, and reference value.  
3. Mark the specific check `@pytest.mark.xfail(strict=True, reason="finding: …")`
   pointing at that finding.

---

## How to re-run

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_aggregation_differential.py -q
```
