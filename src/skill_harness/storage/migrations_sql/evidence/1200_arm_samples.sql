-- #554 — declared-arm (composition) sampling evidence.
--
-- A declared-arm run's unit of comparison is a named arm: a whole prompt
-- assembly (base system + the skill bodies the arm includes), not one clause
-- of one card. The clause-keyed `samples` table cannot carry that unit: its
-- condition column is CHECK-constrained to ('full','ablated','null') and its
-- clause_id is a NOT NULL FK into clauses. Composition arms have neither a
-- clause nor a closed condition name, so their subject outputs get their own
-- append-only table rather than a widened vocabulary on `samples`.
--
-- `arm` carries the run's declared arm name. The vocabulary floor lives in the
-- Python write model (ArmSampleWrite, reading ARM_NAME_PATTERN from
-- storage.models, the single definition shared with the ablation arms module
-- and the SERS receipt mint); this SQL CHECK is the defence-in-depth copy of
-- the same slug rule, like every evidence table's CHECK.
--
-- UNIQUE(run_id, arm, sample_index) is the idempotency key, mirroring
-- samples' UNIQUE(run_id, clause_id, condition, sample_index) (A40): a
-- double-INSERT on the same tuple raises UNIQUE instead of double-counting
-- spend. Per-call cost columns (A41) are written from the actual response
-- usage inside the evidence transaction; the A41 reconciler sums them
-- together with samples.usd as the authoritative evidence spend.
--
-- Append-only, like every evidence table: BEFORE UPDATE / BEFORE DELETE
-- triggers raise append_only_violation.

CREATE TABLE arm_samples (
    sample_id      TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    arm            TEXT NOT NULL CHECK (
                       arm <> ''
                       AND arm NOT GLOB '*[^a-z0-9_-]*'
                       AND arm NOT GLOB '_*'
                       AND arm NOT GLOB '-*'
                   ),
    sample_index   INTEGER NOT NULL,
    subject_model  TEXT NOT NULL,
    subject_seed   TEXT,
    output_text    TEXT NOT NULL,
    output_sha256  TEXT NOT NULL,
    sampled_at     TEXT NOT NULL,
    input_tokens INTEGER DEFAULT NULL,
    cache_read_input_tokens INTEGER DEFAULT NULL,
    cache_creation_input_tokens INTEGER DEFAULT NULL,
    output_tokens INTEGER DEFAULT NULL,
    usd REAL DEFAULT NULL,
    UNIQUE (run_id, arm, sample_index)
);

CREATE TRIGGER arm_samples_no_update
    BEFORE UPDATE ON arm_samples
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: arm_samples'); END;
CREATE TRIGGER arm_samples_no_delete
    BEFORE DELETE ON arm_samples
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: arm_samples'); END;
