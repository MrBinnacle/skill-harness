-- 0700 — task-frontier phase partition (#90 tracer / spec #89, spine #84 unit 2).
--
-- Version range: 0700–0799 reserved for the task-frontier spine (see the A30
-- ledger table in migrations_sql/README.md).
--
-- WHY THREE TABLES AND NOT ONE `phase` COLUMN:
--
--   Spec #89 explicitly REJECTED a single observations table carrying a
--   `phase` column read back through `WHERE phase = 'matched'`. Under that
--   design the calibration/confirmation firewall survives only as long as
--   every caller remembers the predicate — one forgotten WHERE clause and
--   rung-selection data enters the effect estimate, which is the winner's-curse
--   bias the whole unit exists to prevent (split-sample validity; Cox 1975,
--   Fithian–Sun–Taylor 2014).
--
--   Adopted instead: a PHYSICAL partition. Each phase owns its own append-only
--   table, and the estimator feed (`matched_evidence`) can only name
--   `task_frontier_matched_obs`. There is no query you can write against the
--   matched table that returns a calibration observation, so the leak is a
--   missing table reference rather than a missing filter — the same shape as
--   0501's screen store, which is firewalled from the paired evidence model by
--   being a separate store rather than a widened `runs.run_kind`.
--
--   The `phase` column is still present on every row and still CHECK-pinned to
--   its own table's literal. It is the write-time SNAPSHOT (never recomputed at
--   read), so an audit read that holds no manifest can still say which phase a
--   record was admitted to, and a later manifest that repartitions the lineage
--   cannot move an already-written record. The CHECK makes the redundancy
--   load-bearing: a mis-filed row aborts instead of reading back under the
--   wrong phase.
--
-- SEMANTIC LINEAGE, NOT SEED: `semantic_lineage_id` is the generative source of
-- an instance. Two instances from one template are non-independent observations
-- and must not straddle the firewall (rephrased-sample contamination, Yang et
-- al. 2023) — so the partition is declared over lineages, and the lineage is
-- stamped on every row alongside the phase.
--
-- ADMISSIBILITY (mirrors oracle_verdicts / screen_runs): snapshotted at write
-- with a cited reason, never recomputed at read. #90 writes only 'admissible'
-- rows; persisting INADMISSIBLE off-manifest evidence is #92's scope and lands
-- against this same column.
--
-- ADDITIVE ONLY: no existing table is recreated and nothing here is referenced
-- by an existing FK, matching the 0300/0400/0501 pattern (the migration runner
-- applies every file inside BEGIN IMMEDIATE with PRAGMA foreign_keys=ON, where
-- the recreate-and-rename dance fails).
--
-- charset enforcement: TEXT columns use Python-layer Pydantic validation
-- (NUL/control reject), matching 0400/0500/0501 — no SQL-layer CHECK added.

CREATE TABLE task_frontier_calibration_obs (
    observation_id          TEXT PRIMARY KEY,
    task_family_id          TEXT NOT NULL,
    task_family_version     TEXT NOT NULL,
    semantic_lineage_id     TEXT NOT NULL,
    phase                   TEXT NOT NULL CHECK (phase = 'calibration'),
    instance_id             TEXT NOT NULL,
    arm                     TEXT NOT NULL CHECK (arm IN ('full', 'null')),
    passed                  INTEGER NOT NULL CHECK (passed IN (0, 1)),
    generator_fingerprint   TEXT NOT NULL,
    oracle_fingerprint      TEXT NOT NULL,
    admissibility_state     TEXT NOT NULL CHECK (admissibility_state IN ('admissible', 'inadmissible')),
    inadmissibility_reason  TEXT,
    observed_at             TEXT NOT NULL,
    ingested_at             TEXT NOT NULL
);

CREATE TABLE task_frontier_confirmation_obs (
    observation_id          TEXT PRIMARY KEY,
    task_family_id          TEXT NOT NULL,
    task_family_version     TEXT NOT NULL,
    semantic_lineage_id     TEXT NOT NULL,
    phase                   TEXT NOT NULL CHECK (phase = 'confirmation'),
    instance_id             TEXT NOT NULL,
    arm                     TEXT NOT NULL CHECK (arm IN ('full', 'null')),
    passed                  INTEGER NOT NULL CHECK (passed IN (0, 1)),
    generator_fingerprint   TEXT NOT NULL,
    oracle_fingerprint      TEXT NOT NULL,
    admissibility_state     TEXT NOT NULL CHECK (admissibility_state IN ('admissible', 'inadmissible')),
    inadmissibility_reason  TEXT,
    observed_at             TEXT NOT NULL,
    ingested_at             TEXT NOT NULL
);

CREATE TABLE task_frontier_matched_obs (
    observation_id          TEXT PRIMARY KEY,
    task_family_id          TEXT NOT NULL,
    task_family_version     TEXT NOT NULL,
    semantic_lineage_id     TEXT NOT NULL,
    phase                   TEXT NOT NULL CHECK (phase = 'matched'),
    instance_id             TEXT NOT NULL,
    arm                     TEXT NOT NULL CHECK (arm IN ('full', 'null')),
    passed                  INTEGER NOT NULL CHECK (passed IN (0, 1)),
    generator_fingerprint   TEXT NOT NULL,
    oracle_fingerprint      TEXT NOT NULL,
    admissibility_state     TEXT NOT NULL CHECK (admissibility_state IN ('admissible', 'inadmissible')),
    inadmissibility_reason  TEXT,
    observed_at             TEXT NOT NULL,
    ingested_at             TEXT NOT NULL
);

-- Family-version-scoped lookup: every claim is scoped to one task-family
-- VERSION, so that is the leading key on all three partitions.
CREATE INDEX idx_tf_calibration_family
    ON task_frontier_calibration_obs(task_family_id, task_family_version, admissibility_state);
CREATE INDEX idx_tf_confirmation_family
    ON task_frontier_confirmation_obs(task_family_id, task_family_version, admissibility_state);
CREATE INDEX idx_tf_matched_family
    ON task_frontier_matched_obs(task_family_id, task_family_version, admissibility_state);

-- Append-only enforcement (SCHEMA convention: every evidence table carries
-- BEFORE UPDATE/DELETE triggers that RAISE 'append_only_violation: <table>').
-- The UPDATE trigger is also what makes the phase stamp permanent: an attempt
-- to repartition an already-written record aborts (user story 15).
CREATE TRIGGER task_frontier_calibration_obs_no_update  BEFORE UPDATE ON task_frontier_calibration_obs  BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_calibration_obs'); END;
CREATE TRIGGER task_frontier_calibration_obs_no_delete  BEFORE DELETE ON task_frontier_calibration_obs  BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_calibration_obs'); END;
CREATE TRIGGER task_frontier_confirmation_obs_no_update BEFORE UPDATE ON task_frontier_confirmation_obs BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_confirmation_obs'); END;
CREATE TRIGGER task_frontier_confirmation_obs_no_delete BEFORE DELETE ON task_frontier_confirmation_obs BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_confirmation_obs'); END;
CREATE TRIGGER task_frontier_matched_obs_no_update      BEFORE UPDATE ON task_frontier_matched_obs      BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_matched_obs'); END;
CREATE TRIGGER task_frontier_matched_obs_no_delete      BEFORE DELETE ON task_frontier_matched_obs      BEGIN SELECT RAISE(ABORT, 'append_only_violation: task_frontier_matched_obs'); END;
