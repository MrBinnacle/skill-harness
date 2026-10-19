"""Tests for migration 0401_stale_frozen_view.sql (A57).

Tests:
- current_metric_versions VIEW excludes unaudited rows
- current_metric_versions VIEW excludes rows where mechanical_validity_test_passed = 0
- current_metric_versions VIEW returns the most-recent audited+passing row per metric_id
- frozen_cases_with_currency labels correctly: 'current', 'stale', 'no_current_metric_version'
"""

from __future__ import annotations

import sqlite3

_TS1 = "2026-06-01T00:00:00.000Z"
_TS2 = "2026-06-02T00:00:00.000Z"
_TS3 = "2026-06-03T00:00:00.000Z"
_SHA = "a" * 64
_SHA2 = "b" * 64
_SHA3 = "c" * 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_metric_version(
    conn: sqlite3.Connection,
    metric_id: str,
    version: str,
    implementation_hash: str = _SHA,
    audited: int = 1,
    mechanical_validity_test_passed: int = 1,
    registered_at: str = _TS1,
) -> None:
    conn.execute(
        "INSERT INTO metric_versions"
        " (metric_id, version, implementation_hash, tier,"
        " audited, mechanical_validity_test_passed, registered_at)"
        " VALUES (?, ?, ?, 1, ?, ?, ?)",
        (
            metric_id,
            version,
            implementation_hash,
            audited,
            mechanical_validity_test_passed,
            registered_at,
        ),
    )


def _insert_skill(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at)"
        " VALUES ('sk1', 'S', '/p', ?, ?)",
        (_SHA, _TS1),
    )


