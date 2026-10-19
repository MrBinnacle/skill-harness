-- #655 — keep clause_run_outcomes aligned with UnmeasuredSubReason.
--
-- HAZARD_NOT_MET now names a count-backed SERS refusal. The evidence-store
-- CHECK must accept every UnmeasuredSubReason: otherwise INSERT OR IGNORE can
-- silently drop a row that the write model accepts. SQLite cannot alter a CHECK
-- constraint, so rebuild the append-only table and restore its two triggers and
-- run index.

CREATE TABLE clause_run_outcomes_new (
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
        'external_check_missing',
        'length_confounded',
        'HAZARD_NOT_MET'
    )),
    written_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sought_oracle        TEXT,
    PRIMARY KEY (run_id, clause_id)
);

INSERT INTO clause_run_outcomes_new (run_id, clause_id, unmeasured_sub_reason, written_at, sought_oracle)
    SELECT run_id, clause_id, unmeasured_sub_reason, written_at, sought_oracle FROM clause_run_outcomes;

DROP TABLE clause_run_outcomes;

ALTER TABLE clause_run_outcomes_new RENAME TO clause_run_outcomes;

CREATE TRIGGER clause_run_outcomes_no_update BEFORE UPDATE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;
CREATE TRIGGER clause_run_outcomes_no_delete BEFORE DELETE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;

CREATE INDEX idx_clause_run_outcomes_run ON clause_run_outcomes(run_id);
