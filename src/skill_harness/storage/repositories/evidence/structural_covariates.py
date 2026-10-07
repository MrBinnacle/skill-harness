"""Repository functions for append-only structural covariate evidence."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal

from skill_harness.subject.structural_covariates import StructuralCovariates

__all__ = ["append_structural_covariates"]


def append_structural_covariates(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    condition: Literal["full", "null"],
    epoch: int,
    covariates: StructuralCovariates,
) -> None:
    """Append one covariate row after normal sample ingest."""
    rows = conn.execute(
        "SELECT sample_id FROM samples WHERE run_id = ? AND condition = ? AND sample_index = ?",
        (run_id, condition, epoch),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(
            "structural covariates require exactly one ingested sample for "
            f"run={run_id!r}, condition={condition!r}, epoch={epoch}; found {len(rows)}"
        )
    conn.execute(
        """
        INSERT INTO sample_structural_covariates (
            sample_id, state, unmeasured_reason, base_commit,
            registration_json, command_identity_json, reverse_test_pass,
            scope_files_ok, scope_net_line_growth, scope_changed_file_count,
            mechanical_checks_ok, measured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(rows[0][0]),
            covariates.state,
            None if covariates.unmeasured_reason is None else covariates.unmeasured_reason.value,
            covariates.base_commit,
            covariates.registration_json,
            covariates.command_identity_json,
            covariates.reverse_test_pass,
            covariates.scope_files_ok,
            covariates.scope_net_line_growth,
            covariates.scope_changed_file_count,
            covariates.mechanical_checks_ok,
            datetime.now(UTC).isoformat(),
        ),
    )
