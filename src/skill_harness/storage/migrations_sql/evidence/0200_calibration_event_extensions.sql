-- Track C migration — calibration_event statistical + cost-provenance extensions.
-- Adopted findings: A37 (Pre-Track-C council 2026-06-05).
-- Track C range: 0200-0299 (per A30 range guard).
--
-- Adds 10 columns to evidence.calibration_events:
--   STAT extensions: n_a, n_b, n_tie (human-pref counts),
--                    judge_n_a, judge_n_b, judge_n_tie (judge verdict counts),
--                    length_regression_coefficient (β₁, written by C.4),
--                    chance_baseline (p_e from κ formula)
--   COST extensions: total_usd_spent, cost_ledger_run_id
--
-- All new columns default to NULL per ALTER TABLE ADD COLUMN semantics.
-- Existing BEFORE UPDATE / BEFORE DELETE triggers (0001_initial.sql) use
-- whole-row RAISE(ABORT) — they cover new columns automatically because
-- they fire on any UPDATE/DELETE, not on specific column changes.
-- No trigger extension required (verified by test_migration_0200.py).
--
-- state CHECK constraint:
--   Original (0001): state IN ('calibrated','conditional','uncalibrated','expired')
--   A37 adds 'rejected' to the Python model enum; however, rejected events are
--   NEVER written to the DB (N<50 → refuse-to-write per A34). The DB CHECK
--   constraint therefore remains unchanged — 'rejected' is a Python-layer state
--   that gates the write decision, not a persisted value.

ALTER TABLE calibration_events ADD COLUMN n_a INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN n_b INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN n_tie INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN judge_n_a INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN judge_n_b INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN judge_n_tie INTEGER DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN length_regression_coefficient REAL DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN chance_baseline REAL DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN total_usd_spent REAL DEFAULT NULL;
ALTER TABLE calibration_events ADD COLUMN cost_ledger_run_id TEXT DEFAULT NULL;
