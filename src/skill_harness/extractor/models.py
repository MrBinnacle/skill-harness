"""Pydantic models for the extractor layer.

These models represent the structured output from the Claude clause-extraction
tool call. They live in the extractor layer (not the storage layer) and are
translated to ``SkillWrite`` / ``ClauseWrite`` objects before persistence.

DB comparator mapping (schema constraint: increase|decrease|match):
    "increase"              -> "increase"
    "decrease"              -> "decrease"
    "preserve"              -> "match"
    "comparator_unspecified" -> "comparator_unspecified"  [rejected by DB CHECK; caller must handle]

Vacuity flag values in v0.1 (A16: mechanical_vacuous deferred to Track C):
    "none"                              -- non-vacuous clause with falsifying case
    "semantic_vacuous_pending_review"   -- Claude flagged as likely untestable

D4 note: extractor calibration (extractor_id, skill_genre) is deferred to v0.2.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FalsifyingCaseSchema(BaseModel):
    """Falsifying case schema per A15.

    Records the minimum structure needed to construct a test case that can
    falsify a clause. Stored as a SHA-256 of the JSON-serialised schema
    (keys sorted) in ``clauses.falsifying_case_schema_sha256``.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    input_population_spec: Annotated[str, Field(min_length=1)]
    """Human-readable description of the input population the test draws from."""

    expected_directional_pair: Annotated[str, Field(min_length=1)]
    """Description of the (A, B) pair where A should beat B on the clause's axis."""

    min_reproducibility: Annotated[float, Field(gt=0.0, le=1.0)]
    """Minimum fraction of draws that should reproduce the expected direction (0 < x ≤ 1.0)."""

    def sha256_hex(self) -> str:
        """Return the SHA-256 hex digest of the canonical JSON representation."""
        import hashlib

        canonical = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExtractedClause(BaseModel):
    """A single clause as returned by the Claude extraction tool.

    ``comparator`` uses a superset of DB values to let Claude express
    "preserve" (mapped to "match" at persist time) and
    "comparator_unspecified" (used when the clause direction is ambiguous).

    ``vacuity_flag`` in v0.1 is either "none" or
    "semantic_vacuous_pending_review". "mechanical_vacuous" is reserved for
    Track C integration and must not appear here.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    clause_index: Annotated[int, Field(ge=0)]
    """Zero-based position in the skill's authoring order."""

    clause_text: Annotated[str, Field(min_length=1)]
    """Verbatim clause text extracted from the skill body."""

    axis: Annotated[str, Field(min_length=1)]
    """Measurement axis (e.g. 'formality', 'specificity', 'instruction_following')."""

    comparator: Literal["increase", "decrease", "preserve", "comparator_unspecified"]
    """Directional claim made by the clause on its axis."""

    oracle_tier: Literal[1, 2, 3]
    """Preferred oracle tier: 1=mechanical, 2=judge, 3=consequence."""

    vacuity_flag: Literal["none", "semantic_vacuous_pending_review"]
    """v0.1 vacuity classification."""

    falsifying_case: FalsifyingCaseSchema | None = None
    """Present iff vacuity_flag == 'none'."""

    @model_validator(mode="after")
    def falsifying_case_iff_testable(self) -> ExtractedClause:
        """Enforce: falsifying_case required iff vacuity_flag == 'none'."""
        if self.vacuity_flag == "none" and self.falsifying_case is None:
            raise ValueError("falsifying_case is required when vacuity_flag == 'none'")
        if self.vacuity_flag != "none" and self.falsifying_case is not None:
            raise ValueError("falsifying_case must be None when vacuity_flag != 'none'")
        return self


class ExtractionResult(BaseModel):
    """The complete result of one skill extraction pass.

    Returned by ``pipeline.extract_skill()``. Contains both the raw list
    of extracted clauses and derived metadata (skill_id, source_sha256).
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    skill_id: Annotated[str, Field(min_length=1)]
    """Content-derived ID: SHA-256 hex of the raw source bytes."""

    name: Annotated[str, Field(min_length=1)]
    """Skill name, taken from frontmatter ``name`` key or filename stem."""

    source_path: Annotated[str, Field(min_length=1)]
    """Absolute path to the source file."""

    source_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    """SHA-256 hex of the raw source bytes (same as skill_id in v0.1)."""

    clauses: list[ExtractedClause]
    """Extracted clauses in clause_index order."""

    raw_frontmatter: dict[str, Any]
    """Parsed frontmatter key/value pairs (empty dict if no frontmatter)."""
