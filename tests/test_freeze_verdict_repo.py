"""Repository-level tests for freeze_verdict (A56).

Tests:
- freeze_verdict requires observation in {0.0, 0.5} (FAILING side)
- freeze_verdict requires admissibility_state == 'admissible'
- freeze_verdict requires oracle_source == 'mechanical' (Tier-1 only in v0.1)
- freeze_verdict requires parent runs.completed_at IS NOT NULL
- freeze_verdict auto-fills provenance from metric_versions
- freeze_verdict auto-fills failing_input_text from samples
- freeze_verdict returns a frozen_case_id string
- duplicate freeze (same clause_id, axis, sha256) raises sqlite3.IntegrityError
- winning verdict (observation=1.0) cannot be frozen
"""

from __future__ import annotations

import sqlite3

import pytest

from skill_harness.storage.repositories.evidence.frozen_cases import freeze_verdict

_TS = "2026-06-06T10:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_skill(conn: sqlite3.Connection, skill_id: str = "sk1") -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES (?, 'S', '/p', ?, ?)",
        (skill_id, _SHA, _TS),
    )


def _insert_clause(conn: sqlite3.Connection, clause_id: str = "cl1") -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " (?, 'sk1', 0, 0, 'text', 'verbosity', 'decrease', 1, 'none')",
        (clause_id,),
    )


def _insert_metric(conn: sqlite3.Connection, metric_id: str = "m1", version: str = "1.0") -> None:
    conn.execute(
        "INSERT INTO metric_versions (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed) VALUES (?, ?, ?, 1, 1, 1)",
        (metric_id, version, _SHA),
    )


def _insert_run(conn: sqlite3.Connection, run_id: str = "run1", completed: bool = True) -> None:
    completed_at = _TS if completed else None
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, 'sk1', 'ablation', '{}', ?, ?)",
        (run_id, _TS, completed_at),
    )


def _insert_sample(
    conn: sqlite3.Connection,
    sample_id: str,
    run_id: str = "run1",
    clause_id: str = "cl1",
    condition: str = "full",
    output_text: str = "sample output text",
) -> None:
    import hashlib

    sha = hashlib.sha256(output_text.encode()).hexdigest()
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at)"
        " VALUES (?, ?, ?, ?, 'model-x', ?, ?, ?)",
        (sample_id, run_id, clause_id, condition, output_text, sha, _TS),
    )


def _insert_verdict(
    conn: sqlite3.Connection,
    verdict_id: str = "vrd1",
    run_id: str = "run1",
    clause_id: str = "cl1",
    sample_a_id: str = "samp1",
    sample_b_id: str = "samp2",
    observation: float = 0.0,
    oracle_tier: int = 1,
    metric_id: str | None = "m1",
    metric_version: str | None = "1.0",
    admissibility_state: str = "admissible",
) -> None:
    judge_id = None
    calib_id = None
    pos_swap = None
    if oracle_tier == 2:
        judge_id = "judge1"
        calib_id = "cal1"
    conn.execute(
        "INSERT INTO oracle_verdicts ("
        " verdict_id, run_id, clause_id, axis, comparison,"
        " sample_a_id, sample_b_id, observation, oracle_tier,"
        " metric_id, metric_version, judge_id, calibration_event_id,"
        " position_swap_agreement, admissibility_state, written_at"
        ") VALUES (?, ?, ?, 'verbosity', 'full_vs_ablated',"
        " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            verdict_id,
            run_id,
            clause_id,
            sample_a_id,
            sample_b_id,
            observation,
            oracle_tier,
            metric_id,
            metric_version,
            judge_id,
            calib_id,
            pos_swap,
            admissibility_state,
            _TS,
        ),
    )


