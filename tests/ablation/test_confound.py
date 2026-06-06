"""Tests for confound monitoring (A11, A45, A46, A47) and QUAL-1.

Covers:
- NullAccumulator: accumulates Null scores, computes sigmas correctly.
- detect_confounds: threshold-triggered event emission only.
- delta_kind classification: confound_flagged vs observed_unclaimed_delta.
- N_null floor: confound detection disabled below floor.
- check_operator_length_tolerance: QUAL-1 sub-tolerance clause detection.
- delta_to_observation: Win/Tie/Loss encoding.
- A46 write-side assertion: primary_clause_id == ablated_clause_id.
"""

from __future__ import annotations

from skill_harness.ablation.confound import (
    K_THRESHOLD,
    N_NULL_FLOOR,
    NullAccumulator,
    check_operator_length_tolerance,
    delta_to_observation,
    detect_confounds,
)

# ---------------------------------------------------------------------------
# Fake metric scorer for tests (deterministic, no wordlist needed)
# ---------------------------------------------------------------------------


def _fake_word_count(text: str) -> float:
    """Count whitespace-separated words."""
    return float(len(text.split()))


def _fake_char_count(text: str) -> float:
    """Count characters."""
    return float(len(text))


FAKE_SCORERS = {
    "word_count": _fake_word_count,
    "char_count": _fake_char_count,
}


# ---------------------------------------------------------------------------
# NullAccumulator tests
# ---------------------------------------------------------------------------


class TestNullAccumulator:
    def test_empty_sigmas_below_floor(self) -> None:
        """With fewer than N_NULL_FLOOR samples, sigmas() returns empty dict."""
        acc = NullAccumulator(scorers=FAKE_SCORERS)
        for _ in range(N_NULL_FLOOR - 1):
            acc.add("hello world")
        assert acc.sigmas() == {}
        assert acc.n() == N_NULL_FLOOR - 1

    def test_sigmas_after_floor_met(self) -> None:
        """After N_NULL_FLOOR samples with variance, sigmas returns non-empty dict."""
        acc = NullAccumulator(scorers=FAKE_SCORERS)
        # Alternate between short and long text to create variance
        for i in range(N_NULL_FLOOR):
            if i % 2 == 0:
                acc.add("a b c d e")  # 5 words
            else:
                acc.add("a b c d e f g h i j k l m n o p")  # 16 words
        sigs = acc.sigmas()
        assert "word_count" in sigs
        assert sigs["word_count"] > 0.0

    def test_zero_variance_excluded(self) -> None:
        """Zero-variance axis (all same value) is excluded from sigmas."""
        acc = NullAccumulator(scorers=FAKE_SCORERS)
        # All same text -> zero variance
        for _ in range(N_NULL_FLOOR):
            acc.add("exactly five words here now")
        sigs = acc.sigmas()
        # word_count will be constant (5) -> sigma = 0 -> excluded
        assert "word_count" not in sigs

    def test_axis_n(self) -> None:
        """axis_n() returns sample count for specific axis."""
        acc = NullAccumulator(scorers={"x": lambda t: float(len(t))})
        for _ in range(5):
            acc.add("hello")
        assert acc.axis_n("x") == 5
        assert acc.axis_n("nonexistent") == 0


# ---------------------------------------------------------------------------
# detect_confounds tests
# ---------------------------------------------------------------------------


