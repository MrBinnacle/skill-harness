"""Anthropic's ``input_tokens`` excludes cache tokens, so it is charged as given (#883).

A live ``claude-sonnet-4-6`` call measured it: ``count_tokens`` returned 4839 for a
prompt that the cache-write and the cache-read responses each reported as 13 plain
tokens plus 4826 cache tokens.

The expected figures are hand-derived dollar literals at $3 input, $15 output,
$3.75 cache write and $0.30 cache read per million tokens. Copying the production
formula here is the mirror that hid this bug in ``test_estimate_usd_pricing_333``.
"""

from __future__ import annotations

import pytest

from skill_harness.ablation.subject import _estimate_usd


@pytest.mark.parametrize(
    ("input_tokens", "cache_read", "cache_creation", "output_tokens", "billed_usd"),
    [
        pytest.param(13, 0, 4826, 4, 0.0181965, id="live-cache-write"),
        pytest.param(13, 4826, 0, 4, 0.0015468, id="live-cache-read"),
        pytest.param(5000, 1100, 0, 0, 0.01533, id="large-uncached-tail"),
    ],
)
def test_input_tokens_are_charged_in_full_beside_the_cache_tokens(
    input_tokens: int,
    cache_read: int,
    cache_creation: int,
    output_tokens: int,
    billed_usd: float,
) -> None:
    assert (
        _estimate_usd(
            "claude-sonnet-4-6",
            input_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
            output_tokens=output_tokens,
        )
        == billed_usd
    )
