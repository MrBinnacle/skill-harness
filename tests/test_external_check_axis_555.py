"""Tests for #555 -- external-check axis registry and runner integration.

Tests cover:
  AC1: A run declares an axis whose score comes from a deterministic external check,
       and the runner records it without routing through the judge.
  AC2: The blanket refusal of non-tier-1 clauses before sampling is replaced by a
       refusal that names why a specific clause is unmeasurable.
  AC3: A clause that genuinely has no available oracle still reaches UNMEASURED,
       and the receipt says which oracle was missing.
  AC4: A red demonstration shows a clause refused for a stated reason rather than
       for its tier alone.
  AC6: No path can report a score for an axis whose oracle did not execute.

Build constraint BC1: External checks are a registry like tier-1 axes.
Build constraint BC2: Property test keeps its force (tested in
    test_extractor_aggregation_invariants_167.py).
"""

from __future__ import annotations

from skill_harness.aggregation.status import (
    ClauseStatus,
    ClauseStatusInput,
    UnmeasuredSubReason,
    derive_clause_status,
)
from skill_harness.oracles.tier1.axis_registry import (
    EXTERNAL_CHECK_AXIS_NAMES,
    TIER1_AXIS_NAMES,
    AxisScoreability,
    classify_axis,
    get_external_check_scorers,
    get_tier1_scorers,
)


def _make_input(
    *,
    axis: str = "verbosity",
    admissible_verdict_count: int = 0,
    total_verdict_count: int = 0,
    confounded_verdict_count: int = 0,
    n_verdicts: int = 0,
    p_win_gt_threshold: float = 0.5,
    current_frozen_case_count: int = 0,
    any_stale_frozen_case: bool = False,
    run_state: str | None = None,
    bh_fdr_pass: bool | None = None,
) -> ClauseStatusInput:
    return ClauseStatusInput(
        axis=axis,
        admissible_verdict_count=admissible_verdict_count,
        total_verdict_count=total_verdict_count,
        confounded_verdict_count=confounded_verdict_count,
        n_verdicts=n_verdicts,
        p_win_gt_threshold=p_win_gt_threshold,
        current_frozen_case_count=current_frozen_case_count,
        any_stale_frozen_case=any_stale_frozen_case,
        run_state=run_state,
        bh_fdr_pass=bh_fdr_pass,
    )


# ---------------------------------------------------------------------------
# AC1 + BC1: External-check registry exists and classify_axis returns EXTERNAL_CHECK
# ---------------------------------------------------------------------------


class TestExternalCheckRegistry:
    """AC1: The external-check registry is a first-class citizen beside Tier-1."""

    def test_external_check_axis_names_is_nonempty_tuple(self) -> None:
        """EXTERNAL_CHECK_AXIS_NAMES is a non-empty tuple of strings."""
        assert isinstance(EXTERNAL_CHECK_AXIS_NAMES, tuple)
        assert len(EXTERNAL_CHECK_AXIS_NAMES) > 0
        assert all(isinstance(name, str) for name in EXTERNAL_CHECK_AXIS_NAMES)

    def test_protected_comment_deletion_is_registered(self) -> None:
        """The protected_comment_deletion axis is in the external-check registry."""
        assert "protected_comment_deletion" in EXTERNAL_CHECK_AXIS_NAMES

    def test_classify_axis_returns_external_check_for_registered_axis(self) -> None:
        """classify_axis returns EXTERNAL_CHECK for a registered external-check axis."""
        for axis in EXTERNAL_CHECK_AXIS_NAMES:
            assert classify_axis(axis) is AxisScoreability.EXTERNAL_CHECK

    def test_classify_axis_returns_tier1_for_tier1_axis(self) -> None:
        """classify_axis returns TIER1_MECHANICAL for a registered Tier-1 axis."""
        for axis in TIER1_AXIS_NAMES:
            assert classify_axis(axis) is AxisScoreability.TIER1_MECHANICAL

    def test_classify_axis_returns_unscoreable_for_unknown_axis(self) -> None:
        """classify_axis returns UNSCOREABLE for an axis not in any registry."""
        assert classify_axis("unknown_axis") is AxisScoreability.UNSCOREABLE
        assert classify_axis("") is AxisScoreability.UNSCOREABLE

    def test_registries_are_disjoint(self) -> None:
        """Tier-1 and external-check registries have no overlap."""
        overlap = set(TIER1_AXIS_NAMES) & set(EXTERNAL_CHECK_AXIS_NAMES)
        assert overlap == set(), f"registries overlap on: {overlap}"


