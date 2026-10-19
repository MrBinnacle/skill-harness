"""Confound monitoring for ablation runs (A11, A45, A46, A47).

Design:
- Score every sample on ALL registered metric_library axes in-memory.
- sigma(Null) estimated per (run, axis) at write-time from accumulated Null scores.
- N_null >= 30 floor: if fewer Null samples, confound detection is disabled for that axis.
- k = 2.0: emit a confound_events row ONLY when |delta| > k * sigma_Null.
- Threshold-triggered only -- NO dense per-sample x axis table (A47).
- Uncalibrated Tier-2 axes excluded from sigma(Null).
- Write-side assertion: primary_clause_id == ablated_clause_id (A46).

delta_kind values (A11):
  - 'confound_flagged': movement on a claimed-but-other-clause axis (taints primary verdict)
  - 'observed_unclaimed_delta': movement on a non-claimed axis (audit only, never aggregated)

This module is PURELY in-memory computation -- storage writes happen in the runner via
insert_confound_event(). The confound monitor returns events for the runner to persist.

Per A45: confound stays two-table; exclusion is the read-time VIEW (admissible_verdicts),
never a verdict-row state change. The confound_events row drives the VIEW exclusion.
"""

from __future__ import annotations

import contextlib
import statistics
from dataclasses import dataclass
from typing import Final

from skill_harness.oracles.tier1.axis_registry import MetricFn, get_tier1_scorers

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_NULL_FLOOR: Final[int] = 30
"""Minimum Null samples before sigma(Null) is reliable enough for confound detection."""

K_THRESHOLD: Final[float] = 2.0
"""Sigma multiplier for confound threshold (A47)."""

# The AXIS_* name constants moved to oracles/tier1/axis_registry.py, which is now
# the only place the Tier-1 axis names are written down (#117).

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfoundEvent:
    """A detected confound event (threshold-triggered, A47).

    Does NOT map 1:1 to a DB row -- the runner calls insert_confound_event().
    This is the pure-computation output of the confound monitor.
    """

    primary_clause_id: str
    """The ablated clause whose verdict is being evaluated (A46: == ablated_clause_id)."""

    affected_clause_id: str | None
    """The clause that owns the axis that moved (None for unclaimed axes)."""

    axis: str
    """The metric axis name."""

    delta: float
    """Observed delta (Full score - Ablated_k score) for this axis."""

    null_sigma: float
    """Estimated sigma(Null) for this axis at time of detection."""

    k_threshold: float
    """The k multiplier used (default K_THRESHOLD = 2.0)."""

    delta_kind: str
    """'confound_flagged' or 'observed_unclaimed_delta'."""


# ---------------------------------------------------------------------------
# Metric scorer registry (injected by runner, not module-level globals)
# ---------------------------------------------------------------------------


def get_default_tier1_scorers() -> dict[str, MetricFn]:
    """Return the default set of Tier-1 metric scoring functions.

    Ablation-layer alias for the axis registry's
    :func:`~skill_harness.oracles.tier1.axis_registry.get_tier1_scorers`, which
    owns both the names and the functions (#117). Kept rather than inlined at
    the four call sites because this is the name they already import, and the
    ablation layer is where scorers are injected.
    """
    return get_tier1_scorers()


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def score_text_on_axes(text: str, scorers: dict[str, MetricFn]) -> dict[str, float]:
    """Score a text on all provided metric axes.

    :param text: The output text to score.
    :param scorers: Dict mapping axis_name -> scoring function.
    :returns: Dict mapping axis_name -> float score.
    """
    import contextlib

    scores: dict[str, float] = {}
    for axis, fn in scorers.items():
        with contextlib.suppress(Exception):
            scores[axis] = float(fn(text))
    return scores


# ---------------------------------------------------------------------------
# NullAccumulator
# ---------------------------------------------------------------------------


