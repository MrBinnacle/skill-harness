-- 0500 — v0.2 subject layer: harness-pin fields on samples.
--
-- The v0.2 gate ("Harness pin" row, docs/findings/v0.2-preregistration.md)
-- requires the subject-harness configuration recorded PER TRIAL, identical
-- across arms, or the trial is inadmissible. Published agentic-benchmark
-- experience puts harness-induced variance at 10-20pp on identical weights —
-- larger than most skill effects.
--
-- Columns are nullable: pre-v0.2 rows (single-turn v0.1 subject) have no
-- agentic harness to pin. The cross-arm fingerprint equality check happens at
-- WRITE TIME in skill_harness.subject.ingest (admissibility snapshot on the
-- verdict, per the locked evidence model) — no SQL-layer CHECK added, matching
-- the 0400 pattern (Python-layer validation).
--
-- Version range note: 0500-0599 = v0.2 subject layer (extends the A30 ledger:
-- 0300-0399 Track D ablation, 0400-0499 Track E freeze).

ALTER TABLE samples ADD COLUMN harness_pin_json TEXT DEFAULT NULL;
ALTER TABLE samples ADD COLUMN harness_pin_fingerprint TEXT DEFAULT NULL;
