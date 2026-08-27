"""Immutable, content-addressed contracts for deterministic evaluation.

The registry is the authority surface. Evaluators supply evidence and may not
expand the claims declared by a registered property.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSUPPORTED = "UNSUPPORTED"


class PropertyType(StrEnum):
    MECHANICALLY_DECIDABLE = "mechanically_decidable"
    RESIDUAL = "residual"


class Authority(StrEnum):
    AUTHORITATIVE = "authoritative"
    QUALIFIED = "qualified"
    PROHIBITED = "prohibited"


@dataclass(frozen=True)
class Ceiling:
    establishes: tuple[str, ...]
    does_not_establish: tuple[str, ...]

    def canonical(self) -> dict[str, list[str]]:
        return {
            "establishes": list(self.establishes),
            "does_not_establish": list(self.does_not_establish),
        }


@dataclass(frozen=True)
class Property:
    statement: str
    type: PropertyType
    deterministic_authority: Authority
    judgment_authority: Authority
    ceiling: Ceiling
    evaluators: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        payload = {
            "statement": self.statement,
            "type": self.type.value,
            "authority": {
                "deterministic": self.deterministic_authority.value,
                "judgment": self.judgment_authority.value,
            },
            "ceiling": self.ceiling.canonical(),
        }
        return _hash_json(payload)


@dataclass(frozen=True)
class EvaluatorSpec:
    """Immutable evaluator identity and declared contract."""

    version: str
    input_schema: str
    ceiling: Ceiling
    guarantees: tuple[str, ...] = (
        "pure",
        "deterministic",
        "golden-tested",
        "independently-runnable",
    )
    code_hash: str = ""
    dependency_hash: str = ""

    @property
    def id(self) -> str:
        payload = {
            "code": self.code_hash,
            "version": self.version,
            "deps": self.dependency_hash,
        }
        return _hash_json(payload)


@dataclass(frozen=True)
class EvaluationReceipt:
    property_id: str
    evaluator_id: str
    observation_hash: str
    result: Status
    evidence: Mapping[str, Any]
    ceiling: Ceiling
    run_id: str | None = None
    timestamp: str | None = None

    def canonical(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "evaluator_id": self.evaluator_id,
            "observation_hash": self.observation_hash,
            "result": self.result.value,
            "evidence": _canonicalize(self.evidence),
            "ceiling": self.ceiling.canonical(),
            "run_id": self.run_id,
            "timestamp": self.timestamp,
        }


class ExecutableEvaluator(Protocol):
    spec: EvaluatorSpec

    def evaluate(
        self,
        artifact: Any,
        observation_set: Mapping[str, Any],
    ) -> tuple[Status, Mapping[str, Any]]: ...


@dataclass(frozen=True)
class PropertyRegistry:
    """In-memory immutable registry; persistence is deliberately out of scope."""

    properties: tuple[Property, ...] = ()
    evaluators: tuple[EvaluatorSpec, ...] = ()

    def property(self, property_id: str) -> Property:
        for item in self.properties:
            if item.id == property_id:
                return item
        raise KeyError(property_id)

    def evaluator(self, evaluator_id: str) -> EvaluatorSpec:
        for item in self.evaluators:
            if item.id == evaluator_id:
                return item
        raise KeyError(evaluator_id)

    def register_property(self, item: Property) -> PropertyRegistry:
        if any(existing.id == item.id for existing in self.properties):
            return self
        return PropertyRegistry(self.properties + (item,), self.evaluators)

    def register_evaluator(self, item: EvaluatorSpec) -> PropertyRegistry:
        if any(existing.id == item.id for existing in self.evaluators):
            return self
        return PropertyRegistry(self.properties, self.evaluators + (item,))


def aggregate_criterion(receipts: Sequence[EvaluationReceipt]) -> tuple[Status, ...]:
    """Aggregate atomic property states without collapsing them to a score.

    Any deterministic FAIL remains FAIL. The function returns one status per
    atomic property and therefore preserves the evidence surface.
    """
    return tuple(receipt.result for receipt in receipts)


def observation_hash(observation_set: Mapping[str, Any]) -> str:
    return _hash_json(observation_set)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonicalize(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, set):
        return [_canonicalize(item) for item in sorted(value, key=repr)]
    return value


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
