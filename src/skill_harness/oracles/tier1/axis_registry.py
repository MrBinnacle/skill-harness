"""Single source of truth for the Tier-1 mechanical scorer axes.

These names previously existed twice — as ``AXIS_*`` constants in
``ablation/confound.py`` and as hand-typed prose in the extractor system prompt
— and the two copies had already drifted. This module is the one authority.

NOT a revival of the ``registry.py`` deleted under F1/S49 (see this package's
``__init__`` docstring): that one was a *mutable* runtime registry duplicating
provenance the ``metric_versions`` table already records. This registers
nothing at import time.

Containment boundary: the model proposes an axis, code disposes.
``classify_axis`` is the disposal — an axis absent from this table is
``UNSCOREABLE`` and can only land in "nothing can score this".

Matching is plain exact comparison, with NO normalisation at all — not even a
whitespace strip. Two reasons, and both are load-bearing:

- Fuzzy or case-insensitive matching would raise the apparent match rate by
  manufacturing measurability, which is the failure this instrument exists to
  distrust. A near miss (``"Verbosity"``) must fail closed.
- A strip was tried and reverted. Every downstream consumer of a clause's axis
  compares it raw — ``AblationRunner._score_primary_axis`` keys the scorer dict
  with it, ``detect_confounds`` inverts ``clause_to_axis_map`` on it, and the A1
  invariant check compares it to ``ConfoundEvent.axis``. A gate that accepted
  ``" verbosity "`` while those lookups missed it turned a safe UNMEASURED into
  a run-aborting ``RuntimeError``. Normalising once at the extractor boundary
  (a validator on ``ExtractedClause.axis``) is the correct fix and is a
  deliberate follow-up; until then the rule here is the strictest one, which is
  also the fail-closed one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

MetricFn = Callable[[str], float]
"""A Tier-1 scorer: deterministic, offline, ``(output_text) -> score``."""


@dataclass(frozen=True)
class Tier1Axis:
    """One registered Tier-1 axis: the exact axis string plus its prompt blurb."""

    name: str
    description: str


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

TIER1_AXES: Final[tuple[Tier1Axis, ...]] = (
    Tier1Axis("verbosity", "output token/word count"),
    Tier1Axis("hedge_index", "proportion of hedge words (maybe, perhaps, could, etc.)"),
    Tier1Axis("structure_score", "heading and paragraph-break density"),
    Tier1Axis("compliance_proxy", "directive-keyword density"),
    Tier1Axis(
        "citation_presence_per_flag",
        "fraction of flagged items that include a citation marker",
    ),
)
"""Every axis a registered Tier-1 scorer can measure, in authoring order.

``end_state_categorical.py`` is deliberately absent, and the absence is a shape
mismatch rather than an oversight: ``score_end_state`` is not a ``MetricFn``. It
takes an ``EpochEndState`` of sandbox facts and returns a 4-way category plus an
evidence-admissibility flag, so it cannot enter ablation's Full-vs-Ablated text-delta
path. Listing it would advertise an axis to the extractor with nothing behind it
to score.
"""

TIER1_AXIS_NAMES: Final[tuple[str, ...]] = tuple(axis.name for axis in TIER1_AXES)
"""Just the names, in registry order. What the extractor prompt renders from."""


# ---------------------------------------------------------------------------
# Disposal
# ---------------------------------------------------------------------------


class AxisScoreability(StrEnum):
    """What, if anything, can mechanically score a proposed axis."""

    TIER1_MECHANICAL = "tier1_mechanical"
    UNSCOREABLE = "unscoreable"


def classify_axis(axis: str) -> AxisScoreability:
    """Classify a proposed axis against the Tier-1 registry.

    Total over ``str`` — every input maps to a value, including the empty
    string. Never raises and never guesses a nearest match: ``UNSCOREABLE`` is a
    real answer ("nothing can score this"), not an error condition, because this
    sits downstream of model-generated text where a raise would turn an
    unrecognised axis into a crashed extraction.
    """
    if axis in TIER1_AXIS_NAMES:
        return AxisScoreability.TIER1_MECHANICAL
    return AxisScoreability.UNSCOREABLE


# ---------------------------------------------------------------------------
# Scorer resolution
# ---------------------------------------------------------------------------


def get_tier1_scorers() -> dict[str, MetricFn]:
    """Return the registered axis name -> scoring function mapping.

    Zipped against ``TIER1_AXIS_NAMES`` rather than written as a name-keyed
    literal, so the names live in exactly one place and ``strict=True`` turns a
    scorer added without its registry entry into an immediate error instead of a
    silently short mapping.

    Imports the metric modules only when called, so reading the axis names (e.g.
    to build the extractor prompt, or in the offline ``skill audit`` path) does
    not trigger tiktoken's cold-cache BPE fetch.
    """
    from skill_harness.oracles.tier1.citation_presence_per_flag import (
        compute_citation_presence_per_flag,
    )
    from skill_harness.oracles.tier1.compliance_proxy import compute_compliance_proxy
    from skill_harness.oracles.tier1.hedge_index import compute_hedge_index
    from skill_harness.oracles.tier1.structure_score import compute_structure_score
    from skill_harness.oracles.tier1.verbosity import count_tokens

    # Order MUST match TIER1_AXES.
    scorers: tuple[MetricFn, ...] = (
        count_tokens,
        compute_hedge_index,
        compute_structure_score,
        compute_compliance_proxy,
        compute_citation_presence_per_flag,
    )
    return dict(zip(TIER1_AXIS_NAMES, scorers, strict=True))
