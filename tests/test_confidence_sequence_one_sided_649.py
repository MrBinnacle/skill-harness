"""Tests for #649: the one-sided betting bound's coverage and its relation to the hedged CS."""

from __future__ import annotations

import math
import random
from typing import Literal

import pytest

from skill_harness.aggregation.confidence_sequence import (
    betting_confidence_sequence,
    one_sided_betting_bound,
)

Side = Literal["lower", "upper"]


def _misses(side: Side, draw: str, mean: float, *, n: int, alpha: float, reps: int) -> int:
    rng = random.Random(f"{side}-{draw}-{mean}")
    misses = 0
    for _ in range(reps):
        if draw == "bernoulli":
            xs = [float(rng.random() < mean) for _ in range(n)]
        else:
            xs = [rng.choice((0.0, 0.5, 1.0)) if rng.random() < 0.5 else mean for _ in range(n)]
        bound = one_sided_betting_bound(xs, alpha=alpha, side=side)
        misses += bound > mean if side == "lower" else bound < mean
    return misses


@pytest.mark.parametrize("side", ["lower", "upper"])
@pytest.mark.parametrize("mean", [0.2, 0.5, 0.8])
def test_bernoulli_miscoverage_is_at_most_alpha(side: Side, mean: float) -> None:
    alpha, reps = 0.1, 300
    misses = _misses(side, "bernoulli", mean, n=25, alpha=alpha, reps=reps)
    assert misses / reps <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / reps)


@pytest.mark.parametrize("side", ["lower", "upper"])
def test_half_weight_miscoverage_is_at_most_alpha(side: Side) -> None:
    alpha, reps = 0.1, 300
    misses = _misses(side, "half", 0.5, n=25, alpha=alpha, reps=reps)
    assert misses / reps <= alpha + 3 * math.sqrt(alpha * (1 - alpha) / reps)


@pytest.mark.parametrize("alpha", [0.0209, 0.05, 0.2])
def test_never_looser_than_the_matching_edge_of_the_two_sided_sequence(alpha: float) -> None:
    rng = random.Random(649)
    for _ in range(60):
        xs = [rng.choice((0.0, 0.5, 1.0)) for _ in range(rng.randint(1, 30))]
        two_sided = betting_confidence_sequence(xs, alpha=alpha)
        assert one_sided_betting_bound(xs, alpha=alpha, side="lower") >= two_sided.lo - 1e-12
        assert one_sided_betting_bound(xs, alpha=alpha, side="upper") <= two_sided.hi + 1e-12


def test_all_ones_give_a_positive_lower_bound_and_upper_bound_one() -> None:
    assert one_sided_betting_bound([1.0] * 16, alpha=0.05, side="lower") > 0.6
    assert one_sided_betting_bound([1.0] * 16, alpha=0.05, side="upper") == 1.0


def test_empty_input_is_vacuous() -> None:
    assert one_sided_betting_bound([], side="lower") == 0.0
    assert one_sided_betting_bound([], side="upper") == 1.0


@pytest.mark.parametrize(
    ("xs", "alpha", "side"),
    [([1.2], 0.05, "lower"), ([0.5], 0.0, "lower"), ([0.5], 0.05, "middle")],
)
def test_rejects_bad_input(xs: list[float], alpha: float, side: str) -> None:
    with pytest.raises(ValueError):
        one_sided_betting_bound(xs, alpha=alpha, side=side)  # type: ignore[arg-type]
