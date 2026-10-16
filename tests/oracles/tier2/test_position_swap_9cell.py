"""Tests for position-swap consistency logic (A32).

9-cell (AB x BA) parameterized table covering:
- Admissible cases: AB==A and BA==B (A beats B), AB==B and BA==A (B beats A),
  AB==tie and BA==tie (tie symmetric)
- Inadmissible: all off-diagonal pairs (disagreement → position_disagreement)
- Tie flip: flip(tie)==tie per llm-judge-calibration Discipline 2

Position-swap logic per A32:
  flip("A") == "B", flip("B") == "A", flip("tie") == "tie"
  position_swap_agreement = 1 if (verdict_AB == flip(verdict_BA)) else 0
  If position_swap_agreement == 0: admissibility_state = "inadmissible",
    inadmissibility_reason = "position_disagreement"
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHOICES = ["A", "B", "tie"]


def _flip(choice: str) -> str:
    return {"A": "B", "B": "A", "tie": "tie"}[choice]


def _make_response(choice: str) -> MagicMock:
    """Build a mock response that returns the given choice."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "report_verdict"
    block.input = {"choice": choice, "rationale_brief": "test"}

    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def _run_evaluate_pair_with_ab_ba(ab_choice: str, ba_choice: str) -> Any:
    """Run evaluate_pair with mocked AB response = ab_choice, BA response = ba_choice.

    Uses a side-effect callable that inspects the prompt content to determine
    which call is AB vs BA, per A32 mock discipline.
    """
    from skill_harness.oracles.tier2.judge import JudgeClient

    call_count = {"n": 0}

    def side_effect(**kwargs: Any) -> MagicMock:
        n = call_count["n"]
        call_count["n"] += 1
        # First call is (A,B), second call is (B,A)
        if n == 0:
            return _make_response(ab_choice)
        else:
            return _make_response(ba_choice)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect
    jc = JudgeClient(client=mock_client)
    return jc.evaluate_pair("output_a_text", "output_b_text", "clarity", "rate clarity")


# ---------------------------------------------------------------------------
# 9-cell parameterized table (AB choice x BA choice)
# Each row: (ab_choice, ba_choice, expected_admissible, expected_position_swap_agreement)
# ---------------------------------------------------------------------------

_9_CELL_TABLE = []
for ab in CHOICES:
    for ba in CHOICES:
        # Agreement: AB == flip(BA)
        agreement = int(ab == _flip(ba))
        admissible = agreement == 1
        _9_CELL_TABLE.append(
            pytest.param(
                ab,
                ba,
                admissible,
                agreement,
                id=f"AB={ab}_BA={ba}",
            )
        )


@pytest.mark.parametrize(
    "ab_choice,ba_choice,expected_admissible,expected_agreement", _9_CELL_TABLE
)
def test_position_swap_9cell(
    ab_choice: str,
    ba_choice: str,
    expected_admissible: bool,
    expected_agreement: int,
) -> None:
    """9-cell table: verify admissibility + position_swap_agreement for all AB x BA combos."""
    verdict = _run_evaluate_pair_with_ab_ba(ab_choice, ba_choice)

    assert verdict.position_swap_agreement == expected_agreement, (
        f"AB={ab_choice}, BA={ba_choice}: "
        f"expected position_swap_agreement={expected_agreement}, "
        f"got {verdict.position_swap_agreement}"
    )

    if expected_admissible:
        assert verdict.admissibility_state == "admissible", (
            f"AB={ab_choice}, BA={ba_choice}: expected admissible"
        )
        assert verdict.inadmissibility_reason is None
    else:
        assert verdict.admissibility_state == "inadmissible", (
            f"AB={ab_choice}, BA={ba_choice}: expected inadmissible"
        )
        assert verdict.inadmissibility_reason == "position_disagreement"


# ---------------------------------------------------------------------------
# Specific RED tests required by A32 (named per spec)
# ---------------------------------------------------------------------------


def test_swap_consistent_a_admissible() -> None:
    """A32 RED: AB=A, BA=B → admissible (A beats B consistently)."""
    verdict = _run_evaluate_pair_with_ab_ba("A", "B")
    assert verdict.admissibility_state == "admissible"
    assert verdict.position_swap_agreement == 1
    assert verdict.inadmissibility_reason is None


def test_swap_disagreement_inadmissible() -> None:
    """A32 RED: AB=A, BA=A → inadmissible with reason 'position_disagreement'."""
    verdict = _run_evaluate_pair_with_ab_ba("A", "A")
    assert verdict.admissibility_state == "inadmissible"
    assert verdict.inadmissibility_reason == "position_disagreement"
    assert verdict.position_swap_agreement == 0


def test_swap_consistent_tie_admissible() -> None:
    """A32 RED: AB=tie, BA=tie → admissible (flip(tie)==tie per Discipline 2)."""
    verdict = _run_evaluate_pair_with_ab_ba("tie", "tie")
    assert verdict.admissibility_state == "admissible"
    assert verdict.position_swap_agreement == 1
    assert verdict.inadmissibility_reason is None


# ---------------------------------------------------------------------------
# evaluate_pair is called EXACTLY twice (AB + BA)
# ---------------------------------------------------------------------------


def test_evaluate_pair_calls_api_exactly_twice() -> None:
    """evaluate_pair() must invoke messages.create exactly twice (one AB, one BA)."""
    from skill_harness.oracles.tier2.judge import JudgeClient

    responses = [_make_response("A"), _make_response("B")]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = responses
    jc = JudgeClient(client=mock_client)
    jc.evaluate_pair("out_a", "out_b", "clarity", "rubric")
    assert mock_client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# raw_observation encoding (Win=1.0, Tie=0.5, Loss=0.0 from A's perspective in AB)
# ---------------------------------------------------------------------------


def test_raw_observation_win_is_1() -> None:
    """AB=A (A wins) → raw_observation=1.0 (Win from A's perspective)."""
    verdict = _run_evaluate_pair_with_ab_ba("A", "B")
    assert verdict.raw_observation == pytest.approx(1.0)


def test_raw_observation_loss_is_0() -> None:
    """AB=B (B wins, A loses) → raw_observation=0.0 (Loss from A's perspective)."""
    verdict = _run_evaluate_pair_with_ab_ba("B", "A")
    assert verdict.raw_observation == pytest.approx(0.0)


def test_raw_observation_tie_is_half() -> None:
    """AB=tie → raw_observation=0.5 (half-update per C1 provisional, A10)."""
    verdict = _run_evaluate_pair_with_ab_ba("tie", "tie")
    assert verdict.raw_observation == pytest.approx(0.5)
