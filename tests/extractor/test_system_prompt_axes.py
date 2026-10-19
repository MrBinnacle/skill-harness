"""The extractor prompt's axis list must equal the Tier-1 registry (#117).

These names were hand-typed prose in the system prompt and had already drifted
from the scorers that exist. The prompt now renders from
``oracles/tier1/axis_registry``; this module parses the names back OUT of the
finished prompt string and compares them to the registry, so the two cannot
separate again — including by someone re-adding a hand-written line.
"""

from __future__ import annotations

import re

from skill_harness.extractor.claude import _SYSTEM_PROMPT
from skill_harness.oracles.tier1.axis_registry import TIER1_AXES, TIER1_AXIS_NAMES

# A catalog line is two spaces, the axis name, padding, an em dash, the
# description. Parsed from the rendered prompt rather than re-rendered, so this
# checks the string the model actually receives.
_CATALOG_LINE = re.compile(r"^ {2}(\S+) +— .+$", re.MULTILINE)


def _axis_names_in_prompt() -> tuple[str, ...]:
    return tuple(_CATALOG_LINE.findall(_SYSTEM_PROMPT))


def test_prompt_axis_list_equals_registry_names() -> None:
    """Exact equality, including order. The drift this ticket closed."""
    assert _axis_names_in_prompt() == TIER1_AXIS_NAMES


def test_prompt_lists_every_registered_axis_with_its_description() -> None:
    for axis in TIER1_AXES:
        assert axis.name in _SYSTEM_PROMPT, f"{axis.name!r} missing from prompt"
        assert axis.description in _SYSTEM_PROMPT, f"description for {axis.name!r} missing"


def test_prompt_does_not_offer_the_excluded_end_state_scorer() -> None:
    """``end_state_categorical`` has no ``(text) -> float`` scorer behind it.

    Naming it here would invite clauses onto an axis the ablation path cannot
    measure — the reconciliation this ticket required.
    """
    assert "end_state_categorical" not in _SYSTEM_PROMPT


def test_prompt_catalog_parse_is_not_vacuous() -> None:
    """Guard the guard: an empty parse would match an empty registry silently."""
    assert len(_axis_names_in_prompt()) == len(TIER1_AXES)
    assert TIER1_AXES, "registry is empty — parity above would pass on nothing"


def test_prompt_does_not_couple_vacuity_to_falsifying_case() -> None:
    """#136: vacuity judgement and falsifying_case are independent prompt asks."""
    assert "lacks a constructible falsifying case" not in _SYSTEM_PROMPT
    # Must not condition case writing on vacuity_flag==none.
    assert 'For non-vacuous clauses (vacuity_flag="none"), you MUST provide' not in (_SYSTEM_PROMPT)
    assert "independently of the vacuity judgement" in _SYSTEM_PROMPT
    assert "Do not condition this judgement on whether a falsifying case" in (_SYSTEM_PROMPT)
