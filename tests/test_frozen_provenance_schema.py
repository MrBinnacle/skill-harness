"""Schema-level tests for migration 0400_freeze_provenance.sql (A56).

Tests:
- FK enforced: verdict_id references oracle_verdicts
- FK enforced: run_id references runs
- UNIQUE index on (clause_id, axis, failing_input_sha256) blocks duplicate
- BEFORE INSERT trigger rejects incomplete-parent (runs.completed_at IS NULL)
"""

from __future__ import annotations

import sqlite3

import pytest

# ---------------------------------------------------------------------------
# Shared row-insertion helpers
# ---------------------------------------------------------------------------

_TS = "2026-06-06T10:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64


def _insert_skill(conn: sqlite3.Connection, skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'S', '/p', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_clause(conn: sqlite3.Connection, clause_id: str = "cl1", skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " (?, ?, 0, 0, 'text', 'verbosity', 'decrease', 1, 'none')",
        (clause_id, skill_id),
    )


def _insert_metric_version(
    conn: sqlite3.Connection, metric_id: str = "m1", version: str = "1.0"
) -> None:
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed) VALUES (?, ?, ?, 1, 1, 1)",
        (metric_id, version, _SHA),
    )


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str = "run1",
    skill_id: str = "sk1",
    completed: bool = True,
) -> None:
    completed_at = _TS if completed else None
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, ?, 'ablation', '{}', ?, ?)",
        (run_id, skill_id, _TS, completed_at),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    sample_id: str = "samp1",
    run_id: str = "run1",
    clause_id: str = "cl1",
    condition: str = "full",
) -> None:
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at)"
        " VALUES (?, ?, ?, ?, 'model-x', 'output text', ?, ?)",
        (sample_id, run_id, clause_id, condition, _SHA, _TS),
    )


def _insert_verdict(
    conn: sqlite3.Connection,
    verdict_id: str = "vrd1",
    run_id: str = "run1",
    clause_id: str = "cl1",
    sample_a_id: str = "samp1",
    sample_b_id: str = "samp2",
    observation: float = 0.0,
) -> None:
    conn.execute(
        "INSERT INTO oracle_verdicts ("
        " verdict_id, run_id, clause_id, axis, comparison,"
        " sample_a_id, sample_b_id, observation, oracle_tier,"
        " metric_id, metric_version, judge_id, calibration_event_id,"
        " position_swap_agreement, admissibility_state, written_at"
        ") VALUES (?, ?, ?, 'verbosity', 'full_vs_ablated',"
        " ?, ?, ?, 1, 'm1', '1.0', NULL, NULL, NULL, 'admissible', ?)",
        (verdict_id, run_id, clause_id, sample_a_id, sample_b_id, observation, _TS),
    )


def _seed_standard_parent(conn: sqlite3.Connection) -> None:
    """Insert skill, clause, metric, completed run, two samples, one verdict."""
    _insert_skill(conn)
    _insert_clause(conn)
    _insert_metric_version(conn)
    _insert_run(conn, completed=True)
    _insert_sample(conn, sample_id="samp1", condition="full")
    _insert_sample(conn, sample_id="samp2", condition="ablated")
    _insert_verdict(conn)


def _insert_frozen_case(
    conn: sqlite3.Connection,
    frozen_case_id: str = "fc1",
    clause_id: str = "cl1",
    verdict_id: str | None = "vrd1",
    run_id: str | None = "run1",
    axis: str = "verbosity",
    sha: str = _SHA,
) -> None:
    conn.execute(
        "INSERT INTO frozen_cases ("
        " frozen_case_id, clause_id, failing_input_text, failing_input_sha256,"
        " oracle_source, metric_id, metric_version, implementation_hash,"
        " verdict_id, run_id, axis"
        ") VALUES (?, ?, 'bad input', ?, 'mechanical', 'm1', '1.0', ?, ?, ?, ?)",
        (frozen_case_id, clause_id, sha, _SHA, verdict_id, run_id, axis),
    )


# ---------------------------------------------------------------------------
# Tests: new columns exist
# ---------------------------------------------------------------------------


class TestNewColumnsExist:
    """Migration 0400 adds verdict_id, run_id, axis to frozen_cases."""

    def test_verdict_id_column_exists(self, evidence_db: sqlite3.Connection) -> None:
        cur = evidence_db.execute("PRAGMA table_info(frozen_cases)")
        cols = {row[1] for row in cur.fetchall()}
        assert "verdict_id" in cols, "verdict_id column missing from frozen_cases"

    def test_run_id_column_exists(self, evidence_db: sqlite3.Connection) -> None:
        cur = evidence_db.execute("PRAGMA table_info(frozen_cases)")
        cols = {row[1] for row in cur.fetchall()}
        assert "run_id" in cols, "run_id column missing from frozen_cases"

    def test_axis_column_exists(self, evidence_db: sqlite3.Connection) -> None:
        cur = evidence_db.execute("PRAGMA table_info(frozen_cases)")
        cols = {row[1] for row in cur.fetchall()}
        assert "axis" in cols, "axis column missing from frozen_cases"


# ---------------------------------------------------------------------------
# Tests: FK enforcement
# ---------------------------------------------------------------------------