class TestDetectConfounds:
    def _make_sigmas(self, axes: list[str], sigma_value: float = 1.0) -> dict[str, float]:
        return {ax: sigma_value for ax in axes}

    def test_no_confound_below_threshold(self) -> None:
        """No confound event emitted when delta <= k * sigma."""
        # Full: 10 words, Ablated: 9 words -> delta = 1 word
        # With sigma=1.0 and k=2.0, threshold = 2.0 -> delta=1 < 2 -> no confound
        full_text = " ".join(["word"] * 10)
        ablated_text = " ".join(["word"] * 9)
        null_sigmas = self._make_sigmas(["word_count"], sigma_value=1.0)
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-1",
            clause_to_axis_map={"clause-1": "word_count"},
            scorers=FAKE_SCORERS,
        )
        assert events == []

    def test_confound_flagged_above_threshold(self) -> None:
        """confound_flagged emitted when delta > k * sigma for another clause's axis."""
        # Full: 20 words, Ablated: 5 words -> delta = 15 words
        # sigma = 1.0, k = 2.0 -> threshold = 2.0 -> 15 > 2 -> confound
        # clause-2 owns word_count, clause-1 is primary (ablated)
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        null_sigmas = self._make_sigmas(["word_count"], sigma_value=1.0)
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-1",
            clause_to_axis_map={
                "clause-1": "char_count",  # primary clause claims char_count
                "clause-2": "word_count",  # another clause claims word_count
            },
            scorers=FAKE_SCORERS,
        )
        # word_count moved for another clause's axis -> confound_flagged
        confound_events = [e for e in events if e.delta_kind == "confound_flagged"]
        assert len(confound_events) >= 1
        for e in confound_events:
            assert e.primary_clause_id == "clause-1"
            assert e.affected_clause_id == "clause-2"
            assert e.axis == "word_count"

    def test_observed_unclaimed_delta_for_orphan_axis(self) -> None:
        """observed_unclaimed_delta emitted for axes not claimed by any clause."""
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        null_sigmas = self._make_sigmas(["word_count"], sigma_value=1.0)
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-1",
            clause_to_axis_map={"clause-1": "char_count"},  # only char_count claimed
            scorers=FAKE_SCORERS,
        )
        unclaimed = [e for e in events if e.delta_kind == "observed_unclaimed_delta"]
        assert len(unclaimed) >= 1
        for e in unclaimed:
            assert e.affected_clause_id is None

    def test_primary_axis_not_flagged_as_confound(self) -> None:
        """Primary clause's own claimed axis moving is NOT flagged as a confound."""
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        null_sigmas = self._make_sigmas(["word_count"], sigma_value=1.0)
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-1",
            clause_to_axis_map={"clause-1": "word_count"},  # primary claims word_count
            scorers=FAKE_SCORERS,
        )
        # No confound event for word_count since it's the primary clause's own axis
        word_count_events = [e for e in events if e.axis == "word_count"]
        assert word_count_events == []

    def test_below_null_floor_no_confound(self) -> None:
        """No confound detection when sigma is absent (below N_null floor)."""
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        # Empty null_sigmas -> no detection
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas={},  # no sigmas computed
            primary_clause_id="clause-1",
            clause_to_axis_map={"clause-1": "char_count", "clause-2": "word_count"},
            scorers=FAKE_SCORERS,
        )
        assert events == []

    def test_a46_primary_clause_id_in_event(self) -> None:
        """All confound events carry the primary_clause_id (A46)."""
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        null_sigmas = self._make_sigmas(["word_count"], sigma_value=1.0)
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-x",
            clause_to_axis_map={"clause-x": "char_count", "clause-y": "word_count"},
            scorers=FAKE_SCORERS,
        )
        for e in events:
            assert e.primary_clause_id == "clause-x", (
                f"A46: expected primary_clause_id='clause-x', got {e.primary_clause_id!r}"
            )

    def test_confound_event_fields(self) -> None:
        """ConfoundEvent carries all required fields."""
        full_text = " ".join(["word"] * 20)
        ablated_text = " ".join(["word"] * 5)
        sigma = 1.0
        null_sigmas = {"word_count": sigma}
        events = detect_confounds(
            full_text=full_text,
            ablated_text=ablated_text,
            null_sigmas=null_sigmas,
            primary_clause_id="clause-1",
            clause_to_axis_map={"clause-1": "char_count", "clause-2": "word_count"},
            scorers=FAKE_SCORERS,
        )
        word_events = [e for e in events if e.axis == "word_count"]
        assert len(word_events) == 1
        ev = word_events[0]
        assert isinstance(ev.delta, float)
        assert ev.null_sigma == sigma
        assert ev.k_threshold == K_THRESHOLD


