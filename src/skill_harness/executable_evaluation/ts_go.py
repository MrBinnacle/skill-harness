"""Deterministic evaluators for a TS→Go structural translation fixture.

The runner supplies normalized observations rather than allowing evaluators to
perform I/O. This keeps the evaluator pure while still exercising the TS→Go
property surface. The observation schema is intentionally small and explicit:

    {
      "go_declarations": [{"kind": "type", "name": "User"}, ...],
      "structural_mappings": [
        {"source": "interface User", "target": "type User struct"}, ...
      ]
    }

A future runner can populate these facts with a real TypeScript and Go AST
walk. The evaluator does not make claims about how those facts were obtained.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import Ceiling, EvaluatorSpec, Status


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
class _Evaluator:
    spec: EvaluatorSpec
    expected: tuple[Any, ...]

    def evaluate(
        self,
        artifact: Any,
        observation_set: Mapping[str, Any],
    ) -> tuple[Status, Mapping[str, Any]]:
        raise NotImplementedError


@dataclass(frozen=True)
class _DeclarationEvaluator(_Evaluator):
    expected: tuple[tuple[str, str], ...]

    def evaluate(self, artifact: Any, observation_set: Mapping[str, Any]) -> tuple[Status, Mapping[str, Any]]:
        actual = tuple(
            (str(item["kind"]), str(item["name"]))
            for item in observation_set.get("go_declarations", ())
        )
        expected = tuple(sorted(self.expected))
        actual_sorted = tuple(sorted(actual))
        if actual_sorted == expected:
            return Status.PASS, {"expected": expected, "observed": actual_sorted}
        return Status.FAIL, {"expected": expected, "observed": actual_sorted}


@dataclass(frozen=True)
class _StructuralMappingEvaluator(_Evaluator):
    expected: tuple[tuple[str, str], ...]

    def evaluate(self, artifact: Any, observation_set: Mapping[str, Any]) -> tuple[Status, Mapping[str, Any]]:
        actual = tuple(
            (str(item["source"]), str(item["target"]))
            for item in observation_set.get("structural_mappings", ())
        )
        expected = tuple(sorted(self.expected))
        actual_sorted = tuple(sorted(actual))
        if actual_sorted == expected:
            return Status.PASS, {"expected": expected, "observed": actual_sorted}
        return Status.FAIL, {"expected": expected, "observed": actual_sorted}


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
