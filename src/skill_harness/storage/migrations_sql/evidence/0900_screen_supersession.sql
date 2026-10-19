-- #402 — supersession path for screen_runs.
--
-- screen_runs is append-only (0501 triggers block UPDATE and DELETE), which
-- means a row's admissibility_state is fixed at write time. When a later
-- ruling voids a previously-admissible screen (e.g. D4 prompt leak), the
-- correction cannot be an in-place edit and there is no re-ingest path
-- (screen_ingest.py raises AlreadyIngestedScreenError).
--
-- The correction shape already exists in this repo for two other tables:
--
--   migrations.py 480-494: migration_sha_restamps with superseded_sha256
--   metric_identity.py 224-255: metric_implementation_restamps with superseded_hash
--
-- Nothing is rewritten and nothing is removed: the correction is an appended
-- row, which is how append-only ledgers have always handled corrections. The
-- superseded row stays on the record so the edit remains auditable rather
-- than being erased by its own repair.
--
-- This migration adds:
--   1. screen_run_supersessions table (append-only, with triggers)
--   2. No changes to screen_runs itself — the existing triggers stay exactly
--      as they are.
--
-- The derivation query (derive_p0_by_skill) must exclude rows that appear as
-- superseded_screen_run_id in this table. A supersession that the derivation
-- ignores changes nothing, and one it double-counts is worse than none.

CREATE TABLE screen_run_supersessions (
    restamp_id               INTEGER PRIMARY KEY,
    superseded_screen_run_id TEXT NOT NULL UNIQUE REFERENCES screen_runs(screen_run_id),
    superseding_screen_run_id TEXT NOT NULL UNIQUE REFERENCES screen_runs(screen_run_id),
    reason                   TEXT NOT NULL,
    recorded_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TRIGGER screen_run_supersessions_no_update
    BEFORE UPDATE ON screen_run_supersessions
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_run_supersessions'); END;
CREATE TRIGGER screen_run_supersessions_no_delete
    BEFORE DELETE ON screen_run_supersessions
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: screen_run_supersessions'); END;
