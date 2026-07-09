-- Phase 1.5 council finding A20 (SCHEMA-F3): the original `runs_completed_at_once`
-- trigger was BEFORE UPDATE without a `OF <column>` clause, so it fired on ANY
-- UPDATE to runs once completed_at was set. The trigger name and its error
-- message ("runs.completed_at is immutable once set") implied a per-column
-- guard, but the SQL implemented per-row. The two readings disagreed; SCHEMA
-- confirmed at council that column-immutable was the intent.
--
-- This migration replaces the single trigger with two named, column-scoped
-- triggers that match the intent:
--
--   * runs_completed_at_set_once  — completed_at may transition NULL → value
--     exactly once. Any further UPDATE to completed_at aborts.
--   * runs_immutable_columns      — skill_id, run_kind, config_json, started_at
--     are immutable post-insert; any UPDATE to those aborts unconditionally.
--
-- The PRIMARY KEY (run_id) is already immutable per SQLite.

DROP TRIGGER IF EXISTS runs_completed_at_once;

CREATE TRIGGER runs_completed_at_set_once
    BEFORE UPDATE OF completed_at ON runs
    WHEN OLD.completed_at IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'runs.completed_at is immutable once set');
    END;

CREATE TRIGGER runs_immutable_columns
    BEFORE UPDATE OF skill_id, run_kind, config_json, started_at ON runs
    BEGIN
        SELECT RAISE(ABORT, 'append_only_violation: runs (immutable column)');
    END;
