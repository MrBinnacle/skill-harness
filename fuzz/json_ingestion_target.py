#!/usr/bin/env python3
"""Atheris target: JSON ingestion into extractor output models (#170).

Feeds arbitrary bytes into the pydantic model_validate / model_validate_json
paths that deserialise extraction-tool output and ExtractionResult JSONL rows.
ValidationError and JSONDecodeError are expected refusals, not crashes.

Usage:
  python fuzz/json_ingestion_target.py -max_total_time=1800 fuzz/corpus/json \\
      -artifact_prefix=fuzz/crashes/json/
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import atheris
from pydantic import ValidationError

_REPO = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO / "src" / "skill_harness"
_SRC = _SRC_ROOT / "extractor"


def _ensure_package_shells() -> None:
    if "skill_harness" not in sys.modules:
        pkg = types.ModuleType("skill_harness")
        pkg.__path__ = [str(_SRC_ROOT)]  # type: ignore[attr-defined]
        pkg.__package__ = "skill_harness"
        sys.modules["skill_harness"] = pkg
    if "skill_harness.extractor" not in sys.modules:
        sub = types.ModuleType("skill_harness.extractor")
        sub.__path__ = [str(_SRC)]  # type: ignore[attr-defined]
        sub.__package__ = "skill_harness.extractor"
        sys.modules["skill_harness.extractor"] = sub


_ensure_package_shells()

with atheris.instrument_imports(include=["skill_harness.extractor.models"]):
    from skill_harness.extractor.models import (
        ExtractedClause,
        ExtractionResult,
        FalsifyingCaseSchema,
        instrument_from_mapping,
    )


def TestOneInput(data: bytes) -> None:
    """Feed arbitrary bytes through extraction-output model ingestion."""
    try:
        FalsifyingCaseSchema.model_validate_json(data)
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError):
        pass

    try:
        ExtractedClause.model_validate_json(data)
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError):
        pass

    try:
        ExtractionResult.model_validate_json(data)
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError):
        pass

    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return

    if isinstance(obj, dict):
        try:
            FalsifyingCaseSchema.model_validate(obj)
        except (ValidationError, ValueError, TypeError):
            pass
        try:
            ExtractedClause.model_validate(obj)
        except (ValidationError, ValueError, TypeError):
            pass
        try:
            ExtractionResult.model_validate(obj)
        except (ValidationError, ValueError, TypeError):
            pass
        instrument_from_mapping(obj)
        clauses = obj.get("clauses")
        if isinstance(clauses, list):
            for item in clauses:
                if isinstance(item, dict):
                    try:
                        ExtractedClause.model_validate(item)
                    except (ValidationError, ValueError, TypeError):
                        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
