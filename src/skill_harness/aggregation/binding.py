"""Compile one pre-spend measurement identity binding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Final

from skill_harness.oc import FrontierRow, Gate2Design
from skill_harness.semantics import RegisteredScope
from skill_harness.subject import HarnessPin
from skill_harness.task_frontier import FrozenHashes, TaskFamilyManifest

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
