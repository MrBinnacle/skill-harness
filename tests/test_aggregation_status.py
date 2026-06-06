"""Tests for aggregation/status.py — A57 status state machine.

One falsifying test per rule (8 rules + sub-reason edge cases):
  Rule 1: no admissible verdicts → UNMEASURED(no_data)
  Rule 1b: all inadmissible (no confounds) → UNMEASURED(inadmissible)
  Rule 2: all confounded → CONFOUNDED (tested via engine confound path)
  Rule 3+4: N < N_min → UNMEASURED(underpowered)
  Rule 5a: threshold met but stale frozen case → UNMEASURED(falsifying_case_stale)
  Rule 5b: threshold met but no frozen case → UNMEASURED(falsifying_case_missing)
  Rule 6: threshold met AND current frozen case → PASSED
  Rule 7: threshold below 0.05 → FAILED
  Rule 8: 0.05 < p < 0.95 → UNMEASURED(underpowered)
  Extra: budget_exhausted when run aborted AND N < N_min
"""

from __future__ import annotations

from skill_harness.aggregation.status import (
    N_MIN,
    ClauseStatus,
    ClauseStatusInput,
    UnmeasuredSubReason,
    derive_clause_status,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_input(
    *,
    admissible_verdict_count: int = 0,
    total_verdict_count: int = 0,
    confounded_verdict_count: int = 0,
    n_verdicts: int = 0,
    p_win_gt_threshold: float = 0.5,
    current_frozen_case_count: int = 0,
    any_stale_frozen_case: bool = False,
    run_state: str | None = None,
) -> ClauseStatusInput:
    return ClauseStatusInput(
        admissible_verdict_count=admissible_verdict_count,
        total_verdict_count=total_verdict_count,
        confounded_verdict_count=confounded_verdict_count,
        n_verdicts=n_verdicts,
        p_win_gt_threshold=p_win_gt_threshold,
        current_frozen_case_count=current_frozen_case_count,
        any_stale_frozen_case=any_stale_frozen_case,
        run_state=run_state,
    )


# ---------------------------------------------------------------------------
# Rule 1: No admissible verdicts → UNMEASURED(no_data)
# ---------------------------------------------------------------------------


class TestRule1NoData:
    def test_zero_verdicts(self) -> None:
        """No verdicts at all → UNMEASURED(no_data)."""
        inp = make_input(admissible_verdict_count=0, total_verdict_count=0)
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.NO_DATA

    def test_zero_admissible_with_confounded(self) -> None:
        """Admissible=0 AND confounded>0 AND inadmissible=0 → this is Rule 2 territory.
        But derive_clause_status sees admissible_count=0, confounded=1, total=1.
        Since total>0 and confounded_verdict_count=0 (from this input), it's no_data.
        (Rule 2 / confound is handled externally by engine before calling this fn.)
        """
        # derive_clause_status checks: if admissible=0 AND total>0 AND confounded=0 → inadmissible
        # Here confounded_verdict_count>0 → the function doesn't hit inadmissible
        # It falls to NO_DATA because inadmissible path requires confounded=0
        inp = make_input(
            admissible_verdict_count=0,
            total_verdict_count=1,
            confounded_verdict_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.NO_DATA


# ---------------------------------------------------------------------------
# Rule 1b: All inadmissible (no confounds) → UNMEASURED(inadmissible)
# ---------------------------------------------------------------------------


class TestRule1bInadmissible:
    def test_all_inadmissible(self) -> None:
        """Verdicts exist but all inadmissible, no confounds → UNMEASURED(inadmissible)."""
        inp = make_input(
            admissible_verdict_count=0,
            total_verdict_count=5,
            confounded_verdict_count=0,  # no confounds
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.INADMISSIBLE


# ---------------------------------------------------------------------------
# Rule 3+4: N < N_min → UNMEASURED(underpowered)
# ---------------------------------------------------------------------------


class TestRule3Underpowered:
    def test_n_below_nmin(self) -> None:
        """N=4 < N_min=8 → UNMEASURED(underpowered)."""
        inp = make_input(
            admissible_verdict_count=4,
            total_verdict_count=4,
            n_verdicts=4,
            p_win_gt_threshold=0.97,  # would pass if N were enough
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.UNDERPOWERED

    def test_n_equals_nmin_minus_1(self) -> None:
        """N=N_min-1 → underpowered."""
        inp = make_input(
            admissible_verdict_count=N_MIN - 1,
            total_verdict_count=N_MIN - 1,
            n_verdicts=N_MIN - 1,
            p_win_gt_threshold=0.99,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.UNDERPOWERED

    def test_n_equals_nmin_allowed(self) -> None:
        """N=N_min with p >= threshold → moves past underpowered rule."""
        inp = make_input(
            admissible_verdict_count=N_MIN,
            total_verdict_count=N_MIN,
            n_verdicts=N_MIN,
            p_win_gt_threshold=0.97,  # PASS threshold
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.PASSED
        assert sub is None


# ---------------------------------------------------------------------------
# Rule 5a: Threshold met but stale frozen case → UNMEASURED(falsifying_case_stale)
# ---------------------------------------------------------------------------


class TestRule5aStale:
    def test_stale_frozen_case(self) -> None:
        """P >= 0.95, current=0, stale exists → UNMEASURED(falsifying_case_stale)."""
        inp = make_input(
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.97,
            current_frozen_case_count=0,
            any_stale_frozen_case=True,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.FALSIFYING_CASE_STALE


# ---------------------------------------------------------------------------
# Rule 5b: Threshold met but no frozen case → UNMEASURED(falsifying_case_missing)
# ---------------------------------------------------------------------------


class TestRule5bMissing:
    def test_no_frozen_case(self) -> None:
        """P >= 0.95, current=0, no stale → UNMEASURED(falsifying_case_missing)."""
        inp = make_input(
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.97,
            current_frozen_case_count=0,
            any_stale_frozen_case=False,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.FALSIFYING_CASE_MISSING


# ---------------------------------------------------------------------------
# Rule 6: Threshold met AND current frozen case → PASSED
# ---------------------------------------------------------------------------


class TestRule6Passed:
    def test_passed_with_current_frozen_case(self) -> None:
        """P >= 0.95 AND current_frozen_case_count >= 1 → PASSED."""
        inp = make_input(
            admissible_verdict_count=15,
            total_verdict_count=15,
            n_verdicts=15,
            p_win_gt_threshold=0.97,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.PASSED
        assert sub is None

    def test_passed_with_multiple_frozen_cases(self) -> None:
        """Multiple current frozen cases → still PASSED."""
        inp = make_input(
            admissible_verdict_count=20,
            total_verdict_count=20,
            n_verdicts=20,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=3,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.PASSED
        assert sub is None

    def test_exactly_at_threshold(self) -> None:
        """p_win = PASS_PROB_THRESHOLD exactly → PASSED (>= check)."""
        inp = make_input(
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.95,  # exactly PASS_PROB_THRESHOLD
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.PASSED
        assert sub is None


# ---------------------------------------------------------------------------
# Rule 7: p <= FAIL_PROB_THRESHOLD → FAILED
# ---------------------------------------------------------------------------


class TestRule7Failed:
    def test_failed_low_p(self) -> None:
        """P <= 0.05 → FAILED."""
        inp = make_input(
            admissible_verdict_count=20,
            total_verdict_count=20,
            n_verdicts=20,
            p_win_gt_threshold=0.02,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.FAILED
        assert sub is None

    def test_failed_exactly_at_threshold(self) -> None:
        """P = 0.05 exactly → FAILED (<= check)."""
        inp = make_input(
            admissible_verdict_count=20,
            total_verdict_count=20,
            n_verdicts=20,
            p_win_gt_threshold=0.05,  # exactly FAIL_PROB_THRESHOLD
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.FAILED
        assert sub is None

    def test_failed_with_stale_frozen_case(self) -> None:
        """P <= 0.05 → FAILED regardless of frozen case state."""
        inp = make_input(
            admissible_verdict_count=20,
            total_verdict_count=20,
            n_verdicts=20,
            p_win_gt_threshold=0.01,
            any_stale_frozen_case=True,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.FAILED
        assert sub is None


# ---------------------------------------------------------------------------
# Rule 8: Inconclusive → UNMEASURED(underpowered)
# ---------------------------------------------------------------------------


class TestRule8Inconclusive:
    def test_inconclusive_mid_range(self) -> None:
        """0.05 < p < 0.95, N >= N_min → UNMEASURED(underpowered)."""
        inp = make_input(
            admissible_verdict_count=12,
            total_verdict_count=12,
            n_verdicts=12,
            p_win_gt_threshold=0.50,  # inconclusive
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.UNDERPOWERED

    def test_inconclusive_just_above_fail(self) -> None:
        """p just above 0.05 → still underpowered."""
        inp = make_input(
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.051,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.UNDERPOWERED

    def test_inconclusive_just_below_pass(self) -> None:
        """p just below 0.95 → still underpowered."""
        inp = make_input(
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.94,
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.UNDERPOWERED


# ---------------------------------------------------------------------------
# Extra: budget_exhausted
# ---------------------------------------------------------------------------


class TestBudgetExhausted:
    def test_budget_exhausted_with_low_n(self) -> None:
        """run_state='aborted_budget' AND N < N_min → UNMEASURED(budget_exhausted)."""
        inp = make_input(
            admissible_verdict_count=3,
            total_verdict_count=3,
            n_verdicts=3,
            p_win_gt_threshold=0.97,  # would pass if N were enough
            run_state="aborted_budget",
        )
        status, sub = derive_clause_status(inp)
        assert status == ClauseStatus.UNMEASURED
        assert sub == UnmeasuredSubReason.BUDGET_EXHAUSTED

    def test_budget_exhausted_does_not_fire_if_n_sufficient(self) -> None:
        """run_state='aborted_budget' but N >= N_min → NOT budget_exhausted."""
        inp = make_input(
            admissible_verdict_count=N_MIN,
            total_verdict_count=N_MIN,
            n_verdicts=N_MIN,
            p_win_gt_threshold=0.02,  # FAILED
            run_state="aborted_budget",
        )
        status, _sub = derive_clause_status(inp)
        # Not budget_exhausted — N is sufficient. Falls to FAILED.
        assert status == ClauseStatus.FAILED


# ---------------------------------------------------------------------------
# Edge: status enum values are strings (StrEnum)
# ---------------------------------------------------------------------------


class TestEnumValues:
    def test_clause_status_str_values(self) -> None:
        assert ClauseStatus.PASSED == "PASSED"
        assert ClauseStatus.FAILED == "FAILED"
        assert ClauseStatus.CONFOUNDED == "CONFOUNDED"
        assert ClauseStatus.UNMEASURED == "UNMEASURED"

    def test_unmeasured_sub_reason_str_values(self) -> None:
        assert UnmeasuredSubReason.NO_DATA == "no_data"
        assert UnmeasuredSubReason.INADMISSIBLE == "inadmissible"
        assert UnmeasuredSubReason.UNDERPOWERED == "underpowered"
        assert UnmeasuredSubReason.FALSIFYING_CASE_MISSING == "falsifying_case_missing"
        assert UnmeasuredSubReason.BUDGET_EXHAUSTED == "budget_exhausted"
        assert UnmeasuredSubReason.FALSIFYING_CASE_STALE == "falsifying_case_stale"
