-- Skill Harness — runtime DB initial schema (mutable state).
-- Adopted from council synthesis (2026-06-03): SCHEMA-F2, F-8; COST-F3.
-- This DB carries explicitly MUTABLE state: in-flight runs, current calibration
-- pointers, staging imports, cost budget bookkeeping. Append-only invariants
-- do NOT apply here.

PRAGMA foreign_keys = ON;

CREATE TABLE schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    file_sha256  TEXT NOT NULL,
    notes        TEXT
);

-- In-flight run progress. evidence.runs is the immutable envelope; this is the heartbeat.
CREATE TABLE run_progress (
    run_id            TEXT PRIMARY KEY,
    state             TEXT NOT NULL CHECK (state IN ('pending','running','draining','completed','failed','aborted_budget')),
    samples_planned   INTEGER NOT NULL,
    samples_collected INTEGER NOT NULL DEFAULT 0,
    last_heartbeat    TEXT NOT NULL,
    error             TEXT
);

-- "Current" calibration pointer per (judge_id, axis). Mutated on every recalibration;
-- the immutable history lives in evidence.calibration_events.
CREATE TABLE current_calibration (
    judge_id              TEXT NOT NULL,
    axis                  TEXT NOT NULL,
    calibration_event_id  TEXT NOT NULL,   -- FK into evidence.calibration_events (cross-DB; enforced at app layer)
    state                 TEXT NOT NULL CHECK (state IN ('calibrated','conditional','uncalibrated','expired')),
    expires_at            TEXT,
    updated_at            TEXT NOT NULL,
    PRIMARY KEY (judge_id, axis)
);

CREATE TABLE skill_imports_staging (
    staging_id  TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('parsing','extracted','rejected','promoted')),
    notes       TEXT,
    updated_at  TEXT NOT NULL
);

-- COST-F3 per-run budget + ledger. Hard-cap enforcement reads + updates here
-- inside the same transaction as the sample insert.
CREATE TABLE run_budget (
    run_id            TEXT PRIMARY KEY,
    hard_cap_usd      REAL NOT NULL,
    tokens_spent_in   INTEGER NOT NULL DEFAULT 0,
    tokens_spent_out  INTEGER NOT NULL DEFAULT 0,
    cache_write_in    INTEGER NOT NULL DEFAULT 0,
    cache_read_in     INTEGER NOT NULL DEFAULT 0,
    usd_spent         REAL NOT NULL DEFAULT 0.0,
    dry_run           INTEGER NOT NULL DEFAULT 1 CHECK (dry_run IN (0,1)),
    aborted_at        TEXT,
    last_updated      TEXT NOT NULL
);

-- COST-F3 rolling per-day cap. INSERT per API call; daily cap check sums trailing 24h.
CREATE TABLE cost_ledger (
    ledger_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    run_id         TEXT,
    skill_id       TEXT,
    model_id       TEXT NOT NULL,
    call_kind      TEXT NOT NULL CHECK (call_kind IN ('subject','judge')),
    input_tok      INTEGER NOT NULL,
    cache_write_tok INTEGER NOT NULL DEFAULT 0,
    cache_read_tok INTEGER NOT NULL DEFAULT 0,
    output_tok     INTEGER NOT NULL,
    usd            REAL NOT NULL
);

CREATE INDEX idx_cost_ledger_ts ON cost_ledger(ts);
CREATE INDEX idx_cost_ledger_run ON cost_ledger(run_id);
