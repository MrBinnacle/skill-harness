-- #629 — rebuild clause_run_outcomes so every refusal reason can be stored.
--
-- Migration 1100 CHECK-constrained unmeasured_sub_reason to ten literals.
-- external_check_missing (#555) was added to UnmeasuredSubReason afterwards and
-- never reached the CHECK. The writer used INSERT OR IGNORE, and SQLite's OR
-- IGNORE skips a CHECK violation as well as a key conflict, so every
-- external_check_missing refusal was dropped without an error. Historical runs
-- that lost a row stay as they are: the table is append-only and #503's scope
-- boundary is no back-fill.
--
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt: create the
-- new table, copy every row, drop the old one, rename. DROP TABLE does not fire
-- the BEFORE DELETE trigger, and the old triggers and index go with the old
-- table, so both triggers and the index are recreated below under 1100's names.
--
-- The rebuild also adds sought_oracle (#627 option 2): the axis a refused
-- clause needed an oracle for. It is set for external_check_missing and NULL
-- for every other reason, including every copied row.
--
-- The Python validator (storage/models.ClauseRunOutcomeWrite) and this CHECK
-- must list the same members of UnmeasuredSubReason. They drifted once; the
-- drift test in tests/test_issue_629_outcome_persistence.py now parses this
-- CHECK from the live schema and fails when the two disagree.

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
        'length_confounded'
    )),
    written_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sought_oracle        TEXT,
    PRIMARY KEY (run_id, clause_id)
);

INSERT INTO clause_run_outcomes_new (run_id, clause_id, unmeasured_sub_reason, written_at)
    SELECT run_id, clause_id, unmeasured_sub_reason, written_at FROM clause_run_outcomes;

DROP TABLE clause_run_outcomes;

ALTER TABLE clause_run_outcomes_new RENAME TO clause_run_outcomes;

CREATE TRIGGER clause_run_outcomes_no_update BEFORE UPDATE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;
CREATE TRIGGER clause_run_outcomes_no_delete BEFORE DELETE ON clause_run_outcomes
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: clause_run_outcomes'); END;

CREATE INDEX idx_clause_run_outcomes_run ON clause_run_outcomes(run_id);
