"""Evidence-store write path for paired Inspect ``.eval`` logs (v0.2).

Bridges the agentic subject layer to the append-only evidence store: parse a
Full/Null pair of Inspect eval logs, then write run + samples + Tier-1 outcome
verdicts through the existing repository machinery, with the harness-pin
evidence-admissibility check applied AT WRITE TIME (locked evidence model — the
``admissibility_state`` column is a snapshot, never recomputed at read time).

Design constraints:

- Parsing (``parse_eval_log``) needs the optional ``[inspect]`` extra and is
  lazily imported. Writing (``write_paired_evidence``) is pure stdlib + the
  storage layer, so the entire evidence-admissibility/pairing logic is testable in the
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
- π_c instrumentation (#46/#52): every parsed sample carries ``invoked_skill``
  (v1 detector = a Skill tool-call naming the skill under test, observed in the
  parsed message stream). Every paired write reports π̂_c with a mandatory
  Clopper-Pearson interval over the Full arm, and a treated arm with ZERO
  detected invocations refuses the write (``ZeroInvocationError``) — a dead-arm
  run is an instrumentation finding, never a null effect. Eval logs are
  zstd-compressed (zip method 93): ingestion goes through ``read_eval_log``
  only, never raw archive handling.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import beta as beta_dist  # type: ignore[import-untyped]

from skill_harness.storage.article_fingerprint import ArticleFingerprint
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
from skill_harness.storage.repositories.evidence.metric_identity import (
    append_implementation_restamp,
    classify_implementation_drift,
    record_semantic_digest,
)
from skill_harness.storage.repositories.evidence.metric_versions import (
    get_metric_version,
    insert_metric_version,
)
from skill_harness.storage.repositories.evidence.oracle_verdicts import (
    mint_oracle_verdict,
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
from skill_harness.subject.implementation_identity import semantic_digest
from skill_harness.subject.inspect_adapter import SubjectLayerNotInstalledError

# Whole-skill sentinel clause: v0.2's unit of evaluation is the whole skill
# (Full-vs-Null), not an extracted clause. Real clauses index from 0, so -1 is
# reserved and cannot collide (UNIQUE(skill_id, clause_index)).
WHOLE_SKILL_CLAUSE_INDEX: int = -1
OUTCOME_AXIS: str = "outcome"

# Version of the subject outcome-oracle decision logic (score decoding +
# pairing + observation mapping). Bump on any semantic change; the registered
# implementation_hash pins the exact source alongside it.
# 0.3.0: π_c instrumentation (#52) — pairing gains the zero-invocation refusal
# and the Null-contamination structural check; runs record the π_c block.
ORACLE_METRIC_VERSION: str = "0.3.0"

# π_c (invocation-rate) instrumentation — #46 resolution binds the contract.
# v1 detector = branch (a) only: a Skill tool-call whose arguments name the
# skill under test. Branch (b) (a visible SKILL.md file-read) is DEAD CODE
# under the inspect_swe.claude_code solver (the Skill tool loads SKILL.md
# internally) and stays excluded until a non-claude_code solver exists.
PI_C_DETECTOR_VERSION: str = "v1-skill-tool-call"
SKILL_TOOL_FUNCTION: str = "Skill"
SKILL_TOOL_ARGUMENT: str = "skill"  # arguments key naming the invoked skill
PI_C_CONFIDENCE: float = 0.95

_SCORE_VALUE_MAP: dict[str, float] = {"C": 1.0, "I": 0.0}


class EvalLogIngestError(ValueError):
    """Base error for the .eval → evidence-store write path."""


class EvalLogNotSuccessError(EvalLogIngestError):
    """Raised when an eval log did not complete successfully (apparatus error)."""


class PairedLogMismatchError(EvalLogIngestError):
    """Raised when the two logs are not a valid Full/Null pair (apparatus error)."""


class AlreadyIngestedError(EvalLogIngestError):
    """Raised when this pair of Inspect task ids was already written."""


class MetricImplementationDriftError(EvalLogIngestError):
    """Raised when the store's (metric_id, version) row pins a hash that no
    longer matches the live module (S88 condition K2 — fail-closed re-check)."""


class PiCSummary(BaseModel):
    """π̂_c over the treated (Full) arm, with its Clopper-Pearson interval.

    Mandatory on every :class:`IngestResult` — availability evidence never
    ships without its invocation rate (#52: "mandatory, not optional").
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    invocations: int
    trials: int
    pi_c_hat: float
    ci_low: float
    ci_high: float
    confidence: float


class ZeroInvocationError(EvalLogIngestError):
    """Refusal: the treated (Full) arm shows ZERO detected skill invocations.

    A dead treated arm cannot distinguish "no effect" from "never invoked", so
    no effect verdict is producible — the run surfaces as an INSTRUMENTATION
    FINDING (delivery failure) instead of a null effect (#52). Carries the
    mandatory π̂_c block on ``pi_c`` so the finding renders with its interval.
    """

    def __init__(self, message: str, *, pi_c: PiCSummary) -> None:
        super().__init__(message)
        self.pi_c = pi_c


class ParsedSample(BaseModel):
    """One subject trial extracted from an Inspect eval log."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    condition: Literal["full", "null"]
    skill_name: str
    epoch: int
    scorer_name: str
    # Non-finite refused at the MODEL layer, not only in the parse helper (#363).
    # `_observation(nan, x)` returns 0.5 because both ordered comparisons are
    # False, so a NaN would be recorded as a genuine tie and would dilute every
    # Gate-2 table built from the pair. PR #364's M4 survivor measured that a
    # guard in `_score_to_float` alone does not close this: callers that build
    # `ParsedSample` directly never reach the helper.
    score_value: Annotated[float, Field(allow_inf_nan=False)]  # 1.0 pass | 0.0 fail
    invoked_skill: bool  # v1 π_c detector verdict for this trial (#46/#52)
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
    """What one paired ingest wrote, including write-time evidence admissibility."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    run_id: str
    skill_id: str
    clause_id: str
    sample_ids: tuple[str, ...]
    verdict_ids: tuple[str, ...]
    admissibility_state: Literal["admissible", "inadmissible"]
    inadmissibility_reason: str | None
    pi_c: PiCSummary  # mandatory — never optional (#52)


def detect_skill_invocation(messages: Iterable[object], skill_name: str) -> bool:
    """v1 π_c detector (#46 branch (a)): did this trial invoke the skill?

    Fires iff the message stream contains a tool-call entry with
    ``function == "Skill"`` and ``arguments["skill"] == skill_name``. Only
    ``tool_calls`` lists are consulted — tool-role RESULT messages also carry a
    ``function`` field and must not count. Branch (b) (a visible file-read of
    the skill's SKILL.md) is dead code under the ``inspect_swe.claude_code``
    solver and stays excluded (#46).

    Deliberately conservative: any shape this duck-typed scan does not
    recognize counts as NOT invoked (an undercount can only make the
    zero-invocation refusal fire more, never fabricate an invocation).
    """
    if not skill_name:
        return False
    for message in messages:
        calls = getattr(message, "tool_calls", None) or ()
        for call in calls:
            if getattr(call, "function", None) != SKILL_TOOL_FUNCTION:
                continue
            arguments = getattr(call, "arguments", None)
            if isinstance(arguments, dict) and arguments.get(SKILL_TOOL_ARGUMENT) == skill_name:
                return True
    return False


def clopper_pearson(
    invocations: int, trials: int, *, confidence: float = PI_C_CONFIDENCE
) -> tuple[float, float]:
    """Exact (Clopper-Pearson) two-sided binomial interval for π_c.

    Beta-quantile form: lower = Beta(a/2; x, n-x+1), upper = Beta(1-a/2; x+1,
    n-x) at level a = 1-confidence, with the exact closed endpoints 0 at x=0
    and 1 at x=n. Chosen over
    approximate intervals because π_c reporting is mandatory at any n and the
    treated-arm n here is routinely tiny (#52).
    """
    if trials < 1:
        raise ValueError(f"trials must be >= 1; got {trials}")
    if not 0 <= invocations <= trials:
        raise ValueError(f"invocations must be in [0, {trials}]; got {invocations}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1); got {confidence}")
    alpha = 1.0 - confidence
    low = (
        0.0
        if invocations == 0
        else float(beta_dist.ppf(alpha / 2, invocations, trials - invocations + 1))
    )
    high = (
        1.0
        if invocations == trials
        else float(beta_dist.ppf(1 - alpha / 2, invocations + 1, trials - invocations))
    )
    return low, high


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
        skill_name = str(metadata.get("skill", ""))
        samples.append(
            ParsedSample(
                condition=_require_condition(metadata.get("condition"), path),
                skill_name=skill_name,
                invoked_skill=detect_skill_invocation(s.messages or [], skill_name),
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
    """Write one parsed Full/Null pair through the evidence-admissibility machinery.

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

    π_c rule (#52): π̂_c over the Full arm plus its Clopper-Pearson interval is
    computed on every write, returned on ``IngestResult.pi_c`` (mandatory) and
    recorded in the run's ``config_json``. Zero detected invocations in the
    treated arm REFUSE the write — an instrumentation finding, not evidence.

    :raises EvalLogNotSuccessError: either log's status is not ``success``.
    :raises PairedLogMismatchError: the logs are not a valid Full/Null pair
        (including a detected skill invocation in the Null arm — control-arm
        contamination).
    :raises ZeroInvocationError: zero detected invocations in the Full arm.
    :raises AlreadyIngestedError: this pair of task ids was already written.
    :raises FileNotFoundError: ``skill_dir`` has no SKILL.md.
    """
    _validate_pair(full, null)

    pi_c = _pi_c_summary(full.samples)
    if pi_c.invocations == 0:
        raise ZeroInvocationError(
            f"INSTRUMENTATION FINDING — dead treated arm: 0 skill invocations "
            f"detected across {pi_c.trials} Full-arm epoch(s) "
            f"(pi_c_hat=0.00, {PI_C_CONFIDENCE:.0%} CI "
            f"[{pi_c.ci_low:.3f}, {pi_c.ci_high:.3f}], detector "
            f"{PI_C_DETECTOR_VERSION}). Refusing to produce an effect verdict: "
            f"'no effect' cannot be distinguished from 'never invoked'. This is "
            f"a delivery/instrumentation failure, not evidence about the "
            f"skill's effect.",
            pi_c=pi_c,
        )

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
        existing_metric = get_metric_version(conn, metric_id, ORACLE_METRIC_VERSION)
        if existing_metric is not None:
            # S88 K2 fail-closed re-check: the existence guard alone would let a
            # drifted module keep minting verdicts under a stale registered hash
            # (tamper-evidence blind spot — the hash is otherwise computed at
            # exactly one time, first insert). Raising here aborts the
            # transaction; nothing is written.
            live_hash = _oracle_implementation_hash()
            live_semantic = _oracle_semantic_digest()
            # #209: ask the SECOND question before refusing. A raw-byte mismatch
            # used to end in an unconditional raise, so editing a comment in this
            # module locked the identity permanently and the append-only row could
            # not be corrected. Now a drift whose AST identity digest is unchanged
            # is cleared by APPENDING a compensating restamp. Safeguard A is not
            # weakened: a behaviour change still refuses, and so does an identity
            # holding no digest to compare against.
            #
            # The comparison is delegated ENTIRELY to classify_implementation_drift
            # rather than pre-checked against the row's own hash. That row is
            # append-only and keeps its original hash forever, so after one restamp
            # the recorded hash and the live hash differ permanently while the
            # identity is settled -- pre-checking the recorded hash made every
            # later ingest refuse.
            verdict = classify_implementation_drift(
                conn,
                metric_id=metric_id,
                version=ORACLE_METRIC_VERSION,
                recorded_hash=existing_metric["implementation_hash"],
                live_hash=live_hash,
                live_semantic=live_semantic,
            )
            if verdict.is_current:
                # The hash in force matches, so the module on disk provably IS the
                # registered one and its identity digest is trustworthy. Recording
                # it here is the backfill that heals identities registered before
                # this repair existed: the first ingest after upgrading, BEFORE any
                # edit, gives the identity a digest, so a later comment edit is
                # repairable rather than terminal.
                record_semantic_digest(
                    conn,
                    metric_id=metric_id,
                    version=ORACLE_METRIC_VERSION,
                    implementation_hash=live_hash,
                    semantic=live_semantic,
                )
            elif verdict.restampable:
                append_implementation_restamp(conn, verdict)
            else:
                raise MetricImplementationDriftError(
                    f"metric_versions row ({metric_id!r}, {ORACLE_METRIC_VERSION!r}) pins "
                    f"implementation_hash {existing_metric['implementation_hash']}, but the "
                    f"live oracle module hashes to {live_hash} -- {verdict.reason}"
                )
        else:
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
            # Record the identity digest in the SAME transaction as the row it
            # describes, so the two can never disagree. A newly registered
            # identity is therefore repairable from its first ingest onward; the
            # backfill above exists for identities registered before this code.
            record_semantic_digest(
                conn,
                metric_id=metric_id,
                version=ORACLE_METRIC_VERSION,
                implementation_hash=_oracle_implementation_hash(),
                semantic=_oracle_semantic_digest(),
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
                        "pi_c": {"detector": PI_C_DETECTOR_VERSION, **pi_c.model_dump()},
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
            # #75/#81: every new mint goes through the guarded entrypoint.
            pin = _article_fingerprint_for_pair(full_by_epoch[epoch], null_by_epoch[epoch])
            mint_oracle_verdict(
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
                pin=pin,
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
        pi_c=pi_c,
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

    contaminated = sorted(s.epoch for s in null.samples if s.invoked_skill)
    if contaminated:
        raise PairedLogMismatchError(
            f"null log {null.task_name!r} carries detected skill invocation(s) in "
            f"epoch(s) {contaminated} — control-arm contamination. The Skill tool "
            f"is structurally not launchable in the Null arm (#46), so this means "
            f"mislabelled arms or a misconfigured harness: an apparatus error, "
            f"not evidence."
        )


def _pi_c_summary(samples: tuple[ParsedSample, ...]) -> PiCSummary:
    """π̂_c + Clopper-Pearson interval over the treated arm's parsed samples."""
    trials = len(samples)
    invocations = sum(1 for s in samples if s.invoked_skill)
    ci_low, ci_high = clopper_pearson(invocations, trials, confidence=PI_C_CONFIDENCE)
    return PiCSummary(
        invocations=invocations,
        trials=trials,
        pi_c_hat=invocations / trials,
        ci_low=ci_low,
        ci_high=ci_high,
        confidence=PI_C_CONFIDENCE,
    )


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


def _article_fingerprint_for_pair(
    full_sample: ParsedSample, null_sample: ParsedSample
) -> ArticleFingerprint:
    """Build the mandatory model pin for a newly-minted paired verdict (#75).

    Prefer ``model_snapshot`` from the measured subject model. When both arms
    lack a usable model id, fall back to a response fingerprint (sha256 of the
    Full-arm output) with ``requalify_on_drift=True``.
    """
    models = {full_sample.subject_model, null_sample.subject_model} - {None, ""}
    if len(models) == 1:
        return ArticleFingerprint(model_snapshot=next(iter(models)))
    if len(models) > 1 and full_sample.subject_model:
        # Prefer the Full arm's model as the pin when arms disagree — the
        # harness-pin admissibility path already flags cross-arm harness drift;
        # the article pin records what Full was measured on.
        return ArticleFingerprint(model_snapshot=full_sample.subject_model)
    output_fp = hashlib.sha256(full_sample.output_text.encode("utf-8")).hexdigest()
    return ArticleFingerprint(
        response_fingerprint=output_fp,
        requalify_on_drift=True,
    )


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
        score = float(value)
        if not math.isfinite(score):
            raise EvalLogIngestError(
                f"{path}: non-finite score value {value!r}. An absent measurement is not"
                " a tie: _observation scores it 0.5, which records no-effect evidence"
                " the trial never produced (#363)."
            )
        return score
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


def _oracle_semantic_digest() -> str:
    """AST-shape identity digest of this module -- the #209 second question.

    Deliberately NOT a replacement for ``_oracle_implementation_hash``. That stays
    the tamper detector over raw bytes; this answers *did the behaviour change?*,
    so that editing a comment no longer refuses every further verdict under an
    already-registered measurement identity.

    Read as TEXT rather than bytes, which normalises line endings: a Windows
    checkout must not mint a different measurement identity from a Linux one.
    Docstrings ARE identity-bearing -- see ``implementation_identity`` for why.

    :raises ImplementationIdentityError: this module does not parse. Callers treat
        that as a refusal, never as an absent digest.
    """
    return semantic_digest(Path(__file__).read_text(encoding="utf-8"))


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
