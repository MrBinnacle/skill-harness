"""Evidence-store write path for Stage-0 Null-only SCREEN ``.eval`` logs (v0.2).

A Stage-0 screen runs the bare (Null) arm of a skill's task k times and asks a
single question: does the model already do the task WITHOUT the skill? p0 = the
Null-arm pass rate. p0 close to 1 → the skill is not needed on this task
(CUT-subsumed); p0 < 1 → the task discriminates, proceed to a paired Stage-1
run. Screens are a hardness GATE, firewalled from the paired verdict machinery
(pre-reg: "screen data never enters verdicts") — hence a dedicated store
(migration 0501), not runs/samples/oracle_verdicts.

This module is the screen sibling of ``ingest.py``:

- Parsing reuses ``parse_eval_log`` (needs the optional ``[inspect]`` extra) —
  a screen log IS a Null-condition Inspect log.
- Writing (``write_screen_evidence``) is pure stdlib + the storage layer.
- Evidence admissibility is passed IN, not inferred. The outcome oracle scores INCORRECT
  for ANY non-zero exit and stores no field distinguishing "subject failed" from
  "oracle harness crashed" (e.g. exit=1 with no structured ORACLE-PASS). That
  distinction was a documented human judgment (see the batch-1 backfill
  manifest). A voided screen is still INGESTED — append-only ethos keeps the
  evidence — and marked ``inadmissible`` so p0 derivation excludes it.
- Idempotency: the screen_run_id is derived from the source Inspect task id, so
  re-ingesting the same log raises ``AlreadyIngestedScreenError``.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from skill_harness.storage.models import ScreenRunWrite, ScreenTrialWrite
from skill_harness.storage.repositories.evidence.screens import (
    get_screen_run_by_id,
    insert_screen_run,
    insert_screen_trial,
)
from skill_harness.storage.transaction import writer_transaction
from skill_harness.subject.ingest import ParsedEvalLog, parse_eval_log

AdmissibilityState = Literal["admissible", "inadmissible"]


class ScreenIngestError(ValueError):
    """Base error for the screen ``.eval`` -> evidence-store write path."""


class NotANullScreenError(ScreenIngestError):
    """Raised when a log is not a valid Null-only screen (wrong condition / no samples)."""


class AlreadyIngestedScreenError(ScreenIngestError):
    """Raised when this source Inspect task id was already written as a screen."""


class ScreenIngestResult(BaseModel):
    """What one screen ingest wrote."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    screen_run_id: str
    skill_name: str
    admissibility_state: AdmissibilityState
    n_trials: int
    n_pass: int


def ingest_screen_eval_log(
    path: Path,
    *,
    admissibility_state: AdmissibilityState,
    inadmissibility_reason: str | None,
    conn: sqlite3.Connection,
) -> ScreenIngestResult:
    """Parse a Null-only screen ``.eval`` and write it to the evidence store.

    Convenience composition of :func:`parse_eval_log` (needs the ``[inspect]``
    extra) and :func:`write_screen_evidence` (pure). The source ``.eval`` file
    bytes are hashed for provenance / idempotency.
    """
    source_eval_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return write_screen_evidence(
        parsed=parse_eval_log(path),
        source_eval_sha256=source_eval_sha256,
        admissibility_state=admissibility_state,
        inadmissibility_reason=inadmissibility_reason,
        conn=conn,
    )


def write_screen_evidence(
    *,
    parsed: ParsedEvalLog,
    source_eval_sha256: str,
    admissibility_state: AdmissibilityState,
    inadmissibility_reason: str | None,
    conn: sqlite3.Connection,
) -> ScreenIngestResult:
    """Write one parsed Null-only screen log to the screen store (single transaction).

    Writes one ``screen_runs`` row and one ``screen_trials`` row per epoch,
    ``passed = 1`` iff the Null arm passed the outcome oracle (score 1.0).

    :raises NotANullScreenError: the log has no samples or a non-Null sample.
    :raises ScreenIngestError: a trial score is not a binary pass/fail, or the
        (state, reason) pair is inconsistent.
    :raises AlreadyIngestedScreenError: this source task id was already ingested.
    """
    if admissibility_state == "inadmissible" and not inadmissibility_reason:
        raise ScreenIngestError("inadmissible screen requires an inadmissibility_reason")
    if admissibility_state == "admissible" and inadmissibility_reason:
        raise ScreenIngestError("admissible screen must not carry an inadmissibility_reason")

    if not parsed.samples:
        raise NotANullScreenError(f"screen log {parsed.task_name!r} has no samples")
    wrong = sorted({s.condition for s in parsed.samples if s.condition != "null"})
    if wrong:
        raise NotANullScreenError(
            f"screen log {parsed.task_name!r} carries non-Null condition(s) {wrong}; "
            "a Stage-0 screen is Null-only"
        )

    skill_names = {s.skill_name for s in parsed.samples}
    if len(skill_names) != 1:
        raise NotANullScreenError(f"screen log disagrees on the skill: {sorted(skill_names)}")
    skill_name = next(iter(skill_names))
    subject_model = parsed.samples[0].subject_model
    fingerprints = {s.harness_pin_fingerprint for s in parsed.samples}
    fingerprint = next(iter(fingerprints)) if len(fingerprints) == 1 else None

    screen_run_id = _derived_screen_run_id(parsed.task_id)
    if get_screen_run_by_id(conn, screen_run_id) is not None:
        raise AlreadyIngestedScreenError(
            f"screen task {parsed.task_id!r} already ingested as {screen_run_id}"
        )

    now = _utcnow_iso()
    n_pass = 0
    with writer_transaction(conn):
        insert_screen_run(
            conn,
            ScreenRunWrite(
                screen_run_id=screen_run_id,
                skill_name=skill_name,
                subject_model=subject_model,
                harness_pin_fingerprint=fingerprint,
                source_eval_task_id=parsed.task_id,
                source_eval_sha256=source_eval_sha256,
                admissibility_state=admissibility_state,
                inadmissibility_reason=inadmissibility_reason,
                created_at=parsed.created,
                ingested_at=now,
            ),
        )
        for s in parsed.samples:
            passed = _passed(s.score_value, parsed.task_name)
            n_pass += passed
            insert_screen_trial(
                conn,
                ScreenTrialWrite(
                    screen_trial_id=str(uuid.uuid4()),
                    screen_run_id=screen_run_id,
                    epoch=s.epoch,
                    passed=passed,
                    scorer_name=s.scorer_name,
                    scorer_explanation=None,
                    output_sha256=hashlib.sha256(s.output_text.encode("utf-8")).hexdigest(),
                    sampled_at=parsed.created,
                ),
            )

    return ScreenIngestResult(
        screen_run_id=screen_run_id,
        skill_name=skill_name,
        admissibility_state=admissibility_state,
        n_trials=len(parsed.samples),
        n_pass=n_pass,
    )


def _passed(score_value: float, task_name: str) -> int:
    """Map a binary outcome-oracle score to passed (1) / failed (0).

    A screen trial is pass/fail; a fractional score (e.g. a 0.5 tie) is not a
    valid single-arm outcome and signals a scorer/config problem — refuse rather
    than silently coerce it to a fail.
    """
    if score_value == 1.0:
        return 1
    if score_value == 0.0:
        return 0
    raise ScreenIngestError(
        f"screen {task_name!r}: non-binary trial score {score_value!r} "
        "(expected 1.0 pass or 0.0 fail from the outcome oracle)"
    )


def _derived_screen_run_id(task_id: str) -> str:
    return hashlib.sha256(f"screen-ingest:{task_id}".encode()).hexdigest()


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
