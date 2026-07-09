"""Evidence-store write path for paired Inspect ``.eval`` logs (v0.2).

Bridges the agentic subject layer to the append-only evidence store: parse a
Full/Null pair of Inspect eval logs, then write run + samples + Tier-1 outcome
verdicts through the existing repository machinery, with the harness-pin
admissibility check applied AT WRITE TIME (locked evidence model — the
``admissibility_state`` column is a snapshot, never recomputed at read time).

Design constraints:

- Parsing (``parse_eval_log``) needs the optional ``[inspect]`` extra and is
  lazily imported. Writing (``write_paired_evidence``) is pure stdlib + the
  storage layer, so the entire admissibility/pairing logic is testable in the
  default dev/CI environment (same split as ``inspect_adapter``).
- Pin rule (pre-reg "Harness pin" row): recorded per trial, identical across
  arms, or the trial is INADMISSIBLE. A missing or mismatched fingerprint
  writes the verdicts as ``inadmissible`` (evidence of the defect is kept,
  append-only ethos) — it does not refuse the write. Structural defects
  (wrong condition, different skills, unequal epoch sets, failed eval) DO
  refuse: they are apparatus errors, not evidence.
- Idempotency: the evidence ``run_id`` is derived deterministically from the
  two Inspect task ids, so re-ingesting the same pair of logs raises
  ``AlreadyIngestedError`` instead of double-counting.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict

from skill_harness.storage.models import (
    ClauseWrite,
    MetricVersionWrite,
    OracleVerdictWrite,
    RunWrite,
    SampleWrite,
    SkillWrite,
)
from skill_harness.storage.repositories.evidence.clauses import (
    get_clause_by_id,
    insert_clause,
)
from skill_harness.storage.repositories.evidence.metric_versions import (
    get_metric_version,
    insert_metric_version,
)
from skill_harness.storage.repositories.evidence.oracle_verdicts import (
    insert_oracle_verdict,
)
from skill_harness.storage.repositories.evidence.runs import (
    get_run_by_id,
    insert_run,
)
from skill_harness.storage.repositories.evidence.samples import insert_sample
from skill_harness.storage.repositories.evidence.skills import (
    get_skill_by_id,
    insert_skill,
)
from skill_harness.storage.transaction import writer_transaction
from skill_harness.subject.inspect_adapter import SubjectLayerNotInstalledError

# Whole-skill sentinel clause: v0.2's unit of evaluation is the whole skill
# (Full-vs-Null), not an extracted clause. Real clauses index from 0, so -1 is
# reserved and cannot collide (UNIQUE(skill_id, clause_index)).
WHOLE_SKILL_CLAUSE_INDEX: int = -1
OUTCOME_AXIS: str = "outcome"

# Version of the subject outcome-oracle decision logic (score decoding +
# pairing + observation mapping). Bump on any semantic change; the registered
# implementation_hash pins the exact source alongside it.
ORACLE_METRIC_VERSION: str = "0.2.0"

_SCORE_VALUE_MAP: dict[str, float] = {"C": 1.0, "I": 0.0}


class EvalLogIngestError(ValueError):
    """Base error for the .eval → evidence-store write path."""


class EvalLogNotSuccessError(EvalLogIngestError):
    """Raised when an eval log did not complete successfully (apparatus error)."""


class PairedLogMismatchError(EvalLogIngestError):
    """Raised when the two logs are not a valid Full/Null pair (apparatus error)."""


class AlreadyIngestedError(EvalLogIngestError):
    """Raised when this pair of Inspect task ids was already written."""


class ParsedSample(BaseModel):
    """One subject trial extracted from an Inspect eval log."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    condition: Literal["full", "null"]
    skill_name: str
    epoch: int
    scorer_name: str
    score_value: float  # 1.0 pass | 0.0 fail (outcome oracle)
    output_text: str
    subject_model: str
    harness_pin_json: str | None
    harness_pin_fingerprint: str | None
    input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    output_tokens: int | None
    usd: float | None