class NullAccumulator:
    """Collects Null-condition scores for sigma(Null) estimation across all clauses.

    The runner collects Null samples across ALL clauses in a run so that sigma(Null)
    is estimated with sufficient power (N >= N_NULL_FLOOR per axis, A47).
    """

    def __init__(
        self,
        scorers: dict[str, MetricFn] | None = None,
        null_floor: int = N_NULL_FLOOR,
    ) -> None:
        """
        :param scorers: Metric scoring functions (injected; defaults to Tier-1 set).
        :param null_floor: Minimum Null samples per axis before sigma is reliable.
            Defaults to ``N_NULL_FLOOR`` (30, A47). Lowered ONLY in tests for speed —
            production code must use the default floor.
        """
        self._scorers: dict[str, MetricFn] = (
            scorers if scorers is not None else get_default_tier1_scorers()
        )
        self._null_floor: int = null_floor
        self._axis_values: dict[str, list[float]] = {}

    @property
    def null_floor(self) -> int:
        """The configured Null-sample floor for this accumulator (A47)."""
        return self._null_floor

    def add(self, text: str) -> None:
        """Score text on all axes and accumulate for sigma estimation."""
        scores = score_text_on_axes(text, self._scorers)
        for axis, value in scores.items():
            if axis not in self._axis_values:
                self._axis_values[axis] = []
            self._axis_values[axis].append(value)

    def sigmas(self) -> dict[str, float]:
        """Compute sigma per axis. Returns only axes with >= null_floor samples.

        A6: a floor-met, zero-variance axis is returned as sigma=0.0 rather than
        dropped. Dropping it made "zero variance" and "below floor" both read as
        "axis absent" to callers, which let confound detection go silently inert
        for zero-variance axes -- see ``detect_confounds`` for the consuming side.
        """
        result: dict[str, float] = {}
        for axis, values in self._axis_values.items():
            if len(values) < self._null_floor:
                continue  # Below floor -- confound detection disabled for this axis
            with contextlib.suppress(statistics.StatisticsError):
                result[axis] = statistics.stdev(values)  # may be 0.0 (A6)
        return result

    def n(self) -> int:
        """Total Null sample count (max across axes)."""
        if not self._axis_values:
            return 0
        return max(len(v) for v in self._axis_values.values())

    def axis_n(self, axis: str) -> int:
        """Null sample count for a specific axis."""
        return len(self._axis_values.get(axis, []))


# ---------------------------------------------------------------------------
# Confound detection (stateless -- uses pre-computed sigma)
# ---------------------------------------------------------------------------


def detect_confounds(
    full_text: str,
    ablated_text: str,
    null_sigmas: dict[str, float],
    primary_clause_id: str,
    clause_to_axis_map: dict[str, str],
    scorers: dict[str, MetricFn] | None = None,
    k: float = K_THRESHOLD,
) -> list[ConfoundEvent]:
    """Score Full vs Ablated_k on all axes and return confound events.

    Stateless: uses pre-computed sigma(Null) from a NullAccumulator.
    Threshold-triggered only -- no dense per-sample x axis table (A47).

    :param full_text: Full-condition subject output.
    :param ablated_text: Ablated_k-condition subject output.
    :param null_sigmas: Pre-computed sigma(Null) per axis.
    :param primary_clause_id: The ablated clause ID (A46 write-side assertion).
    :param clause_to_axis_map: Maps clause_id -> claimed axis name.
    :param scorers: Metric scoring functions (defaults to Tier-1 set).
    :param k: Sigma multiplier.
    :returns: List of ConfoundEvent (threshold-triggered only, A47).
    """
    if scorers is None:
        scorers = get_default_tier1_scorers()

    full_scores = score_text_on_axes(full_text, scorers)
    ablated_scores = score_text_on_axes(ablated_text, scorers)

    # Invert clause_to_axis_map: axis -> clause_id (for delta classification)
    axis_to_clause: dict[str, str] = {ax: cid for cid, ax in clause_to_axis_map.items()}

    events: list[ConfoundEvent] = []
    all_axes = set(full_scores.keys()) & set(ablated_scores.keys())

    for axis in sorted(all_axes):  # sorted for determinism
        sigma = null_sigmas.get(axis)
        if sigma is None:
            continue  # Below N_null floor -- genuinely insufficient Null data (A47)

        delta = full_scores[axis] - ablated_scores[axis]
        # A6: when sigma == 0.0 (floor met, zero variance under Null), k * sigma == 0,
        # so this only screens out an EXACT-zero delta. Any nonzero delta falls
        # through and is flagged -- a zero-variance Null gives no safe threshold to
        # hide real movement behind, so confound monitoring must never go silently
        # inert for a zero-variance axis.
        if abs(delta) <= k * sigma:
            continue  # Within threshold -- not a confound event

        # Determine delta_kind and affected_clause_id (A11)
        owner_clause = axis_to_clause.get(axis)

        if owner_clause is None:
            # No clause claims this axis -> observed_unclaimed_delta (audit only)
            events.append(
                ConfoundEvent(
                    primary_clause_id=primary_clause_id,
                    affected_clause_id=None,
                    axis=axis,
                    delta=delta,
                    null_sigma=sigma,
                    k_threshold=k,
                    delta_kind="observed_unclaimed_delta",
                )
            )
        elif owner_clause == primary_clause_id:
            # Primary clause's own axis moved -- expected, not a confound
            # (the runner's oracle measures this axis as the primary signal)
            pass
        else:
            # Another clause's axis moved -> confound_flagged (taints primary verdict)
            events.append(
                ConfoundEvent(
                    primary_clause_id=primary_clause_id,
                    affected_clause_id=owner_clause,
                    axis=axis,
                    delta=delta,
                    null_sigma=sigma,
                    k_threshold=k,
                    delta_kind="confound_flagged",
                )
            )

    return events


