-- Track E.1 migration — stale frozen case VIEWs (A57).
-- Pre-Track-E council finding A57. VIEW-creation only — no UPDATE/DELETE logic.
--
-- Rationale:
--   A15 requires "PASSED implies >=1 frozen_case at current metric_version".
--   Before this migration there was no "current" pointer for metric_versions.
--   Two VIEWs implement the pointer + currency labeling:
--
-- current_metric_versions:
--   The "current" version for each metric_id is the most-recently-registered
--   row where both audited=1 AND mechanical_validity_test_passed=1.
--   The audited+validity filter is LOAD-BEARING: a metric_version that failed
--   A14/A33 mechanical validity MUST NOT be treated as "current".
--   implementation_hash equality (not just version-string) is the
--   tamper-evident comparison per A14.
--
-- frozen_cases_with_currency:
--   Joins frozen_cases to current_metric_versions and labels each row with
--   one of three states:
--     'current'                  -- metric_version + implementation_hash both match current
--     'stale'                    -- a newer current version exists, or hash mismatch
--     'no_current_metric_version' -- no audited+valid current version for this metric_id
--
-- NOT IN THIS MIGRATION: any UPDATE/DELETE-issuing logic; Track E.2 reads these VIEWs.

CREATE VIEW current_metric_versions AS
    SELECT mv.metric_id, mv.version, mv.implementation_hash, mv.registered_at
    FROM metric_versions mv
    WHERE mv.audited = 1
      AND mv.mechanical_validity_test_passed = 1
      AND mv.registered_at = (
          SELECT MAX(mv2.registered_at)
          FROM metric_versions mv2
          WHERE mv2.metric_id = mv.metric_id
            AND mv2.audited = 1
            AND mv2.mechanical_validity_test_passed = 1
      );

CREATE VIEW frozen_cases_with_currency AS
    SELECT
        f.*,
        CASE
            WHEN c.version IS NULL THEN 'no_current_metric_version'
            WHEN f.metric_version = c.version
                 AND f.implementation_hash = c.implementation_hash THEN 'current'
            ELSE 'stale'
        END AS currency_state
    FROM frozen_cases f
    LEFT JOIN current_metric_versions c ON c.metric_id = f.metric_id;
