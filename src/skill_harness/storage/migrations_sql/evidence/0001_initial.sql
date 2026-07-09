-- Skill Harness — evidence DB initial schema
-- Adopted from council synthesis (2026-06-03): SCHEMA-F1, F-2, F-3, F-6, F-7; STAT-F3, F-4; TEST-ARCH-F1, F-4, F-5; EVAL-F5, F-7; COST-F3, F-5.
-- This DB is APPEND-ONLY. Every evidence table carries BEFORE UPDATE/DELETE triggers.

PRAGMA foreign_keys = ON;

-- Migration ledger (must be created BEFORE other tables; the runner stamps this).
CREATE TABLE schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    file_sha256  TEXT NOT NULL,
    notes        TEXT
);
CREATE TRIGGER schema_migrations_no_update BEFORE UPDATE ON schema_migrations
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: schema_migrations'); END;
CREATE TRIGGER schema_migrations_no_delete BEFORE DELETE ON schema_migrations
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: schema_migrations'); END;

-- ---------------------------------------------------------------------------
-- Domain tables
-- ---------------------------------------------------------------------------

CREATE TABLE skills (
    skill_id      TEXT PRIMARY KEY,                  -- content hash of skill source
    name          TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    imported_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE clauses (
    clause_id          TEXT PRIMARY KEY,                  -- hash(skill_id || clause_index)
    skill_id           TEXT NOT NULL REFERENCES skills(skill_id),
    clause_index       INTEGER NOT NULL,                  -- authoring order (frozen)
    rendering_index    INTEGER NOT NULL,                  -- runtime ordering for cache reuse (COST-F2)
    clause_text        TEXT NOT NULL,
    axis               TEXT NOT NULL,
    comparator         TEXT NOT NULL CHECK (comparator IN ('increase','decrease','match')),
    oracle_tier        INTEGER NOT NULL CHECK (oracle_tier IN (1,2,3)),
    vacuity_flag       TEXT NOT NULL DEFAULT 'none'
                       CHECK (vacuity_flag IN ('none','mechanical_vacuous','semantic_vacuous_pending_review')),
    falsifying_case_schema_sha256 TEXT,                   -- nullable until §7a Falsifying Case Schema is frozen
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(skill_id, clause_index)
);

-- §10 metric provenance — every Tier-1 metric is a versioned, hashed artifact.
CREATE TABLE metric_versions (
    metric_id           TEXT NOT NULL,
    version             TEXT NOT NULL,                    -- semver
    implementation_hash TEXT NOT NULL,                    -- sha256 of implementation source
    tier                INTEGER NOT NULL CHECK (tier IN (1,2,3)),
    audited             INTEGER NOT NULL DEFAULT 0 CHECK (audited IN (0,1)),
    mechanical_validity_test_passed INTEGER NOT NULL DEFAULT 0 CHECK (mechanical_validity_test_passed IN (0,1)),
    registered_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (metric_id, version)
);

CREATE TABLE judges (
    judge_id             TEXT PRIMARY KEY,                -- hash(model_id || system_prompt_sha256)
    model_id             TEXT NOT NULL,
    system_prompt_sha256 TEXT NOT NULL,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- §13 calibration — APPEND-ONLY history of every calibration validation.
-- The "current" pointer lives in runtime.db.current_calibration; this is the audit trail.
CREATE TABLE calibration_events (
    calibration_event_id        TEXT PRIMARY KEY,
    judge_id                    TEXT NOT NULL REFERENCES judges(judge_id),
    axis                        TEXT NOT NULL,
    -- primary pairwise-preference metric (EVAL-F2): position-swap-symmetric agreement on pairs
    pairwise_agreement          REAL NOT NULL CHECK (pairwise_agreement BETWEEN 0 AND 1),
    position_consistency        REAL NOT NULL CHECK (position_consistency BETWEEN 0 AND 1),
    length_controlled_agreement REAL,
    cohen_kappa                 REAL,                     -- secondary, chance-corrected
    pair_set_size               INTEGER NOT NULL CHECK (pair_set_size >= 50),
    pair_set_sha256             TEXT NOT NULL,
    state                       TEXT NOT NULL CHECK (state IN ('calibrated','conditional','uncalibrated','expired')),
    expires_at                  TEXT,                     -- 90-day default, nullable
    validated_at                TEXT NOT NULL
);

-- Runs are RECORDED here; in-flight progress lives in runtime.db.run_progress.
-- completed_at is the one mutable field (NULL → timestamp, ONCE), enforced by trigger.
CREATE TABLE runs (
    run_id        TEXT PRIMARY KEY,
    skill_id      TEXT NOT NULL REFERENCES skills(skill_id),
    run_kind      TEXT NOT NULL CHECK (run_kind IN ('ablation','evaluate_skill','diff')),
    config_json   TEXT NOT NULL,                          -- frozen at run start (includes K, N, thresholds, model)
    started_at    TEXT NOT NULL,
    completed_at  TEXT                                    -- nullable until run completes
);

-- Append-only stochastic outputs from the subject model.
CREATE TABLE samples (
    sample_id      TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    clause_id      TEXT NOT NULL REFERENCES clauses(clause_id),
    condition      TEXT NOT NULL CHECK (condition IN ('full','ablated','null')),
    subject_model  TEXT NOT NULL,
    subject_seed   TEXT,
    output_text    TEXT NOT NULL,
    output_sha256  TEXT NOT NULL,
    sampled_at     TEXT NOT NULL
);

-- §6 admissibility recorded AT WRITE TIME. The calibration_event_id FK snapshots
-- the exact calibration state that gated admissibility — never recomputed.
-- Tier-1 verdicts leave judge_id/calibration_event_id NULL; Tier-2 require both NOT NULL.
CREATE TABLE oracle_verdicts (
    verdict_id              TEXT PRIMARY KEY,
    run_id                  TEXT NOT NULL REFERENCES runs(run_id),
    clause_id               TEXT NOT NULL REFERENCES clauses(clause_id),
    axis                    TEXT NOT NULL,
    comparison              TEXT NOT NULL CHECK (comparison IN ('full_vs_ablated','full_vs_null')),
    sample_a_id             TEXT NOT NULL REFERENCES samples(sample_id),
    sample_b_id             TEXT NOT NULL REFERENCES samples(sample_id),
    -- {0, 0.5, 1} encoding adopted per STAT-F4 "half-update" reconciliation;
    -- tie_count column lets aggregator switch to drop-ties at report time without re-sampling.
    observation             REAL NOT NULL CHECK (observation IN (0.0, 0.5, 1.0)),
    oracle_tier             INTEGER NOT NULL CHECK (oracle_tier IN (1,2,3)),
    metric_id               TEXT,
    metric_version          TEXT,
    judge_id                TEXT REFERENCES judges(judge_id),
    calibration_event_id    TEXT REFERENCES calibration_events(calibration_event_id),
    position_swap_agreement INTEGER CHECK (position_swap_agreement IN (0, 1)),  -- EVAL-F7: NULL for Tier-1
    admissibility_state     TEXT NOT NULL CHECK (admissibility_state IN ('admissible','inadmissible')),
    inadmissibility_reason  TEXT,
    written_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (metric_id, metric_version) REFERENCES metric_versions(metric_id, version),
    -- Tier-1 verdicts must NOT carry judge fields; Tier-2 verdicts MUST.
    CHECK (
        (oracle_tier = 1 AND judge_id IS NULL AND calibration_event_id IS NULL AND metric_id IS NOT NULL)
     OR (oracle_tier = 2 AND judge_id IS NOT NULL AND calibration_event_id IS NOT NULL)
     OR (oracle_tier = 3)
    )
);

-- §11 confound detection over the FULL metric universe, not just clause-claimed axes (TEST-ARCH-F3).
-- delta_kind distinguishes confound (claimed axis moved) from orphan observation.
CREATE TABLE confound_events (
    confound_event_id   TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(run_id),
    primary_clause_id   TEXT NOT NULL REFERENCES clauses(clause_id),
    affected_clause_id  TEXT REFERENCES clauses(clause_id),    -- NULL for orphan axes
    axis                TEXT NOT NULL,
    delta               REAL NOT NULL,
    null_sigma          REAL NOT NULL,                          -- EVAL-F6: σ_Y(Null)
    k_threshold         REAL NOT NULL,                          -- default 2.0
    delta_kind          TEXT NOT NULL
                        CHECK (delta_kind IN ('confound_flagged','observed_unclaimed_delta')),
    detected_at         TEXT NOT NULL
);

-- §9 frozen regression suite — provenance lanes per oracle source.
CREATE TABLE frozen_cases (
    frozen_case_id      TEXT PRIMARY KEY,
    clause_id           TEXT NOT NULL REFERENCES clauses(clause_id),
    failing_input_text  TEXT NOT NULL,
    failing_input_sha256 TEXT NOT NULL,
    oracle_source       TEXT NOT NULL CHECK (oracle_source IN ('human','mechanical')),
    -- human provenance:
    labeled_by          TEXT,
    labeled_at          TEXT,
    -- mechanical provenance:
    metric_id           TEXT,
    metric_version      TEXT,
    implementation_hash TEXT,                                   -- snapshot copy for tamper-evidence
    frozen_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Tier-3 oracle deferred to v0.2 per EVAL-F3.
    CHECK (
        (oracle_source = 'human'      AND labeled_by IS NOT NULL AND labeled_at IS NOT NULL)
     OR (oracle_source = 'mechanical' AND metric_id IS NOT NULL AND metric_version IS NOT NULL AND implementation_hash IS NOT NULL)
    ),
    FOREIGN KEY (metric_id, metric_version) REFERENCES metric_versions(metric_id, version)
);

-- ---------------------------------------------------------------------------
-- Append-only enforcement triggers (SCHEMA-F1, F-6).
-- ---------------------------------------------------------------------------

CREATE TRIGGER skills_no_update            BEFORE UPDATE ON skills            BEGIN SELECT RAISE(ABORT, 'append_only_violation: skills'); END;
CREATE TRIGGER skills_no_delete            BEFORE DELETE ON skills            BEGIN SELECT RAISE(ABORT, 'append_only_violation: skills'); END;
CREATE TRIGGER clauses_no_update           BEFORE UPDATE ON clauses           BEGIN SELECT RAISE(ABORT, 'append_only_violation: clauses'); END;
CREATE TRIGGER clauses_no_delete           BEFORE DELETE ON clauses           BEGIN SELECT RAISE(ABORT, 'append_only_violation: clauses'); END;
CREATE TRIGGER metric_versions_no_update   BEFORE UPDATE ON metric_versions   BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_versions'); END;
CREATE TRIGGER metric_versions_no_delete   BEFORE DELETE ON metric_versions   BEGIN SELECT RAISE(ABORT, 'append_only_violation: metric_versions'); END;
CREATE TRIGGER judges_no_update            BEFORE UPDATE ON judges            BEGIN SELECT RAISE(ABORT, 'append_only_violation: judges'); END;
CREATE TRIGGER judges_no_delete            BEFORE DELETE ON judges            BEGIN SELECT RAISE(ABORT, 'append_only_violation: judges'); END;
CREATE TRIGGER calibration_events_no_update BEFORE UPDATE ON calibration_events BEGIN SELECT RAISE(ABORT, 'append_only_violation: calibration_events'); END;
CREATE TRIGGER calibration_events_no_delete BEFORE DELETE ON calibration_events BEGIN SELECT RAISE(ABORT, 'append_only_violation: calibration_events'); END;
CREATE TRIGGER samples_no_update           BEFORE UPDATE ON samples           BEGIN SELECT RAISE(ABORT, 'append_only_violation: samples'); END;
CREATE TRIGGER samples_no_delete           BEFORE DELETE ON samples           BEGIN SELECT RAISE(ABORT, 'append_only_violation: samples'); END;
CREATE TRIGGER oracle_verdicts_no_update   BEFORE UPDATE ON oracle_verdicts   BEGIN SELECT RAISE(ABORT, 'append_only_violation: oracle_verdicts'); END;
CREATE TRIGGER oracle_verdicts_no_delete   BEFORE DELETE ON oracle_verdicts   BEGIN SELECT RAISE(ABORT, 'append_only_violation: oracle_verdicts'); END;
CREATE TRIGGER confound_events_no_update   BEFORE UPDATE ON confound_events   BEGIN SELECT RAISE(ABORT, 'append_only_violation: confound_events'); END;
CREATE TRIGGER confound_events_no_delete   BEFORE DELETE ON confound_events   BEGIN SELECT RAISE(ABORT, 'append_only_violation: confound_events'); END;
CREATE TRIGGER frozen_cases_no_update      BEFORE UPDATE ON frozen_cases      BEGIN SELECT RAISE(ABORT, 'append_only_violation: frozen_cases'); END;
CREATE TRIGGER frozen_cases_no_delete      BEFORE DELETE ON frozen_cases      BEGIN SELECT RAISE(ABORT, 'append_only_violation: frozen_cases'); END;

-- runs.completed_at is the sole mutable field (set once on completion).
CREATE TRIGGER runs_completed_at_once BEFORE UPDATE ON runs
    WHEN OLD.completed_at IS NOT NULL
    BEGIN SELECT RAISE(ABORT, 'runs.completed_at is immutable once set'); END;
CREATE TRIGGER runs_no_delete BEFORE DELETE ON runs
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: runs'); END;

-- ---------------------------------------------------------------------------
-- Indexes (SCHEMA-F7) — confound detection + aggregation hot paths.
-- ---------------------------------------------------------------------------

CREATE INDEX idx_verdicts_run_axis_cond   ON oracle_verdicts(run_id, axis, comparison);
CREATE INDEX idx_verdicts_run_clause      ON oracle_verdicts(run_id, clause_id);
CREATE INDEX idx_verdicts_clause_adm      ON oracle_verdicts(clause_id, admissibility_state);
CREATE INDEX idx_samples_run_clause_cond  ON samples(run_id, clause_id, condition);
CREATE INDEX idx_frozen_clause            ON frozen_cases(clause_id, oracle_source);
CREATE INDEX idx_clauses_skill            ON clauses(skill_id, clause_index);
CREATE INDEX idx_calib_judge_axis_validated ON calibration_events(judge_id, axis, validated_at);
CREATE INDEX idx_confound_run             ON confound_events(run_id, primary_clause_id);
