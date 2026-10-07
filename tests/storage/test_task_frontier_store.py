"""Storage-layer proof for the task-frontier phase partition (migration 0700).

These are deliberately NOT seam tests. #90's acceptance criterion "the store is
append-only (UPDATE/DELETE abort, matching the repo's other evidence tables)"
is a property of the SQL triggers, and the only way to falsify it is to issue
the raw UPDATE/DELETE the triggers exist to abort — exactly as
``tests/test_migration_0300.py`` and ``tests/test_smoke.py`` do for the older
evidence tables. The behavioural, through-the-seam tests live in
``tests/task_frontier/test_tracer.py``.

The second property proven here is the PHYSICAL partition: three separate
tables, each with a CHECK that pins its own phase literal, so a row cannot be
filed under a phase it was not admitted to even by a direct writer.
"""

from __future__ import annotations

import sqlite3

import pytest

from skill_harness.storage.models import TaskFrontierObservationWrite
from skill_harness.storage.repositories.evidence.task_frontier import (
    PHASE_TABLES,
    insert_task_frontier_observation,
)


def _write(observation_id: str, phase: str, lineage: str = "lin-a") -> TaskFrontierObservationWrite:
    return TaskFrontierObservationWrite(
        observation_id=observation_id,
        task_family_id="fam-1",
        task_family_version="1",
        semantic_lineage_id=lineage,
        phase=phase,
        instance_id=f"inst-{observation_id}",
        arm="null",
        passed=1,
        generator_fingerprint="gen-1",
        oracle_fingerprint="ora-1",
        admissibility_state="admissible",
        inadmissibility_reason=None,
        observed_at="2026-08-04T12:00:00+00:00",
        ingested_at="2026-08-04T12:00:01+00:00",
    )


class TestPhasePartitionIsPhysical:
    def test_every_phase_has_its_own_table(self) -> None:
        assert PHASE_TABLES == {
            "calibration": "task_frontier_calibration_obs",
            "confirmation": "task_frontier_confirmation_obs",
            "matched": "task_frontier_matched_obs",
        }

    @pytest.mark.parametrize("phase", ["calibration", "confirmation", "matched"])
    def test_tables_exist_after_migration(
        self, evidence_db: sqlite3.Connection, phase: str
    ) -> None:
        table = PHASE_TABLES[phase]
        row = evidence_db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        assert row is not None, f"migration 0700 did not create {table}"

    @pytest.mark.parametrize("phase", ["calibration", "confirmation", "matched"])
    def test_each_table_refuses_a_foreign_phase_literal(
        self, evidence_db: sqlite3.Connection, phase: str
    ) -> None:
        """The CHECK pins the phase literal per table — a mis-filed row aborts.

        This is what makes the partition physical rather than a column
        convention: even a direct writer cannot park a 'calibration' row in the
        matched table and have it read back as matched evidence.
        """
        wrong_phase = "matched" if phase != "matched" else "calibration"
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            evidence_db.execute(
                f"""
                INSERT INTO {PHASE_TABLES[phase]} (
                    observation_id, task_family_id, task_family_version,
                    semantic_lineage_id, phase, instance_id, arm, passed,
                    generator_fingerprint, oracle_fingerprint,
                    admissibility_state, inadmissibility_reason,
                    observed_at, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "obs-x",
                    "fam-1",
                    "1",
                    "lin-a",
                    wrong_phase,
                    "inst-x",
                    "null",
                    1,
                    "gen-1",
                    "ora-1",
                    "admissible",
                    None,
                    "2026-08-04T12:00:00+00:00",
                    "2026-08-04T12:00:01+00:00",
                ),
            )


class TestAppendOnly:
    @pytest.mark.parametrize("phase", ["calibration", "confirmation", "matched"])
    def test_update_aborts(self, evidence_db: sqlite3.Connection, phase: str) -> None:
        table = PHASE_TABLES[phase]
        insert_task_frontier_observation(evidence_db, _write("obs-u", phase))
        with pytest.raises(sqlite3.IntegrityError, match=f"append_only_violation: {table}"):
            evidence_db.execute(f"UPDATE {table} SET passed = 0 WHERE observation_id = 'obs-u'")

    @pytest.mark.parametrize("phase", ["calibration", "confirmation", "matched"])
    def test_delete_aborts(self, evidence_db: sqlite3.Connection, phase: str) -> None:
        table = PHASE_TABLES[phase]
        insert_task_frontier_observation(evidence_db, _write("obs-d", phase))
        with pytest.raises(sqlite3.IntegrityError, match=f"append_only_violation: {table}"):
            evidence_db.execute(f"DELETE FROM {table} WHERE observation_id = 'obs-d'")

    @pytest.mark.parametrize("phase", ["calibration", "confirmation", "matched"])
    def test_repartitioning_an_existing_row_aborts(
        self, evidence_db: sqlite3.Connection, phase: str
    ) -> None:
        """The audit trail cannot be silently re-partitioned after the fact
        (user story 15) — an UPDATE to `phase` is an append-only violation
        before the CHECK ever gets a chance to fire."""
        table = PHASE_TABLES[phase]
        insert_task_frontier_observation(evidence_db, _write("obs-r", phase))
        with pytest.raises(sqlite3.IntegrityError, match=f"append_only_violation: {table}"):
            evidence_db.execute(
                f"UPDATE {table} SET phase = 'matched' WHERE observation_id = 'obs-r'"
            )


class TestWriteModelRefusesRatherThanCoerces:
    def test_unknown_phase_is_refused(self) -> None:
        with pytest.raises(ValueError, match="phase"):
            _write("obs-bad", "exploration")

    def test_unknown_arm_is_refused(self) -> None:
        with pytest.raises(ValueError, match="arm"):
            TaskFrontierObservationWrite(
                observation_id="obs-bad",
                task_family_id="fam-1",
                task_family_version="1",
                semantic_lineage_id="lin-a",
                phase="matched",
                instance_id="inst-1",
                arm="ablated",
                passed=1,
                generator_fingerprint="gen-1",
                oracle_fingerprint="ora-1",
                admissibility_state="admissible",
                inadmissibility_reason=None,
                observed_at="2026-08-04T12:00:00+00:00",
                ingested_at="2026-08-04T12:00:01+00:00",
            )
