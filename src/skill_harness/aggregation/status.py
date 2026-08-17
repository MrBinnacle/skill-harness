"""Status state machine for clause aggregation (A57).

Implements `derive_clause_status()` — a pure function that maps clause evidence
to a (ClauseStatus, UnmeasuredSubReason | None) pair.

State derivation rules (A57, ordered by priority):
  0. Axis has no registered Tier-1 mechanical scorer → UNMEASURED(mechanical_vacuous)
  1. No admissible+non-confounded verdicts → UNMEASURED(no_data)
  2. Verdicts exist but ALL confounded → CONFOUNDED
  3. N < N_min (8) → UNMEASURED(underpowered)
  4. Sequential-stop at N_max without resolution → UNMEASURED(underpowered)
  5. Posterior threshold MET but no current frozen case:
       - stale frozen case exists → UNMEASURED(falsifying_case_stale)
       - no frozen case at all → UNMEASURED(falsifying_case_missing)
  6. Posterior threshold MET AND ≥1 current frozen case → PASSED
     (B1: when the skill fit used BH-FDR fallback, PASSED additionally requires
     bh_fdr_pass=True — the raw threshold alone is not FDR-corrected.)
  7. Posterior threshold MET-BELOW (p <= 0.05) → FAILED
  8. Otherwise (0.05 < p < 0.95) → UNMEASURED(underpowered)

Additional sub-reasons:
  - inadmissible: verdicts exist but ALL are inadmissible (no confounds — this is
    distinct from CONFOUNDED which requires confound_events rows).
  - budget_exhausted: run state = 'aborted_budget' AND verdict count < N_min.

The inadmissible and budget_exhausted checks are applied BEFORE the N-count checks
because they explain WHY there is insufficient admissible evidence.

Rule 0 is load-bearing and must come first: if no registered scorer can ever
measure the axis, NO_DATA is a false explanation (it implies more sampling would
resolve the clause). Scoreability is exact membership in TIER1_AXIS_NAMES via
classify_axis — never fuzzy, never case-insensitive, never a Tier-2 judge.
"""

from __future__ import annotations

from enum import StrEnum

from skill_harness.oracles.tier1.axis_registry import AxisScoreability, classify_axis

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ClauseStatus(StrEnum):
    """Terminal status for a clause after aggregation."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    CONFOUNDED = "CONFOUNDED"
    UNMEASURED = "UNMEASURED"


class UnmeasuredSubReason(StrEnum):
    """Sub-reason qualifying UNMEASURED status (A57 extension of A17)."""

    NO_DATA = "no_data"
    INADMISSIBLE = "inadmissible"
    UNDERPOWERED = "underpowered"
    FALSIFYING_CASE_MISSING = "falsifying_case_missing"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FALSIFYING_CASE_STALE = "falsifying_case_stale"
    FDR_CORRECTION_FAILED = "fdr_correction_failed"
    """F-3 (S55 hostile review): the raw (uncorrected) posterior crossed
    PASS_PROB_THRESHOLD but B1's BH-FDR gate rejected this clause
    (bh_fdr_pass=False). Distinct from UNDERPOWERED -- N and the raw posterior
    are both fine; what failed is the multiple-testing correction, not the
    sample size. Pre-fix this fell through to the generic Rule 8 UNDERPOWERED
    branch with no way to distinguish "not enough evidence yet" from "enough
    evidence, but doesn't survive FDR correction"."""
    MECHANICAL_VACUOUS = "mechanical_vacuous"
    """No registered Tier-1 mechanical scorer can see this axis.

    Orthogonal to write-time vacuity_flag: a clause may be constructibly
    testable (has a falsifying case) and still mechanically unscoreable.
    Lifetime is registry-dependent — recomputed at aggregation, never frozen
    onto clauses.vacuity_flag.
    """


# ---------------------------------------------------------------------------
# Locked thresholds (pass rule — do NOT silently retune; see docs/INVARIANTS.md #1)
# ---------------------------------------------------------------------------

PASS_PROB_THRESHOLD: float = 0.95
FAIL_PROB_THRESHOLD: float = 0.05
N_MIN: int = 8


# ---------------------------------------------------------------------------
# Input shape for state derivation
# ---------------------------------------------------------------------------


