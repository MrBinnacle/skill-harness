-- #503 — persist the refusal sub-reason alongside the run.
--
-- The runner's ClauseResult.unmeasured_reason recorded WHY a clause was
-- refused before sampling (BLOCKER-1 tier2_uncalibrated, QUAL-1
-- length_confounded), but the field was never persisted: grep for
-- unmeasured_reason in src/skill_harness/storage/ returned zero matches.
-- After the run ended the reason a refusal happened could not be read back.
--
-- This table is the append-only home for that record. One row per (run,
-- clause) that the runner refused BEFORE sampling. A clause that reaches the
-- sampling loop is NOT refused here -- its UNMEASURED sub-reason, if any, is
-- derived at aggregation from the evidence -- so no row is written for it.
--
-- The sub-reason vocabulary is UnmeasuredSubReason in
-- aggregation/status.py: the single source of truth. The write model
-- (storage/models.ClauseRunOutcomeWrite) rejects a value outside the
-- enumeration, so a non-member cannot reach storage. The SQL CHECK below is a
-- defence-in-depth floor naming the same literals; the Python validator is
-- authoritative because it reads the live enumeration, this copy does not.
--
-- Append-only, like every evidence table: BEFORE UPDATE / BEFORE DELETE
-- triggers raise append_only_violation (the structural test in
-- test_store_bricking_deadlock.py requires both on every evidence table).

CREATE TABLE clause_run_outcomes (
    run_id               TEXT NOT NULL REFERENCES runs(run_id),
    clause_id            TEXT NOT NULL REFERENCES clauses(clause_id),
    unmeasured_sub_reason TEXT NOT NULL CHECK (unmeasured_sub_reason IN (
        'no_data',
        'inadmissible',
        'underpowered',
        'falsifying_case_missing',
        'budget_exhausted',
        'falsifying_case_stale',
        'fdr_correction_failed',
        'mechanical_vacuous',
        'tier2_uncalibrated',
        'length_confounded'
    )),
    written_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (run_id, clause_id)
);

CREATE TRIGGER clause_run_outcomes_no_update BEFORE UPDATE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;
CREATE TRIGGER clause_run_outcomes_no_delete BEFORE DELETE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;

CREATE INDEX idx_clause_run_outcomes_run ON clause_run_outcomes(run_id);