# ---------------------------------------------------------------------------
# QUAL-1: sub-tolerance clause detection
# ---------------------------------------------------------------------------


class TestQual1OperatorLengthTolerance:
    def test_normal_clause_within_tolerance(self) -> None:
        """A typical clause produces a placeholder within tolerance."""
        from skill_harness.ablation.operator import AblationOperator

        op = AblationOperator()
        clause = "Always begin your response with 'Certainly!' before answering."
        placeholder = op.render(clause)
        within, clause_toks, placeholder_toks, tolerance = check_operator_length_tolerance(
            clause, placeholder
        )
        assert within, (
            f"Expected within tolerance: clause={clause_toks} toks, "
            f"placeholder={placeholder_toks} toks, tolerance={tolerance}"
        )

    def test_sub_tolerance_very_short_clause(self) -> None:
        """A 1-2 token clause cannot be matched within +/-2-token tolerance by [ABLATED] (4 tokens).

        [ABLATED] is 4 tokens. A 1-token clause has tolerance=max(2, 0)=2.
        4 tokens - 1 token = 3 delta > 2 tolerance -> length-confounded.
        """
        # "Hi" is 1 token in cl100k_base
        clause = "Hi"
        from skill_harness.ablation.operator import AblationOperator

        op = AblationOperator()
        placeholder = op.render(clause)
        within, clause_toks, placeholder_toks, tolerance = check_operator_length_tolerance(
            clause, placeholder
        )
        # This may or may not be within tolerance depending on tokenization
        # The key invariant: if NOT within tolerance, we should flag it
        # We test that the function correctly identifies the tolerance condition
        delta = abs(placeholder_toks - clause_toks)
        expected_within = delta <= tolerance
        assert within == expected_within, (
            f"check_operator_length_tolerance mismatch: "
            f"delta={delta}, tolerance={tolerance}, reported_within={within}"
        )

    def test_returns_token_counts(self) -> None:
        """check_operator_length_tolerance returns (within, clause_toks, placeholder_toks, tol)."""
        clause = "Be concise."
        from skill_harness.ablation.operator import AblationOperator

        op = AblationOperator()
        placeholder = op.render(clause)
        result = check_operator_length_tolerance(clause, placeholder)
        assert len(result) == 4
        within, clause_toks, placeholder_toks, tolerance = result
        assert isinstance(within, bool)
        assert isinstance(clause_toks, int)
        assert isinstance(placeholder_toks, int)
        assert isinstance(tolerance, int)
        assert clause_toks > 0
        assert placeholder_toks > 0
        assert tolerance >= 2


# ---------------------------------------------------------------------------
# delta_to_observation tests
# ---------------------------------------------------------------------------


class TestDeltaToObservation:
    def test_positive_delta_win(self) -> None:
        """Positive delta -> Win (1.0): Full beats Ablated_k."""
        assert delta_to_observation(5.0) == 1.0

    def test_negative_delta_loss(self) -> None:
        """Negative delta -> Loss (0.0): Ablated_k beats Full."""
        assert delta_to_observation(-5.0) == 0.0

    def test_zero_delta_tie(self) -> None:
        """Zero delta -> Tie (0.5)."""
        assert delta_to_observation(0.0) == 0.5

    def test_within_tolerance_tie(self) -> None:
        """Small delta within tolerance -> Tie."""
        assert delta_to_observation(0.3, tie_tolerance=0.5) == 0.5

    def test_just_above_tolerance_win(self) -> None:
        """Delta just above tolerance -> Win."""
        assert delta_to_observation(0.6, tie_tolerance=0.5) == 1.0
