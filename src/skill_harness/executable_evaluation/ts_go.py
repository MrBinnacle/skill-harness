"""Deterministic evaluators for a TS→Go structural translation fixture.

The runner supplies normalized observations rather than allowing evaluators to
perform I/O. This keeps the evaluator pure while still exercising the TS→Go
property surface. A future runner can populate these facts from real
TypeScript and Go AST walks; the evaluator does not claim how they were
obtained.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import Ceiling, EvaluatorSpec, ExecutableEvaluator, Status


_DECLARATION_CEILING = Ceiling(
    establishes=("required declarations are present", "forbidden declarations are absent"),
    does_not_establish=("semantic equivalence", "runtime behavior", "type soundness beyond the observed declarations"),
)

_MAPPING_CEILING = Ceiling(
    establishes=("declared TS→Go structural mappings match the fixed mapping table",),
    does_not_establish=("semantic equivalence", "runtime behavior", "unlisted language constructs"),
)


def declaration_evaluator_spec(code_hash: str = "fixture-v1") -> EvaluatorSpec:
    return EvaluatorSpec(
        version="1.0.0",
        input_schema="artifact + observation_set.go_declarations",
        ceiling=_DECLARATION_CEILING,
        code_hash=code_hash,
        dependency_hash="stdlib-only",
    )


def structural_mapping_evaluator_spec(code_hash: str = "fixture-v1") -> EvaluatorSpec:
    return EvaluatorSpec(
        version="1.0.0",
        input_schema="artifact + observation_set.structural_mappings",
        ceiling=_MAPPING_CEILING,
        code_hash=code_hash,
        dependency_hash="stdlib-only",
    )


@dataclass(frozen=True)
class _DeclarationEvaluator:
    spec: EvaluatorSpec
    expected: tuple[tuple[str, str], ...]

    def evaluate(self, artifact: Any, observation_set: Mapping[str, Any]) -> tuple[Status, Mapping[str, Any]]:
        del artifact
        if "go_declarations" not in observation_set:
            return Status.UNSUPPORTED, {"reason": "go_declarations observation is absent"}

        actual = {
            (str(item["kind"]), str(item["name"]))
            for item in observation_set["go_declarations"]
        }
        expected = set(self.expected)
        forbidden = {
            (str(item["kind"]), str(item["name"]))
            for item in observation_set.get("forbidden_go_declarations", ())
        }
        missing = sorted(expected - actual)
        present_forbidden = sorted(forbidden & actual)
        evidence = {
            "expected": sorted(expected),
            "observed": sorted(actual),
            "missing": missing,
            "forbidden_present": present_forbidden,
        }
        if missing or present_forbidden:
            return Status.FAIL, evidence
        return Status.PASS, evidence


@dataclass(frozen=True)
class _StructuralMappingEvaluator:
    spec: EvaluatorSpec
    expected: tuple[tuple[str, str], ...]

    def evaluate(self, artifact: Any, observation_set: Mapping[str, Any]) -> tuple[Status, Mapping[str, Any]]:
        del artifact
        if "structural_mappings" not in observation_set:
            return Status.UNSUPPORTED, {"reason": "structural_mappings observation is absent"}

        actual = {
            (str(item["source"]), str(item["target"]))
            for item in observation_set["structural_mappings"]
        }
        expected = set(self.expected)
        missing = sorted(expected - actual)
        evidence = {
            "expected": sorted(expected),
            "observed": sorted(actual),
            "missing": missing,
        }
        if missing:
            return Status.FAIL, evidence
        return Status.PASS, evidence


def declaration_evaluator(
    expected: tuple[tuple[str, str], ...],
    code_hash: str = "fixture-v1",
) -> ExecutableEvaluator:
    return _DeclarationEvaluator(declaration_evaluator_spec(code_hash), expected)


def structural_mapping_evaluator(
    expected: tuple[tuple[str, str], ...],
    code_hash: str = "fixture-v1",
) -> ExecutableEvaluator:
    return _StructuralMappingEvaluator(structural_mapping_evaluator_spec(code_hash), expected)
