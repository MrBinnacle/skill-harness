"""Deterministic executable-evaluator contracts.

This package defines the authority boundary between mechanically decidable
properties and residual judgment. Evaluators are pure functions over an
artifact and an immutable observation set; they never invoke a model.
"""

from .contracts import (
    Authority,
    Ceiling,
    CriterionResult,
    EvaluationReceipt,
    ExecutableEvaluator,
    EvaluatorSpec,
    Property,
    PropertyRegistry,
    PropertyType,
    Status,
    aggregate_criterion,
)
from .ts_go import declaration_evaluator, structural_mapping_evaluator

__all__ = [
    "Authority",
    "Ceiling",
    "CriterionResult",
    "EvaluationReceipt",
    "ExecutableEvaluator",
    "EvaluatorSpec",
    "Property",
    "PropertyRegistry",
    "PropertyType",
    "Status",
    "aggregate_criterion",
    "declaration_evaluator",
    "structural_mapping_evaluator",
]
