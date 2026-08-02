"""A36 cost projection for the calibrate command.

Computes projected token counts and USD cost for a calibration run using
the A36 formula with prompt-caching discipline.

Formula (A36 verbatim):
    N_calls = N_pairs x 2  (position swap per A6)
    T_in_uncached_first_call = system_prompt_tokens + tool_schema_tokens
                               + candidate_output_avg_tokens * 2
    T_in_cached_per_call = candidate_output_avg_tokens * 2  (unique tail)
    T_in_cache_read = (N_calls - 1) x (system_prompt_tokens + tool_schema_tokens)
    T_out = N_calls x 50  (choice + rationale estimate)
    cost = T_in_uncached_first_call x input_price_per_M / 1_000_000
         + T_in_cache_read x cache_read_price_per_M / 1_000_000
         + sum(T_in_cached_per_call for all N calls) x input_price_per_M / 1_000_000
         + T_out x output_price_per_M / 1_000_000

Stat projections (bayesian-eval-discipline):
    est_se = sqrt(0.7 * 0.3 / N_pairs)   (normal approximation at threshold 0.7)
    est_ci_95_width = 2 * 1.96 * est_se

Budget ceiling (A36):
    DAILY_CAP_HARD_CEILING_USD = 100.0
    Override via SKILL_HARNESS_DAILY_CAP_OVERRIDE=1 env var.
"""

from __future__ import annotations

import math
import os

from pydantic import BaseModel, ConfigDict

from skill_harness.ablation.subject import PRICE_PER_MTOK

# ---------------------------------------------------------------------------
# Pricing dict — only the 3 judge models we actually use (claude-api verified)
# ---------------------------------------------------------------------------
# F3 fix: this used to be a second, hand-maintained copy of the rates in
# skill_harness.ablation.subject.PRICE_PER_MTOK (one overlapping entry,
# claude-sonnet-4-6, which happened to agree — but nothing enforced that).
# Values now come from that single canonical table; only the ALLOW-LIST of
# judge-supported models lives here, so project_calibration_cost() keeps
# raising KeyError for any model outside this project's 3 supported judges
# (the canonical table also carries gpt-* subject-model entries that must
# stay out of the judge-cost-projection surface).
_SUPPORTED_JUDGE_MODELS: tuple[str, ...] = (
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5",
)

MODEL_PRICING_USD_PER_M: dict[str, dict[str, float]] = {
    model: PRICE_PER_MTOK[model] for model in _SUPPORTED_JUDGE_MODELS
}

# ---------------------------------------------------------------------------
# A36 hard ceiling on --daily-cap
# ---------------------------------------------------------------------------

DAILY_CAP_HARD_CEILING_USD: float = 100.0
DAILY_CAP_OVERRIDE_ENV: str = "SKILL_HARNESS_DAILY_CAP_OVERRIDE"

# ---------------------------------------------------------------------------
# #40 per-evaluation hard cap (registered budget value; drift row DC-10)
# ---------------------------------------------------------------------------

# Ratified decision #40 (operator-picked values decision): $35 hard cap per
# skill-task evaluation. The cap tests WORST-CASE FIXED-N projected cost
# pre-spend - never curtailed expectation (a hard cap that assumes savings
# is not hard, #40(b)) - and is registered through the EXISTING
# runtime.run_budget.hard_cap_usd per-run surface. The oc frontier (#56)
# marks over-cap rows visible-but-infeasible against this value; the RAT
# preflight gate (#57) binds record cap == passed budget mechanically.
# Drift row DC-10 pins this value and the daily ceiling above against the
# locked doc quotes.
EVALUATION_HARD_CAP_USD: float = 35.0

# T_out estimate per call: ~50 tokens (choice + rationale per A36)
_T_OUT_PER_CALL: int = 50


# ---------------------------------------------------------------------------
# CostProjection Pydantic model
# ---------------------------------------------------------------------------


