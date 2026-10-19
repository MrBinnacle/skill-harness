-- 0501 — v0.2 subject layer: Stage-0 Null-only SCREEN store.
--
-- Version range note: 0500-0599 = v0.2 subject layer (per the A30 ledger in
-- 0500). This is the screen sibling of 0500's paired harness-pin extensions.
--
-- WHY A SEPARATE STORE (not a widened runs.run_kind, not oracle_verdicts):
--
--   1. The pre-registration (docs/findings/v0.2-preregistration.md, Stage 0)
--      is explicit: "Null-only screen ... screen data NEVER ENTERS VERDICTS."
--      Screens are a hardness GATE (p0 < 1 → proceed to a paired Stage-1 run),
--      not a Full-vs-Null contrast. Routing them through oracle_verdicts
--      (comparison IN ('full_vs_ablated','full_vs_null'), two NOT NULL sample
--      refs, observation = a contrast) would both misuse that table and
--      violate the firewall. A screen is a SINGLE-arm pass rate; no contrast
--      exists.
--
--   2. A single arm's pass/fail is stored NOWHERE in the paired model: samples
--      carries output/tokens/pin but no score; the score only exists as the
--      paired oracle_verdicts.observation. So a Null-only p0 needs new storage
--      regardless.
--
--   3. Widening runs.run_kind to add 'screen' would require recreating the
--      `runs` table (SQLite cannot alter a CHECK in place). `runs` is
--      referenced by samples/oracle_verdicts/frozen_cases and carries three
--      triggers; the migration runner applies every migration INSIDE a
--      BEGIN IMMEDIATE transaction with PRAGMA foreign_keys=ON, and
--      `PRAGMA foreign_keys=OFF` is a documented no-op inside a transaction.
--      Empirically the recreate-and-rename dance fails with
--      "FOREIGN KEY constraint failed" (the implicit DELETE of runs rows hits
--      the samples FK). This migration is therefore purely ADDITIVE, matching
--      the 0300/0400 pattern, and touches nothing referenced.
--
-- ISOLATION: screen_runs is keyed by skill_name (the Inspect log's `skill`
-- metadata), NOT skill_id (= sha256 of SKILL.md). Screens are firewalled from
-- the paired evidence identity model, so they take no FK into skills/runs and
-- carry no dependency on SKILL.md bytes at backfill time. A screen store is
-- fully reconstructable from the .eval logs alone.
--
-- ADMISSIBILITY (mirrors oracle_verdicts.admissibility_state): a voided screen
-- (e.g. an oracle-harness crash: exit=1 with no structured ORACLE-PASS, or a
-- credit-exhaustion incident) is INGESTED and marked inadmissible — the
-- append-only ethos keeps the evidence of the void — and p0 derivation
-- excludes it. The admissibility decision is recorded per screen_run with a
-- cited reason; it is the one human judgment in the pipeline, localized and
-- auditable against the stored scorer_explanation of each trial.
--
-- p0 is DERIVED, never stored (Discipline 6): mean(passed) over the trials of
-- ADMISSIBLE screen_runs for a skill. See aggregation/screen_p0.py.
--
-- charset enforcement: TEXT columns use Python-layer Pydantic validation
-- (NUL/control reject), matching 0400/0500 — no SQL-layer CHECK added.

CREATE TABLE screen_runs (
    screen_run_id           TEXT PRIMARY KEY,
    skill_name              TEXT NOT NULL,
    subject_model           TEXT NOT NULL,
    harness_pin_fingerprint TEXT,
    source_eval_task_id     TEXT NOT NULL,
    source_eval_sha256      TEXT NOT NULL,
    admissibility_state     TEXT NOT NULL CHECK (admissibility_state IN ('admissible','inadmissible')),
    inadmissibility_reason  TEXT,
    created_at              TEXT NOT NULL,
    ingested_at             TEXT NOT NULL
);

CREATE TABLE screen_trials (
    screen_trial_id     TEXT PRIMARY KEY,
    screen_run_id       TEXT NOT NULL REFERENCES screen_runs(screen_run_id),
    epoch               INTEGER NOT NULL,
    passed              INTEGER NOT NULL CHECK (passed IN (0, 1)),
    scorer_name         TEXT NOT NULL,
    scorer_explanation  TEXT,
    output_sha256       TEXT NOT NULL,
    sampled_at          TEXT NOT NULL,
    UNIQUE (screen_run_id, epoch)
);

CREATE INDEX idx_screen_trials_run ON screen_trials(screen_run_id);
CREATE INDEX idx_screen_runs_skill ON screen_runs(skill_name, admissibility_state);

-- Append-only enforcement (SCHEMA convention: every evidence table carries
-- BEFORE UPDATE/DELETE triggers that RAISE 'append_only_violation: <table>').
CREATE TRIGGER screen_runs_no_update   BEFORE UPDATE ON screen_runs   BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_runs'); END;
CREATE TRIGGER screen_runs_no_delete   BEFORE DELETE ON screen_runs   BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_runs'); END;
CREATE TRIGGER screen_trials_no_update BEFORE UPDATE ON screen_trials BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_trials'); END;
CREATE TRIGGER screen_trials_no_delete BEFORE DELETE ON screen_trials BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_trials'); END;
