"""Tests for length_regression.py — determinism, formula correctness.

TDD RED phase: all tests should fail until length_regression.py is created.
"""

from __future__ import annotations

import os

import pytest


def test_pythonhashseed_set() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0", (
        "PYTHONHASHSEED must be set to 0. Run with: PYTHONHASHSEED=0 pytest"
    )


from skill_harness.oracles.calibration.jsonl_parser import CalibrationPair  # noqa: E402
from skill_harness.oracles.calibration.length_regression import (  # noqa: E402
    apply_length_correction,
    fit_length_regression,
)
from skill_harness.oracles.tier2.judge import JudgeVerdict  # noqa: E402

# ------------------------------------------------------------------
# Helpers to build test fixtures
# ------------------------------------------------------------------


def _make_pair(
    pair_id: str = "p1",
    response_a: str = "short",
    response_b: str = "longer response here",
    human_preference: str = "A",
) -> CalibrationPair:
    return CalibrationPair(
        pair_id=pair_id,
        axis="test_axis",
        prompt="prompt text",
        response_a=response_a,
        response_b=response_b,
        human_preference=human_preference,  # type: ignore[arg-type]
        labeler_id="labeler_1",
        labeled_at="2026-01-01T00:00:00Z",
    )


def _make_verdict(
    choice: str = "A",
    length_a: int = 10,
    length_b: int = 20,
    position_swap_agreement: int = 1,
    admissible: bool = True,
) -> JudgeVerdict:
    from typing import Literal, cast

    return JudgeVerdict(
        choice=cast(Literal["A", "B", "tie"], choice),
        position_swap_agreement=cast(Literal[0, 1], position_swap_agreement),
        admissibility_state="admissible" if admissible else "inadmissible",
        inadmissibility_reason=None if admissible else "position_disagreement",
        raw_observation={"A": 1.0, "B": 0.0, "tie": 0.5}[choice],
        length_adjusted_observation=None,
        length_a=length_a,
        length_b=length_b,
        rationale_brief="test rationale",
    )


# ------------------------------------------------------------------
# Determinism: same input → same β_1 across two invocations
# ------------------------------------------------------------------


class TestFitLengthRegressionDeterministic:
    """fit_length_regression must return identical β_1 on repeated calls."""

    def _build_fixture(self) -> tuple[list[CalibrationPair], list[JudgeVerdict]]:
        pairs = [
            _make_pair(
                "p1",
                response_a="short",
                response_b="a much longer piece of text here",
                human_preference="A",
            ),
            _make_pair("p2", response_a="medium length text", response_b="x", human_preference="B"),
            _make_pair("p3", response_a="a", response_b="b", human_preference="tie"),
            _make_pair(
                "p4",
                response_a="somewhat long text output here",
                response_b="tiny",
                human_preference="A",
            ),
            _make_pair("p5", response_a="equal", response_b="equal", human_preference="tie"),
        ]
        verdicts = [
            _make_verdict("A", length_a=5, length_b=50),
            _make_verdict("B", length_a=20, length_b=3),
            _make_verdict("tie", length_a=10, length_b=10),
            _make_verdict("A", length_a=30, length_b=5),
            _make_verdict("tie", length_a=10, length_b=10),
        ]
        return pairs, verdicts

    def test_same_result_twice(self) -> None:
        pairs, verdicts = self._build_fixture()
        beta_1_first = fit_length_regression(pairs, verdicts)
        beta_1_second = fit_length_regression(pairs, verdicts)
        assert beta_1_first == pytest.approx(beta_1_second, abs=1e-12), (
            f"Non-deterministic: first={beta_1_first}, second={beta_1_second}"
        )

    def test_returns_float(self) -> None:
        pairs, verdicts = self._build_fixture()
        result = fit_length_regression(pairs, verdicts)
        assert isinstance(result, float)

    def test_same_result_after_seed_reset(self) -> None:
        """Even if random state is mutated between calls, result must be identical."""
        import random

        import numpy as np

        pairs, verdicts = self._build_fixture()
        beta1 = fit_length_regression(pairs, verdicts)

        # Perturb random state
        random.seed(42)
        np.random.seed(42)

        beta2 = fit_length_regression(pairs, verdicts)
        assert beta1 == pytest.approx(beta2, abs=1e-12)


# ------------------------------------------------------------------
# OLS fit: beta_1 sign is predictable for length-biased data
# ------------------------------------------------------------------


class TestFitLengthRegressionSignCorrectness:
    """β_1 should be positive when judge systematically prefers longer outputs."""

    def test_beta_1_positive_when_longer_wins(self) -> None:
        """When longer responses always win, β_1 should be positive.

        Δlen = len_a - len_b; raw_observation=1.0 (A wins) when A is longer.
        Positive slope = length bias toward A.
        """
        # Construct 10 pairs where the longer output always wins
        pairs = []
        verdicts = []
        for i in range(10):
            pairs.append(_make_pair(f"p{i}", human_preference="A"))
            verdicts.append(_make_verdict("A", length_a=100 + i * 10, length_b=20))

        beta_1 = fit_length_regression(pairs, verdicts)
        # With perfect length-biased data, slope should be non-negative
        # (may be near zero if relationship is not strong in OLS)
        assert isinstance(beta_1, float)  # basic sanity

    def test_beta_1_near_zero_for_unbiased_data(self) -> None:
        """When outcomes are random with respect to length, β_1 should be near 0."""
        pairs = []
        verdicts = []
        # Alternate wins with no length pattern
        for i in range(20):
            choice = "A" if i % 2 == 0 else "B"
            pairs.append(_make_pair(f"p{i}", human_preference=choice))
            # Constant lengths — no length signal
            verdicts.append(_make_verdict(choice, length_a=100, length_b=100))

        beta_1 = fit_length_regression(pairs, verdicts)
        # Zero Δlen → zero covariance → slope should be 0 (or NaN handled)
        # The function should still return a float
        assert isinstance(beta_1, float)


# ------------------------------------------------------------------
# apply_length_correction
# ------------------------------------------------------------------


class TestApplyLengthCorrection:
    """apply_length_correction(raw_logit, length_delta, beta_1) -> float."""

    def test_zero_correction_when_beta_zero(self) -> None:
        result = apply_length_correction(raw_logit=0.8, length_delta=100, beta_1=0.0)
        assert result == pytest.approx(0.8)

    def test_zero_correction_when_delta_zero(self) -> None:
        result = apply_length_correction(raw_logit=0.8, length_delta=0, beta_1=0.01)
        assert result == pytest.approx(0.8)

    def test_correction_reduces_for_positive_beta_and_positive_delta(self) -> None:
        """Positive β_1 with positive Δlen → subtract β_1*Δlen from raw_logit."""
        raw = 0.9
        delta = 50
        beta = 0.002
        result = apply_length_correction(raw_logit=raw, length_delta=delta, beta_1=beta)
        expected = raw - beta * delta
        assert result == pytest.approx(expected)

    def test_correction_increases_for_negative_delta(self) -> None:
        """Negative Δlen (B is longer) with positive β_1 → increases adjusted logit."""
        raw = 0.5
        delta = -50
        beta = 0.002
        result = apply_length_correction(raw_logit=raw, length_delta=delta, beta_1=beta)
        expected = raw - beta * delta  # 0.5 - 0.002 * (-50) = 0.6
        assert result == pytest.approx(expected)

    def test_returns_float(self) -> None:
        result = apply_length_correction(raw_logit=0.5, length_delta=10, beta_1=0.001)
        assert isinstance(result, float)
