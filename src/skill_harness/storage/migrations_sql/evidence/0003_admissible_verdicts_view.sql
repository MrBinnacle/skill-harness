-- Migration 0003: admissible_verdicts VIEW (A29)
--
-- This VIEW is the canonical aggregation surface per A29. It enforces two
-- conditions simultaneously:
--   1. admissibility_state = 'admissible'
--   2. No confound_events row with delta_kind = 'confound_flagged' exists
--      for the same (run_id, primary_clause_id = oracle_verdicts.clause_id)
--
-- The VIEW provides structural defense: ad-hoc sqlite3 queries that SELECT
-- from admissible_verdicts inherit safe defaults without requiring the caller
-- to remember both filter conditions.
--
-- Python repo layer:
--   get_admissible_verdicts(conn, run_id) -- use for aggregation (reads VIEW)
--   audit_all_verdicts(conn, run_id)      -- use for auditing (reads raw table)
--
-- A29 JOIN directionality (pending EVAL-RESEARCH at Pre-Track-D council):
-- The VIEW currently excludes verdicts whose CLAUSE_ID matches the
-- confound_events.primary_clause_id (the ablated clause). Whether the
-- AFFECTED clause (confound_events.affected_clause_id) should ALSO mark
-- its own verdicts as confounded is an EVAL-RESEARCH question to be
-- answered at the Pre-Track-D council fire. Until then, this VIEW
-- implements the A29-verbatim primary_clause_id semantics.

CREATE VIEW admissible_verdicts AS
SELECT v.*
FROM oracle_verdicts v
WHERE v.admissibility_state = 'admissible'
  AND NOT EXISTS (
    SELECT 1
    FROM confound_events ce
    WHERE ce.run_id = v.run_id
      AND ce.primary_clause_id = v.clause_id
      AND ce.delta_kind = 'confound_flagged'
  );
