"""Compile and verify one pre-spend measurement identity binding.

The #47 gate checks a declared invocation against the RAT ledger before spend.
This module's verifier checks stored evidence against a compiled binding after
collection. The direction and evidence differ, so the two checks do not
duplicate one another.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Final, Literal

from skill_harness.oc import FrontierRow, Gate2Design
from skill_harness.semantics import RegisteredScope
from skill_harness.subject import HarnessPin
from skill_harness.task_frontier import FrozenHashes, Phase, StoredObservation, TaskFamilyManifest

BINDING_ALGO_VERSION: Final[str] = "1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class BindingRecord:
    """Frozen, hash-addressed identity fixed before measurement spend."""

    binding_algo_version: str
    registered_scope: RegisteredScope
    task_family_id: str
    task_family_version: str
    frozen_hashes: FrozenHashes
    gate2_design: Gate2Design
    frontier_row_hash: str
    budget_cap_cents: int
    harness_pin: HarnessPin
    harness_pin_fingerprint: str
    canonical_bytes: bytes
    digest: str


class DivergenceReason(StrEnum):
    """One evidence-to-binding comparison that did not establish identity."""

    TASK_FAMILY_MISMATCH = "task-family-mismatch"
    TASK_FAMILY_VERSION_MISMATCH = "task-family-version-mismatch"
    ORACLE_FINGERPRINT_DRIFT = "oracle-fingerprint-drift"
    GENERATOR_FINGERPRINT_DRIFT = "generator-fingerprint-drift"
    PHASE_VIOLATION = "phase-violation"
    INADMISSIBLE_EVIDENCE = "inadmissible-evidence"
    UNVERIFIABLE_AXIS = "unverifiable-axis"


class UnverifiableAxis(StrEnum):
    """A bound identity axis absent from stored observation rows."""

    ESTIMAND = "estimand"
    SKILL_ID = "skill-id"
    DESIGN_IDENTITY = "design-identity"
    DELIVERY_MECHANISM = "delivery-mechanism"
    ADMISSIBILITY_POLICY = "admissibility-policy"


class BindingVerificationRefusalReason(StrEnum):
    """Reasons the verifier cannot begin evidence comparisons."""

    MALFORMED_BINDING = "malformed-binding"
    EMPTY_EVIDENCE = "empty-evidence"


@dataclass(frozen=True)
class DivergenceEntry:
    """One failed or unavailable comparison in the verification ledger."""

    reason: DivergenceReason
    observation_ids: tuple[str, ...]
    axis: UnverifiableAxis | None = None
    stored_reason: str | None = None


@dataclass(frozen=True)
class BindingVerificationLedger:
    """Every divergence found while checking one binding."""

    entries: tuple[DivergenceEntry, ...]


@dataclass(frozen=True)
class BindingVerificationMatch:
    """Stored evidence whose checkable identity matches the binding."""

    binding_digest: str
    task_family_id: str
    task_family_version: str
    observation_ids: tuple[str, ...]
    ledger: BindingVerificationLedger
    refusal: Literal[None] = None


@dataclass(frozen=True)
class BindingVerificationDivergence:
    """Stored evidence with one or more ledgered identity divergences."""

    binding_digest: str
    task_family_id: str
    task_family_version: str
    observation_ids: tuple[str, ...]
    ledger: BindingVerificationLedger
    refusal: Literal[None] = None


@dataclass(frozen=True)
class BindingVerificationRefusal:
    """Whole-verification refusal with the same identity field set."""

    binding_digest: str
    task_family_id: str
    task_family_version: str
    observation_ids: tuple[str, ...]
    ledger: BindingVerificationLedger
    refusal: BindingVerificationRefusalReason


type BindingVerificationResult = (
    BindingVerificationMatch | BindingVerificationDivergence | BindingVerificationRefusal
)


_UNVERIFIABLE_AXES: Final[tuple[UnverifiableAxis, ...]] = tuple(
    sorted(UnverifiableAxis, key=lambda axis: axis.value)
)


def compile_binding(
    *,
    scope: RegisteredScope,
    manifest: TaskFamilyManifest,
    design: Gate2Design,
    frontier_row: FrontierRow,
    budget_cap_cents: int,
    harness_pin: HarnessPin,
) -> BindingRecord:
    """Compose existing identity carriers into one canonical binding."""
    frontier_row_hash = _sha256(_canonical_bytes(asdict(frontier_row)))
    payload: dict[str, Any] = {
        "binding_algo_version": BINDING_ALGO_VERSION,
        "registered_scope": {
            "skill": scope.skill,
            "task_family": scope.task_family,
            "estimand": scope.estimand.value,
            "delivery_mechanism": scope.delivery_mechanism.value,
            "null_arm_semantic": scope.null_arm_semantic,
        },
        "task_family": {
            "id": manifest.task_family_id,
            "version": manifest.task_family_version,
            "frozen_hashes": asdict(manifest.frozen_hashes),
        },
        "gate2_design": asdict(design),
        "frontier_row_hash": frontier_row_hash,
        "budget_cap_cents": budget_cap_cents,
        "harness_pin_fingerprint": harness_pin.fingerprint(),
    }
    canonical = _canonical_bytes(payload)
    return BindingRecord(
        binding_algo_version=BINDING_ALGO_VERSION,
        registered_scope=scope,
        task_family_id=manifest.task_family_id,
        task_family_version=manifest.task_family_version,
        frozen_hashes=manifest.frozen_hashes,
        gate2_design=design,
        frontier_row_hash=frontier_row_hash,
        budget_cap_cents=budget_cap_cents,
        harness_pin=harness_pin,
        harness_pin_fingerprint=harness_pin.fingerprint(),
        canonical_bytes=canonical,
        digest=_sha256(canonical),
    )


def verify_binding(
    binding: BindingRecord, evidence: tuple[StoredObservation, ...]
) -> BindingVerificationResult:
    """Compare stored evidence with a binding without guessing absent identity."""
    if not isinstance(binding, BindingRecord):
        return BindingVerificationRefusal(
            binding_digest="",
            task_family_id="",
            task_family_version="",
            observation_ids=(),
            ledger=BindingVerificationLedger(entries=()),
            refusal=BindingVerificationRefusalReason.MALFORMED_BINDING,
        )
    if not evidence:
        return BindingVerificationRefusal(
            binding_digest=binding.digest,
            task_family_id=binding.task_family_id,
            task_family_version=binding.task_family_version,
            observation_ids=(),
            ledger=BindingVerificationLedger(entries=()),
            refusal=BindingVerificationRefusalReason.EMPTY_EVIDENCE,
        )
    records = tuple(sorted(evidence, key=lambda record: record.observation_id))
    entries: list[DivergenceEntry] = []
    for record in records:
        checks = (
            (
                record.task_family_id != binding.task_family_id,
                DivergenceReason.TASK_FAMILY_MISMATCH,
            ),
            (
                record.task_family_version != binding.task_family_version,
                DivergenceReason.TASK_FAMILY_VERSION_MISMATCH,
            ),
            (
                record.oracle_fingerprint != binding.frozen_hashes.oracle,
                DivergenceReason.ORACLE_FINGERPRINT_DRIFT,
            ),
            (
                record.generator_fingerprint != binding.frozen_hashes.generator,
                DivergenceReason.GENERATOR_FINGERPRINT_DRIFT,
            ),
            (record.phase is not Phase.MATCHED, DivergenceReason.PHASE_VIOLATION),
        )
        for diverged, reason in checks:
            if diverged:
                entries.append(
                    DivergenceEntry(reason=reason, observation_ids=(record.observation_id,))
                )
        if record.admissibility_state != "admissible":
            entries.append(
                DivergenceEntry(
                    reason=DivergenceReason.INADMISSIBLE_EVIDENCE,
                    observation_ids=(record.observation_id,),
                    stored_reason=record.inadmissibility_reason,
                )
            )

    entries.extend(
        DivergenceEntry(
            reason=DivergenceReason.UNVERIFIABLE_AXIS,
            observation_ids=(),
            axis=axis,
        )
        for axis in _UNVERIFIABLE_AXES
    )
    ledger = BindingVerificationLedger(
        entries=tuple(
            sorted(
                entries,
                key=lambda entry: (
                    not entry.observation_ids,
                    entry.observation_ids,
                    entry.reason.value,
                    "" if entry.axis is None else entry.axis.value,
                ),
            )
        )
    )
    observation_ids = tuple(record.observation_id for record in records)
    evidence_diverged = any(
        entry.reason is not DivergenceReason.UNVERIFIABLE_AXIS for entry in ledger.entries
    )
    if evidence_diverged:
        return BindingVerificationDivergence(
            binding_digest=binding.digest,
            task_family_id=binding.task_family_id,
            task_family_version=binding.task_family_version,
            observation_ids=observation_ids,
            ledger=ledger,
        )
    return BindingVerificationMatch(
        binding_digest=binding.digest,
        task_family_id=binding.task_family_id,
        task_family_version=binding.task_family_version,
        observation_ids=observation_ids,
        ledger=ledger,
    )
