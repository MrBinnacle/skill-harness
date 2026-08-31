# Finding: confound status silent understatement

**Severity:** `WRONG_NUMBER`
**Ticket:** #348 (e2e detector); repair filed as separate ticket
**Status:** open — detector landed; repair not yet built
**Harness:** `tests/test_confound_status_e2e.py`
**Report:** this document
**Master seed:** not applicable (deterministic DB seeding, no RNG)

---

## Summary

When confound events exist for a clause, the status is
`UNMEASURED(inadmissible)` instead of `CONFOUNDED`.  The operator is told
the evidence was rejected as inadmissible without cause named as confound,
where the truth is that the data was thrown out for confound.

### Observed on the detector fixture (2026-08-31)

| Field | Value |
|-------|-------|
| `clause.status` | `UNMEASURED` |
| `clause.sub_reason` | `inadmissible` |
| `vector.confounded` | `0` |
| `vector.unmeasured_breakdown` | `{inadmissible: 1}` |
| `n_verdicts` / VIEW rows | `0` (primary exclusion holds) |

`NO_DATA` is the adjacent dead branch in `derive_clause_status` (Rule 1 when
`confounded_verdict_count > 0` but the engine override never fires).  The
runner-shaped fixture hits `inadmissible` because the engine reports
`confounded_verdict_count = 0`.

### Three-layer split-brain

| Layer | What it does | What it produces |
|-------|-------------|-----------------|
| Runner `_snapshot_admissibility` | Writes verdicts as `inadmissible/confounded` | `admissibility_state = 'inadmissible'` |
| Admissible VIEW `0003` | Filters on `admissibility_state = 'admissible'` AND no matching `confound_events` row on `primary_clause_id` | Excludes inadmissible rows (already excluded by state) |
| Engine `all_confounded_flag` | JOINs `oracle_verdicts` to `confound_events` on `admissibility_state = 'admissible'` | Always false — confounded verdicts are never admissible |
| `derive_clause_status` | Never returns `CONFOUNDED` (Rule 2 is dead code) | `UNMEASURED(inadmissible)` when total>0 and confounded_count=0 |

The runner writes `inadmissible`, so the engine's query for
"admissible but confounded" finds nothing.  `all_confounded_flag` is
always false.  `derive_clause_status` is called instead and returns
`UNMEASURED(inadmissible)` because `admissible_verdict_count == 0`,
`total_verdict_count > 0`, and `confounded_verdict_count == 0`.

### Operator impact

- Status: `UNMEASURED(inadmissible)` instead of `CONFOUNDED`
- Implication: "evidence was rejected" without naming confound as the cause
- `paired_verdict` never takes the confounded branch
- Confounded work is silently understated (`vector.confounded` stays 0)

### Structural cause

The runner's write path and the engine's read path disagree on the
representation of confounded verdicts:

- **Runner writes:** `admissibility_state = 'inadmissible'` when confounded
- **Engine reads:** looks for `admissibility_state = 'admissible'` rows that
  also have `confound_events` entries

These two conditions are mutually exclusive by construction of the write
path.  The engine's `all_confounded_flag` can never be true.

### What a fix would have to change

1. The runner must write confounded verdicts as `admissible` (so the engine
   can find them) with a separate confound marker, OR
2. The engine must query for inadmissible+confounded rows directly, OR
3. `derive_clause_status` must be extended to accept confound information
   and return `CONFOUNDED` on its own.

The admissible VIEW's `affected_clause_id` filtering is an open research
question (migration 0003 comment) and is not settled by this finding.

---

## Detection wiring

- `tests/test_confound_status_e2e.py::TestConfoundStatusE2E::test_confound_events_produce_confounded_status`
  — strict xfail pointing at this document.
- `tests/test_confound_status_e2e.py::TestConfoundStatusE2E::test_primary_confounded_rows_do_not_enter_aggregation`
  — green pin: primary-tainted rows stay out of the VIEW and the fit.
- Test seeds: all verdicts `inadmissible`, confound_events rows present,
  frozen_case present (precondition).  Calls `aggregate_skill()`.  Asserts
  `clause.status == ClauseStatus.CONFOUNDED`.
- On main: status is `UNMEASURED` / `inadmissible`, assertion fails, xfail fires.
- After fix: assertion passes, xfail must be removed.

---

## Reproduction

```bash
PYTHONHASHSEED=0 python -m pytest tests/test_confound_status_e2e.py -xvs
```

Expected: one passed (primary exclusion pin), one XFAIL (status is
`UNMEASURED(inadmissible)`, not `CONFOUNDED`).
