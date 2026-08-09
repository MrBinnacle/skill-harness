"""Coverage calibration: legacy posterior CI (#164) + anytime-valid CS (#187).

Offline, seeded, deterministic. Two estimands share the sequential stopper:

1. **Legacy posterior interval** (characterization of #164 finding):
   ``fit_skill`` unpooled Beta(1+w, 1+n-w) equal-tailed 95% credible interval.
   Grid remains null/small/large at pinned seeds; measured rates 0.940 / 0.882 /
   0.982 must still reproduce. Strict xfails remain **only** on this legacy
   characterization (``small``, ``large``), never on the production CS.

2. **Production confidence sequence** (#187):
   ``betting_confidence_sequence`` (predictable-plugin hedged CS). Dense grid
   p in {0.05, 0.25, 0.50, 0.58, 0.60, 0.62, 0.65, 0.75, 0.85, 0.95} x
   tie rates {0%, 20%, 50%}. Contract: coverage >= registered lower tolerance
   at every grid point (overcoverage is NOT a failure). Width metrics
   (median, p90) are recorded for the report; they never reject valid
   overcoverage.

## Sequential-stopping requirement

Each replication generates observations through the production stopper
(``N_MIN=8``, ``N_INC=4``, ``N_MAX=40``). Ties: with probability ``tie_rate``
emit 0.5; otherwise Bernoulli(p) on {0, 1}.

## Compute budget

Each dense-grid cell is computed **at most once** at module scope (shared
cache) plus at most one independent recompute for the determinism assertion.
The dense suite is a separate CI job (see ``.github/workflows/ci.yml``) so
the matrix cell's 15-minute cap is not raised.
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
from skill_harness.aggregation.confidence_sequence import (
    betting_confidence_sequence,
)
from skill_harness.aggregation.fit import ClauseObservations, fit_skill
from skill_harness.aggregation.two_arm import two_arm_gate

# ---------------------------------------------------------------------------
# Registered constants — do not retune on coverage misses
# ---------------------------------------------------------------------------

N_REPS = 500
SEED = 164_2026_08_09  # issue #164, deterministic (legacy characterization)
SEED_CS = 187_2026_08_09  # issue #187 dense CS grid
NOMINAL_COVERAGE = 0.95

# Legacy #164 planted clause win-rates (null / small / large). Seed offset = grid index.
EFFECT_GRID: tuple[tuple[str, float], ...] = (
    ("null", 0.50),
    ("small", 0.65),
    ("large", 0.85),
)

# #187 dense CS grid
CS_P_GRID: tuple[float, ...] = (
    0.05,
    0.25,
    0.50,
    0.58,
    0.60,
    0.62,
    0.65,
    0.75,
    0.85,
    0.95,
)
CS_TIE_RATES: tuple[float, ...] = (0.0, 0.20, 0.50)

# Two-arm side-channel (pipeline exercise; not the coverage estimand).
CONTROL_P = 0.50
DELTA = 0.1
PROB_THRESHOLD = 0.95

# Central 95% band of Binomial(N_REPS, NOMINAL_COVERAGE) — see module docstring.
COV_COUNT_LO = int(binom.ppf(0.025, N_REPS, NOMINAL_COVERAGE))
COV_COUNT_HI = int(binom.ppf(0.975, N_REPS, NOMINAL_COVERAGE))

# CS contract: coverage count must be >= lower edge of the binomial band.
# Overcoverage (above COV_COUNT_HI) is NOT a failure for the CS.
CS_COV_COUNT_LO = COV_COUNT_LO  # 465

_REPORT = Path(__file__).resolve().parent.parent / "docs" / "assurance" / "calibration-report.md"

# Grid points whose measured *legacy posterior* coverage falls outside the band.
# Findings, not math changes. Strict xfail ONLY on legacy characterization.
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


def _run_arm_sequential(
    rng: np.random.Generator,
    p: float,
    *,
    tie_rate: float = 0.0,
) -> tuple[StopDecision, list[float]]:
    """Draw observations through the real sequential stopper; return decision + path."""
    acc = BetaBinomialAccumulator()
    next_at = N_MIN
    decision: StopDecision | None = None
    path: list[float] = []
    while acc.n < N_MAX:
        target = min(next_at, N_MAX)
        while acc.n < target:
            if tie_rate > 0.0 and float(rng.random()) < tie_rate:
                obs = 0.5
            else:
                obs = 1.0 if float(rng.random()) < p else 0.0
            acc.add(obs)
            path.append(obs)
        decision = acc.check_stop()
        if decision.should_stop:
            return decision, path
        next_at = next_check_at(acc.n)
        if next_at > N_MAX:
            break
    if decision is None:
        decision = acc.check_stop()
    return decision, path


@dataclass(frozen=True)
class GridPointResult:
    """Coverage summary for one planted-effect grid point (legacy posterior)."""

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


@dataclass(frozen=True)
class CSGridPointResult:
    """Coverage + width summary for one CS dense-grid cell."""

    label: str
    planted_p: float
    tie_rate: float
    n_reps: int
    seed: int
    coverage_count: int
    coverage_rate: float
    cov_count_lo: int
    stopping_reason_counts: dict[str, int]
    mean_n_planted: float
    median_width: float
    p90_width: float


def run_calibration_grid_point(
    label: str,
    planted_p: float,
    *,
    n_reps: int = N_REPS,
    seed: int,
) -> GridPointResult:
    """Run ``n_reps`` sequential replications at one planted rate; score legacy CI coverage."""
    rng = np.random.default_rng(seed)
    covered = 0
    stopping_reason_counts: Counter[str] = Counter()
    two_arm_outcome_counts: Counter[str] = Counter()
    n_sum = 0

    for _ in range(n_reps):
        planted, _path = _run_arm_sequential(rng, planted_p)
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
        control, _ = _run_arm_sequential(rng, CONTROL_P)
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


def run_cs_grid_point(
    label: str,
    planted_p: float,
    tie_rate: float,
    *,
    n_reps: int = N_REPS,
    seed: int,
    cs_fn: object = betting_confidence_sequence,
) -> CSGridPointResult:
    """Sequential replications scoring the production (or poison) CS coverage.

    Estimand is the observation mean under the DGP
    ``X = 0.5 w.p. tie_rate, else Bern(planted_p)``, i.e.
    ``mu = tie_rate * 0.5 + (1 - tie_rate) * planted_p``. The CS targets the
    mean of bounded observations, not a latent Bernoulli parameter.
    """
    true_mean = tie_rate * 0.5 + (1.0 - tie_rate) * planted_p
    rng = np.random.default_rng(seed)
    covered = 0
    stopping_reason_counts: Counter[str] = Counter()
    n_sum = 0
    widths: list[float] = []

    for _ in range(n_reps):
        planted, path = _run_arm_sequential(rng, planted_p, tie_rate=tie_rate)
        reason = planted.stopping_reason
        assert reason is not None
        stopping_reason_counts[reason.value] += 1
        n_sum += planted.n_samples
        assert len(path) == planted.n_samples

        cs = cs_fn(path)  # type: ignore[operator]
        if cs.lo <= true_mean <= cs.hi:
            covered += 1
        widths.append(float(cs.hi - cs.lo))

    widths_arr = np.asarray(widths, dtype=float)
    return CSGridPointResult(
        label=label,
        planted_p=planted_p,
        tie_rate=tie_rate,
        n_reps=n_reps,
        seed=seed,
        coverage_count=covered,
        coverage_rate=covered / n_reps,
        cov_count_lo=int(binom.ppf(0.025, n_reps, NOMINAL_COVERAGE)),
        stopping_reason_counts=dict(stopping_reason_counts),
        mean_n_planted=n_sum / n_reps,
        median_width=float(np.median(widths_arr)),
        p90_width=float(np.percentile(widths_arr, 90)),
    )


def run_full_calibration(
    *,
    n_reps: int = N_REPS,
    master_seed: int = SEED,
) -> tuple[GridPointResult, ...]:
    """Run every legacy grid point with ``master_seed + grid_index`` child seeds."""
    return tuple(
        run_calibration_grid_point(
            label,
            planted_p,
            n_reps=n_reps,
            seed=master_seed + offset,
        )
        for offset, (label, planted_p) in enumerate(EFFECT_GRID)
    )


def run_full_cs_calibration(
    *,
    n_reps: int = N_REPS,
    master_seed: int = SEED_CS,
    cs_fn: object = betting_confidence_sequence,
) -> tuple[CSGridPointResult, ...]:
    """Dense CS grid; child seed = master + flat index."""
    results: list[CSGridPointResult] = []
    idx = 0
    for tie_rate in CS_TIE_RATES:
        for p in CS_P_GRID:
            label = f"p{p:.2f}_tie{int(tie_rate * 100):02d}"
            results.append(
                run_cs_grid_point(
                    label,
                    p,
                    tie_rate,
                    n_reps=n_reps,
                    seed=master_seed + idx,
                    cs_fn=cs_fn,
                )
            )
            idx += 1
    return tuple(results)


# Shared caches — each grid computed at most once per process (+ one recompute
# for determinism). Keeps the dense suite inside CI budget.
_FULL_CALIBRATION_CACHE: tuple[GridPointResult, ...] | None = None
_FULL_CS_CALIBRATION_CACHE: tuple[CSGridPointResult, ...] | None = None


def _cached_full_calibration() -> tuple[GridPointResult, ...]:
    global _FULL_CALIBRATION_CACHE
    if _FULL_CALIBRATION_CACHE is None:
        _FULL_CALIBRATION_CACHE = run_full_calibration()
    return _FULL_CALIBRATION_CACHE


def _cached_full_cs_calibration() -> tuple[CSGridPointResult, ...]:
    global _FULL_CS_CALIBRATION_CACHE
    if _FULL_CS_CALIBRATION_CACHE is None:
        _FULL_CS_CALIBRATION_CACHE = run_full_cs_calibration()
    return _FULL_CS_CALIBRATION_CACHE


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
# Legacy posterior coverage harness (parametrized per grid point) — #164
# ---------------------------------------------------------------------------


def _coverage_mark(label: str) -> pytest.MarkDecorator | None:
    if label in _XFAIL_OUTSIDE_BAND:
        return pytest.mark.xfail(
            strict=True,
            reason=(
                "finding: docs/findings/aggregation-ci-coverage-under-sequential-stop.md "
                f"(grid point {label!r}; severity WRONG_NUMBER; legacy posterior only)"
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
    """N=500 sequential replications: legacy posterior CI coverage band.

    Tolerance arithmetic (see module docstring)::

        pi = 0.95
        lo = binom.ppf(0.025, 500, 0.95) = 465
        hi = binom.ppf(0.975, 500, 0.95) = 484
        assert lo <= coverage_count <= hi

    Outside the band -> WRONG_NUMBER finding + xfail on *legacy only*; never
    retune thresholds or aggregation math. Production CS is asserted separately.
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


