-- #501 — structural outcome covariates remain separate from decision evidence.
CREATE TABLE sample_structural_covariates (
    sample_id TEXT PRIMARY KEY REFERENCES samples(sample_id),
    state TEXT NOT NULL CHECK (state IN ('measured', 'unmeasured')),
    unmeasured_reason TEXT,
    base_commit TEXT,
    registration_json TEXT,
    command_identity_json TEXT,
    reverse_test_pass INTEGER CHECK (reverse_test_pass IN (0, 1)),
    scope_files_ok INTEGER CHECK (scope_files_ok IN (0, 1)),
    scope_net_line_growth INTEGER,
    scope_changed_file_count INTEGER,
    mechanical_checks_ok INTEGER CHECK (mechanical_checks_ok IN (0, 1)),
    measured_at TEXT NOT NULL,
    CHECK (
      (state = 'measured'
       AND unmeasured_reason IS NULL
       AND base_commit IS NOT NULL
       AND registration_json IS NOT NULL
       AND command_identity_json IS NOT NULL
       AND reverse_test_pass IS NOT NULL
       AND scope_files_ok IS NOT NULL
       AND scope_net_line_growth IS NOT NULL
       AND scope_changed_file_count IS NOT NULL
       AND mechanical_checks_ok IS NOT NULL)
      OR
      (state = 'unmeasured'
       AND unmeasured_reason IS NOT NULL
       AND reverse_test_pass IS NULL
       AND scope_files_ok IS NULL
       AND scope_net_line_growth IS NULL
       AND scope_changed_file_count IS NULL
       AND mechanical_checks_ok IS NULL)
    )
);
CREATE TRIGGER sample_structural_covariates_no_update
    BEFORE UPDATE ON sample_structural_covariates
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: sample_structural_covariates'); END;
CREATE TRIGGER sample_structural_covariates_no_delete
    BEFORE DELETE ON sample_structural_covariates
    BEGIN SELECT RAISE(ABORT, 'append_only_violation: sample_structural_covariates'); END;
