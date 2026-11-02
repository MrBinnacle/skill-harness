"""_estimate_usd must price the recorded identifier, or refuse (#333).

Two defects in the pre-#333 lookup, both in one line
(``PRICE_PER_MTOK.get(model, PRICE_PER_MTOK["_default"])``):

1. It looked the model up verbatim, so a provider-routed identifier such as
   ``anthropic/claude-sonnet-5`` missed its row. #302 added
   ``resolve_price_key`` and routed ``cost_projection`` through it; this path
   was left on the raw lookup.
2. On a miss it returned ``_default``, which carries Sonnet-4.6's rates
   ($3/$15 per MTok). The caller received a plausible number, 50 percent high
   on both the input and the output rate, and nothing in ``SubjectResponse``
   marked it as a fallback. That figure is written to the append-only evidence
   store as ``samples.usd``.

The fix normalises the key and refuses on a genuine miss.
"""

from __future__ import annotations

import pytest

from skill_harness.ablation.subject import (
    PRICE_PER_MTOK,
    _estimate_usd,
    lookup_price_row,
)

# The literal string the production evidence store carries in
# samples.subject_model, verified against
# .private/_preserved-root-dbs/evidence.db during #302 and again in #333.
_RECORDED_SONNET_5 = "anthropic/claude-sonnet-5"

# Token counts chosen so every rate in the row contributes a distinct term.
_INPUT_TOKENS = 1_000_000
_CACHE_READ = 200_000
_CACHE_CREATION = 100_000
_OUTPUT_TOKENS = 50_000

_SONNET_5_USD = round(2.00 + 0.25 + 0.04 + 0.50, 8)


def _estimate(model: str) -> float:
    return _estimate_usd(
        model=model,
        input_tokens=_INPUT_TOKENS,
        cache_read_input_tokens=_CACHE_READ,
        cache_creation_input_tokens=_CACHE_CREATION,
        output_tokens=_OUTPUT_TOKENS,
    )


def test_recorded_prefixed_sonnet_5_prices_at_the_sonnet_5_rate() -> None:
    """The literal store string must price at $2/$10, not the $3/$15 default."""
    assert _RECORDED_SONNET_5 not in PRICE_PER_MTOK, (
        "The canonical pricing key is the bare vendor name; a provider-prefixed "
        "row would defeat the normalisation this test guards."
    )

    usd = _estimate(_RECORDED_SONNET_5)

    assert usd == _SONNET_5_USD, (
        f"{_RECORDED_SONNET_5!r} priced at {usd} rather than the Sonnet-5 rate. "
        "The pre-#333 lookup missed the row and returned the '_default' "
        "(Sonnet-4.6) rates, which is 50 percent high on input and output."
    )


def test_route_prefix_does_not_change_the_price() -> None:
    """The provider segment names the route, not the model (#302 reasoning)."""
    assert _estimate(_RECORDED_SONNET_5) == _estimate("claude-sonnet-5")


def test_unknown_model_refuses_rather_than_pricing_at_the_default_rate() -> None:
    """A model with no row must raise, not return a plausible wrong number."""
    with pytest.raises(KeyError) as excinfo:
        _estimate("claude-nonexistent-model")
    assert "claude-nonexistent-model" in str(excinfo.value)


def test_unknown_model_behind_a_route_prefix_also_refuses() -> None:
    """Stripping the route must not widen the lookup."""
    with pytest.raises(KeyError) as excinfo:
        _estimate("anthropic/claude-nonexistent-model")
    assert "anthropic/claude-nonexistent-model" in str(excinfo.value)


def test_the_table_has_no_fallback_row() -> None:
    with pytest.raises(KeyError):
        lookup_price_row("_default")
    with pytest.raises(KeyError):
        lookup_price_row("_no_such_model_")