class TestForeignKeys:
    """FK to oracle_verdicts and runs are enforced (open_db sets foreign_keys=ON)."""

    def test_verdict_id_fk_enforced(self, evidence_db: sqlite3.Connection) -> None:
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric_version(evidence_db)
        _insert_run(evidence_db, completed=True)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_frozen_case(
                evidence_db,
                verdict_id="nonexistent-verdict",
            )

    def test_run_id_fk_enforced(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard_parent(evidence_db)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_frozen_case(
                evidence_db,
                run_id="nonexistent-run",
            )

    def test_null_verdict_id_allowed(self, evidence_db: sqlite3.Connection) -> None:
        """verdict_id allows NULL (legacy row backward compat)."""
        _seed_standard_parent(evidence_db)
        # Should not raise — NULL verdict_id is allowed for legacy rows
        _insert_frozen_case(evidence_db, frozen_case_id="fc-null-vrd", verdict_id=None)
        row = evidence_db.execute(
            "SELECT verdict_id FROM frozen_cases WHERE frozen_case_id = 'fc-null-vrd'"
        ).fetchone()
        assert row is not None
        assert row[0] is None

    def test_null_run_id_allowed(self, evidence_db: sqlite3.Connection) -> None:
        """run_id allows NULL (legacy row backward compat)."""
        _seed_standard_parent(evidence_db)
        _insert_frozen_case(evidence_db, frozen_case_id="fc-null-run", run_id=None)
        row = evidence_db.execute(
            "SELECT run_id FROM frozen_cases WHERE frozen_case_id = 'fc-null-run'"
        ).fetchone()
        assert row is not None
        assert row[0] is None


# ---------------------------------------------------------------------------
# Tests: UNIQUE index
# ---------------------------------------------------------------------------


class TestUniqueIndex:
    """(clause_id, axis, failing_input_sha256) must be unique."""

    def test_unique_collision_raises(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard_parent(evidence_db)
        # First insert: OK
        _insert_frozen_case(evidence_db, frozen_case_id="fc1")
        # Second insert with same (clause_id, axis, sha256): must raise
        with pytest.raises(sqlite3.IntegrityError):
            _insert_frozen_case(evidence_db, frozen_case_id="fc2", sha=_SHA)

    def test_different_axis_allowed(self, evidence_db: sqlite3.Connection) -> None:
        """Same (clause_id, sha256) but different axis is allowed."""
        _seed_standard_parent(evidence_db)
        # Insert another verdict for axis2
        _insert_sample(evidence_db, sample_id="samp3", condition="null")
        _insert_verdict(evidence_db, verdict_id="vrd2", sample_a_id="samp1", sample_b_id="samp3")
        _insert_frozen_case(evidence_db, frozen_case_id="fc1", axis="verbosity")
        # Different axis — should be allowed
        _insert_frozen_case(evidence_db, frozen_case_id="fc2", axis="clarity", verdict_id="vrd2")

    def test_different_sha_allowed(self, evidence_db: sqlite3.Connection) -> None:
        """Same (clause_id, axis) but different sha256 is a distinct case."""
        _seed_standard_parent(evidence_db)
        _insert_sample(evidence_db, sample_id="samp3", condition="null")
        _insert_verdict(evidence_db, verdict_id="vrd2", sample_a_id="samp1", sample_b_id="samp3")
        _insert_frozen_case(evidence_db, frozen_case_id="fc1", sha=_SHA)
        # Different input sha — should be allowed
        _insert_frozen_case(evidence_db, frozen_case_id="fc2", verdict_id="vrd2", sha=_SHA2)


# ---------------------------------------------------------------------------
# Tests: BEFORE INSERT trigger (incomplete parent)
# ---------------------------------------------------------------------------


class TestIncompleteParentTrigger:
    """BEFORE INSERT trigger fires when the parent run has completed_at IS NULL."""

    def test_trigger_fires_for_incomplete_run(self, evidence_db: sqlite3.Connection) -> None:
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric_version(evidence_db)
        # Run inserted with completed_at IS NULL
        _insert_run(evidence_db, completed=False)
        _insert_sample(evidence_db, sample_id="samp1", condition="full")
        _insert_sample(evidence_db, sample_id="samp2", condition="ablated")
        _insert_verdict(evidence_db)

        with pytest.raises(sqlite3.IntegrityError, match="frozen_case_parent_incomplete"):
            _insert_frozen_case(evidence_db)

    def test_trigger_does_not_fire_for_complete_run(self, evidence_db: sqlite3.Connection) -> None:
        """Completed parent should insert without error."""
        _seed_standard_parent(evidence_db)
        # Should not raise
        _insert_frozen_case(evidence_db)
        row = evidence_db.execute(
            "SELECT frozen_case_id FROM frozen_cases WHERE frozen_case_id = 'fc1'"
        ).fetchone()
        assert row is not None

    def test_trigger_does_not_fire_when_run_id_null(self, evidence_db: sqlite3.Connection) -> None:
        """When run_id IS NULL, trigger WHEN condition is false — insert succeeds."""
        _seed_standard_parent(evidence_db)
        # run_id=None — trigger WHEN clause requires run_id IS NOT NULL
        _insert_frozen_case(evidence_db, frozen_case_id="fc-null", run_id=None)
        row = evidence_db.execute(
            "SELECT frozen_case_id FROM frozen_cases WHERE frozen_case_id = 'fc-null'"
        ).fetchone()
        assert row is not None