class CostProjection(BaseModel):
    """Frozen projection of calibration run cost (A36).

    Fields
    ------
    n_calls : int
        Total judge API calls = N_pairs x 2 (position swap).
    t_in_cached : int
        Input tokens paid at full (uncached) price across all N calls.
        This is the first call's full prefix + all calls' unique tails.
    t_in_uncached : int
        Input tokens for the first call (system + tool schema + pair tail).
        Paid at full input rate (cache-WRITE on first call is 1.25x, but
        for projection simplicity we treat as full input rate).
    t_in_cache_read : int
        Tokens served from cache prefix across calls 2..N.
        = (N_calls - 1) x (system_prompt_tokens + tool_schema_tokens)
    t_out : int
        Total output tokens = N_calls x 50.
    usd : float
        Projected total cost in USD.
    cache_reuse_pct : float
        Fraction of input tokens served from cache (0..100).
    est_se_pairwise_agreement : float
        sqrt(0.7 * 0.3 / N_pairs) — normal approximation SE.
    est_ci_95_width : float
        2 * 1.96 * est_se_pairwise_agreement — 95% CI width.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    n_calls: int
    t_in_cached: int  # all N calls' unique pair tails (full input price)
    t_in_uncached: int  # first call's full prefix + tail (full input price)
    t_in_cache_read: int  # cache-read tokens (calls 2..N prefix)
    t_out: int
    usd: float
    cache_reuse_pct: float
    est_se_pairwise_agreement: float
    est_ci_95_width: float


# ---------------------------------------------------------------------------
# project_calibration_cost
# ---------------------------------------------------------------------------


def project_calibration_cost(
    n_pairs: int,
    model_id: str,
    system_prompt_tokens: int,
    tool_schema_tokens: int,
    candidate_output_avg_tokens: int,
) -> CostProjection:
    """Project the cost of a calibration run (A36 formula).

    Parameters
    ----------
    n_pairs:
        Number of calibration pairs in the JSONL.
    model_id:
        Judge model (must be in MODEL_PRICING_USD_PER_M).
    system_prompt_tokens:
        Token count of the judge system prompt (the stable cacheable prefix).
    tool_schema_tokens:
        Token count of the tool schema (also part of the stable prefix).
    candidate_output_avg_tokens:
        Average token count of a single candidate output. Each pair has two
        candidates, so unique tail tokens per call = candidate_output_avg_tokens x 2.

    Returns
    -------
    CostProjection
        Frozen projection of token counts, cost, and statistical projections.

    Raises
    ------
    KeyError:
        If model_id is not in MODEL_PRICING_USD_PER_M.
    """
    pricing = MODEL_PRICING_USD_PER_M[model_id]

    # --- Token counting (A36 formula verbatim) ---
    n_calls = n_pairs * 2  # position swap per A6

    # Stable prefix = system prompt + tool schema (cacheable)
    prefix_tokens = system_prompt_tokens + tool_schema_tokens

    # Unique tail per call = both candidate outputs
    pair_unique_tokens = candidate_output_avg_tokens * 2

    # First call: pays full input price for prefix + unique tail
    t_in_uncached = prefix_tokens + pair_unique_tokens

    # All N calls pay for their unique pair tails at full input price
    t_in_cached = pair_unique_tokens * n_calls

    # Calls 2..N read the cached prefix
    t_in_cache_read = (n_calls - 1) * prefix_tokens if n_calls > 1 else 0

    # Output tokens
    t_out = n_calls * _T_OUT_PER_CALL

    # --- USD cost computation ---
    # First call: full input price for prefix (cache-write) + all pairs x full input
    # For projection, treat cache-write as full input price (conservative approximation;
    # actual cost is 1.25x but the brief's formula uses full input pricing for simplicity)
    input_per_m = pricing["input"]
    cache_read_per_m = pricing["cache_read"]
    output_per_m = pricing["output"]

    cost_uncached_input = t_in_uncached * input_per_m / 1_000_000
    cost_cached_input = t_in_cached * input_per_m / 1_000_000
    cost_cache_read = t_in_cache_read * cache_read_per_m / 1_000_000
    cost_output = t_out * output_per_m / 1_000_000

    usd = cost_uncached_input + cost_cached_input + cost_cache_read + cost_output

    # --- Cache reuse percentage ---
    total_input_tokens = t_in_uncached + t_in_cached + t_in_cache_read
    if total_input_tokens > 0:
        cache_reuse_pct = (t_in_cache_read / total_input_tokens) * 100.0
    else:
        cache_reuse_pct = 0.0

    # --- Statistical projections (bayesian-eval-discipline) ---
    est_se = math.sqrt(0.7 * 0.3 / n_pairs) if n_pairs > 0 else 0.0
    est_ci_95_width = 2 * 1.96 * est_se

    return CostProjection(
        n_calls=n_calls,
        t_in_cached=t_in_cached,
        t_in_uncached=t_in_uncached,
        t_in_cache_read=t_in_cache_read,
        t_out=t_out,
        usd=usd,
        cache_reuse_pct=cache_reuse_pct,
        est_se_pairwise_agreement=est_se,
        est_ci_95_width=est_ci_95_width,
    )


# ---------------------------------------------------------------------------
# Daily cap validation helper (used by command.py)
# ---------------------------------------------------------------------------


def validate_daily_cap(requested: float) -> float:
    """Validate --daily-cap does not exceed the hard ceiling.

    Parameters
    ----------
    requested:
        The requested daily cap in USD.

    Returns
    -------
    float
        The validated cap (same as requested if valid).

    Raises
    ------
    ValueError:
        If requested > DAILY_CAP_HARD_CEILING_USD and override env is not set.
    """
    if requested > DAILY_CAP_HARD_CEILING_USD:
        if os.environ.get(DAILY_CAP_OVERRIDE_ENV) == "1":
            return requested
        raise ValueError(
            f"--daily-cap {requested:.2f} exceeds hard ceiling "
            f"{DAILY_CAP_HARD_CEILING_USD:.2f}; "
            f"set {DAILY_CAP_OVERRIDE_ENV}=1 to override"
        )
    return requested


# ---------------------------------------------------------------------------
# Evaluation-run projections (#56): live PRICE_PER_MTOK -> USD, worst case
# ---------------------------------------------------------------------------


def _project_tokens_usd(model_id: str, input_tokens: float, output_tokens: float) -> float:
    """Worst-case USD for one unit of calibrated token spend.

    Deliberately assumes NO cache discount: this feeds the #40 pre-spend
    hard-cap projection, and a cap that assumes savings is not hard. Rates
    come from the canonical PRICE_PER_MTOK table (F3 single source of truth);
    an unknown model raises KeyError rather than default-pricing - a cap
    projection must never silently price the wrong model.
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError(
            f"token counts must be >= 0; got input={input_tokens}, output={output_tokens}"
        )
    rates = PRICE_PER_MTOK[model_id]
    return round((input_tokens * rates["input"] + output_tokens * rates["output"]) / 1e6, 8)


