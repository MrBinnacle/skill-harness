"""Clause extraction package.

Public API::

    from skill_harness.extractor import extract_skill, ExtractionResult, ExtractionError

``extract_skill`` is the primary entry point. ``ExtractionResult`` holds the
full extraction output. ``ExtractionError`` (and its subclasses) are raised on
failure.
"""

from __future__ import annotations

from skill_harness.extractor.errors import (
    ExtractionError,
    ExtractorClaudeError,
    MalformedSkillError,
)
from skill_harness.extractor.models import (
    ExtractedClause,
    ExtractionResult,
    ExtractorInstrument,
    FalsifyingCaseSchema,
    compare_extractor_generations,
    instrument_from_mapping,
)
from skill_harness.extractor.pipeline import extract_skill

__all__ = [
    "ExtractedClause",
    "ExtractionError",
    "ExtractionResult",
    "ExtractorClaudeError",
    "ExtractorInstrument",
    "FalsifyingCaseSchema",
    "MalformedSkillError",
    "compare_extractor_generations",
    "extract_skill",
    "instrument_from_mapping",
]
