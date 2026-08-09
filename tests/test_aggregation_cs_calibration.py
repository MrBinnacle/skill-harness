"""Dense anytime-valid CS coverage calibration (#187).

Separated from the legacy #164 posterior characterization so CI can run this
suite in its own job without raising the matrix-cell 15-minute cap.
"""

from __future__ import annotations

import pytest
from scipy.stats import binom  # type: ignore[import-untyped]

from skill_harness.ablation.stopping import StoppingReason
from skill_harness.aggregation.confidence_sequence import miscalibrated_nonpredictable_cs
from tests.test_aggregation_calibration import (
    CS_COV_COUNT_LO,
    CS_P_GRID,
    CS_TIE_RATES,
    N_REPS,
    NOMINAL_COVERAGE,
    SEED_CS,
    _cached_full_cs_calibration,
    _cs_grid_params,
    run_cs_grid_point,
    run_full_cs_calibration,
)

pytestmark = pytest.mark.calibration


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Block all network I/O for every test in this module."""


def test_cs_dense_grid_contract() -> None:
    """#187 dense grid: 10 rates x 3 tie rates."""
    assert CS_P_GRID == (0.05, 0.25, 0.50, 0.58, 0.60, 0.62, 0.65, 0.75, 0.85, 0.95)
    assert CS_TIE_RATES == (0.0, 0.20, 0.50)


@pytest.mark.parametrize(("label", "planted_p", "tie_rate", "seed"), _cs_grid_params())
def test_cs_coverage_at_least_lower_tolerance(
    label: str,
    planted_p: float,
    tie_rate: float,
    seed: int,
) -> None:
    """Production CS: coverage count >= binom lower edge; overcoverage OK."""
    result = next(r for r in _cached_full_cs_calibration() if r.label == label)
    assert result.seed == seed
    assert result.planted_p == planted_p
    assert result.tie_rate == tie_rate
    assert result.n_reps == N_REPS
    assert sum(result.stopping_reason_counts.values()) == N_REPS
    assert set(result.stopping_reason_counts).issubset({r.value for r in StoppingReason})

    x = result.coverage_count
    assert x >= CS_COV_COUNT_LO, (
        f"CS grid={label!r} p={planted_p} tie={tie_rate}: coverage count {x} "
        f"below lower tolerance {CS_COV_COUNT_LO} (rate={result.coverage_rate:.4f}). "
        f"median_width={result.median_width:.4f} p90_width={result.p90_width:.4f}."
    )
    assert 0.0 <= result.median_width <= 1.0
    assert result.median_width <= result.p90_width <= 1.0


def test_cs_calibration_is_deterministic() -> None:
    """Dense CS grid is bit-identical across independent recomputes."""
    a = _cached_full_cs_calibration()
    b = run_full_cs_calibration()
    assert a == b


def test_cs_grid_exercises_stopping_reasons() -> None:
    """Across the dense grid, multiple StoppingReason values appear."""
    seen: set[str] = set()
    for r in _cached_full_cs_calibration():
        seen.update(r.stopping_reason_counts)
    expected = {s.value for s in StoppingReason}
    assert seen.issubset(expected)
    assert "passed" in seen or "failed" in seen or "underpowered_nmax" in seen
    assert len(seen) >= 2


def test_poison_nonpredictable_cs_breaches_coverage() -> None:
    """Harness catches invalid sequences: lookahead poison goes RED on coverage."""
    n_reps = 200
    seed = SEED_CS + 999
    poison = run_cs_grid_point(
        "poison_p0.65",
        0.65,
        0.0,
        n_reps=n_reps,
        seed=seed,
        cs_fn=miscalibrated_nonpredictable_cs,
    )
    lo = int(binom.ppf(0.025, n_reps, NOMINAL_COVERAGE))
    assert poison.coverage_count < lo, (
        f"poison CS unexpectedly covered {poison.coverage_count}/{n_reps} "
        f"(lower tol {lo}); harness cannot demonstrate RED on invalid sequences."
    )