def _seed_standard(conn: sqlite3.Connection) -> None:
    """Seed the standard happy-path: skill, clause, metric, completed run, samples, verdict."""
    _insert_skill(conn)
    _insert_clause(conn)
    _insert_metric(conn)
    _insert_run(conn, completed=True)
    _insert_sample(conn, "samp1", condition="full", output_text="full output")
    _insert_sample(conn, "samp2", condition="ablated", output_text="ablated output (failing)")
    _insert_verdict(conn, observation=0.0)  # FAILING — admissible Tier-1


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestFreezeVerdictHappyPath:
    def test_returns_frozen_case_id_string(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        assert isinstance(fid, str)
        assert len(fid) > 0

    def test_row_inserted_in_frozen_cases(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT * FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row is not None

    def test_provenance_auto_fill_metric_id(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT metric_id FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == "m1"

    def test_provenance_auto_fill_metric_version(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT metric_version FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == "1.0"

    def test_provenance_auto_fill_implementation_hash(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT implementation_hash FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == _SHA

    def test_failing_input_text_from_ablated_sample(self, evidence_db: sqlite3.Connection) -> None:
        """failing_input_text is the output_text of the ablated condition sample."""
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT failing_input_text FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        # The ablated sample's output_text is "ablated output (failing)"
        assert row[0] == "ablated output (failing)"

    def test_verdict_id_stored(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT verdict_id FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == "vrd1"

    def test_run_id_stored(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT run_id FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == "run1"

    def test_axis_stored(self, evidence_db: sqlite3.Connection) -> None:
        _seed_standard(evidence_db)
        fid = freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        row = evidence_db.execute(
            "SELECT axis FROM frozen_cases WHERE frozen_case_id = ?", (fid,)
        ).fetchone()
        assert row[0] == "verbosity"

    def test_tie_observation_allowed(self, evidence_db: sqlite3.Connection) -> None:
        """observation=0.5 (tie) is also on the FAILING side — allowed."""
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric(evidence_db)
        _insert_run(evidence_db, completed=True)
        _insert_sample(evidence_db, "samp1", condition="full")
        _insert_sample(evidence_db, "samp2", condition="ablated", output_text="tie output")
        _insert_verdict(evidence_db, observation=0.5, verdict_id="vrd-tie")
        fid = freeze_verdict(evidence_db, "vrd-tie", oracle_source="mechanical")
        assert isinstance(fid, str)


# ---------------------------------------------------------------------------
# Tests: eligibility validation
# ---------------------------------------------------------------------------


class TestFreezeVerdictEligibility:
    def test_winning_verdict_rejected(self, evidence_db: sqlite3.Connection) -> None:
        """observation=1.0 is NOT on the failing side."""
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric(evidence_db)
        _insert_run(evidence_db, completed=True)
        _insert_sample(evidence_db, "samp1", condition="full")
        _insert_sample(evidence_db, "samp2", condition="ablated")
        _insert_verdict(evidence_db, observation=1.0, verdict_id="vrd-win")
        with pytest.raises(ValueError, match="observation"):
            freeze_verdict(evidence_db, "vrd-win", oracle_source="mechanical")

    def test_inadmissible_verdict_rejected(self, evidence_db: sqlite3.Connection) -> None:
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric(evidence_db)
        _insert_run(evidence_db, completed=True)
        _insert_sample(evidence_db, "samp1", condition="full")
        _insert_sample(evidence_db, "samp2", condition="ablated")
        _insert_verdict(
            evidence_db, verdict_id="vrd-inadm", observation=0.0, admissibility_state="inadmissible"
        )
        with pytest.raises(ValueError, match="admissib"):
            freeze_verdict(evidence_db, "vrd-inadm", oracle_source="mechanical")

    def test_nonexistent_verdict_raises(self, evidence_db: sqlite3.Connection) -> None:
        with pytest.raises(ValueError, match="verdict_id"):
            freeze_verdict(evidence_db, "nonexistent-verdict", oracle_source="mechanical")

    def test_non_mechanical_oracle_source_rejected(self, evidence_db: sqlite3.Connection) -> None:
        """v0.1 only allows oracle_source='mechanical'."""
        _seed_standard(evidence_db)
        with pytest.raises(ValueError, match="oracle_source"):
            freeze_verdict(evidence_db, "vrd1", oracle_source="human")

    def test_incomplete_run_parent_rejected(self, evidence_db: sqlite3.Connection) -> None:
        """Parent run has completed_at IS NULL — both Python validation and DB trigger block it."""
        _insert_skill(evidence_db)
        _insert_clause(evidence_db)
        _insert_metric(evidence_db)
        _insert_run(evidence_db, completed=False)
        _insert_sample(evidence_db, "samp1", condition="full")
        _insert_sample(evidence_db, "samp2", condition="ablated")
        _insert_verdict(evidence_db, observation=0.0)
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")


# ---------------------------------------------------------------------------
# Tests: idempotency (duplicate freeze raises IntegrityError)
# ---------------------------------------------------------------------------


class TestFreezeVerdictIdempotency:
    def test_duplicate_freeze_raises_integrity_error(self, evidence_db: sqlite3.Connection) -> None:
        """Second freeze of same (clause_id, axis, failing_input_sha256) raises IntegrityError."""
        _seed_standard(evidence_db)
        freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
        # Attempt second freeze of same verdict — same (clause, axis, input sha256)
        with pytest.raises(sqlite3.IntegrityError):
            freeze_verdict(evidence_db, "vrd1", oracle_source="mechanical")
