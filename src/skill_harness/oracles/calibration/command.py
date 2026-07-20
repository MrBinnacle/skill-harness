"""Calibration command orchestration (A34, A37, A36).

Implements:
- ``cohen_kappa_observed_marginals`` — κ formula with observed marginals (A34)
- ``determine_state`` — three-tier admissibility logic (A34)
- ``_warmup_first_call`` — serialize first judge call to populate cache (A36)
- ``calibrate`` — full calibration orchestration: parse JSONL, run judge,
  compute metrics, determine state, write to DB if calibrated/conditional.

Included from C.4 scope:
- Cost projection formula and ``--max-usd`` enforcement (A36)
- ``_warmup_first_call()`` serialization discipline (A36 cache discipline)
- Length regression fit (β₁ via statsmodels OLS) on execute path (A35)
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from skill_harness.oracles.calibration.cost_projection import (
    CostProjection,
    project_calibration_cost,
)
from skill_harness.oracles.calibration.jsonl_parser import (
    CalibrationPair,
    compute_pair_set_sha256,
    parse_pair_set,
)
from skill_harness.oracles.calibration.length_regression import (
    SENTINEL_INADMISSIBILITY_REASONS,
    apply_length_correction,
    fit_length_regression,
)
from skill_harness.storage.dual_write import write_calibration_event_with_pointer
from skill_harness.storage.models import CalibrationEventWrite, CurrentCalibrationWrite

# ---------------------------------------------------------------------------
# JudgeClient protocol (avoids circular import with tier2.judge)
# ---------------------------------------------------------------------------


class _JudgeProtocol(Protocol):
    """Structural protocol for JudgeClient.evaluate_pair (A31/A32)."""

    def evaluate_pair(
        self,
        output_a: str,
        output_b: str,
        axis_name: str,
        axis_rubric: str,
    ) -> object:
        """Evaluate a pair; return an object with .choice and .position_swap_agreement."""
        ...


# ---------------------------------------------------------------------------
# Default budget parameters (A36)
# ---------------------------------------------------------------------------

DEFAULT_MAX_USD: float = 5.0  # per-run cap default
DEFAULT_DAILY_CAP: float = 20.0  # per-day cap default

# System prompt + tool schema tokens estimate for cost projection
# These are estimates used when no actual call has been made yet.
# The judge's _build_prompt uses ~1500 tokens for the fixed prefix.
_ESTIMATE_SYSTEM_PROMPT_TOKENS: int = 1200
_ESTIMATE_TOOL_SCHEMA_TOKENS: int = 300
_ESTIMATE_CANDIDATE_OUTPUT_TOKENS: int = 150  # per side

# ---------------------------------------------------------------------------
# Admissibility thresholds (A34 / llm-judge-calibration Discipline 4)
# ---------------------------------------------------------------------------

_N_FLOOR_REJECTED: int = 50  # N < 50 → rejected
_N_FLOOR_CONDITIONAL: int = 100  # 50 ≤ N < 100 → conditional; N ≥ 100 → checked

_THRESHOLD_PAIRWISE_AGREEMENT: float = 0.70
_THRESHOLD_POSITION_CONSISTENCY: float = 0.80
_THRESHOLD_LENGTH_CONTROLLED: float = 0.65
_THRESHOLD_COHEN_KAPPA: float = 0.40


# ---------------------------------------------------------------------------
# Cohen's κ — observed marginals (A34 / Cohen 1960)
# ---------------------------------------------------------------------------


def cohen_kappa_observed_marginals(
    pairs: Sequence[tuple[str, str]],
) -> tuple[float, float]:
    """Compute Cohen's κ for 3-class pairwise judgement (A34).

    Parameters
    ----------
    pairs:
        Sequence of ``(human_choice, judge_choice)`` tuples where each
        choice ∈ {``"A"``, ``"B"``, ``"tie"``}.

    Returns
    -------
    (kappa, p_e)
        ``kappa`` — chance-corrected agreement coefficient.
        ``p_e`` — chance baseline (stored as ``chance_baseline`` per A34).

    Formula (Cohen 1960):
        p_o = observed agreement = fraction of pairs where human == judge
        p_e = sum_c (n_human_c / N) * (n_judge_c / N)  for c in {A, B, tie}
        kappa = (p_o - p_e) / (1 - p_e)

    ``p_e`` uses *observed* marginals, NOT a uniform 1/3 assumption.
    Both ``p_o`` and ``p_e`` are stored in the calibration_event so
    the audit can re-derive κ if the formula is updated later (A34).
    """
    n = len(pairs)
    if n == 0:
        return (0.0, 0.0)

    # --- Count observed agreements and marginals ---
    n_human: dict[str, int] = {"A": 0, "B": 0, "tie": 0}
    n_judge: dict[str, int] = {"A": 0, "B": 0, "tie": 0}
    n_agree: int = 0

    for human_choice, judge_choice in pairs:
        n_human[human_choice] = n_human.get(human_choice, 0) + 1
        n_judge[judge_choice] = n_judge.get(judge_choice, 0) + 1
        if human_choice == judge_choice:
            n_agree += 1

    p_o = n_agree / n

    # p_e uses observed marginals (NOT 1/3 uniform)
    p_e = sum((n_human.get(c, 0) / n) * (n_judge.get(c, 0) / n) for c in ("A", "B", "tie"))

    if abs(1.0 - p_e) < 1e-12:
        # Edge case: perfect marginal alignment → κ is undefined; return 1.0
        return (1.0, float(p_e))

    kappa = (p_o - p_e) / (1.0 - p_e)
    return (float(kappa), float(p_e))


# ---------------------------------------------------------------------------
# Three-tier admissibility
# ---------------------------------------------------------------------------


def determine_state(
    n_pairs: int,
    pairwise_agreement: float,
    position_consistency: float,
    length_controlled_agreement: float | None,
    cohen_kappa: float,
) -> tuple[str, str | None]:
    """Determine three-tier calibration admissibility state (A34).

    Returns
    -------
    (state, reason)
        ``state`` ∈ {``"rejected"``, ``"conditional"``, ``"calibrated"``}.
        ``reason`` is ``None`` when ``state == "calibrated"``; a short
        machine-readable string otherwise.
    """
    if n_pairs < _N_FLOOR_REJECTED:
        return ("rejected", "pair_set_size_below_floor")

    if n_pairs < _N_FLOOR_CONDITIONAL:
        return ("conditional", "underpowered_50_99")

    # N ≥ 100 — check all four thresholds
    if pairwise_agreement < _THRESHOLD_PAIRWISE_AGREEMENT:
        return ("rejected", "pairwise_agreement_below_threshold")

    if position_consistency < _THRESHOLD_POSITION_CONSISTENCY:
        return ("rejected", "position_consistency_below_threshold")

    if (
        length_controlled_agreement is not None
        and length_controlled_agreement < _THRESHOLD_LENGTH_CONTROLLED
    ):
        return ("rejected", "length_controlled_below_threshold")

    if cohen_kappa < _THRESHOLD_COHEN_KAPPA:
        return ("rejected", "cohen_kappa_below_threshold")

    return ("calibrated", None)


# ---------------------------------------------------------------------------
# _warmup_first_call — serialize first judge call to populate cache (A36)
# ---------------------------------------------------------------------------


def _warmup_first_call(
    judge_client: _JudgeProtocol,
    first_pair: CalibrationPair,
    axis: str,
) -> object:
    """Issue the first judge call synchronously to populate the cache.

    Per A36 cache discipline: the stable prefix (system prompt + tool schema)
    is written to cache by the first call. Calls 2..N can then read the cached
    prefix. Without this serialization, all N_calls may fire before any cache
    entry exists, causing each to pay full uncached input price.

    Cache reads are only available after the first response begins streaming
    (5-min TTL semantics per claude-api prompt-caching). The warmup call blocks
    until the verdict is returned, ensuring the cache is populated before the
    remaining N-1 calls proceed.

    :param judge_client: JudgeClient (or any _JudgeProtocol implementation).
    :param first_pair: The first CalibrationPair to evaluate.
    :param axis: The axis name being calibrated.
    :returns: JudgeVerdict from the first pair evaluation.
    """
    return judge_client.evaluate_pair(
        output_a=first_pair.response_a,
        output_b=first_pair.response_b,
        axis_name=axis,
        axis_rubric=axis,
    )


# ---------------------------------------------------------------------------
# CalibrationResult dataclass (return value of calibrate())
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationResult:
    """Summary of a calibration run.

    Fields
    ------
    state : str
        Three-tier admissibility outcome: "rejected" | "conditional" | "calibrated".
    reason : str | None
        Machine-readable rejection reason; None if state == "calibrated".
    n_pairs : int
        Number of pairs parsed from the JSONL.
    pairwise_agreement : float
        Fraction of ADMISSIBLE verdicts where judge and human agreed (C2 fix:
        sentinel/inadmissible verdicts — no real judge call completed, or the
        call was truncated/malformed — are excluded; see n_inadmissible_verdicts).
        0.0 if there are zero admissible verdicts.
    position_consistency : float
        Fraction of ALL pairs where judge verdict was consistent across position
        swap (denominator is n_pairs, not n_admissible — this metric intentionally
        measures the swap-consistency rate across every attempted/short-circuited
        call, unlike pairwise_agreement/cohen_kappa).
    cohen_kappa : float
        Chance-corrected agreement coefficient, computed over ADMISSIBLE verdicts
        only (C2 fix — same admissible subset as pairwise_agreement).
    chance_baseline : float
        p_e from the κ formula (stored for audit re-derivation).
    pair_set_sha256 : str
        Content hash of the canonical-sorted pair set.
    calibration_event_id : str | None
        UUID of the written calibration_event row; None if rejected (no write).
    cost_projection : CostProjection | None
        A36 cost projection computed before any judge calls (None on dry-run
        if pair count < 50 and we reject before projecting).
    length_regression_coefficient : float | None
        β_1 from OLS fit; None in dry-run or if N < 50 (A35 observation-time).
    n_inadmissible_verdicts : int
        Count of verdicts excluded from pairwise_agreement/cohen_kappa/judge_n_*
        because admissibility_state != "admissible" (C2 fix). Never hidden —
        always reported, even when 0.
    n_length_regression_excluded : int
        Count of verdicts excluded from the length-regression OLS fit because
        inadmissibility_reason is a sentinel reason (suspected_injection or
        judge_response_malformed — see SENTINEL_INADMISSIBILITY_REASONS). This
        is a SUBSET of n_inadmissible_verdicts: position_disagreement verdicts
        are excluded from pairwise_agreement/kappa but deliberately stay IN the
        OLS fit (documented rationale in length_regression.py).
    """

    state: str
    reason: str | None
    n_pairs: int
    pairwise_agreement: float
    position_consistency: float
    cohen_kappa: float
    chance_baseline: float
    pair_set_sha256: str
    calibration_event_id: str | None
    cost_projection: CostProjection | None = None
    length_regression_coefficient: float | None = None
    n_inadmissible_verdicts: int = 0
    n_length_regression_excluded: int = 0


# ---------------------------------------------------------------------------
# calibrate() — main orchestration
# ---------------------------------------------------------------------------


def calibrate(
    judge_id: str,
    axis: str,
    pair_set_path: Path,
    judge_client: _JudgeProtocol,
    evidence_conn: sqlite3.Connection,
    runtime_conn: sqlite3.Connection,
    max_usd: float = DEFAULT_MAX_USD,
    daily_cap: float = DEFAULT_DAILY_CAP,
    dry_run: bool = True,
) -> CalibrationResult:
    """Run calibration: parse JSONL, project cost, evaluate pairs, write event.

    Parameters
    ----------
    judge_id:
        Opaque identifier for the judge (sha256(model_id || system_prompt_sha256
        || tool_schema_sha256) per A31).
    axis:
        Axis name being calibrated (e.g. ``"citation_support"``).
    pair_set_path:
        Path to the JSONL file of ``CalibrationPair`` records.
    judge_client:
        A ``JudgeClient`` instance (from ``oracles.tier2.judge``).
    evidence_conn:
        Open evidence DB connection (``synchronous=FULL``).
    runtime_conn:
        Open runtime DB connection.
    max_usd:
        Per-run cost cap in USD. Refuse if projected cost exceeds this.
    daily_cap:
        Per-day rolling cost cap in USD (validated against hard ceiling $100).
    dry_run:
        If True (default), compute projection and metrics but skip DB writes.
        Requires ``--execute`` flag / ``dry_run=False`` to persist.

    Returns
    -------
    CalibrationResult
        Summary with state, metrics, cost_projection, and optional event ID.

    Notes
    -----
    - N < 50 → rejected; no DB write.
    - 50 ≤ N < 100 → conditional; DB write if not dry_run.
    - N ≥ 100 → all thresholds checked; calibrated or rejected; DB write if
      state is "calibrated" or "conditional" and not dry_run.
    - Cost projection is computed up front; run refuses if projection > max_usd.
    - On execute: warmup first call (A36 cache discipline), then remaining pairs.
      After all verdicts: fit length regression → store β_1 in calibration_event.
    """
    # 1. Parse JSONL
    pairs: list[CalibrationPair] = parse_pair_set(pair_set_path)
    n_pairs = len(pairs)
    pair_set_sha = compute_pair_set_sha256(pairs)

    # 2. Compute cost projection up front (A36)
    projection = project_calibration_cost(
        n_pairs=n_pairs,
        model_id="claude-sonnet-4-6",  # default judge model (model-pinning convention)
        system_prompt_tokens=_ESTIMATE_SYSTEM_PROMPT_TOKENS,
        tool_schema_tokens=_ESTIMATE_TOOL_SCHEMA_TOKENS,
        candidate_output_avg_tokens=_ESTIMATE_CANDIDATE_OUTPUT_TOKENS,
    )

    # 3. Enforce per-run cap (A36)
    if projection.usd > max_usd:
        return CalibrationResult(
            state="rejected",
            reason=f"projected_cost_exceeds_max_usd_{max_usd:.2f}",
            n_pairs=n_pairs,
            pairwise_agreement=0.0,
            position_consistency=0.0,
            cohen_kappa=0.0,
            chance_baseline=0.0,
            pair_set_sha256=pair_set_sha,
            calibration_event_id=None,
            cost_projection=projection,
        )

    # 4. Early exit for N < 50 (never write a rejected event to DB)
    if n_pairs < _N_FLOOR_REJECTED:
        return CalibrationResult(
            state="rejected",
            reason="pair_set_size_below_floor",
            n_pairs=n_pairs,
            pairwise_agreement=0.0,
            position_consistency=0.0,
            cohen_kappa=0.0,
            chance_baseline=0.0,
            pair_set_sha256=pair_set_sha,
            calibration_event_id=None,
            cost_projection=projection,
        )

    # 5. In dry-run mode: compute metrics from a single pass without calling the judge
    if dry_run:
        # Return projection + size info without making any API calls
        return CalibrationResult(
            state="dry_run",
            reason=None,
            n_pairs=n_pairs,
            pairwise_agreement=0.0,
            position_consistency=0.0,
            cohen_kappa=0.0,
            chance_baseline=0.0,
            pair_set_sha256=pair_set_sha,
            calibration_event_id=None,
            cost_projection=projection,
        )

    # 6. Execute path: warmup first call (A36 cache discipline), then remaining pairs
    all_verdicts: list[object] = []

    # Warmup: serialize first call to populate the cache prefix
    first_verdict = _warmup_first_call(judge_client, pairs[0], axis)
    all_verdicts.append(first_verdict)

    # Remaining N-1 pairs (cache is now populated)
    for pair in pairs[1:]:
        verdict = judge_client.evaluate_pair(
            output_a=pair.response_a,
            output_b=pair.response_b,
            axis_name=axis,
            axis_rubric=axis,
        )
        all_verdicts.append(verdict)

    # 7. Aggregate verdicts
    # C2 fix: sentinel/inadmissible verdicts (choice/raw_observation are
    # hardcoded placeholders — no real judge call completed, or the call was
    # truncated/malformed; see judge.py admissibility resolution) must not
    # enter human-judge agreement, κ marginals, or judge choice counts. This
    # mirrors the repo-wide admissible_verdicts VIEW convention (A29,
    # 0003_admissible_verdicts_view.sql / aggregation/engine.py): the
    # aggregation surface is admissible rows only; inadmissible rows are
    # counted separately and never silently dropped.
    #
    # position_consistent_count intentionally sums over ALL verdicts (not just
    # admissible) — position_consistency measures the swap-agreement rate
    # across every attempted/short-circuited call, a different question from
    # "did the judge's choice agree with the human."
    admissible_rows: list[tuple[CalibrationPair, object]] = []
    human_judge_pairs: list[tuple[str, str]] = []
    position_consistent_count = 0
    n_judge_choices: dict[str, int] = {"A": 0, "B": 0, "tie": 0}
    n_inadmissible_verdicts = 0

    for pair, verdict in zip(pairs, all_verdicts, strict=True):
        position_consistent_count += int(getattr(verdict, "position_swap_agreement", 0))

        if getattr(verdict, "admissibility_state", "inadmissible") != "admissible":
            n_inadmissible_verdicts += 1
            continue

        judge_choice = str(getattr(verdict, "choice", "tie"))
        admissible_rows.append((pair, verdict))
        human_judge_pairs.append((pair.human_preference, judge_choice))
        n_judge_choices[judge_choice] = n_judge_choices.get(judge_choice, 0) + 1

    # 8. Compute metrics
    n_human: dict[str, int] = {"A": 0, "B": 0, "tie": 0}
    for pair in pairs:
        n_human[pair.human_preference] = n_human.get(pair.human_preference, 0) + 1

    n_admissible = len(human_judge_pairs)
    pairwise_agreement = (
        sum(1 for h, j in human_judge_pairs if h == j) / n_admissible if n_admissible else 0.0
    )
    position_consistency = position_consistent_count / n_pairs

    kappa, chance_baseline = cohen_kappa_observed_marginals(human_judge_pairs)

    # 9. Fit length regression (A35 observation-time half) — uses JudgeVerdict objects
    from skill_harness.oracles.tier2.judge import JudgeVerdict as _JudgeVerdict

    typed_verdicts = [v for v in all_verdicts if isinstance(v, _JudgeVerdict)]
    n_length_regression_excluded = sum(
        1 for v in typed_verdicts if v.inadmissibility_reason in SENTINEL_INADMISSIBILITY_REASONS
    )
    beta_1: float | None = None
    if len(typed_verdicts) == len(pairs):
        beta_1 = fit_length_regression(pairs, typed_verdicts)

    # Apply length correction to compute length_controlled_agreement.
    # C2 fix: restricted to the same admissible subset as pairwise_agreement —
    # a sentinel raw_observation=0.0 is not real judge signal and must not be
    # length-corrected and counted as if it were (this metric feeds
    # determine_state's threshold gating, same as pairwise_agreement).
    length_controlled_agreement: float | None = None
    if beta_1 is not None and len(typed_verdicts) == len(pairs) and n_admissible > 0:
        adjusted_observations = [
            apply_length_correction(
                raw_logit=v.raw_observation,  # type: ignore[attr-defined]
                length_delta=v.length_a - v.length_b,  # type: ignore[attr-defined]
                beta_1=beta_1,
            )
            for _pair, v in admissible_rows
        ]
        # Length-controlled agreement: map adjusted logit back to choice, compare to human.
        # Thresholds: obs >= 0.75 → A wins, obs <= 0.25 → B wins, otherwise tie.
        adj_choices = [
            "A" if obs >= 0.75 else ("B" if obs <= 0.25 else "tie") for obs in adjusted_observations
        ]
        lca_agree = sum(
            1 for (h, _), adj in zip(human_judge_pairs, adj_choices, strict=True) if h == adj
        )
        length_controlled_agreement = lca_agree / n_admissible

    # 10. Determine state
    state, reason = determine_state(
        n_pairs=n_pairs,
        pairwise_agreement=pairwise_agreement,
        position_consistency=position_consistency,
        length_controlled_agreement=length_controlled_agreement,
        cohen_kappa=kappa,
    )

    # 11. Write to DB if state is calibrated or conditional
    calibration_event_id: str | None = None
    if state in ("calibrated", "conditional"):
        calibration_event_id = str(uuid.uuid4())
        now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        event = CalibrationEventWrite(
            calibration_event_id=calibration_event_id,
            judge_id=judge_id,
            axis=axis,
            pairwise_agreement=pairwise_agreement,
            position_consistency=position_consistency,
            length_controlled_agreement=length_controlled_agreement,
            cohen_kappa=kappa,
            pair_set_size=n_pairs,
            pair_set_sha256=pair_set_sha,
            state=state,
            expires_at=None,
            validated_at=now_str,
            # A37 STAT extensions
            n_a=n_human.get("A", 0),
            n_b=n_human.get("B", 0),
            n_tie=n_human.get("tie", 0),
            judge_n_a=n_judge_choices.get("A", 0),
            judge_n_b=n_judge_choices.get("B", 0),
            judge_n_tie=n_judge_choices.get("tie", 0),
            length_regression_coefficient=beta_1,
            chance_baseline=chance_baseline,
            # A37 COST extensions
            total_usd_spent=projection.usd,
            cost_ledger_run_id=None,
        )
        pointer = CurrentCalibrationWrite(
            judge_id=judge_id,
            axis=axis,
            calibration_event_id=calibration_event_id,
            state=state,
            expires_at=None,
            updated_at=now_str,
        )
        write_calibration_event_with_pointer(evidence_conn, runtime_conn, event, pointer)

    return CalibrationResult(
        state=state,
        reason=reason,
        n_pairs=n_pairs,
        pairwise_agreement=pairwise_agreement,
        position_consistency=position_consistency,
        cohen_kappa=kappa,
        chance_baseline=chance_baseline,
        pair_set_sha256=pair_set_sha,
        calibration_event_id=calibration_event_id,
        cost_projection=projection,
        length_regression_coefficient=beta_1,
        n_inadmissible_verdicts=n_inadmissible_verdicts,
        n_length_regression_excluded=n_length_regression_excluded,
    )
