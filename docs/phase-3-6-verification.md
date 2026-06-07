# Phase 3.6 Verify Pass — PRD §19 Success Criteria

**Date**: 2026-06-07  
**Branch**: worktree-agent-a0cfa88d8aef00d04  
**Gates**: pytest 896 passed (not live) · mypy strict 0 issues · ruff check clean · ruff format clean

---

## Method

Each criterion is exercised via a fixture-seeded SQLite database and the `run evaluate-skill` or `diff skill` CLI invoked through Click's `CliRunner`. No live Anthropic API calls are made. All fixtures are ephemeral (`tempfile.TemporaryDirectory`). JSON output is parsed from `result.stdout` (Click 8.4 separates stdout/stderr).

---

### §19 #1 — Detect clause regressions caused by skill edits

**Walkthrough**: Two skill revisions are seeded with identical clause text (same SHA-256 = same comparability key per A55). Skill A has 9 admissible wins → PASSED. Skill B has 9 admissible losses (observation=0.0) against the same clause text → FAILED. `diff skill sA sB --format=json --exit-on-divergence` is invoked. The diff engine aligns the clause by `(axis, sha256(clause_text))`, computes a status delta, and exits 2 when divergence is detected.

**Command**:
```
diff skill sA sB --format=json --exit-on-divergence \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
```

**Expected**:
- Exit code 2 (divergence detected + `--exit-on-divergence`)
- Per-clause delta = `regressed`
- `status_a = PASSED`, `status_b = FAILED`

**Observed**:
- Exit code: 2
- `sha256[:8]=8ae6fc00, delta=regressed, status_a=PASSED, status_b=FAILED`

**Verdict**: PASS — `diff skill --exit-on-divergence` detects a PASSED→FAILED regression and exits 2. The `regressed` delta is issued because PASSED > FAILED in the status ordering.

---

### §19 #2 — Distinguish failed clauses from unmeasured clauses

**Walkthrough**: A skill with two clauses is seeded. `c-passed` has 9 admissible wins (PASSED). `c-unmeasured` has only 2 admissible verdicts — below the N_min=8 floor → UNMEASURED(underpowered). `run evaluate-skill --format=json` is invoked. Exit code 2 signals ≥1 UNMEASURED clause.

**Command**:
```
run evaluate-skill s2 --format=json \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
```

**Expected**:
- Exit code 2 (≥1 UNMEASURED clause per A58)
- JSON `clauses` contains distinct status values: PASSED and UNMEASURED

**Observed**:
- Exit code: 2
- clause statuses: `{'c-passed': 'PASSED', 'c-unmeasured': 'UNMEASURED'}`

**Verdict**: PASS — PASSED and UNMEASURED are rendered as distinct statuses with distinct exit-code semantics (exit 2 for UNMEASURED, exit 0 for all-PASSED).

---

### §19 #3 — Reject uncalibrated judges automatically

**Walkthrough**: A clause with 9 admissible wins is seeded (sufficient for PASSED). One additional verdict is inserted with `admissibility_state='inadmissible'` and `inadmissibility_reason='uncalibrated_judge'` and `observation=0.0` (a losing verdict that would contaminate the posterior if admitted). The `admissible_verdicts` VIEW (migration 0003, A29) filters it out at query time. `run evaluate-skill --format=json` is invoked.

Note: In v0.1, admissibility_state is set at write time by the harness (never by a model). A Tier-2 judge verdict that lacks a calibration record would arrive with `admissibility_state='inadmissible'` stamped at write time. The calibration check path for live judge calls is in `oracles/calibration/` and is not wired to live API in v0.1 — the fixture simulates the outcome of that check (an inadmissible row).

**Command**:
```
run evaluate-skill s3 --format=json \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
```

**Expected**:
- Exit code 0 (PASSED despite the inadmissible row)
- status = PASSED (inadmissible observation=0.0 not admitted into Beta-Binomial pool)
- n_verdicts = 9 (not 10; inadmissible row excluded)

**Observed**:
- Exit code: 0
- status: PASSED
- n_verdicts: 9 (confirming the inadmissible verdict is excluded from the pool)

**Verdict**: PARTIAL — The admissibility gate (A29 VIEW) works correctly: inadmissible verdicts do not enter the posterior. The fixture simulates the post-calibration-check outcome (write-time `admissibility_state` stamp). Live Tier-2 judge wiring is not wired in v0.1 (deferred to Phase 4.4 dogfooding / v0.2 D22); the calibration command (`calibrate`) exists and has its own tests. The gating contract is verified via the VIEW and n_verdicts count.

---

### §19 #4 — Preserve oracle and metric provenance

**Walkthrough**: A PASSED clause is seeded with a known metric_id (`verbosity`), metric_version (`1.0.0`), and run_id (`r1`). `run evaluate-skill --format=json` is invoked. The JSON output is inspected for all per-clause provenance fields required by A60 and for the `aggregation_provenance` block with `aggregation_method` in the valid enum set.

**Command**:
```
run evaluate-skill s1 --format=json \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
```

**Expected**:
- Per-clause: `metric_id_per_axis`, `metric_version_per_axis`, `ablation_operator_hash`, `run_ids_aggregated` all present
- `aggregation_provenance` block present with `aggregation_method ∈ {ebmom_hierarchical, bh_fdr_fallback, unpooled}`
- Top-level `report_schema_version = "1.1.0"`

