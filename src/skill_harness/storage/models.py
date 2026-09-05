"""Pydantic write-models for all evidence and runtime DB tables.

Design constraints (per A24 council finding):
- Every model uses ConfigDict(strict=True, extra='forbid', frozen=True).
- Per-model field_validator rejects NUL bytes and non-printable C0 control
  characters (Unicode category Cc / ASCII 0x00-0x1F), EXCEPT the three
  printable whitespace characters: \\t (0x09), \\n (0x0A), \\r (0x0D).
- Size caps are CONFIGURABLE CONSTANTS at module level, not hard-coded literals
  in each model. Python-layer enforcement; DB-layer deferred to D14.
- Write shapes only (Read shapes are Track E scope).
- Timestamp columns are TEXT (ISO 8601) matching the schema DEFAULT expressions.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

# ---------------------------------------------------------------------------
# Configurable size caps (bytes when UTF-8-encoded)
# ---------------------------------------------------------------------------

OUTPUT_TEXT_MAX_BYTES: int = 256 * 1024  # 256 KB — oracle_verdicts.output_text
CLAUSE_TEXT_MAX_BYTES: int = 64 * 1024  # 64 KB  — clauses.clause_text

# ---------------------------------------------------------------------------
# Task-frontier enumerated values (migration 0700)
# ---------------------------------------------------------------------------
# Defined HERE, not in `task_frontier/`, because the write model is the lowest
# layer that must know them and `storage` may not import upward. The
# `task_frontier` package re-exports these very objects as its public `Phase` /
# `Arm`, so the SQL CHECK, the write model and the seam enum are ONE definition
# rather than three that need a drift guard.


class TaskFrontierPhase(StrEnum):
    """The three walled-off phases. Values match migration 0700's CHECK literals."""

    CALIBRATION = "calibration"
    CONFIRMATION = "confirmation"
    MATCHED = "matched"


class TaskFrontierArm(StrEnum):
    """Which arm of the whole-skill contrast produced an observation."""

    FULL = "full"
    NULL = "null"


TASK_FRONTIER_PHASES: frozenset[str] = frozenset(member.value for member in TaskFrontierPhase)
TASK_FRONTIER_ARMS: frozenset[str] = frozenset(member.value for member in TaskFrontierArm)
TASK_FRONTIER_ADMISSIBILITY_STATES: frozenset[str] = frozenset({"admissible", "inadmissible"})

# ---------------------------------------------------------------------------
# Shared validator helpers
# ---------------------------------------------------------------------------

# Pre-compiled pattern: matches any C0 control char EXCEPT \t, \n, \r.
# C0 range is 0x00-0x1F; we exclude 0x09 (\t), 0x0A (\n), 0x0D (\r).
_FORBIDDEN_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _check_text(value: str, field_name: str = "value") -> str:
    """Reject NUL bytes and forbidden C0 control characters."""
    if _FORBIDDEN_CTRL.search(value):
        raise ValueError(
            f"{field_name}: contains forbidden control characters "
            "(NUL or C0 0x00-0x1F excluding \\t, \\n, \\r)"
        )
    return value


def _check_text_size(value: str, max_bytes: int, field_name: str = "value") -> str:
    """Reject strings whose UTF-8 encoding exceeds max_bytes."""
    encoded_len = len(value.encode("utf-8"))
    if encoded_len > max_bytes:
        raise ValueError(
            f"{field_name}: UTF-8 size {encoded_len} bytes exceeds cap of {max_bytes} bytes"
        )
    return value


# ---------------------------------------------------------------------------
# Evidence-side write models
# ---------------------------------------------------------------------------