class ParsedEvalLog(BaseModel):
    """The write-relevant projection of one Inspect ``.eval`` log."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    task_name: str
    task_id: str
    created: str
    status: str
    samples: tuple[ParsedSample, ...]


class IngestResult(BaseModel):
    """What one paired ingest wrote, including the write-time admissibility."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    run_id: str
    skill_id: str
    clause_id: str
    sample_ids: tuple[str, ...]
    verdict_ids: tuple[str, ...]
    admissibility_state: Literal["admissible", "inadmissible"]
    inadmissibility_reason: str | None


def parse_eval_log(path: Path) -> ParsedEvalLog:
    """Parse one Inspect ``.eval`` log into the write-relevant projection.

    Requires the optional ``[inspect]`` extra (lazy import, same convention as
    ``build_paired_tasks``).

    :raises SubjectLayerNotInstalledError: optional extra not installed.
    :raises EvalLogIngestError: a sample carries no score.
    """
    try:
        from inspect_ai.log import read_eval_log
    except ImportError as exc:  # pragma: no cover — exercised only sans extra
        raise SubjectLayerNotInstalledError(
            'parsing .eval logs requires the optional extra: pip install "skill-harness[inspect]"'
        ) from exc

    log = read_eval_log(str(path))
    samples: list[ParsedSample] = []
    for s in log.samples or []:
        if not s.scores:
            raise EvalLogIngestError(f"{path}: sample id={s.id} epoch={s.epoch} has no scores")
        scorer_name, score = next(iter(s.scores.items()))
        metadata = s.metadata or {}
        pin = metadata.get("harness_pin")
        usage = _sum_usage(getattr(s, "model_usage", None) or {})
        completion = getattr(s.output, "completion", "") or ""
        samples.append(
            ParsedSample(
                condition=_require_condition(metadata.get("condition"), path),
                skill_name=str(metadata.get("skill", "")),
                epoch=int(s.epoch),
                scorer_name=scorer_name,
                score_value=_score_to_float(score.value, path),
                output_text=completion,
                subject_model=str((pin or {}).get("model") or log.eval.model),
                harness_pin_json=(
                    json.dumps(pin, sort_keys=True, separators=(",", ":"))
                    if pin is not None
                    else None
                ),
                harness_pin_fingerprint=metadata.get("harness_pin_fingerprint"),
                input_tokens=usage.input_tokens,
                cache_read_input_tokens=usage.cache_read,
                cache_creation_input_tokens=usage.cache_write,
                output_tokens=usage.output_tokens,
                usd=usage.usd,
            )
        )
    return ParsedEvalLog(
        task_name=log.eval.task,
        task_id=log.eval.task_id,
        created=log.eval.created,
        status=str(log.status),
        samples=tuple(samples),
    )


def ingest_paired_eval_logs(
    *,
    full_log: Path,
    null_log: Path,
    skill_dir: Path,
    conn: sqlite3.Connection,
) -> IngestResult:
    """Parse a Full/Null ``.eval`` pair and write it to the evidence store.

    Convenience composition of :func:`parse_eval_log` (needs the ``[inspect]``
    extra) and :func:`write_paired_evidence` (pure).
    """
    return write_paired_evidence(
        full=parse_eval_log(full_log),
        null=parse_eval_log(null_log),
        skill_dir=skill_dir,
        conn=conn,
    )


