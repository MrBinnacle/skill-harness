-- Track E.1 migration — freeze provenance extensions (A56).
-- Pre-Track-E council finding A56. Track E range: 0400-0499 (per A30 range guard).
--
-- Extends frozen_cases with three new columns:
--   verdict_id            -- FK to oracle_verdicts (nullable for legacy rows)
--   run_id                -- FK to runs (nullable for legacy rows)
--   axis                  -- axis-specific frozen case (nullable for legacy rows)
--
-- Adds:
--   UNIQUE INDEX idx_frozen_unique ON frozen_cases(clause_id, axis, failing_input_sha256)
--     Prevents duplicate freeze of same (clause, axis, input) which would inflate
--     the A15 ">=1 frozen_case_at_current_metric_version" count.
--
--   BEFORE INSERT trigger frozen_cases_reject_incomplete_parent
--     Refuses INSERT when the parent run has completed_at IS NULL.
--
-- All new columns allow NULL so the migration is backward-compatible:
-- there are zero production frozen_cases rows (freeze stub was never used),
-- but the column nullability is intentional and must not be changed.
--
-- Existing BEFORE UPDATE / BEFORE DELETE triggers (0001_initial.sql) cover new
-- columns automatically — no trigger extension required.
--
-- charset enforcement: axis and other TEXT columns use Python-layer Pydantic
-- validation (NUL/control reject); no SQL-layer CHECK added (Python-layer-validation pattern).

ALTER TABLE frozen_cases ADD COLUMN verdict_id TEXT REFERENCES oracle_verdicts(verdict_id);
ALTER TABLE frozen_cases ADD COLUMN run_id TEXT REFERENCES runs(run_id);
ALTER TABLE frozen_cases ADD COLUMN axis TEXT;

CREATE UNIQUE INDEX idx_frozen_unique ON frozen_cases(clause_id, axis, failing_input_sha256);

CREATE TRIGGER frozen_cases_reject_incomplete_parent
BEFORE INSERT ON frozen_cases
WHEN NEW.run_id IS NOT NULL AND (
    SELECT completed_at FROM runs WHERE run_id = NEW.run_id
) IS NULL
BEGIN
    SELECT RAISE(ABORT, 'frozen_case_parent_incomplete');
END;