class SkillWrite(BaseModel):
    """Insert shape for evidence.skills."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    skill_id: str
    name: str
    source_path: str
    source_sha256: str
    imported_at: str

    @field_validator("skill_id", "name", "source_path", "source_sha256", "imported_at")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


class ClauseWrite(BaseModel):
    """Insert shape for evidence.clauses."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    clause_id: str
    skill_id: str
    clause_index: int
    rendering_index: int
    clause_text: str
    axis: str
    comparator: str
    oracle_tier: int
    vacuity_flag: str
    falsifying_case_schema_sha256: str | None
    created_at: str

    @field_validator(
        "clause_id",
        "skill_id",
        "clause_text",
        "axis",
        "comparator",
        "vacuity_flag",
        "created_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("falsifying_case_schema_sha256", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "falsifying_case_schema_sha256")
        return v

    @field_validator("clause_text")
    @classmethod
    def clause_text_size_cap(cls, v: str) -> str:
        return _check_text_size(v, CLAUSE_TEXT_MAX_BYTES, "clause_text")


class MetricVersionWrite(BaseModel):
    """Insert shape for evidence.metric_versions."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    metric_id: str
    version: str
    implementation_hash: str
    tier: int
    audited: int
    mechanical_validity_test_passed: int
    registered_at: str

    @field_validator(
        "metric_id",
        "version",
        "implementation_hash",
        "registered_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


class JudgeWrite(BaseModel):
    """Insert shape for evidence.judges."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    judge_id: str
    model_id: str
    system_prompt_sha256: str
    created_at: str

    @field_validator("judge_id", "model_id", "system_prompt_sha256", "created_at")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


class CalibrationEventWrite(BaseModel):
    """Insert shape for evidence.calibration_events.

    Extended by Track C.3 (A37) with 10 new fields:
      STAT: n_a, n_b, n_tie (human-pref counts),
            judge_n_a, judge_n_b, judge_n_tie (judge verdict counts),
            length_regression_coefficient (β₁; None until C.4 fits regression),
            chance_baseline (p_e from κ formula)
      COST: total_usd_spent (C.4 fills via cost_ledger sum),
            cost_ledger_run_id (cross-DB pointer; nullable in v0.1)

    state enum per A37: 'calibrated' | 'conditional' | 'rejected' | 'expired'
                        | 'uncalibrated'
    Note: 'rejected' events (N<50) are never written to the DB — the command
    layer refuses to call this model for rejected events.  The value IS valid
    here so the orchestration layer can represent the outcome before deciding
    not to write.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    calibration_event_id: str
    judge_id: str
    axis: str
    pairwise_agreement: float
    position_consistency: float
    length_controlled_agreement: float | None
    cohen_kappa: float | None
    pair_set_size: int
    pair_set_sha256: str
    state: str
    expires_at: str | None
    validated_at: str

    # -----------------------------------------------------------------------
    # A37 — STAT extensions
    # -----------------------------------------------------------------------
    n_a: int | None  # human-pref A count
    n_b: int | None  # human-pref B count
    n_tie: int | None  # human-pref tie count
    judge_n_a: int | None  # judge verdict A count
    judge_n_b: int | None  # judge verdict B count
    judge_n_tie: int | None  # judge verdict tie count
    length_regression_coefficient: float | None  # β₁; None until C.4 fits OLS
    chance_baseline: float | None  # p_e from κ formula; None until computed

    # -----------------------------------------------------------------------
    # A37 — COST extensions
    # -----------------------------------------------------------------------
    total_usd_spent: float  # 0.0 until C.4 cost ledger sums
    cost_ledger_run_id: str | None  # cross-DB pointer; nullable in v0.1

    @field_validator(
        "calibration_event_id",
        "judge_id",
        "axis",
        "pair_set_sha256",
        "state",
        "validated_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("expires_at", "cost_ledger_run_id", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: object) -> object:
        if isinstance(v, str):
            field_name = getattr(info, "field_name", "field") if info else "field"
            return _check_text(v, field_name)
        return v


class RunWrite(BaseModel):
    """Insert shape for evidence.runs."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    run_id: str
    skill_id: str
    run_kind: str
    config_json: str
    started_at: str
    completed_at: str | None

    @field_validator("run_id", "skill_id", "run_kind", "config_json", "started_at")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("completed_at", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "completed_at")
        return v


class SampleWrite(BaseModel):
    """Insert shape for evidence.samples.

    Migration 0300 (Track D, A40) added:
    - ``sample_index`` — positional key for idempotency + resume.
      ``UNIQUE(run_id, clause_id, condition, sample_index)`` prevents double-counting
      w/n in the Beta-Binomial on crash-resume. Default 0 for backward compat with
      tests that insert a single sample per (run_id, clause_id, condition) tuple.
    - Per-call cost columns (A41): ``input_tokens``, ``cache_read_input_tokens``,
      ``cache_creation_input_tokens``, ``output_tokens``, ``usd``. All optional
      (None for non-API-generating rows and pre-migration rows).

    Migration 0500 (v0.2 subject layer) added:
    - ``harness_pin_json`` / ``harness_pin_fingerprint`` — the subject-harness
      configuration recorded per trial (pre-reg "Harness pin" row). None for
      non-agentic rows; cross-arm fingerprint equality is checked at write time
      by ``skill_harness.subject.ingest``.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    sample_id: str
    run_id: str
    clause_id: str
    condition: str
    subject_model: str
    subject_seed: str | None
    output_text: str
    output_sha256: str
    sampled_at: str

    # A40 — idempotency key (migration 0300)
    sample_index: int = 0

    # A41 — per-call cost columns (migration 0300); None for non-API rows
    input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    output_tokens: int | None = None
    usd: float | None = None

    # v0.2 — harness-pin fields (migration 0500); None for non-agentic rows
    harness_pin_json: str | None = None
    harness_pin_fingerprint: str | None = None

    @field_validator(
        "sample_id",
        "run_id",
        "clause_id",
        "condition",
        "subject_model",
        "output_sha256",
        "sampled_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("subject_seed", "harness_pin_json", "harness_pin_fingerprint", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v

    @field_validator("output_text")
    @classmethod
    def output_text_size_cap(cls, v: str) -> str:
        return _check_text_size(v, OUTPUT_TEXT_MAX_BYTES, "output_text")


class OracleVerdictWrite(BaseModel):
    """Insert shape for evidence.oracle_verdicts.

    Model-pin columns (migration 0600 / #75) are optional on the write shape so
    historical and test fixtures may omit them. New mints MUST go through
    ``mint_oracle_verdict`` with an ``ArticleFingerprint`` (#81) — see
    ``skill_harness.storage.repositories.evidence.oracle_verdicts``.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    verdict_id: str
    run_id: str
    clause_id: str
    axis: str
    comparison: str
    sample_a_id: str
    sample_b_id: str
    observation: float
    oracle_tier: int
    metric_id: str | None
    metric_version: str | None
    judge_id: str | None
    calibration_event_id: str | None
    position_swap_agreement: int | None
    admissibility_state: str
    inadmissibility_reason: str | None
    written_at: str
    # 0600 — model pin + drift fingerprint (nullable: no retrofit of historical)
    model_snapshot: str | None = None
    response_fingerprint: str | None = None
    requalify_on_drift: int = 0
    drift_fingerprint: str | None = None

    @field_validator(
        "verdict_id",
        "run_id",
        "clause_id",
        "axis",
        "comparison",
        "sample_a_id",
        "sample_b_id",
        "admissibility_state",
        "written_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator(
        "metric_id",
        "metric_version",
        "judge_id",
        "calibration_event_id",
        "inadmissibility_reason",
        "model_snapshot",
        "response_fingerprint",
        "drift_fingerprint",
        mode="before",
    )
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v


class ConfoundEventWrite(BaseModel):
    """Insert shape for evidence.confound_events."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    confound_event_id: str
    run_id: str
    primary_clause_id: str
    affected_clause_id: str | None
    axis: str
    delta: float
    null_sigma: float
    k_threshold: float
    delta_kind: str
    detected_at: str

    @field_validator(
        "confound_event_id",
        "run_id",
        "primary_clause_id",
        "axis",
        "delta_kind",
        "detected_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("affected_clause_id", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "affected_clause_id")
        return v


class FrozenCaseWrite(BaseModel):
    """Insert shape for evidence.frozen_cases.

    Extended by Track E.1 (A56) with three new fields:
      verdict_id        -- FK to oracle_verdicts (nullable for legacy rows)
      run_id            -- FK to runs (nullable for legacy rows)
      axis              -- axis-specific frozen case (nullable for legacy rows)
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    frozen_case_id: str
    clause_id: str
    failing_input_text: str
    failing_input_sha256: str
    oracle_source: str
    labeled_by: str | None
    labeled_at: str | None
    metric_id: str | None
    metric_version: str | None
    implementation_hash: str | None
    frozen_at: str

    # A56 — provenance extensions (migration 0400)
    verdict_id: str | None = None
    run_id: str | None = None
    axis: str | None = None

    @field_validator(
        "frozen_case_id",
        "clause_id",
        "failing_input_sha256",
        "oracle_source",
        "frozen_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator(
        "labeled_by",
        "labeled_at",
        "metric_id",
        "metric_version",
        "implementation_hash",
        "verdict_id",
        "run_id",
        "axis",
        mode="before",
    )
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v

    @field_validator("failing_input_text")
    @classmethod
    def no_control_chars_input(cls, v: str) -> str:
        # failing_input_text may legitimately contain any content; still reject
        # C0 control bytes that would corrupt storage.
        return _check_text(v, "failing_input_text")


# ---------------------------------------------------------------------------
# Runtime-side write models
# ---------------------------------------------------------------------------


class SkillImportsStagingWrite(BaseModel):
    """Insert shape for runtime.skill_imports_staging."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    staging_id: str
    source_path: str
    state: str
    notes: str | None
    updated_at: str

    @field_validator("staging_id", "source_path", "state", "updated_at")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("notes", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "notes")
        return v


class RunProgressWrite(BaseModel):
    """Insert shape for runtime.run_progress."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    run_id: str
    state: str
    samples_planned: int
    samples_collected: int
    last_heartbeat: str
    error: str | None

    @field_validator("run_id", "state", "last_heartbeat")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("error", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "error")
        return v


class CurrentCalibrationWrite(BaseModel):
    """Insert/upsert shape for runtime.current_calibration."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    judge_id: str
    axis: str
    calibration_event_id: str
    state: str
    expires_at: str | None
    updated_at: str

    @field_validator("judge_id", "axis", "calibration_event_id", "state", "updated_at")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("expires_at", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "expires_at")
        return v


class RunBudgetWrite(BaseModel):
    """Insert shape for runtime.run_budget."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    run_id: str
    hard_cap_usd: float
    tokens_spent_in: int
    tokens_spent_out: int
    cache_write_in: int
    cache_read_in: int
    usd_spent: float
    dry_run: int
    aborted_at: str | None
    last_updated: str

    @field_validator("run_id", "last_updated")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("aborted_at", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object) -> object:
        if isinstance(v, str):
            return _check_text(v, "aborted_at")
        return v


class CostLedgerWrite(BaseModel):
    """Insert shape for runtime.cost_ledger (ledger_id is AUTOINCREMENT — omit on insert)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ts: str
    run_id: str | None
    skill_id: str | None
    model_id: str
    call_kind: str
    input_tok: int
    cache_write_tok: int
    cache_read_tok: int
    output_tok: int
    usd: float

    @field_validator("ts", "model_id", "call_kind")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("run_id", "skill_id", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v


# ---------------------------------------------------------------------------
# Screen store (migration 0501) — Stage-0 Null-only screens, firewalled from
# the paired evidence model (pre-reg: "screen data never enters verdicts").
# Keyed by skill_name; no FK into skills/runs. p0 is derived from admissible
# trials, never stored.
# ---------------------------------------------------------------------------


# Coded D4 status on screen_runs (migration 1000). Required on every write —
# no Python default, so omission is a type error rather than a silent
# unknown_legacy (the SQLite column default, reserved for pre-migration rows).
D4_CHECK_STATES = frozenset({"unknown_legacy", "not_applicable", "ran_clean", "ran_flagged"})
D4CheckState = Literal["unknown_legacy", "not_applicable", "ran_clean", "ran_flagged"]


class ScreenRunWrite(BaseModel):
    """Insert shape for evidence.screen_runs (migrations 0501 + 1000)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    screen_run_id: str
    skill_name: str
    subject_model: str
    harness_pin_fingerprint: str | None
    source_eval_task_id: str
    source_eval_sha256: str
    admissibility_state: str
    inadmissibility_reason: str | None
    d4_check_state: D4CheckState
    created_at: str
    ingested_at: str

    @field_validator(
        "screen_run_id",
        "skill_name",
        "subject_model",
        "source_eval_task_id",
        "source_eval_sha256",
        "admissibility_state",
        "d4_check_state",
        "created_at",
        "ingested_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("d4_check_state")
    @classmethod
    def known_d4_check_state(cls, v: str) -> str:
        if v not in D4_CHECK_STATES:
            raise ValueError(f"d4_check_state must be one of {sorted(D4_CHECK_STATES)}; got {v!r}")
        return v

    @field_validator("harness_pin_fingerprint", "inadmissibility_reason", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v


class ScreenTrialWrite(BaseModel):
    """Insert shape for evidence.screen_trials (migration 0501)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    screen_trial_id: str
    screen_run_id: str
    epoch: int
    passed: int  # 1 = null arm passed the task, 0 = failed
    scorer_name: str
    scorer_explanation: str | None
    output_sha256: str
    sampled_at: str

    @field_validator(
        "screen_trial_id", "screen_run_id", "scorer_name", "output_sha256", "sampled_at"
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("scorer_explanation", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v


class ScreenRunSupersessionWrite(BaseModel):
    """Insert shape for evidence.screen_run_supersessions (migration 0900)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    superseded_screen_run_id: str
    superseding_screen_run_id: str
    reason: str

    @field_validator("superseded_screen_run_id", "superseding_screen_run_id", "reason")
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)


class TaskFrontierObservationWrite(BaseModel):
    """Insert shape for the three task-frontier phase partitions (migration 0700).

    ONE write shape, THREE physical tables: `phase` selects the partition at
    write time (see `repositories.evidence.task_frontier.PHASE_TABLES`). The
    column is CHECK-pinned per table, so this model's `phase` validator and the
    SQL CHECK are two independent guards on the same invariant — a mis-routed
    row is refused by whichever fires first.

    Refusal over coercion (the `two_arm_gate` / `oc` convention): an unknown
    phase, arm or evidence-admissibility state raises rather than being normalised.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    observation_id: str
    task_family_id: str
    task_family_version: str
    semantic_lineage_id: str
    phase: str
    instance_id: str
    arm: str
    passed: int  # 1 = this arm passed the task instance, 0 = failed
    generator_fingerprint: str
    oracle_fingerprint: str
    admissibility_state: str
    inadmissibility_reason: str | None
    observed_at: str
    ingested_at: str

    @field_validator(
        "observation_id",
        "task_family_id",
        "task_family_version",
        "semantic_lineage_id",
        "phase",
        "instance_id",
        "arm",
        "generator_fingerprint",
        "oracle_fingerprint",
        "admissibility_state",
        "observed_at",
        "ingested_at",
    )
    @classmethod
    def no_control_chars(cls, v: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field") if info else "field"
        return _check_text(v, field_name)

    @field_validator("inadmissibility_reason", mode="before")
    @classmethod
    def no_control_chars_optional(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str):
            return _check_text(v, info.field_name or "field")
        return v

    @field_validator("phase")
    @classmethod
    def known_phase(cls, v: str) -> str:
        if v not in TASK_FRONTIER_PHASES:
            raise ValueError(
                f"phase must be one of {sorted(TASK_FRONTIER_PHASES)} — each names its own "
                f"physical partition and there is no catch-all table; got {v!r}"
            )
        return v

    @field_validator("arm")
    @classmethod
    def known_arm(cls, v: str) -> str:
        if v not in TASK_FRONTIER_ARMS:
            raise ValueError(
                f"arm must be one of {sorted(TASK_FRONTIER_ARMS)} — the frontier measures the "
                f"whole-skill Full-vs-Null contrast, not clause ablation; got {v!r}"
            )
        return v

    @field_validator("admissibility_state")
    @classmethod
    def known_admissibility_state(cls, v: str) -> str:
        if v not in TASK_FRONTIER_ADMISSIBILITY_STATES:
            raise ValueError(
                f"admissibility_state must be one of "
                f"{sorted(TASK_FRONTIER_ADMISSIBILITY_STATES)}; got {v!r}"
            )
        return v

    @field_validator("passed")
    @classmethod
    def passed_is_a_bit(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError(f"passed must be 0 or 1; got {v}")
        return v
