"""The write-time phase-admission firewall (spec #89, ticket #90).

`admit` is the ONLY way an observation enters the frontier. It reads the
lineage's phase out of the frozen manifest, stamps it on the record, and writes
that record to the matching physical partition — in one step, so there is no
"admitted but unwritten" or "written but unadmitted" state a caller could reach.

Reads come back through `audit_observation` (by id, phase from the stamp, no
manifest involved) and `matched_evidence` (the estimator feed, matched
partition only). There is deliberately no third reader.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from skill_harness.storage.models import TaskFrontierObservationWrite
from skill_harness.storage.repositories.evidence.task_frontier import (
    get_task_frontier_observation_by_id,
    insert_task_frontier_observation,
    select_matched_observations,
)
from skill_harness.storage.transaction import writer_transaction
from skill_harness.task_frontier.manifest import Arm, Phase, TaskFamilyManifest


def _utcnow_iso() -> str:
    """Millisecond-truncated UTC, `Z`-suffixed — the ingest timestamp format.

    Deliberately a local copy of `subject.ingest._utcnow_iso` rather than an
    import: `subject` is the optional `[inspect]` extra's layer, and the
    frontier must not acquire a dependency on it to write a timestamp. The
    FORMAT is copied on purpose so `ingested_at` reads the same across every
    evidence table.
    """
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Observation:
    """One arm's result on one task instance, before admission.

    Carries the fingerprints of the generator and oracle that produced it so a
    later ticket can refuse evidence that drifted away from the manifest freeze
    (#92); #90 stores them without comparing.
    """

    observation_id: str
    semantic_lineage_id: str
    instance_id: str
    arm: Arm
    passed: bool
    generator_fingerprint: str
    oracle_fingerprint: str
    observed_at: str


@dataclass(frozen=True)
class Admission:
    """The firewall's verdict on one observation.

    `admissible=False` carries a cited `reason` and NO phase — the record was
    not filed anywhere, because there is no partition for evidence the manifest
    does not recognise.
    """

    admissible: bool
    phase: Phase | None
    reason: str | None


@dataclass(frozen=True)
class StoredObservation:
    """An observation as it came back out of a partition.

    `phase` is the write-time stamp, not a recomputation: nothing on this path
    consults a manifest, so a manifest that repartitions the lineage after the
    fact cannot move an already-stored record.
    """

    observation_id: str
    task_family_id: str
    task_family_version: str
    semantic_lineage_id: str
    phase: Phase
    instance_id: str
    arm: Arm
    passed: bool
    generator_fingerprint: str
    oracle_fingerprint: str
    admissibility_state: str
    inadmissibility_reason: str | None
    observed_at: str
    ingested_at: str


def _row_to_stored(row: dict[str, object]) -> StoredObservation:
    return StoredObservation(
        observation_id=str(row["observation_id"]),
        task_family_id=str(row["task_family_id"]),
        task_family_version=str(row["task_family_version"]),
        semantic_lineage_id=str(row["semantic_lineage_id"]),
        phase=Phase(str(row["phase"])),
        instance_id=str(row["instance_id"]),
        arm=Arm(str(row["arm"])),
        passed=bool(row["passed"]),
        generator_fingerprint=str(row["generator_fingerprint"]),
        oracle_fingerprint=str(row["oracle_fingerprint"]),
        admissibility_state=str(row["admissibility_state"]),
        inadmissibility_reason=(
            None if row["inadmissibility_reason"] is None else str(row["inadmissibility_reason"])
        ),
        observed_at=str(row["observed_at"]),
        ingested_at=str(row["ingested_at"]),
    )


def admit(
    conn: sqlite3.Connection,
    manifest: TaskFamilyManifest,
    observation: Observation,
) -> Admission:
    """Admit one observation to its manifest-declared phase and store it there.

    :param conn: An evidence-DB connection from ``storage.migrations.open_evidence``.
    :param manifest: The frozen manifest that declares the phase partition.
    :param observation: The observation to admit.
    :returns: The `Admission` — the phase it was filed under, or a refusal with
        a cited reason.
    :raises ValueError: If this `observation_id` is already stored in ANY
        partition. Per-table PRIMARY KEYs cannot see across the partition, so
        without this check the same id could sit in two phases at once and
        `audit_observation` would silently answer with whichever it reached
        first — an ambiguous audit read is worse than a refused write.

    An off-manifest lineage is refused and NOT written. Persisting inadmissible
    off-manifest evidence with its reason (spec #89 user story 14) is #92's
    scope; until then the refusal is returned to the caller rather than
    swallowed, so nothing is silently dropped without someone seeing it.

    Note the two failure kinds are deliberately different types: an off-manifest
    lineage is an EVIDENCE judgment and comes back as an `Admission`; a
    duplicate id is a CALLER bug and raises.
    """
    phase = manifest.phase_of(observation.semantic_lineage_id)
    if phase is None:
        return Admission(
            admissible=False,
            phase=None,
            reason=(
                f"semantic lineage {observation.semantic_lineage_id!r} is absent from the "
                f"frozen phase partition of task family "
                f"{manifest.task_family_id}@{manifest.task_family_version} — off-manifest "
                "evidence cannot be assigned a phase"
            ),
        )

    write = TaskFrontierObservationWrite(
        observation_id=observation.observation_id,
        task_family_id=manifest.task_family_id,
        task_family_version=manifest.task_family_version,
        semantic_lineage_id=observation.semantic_lineage_id,
        phase=phase.value,
        instance_id=observation.instance_id,
        # Re-wrapped rather than `.value`d: the annotation says `Arm`, but an
        # untyped caller can still hand in a bare string, and this turns that
        # into a ValueError here instead of a mis-typed row later.
        arm=Arm(observation.arm).value,
        passed=1 if observation.passed else 0,
        generator_fingerprint=observation.generator_fingerprint,
        oracle_fingerprint=observation.oracle_fingerprint,
        admissibility_state="admissible",
        inadmissibility_reason=None,
        observed_at=observation.observed_at,
        ingested_at=_utcnow_iso(),
    )

    # The duplicate-id check and the insert must be one atomic unit: they span
    # three tables whose PRIMARY KEYs cannot see each other, so a plain
    # read-then-write would let two concurrent writers both pass the check.
    # BEGIN IMMEDIATE is the repo's writer-exclusion primitive (A26).
    with writer_transaction(conn):
        existing = get_task_frontier_observation_by_id(conn, observation.observation_id)
        if existing is not None:
            raise ValueError(
                f"observation_id {observation.observation_id!r} is already stored in the "
                f"{existing['phase']!r} partition — the frontier is append-only and an id "
                "must identify exactly one observation across all three phases"
            )
        insert_task_frontier_observation(conn, write)
    return Admission(admissible=True, phase=phase, reason=None)


def audit_observation(conn: sqlite3.Connection, observation_id: str) -> StoredObservation | None:
    """Read one stored observation back by id, or None if no partition holds it.

    An AUDIT surface, not an evidence accessor: it takes no manifest and no
    phase, answers one id at a time, and cannot enumerate a phase — so it
    reveals what was admitted without giving the effect path a way to pull
    calibration or confirmation evidence in bulk.
    """
    row = get_task_frontier_observation_by_id(conn, observation_id)
    return None if row is None else _row_to_stored(row)


def matched_evidence(
    conn: sqlite3.Connection, manifest: TaskFamilyManifest
) -> tuple[StoredObservation, ...]:
    """Return the admissible MATCHED-phase observations for this family version.

    The one feed the effect estimator gets. It reaches a single physical
    partition, so calibration and confirmation evidence is not filtered out
    here — it was never in scope to begin with.

    #90 returns the raw matched records; pairing them into the (x_f, x_n)
    discordant counts ``oc/gate2`` consumes is #91.
    """
    rows = select_matched_observations(conn, manifest.task_family_id, manifest.task_family_version)
    return tuple(_row_to_stored(row) for row in rows)
