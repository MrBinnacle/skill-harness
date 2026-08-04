"""#90 tracer bullet — a task family flows through the frontier firewall, thinly.

Every assertion here crosses the ONE `task_frontier` seam (manifest in,
observation in, read back out). Storage internals are never touched: the
append-only trigger behaviour of the phase-partitioned tables is proven
separately in ``tests/storage/test_task_frontier_store.py``, which is a
storage-layer test by nature (it must issue raw UPDATE/DELETE to prove the
triggers abort).

The property under test is the write-time phase firewall:

  * ``load_manifest`` freezes the phase→semantic-lineage partition;
  * ``admit`` reads a lineage's phase OUT of that frozen partition and stamps
    it on the record AT WRITE TIME;
  * reads return the stamp, never a recomputation against whatever manifest
    the reader happens to be holding.

The snapshot test is the load-bearing one: it re-reads a record while holding a
manifest that reassigns the very lineage to a different phase, and asserts the
record does not move. A read-time ``WHERE phase = 'matched'`` filter would fail
that test — which is exactly why spec #89 rejected that seam placement.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from skill_harness.task_frontier import (
    Arm,
    Observation,
    Phase,
    admit,
    audit_observation,
    load_manifest,
    matched_evidence,
)

# ---------------------------------------------------------------------------
# Fixtures — a minimal, hand-checkable family: one lineage per phase.
# ---------------------------------------------------------------------------

CAL_LINEAGE = "lineage-cal-a"
CON_LINEAGE = "lineage-con-a"
MAT_LINEAGE = "lineage-mat-a"

GENERATOR_FP = "gen-sha-0001"
ORACLE_FP = "ora-sha-0001"


def _manifest_data(
    *,
    calibration: list[str] | None = None,
    confirmation: list[str] | None = None,
    matched: list[str] | None = None,
    version: str = "1",
) -> dict[str, Any]:
    """A well-formed minimal manifest, as the raw mapping ``load_manifest`` takes."""
    return {
        "task_family_id": "fts5-notes-search",
        "task_family_version": version,
        "frozen_hashes": {
            "generator": GENERATOR_FP,
            "fixture": "fix-sha-0001",
            "oracle": ORACLE_FP,
            "harness": "har-sha-0001",
            "code": "cod-sha-0001",
        },
        "phase_partition": {
            "calibration": [CAL_LINEAGE] if calibration is None else calibration,
            "confirmation": [CON_LINEAGE] if confirmation is None else confirmation,
            "matched": [MAT_LINEAGE] if matched is None else matched,
        },
        "confirmation_attempt_budget": 2,
    }


def _observation(
    observation_id: str,
    lineage: str,
    *,
    arm: Arm = Arm.NULL,
    passed: bool = True,
    generator_fingerprint: str = GENERATOR_FP,
    oracle_fingerprint: str = ORACLE_FP,
) -> Observation:
    return Observation(
        observation_id=observation_id,
        semantic_lineage_id=lineage,
        instance_id=f"inst-{observation_id}",
        arm=arm,
        passed=passed,
        generator_fingerprint=generator_fingerprint,
        oracle_fingerprint=oracle_fingerprint,
        observed_at="2026-08-04T12:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# AC1 — a well-formed minimal manifest loads, validates and round-trips frozen.
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    def test_minimal_manifest_round_trips(self) -> None:
        manifest = load_manifest(_manifest_data())

        assert manifest.task_family_id == "fts5-notes-search"
        assert manifest.task_family_version == "1"
        assert manifest.confirmation_attempt_budget == 2
        assert manifest.frozen_hashes.generator == GENERATOR_FP
        assert manifest.frozen_hashes.oracle == ORACLE_FP
        assert manifest.phase_of(CAL_LINEAGE) is Phase.CALIBRATION
        assert manifest.phase_of(CON_LINEAGE) is Phase.CONFIRMATION
        assert manifest.phase_of(MAT_LINEAGE) is Phase.MATCHED

    def test_manifest_is_frozen(self) -> None:
        """A manifest that could be edited after loading is not a freeze."""
        manifest = load_manifest(_manifest_data())
        with pytest.raises((AttributeError, TypeError)):
            manifest.task_family_id = "something-else"  # type: ignore[misc]

    def test_lineage_absent_from_the_partition_has_no_phase(self) -> None:
        manifest = load_manifest(_manifest_data())
        assert manifest.phase_of("lineage-never-declared") is None


class TestTheGuardsBite:
    """Prove-the-rules-bite (#89 Testing Decisions): pass → induce → refuse → pass.

    Only the guards #90 actually carries are here. #92's remaining guard set
    (unfrozen hash, semantic surrogacy, unassigned lineage, off-manifest
    admission persistence) is NOT built and is not asserted absent-of-purpose.
    """

    def test_a_lineage_claimed_by_two_phases_is_refused(self) -> None:
        """Last-writer-wins on the partition would breach the firewall silently."""
        load_manifest(_manifest_data())  # passes

        with pytest.raises(ValueError, match="claimed by both"):
            load_manifest(_manifest_data(calibration=[CAL_LINEAGE, MAT_LINEAGE]))

        load_manifest(_manifest_data())  # and passes again

    def test_the_refusal_names_both_phases_and_the_lineage(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            load_manifest(_manifest_data(confirmation=[CON_LINEAGE, CAL_LINEAGE]))
        message = str(excinfo.value)
        assert CAL_LINEAGE in message
        assert "'calibration'" in message
        assert "'confirmation'" in message

    def test_an_unrecognised_manifest_key_is_refused_not_dropped(self) -> None:
        """A dropped `hard_budget` would read as registered while nothing read it.

        #90 carries a SUBSET of spec #89's manifest shape; the rest lands with
        #92. Refusing is what keeps that gap visible to an operator.
        """
        data = _manifest_data()
        data["hard_budget"] = 25.0
        with pytest.raises(ValueError, match="unrecognised key"):
            load_manifest(data)

    def test_an_unrecognised_frozen_hash_key_is_refused(self) -> None:
        data = _manifest_data()
        data["frozen_hashes"]["prompt"] = "prm-sha-0001"
        with pytest.raises(ValueError, match="unrecognised key"):
            load_manifest(data)

    def test_an_unrecognised_phase_name_is_refused(self) -> None:
        data = _manifest_data()
        data["phase_partition"]["exploration"] = ["lineage-exp-a"]
        with pytest.raises(ValueError, match="unrecognised key"):
            load_manifest(data)

    @pytest.mark.parametrize(
        "missing",
        [
            "task_family_id",
            "task_family_version",
            "frozen_hashes",
            "phase_partition",
            "confirmation_attempt_budget",
        ],
    )
    def test_a_missing_required_key_is_refused(self, missing: str) -> None:
        data = _manifest_data()
        del data[missing]
        with pytest.raises(ValueError, match=f"missing required key '{missing}'"):
            load_manifest(data)

    def test_a_missing_freeze_hash_is_refused(self) -> None:
        """The freeze is the anti-retrofit guarantee — a partial freeze is none."""
        data = _manifest_data()
        del data["frozen_hashes"]["oracle"]
        with pytest.raises(ValueError, match="missing required key 'oracle'"):
            load_manifest(data)


# ---------------------------------------------------------------------------
# AC2 — admit() returns the phase taken from the frozen lineage partition.
# ---------------------------------------------------------------------------


class TestAdmitReturnsPhase:
    @pytest.mark.parametrize(
        ("lineage", "expected"),
        [
            (CAL_LINEAGE, Phase.CALIBRATION),
            (CON_LINEAGE, Phase.CONFIRMATION),
            (MAT_LINEAGE, Phase.MATCHED),
        ],
    )
    def test_admit_returns_the_manifest_phase(
        self, evidence_db: sqlite3.Connection, lineage: str, expected: Phase
    ) -> None:
        manifest = load_manifest(_manifest_data())
        admission = admit(evidence_db, manifest, _observation("obs-1", lineage))

        assert admission.admissible is True
        assert admission.phase is expected
        assert admission.reason is None

    def test_unknown_lineage_is_inadmissible_with_a_cited_reason(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """Off-manifest evidence is refused with a reason, never silently dropped.

        #90 scope: the refusal is returned and nothing is written. PERSISTING
        inadmissible off-manifest observations (user story 14) is #92's scope —
        tracked, not silently skipped.
        """
        manifest = load_manifest(_manifest_data())
        observation = _observation("obs-off", "lineage-never-declared")

        admission = admit(evidence_db, manifest, observation)

        assert admission.admissible is False
        assert admission.phase is None
        assert admission.reason is not None
        assert "lineage-never-declared" in admission.reason
        assert audit_observation(evidence_db, "obs-off") is None

    def test_an_id_already_stored_in_another_phase_is_refused(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """One id, one observation — across the whole partition, not per table.

        Each partition has its own PRIMARY KEY and none of them can see the
        others, so a repartitioned manifest could otherwise file the same id
        under two phases and leave `audit_observation` answering with whichever
        table it reached first. A refused write beats an ambiguous audit read.
        """
        original = load_manifest(_manifest_data())
        admit(evidence_db, original, _observation("obs-dup", MAT_LINEAGE))

        repartitioned = load_manifest(
            _manifest_data(calibration=[MAT_LINEAGE], matched=[CAL_LINEAGE])
        )
        with pytest.raises(ValueError, match="already stored in the 'matched' partition"):
            admit(evidence_db, repartitioned, _observation("obs-dup", MAT_LINEAGE))

        stored = audit_observation(evidence_db, "obs-dup")
        assert stored is not None
        assert stored.phase is Phase.MATCHED

    def test_the_same_id_twice_in_one_phase_is_refused_the_same_way(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """The within-table PRIMARY KEY collision surfaces as the same error
        type as the cross-partition one — one uniform failure for one bug."""
        manifest = load_manifest(_manifest_data())
        admit(evidence_db, manifest, _observation("obs-twice", CAL_LINEAGE))
        with pytest.raises(ValueError, match="already stored in the 'calibration' partition"):
            admit(evidence_db, manifest, _observation("obs-twice", CAL_LINEAGE))


# ---------------------------------------------------------------------------
# AC3 / AC4 — the record is written with phase + lineage stamped at write, and
# reads back under the phase it was ADMITTED to.
# ---------------------------------------------------------------------------


class TestWriteTimeStampAndReadBack:
    @pytest.mark.parametrize(
        ("lineage", "expected"),
        [
            (CAL_LINEAGE, Phase.CALIBRATION),
            (CON_LINEAGE, Phase.CONFIRMATION),
            (MAT_LINEAGE, Phase.MATCHED),
        ],
    )
    def test_admitted_record_reads_back_under_its_phase(
        self, evidence_db: sqlite3.Connection, lineage: str, expected: Phase
    ) -> None:
        manifest = load_manifest(_manifest_data())
        admit(evidence_db, manifest, _observation("obs-rt", lineage))

        stored = audit_observation(evidence_db, "obs-rt")

        assert stored is not None
        assert stored.phase is expected
        assert stored.semantic_lineage_id == lineage
        assert stored.observation_id == "obs-rt"
        assert stored.task_family_id == "fts5-notes-search"
        assert stored.task_family_version == "1"
        assert stored.instance_id == "inst-obs-rt"
        assert stored.arm is Arm.NULL
        assert stored.passed is True
        assert stored.observed_at == "2026-08-04T12:00:00+00:00"
        assert stored.ingested_at  # stamped by the write path, not the caller

    def test_the_phase_stamp_is_a_snapshot_not_recomputed_at_read(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """The record does not move when a LATER manifest repartitions its lineage.

        This is the test a read-time ``WHERE phase = ?`` filter cannot pass, and
        the reason #89 rejected that seam placement.
        """
        original = load_manifest(_manifest_data())
        admit(evidence_db, original, _observation("obs-snap", MAT_LINEAGE))

        # A repartitioned manifest at the SAME family id + version that now
        # calls the very same lineage a calibration lineage.
        repartitioned = load_manifest(
            _manifest_data(calibration=[MAT_LINEAGE], matched=[CAL_LINEAGE])
        )
        assert repartitioned.phase_of(MAT_LINEAGE) is Phase.CALIBRATION

        # The audit read takes NO manifest — the phase can only come from the
        # stamp written at admission time.
        stored = audit_observation(evidence_db, "obs-snap")
        assert stored is not None
        assert stored.phase is Phase.MATCHED

        # And the estimator feed still sees it as matched evidence, because the
        # partition it landed in is physical, not a query predicate.
        ids = [record.observation_id for record in matched_evidence(evidence_db, repartitioned)]
        assert ids == ["obs-snap"]


# ---------------------------------------------------------------------------
# The estimator feed sees matched-phase evidence and nothing else.
# ---------------------------------------------------------------------------


class TestMatchedEvidenceIsPhaseIsolated:
    def test_matched_evidence_returns_only_matched_phase_records(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        manifest = load_manifest(_manifest_data())
        admit(evidence_db, manifest, _observation("obs-cal", CAL_LINEAGE))
        admit(evidence_db, manifest, _observation("obs-con", CON_LINEAGE))
        admit(evidence_db, manifest, _observation("obs-mat", MAT_LINEAGE, arm=Arm.FULL))

        records = matched_evidence(evidence_db, manifest)

        assert [record.observation_id for record in records] == ["obs-mat"]
        assert records[0].phase is Phase.MATCHED
        assert records[0].arm is Arm.FULL

    def test_matched_evidence_is_scoped_to_the_family_version(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        """A different task-family VERSION is a different measurement."""
        v1 = load_manifest(_manifest_data(version="1"))
        v2 = load_manifest(_manifest_data(version="2"))
        admit(evidence_db, v1, _observation("obs-v1", MAT_LINEAGE))
        admit(evidence_db, v2, _observation("obs-v2", MAT_LINEAGE))

        assert [r.observation_id for r in matched_evidence(evidence_db, v1)] == ["obs-v1"]
        assert [r.observation_id for r in matched_evidence(evidence_db, v2)] == ["obs-v2"]

    def test_matched_evidence_ordering_is_deterministic(
        self, evidence_db: sqlite3.Connection
    ) -> None:
        manifest = load_manifest(_manifest_data(matched=[MAT_LINEAGE, "lineage-mat-b"]))
        for observation_id, lineage in [
            ("obs-c", "lineage-mat-b"),
            ("obs-a", MAT_LINEAGE),
            ("obs-b", MAT_LINEAGE),
        ]:
            admit(evidence_db, manifest, _observation(observation_id, lineage))

        assert [r.observation_id for r in matched_evidence(evidence_db, manifest)] == [
            "obs-a",
            "obs-b",
            "obs-c",
        ]


# ---------------------------------------------------------------------------
# The seam is the whole public surface (spec #89: "deep behind one interface").
# ---------------------------------------------------------------------------


def test_the_interface_exposes_no_bulk_accessor_for_walled_off_phases() -> None:
    """No public call hands calibration/confirmation OBSERVATIONS to a caller.

    The rung is exposed as a decision by a later ticket; the raw pre-matched
    observations never are. This test pins the public surface so a future
    convenience accessor cannot quietly reopen the leak path.
    """
    import skill_harness.task_frontier as tf

    public = set(tf.__all__)
    assert "calibration_observations" not in public
    assert "confirmation_observations" not in public
    assert "observations_for_phase" not in public
    assert public == {
        "Admission",
        "Arm",
        "FrozenHashes",
        "Observation",
        "Phase",
        "StoredObservation",
        "TaskFamilyManifest",
        "admit",
        "audit_observation",
        "load_manifest",
        "matched_evidence",
    }


def test_the_manifest_cannot_enumerate_a_phases_lineages() -> None:
    """`audit_observation` reads by id — so the ids must not be obtainable here.

    A `lineages_in(Phase.CALIBRATION)` convenience would compose with the by-id
    audit read into a way to walk walled-off evidence. The manifest answers
    "what phase is THIS lineage in", never "which lineages are in this phase".
    """
    manifest = load_manifest(_manifest_data())
    enumerators = [
        name
        for name in dir(manifest)
        if not name.startswith("__") and name not in {"phase_of", "_phase_by_lineage"}
    ]
    assert enumerators == [
        "confirmation_attempt_budget",
        "frozen_hashes",
        "task_family_id",
        "task_family_version",
    ], f"unexpected public surface on TaskFamilyManifest: {enumerators}"