# ---------------------------------------------------------------------------
# Directional observation conversion
# ---------------------------------------------------------------------------


def delta_to_observation(
    delta: float, comparator: str = "increase", tie_tolerance: float = 0.0
) -> float:
    """Convert a metric delta to a Win/Tie/Loss observation (A10 half-update).

    :param delta: Full score - Ablated_k score on the primary axis.
    :param comparator: The clause's persisted directional claim (schema CHECK:
        increase|decrease|match). Determines which sign of delta counts as a Win:
        - 'increase': Win = Full > Ablated (delta > 0). The clause claims the axis
          rises -- this is the original, pre-A2 behavior and the default.
        - 'decrease': Win = Full < Ablated (delta < 0). The clause claims the axis
          falls, so the sign is flipped relative to 'increase' -- an effective
          decrease-direction clause (e.g. "be concise" on verbosity) must verdict
          Win, not Loss (A2).
        - 'match'/anything else: treated as 'increase'. A "preserve" claim is a
          magnitude-of-change question, not a delta-sign question, and defining that
          comparison model is out of scope here -- this is a deliberate placeholder,
          not a considered design decision.
    :param tie_tolerance: Absolute tolerance for tie classification (0.0 = strict equality).
    :returns: 1.0 (Win), 0.5 (Tie), 0.0 (Loss).
    """
    if abs(delta) <= tie_tolerance:
        return 0.5
    if comparator == "decrease":
        return 1.0 if delta < 0 else 0.0
    return 1.0 if delta > 0 else 0.0


# ---------------------------------------------------------------------------
# QUAL-1: Length-confound detection for sub-tolerance clauses
# ---------------------------------------------------------------------------


def check_operator_length_tolerance(
    clause_text: str,
    placeholder_text: str,
    tolerance_fraction: float = 0.10,
    min_tolerance_tokens: int = 2,
) -> tuple[bool, int, int, int]:
    """Check whether the AblationOperator met its length tolerance for a clause.

    QUAL-1 carry-forward from D.1: [ABLATED] is 4 tokens, so 1-2-token clauses
    cannot achieve the +/-2-token minimum tolerance. The runner must detect this
    and flag the Ablated_k samples as length-confounded (never emit clean-looking
    verbosity evidence from them).

    :param clause_text: Original clause text.
    :param placeholder_text: AblationOperator placeholder for this clause.
    :param tolerance_fraction: Token length tolerance fraction (default 10%).
    :param min_tolerance_tokens: Minimum tolerance in tokens (default 2).
    :returns: (within_tolerance, clause_tokens, placeholder_tokens, tolerance)
    """
    # F4: delegate to the canonical cl100k_base counter (tier1/verbosity.py)
    # instead of a third local tiktoken.get_encoding() re-implementation —
    # this module already imports the same counter inside
    # get_default_tier1_scorers(); a second copy here was the drift risk.
    from skill_harness.oracles.tier1.verbosity import count_tokens

    clause_tokens = count_tokens(clause_text)
    placeholder_tokens = count_tokens(placeholder_text)
    tolerance = max(min_tolerance_tokens, int(clause_tokens * tolerance_fraction))
    within = abs(placeholder_tokens - clause_tokens) <= tolerance
    return within, clause_tokens, placeholder_tokens, tolerance