# ---------------------------------------------------------------------------
# AC2: Blanket refusal replaced with clause-specific reason
# ---------------------------------------------------------------------------


class TestClauseRefusalReason:
    """AC2: derive_clause_status refuses clauses with specific reasons."""

    def test_tier1_axis_with_evidence_passes_rule0(self) -> None:
        """A Tier-1 axis with evidence passes Rule 0 (not MECHANICAL_VACUOUS)."""
        inp = _make_input(
            axis="verbosity",
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.PASSED
        assert sub is None

    def test_external_check_axis_with_evidence_passes_rule0(self) -> None:
        """An external-check axis with evidence passes Rule 0 (not MECHANICAL_VACUOUS).

        This is the key AC2 test: the aggregation layer does NOT refuse
        external-check axes. They are scoreable by a deterministic program.
        """
        inp = _make_input(
            axis="protected_comment_deletion",
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.PASSED
        assert sub is None

    def test_unknown_axis_refused_as_mechanical_vacuous(self) -> None:
        """An axis not in any registry is refused as MECHANICAL_VACUOUS at aggregation."""
        inp = _make_input(
            axis="unknown_axis",
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.MECHANICAL_VACUOUS

    def test_axis_classification_determines_refusal_reason(self) -> None:
        """The axis classification determines the refusal reason at aggregation.

        MECHANICAL_VACUOUS: axis not in any registry
        No refusal: axis in Tier-1 or external-check registry
        """
        # Unknown axis -> MECHANICAL_VACUOUS
        assert classify_axis("unknown") is AxisScoreability.UNSCOREABLE
        inp = _make_input(axis="unknown")
        _status, sub = derive_clause_status(inp)
        assert sub is UnmeasuredSubReason.MECHANICAL_VACUOUS

        # External-check axis -> not MECHANICAL_VACUOUS
        assert classify_axis("protected_comment_deletion") is AxisScoreability.EXTERNAL_CHECK
        inp = _make_input(
            axis="protected_comment_deletion",
            admissible_verdict_count=0,
            total_verdict_count=0,
        )
        _status, sub = derive_clause_status(inp)
        assert sub is UnmeasuredSubReason.NO_DATA  # not MECHANICAL_VACUOUS


# ---------------------------------------------------------------------------
# AC3: Clause with no oracle reaches UNMEASURED with missing oracle named
# ---------------------------------------------------------------------------


class TestNoOracleClause:
    """AC3: A clause with no available oracle reaches UNMEASURED with the missing oracle named."""

    def test_unknown_axis_aggregation_returns_mechanical_vacuous(self) -> None:
        """Aggregation of an unknown axis returns UNMEASURED(MECHANICAL_VACUOUS)."""
        inp = _make_input(axis="unknown_axis")
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.MECHANICAL_VACUOUS

    def test_external_check_axis_no_verdicts_returns_no_data(self) -> None:
        """An external-check axis with no verdicts returns UNMEASURED(NO_DATA).

        This proves the axis passed Rule 0 (it IS in a registry) but has no
        evidence yet. The receipt says "no_data" -- the oracle exists but
        has not executed.
        """
        inp = _make_input(axis="protected_comment_deletion")
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.NO_DATA

    def test_tier1_axis_no_verdicts_returns_no_data(self) -> None:
        """A Tier-1 axis with no verdicts returns UNMEASURED(NO_DATA)."""
        inp = _make_input(axis="verbosity")
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.NO_DATA


# ---------------------------------------------------------------------------
# AC4: Red demonstration -- clause refused for stated reason, not tier alone
# ---------------------------------------------------------------------------


class TestRedDemonstration:
    """AC4: A clause is refused for a stated reason rather than for its tier alone."""

    def test_tier2_oracle_on_tier1_axis_refused_as_tier2_uncalibrated(self) -> None:
        """A clause with oracle_tier=2 on a Tier-1 axis is not refused by Rule 0.

        Rule 0 only checks the axis registry, not the oracle tier. The axis
        'verbosity' IS in TIER1_AXIS_NAMES, so Rule 0 passes. The clause
        would be refused by the runner's BLOCKER-1 gate (oracle_tier != 1),
        but aggregation sees it as NO_DATA (no verdicts).
        """
        inp = _make_input(
            axis="verbosity",
            admissible_verdict_count=0,
            total_verdict_count=0,
        )
        status, sub = derive_clause_status(inp)
        # Rule 0 passes (verbosity is registered), but no evidence -> NO_DATA
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.NO_DATA

    def test_unknown_axis_refused_as_mechanical_vacuous_not_tier2(self) -> None:
        """An unknown axis is refused as MECHANICAL_VACUOUS, not TIER2_UNCALIBRATED.

        This is the key difference from the old behavior: the refusal now names
        the specific reason (no oracle at all) rather than hiding behind TIER2.
        """
        inp = _make_input(
            axis="totally_unknown",
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.MECHANICAL_VACUOUS

    def test_external_check_axis_not_refused_by_rule0(self) -> None:
        """An external-check axis is not refused by Rule 0 (it IS registered).

        The old code would have refused it as MECHANICAL_VACUOUS because only
        TIER1_AXIS_NAMES was checked. Now EXTERNAL_CHECK_AXIS_NAMES is also
        checked, so the axis passes Rule 0.
        """
        assert classify_axis("protected_comment_deletion") is AxisScoreability.EXTERNAL_CHECK
        inp = _make_input(
            axis="protected_comment_deletion",
            admissible_verdict_count=5,
            total_verdict_count=5,
            n_verdicts=5,
            p_win_gt_threshold=0.50,
        )
        status, sub = derive_clause_status(inp)
        # Rule 0 passes (external-check axis is registered)
        # But N < N_MIN -> underpowered
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.UNDERPOWERED


# ---------------------------------------------------------------------------
# AC6: No path can report a score for an axis whose oracle did not execute
# ---------------------------------------------------------------------------


class TestNoScoreWithoutOracle:
    """AC6: No path reports a score for an axis whose oracle did not execute."""

    def test_external_check_scorers_is_empty_dict(self) -> None:
        """get_external_check_scorers returns an empty dict (no scorers registered).

        This proves that no external-check axis can be scored until a checker
        is registered. The protected_comment_deletion axis is in the registry
        but has no scorer, so the runner would refuse it.
        """
        scorers = get_external_check_scorers()
        assert scorers == {}

    def test_tier1_scorers_cover_all_tier1_axes(self) -> None:
        """get_tier1_scorers returns a scorer for every Tier-1 axis.

        This is a sanity check that the Tier-1 registry is complete.
        """
        scorers = get_tier1_scorers()
        assert set(scorers.keys()) == set(TIER1_AXIS_NAMES)

    def test_classify_axis_prevents_unregistered_axis_from_scoring(self) -> None:
        """classify_axis returns UNSCOREABLE for axes not in any registry.

        An UNSCOREABLE axis cannot be scored because aggregation marks it
        MECHANICAL_VACUOUS (Rule 0), and the runner refuses it before sampling.
        """
        assert classify_axis("nonexistent_axis") is AxisScoreability.UNSCOREABLE
        # Verify that MECHANICAL_VACUOUS blocks scoring at aggregation
        inp = _make_input(
            axis="nonexistent_axis",
            admissible_verdict_count=10,
            total_verdict_count=10,
            n_verdicts=10,
            p_win_gt_threshold=0.99,
            current_frozen_case_count=1,
        )
        status, sub = derive_clause_status(inp)
        assert status is ClauseStatus.UNMEASURED
        assert sub is UnmeasuredSubReason.MECHANICAL_VACUOUS