def test_legacy_posterior_pinned_rates_reproduce() -> None:
    """#164 pinned rates must still reproduce at master seed 164_2026_08_09."""
    results = {r.label: r for r in _cached_full_calibration()}
    assert results["null"].coverage_count == 470  # 0.940
    assert results["small"].coverage_count == 441  # 0.882
    assert results["large"].coverage_count == 491  # 0.982


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

    # #187 additions
    assert "confidence sequence" in text.lower() or "predictable_plugin" in text
    assert "187" in text


# ---------------------------------------------------------------------------
# Helpers exported for tests/test_aggregation_cs_calibration.py (#187)
# ---------------------------------------------------------------------------


def _cs_grid_params() -> list[object]:
    params: list[object] = []
    idx = 0
    for tie_rate in CS_TIE_RATES:
        for p in CS_P_GRID:
            label = f"p{p:.2f}_tie{int(tie_rate * 100):02d}"
            params.append(
                pytest.param(label, p, tie_rate, SEED_CS + idx, id=label),
            )
            idx += 1
    return params


def test_cs_dense_grid_contract() -> None:
    """#187 dense grid shape is locked (full suite lives under calibration mark)."""
    assert CS_P_GRID == (0.05, 0.25, 0.50, 0.58, 0.60, 0.62, 0.65, 0.75, 0.85, 0.95)
    assert CS_TIE_RATES == (0.0, 0.20, 0.50)
