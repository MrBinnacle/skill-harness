"""Coverage calibration by simulation for aggregation 95% intervals (#164).

Offline, seeded, deterministic. Extends the one-shot planted synthetic control
into a repeated quantitative property: plant known clause-level win-rates on a
grid (null / small / large), drive each replication through the production
sequential stopper, run the stopped ``(w, n)`` through ``fit_skill`` (the
interval producer used by ``engine.aggregate_skill``), and measure how often the
95% credible interval contains the planted truth.

## What is driven

- Observation generation mirrors ``ablation/runner.py``:
  ``BetaBinomialAccumulator.add`` → ``check_stop`` / ``next_check_at``
  (``N_MIN=8``, ``N_INC=4``, ``N_MAX=40``). No fixed-n draws.
- ``fit_skill`` (``aggregation/fit.py``) — unpooled Beta(1+w, 1+n-w) 95%
  equal-tailed credible interval (K=1 < ``K_MIN_FOR_EB``).
- ``two_arm_gate`` (``aggregation/two_arm.py``) — secondary pipeline exercise:
  planted arm vs an independent control arm at Bernoulli(0.5), DIF K7 constants
  ``delta=0.1``, ``prob_threshold=0.95``. Recorded for the report; not the
  coverage estimand (the gate emits directional posterior mass, not a CI).
- ``aggregate_skill`` (``engine.py``) is the DB orchestrator over already-stopped
  verdicts; its interval numerics are delegated to ``fit_skill``. This harness
  therefore drives ``fit_skill`` directly (same surface A/A #163 and differential
  #165 use for pure numerics).

## Planted-effect grid (clause win-rate estimand)

| Label | Planted ``p`` | Interpretation |
| --- | --- | --- |
| ``null`` | 0.50 | chance-level rate (exact null vs 0.5) |
| ``small`` | 0.65 | modest lift above the locked 0.60 pass threshold |
| ``large`` | 0.85 | large, early-stop-prone rate |

## Tolerance arithmetic (N=500, nominal coverage = 0.95)

Under a well-calibrated 95% interval the coverage count ``X`` is modelled as
``X ~ Binomial(N=500, π=0.95)``. The acceptance band is the central 95%
probability mass of that binomial (exact, via ``scipy.stats.binom.ppf``):

    lo = binom.ppf(0.025, n=500, p=0.95)   # = 465
    hi = binom.ppf(0.975, n=500, p=0.95)   # = 484
    E[X] = 500 * 0.95 = 475

Assert ``lo <= X <= hi`` **per grid point**. This is a Monte-Carlo check that
observed coverage sits near nominal — not a claim that equal-tailed Beta
credible intervals are exact frequentist 95% CIs at every (n, p), nor that
optional stopping preserves coverage. If ``X`` falls outside, do **not** retune
aggregation math or stopper thresholds: file a finding (severity WRONG_NUMBER),
xfail with a pointer, record seed + count + ``StoppingReason`` histogram.

## Sequential-stopping requirement

Each replication generates observations by:

    acc = BetaBinomialAccumulator()
    next_at = N_MIN
    while True:
        while acc.n < next_at and acc.n < N_MAX:
            acc.add(Bernoulli(p) in {0.0, 1.0})  # no ties in this harness
        decision = acc.check_stop()
        if decision.should_stop:
            break
        next_at = next_check_at(acc.n)

Stopped ``(w, n)`` feed ``fit_skill``. Each planted arm's ``StoppingReason`` is
tallied for the report (control-arm reasons for the two-arm side-channel are
tallied separately and not mixed into the coverage arm histogram).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import binom  # type: ignore[import-untyped]

from skill_harness.ablation.stopping import (
    N_MAX,
    N_MIN,
    BetaBinomialAccumulator,
    StopDecision,
    StoppingReason,
    next_check_at,
)
from skill_harness.aggregation.fit import ClauseObservations, fit_skill
from skill_harness.aggregation.two_arm import two_arm_gate

# ---------------------------------------------------------------------------
# Registered constants — do not retune on coverage misses
# ---------------------------------------------------------------------------

N_REPS = 500
SEED = 164_2026_08_09  # issue #164, deterministic
NOMINAL_COVERAGE = 0.95

# Planted clause win-rates (null / small / large). Seed offset = grid index.
EFFECT_GRID: tuple[tuple[str, float], ...] = (
    ("null", 0.50),
    ("small", 0.65),
    ("large", 0.85),
)

# Two-arm side-channel (pipeline exercise; not the coverage estimand).
CONTROL_P = 0.50
DELTA = 0.1
PROB_THRESHOLD = 0.95

# Central 95% band of Binomial(N_REPS, NOMINAL_COVERAGE) — see module docstring.
COV_COUNT_LO = int(binom.ppf(0.025, N_REPS, NOMINAL_COVERAGE))
COV_COUNT_HI = int(binom.ppf(0.975, N_REPS, NOMINAL_COVERAGE))

_REPORT = Path(__file__).resolve().parent.parent / "docs" / "assurance" / "calibration-report.md"

# Grid points whose measured coverage falls outside the binomial band under the
# locked sequential stopper + unpooled Beta CI. Findings, not math changes.
# See docs/findings/aggregation-ci-coverage-under-sequential-stop.md
_XFAIL_OUTSIDE_BAND: frozenset[str] = frozenset({"small", "large"})


# ---------------------------------------------------------------------------
# Offline discipline (pytest-socket)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(socket_disabled: None) -> None:
    """Block all network I/O for every test in this module."""


# ---------------------------------------------------------------------------
# Sequential arm simulation (mirrors ablation/runner.py stop loop)
# ---------------------------------------------------------------------------


def _run_arm_sequential(rng: np.random.Generator, p: float) -> StopDecision:
    """Draw Bernoulli(p) observations through the real sequential stopper."""
    acc = BetaBinomialAccumulator()
    next_at = N_MIN
    decision: StopDecision | None = None
    while acc.n < N_MAX:
        target = min(next_at, N_MAX)
        while acc.n < target:
            obs = 1.0 if float(rng.random()) < p else 0.0
            acc.add(obs)
        decision = acc.check_stop()
        if decision.should_stop:
            return decision
        next_at = next_check_at(acc.n)
        if next_at > N_MAX:
            break
    if decision is None:
        decision = acc.check_stop()
    return decision


@dataclass(frozen=True)
class GridPointResult:
    """Coverage summary for one planted-effect grid point."""

    label: str
    planted_p: float
    n_reps: int
    seed: int
    coverage_count: int
    coverage_rate: float
    cov_count_lo: int
    cov_count_hi: int
    inside_tolerance: bool
    stopping_reason_counts: dict[str, int]
    two_arm_outcome_counts: dict[str, int]
    mean_n_planted: float


def run_calibration_grid_point(
    label: str,
    planted_p: float,
    *,
    n_reps: int = N_REPS,
    seed: int,
) -> GridPointResult:
    """Run ``n_reps`` sequential replications at one planted rate; score CI coverage."""
    rng = np.random.default_rng(seed)
    covered = 0
    stopping_reason_counts: Counter[str] = Counter()
    two_arm_outcome_counts: Counter[str] = Counter()
    n_sum = 0

    for _ in range(n_reps):
        planted = _run_arm_sequential(rng, planted_p)
        reason = planted.stopping_reason
        assert reason is not None
        stopping_reason_counts[reason.value] += 1
        n_sum += planted.n_samples

        w = planted.w_accumulator
        n = planted.n_samples
        assert n >= 1
        assert 0.0 <= w <= float(n)

        fit = fit_skill([ClauseObservations(clause_id="planted", w=w, n=n)])
        assert fit.aggregation_method == "unpooled"
        assert len(fit.posteriors) == 1
        post = fit.posteriors[0]
        if post.credible_interval_lo <= planted_p <= post.credible_interval_hi:
            covered += 1

        # Side-channel: two_arm_gate on planted vs independent null control.
        control = _run_arm_sequential(rng, CONTROL_P)
        gate = two_arm_gate(
            int(planted.w_accumulator),
            planted.n_samples,
            int(control.w_accumulator),
            control.n_samples,
            delta=DELTA,
            prob_threshold=PROB_THRESHOLD,
        )
        two_arm_outcome_counts[gate.outcome.value] += 1

    lo = int(binom.ppf(0.025, n_reps, NOMINAL_COVERAGE))
    hi = int(binom.ppf(0.975, n_reps, NOMINAL_COVERAGE))
    return GridPointResult(
        label=label,
        planted_p=planted_p,
        n_reps=n_reps,
        seed=seed,
        coverage_count=covered,
        coverage_rate=covered / n_reps,
        cov_count_lo=lo,
        cov_count_hi=hi,
        inside_tolerance=lo <= covered <= hi,
        stopping_reason_counts=dict(stopping_reason_counts),
        two_arm_outcome_counts=dict(two_arm_outcome_counts),
        mean_n_planted=n_sum / n_reps,
    )


def run_full_calibration(
    *,
    n_reps: int = N_REPS,
    master_seed: int = SEED,
) -> tuple[GridPointResult, ...]:
    """Run every grid point with ``master_seed + grid_index`` child seeds."""
    return tuple(
        run_calibration_grid_point(
            label,
            planted_p,
            n_reps=n_reps,
            seed=master_seed + offset,
        )
        for offset, (label, planted_p) in enumerate(EFFECT_GRID)
    )


# The full grid costs minutes per computation on the Windows CI runners, and the
# test job has a 15-minute cap (ci.yml `timeout-minutes`) that the py3.12 cell
# exceeded when this module computed the grid six times. Compute it once per
# module and share; the determinism test still performs one independent
# recompute, so the cache never hides nondeterminism.
_FULL_CALIBRATION_CACHE: tuple[GridPointResult, ...] | None = None


def _cached_full_calibration() -> tuple[GridPointResult, ...]:
    global _FULL_CALIBRATION_CACHE
    if _FULL_CALIBRATION_CACHE is None:
        _FULL_CALIBRATION_CACHE = run_full_calibration()
    return _FULL_CALIBRATION_CACHE


# ---------------------------------------------------------------------------
# Tolerance constants pin
# ---------------------------------------------------------------------------


def test_binomial_tolerance_constants() -> None:
    """Documented lo/hi match exact Binomial(500, 0.95) central 95% mass."""
    assert pytest.approx(0.95) == NOMINAL_COVERAGE
    assert COV_COUNT_LO == 465
    assert COV_COUNT_HI == 484
    assert int(binom.ppf(0.025, N_REPS, NOMINAL_COVERAGE)) == COV_COUNT_LO
    assert int(binom.ppf(0.975, N_REPS, NOMINAL_COVERAGE)) == COV_COUNT_HI


def test_effect_grid_includes_null_small_large() -> None:
    """Grid contracts null / small / large planted rates in increasing order."""
    labels = [lab for lab, _ in EFFECT_GRID]
    assert labels == ["null", "small", "large"]
    rates = [p for _, p in EFFECT_GRID]
    assert rates[0] == pytest.approx(0.50)
    assert rates[1] == pytest.approx(0.65)
    assert rates[2] == pytest.approx(0.85)
    assert rates == sorted(rates)


# ---------------------------------------------------------------------------
# Core coverage harness (parametrized per grid point)
# ---------------------------------------------------------------------------


def _coverage_mark(label: str) -> pytest.MarkDecorator | None:
    if label in _XFAIL_OUTSIDE_BAND:
        return pytest.mark.xfail(
            strict=True,
            reason=(
                "finding: docs/findings/aggregation-ci-coverage-under-sequential-stop.md "
                f"(grid point {label!r}; severity WRONG_NUMBER)"
            ),
        )
    return None


def _grid_params() -> list[object]:
    params: list[object] = []
    for offset, (label, planted_p) in enumerate(EFFECT_GRID):
        marks = []
        m = _coverage_mark(label)
        if m is not None:
            marks.append(m)
        params.append(
            pytest.param(label, planted_p, SEED + offset, id=label, marks=marks),
        )
    return params


@pytest.mark.parametrize(("label", "planted_p", "seed"), _grid_params())
def test_coverage_within_binomial_tolerance_per_grid_point(
    label: str,
    planted_p: float,
    seed: int,
) -> None:
    """N=500 sequential replications: CI coverage inside Binomial(500, 0.95) band.

    Tolerance arithmetic (see module docstring)::

        pi = 0.95
        lo = binom.ppf(0.025, 500, 0.95) = 465
        hi = binom.ppf(0.975, 500, 0.95) = 484
        assert lo <= coverage_count <= hi

    Outside the band -> WRONG_NUMBER finding + xfail; never retune thresholds
    or aggregation math.
    """
    result = next(r for r in _cached_full_calibration() if r.label == label)

    assert result.n_reps == N_REPS
    assert result.seed == seed
    assert result.planted_p == planted_p
    assert sum(result.stopping_reason_counts.values()) == N_REPS
    assert set(result.stopping_reason_counts).issubset({r.value for r in StoppingReason})
    assert sum(result.two_arm_outcome_counts.values()) == N_REPS

    x = result.coverage_count
    assert COV_COUNT_LO <= x <= COV_COUNT_HI, (
        f"grid={label!r} planted_p={planted_p}: coverage count {x} outside binomial "
        f"tolerance [{COV_COUNT_LO}, {COV_COUNT_HI}] for Binomial({N_REPS}, "
        f"{NOMINAL_COVERAGE}). rate={result.coverage_rate:.4f}; seed={seed}. "
        "Do not retune aggregation math — file docs/findings with severity WRONG_NUMBER."
    )


def test_calibration_harness_is_deterministic() -> None:
    """Same seeds yield bit-identical counts (no network, no wall clock).

    Compares the shared cached grid against one genuinely independent
    recompute, the one place the cache is deliberately bypassed.
    """
    a = _cached_full_calibration()
    b = run_full_calibration()
    assert a == b


def test_calibration_report_records_coverage_table() -> None:
    """docs/assurance/calibration-report.md records the coverage table + reasons."""
    assert _REPORT.is_file(), f"missing calibration report at {_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "coverage" in text.lower()
    assert "0.95" in text or "95%" in text
    assert "binom" in text.lower() or "Binomial" in text
    assert "500" in text
    assert "StoppingReason" in text or "stopping_reason" in text
    assert str(SEED) in text or "164_2026_08_09" in text
    for label, planted_p in EFFECT_GRID:
        assert label in text
        assert str(planted_p) in text or f"{planted_p:.2f}" in text

    results = _cached_full_calibration()
    for result in results:
        assert str(result.coverage_count) in text
        for reason in result.stopping_reason_counts:
            assert reason in text
