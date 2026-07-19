"""Skill extraction pipeline.

Orchestrates: parse → Claude extract → validate → (optionally) persist.

Entry point: ``extract_skill()``.

Persistence rules (pipeline safety — see docs/INVARIANTS.md #2):
- ``extract_skill()`` ALWAYS calls Claude (even in dry-run).
- When ``evidence_conn`` is None, results are returned but NOT written.
- When ``evidence_conn`` is provided, rows are written inside a single
  ``writer_transaction`` (BEGIN IMMEDIATE).
- Callers must open the connection via ``open_evidence()`` / ``StorageContext``
  (never a raw sqlite3 connection) to preserve FULL synchronous mode and
  foreign_keys=ON.

Comparator mapping at persist time:
    "preserve"              -> "match"  (DB CHECK accepts increase|decrease|match)
    "comparator_unspecified" -> raises ValueError. extract_skill() lets this
                                 propagate and aborts the whole persist step (no
                                 partial write) rather than silently dropping the
                                 clause -- a silent drop would make the persisted
                                 clause count disagree with the reported extraction
                                 count, corrupting Coverage/Contribution metrics
                                 (mirrors the abort doctrine in extractor/claude.py).
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from skill_harness.extractor.claude import call_extract_clauses
from skill_harness.extractor.models import ExtractedClause, ExtractionResult
from skill_harness.extractor.parser import parse_skill_file
from skill_harness.storage.models import ClauseWrite, SkillWrite
from skill_harness.storage.repositories.evidence.clauses import insert_clause
from skill_harness.storage.repositories.evidence.skills import insert_skill
from skill_harness.storage.transaction import writer_transaction


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _clause_id(skill_id: str, clause_index: int) -> str:
    """Deterministic clause ID: SHA-256 of ``skill_id || ":" || clause_index``."""
    raw = f"{skill_id}:{clause_index}".encode()
    return hashlib.sha256(raw).hexdigest()


def _to_db_comparator(comparator: str) -> str:
    """Map extractor comparator to DB-accepted value."""
    if comparator == "preserve":
        return "match"
    if comparator == "comparator_unspecified":
        raise ValueError(
            "comparator_unspecified cannot be stored: "
            "the clause direction is undefined. "
            "Mark the clause as semantic_vacuous_pending_review instead."
        )
    return comparator  # increase | decrease


def _build_clause_write(
    skill_id: str,
    clause: ExtractedClause,
    now: str,
) -> ClauseWrite:
    """Convert an ``ExtractedClause`` to a ``ClauseWrite`` storage model."""
    fc_sha: str | None = None
    if clause.falsifying_case is not None:
        fc_sha = clause.falsifying_case.sha256_hex()

    return ClauseWrite(
        clause_id=_clause_id(skill_id, clause.clause_index),
        skill_id=skill_id,
        clause_index=clause.clause_index,
        rendering_index=clause.clause_index,  # v0.1: rendering_index == clause_index
        clause_text=clause.clause_text,
        axis=clause.axis,
        comparator=_to_db_comparator(clause.comparator),
        oracle_tier=clause.oracle_tier,
        vacuity_flag=clause.vacuity_flag,
        falsifying_case_schema_sha256=fc_sha,
        created_at=now,
    )


def extract_skill(
    path: Path,
    evidence_conn: sqlite3.Connection | None = None,
) -> ExtractionResult:
    """Parse ``path``, extract clauses via Claude, and optionally persist.

    :param path: Path to the skill SKILL.md (or any .md file).
    :param evidence_conn: If provided, skill + clauses are written inside a
        ``writer_transaction``. If None, extraction proceeds but nothing is
        written (dry-run mode).
    :returns: ``ExtractionResult`` with all extracted clauses.
    :raises MalformedSkillError: If the file cannot be parsed.
    :raises ExtractorClaudeError: If the Claude call fails or returns no clauses.
    :raises ValueError: If any clause has ``comparator_unspecified`` and
        persistence is requested.
    """
    # 1. Parse the source file.
    parsed = parse_skill_file(path)

    # 2. Call Claude to extract clauses.
    clauses = call_extract_clauses(parsed.body)

    # 3. Build the ExtractionResult.
    result = ExtractionResult(
        skill_id=parsed.source_sha256,
        name=parsed.name,
        source_path=parsed.source_path,
        source_sha256=parsed.source_sha256,
        clauses=clauses,
        raw_frontmatter=dict(parsed.frontmatter),
    )

    # 4. Persist (if evidence_conn provided).
    if evidence_conn is not None:
        now = _now_iso()

        skill_write = SkillWrite(
            skill_id=result.skill_id,
            name=result.name,
            source_path=result.source_path,
            source_sha256=result.source_sha256,
            imported_at=now,
        )

        # No pre-filter: _build_clause_write -> _to_db_comparator raises ValueError
        # for comparator_unspecified. Letting it propagate here (before
        # writer_transaction opens) means persistence aborts entirely -- no skill
        # row, no clause rows -- rather than silently writing fewer clauses than
        # were reported (see module docstring).
        clause_writes = [
            _build_clause_write(result.skill_id, clause, now) for clause in result.clauses
        ]

        with writer_transaction(evidence_conn):
            insert_skill(evidence_conn, skill_write)
            for cw in clause_writes:
                insert_clause(evidence_conn, cw)

    return result
