# Assurance pass — Phase 0 falsification plan

Phase 0 of the assurance pass (parent #160; this document is #162). Observe
only: no production code and no tests change in the landing of this file.
Later phases build detections from the ranked list below; they do not invent
new failure modes without revisiting this plan.

---

## Baseline record

Recorded on branch `agent/issue-162` against the tree at the time of this
document, with `PYTHONHASHSEED=0` (required: Tier-1 oracle collection aborts
otherwise).

| Check | Result | Counts / detail |
| --- | --- | --- |
| Full pytest suite (`PYTHONHASHSEED=0 python -m pytest --tb=no -q`) | **PASS** | **1800 passed**, **8 skipped**, 0 failed; **1808 collected** |
| `python scripts/release_gate.py` | **PASS** | Public surfaces in lockstep at version **0.2.2** (G6 tag-match self-skips on a non-tag local run) |
| `python scripts/drift_check.py` | **PASS** | **12 / 12** live contracts hold (DC-1 … DC-12); DC-13 remains PLANNED (OBS ledger) |

All three gates green, as expected before the assurance pass starts changing
detections.

Skipped pytest cells (not failures): extractor live/three-skills paths that
need an external `ai-slop-sentinel` SKILL.md (4), and subject-layer cells that
need the optional Inspect extra (4).

---

## Ranked falsification list (exactly ten)

Wrong numbers with green tests — ranked by operator damage (false KEEP/CUT,
false FDR control, silent overspend, false “subsumed”). Style and lint are
out of scope. Each item names **exactly one** detection (a concrete test
module or tool), not a vague intention.

### 1. BH-FDR fallback fed posterior masses as if they were frequentist p-values

**Silent wrongness.** When EB-MoM fails to converge, `fit_skill` builds
`p_values = [1.0 - p_exceed]` from posterior mass
`P(rate > 0.60 | data)` and runs Benjamini–Hochberg
(`src/skill_harness/aggregation/fit.py`). BH assumes valid null p-values.
That transform is not one. A skill with many near-null clauses can still get
`bh_fdr_fallback`, cross the locked 0.95 PASS gate, and mint KEEP via
`paired_verdict` — or the inverse, false `FDR_CORRECTION_FAILED` — while
existing fit tests stay green because they pin the algorithm on hand numbers
and the same transform.

**Detection:** `tests/test_aggregation_fit_fdr_calibration.py` — null-world
simulation (binomial / hierarchical nulls): empirical FDR among declared
passes must stay ≤ the nominal q; failure means the p-input is not a p-value.

### 2. EB-MoM treats empirical rates as Beta draws (no sampling-variance peel)

**Silent wrongness.** `_ebmom` / `fit_skill` take clause rates `w/n`, compute
population variance over clauses, and invert the Beta moment map with no
subtraction of mean binomial sampling variance
(`src/skill_harness/aggregation/fit.py`). Small-n clauses look more
heterogeneous than they are (under-shrinkage → overconfident PASS/FAIL), or
low true heterogeneity plus `/k` variance over-shrinks toward the mean and
drags a strong clause below 0.95. Tests assert algebraic MoM identities on
fixed rate vectors, not recovery of a known hyperprior under hierarchical
Bernoulli draws. Wrong `p_win_gt_threshold` flips Path B KEEP/CUT at the
locked thresholds in `docs/INVARIANTS.md` §1.

**Detection:** `tests/test_aggregation_fit_ebmom_recovery.py` — draw
`p_k ~ Beta(α*, β*)`, `w_k ~ Bin(n_k, p_k)`, require recovered
`(α̂, β̂)` and pass-rate decisions inside a pre-registered bias/coverage
bound against the known truth.

### 3. Path B half-update scalars discard the Gate-2 discordant lattice

**Silent wrongness.** Paired ingest collapses Full-vs-Null into
`{1.0, 0.5, 0.0}` observations; the aggregation engine pools them into
`ClauseObservations(w, n)` and a Beta fit, then `paired_verdict`
(`subject` ingest → `aggregation/engine.py` → `verdict.paired_verdict`).
Gate-2 (`oc/gate2.py`) requires the discordant table `(x_f, x_n)` and
forbids scalar half-update state for the OC estimand. Both-pass and
both-fail both become 0.5: a skill heavy in both-pass ties can approach
PASSED without any discordant benefit. OC seam tests never touch this
pipeline; Path C (`effect_from_matched_gate2`) is coded but matched frontier
feed is still incomplete. Operator KEEP while Gate-2 would be
EQUIVALENT/UNRESOLVED.

**Detection:** `tests/test_paired_halfupdate_vs_gate2_lattice.py` — same 2×2
outcome tables through half-update fit+status+verdict and through
`gate2_decide`; pin the documented divergence cases (ties-as-half-wins vs
discordant-only net lift).

### 4. Float64 OC primitives at sharp γ thresholds (n up to 40)

**Silent wrongness.** `beta_cdf` and `beta_binomial_pmf` are float64 closed
forms; `dirichlet_delta_tail` is Fraction-exact then cast to float
(`oc/exact.py`). Gate-1/2 compare posterior mass to locked γ. At grid edge
(`GRID_N_MAX=40`), extreme `p0`/`d`, underflow or cancellation can move mass
across a decision boundary while hand-literal seam tests (moderate params,
~1e-12 tol) stay green. Wrong QUALIFIES/REJECTED/BENEFIT and wrong attained
errors / frontier ratifiability.

**Detection:** `tests/test_oc_exact_scipy_grid.py` — cross-check
`beta_cdf` / beta-binomial masses against `scipy.special.betainc` /
`scipy.stats.beta` over the full `GRID_N_MIN..GRID_N_MAX` integer lattice
and shapes up to `n+1`; fail on max abs error above a tight bound and on
pmf sum-to-one stress at n=40.

### 5. Half-update tie encoding vs the scientific estimand

**Silent wrongness.** Win=1.0 / Tie=0.5 / Loss=0.0 with `n += 1` per tie
feeds stopping (`ablation/stopping.py`), fit, confound deltas, and judge
observations. The PRD still marks half-update as provisional relative to
drop-ties; variance under ties is not the same as two pseudo-Bernoulli
½-trials. Tie-heavy axes can stop PASSED/FAILED (or never stop) differently
than a win/loss-only or drop-ties encoding, while runner and aggregation
agree with each other and with green tests. Locked INVARIANTS §1 encode the
choice without a differential oracle.

**Detection:** `tests/test_halfupdate_tie_sensitivity.py` — paired scenarios
with identical wins/losses and varying tie counts; assert documented
sensitivity bounds and an optional drop-ties recompute from filtering
`observation == 0.5`.

### 6. Confound status split-brain (runner vs VIEW vs `derive_clause_status`)

**Silent wrongness.** The runner snapshots confounds as
`inadmissible`/`confounded`; the admissible VIEW filters on
`primary_clause_id` only; `derive_clause_status` never returns
`CONFOUNDED` (zero admissible + confound → `NO_DATA`). Engine special-cases
looking for admissible rows with confound events that the runner does not
write. Today: confounded work understates as INADMISSIBLE/NO_DATA, so
`paired_verdict` never takes the CONFOUNDED branch. Later “fix one layer”
risk: confounds re-enter aggregation or drop twice; VIEW still ignores
`affected_clause_id`. Wrong status, wrong operator story, future silent
leak into fit.

**Detection:** `tests/test_confound_status_e2e.py` — end-to-end
runner → VIEW → engine → status: when confound events exist, status is
CONFOUNDED (not silent NO_DATA), and aggregation never sees primary- or
affected-tainted rows.

### 7. Budget / cost accounting non-atomic gate and dual-write orphans

**Silent wrongness.** Budget check is pre-call read then post-call update,
not a single reservation (`ablation/runner.py`). Subject pricing tables can
drift from vendor `usage.cost`. Evidence commit + runtime cost failure in
dual-write can leave orphan evidence while cost UI understates spend.
Frontier feasibility uses worst-case pair cost; profile
`effect_per_cost` trusts the ledger. Silent overspend past the $35
evaluation hard cap, or premature `aborted_budget` → UNDERPOWERED /
wrong UNMEASURED — green unit tests on each piece in isolation.

**Detection:** `tests/test_budget_ledger_reconciliation.py` — property that
every recorded call reconciles tokens ↔ usd ↔ model price within ε; inject
runtime commit failure and require the suite to fail unless evidence and
cost ledgers agree; assert hard-cap refusal cannot be bypassed by
interleaved spend.

### 8. Matched pair / arm / epoch mis-keying inverts the signed effect

**Silent wrongness.** Paired evidence is joined by epoch dicts and harness
pins; a swapped Full/Null log, renumbered epoch, or missing score key
inverts or dilutes `_observation` and any later Gate-2 table. Freeze path
stores Null samples under binary rules that disagree with half-update ties.
Unit tests use hand-built aligned pairs. Production misalignment →
systematic KEEP↔CUT(harmful) flip with green fixtures.

**Detection:** `tests/test_paired_arm_epoch_adversarial.py` — Hypothesis (or
equivalent property) over pair tables: epoch shuffle, arm swap, and absent
scores must refuse write or fail closed; never emit an inverted KEEP from a
swapped beneficial table.

### 9. Value-class guard bypass → false CUT(subsumed) / CUT(no_lift)

**Silent wrongness.** `screen_verdict` and `matched_gate2_verdict` emit
CUT(subsumed) / CUT(no_lift) only for
`ValueClass.TRANSFORMATIVE_LIFT`; unset defaults to withhold CUT
(`aggregation/verdict.py`). Bypass: a caller passes
`TRANSFORMATIVE_LIFT` incorrectly, or a CLI/profile path omits
`value_class_for(skill_name)` after a rename/registry edit. That is the
failure mode #76/#77 were built to prevent — false CUT on trap-discipline
and calibration skills (the dominant real portfolio classes). Portfolio and
pure-function tests stay green if the bad call site is elsewhere.

**Detection:** `tests/test_value_class_call_sites_static.py` — AST/static
scan: every production call to `screen_verdict` /
`matched_gate2_verdict` must pass `value_class=` from
`value_class_for` or an explicit, reviewed constant; bare calls fail CI.

### 10. Unpinned `insert_oracle_verdict` / stale freeze currency → false PASSED

**Silent wrongness.** `mint_oracle_verdict` requires `ArticleFingerprint`;
`insert_oracle_verdict` remains open for fixtures, historical dual-write,
and reconcilers. PASSED still requires a current frozen case count ≥ 1,
and the gate that decides "current" is `frozen_cases_with_currency`
(A57/0401): a case is `current` only when its `metric_version` AND
`implementation_hash` both match the current audited metric version. A
path that inserts without pin, or a currency VIEW change that promotes a
stale / hash-mismatched / never-audited case to `current`, lets
threshold-clearing evidence look current when it is not — false
PASSED/KEEP, or the inverse silent UNMEASURED. Append-only and mint tests
can both pass while the allowlist hole remains. *(Corrected 2026-08-31 by
#352: this row originally pointed at `is_stale_vs_fleet`, which has no
production caller — nothing downstream reads it; a detector written
against that function would exercise code the PASSED gate never calls.)*

**Detection:** `tests/test_mint_path_allowlist.py` — static + behavioral
ban: production modules outside an explicit allowlist must not call
`insert_oracle_verdict` (pre-commit mirror `ban-unpinned-verdict-insert`
+ F-8 drift cross-check); a frozen case whose currency state is not
`current` must not satisfy the PASSED frozen-case gate, and the currency
VIEW must never promote a stale, hash-mismatched, or never-audited case.

---

## Reconciliation to planned assurance phases

Planned phases (parent assurance-pass spec): **statistical correctness**;
**mutation**; **property / stateful / fuzz**; **static analysis**;
**supply chain**; **independent review**.

| # | Item (short) | Primary phase | Notes |
| --- | --- | --- | --- |
| 1 | BH-FDR pseudo-p-values | statistical correctness | Independent review of the estimand (posterior mass ≠ p-value) before rewriting the fallback; mutation alone will not catch a shared wrong oracle. |
| 2 | EB-MoM no sampling-variance peel | statistical correctness | Hierarchical recovery test is the gate; mutation secondary once the oracle exists. |
| 3 | Path B half-update vs Gate-2 lattice | statistical correctness | Property phase owns table generation; independent review of Path B vs Path C estimand split. |
| 4 | Float64 OC at γ edges | statistical correctness | Mutation phase (`mutmut` on `oc/exact.py`, per `requirements-assurance-container.txt`) after the scipy grid oracle lands. |
| 5 | Half-update tie encoding | statistical correctness | Mutation on observation ∈ {0, 0.5, 1} / drop-ties branch after sensitivity bounds exist. |
| 6 | Confound status split-brain | property / stateful / fuzz | Static analysis supports the aggregation SQL surface (no raw `oracle_verdicts` outside `audit/`); independent review of affected-clause policy. |
| 7 | Budget / cost reconciliation | property / stateful / fuzz | Supply chain owns pricing-table drift vs vendor; mutation on budget compare operators. |
| 8 | Paired arm/epoch mis-keying | property / stateful / fuzz | Fuzz/Hypothesis generation of adversarial pair tables; mutation on epoch keying. |
| 9 | Value-class call-site bypass | static analysis | Independent review of portfolio class assignments remains human; the detection is the AST guard. |
| 10 | Mint allowlist / freeze currency | static analysis | Property phase already covers append-only evidence; this item adds the insert-vs-mint allowlist and NULL-drift currency cases. |

Every ranked item maps to at least one planned phase. No item in the top ten
is left without a phase.

### Additional detections required

None for the top ten — each row above has a home phase. Items deliberately
**not** elevated into the ten (still real, lower immediate damage or already
partially pinned) that later phases may still touch without expanding this
ranked list:

- Task-frontier calibration→effect leakage (physical partition exists;
  estimator wiring incomplete) — property/static when matched feed lands.
- Judge length-bias with position-swap agreement — property + statistical
  correctness on calibration gates.
- Multi-axis `(clause_id, axis)` collapsed to `clause_id` in BH membership —
  property on the aggregation engine.
- `dirichlet_delta_tail` / two-arm quadrature edges for non-decimal margins —
  statistical correctness adjacent to item 4.

Those are backlog for phase design, not silent omissions from the ranked
ten.

---

## Copy and scope rules (this document)

- Observe-only landing: no production modules and no tests are modified by
  the commit that introduces this file.
- The words banned by the operator copy rule for this ticket do not appear
  in this document.
- Detections named above are **planned**; implementing them is later-phase
  work, not Phase 0.
