-- 0600 — model pin + drift fingerprint on oracle_verdicts (#75, Honest Live Board S1).
--
-- Every newly-minted verdict pins the model it was measured on so no cell floats
-- free of its measuring model. Columns are nullable: pre-registry / historical
-- rows are NOT retrofitted (#41 no-retrofit). Enforcement of the pin on new
-- mints is at the Python mint paths (ArticleFingerprint), matching the 0400 /
-- 0500 pattern (Python-layer validation; no SQL CHECK that would reject legacy
-- NULL rows).
--
-- Columns:
--   model_snapshot         — primary pin (subject/judge model id at measure time)
--   response_fingerprint   — fallback pin when no model snapshot exists
--   requalify_on_drift     — 1 when the fallback path was used (must requalify
--                            on fleet drift rather than simple model compare)
--   drift_fingerprint      — stable token compared to the current fleet model
--                            (precondition for the board day-one stale badge)
--
-- Version range: 0600–0699 reserved for Honest Live Board delivery spine.

ALTER TABLE oracle_verdicts ADD COLUMN model_snapshot TEXT DEFAULT NULL;
ALTER TABLE oracle_verdicts ADD COLUMN response_fingerprint TEXT DEFAULT NULL;
ALTER TABLE oracle_verdicts ADD COLUMN requalify_on_drift INTEGER NOT NULL DEFAULT 0
    CHECK (requalify_on_drift IN (0, 1));
ALTER TABLE oracle_verdicts ADD COLUMN drift_fingerprint TEXT DEFAULT NULL;
