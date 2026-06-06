# Track D.2 — Fix-Loop Brief (council disposition)

D.2 (`a84fe85`) reviewed by the 5-seat parallel council. Gates were green (575 pass, mypy
--strict clean) but the council found **2 BLOCKER clusters** that the test suite did not
exercise. D.2 does NOT merge until these are fixed and re-reviewed. Stay entirely inside
`src/skill_harness/ablation/` and `tests/ablation/` (no cross-module edits to oracles/ or storage/
schema beyond what's noted; if you think a schema change is needed, STOP and report it).

## Root insight (read first)
`_write_verdict_and_confounds` hardcodes `admissibility_state = "admissible"` (runner.py ~L920-921).
That single constant is the root of three findings. `admissibility_state` must be a **real
write-time snapshot** computed from the actual state of the comparison:
- Tier-2 / no-Tier-1-scorer  → `inadmissible`, reason `tier2_uncalibrated`
- confound_flagged this comparison → not aggregated (VIEW handles it) AND not added to posterior
- Null-accumulator below floor (N_null<30) → `inadmissible`/UNMEASURED, reason `underpowered`
- otherwise → `admissible`
Snapshot it at write time; never recompute at read time (locked invariant).

## BLOCKER-1 — Tier-2 clauses get a silent wrong-axis admissible verdict
Evidence: `_score_primary_axis` (runner.py ~L976-993) keys only on `clause_spec.axis` and falls
through to `count_tokens` (verbosity) for any axis not in `self._scorers`, with NO `oracle_tier`
check. Verdict then written `admissible` (L920-921) and fed to `acc.add` (L770). A Tier-2 clause
enters the pass rule measured on the WRONG axis. Violates CLAUDE.md "Tier-2 inadmissible without a
calibrated (judge_id,axis) record", "no admissible evidence ⇒ UNMEASURED never PASSED", and
axis-specificity.
Fix: before sampling (mirror the QUAL-1 early-return at runner.py ~L594-606), if
`oracle_tier != 1` OR `axis not in self._scorers`: mark the clause UNMEASURED, write NO admissible
verdict (or write one with `admissibility_state="inadmissible"`, reason `tier2_uncalibrated`), and
do NOT call `acc.add`. Add a test: a Tier-2 clause yields UNMEASURED, zero admissible verdicts,
empty posterior.

## BLOCKER-2 — Resume corrupts verdict→sample provenance (and crashes on FK)
Evidence: on resume, samples loaded from evidence pass `""` for their id (runner.py ~L765-766),
then `_write_verdict_and_confounds` substitutes `sample_a_id = full_sample_id if full_sample_id else
verdict_id` (~L930-931). `sample_a_id`/`sample_b_id` are `TEXT NOT NULL REFERENCES samples(sample_id)`
(0001_initial.sql:117-118) with `foreign_keys=ON` → inserting `verdict_id` (not a real sample id)
raises IntegrityError. **Resume is broken.** It passed only because NO test exercises the non-empty
`existing_samples` branch.
Fix:
1. `_load_sample_output` (runner.py ~L1061-1071) must also return the real `sample_id` (it already
   queries that row). Thread the real id through `_run_clause` into the verdict write. Never
   substitute `verdict_id`.
2. SCHEMA-3: verdict writes are NOT gated by the existing-sample check the way sample writes are
   (sample writes skip when `*_key in existing_samples`; the verdict write at ~L760 is
   unconditional), so resume APPENDS a second verdict per comparison. Gate the verdict write on the
   same idempotency check (skip if the comparison was already recorded), OR add the appropriate guard
   in code. Do NOT add a DB UNIQUE constraint without flagging (schema change = ASK-FIRST).
3. **Add the missing test**: a resume against a run with non-empty `existing_samples` (some
   Full/Ablated samples already in evidence) — assert (a) no IntegrityError, (b) verdict
   `sample_a_id`/`sample_b_id` point at REAL existing sample rows, (c) no duplicate verdict rows,
   (d) posterior rebuilt deterministically. This test is the load-bearing deliverable — it is the
   coverage hole that hid both BLOCKERs.

## MAJOR-1 — Confounded observation biases the stopping posterior
The `admissible_verdicts` VIEW (0003) already excludes confounded verdicts from AGGREGATION, so the
aggregation surface is safe. But `acc.add(observation)` (runner.py ~L770) runs unconditionally, so a
confound_flagged comparison still moves the clause's own stopping posterior → biased early-stop and a
runner-reported PASS/FAIL that can disagree with the aggregated truth.
Fix: when `detect_confounds` flags this comparison (an event with `primary_clause_id == this clause`),
skip `acc.add` (or add it as a non-aggregating/tagged observation) so stopping matches the VIEW.

## MAJOR-2 — Hard budget cap can be exceeded on resume
Evidence: resume reads `samples_collected` from runtime `progress` (runner.py ~L510) and
`usd_spent` is only incrementally updated (~L825-840), never re-derived from evidence. A crash
between the evidence sample-commit and the runtime budget-spend update leaves budget under-counting →
the A42 "hard cap" can be overspent after resume.
Fix: on resume, re-derive `usd_spent` from `SELECT SUM(usd) FROM samples WHERE run_id=?` and
`samples_collected` from `COUNT(*)`, both from evidence (authoritative), before re-entering the loop —
mirror how `_get_existing_samples` already re-derives the idempotency set from evidence.

## MAJOR-3 — Below-floor confound verdicts written admissible
When the Null accumulator is below the N_null=30 floor (A47), detection is correctly disabled, but
the affected verdicts are still written `admissible` instead of UNMEASURED(underpowered). Snapshot
`admissibility_state="inadmissible"`/reason `underpowered` in that case (part of the root-insight fix).

## MINORs (fold in; cheap)
- REL-1: initialize `full_sample_id = ""` and `abl_sample_id = ""` at the top of the loop (~L621) to
  kill the latent UnboundLocalError trap (currently safe only by Python's lazy if/else).
- REL-7: the A42 docstring claims "check + reservation in ONE transaction" but the check and spend are
  two separate `BEGIN IMMEDIATE` transactions. Either correct the docstring to "single-threaded
  serialization, not transactional reservation," or implement an in-transaction reservation.
- SEC-4: confirm no control-flow branches on the `[ABLATED]`/`[CLAUSE k — ABLATED]` sentinel appearing
  in *model output* (sentinel is test-only). Likely already fine; just verify.

## Carry-forward (NOT D.2 fixes — record only)
- TA-4: per-verdict multiplicity context (family_size) is on RunConfig but not on each
  OracleVerdictWrite; Track E re-derives via runs.config_json. Acceptable; note in D.3/Track-E brief.
- SEC forward caveats: when the Tier-2 judge is wired (Track C/D judge layer), re-audit output_text →
  judge-system-prompt interpolation for injection.

## Gate + return contract
Re-run from the worktree with the venv interpreter and PYTHONPATH=<worktree>\src:
`pytest -q -m "not live"` (must stay green INCLUDING the new resume test) and `mypy --strict src/`
(must be clean). Report DONE / DONE_WITH_CONCERNS with the new test names and a one-line note per
BLOCKER/MAJOR on how it was resolved. Keep all changes inside ablation/ + tests/ablation/.