def project_pair_usd(
    model_id: str, *, input_tokens_per_pair: float, output_tokens_per_pair: float
) -> float:
    """Worst-case projected USD for ONE Gate-2 evaluation pair (#40(c)).

    The frontier's cost column is computed live from the current
    PRICE_PER_MTOK rates times the CALIBRATED tokens-per-pair measurement
    supplied by the caller - never a hard-coded per-pair dollar constant
    (drift row DC-9 bans the prototype's snapshot constant by token).

    :param model_id: Subject model in the canonical pricing table.
    :param input_tokens_per_pair: Calibrated input tokens across both arms
        of one pair, >= 0.
    :param output_tokens_per_pair: Calibrated output tokens across both arms
        of one pair, >= 0.
    :returns: Projected USD per pair (no cache discount - worst case).
    :raises KeyError: If the model is not in the canonical pricing table.
    :raises ValueError: If a token count is negative.
    """
    return _project_tokens_usd(model_id, input_tokens_per_pair, output_tokens_per_pair)


def project_trial_usd(
    model_id: str, *, input_tokens_per_trial: float, output_tokens_per_trial: float
) -> float:
    """Worst-case projected USD for ONE Gate-1 screen trial (single arm).

    Same worst-case discipline as :func:`project_pair_usd`; the Gate-1
    screen cost is display-only on the frontier (the #40 hard cap tests the
    Gate-2 pair spend, matching that record's own worst-case arithmetic).

    :param model_id: Subject model in the canonical pricing table.
    :param input_tokens_per_trial: Calibrated input tokens per trial, >= 0.
    :param output_tokens_per_trial: Calibrated output tokens per trial, >= 0.
    :returns: Projected USD per trial (no cache discount - worst case).
    :raises KeyError: If the model is not in the canonical pricing table.
    :raises ValueError: If a token count is negative.
    """
    return _project_tokens_usd(model_id, input_tokens_per_trial, output_tokens_per_trial)
