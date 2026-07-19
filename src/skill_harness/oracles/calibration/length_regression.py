"""AlpacaEval-2 length-controlled scoring (A35 observation-time half).

``fit_length_regression`` fits OLS to estimate β_1 — the linear dependence
of judge verdicts on Δlen = len(response_a) - len(response_b).

``apply_length_correction`` applies the correction:
    adjusted_logit = raw_logit - β_1 x Δlen

References:
    Dubois et al. (2024). Length-Controlled AlpacaEval. arXiv:2404.04475.
    statsmodels OLS: preferred over scipy.linregress for output statistics.

Determinism:
    statsmodels OLS is fully deterministic for the same input data.
    No random state is needed or used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import statsmodels.api as sm

if TYPE_CHECKING:
    from skill_harness.oracles.calibration.jsonl_parser import CalibrationPair
    from skill_harness.oracles.tier2.judge import JudgeVerdict

# C2 fix: inadmissibility reasons whose choice/raw_observation are hardcoded
# sentinels — no judge call completed (injection short-circuit, judge.py:270-283)
# or the response was truncated/malformed (judge.py:301-311, 323-334) — carry no
# real length-vs-verdict signal and must never enter the OLS fit below.
# NOT included: "position_disagreement" — that reason marks a REAL completed
# judge call (both AB and BA calls succeeded; the choice/raw_observation are
# genuine model output) that merely disagreed under position swap. Excluding it
# is the deliberate, documented behavior in fit_length_regression's docstring.
SENTINEL_INADMISSIBILITY_REASONS: frozenset[str] = frozenset(
    {"suspected_injection", "judge_response_malformed"}
)


def fit_length_regression(
    pairs: list[CalibrationPair],
    judge_verdicts: list[JudgeVerdict],
) -> float:
    """Fit OLS regression of verdicts on Δlen and return β_1.

    Parameters
    ----------
    pairs:
        List of ``CalibrationPair`` objects (used for token lengths from verdicts).
    judge_verdicts:
        List of ``JudgeVerdict`` objects with ``length_a``, ``length_b``, and
        ``raw_observation`` fields.  Indices must correspond to ``pairs``.

    Returns
    -------
    float
        β_1 coefficient — the slope of raw_observation on Δlen.
        Returns 0.0 if the regression cannot be fit (e.g., zero variance in Δlen).

    Notes
    -----
    - Fits: raw_observation = β_0 + β_1 x (length_a - length_b)
    - Uses statsmodels OLS with a constant term added via sm.add_constant.
    - Deterministic: same input always produces the same β_1.
    - Position-inconsistent verdicts (inadmissibility_reason ==
      "position_disagreement") are NOT excluded — the regression describes the
      judge's overall behavior including position-inconsistent calls.
      (Exclusion would bias the β_1 estimate by removing length-extreme pairs.)
    - Sentinel verdicts ARE excluded (C2 fix): inadmissibility_reason in
      ``SENTINEL_INADMISSIBILITY_REASONS`` ("suspected_injection",
      "judge_response_malformed") means no real judge call completed — their
      choice and raw_observation=0.0 are hardcoded placeholders, not judge
      signal, and would corrupt the β_1 estimate with fabricated zeros.
    """
    if len(pairs) != len(judge_verdicts):
        raise ValueError(
            f"pairs ({len(pairs)}) and judge_verdicts ({len(judge_verdicts)}) must have "
            "the same length"
        )

    admissible = [
        (p, v)
        for p, v in zip(pairs, judge_verdicts, strict=True)
        if v.inadmissibility_reason not in SENTINEL_INADMISSIBILITY_REASONS
    ]

    if len(admissible) < 2:
        return 0.0

    delta_len = [float(v.length_a - v.length_b) for _p, v in admissible]
    outcomes = [v.raw_observation for _p, v in admissible]

    # Check for zero variance in Δlen (degenerate case — all pairs same length)
    if max(delta_len) == min(delta_len):
        return 0.0

    # OLS: outcomes ~ β_0 + β_1 x delta_len
    # sm.add_constant adds a column of 1s for the intercept
    x = sm.add_constant(delta_len, has_constant="add")
    model = sm.OLS(outcomes, x)
    result = model.fit()

    # result.params[0] is β_0 (intercept), result.params[1] is β_1 (slope)
    beta_1: float = float(result.params[1])
    return beta_1


def apply_length_correction(
    raw_logit: float,
    length_delta: int,
    beta_1: float,
) -> float:
    """Apply AlpacaEval-2 length correction to a raw logit/observation.

    Per A35:
        adjusted_logit = raw_logit - β_1 x Δlen

    Parameters
    ----------
    raw_logit:
        Raw observation (e.g., 1.0 for A wins, 0.5 for tie, 0.0 for B wins).
    length_delta:
        Δlen = length_a - length_b (in tokens, from JudgeVerdict).
    beta_1:
        Length regression coefficient from ``fit_length_regression``.

    Returns
    -------
    float
        Length-adjusted observation.
    """
    return raw_logit - beta_1 * length_delta