def write_paired_evidence(
    *,
    full: ParsedEvalLog,
    null: ParsedEvalLog,
    skill_dir: Path,
    conn: sqlite3.Connection,
) -> IngestResult:
    """Write one parsed Full/Null pair through the admissibility machinery.

    Writes (single ``BEGIN IMMEDIATE`` transaction): the skill row (idempotent,
    ``skill_id`` = SHA-256 of SKILL.md bytes, extractor convention), the
    whole-skill sentinel clause, the outcome-oracle ``metric_versions`` row,
    one ``runs`` row (``run_kind='evaluate_skill'``), one sample per (arm,
    epoch) carrying the harness-pin fields, and one ``full_vs_null`` Tier-1
    verdict per epoch with observation 1.0 (Full passed, Null failed) / 0.5
    (tie) / 0.0 (Null passed, Full failed).

    Harness-pin rule applied at write time: every sample must carry a pin
    fingerprint and all fingerprints must be identical across both arms, else
    every verdict of this run is written ``inadmissible``
    (``harness_pin_missing`` / ``harness_pin_mismatch``).

    :raises EvalLogNotSuccessError: either log's status is not ``success``.
    :raises PairedLogMismatchError: the logs are not a valid Full/Null pair.
    :raises AlreadyIngestedError: this pair of task ids was already written.
    :raises FileNotFoundError: ``skill_dir`` has no SKILL.md.
    """
    _validate_pair(full, null)

    skill_source = skill_dir / "SKILL.md"
    if not skill_source.is_file():
        raise FileNotFoundError(f"no SKILL.md in skill_dir: {skill_dir}")
    source_bytes = skill_source.read_bytes()
    skill_id = hashlib.sha256(source_bytes).hexdigest()
    skill_name = full.samples[0].skill_name

    run_id = _derived_run_id(full.task_id, null.task_id)
    if get_run_by_id(conn, run_id) is not None:
        raise AlreadyIngestedError(
            f"task pair ({full.task_id}, {null.task_id}) already ingested as run {run_id}"
        )

    admissibility_state, inadmissibility_reason = _pin_admissibility(full, null)
    scorer_name = full.samples[0].scorer_name
    metric_id = f"subject:{scorer_name}"
    clause_id = hashlib.sha256(f"{skill_id}:{WHOLE_SKILL_CLAUSE_INDEX}".encode()).hexdigest()
    now = _utcnow_iso()

    sample_ids: list[str] = []
    verdict_ids: list[str] = []
    with writer_transaction(conn):
        if get_skill_by_id(conn, skill_id) is None:
            insert_skill(
                conn,
                SkillWrite(
                    skill_id=skill_id,
                    name=skill_name,
                    source_path=str(skill_source),
                    source_sha256=skill_id,
                    imported_at=now,
                ),
            )
        if get_clause_by_id(conn, clause_id) is None:
            insert_clause(
                conn,
                ClauseWrite(
                    clause_id=clause_id,
                    skill_id=skill_id,
                    clause_index=WHOLE_SKILL_CLAUSE_INDEX,
                    rendering_index=WHOLE_SKILL_CLAUSE_INDEX,
                    clause_text=(
                        "WHOLE-SKILL — v0.2 Full-vs-Null primary contrast "
                        "(subject-layer outcome oracle; not an extracted clause)"
                    ),
                    axis=OUTCOME_AXIS,
                    comparator="increase",
                    oracle_tier=1,
                    vacuity_flag="none",
                    falsifying_case_schema_sha256=None,
                    created_at=now,
                ),
            )
        if get_metric_version(conn, metric_id, ORACLE_METRIC_VERSION) is None:
            insert_metric_version(
                conn,
                MetricVersionWrite(
                    metric_id=metric_id,
                    version=ORACLE_METRIC_VERSION,
                    implementation_hash=_oracle_implementation_hash(),
                    tier=1,
                    audited=0,
                    # Mechanical validity = the offline unit tests over score
                    # decoding + pairing + observation mapping
                    # (tests/test_subject_ingest.py); sandbox execution is
                    # environment, pinned by the harness pin.
                    mechanical_validity_test_passed=1,
                    registered_at=now,
                ),
            )
        insert_run(
            conn,
            RunWrite(
                run_id=run_id,
                skill_id=skill_id,
                run_kind="evaluate_skill",
                config_json=json.dumps(
                    {
                        "source": "inspect_eval_log",
                        "contrast": "full_vs_null",
                        "full_task_id": full.task_id,
                        "full_task_name": full.task_name,
                        "null_task_id": null.task_id,
                        "null_task_name": null.task_name,
                        "scorer": scorer_name,
                        "harness_pin_json": full.samples[0].harness_pin_json,
                        "harness_pin_fingerprint": full.samples[0].harness_pin_fingerprint,
                    },
                    sort_keys=True,
                ),
                started_at=full.created,
                # the pair is already finished when ingested — no in-flight state
                completed_at=now,
            ),
        )

        by_epoch: dict[int, dict[str, str]] = {}
        for log in (full, null):
            for parsed in log.samples:
                sample_id = str(uuid.uuid4())
                insert_sample(
                    conn,
                    SampleWrite(
                        sample_id=sample_id,
                        run_id=run_id,
                        clause_id=clause_id,
                        condition=parsed.condition,
                        subject_model=parsed.subject_model,
                        subject_seed=None,
                        output_text=parsed.output_text,
                        output_sha256=hashlib.sha256(
                            parsed.output_text.encode("utf-8")
                        ).hexdigest(),
                        sampled_at=log.created,
                        sample_index=parsed.epoch,
                        input_tokens=parsed.input_tokens,
                        cache_read_input_tokens=parsed.cache_read_input_tokens,
                        cache_creation_input_tokens=parsed.cache_creation_input_tokens,
                        output_tokens=parsed.output_tokens,
                        usd=parsed.usd,
                        harness_pin_json=parsed.harness_pin_json,
                        harness_pin_fingerprint=parsed.harness_pin_fingerprint,
                    ),
                )
                sample_ids.append(sample_id)
                by_epoch.setdefault(parsed.epoch, {})[parsed.condition] = sample_id

        full_by_epoch = {s.epoch: s for s in full.samples}
        null_by_epoch = {s.epoch: s for s in null.samples}
        for epoch in sorted(by_epoch):
            verdict_id = str(uuid.uuid4())
            insert_oracle_verdict(
                conn,
                OracleVerdictWrite(
                    verdict_id=verdict_id,
                    run_id=run_id,
                    clause_id=clause_id,
                    axis=OUTCOME_AXIS,
                    comparison="full_vs_null",
                    sample_a_id=by_epoch[epoch]["full"],
                    sample_b_id=by_epoch[epoch]["null"],
                    observation=_observation(
                        full_by_epoch[epoch].score_value, null_by_epoch[epoch].score_value
                    ),
                    oracle_tier=1,
                    metric_id=metric_id,
                    metric_version=ORACLE_METRIC_VERSION,
                    judge_id=None,
                    calibration_event_id=None,
                    position_swap_agreement=None,
                    admissibility_state=admissibility_state,
                    inadmissibility_reason=inadmissibility_reason,
                    written_at=now,
                ),
            )
            verdict_ids.append(verdict_id)

    return IngestResult(
        run_id=run_id,
        skill_id=skill_id,
        clause_id=clause_id,
        sample_ids=tuple(sample_ids),
        verdict_ids=tuple(verdict_ids),
        admissibility_state=admissibility_state,
        inadmissibility_reason=inadmissibility_reason,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _validate_pair(full: ParsedEvalLog, null: ParsedEvalLog) -> None:
    for role, log in (("full", full), ("null", null)):
        if log.status != "success":
            raise EvalLogNotSuccessError(
                f"{role} log {log.task_name!r} has status {log.status!r}, not success"
            )
        if not log.samples:
            raise PairedLogMismatchError(f"{role} log {log.task_name!r} has no samples")
        wrong = [s.condition for s in log.samples if s.condition != role]
        if wrong:
            raise PairedLogMismatchError(
                f"{role} log {log.task_name!r} carries samples with condition(s) {wrong}"
            )
        epochs = [s.epoch for s in log.samples]
        if len(epochs) != len(set(epochs)):
            raise PairedLogMismatchError(f"{role} log {log.task_name!r} has duplicate epochs")

    skills = {s.skill_name for s in full.samples} | {s.skill_name for s in null.samples}
    if len(skills) != 1:
        raise PairedLogMismatchError(f"logs disagree on the skill under test: {sorted(skills)}")

    full_epochs = {s.epoch for s in full.samples}
    null_epochs = {s.epoch for s in null.samples}
    if full_epochs != null_epochs:
        raise PairedLogMismatchError(
            f"unpaired epochs: full={sorted(full_epochs)} null={sorted(null_epochs)}"
        )

    scorers = {s.scorer_name for s in full.samples} | {s.scorer_name for s in null.samples}
    if len(scorers) != 1:
        raise PairedLogMismatchError(f"logs disagree on the scorer: {sorted(scorers)}")


def _pin_admissibility(
    full: ParsedEvalLog, null: ParsedEvalLog
) -> tuple[Literal["admissible", "inadmissible"], str | None]:
    fingerprints = {s.harness_pin_fingerprint for s in full.samples} | {
        s.harness_pin_fingerprint for s in null.samples
    }
    if None in fingerprints or "" in fingerprints:
        return "inadmissible", "harness_pin_missing"
    if len(fingerprints) > 1:
        return "inadmissible", "harness_pin_mismatch"
    return "admissible", None


def _observation(full_score: float, null_score: float) -> float:
    """Map a paired outcome to the {0, 0.5, 1} verdict encoding (STAT-F4)."""
    if full_score > null_score:
        return 1.0
    if full_score < null_score:
        return 0.0
    return 0.5


def _score_to_float(value: object, path: Path) -> float:
    if isinstance(value, str):
        mapped = _SCORE_VALUE_MAP.get(value)
        if mapped is None:
            raise EvalLogIngestError(f"{path}: unmappable score value {value!r}")
        return mapped
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    raise EvalLogIngestError(f"{path}: unmappable score value {value!r}")


class _UsageTotals(NamedTuple):
    input_tokens: int | None
    output_tokens: int | None
    cache_read: int | None
    cache_write: int | None
    usd: float | None


def _sum_usage(model_usage: dict[str, object]) -> _UsageTotals:
    """Collapse per-model usage into flat totals (usually a single model)."""
    tokens: dict[str, int | None] = dict.fromkeys(
        ("input_tokens", "output_tokens", "cache_read", "cache_write")
    )
    usd: float | None = None
    for usage in model_usage.values():
        for src, dst in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("input_tokens_cache_read", "cache_read"),
            ("input_tokens_cache_write", "cache_write"),
        ):
            value = getattr(usage, src, None)
            if value is not None:
                tokens[dst] = (tokens[dst] or 0) + int(value)
        cost = getattr(usage, "total_cost", None)
        if cost is not None:  # e.g. the OpenRouter bridge reports no cost
            usd = (usd or 0.0) + float(cost)
    return _UsageTotals(
        input_tokens=tokens["input_tokens"],
        output_tokens=tokens["output_tokens"],
        cache_read=tokens["cache_read"],
        cache_write=tokens["cache_write"],
        usd=usd,
    )


def _require_condition(value: object, path: Path) -> Literal["full", "null"]:
    if value == "full":
        return "full"
    if value == "null":
        return "null"
    raise EvalLogIngestError(
        f"{path}: sample metadata 'condition' is {value!r}, expected 'full' or 'null' "
        "(was this log produced by build_paired_tasks?)"
    )


def _derived_run_id(full_task_id: str, null_task_id: str) -> str:
    return hashlib.sha256(f"subject-ingest:{full_task_id}:{null_task_id}".encode()).hexdigest()


def _oracle_implementation_hash() -> str:
    """SHA-256 over this module's source — pins the oracle decision logic."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
