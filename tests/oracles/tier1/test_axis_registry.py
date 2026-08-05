"""Tests for the Tier-1 axis registry and its fail-closed axis classifier (#117).

The registry is the containment boundary between a model that *proposes* an
axis and code that *disposes*. These tests pin two properties:

1. The registry and the scorers cannot drift apart — the name table and the
   scorer mapping are asserted equal, in order.
2. The classifier fails closed. A near miss is ``UNSCOREABLE``, never repaired
   to the nearest registered name; a lenient match here is what would let a
   hallucinated or drifted axis produce a measurement.
"""

from __future__ import annotations

import pytest

from skill_harness.oracles.tier1.axis_registry import (
    TIER1_AXES,
    TIER1_AXIS_NAMES,
    AxisScoreability,
    classify_axis,
    get_tier1_scorers,
)

# ---------------------------------------------------------------------------
# Single-source property
# ---------------------------------------------------------------------------


def test_axis_names_match_registry_entries_in_order() -> None:
    """TIER1_AXIS_NAMES is a projection of TIER1_AXES, not a second list."""
    assert tuple(axis.name for axis in TIER1_AXES) == TIER1_AXIS_NAMES


def test_scorer_mapping_keys_equal_registry_names() -> None:
    """A scorer cannot be added or dropped without the name table moving with it.

    This is the assertion that makes the registry authoritative rather than
    merely adjacent: if the two ever diverge, an axis is either advertised to
    the extractor with nothing behind it, or scoreable but never offered.
    """
    assert tuple(get_tier1_scorers().keys()) == TIER1_AXIS_NAMES


def test_registry_entries_are_well_formed() -> None:
    """No blank names or descriptions, and no duplicate names."""
    assert len(set(TIER1_AXIS_NAMES)) == len(TIER1_AXIS_NAMES)
    for axis in TIER1_AXES:
        assert axis.name.strip() == axis.name, f"{axis.name!r} carries stray whitespace"
        assert axis.name, "empty axis name"
        assert axis.description.strip(), f"{axis.name!r} has no description"


def test_end_state_categorical_is_not_a_registered_axis() -> None:
    """The one tier1/ module that is deliberately excluded stays excluded.

    ``score_end_state`` is not a ``(text) -> float`` metric — registering it
    would advertise an axis to the extractor that the ablation path cannot
    score. See axis_registry.TIER1_AXES for the full reasoning.
    """
    assert "end_state_categorical" not in TIER1_AXIS_NAMES
    assert "end_state_categorical" not in get_tier1_scorers()


# ---------------------------------------------------------------------------
# classify_axis — the disposal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", TIER1_AXIS_NAMES)
def test_registered_axis_classifies_as_tier1_mechanical(name: str) -> None:
    assert classify_axis(name) is AxisScoreability.TIER1_MECHANICAL


def test_unregistered_axis_is_unscoreable() -> None:
    """An axis with no scorer is a real answer ("nothing can score this")."""
    assert classify_axis("formality") is AxisScoreability.UNSCOREABLE


def test_empty_axis_is_unscoreable() -> None:
    assert classify_axis("") is AxisScoreability.UNSCOREABLE


def test_whitespace_only_axis_is_unscoreable() -> None:
    assert classify_axis("   \t\n ") is AxisScoreability.UNSCOREABLE


@pytest.mark.parametrize(
    "near_miss",
    [
        "Verbosity",  # capitalised
        "VERBOSITY",  # shouted
        "verbosities",  # pluralised
        "verbosity_score",  # suffixed
        "hedge-index",  # hyphen instead of underscore
        "hedge index",  # space instead of underscore
        "structure",  # truncated
        "citation_presence",  # truncated
        "complianceproxy",  # separator dropped
    ],
)
def test_near_miss_fails_closed(near_miss: str) -> None:
    """A near miss must NOT be silently matched.

    This is the ticket's known trap: relaxing the join to raise the match rate
    would manufacture measurability. Any fuzzy or case-insensitive matching
    added later fails here.
    """
    assert near_miss not in TIER1_AXIS_NAMES, "test case is not actually a near miss"
    assert classify_axis(near_miss) is AxisScoreability.UNSCOREABLE


def test_no_normalisation_at_all_not_even_a_whitespace_strip() -> None:
    """A padded axis is UNSCOREABLE, and that is deliberate — not an oversight.

    The runner's pre-sampling gate and ``_score_primary_axis``'s scorer lookup
    must agree exactly. A strip here (tried, reverted) admitted a padded axis
    the raw lookup then missed, turning a safe UNMEASURED into an uncaught
    RuntimeError mid-run. Whoever adds normalisation must fix that first, at the
    extractor boundary; this test is the tripwire.
    """
    assert classify_axis("  verbosity  ") is AxisScoreability.UNSCOREABLE
    assert classify_axis("\tverbosity\n") is AxisScoreability.UNSCOREABLE
    assert classify_axis("verbosity ") is AxisScoreability.UNSCOREABLE
    assert classify_axis("hedge_ index") is AxisScoreability.UNSCOREABLE


@pytest.mark.parametrize(
    "hostile",
    [
        "",
        " ",
        "\x00",
        "verbosity\x00",
        "詳細度",
        "verbosity" * 1000,
        "a\nb\nc",
        "*",
        "%s",
        "{axis}",
    ],
)
def test_classify_axis_never_raises(hostile: str) -> None:
    """Total over str: every input gets a classification, none get an exception.

    The classifier sits downstream of model-generated text, so a raise here
    would turn "unrecognised axis" into a crashed extraction.
    """
    assert classify_axis(hostile) in {
        AxisScoreability.TIER1_MECHANICAL,
        AxisScoreability.UNSCOREABLE,
    }


def test_classify_axis_is_deterministic() -> None:
    """Same input, same answer — no state, no ordering dependence."""
    for name in (*TIER1_AXIS_NAMES, "formality", "", "Verbosity"):
        assert classify_axis(name) is classify_axis(name)


# ---------------------------------------------------------------------------
# Agreement with the runner's gate
# ---------------------------------------------------------------------------


def test_classify_axis_agrees_with_raw_scorer_membership() -> None:
    """The classifier and the runner's pre-sampling gate must never disagree.

    ``AblationRunner._is_tier1_measurable`` gates on ``axis in self._scorers``
    and ``_score_primary_axis`` then looks the axis up the same raw way. If
    ``classify_axis`` ever answers differently for the same string, one of the
    three has grown a normalisation the others lack — which is the failure mode
    that produced an uncaught RuntimeError during review of #117.
    """
    scorers = get_tier1_scorers()
    for candidate in (
        *TIER1_AXIS_NAMES,
        "formality",
        "",
        "  verbosity  ",
        "verbosity ",
        "Verbosity",
    ):
        expected = (
            AxisScoreability.TIER1_MECHANICAL
            if candidate in scorers
            else AxisScoreability.UNSCOREABLE
        )
        assert classify_axis(candidate) is expected, candidate
