"""A28 — Verify that the evidence_db_for_property_tests fixture isolates Hypothesis examples.

Usage pattern: property tests call conn.execute("SAVEPOINT hyp_example") at the
start of the @given body and conn.execute("ROLLBACK TO hyp_example") + RELEASE at
the end.  The fixture provides a fresh connection already past the initial
SAVEPOINT acquired in conftest; tests use the pattern explicitly per-example.

Test A: SAVEPOINT / INSERT / ROLLBACK leaves the table empty (proves rollback works).
Test B: SAVEPOINT acquired inside a property body — after ROLLBACK the table is
        clean for the next example (proves the fixture + SAVEPOINT/ROLLBACK pattern
        isolates Hypothesis examples from each other).
"""

from __future__ import annotations

import sqlite3

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_SHA = "a" * 64
_TS = "2026-06-05T00:00:00.000Z"


def _insert_skill(conn: sqlite3.Connection, skill_id: str) -> None:
    conn.execute(
        "INSERT INTO skills (skill_id, name, source_path, source_sha256, imported_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (skill_id, "TestSkill", "/tmp/x.md", _SHA, _TS),
    )


class TestSavepointIsolation:
    def test_a_savepoint_rollback_undoes_insert(
        self, evidence_db_for_property_tests: sqlite3.Connection
    ) -> None:
        """SAVEPOINT / INSERT / ROLLBACK TO / RELEASE leaves the table empty.

        This is the mechanical correctness proof: SAVEPOINT semantics work on
        the evidence connection returned by the fixture.
        """
        conn = evidence_db_for_property_tests

        # Verify table is empty at the start
        assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0

        # Acquire a nested savepoint, insert, then roll back
        conn.execute("SAVEPOINT inner_test")
        _insert_skill(conn, "skill-will-rollback")
        assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 1
        conn.execute("ROLLBACK TO inner_test")
        conn.execute("RELEASE inner_test")

        # After ROLLBACK TO, the insert is gone
        assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 0

    def test_b_property_examples_are_isolated(
        self, evidence_db_for_property_tests: sqlite3.Connection
    ) -> None:
        """Each @given example that uses the SAVEPOINT pattern sees an empty table.

        Pattern used by property tests:
            conn.execute("SAVEPOINT hyp_example")
            try:
                <test body — inserts rows>
            finally:
                conn.execute("ROLLBACK TO hyp_example")
                conn.execute("RELEASE hyp_example")
        """
        conn = evidence_db_for_property_tests
        example_count = [0]

        @given(skill_suffix=st.integers(min_value=1, max_value=9999))
        @settings(
            max_examples=10,
            deadline=None,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        )
        def _property(skill_suffix: int) -> None:
            example_count[0] += 1
            conn.execute("SAVEPOINT hyp_example")
            try:
                # Table should be empty at the start of each example
                count_before = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
                assert count_before == 0, (
                    f"example {example_count[0]}: skills table has {count_before} rows "
                    "at example start — prior ROLLBACK TO failed"
                )
                # Insert a row
                _insert_skill(conn, f"skill-{skill_suffix}")
                assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 1
            finally:
                conn.execute("ROLLBACK TO hyp_example")
                conn.execute("RELEASE hyp_example")

        _property()
        # Confirm all 10 examples ran
        assert example_count[0] == 10

    def test_c_exception_mid_body_leaves_table_clean(
        self, evidence_db_for_property_tests: sqlite3.Connection
    ) -> None:
        """When the test body raises, the finally-ROLLBACK undoes partial inserts."""
        conn = evidence_db_for_property_tests

        conn.execute("SAVEPOINT hyp_example")
        try:
            _insert_skill(conn, "skill-will-fail")
            assert conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == 1
            raise RuntimeError("simulated mid-body failure")
        except RuntimeError:
            pass
        finally:
            conn.execute("ROLLBACK TO hyp_example")
            conn.execute("RELEASE hyp_example")

        # After ROLLBACK TO, the partial insert is gone
        count = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        assert count == 0, f"finally-ROLLBACK did not clean up: {count} row(s) remain"
