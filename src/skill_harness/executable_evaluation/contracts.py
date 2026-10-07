"""Immutable, content-addressed contracts for deterministic evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class Status(StrEnum):
    PASS = "PASS"  # noqa: S105 - an evaluator verdict, not a credential
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
        return _hash_json(
            {"code": self.code_hash, "version": self.version, "deps": self.dependency_hash}
        )


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


@dataclass(frozen=True)
class CriterionResult:
    """Structured aggregation of atomic property states; never a score."""

    properties: tuple[EvaluationReceipt, ...]

    @property
    def has_failure(self) -> bool:
        return any(receipt.result is Status.FAIL for receipt in self.properties)

    def statuses(self) -> tuple[Status, ...]:
        return tuple(receipt.result for receipt in self.properties)


class ExecutableEvaluator(Protocol):
    @property
    def spec(self) -> EvaluatorSpec:
        """Read-only: an evaluator's spec is fixed at construction.

        Declared as a property rather than a mutable attribute so frozen
        dataclass implementations satisfy the protocol. A settable `spec`
        would let a caller swap an evaluator's identity after a receipt
        already cited it.
        """

    def evaluate(
        self, artifact: Any, observation_set: Mapping[str, Any]
    ) -> tuple[Status, Mapping[str, Any]]: ...


@dataclass(frozen=True)
class PropertyRegistry:
    """Immutable registry; persistence is deliberately out of scope here."""

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
        return PropertyRegistry((*self.properties, item), self.evaluators)

    def register_evaluator(self, item: EvaluatorSpec) -> PropertyRegistry:
        if any(existing.id == item.id for existing in self.evaluators):
            return self
        return PropertyRegistry(self.properties, (*self.evaluators, item))

    def bind(self, property_id: str, evaluator_id: str) -> Property:
        """Validate that an evaluator cannot exceed the property's ceiling."""
        prop = self.property(property_id)
        evaluator = self.evaluator(evaluator_id)
        if not set(evaluator.ceiling.establishes).issubset(prop.ceiling.establishes):
            raise ValueError("evaluator establishes claims outside the property's ceiling")
        return prop


def aggregate_criterion(receipts: Sequence[EvaluationReceipt]) -> CriterionResult:
    """Preserve atomic results; deterministic FAIL remains final at that property."""
    return CriterionResult(tuple(receipts))


def make_receipt(
    property: Property,
    evaluator: EvaluatorSpec,
    observation_set: Mapping[str, Any],
    result: Status,
    evidence: Mapping[str, Any],
    *,
    run_id: str | None = None,
    timestamp: str | None = None,
) -> EvaluationReceipt:
    """Create a receipt only when evaluator authority fits property authority."""
    if not set(evaluator.ceiling.establishes).issubset(property.ceiling.establishes):
        raise ValueError("evaluator establishes claims outside the property's ceiling")
    return EvaluationReceipt(
        property_id=property.id,
        evaluator_id=evaluator.id,
        observation_hash=observation_hash(observation_set),
        result=result,
        evidence=evidence,
        ceiling=evaluator.ceiling,
        run_id=run_id,
        timestamp=timestamp,
    )


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
        _canonicalize(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