class ClauseStatusInput:
    """All evidence needed to derive clause status.

    Attributes
    ----------
    axis : str
        Measurement axis for the clause (exact string; matched against TIER1_AXIS_NAMES
        via classify_axis — no normalisation).
    admissible_verdict_count : int
        Count of rows from admissible_verdicts VIEW for this clause/axis.
    total_verdict_count : int
        Count of ALL oracle_verdicts rows for this clause (before evidence-admissibility filter).
    confounded_verdict_count : int
        Count of verdicts that have confound_events with delta_kind='confound_flagged'.
    n_verdicts : int
        Count of admissible+non-confounded verdicts (= effective N for stopping rule).
    p_win_gt_threshold : float
        P(rate > 0.60) from the posterior (shrunken or unpooled, per fit method).
    current_frozen_case_count : int
        Count of frozen_cases rows with currency_state='current' for (clause_id, axis).
    any_stale_frozen_case : bool
        True if ≥1 frozen_cases row exists for (clause_id, axis) with currency_state='stale'.
    run_state : str | None
        The run_progress.state for the source run (e.g. 'aborted_budget').
        None if the run_progress row is unavailable (tolerated).
    bh_fdr_pass : bool | None
        B1: gates the raw p_win_gt_threshold>=0.95 PASS check when the skill's fit used
        the BH-FDR fallback method. None means "not applicable" (EB-MoM/unpooled method,
        or this method's bh_fdr_passes is unavailable) — the raw threshold applies
        unmodified. True/False means the fit DID run BH-FDR and this clause did/did not
        survive the FDR-corrected test; False must block PASSED even if the raw
        (uncorrected) posterior crosses 0.95 — otherwise the raw per-clause threshold
        produces false PASSes at ~K*q the claimed FDR rate under multiple testing.
    """

    def __init__(
        self,
        *,
        axis: str,
        admissible_verdict_count: int,
        total_verdict_count: int,
        confounded_verdict_count: int,
        n_verdicts: int,
        p_win_gt_threshold: float,
        current_frozen_case_count: int,
        any_stale_frozen_case: bool,
        run_state: str | None = None,
        bh_fdr_pass: bool | None = None,
    ) -> None:
        self.axis = axis
        self.admissible_verdict_count = admissible_verdict_count
        self.total_verdict_count = total_verdict_count
        self.confounded_verdict_count = confounded_verdict_count
        self.n_verdicts = n_verdicts
        self.p_win_gt_threshold = p_win_gt_threshold
        self.current_frozen_case_count = current_frozen_case_count
        self.any_stale_frozen_case = any_stale_frozen_case
        self.run_state = run_state
        self.bh_fdr_pass = bh_fdr_pass


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def derive_clause_status(
    inp: ClauseStatusInput,
) -> tuple[ClauseStatus, UnmeasuredSubReason | None]:
    """Map evidence to (ClauseStatus, sub_reason | None).

    Implements A57 rules in priority order.  The function is pure — no DB
    access, no side effects.  All queries must be pre-computed by the engine.
    """
    # Rule 0: axis not mechanically scoreable by any registered Tier-1 scorer
    if classify_axis(inp.axis) is AxisScoreability.UNSCOREABLE:
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.MECHANICAL_VACUOUS

    # Rule 1: No admissible+non-confounded verdicts at all
    if inp.admissible_verdict_count == 0:
        # Distinguish: were there ANY verdicts (just all inadmissible)?
        if inp.total_verdict_count > 0 and inp.confounded_verdict_count == 0:
            # Verdicts exist but ALL inadmissible (no confounds)
            return ClauseStatus.UNMEASURED, UnmeasuredSubReason.INADMISSIBLE
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.NO_DATA

    # Rule 2: All verdicts confounded (admissible_count == 0 after confound filter,
    # but confound_events exist — distinct from rule 1)
    # Note: admissible_verdict_count already excludes confounded via VIEW.
    # If confounded_verdict_count > 0 AND admissible_verdict_count == 0, that's
    # captured above. But the spec says "verdicts exist but ALL are confounded" —
    # this means admissible_verdict_count == 0 AND confounded_verdict_count > 0.
    # Already handled in Rule 1 path — but we need to distinguish here:
    # If we reach this point, admissible_verdict_count > 0, so Rule 2 doesn't apply.
    # The spec's Rule 2 is really a sub-case of Rule 1.

    n = inp.n_verdicts
    p = inp.p_win_gt_threshold

    # Rule: budget_exhausted — run aborted AND not enough admissible evidence
    if inp.run_state == "aborted_budget" and n < N_MIN:
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.BUDGET_EXHAUSTED

    # Rule 3 + 4: Under-sampled (N < N_min) or N_max without resolution
    if n < N_MIN:
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.UNDERPOWERED

    # Rule 7: FAILED — posterior threshold decidedly below (check before PASSED/stale)
    if p <= FAIL_PROB_THRESHOLD:
        return ClauseStatus.FAILED, None

    # Rules 5 + 6: PASSED gate — check frozen case currency
    # B1: bh_fdr_pass is False means this skill's fit fell back to BH-FDR and this
    # clause did NOT survive the FDR-corrected test. The raw uncorrected
    # p_win_gt_threshold>=0.95 crossing is then not a valid PASS signal on its own —
    # fall through to Rule 8 (UNMEASURED/underpowered) instead of PASSED/FAILED-gate.
    if p >= PASS_PROB_THRESHOLD and inp.bh_fdr_pass is not False:
        if inp.current_frozen_case_count >= 1:
            # Rule 6: threshold met AND current frozen case → PASSED
            return ClauseStatus.PASSED, None
        # Rule 5: threshold met but no current frozen case
        if inp.any_stale_frozen_case:
            return ClauseStatus.UNMEASURED, UnmeasuredSubReason.FALSIFYING_CASE_STALE
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.FALSIFYING_CASE_MISSING

    # F-3 (S55 hostile review): raw posterior crossed PASS_PROB_THRESHOLD but the
    # skill's BH-FDR fit rejected this clause (bh_fdr_pass=False). Must NOT fall
    # through to the generic Rule 8 UNDERPOWERED branch below -- N and the raw
    # posterior are both fine here; it is the FDR correction that failed, a
    # different (and more informative) reason than "not enough evidence yet".
    if p >= PASS_PROB_THRESHOLD and inp.bh_fdr_pass is False:
        return ClauseStatus.UNMEASURED, UnmeasuredSubReason.FDR_CORRECTION_FAILED

    # Rule 8: Inconclusive posterior — 0.05 < p < 0.95
    return ClauseStatus.UNMEASURED, UnmeasuredSubReason.UNDERPOWERED