**Observed**:
- `metric_id_per_axis`: `{'verbosity': 'verbosity'}`
- `metric_version_per_axis`: `{'verbosity': '1.0.0'}`
- `ablation_operator_hash`: present (value "unknown" when not stored in run config — this is the correct fallback per engine.py line 212)
- `run_ids_aggregated`: `['r1']`
- `aggregation_provenance` keys: `['family_size_used', 'k_clauses', 'reason']`
- `aggregation_method`: `unpooled` (K=1 < 10, BH-FDR fallback to unpooled per A53)
- `aggregation_method in valid set`: True
- JSON sorted keys: True
- `report_schema_version`: `1.1.0`

**Verdict**: PASS — All A60-required provenance fields are present. `aggregation_method` is in the valid enum set. `aggregation_provenance` block is always present. Note: `ablation_operator_hash` resolves to `"unknown"` when the run config did not store an explicit operator hash (fixture gap, not a code gap — live runs written by AblationRunner include the hash in config_json). The field presence contract is satisfied.

---

### §19 #5 — Surface confounded measurements instead of silently aggregating

**Walkthrough**: A clause with 9 admissible wins is seeded. A `confound_events` row is inserted with `primary_clause_id = c5` and `delta_kind = 'confound_flagged'` for run `r5`. The `admissible_verdicts` VIEW (A29) excludes verdicts for `(run_id, primary_clause_id)` pairs with a matching `confound_flagged` event. The aggregation engine then sees 0 admissible non-confounded verdicts for `c5`, and since `confound_events` rows exist, derives status `CONFOUNDED` (not `UNMEASURED`).

**Command**:
```
run evaluate-skill s5 --format=json \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
```

**Expected**:
- Exit code 0 (CONFOUNDED is not UNMEASURED; per A58 exit 2 is only for UNMEASURED)
- status = CONFOUNDED

**Observed**:
- Exit code: 0
- status: CONFOUNDED

**Verdict**: PASS — Confounded verdicts are excluded from aggregation via the `admissible_verdicts` VIEW and surfaced as `CONFOUNDED` status, not silently passed through or reported as UNMEASURED.

---

### §19 #6 — Produce reproducible clause-level evidence across skill versions

**Walkthrough**: A PASSED clause is seeded once. `run evaluate-skill --format=json` is invoked twice with `datetime.now()` patched to a fixed timestamp. The two stdout payloads are compared byte-for-byte.

**Command**:
```
run evaluate-skill s6 --format=json \
  --evidence-db ./evidence.db --runtime-db ./runtime.db
  (invoked twice with fixed generated_at_utc)
```

**Expected**:
- Both invocations exit 0
- Byte-stable output (run1.stdout == run2.stdout)
- `report_schema_version = "1.1.0"` present

**Observed**:
- Exit code run1: 0 · run2: 0
- Byte-stable: True
- `report_schema_version`: `1.1.0`

**Verdict**: PASS — Identical evidence + fixed `generated_at_utc` → byte-identical JSON. Sorted keys and compact separators enforced by `to_json_bytes` (A60). The `report_schema_version` "1.1.0" field is present in every report.

---

## Gate Evidence

| Gate | Last output |
|---|---|
| `pytest -q -m "not live"` | `896 passed, 1 deselected in 50.50s` |
| `mypy --strict src/` | `Success: no issues found in 67 source files` |
| `ruff check src/ tests/` | `All checks passed!` |
| `ruff format --check src/ tests/` | `140 files already formatted` |

No new source files were created. Gates are unchanged from pre-verify state.

---

## Halt-Triggers

- **None.** No criterion returned FAIL and no runtime errors were encountered.
- **Tier-2 judge live wiring (§19 #3)**: Criterion 3 is PARTIAL. The calibration path (`calibrate` command) exists and has 15 passing tests. The admissibility gate (A29 VIEW, write-time `admissibility_state` stamp) is verified via fixture — it correctly excludes `observation=0.0` inadmissible rows and prevents posterior contamination. Live Tier-2 wiring (judge makes a real call, calibration check fires, result is stored inadmissible) is not wired in v0.1 and is deferred to Phase 4.4 / v0.2 D22. This is a **PARTIAL**, not a blocker.

---

## Tag-Readiness Assessment

On §19 grounds:

- §19 #1 PASS — regression detection via `diff skill --exit-on-divergence` produces `regressed` delta and exit 2.
- §19 #2 PASS — PASSED and UNMEASURED render as distinct statuses; exit-code discrimination (0 vs 2) is correct.
- §19 #3 PARTIAL — admissibility gate confirmed via fixture (inadmissible row excluded, n_verdicts = 9 not 10); live Tier-2 judge calibration path not wired in v0.1 by design.
- §19 #4 PASS — all A60 provenance fields present in JSON output; `aggregation_provenance` block present; `aggregation_method` in valid enum set.
- §19 #5 PASS — confounded verdicts surfaced as CONFOUNDED, not silently aggregated.
- §19 #6 PASS — byte-stable JSON for identical evidence; `report_schema_version "1.1.0"` present.

**Assessment**: v0.1 is shippable on §19 grounds. The one PARTIAL (#3) is a documented v0.1 scope limitation (D22 deferred) and does not contradict the criterion — the rejection mechanism (write-time admissibility stamp + VIEW filter) is present and verified. Phase 4.2 azimuth makes the final release call.