def _insert_clause(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO clauses (clause_id, skill_id, clause_index, rendering_index,"
        " clause_text, axis, comparator, oracle_tier, vacuity_flag) VALUES"
        " ('cl1', 'sk1', 0, 0, 'text', 'verbosity', 'decrease', 1, 'none')"
    )


def _insert_run(conn: sqlite3.Connection, run_id: str = "run1") -> None:
    conn.execute(
        "INSERT INTO runs (run_id, skill_id, run_kind, config_json, started_at, completed_at)"
        " VALUES (?, 'sk1', 'ablation', '{}', ?, ?)",
        (run_id, _TS1, _TS1),
    )


def _insert_sample(conn: sqlite3.Connection, sample_id: str, run_id: str = "run1") -> None:
    conn.execute(
        "INSERT INTO samples (sample_id, run_id, clause_id, condition,"
        " subject_model, output_text, output_sha256, sampled_at)"
        " VALUES (?, ?, 'cl1', 'full', 'model-x', 'output', ?, ?)",
        (sample_id, run_id, _SHA, _TS1),
    )


def _insert_frozen_case(
    conn: sqlite3.Connection,
    frozen_case_id: str,
    metric_id: str,
    metric_version: str,
    implementation_hash: str,
    verdict_id: str | None = None,
    run_id: str | None = None,
    axis: str = "verbosity",
    sha: str = _SHA,
) -> None:
    conn.execute(
        "INSERT INTO frozen_cases ("
        " frozen_case_id, clause_id, failing_input_text, failing_input_sha256,"
        " oracle_source, metric_id, metric_version, implementation_hash,"
        " verdict_id, run_id, axis"
        ") VALUES (?, 'cl1', 'bad', ?, 'mechanical', ?, ?, ?, ?, ?, ?)",
        (
            frozen_case_id,
            sha,
            metric_id,
            metric_version,
            implementation_hash,
            verdict_id,
            run_id,
            axis,
        ),
    )


# ---------------------------------------------------------------------------
# Tests: current_metric_versions VIEW
# ---------------------------------------------------------------------------


class TestCurrentMetricVersionsView:
    """The VIEW returns only audited + validity-passed rows, most-recent per metric_id."""

    def test_view_exists(self, evidence_db: sqlite3.Connection) -> None:
        cur = evidence_db.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='current_metric_versions'"
        )
        assert cur.fetchone() is not None, "current_metric_versions view not found"

    def test_view_returns_audited_passing_row(self, evidence_db: sqlite3.Connection) -> None:
        _insert_metric_version(
            evidence_db, "m1", "1.0", audited=1, mechanical_validity_test_passed=1
        )
        cur = evidence_db.execute(
            "SELECT metric_id, version FROM current_metric_versions WHERE metric_id = 'm1'"
        )
        row = cur.fetchone()
        assert row is not None, "expected row missing from current_metric_versions"
        assert row[0] == "m1"
        assert row[1] == "1.0"

    def test_view_excludes_unaudited(self, evidence_db: sqlite3.Connection) -> None:
        _insert_metric_version(
            evidence_db, "m2", "1.0", audited=0, mechanical_validity_test_passed=1
        )
        cur = evidence_db.execute("SELECT * FROM current_metric_versions WHERE metric_id = 'm2'")
        assert cur.fetchone() is None, "unaudited row must be excluded from current_metric_versions"

    def test_view_excludes_validity_failed(self, evidence_db: sqlite3.Connection) -> None:
        _insert_metric_version(
            evidence_db, "m3", "1.0", audited=1, mechanical_validity_test_passed=0
        )
        cur = evidence_db.execute("SELECT * FROM current_metric_versions WHERE metric_id = 'm3'")
        assert cur.fetchone() is None, "validity-failed row must be excluded"

    def test_view_returns_most_recent_when_multiple_audited(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """Older audited+passing row at TS1, newer audited+passing at TS2 — VIEW returns TS2."""
        _insert_metric_version(
            evidence_db, "m4", "1.0", implementation_hash=_SHA, registered_at=_TS1
        )
        _insert_metric_version(
            evidence_db, "m4", "2.0", implementation_hash=_SHA2, registered_at=_TS2
        )
        cur = evidence_db.execute(
            "SELECT version FROM current_metric_versions WHERE metric_id = 'm4'"
        )
        rows = cur.fetchall()
        assert len(rows) == 1, f"expected exactly 1 current row, got {len(rows)}"
        assert rows[0][0] == "2.0", f"expected version 2.0, got {rows[0][0]}"

    def test_view_prefers_older_if_newer_unaudited(self, evidence_db: sqlite3.Connection) -> None:
        """If the newer version is unaudited, the older audited version is 'current'."""
        _insert_metric_version(
            evidence_db,
            "m5",
            "1.0",
            implementation_hash=_SHA,
            audited=1,
            mechanical_validity_test_passed=1,
            registered_at=_TS1,
        )
        _insert_metric_version(
            evidence_db,
            "m5",
            "2.0",
            implementation_hash=_SHA2,
            audited=0,
            mechanical_validity_test_passed=1,
            registered_at=_TS2,
        )
        cur = evidence_db.execute(
            "SELECT version FROM current_metric_versions WHERE metric_id = 'm5'"
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "1.0", "older audited row should be current when newer is unaudited"

    def test_view_multiple_metrics_independent(self, evidence_db: sqlite3.Connection) -> None:
        """Each metric_id has its own 'current' row; they don't bleed across."""
        _insert_metric_version(evidence_db, "mx", "1.0", implementation_hash=_SHA)
        _insert_metric_version(evidence_db, "my", "3.0", implementation_hash=_SHA2)
        cur = evidence_db.execute(
            "SELECT metric_id FROM current_metric_versions ORDER BY metric_id"
        )
        metric_ids = [r[0] for r in cur.fetchall()]
        assert metric_ids == ["mx", "my"]


# ---------------------------------------------------------------------------
# Tests: frozen_cases_with_currency VIEW
# ---------------------------------------------------------------------------


class TestFrozenCasesWithCurrencyView:
    """frozen_cases_with_currency labels frozen cases correctly."""

    def test_view_exists(self, evidence_db: sqlite3.Connection) -> None:
        cur = evidence_db.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='frozen_cases_with_currency'"
        )
        assert cur.fetchone() is not None, "frozen_cases_with_currency view not found"

    def _seed_base(self, conn: sqlite3.Connection) -> None:
        _insert_skill(conn)
        _insert_clause(conn)
        _insert_run(conn)
        _insert_sample(conn, "samp1")

    def test_current_label(self, evidence_db: sqlite3.Connection) -> None:
        """A frozen case whose metric_version + implementation_hash matches current → 'current'."""
        self._seed_base(evidence_db)
        _insert_metric_version(
            evidence_db,
            "m1",
            "1.0",
            implementation_hash=_SHA,
            audited=1,
            mechanical_validity_test_passed=1,
        )
        _insert_frozen_case(
            evidence_db,
            "fc1",
            metric_id="m1",
            metric_version="1.0",
            implementation_hash=_SHA,
        )
        cur = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = 'fc1'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "current"

    def test_stale_label_version_mismatch(self, evidence_db: sqlite3.Connection) -> None:
        """Frozen at old metric_version while a newer version is current → 'stale'."""
        self._seed_base(evidence_db)
        _insert_metric_version(
            evidence_db,
            "m1",
            "1.0",
            implementation_hash=_SHA,
            registered_at=_TS1,
        )
        _insert_metric_version(
            evidence_db,
            "m1",
            "2.0",
            implementation_hash=_SHA2,
            registered_at=_TS2,
        )
        _insert_frozen_case(
            evidence_db,
            "fc2",
            metric_id="m1",
            metric_version="1.0",
            implementation_hash=_SHA,
            sha=_SHA2,
        )
        cur = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = 'fc2'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "stale"

    def test_stale_label_hash_mismatch(self, evidence_db: sqlite3.Connection) -> None:
        """Same version string but different implementation_hash → 'stale' (tamper-evidence)."""
        self._seed_base(evidence_db)
        _insert_metric_version(
            evidence_db,
            "m1",
            "1.0",
            implementation_hash=_SHA,
        )
        # frozen_case has same version but different hash
        _insert_frozen_case(
            evidence_db,
            "fc3",
            metric_id="m1",
            metric_version="1.0",
            implementation_hash=_SHA2,
            sha=_SHA3,
        )
        cur = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = 'fc3'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "stale"

    def test_no_current_metric_version_label(self, evidence_db: sqlite3.Connection) -> None:
        """No audited+valid current version for the metric_id → 'no_current_metric_version'."""
        self._seed_base(evidence_db)
        # metric_version exists but is unaudited
        _insert_metric_version(
            evidence_db,
            "m1",
            "1.0",
            implementation_hash=_SHA,
            audited=0,
            mechanical_validity_test_passed=1,
        )
        _insert_frozen_case(
            evidence_db,
            "fc4",
            metric_id="m1",
            metric_version="1.0",
            implementation_hash=_SHA,
        )
        cur = evidence_db.execute(
            "SELECT currency_state FROM frozen_cases_with_currency WHERE frozen_case_id = 'fc4'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "no_current_metric_version"

    def test_view_returns_all_frozen_case_columns(self, evidence_db: sqlite3.Connection) -> None:
        """The VIEW exposes f.* (all frozen_cases columns)."""
        self._seed_base(evidence_db)
        _insert_metric_version(evidence_db, "m1", "1.0", implementation_hash=_SHA)
        _insert_frozen_case(
            evidence_db,
            "fc5",
            metric_id="m1",
            metric_version="1.0",
            implementation_hash=_SHA,
        )
        cur = evidence_db.execute(
            "SELECT * FROM frozen_cases_with_currency WHERE frozen_case_id = 'fc5'"
        )
        row = cur.fetchone()
        assert row is not None
        col_names = [d[0] for d in cur.description]
        assert "frozen_case_id" in col_names
        assert "currency_state" in col_names
