"""Single source of truth for the Tier-1 mechanical scorer axes and deterministic
external-check axes.

These names previously existed twice — as ``AXIS_*`` constants in
``ablation/confound.py`` and as hand-typed prose in the extractor system prompt
— and the two copies had already drifted. This module is the one authority.

NOT a revival of the ``registry.py`` deleted under F1/S49 (see this package's
``__init__`` docstring): that one was a *mutable* runtime registry duplicating
provenance the ``metric_versions`` table already records. This registers
nothing at import time.

Containment boundary: the model proposes an axis, code disposes.
``classify_axis`` is the disposal — an axis absent from either registry is
``UNSCOREABLE`` and can only land in "nothing can score this".

Matching is plain exact comparison, with NO normalisation at all — not even a
whitespace strip. Two reasons, and both are load-bearing:

- Fuzzy or case-insensitive matching would raise the apparent match rate by
  manufacturing measurability, which is the failure this instrument exists to
  distrust. A near miss (``"Verbosity"``) must fail closed.
- A strip was tried and reverted here. Every downstream consumer of a clause's
  axis compares it raw — ``AblationRunner._score_primary_axis`` keys the scorer
  dict with it, ``detect_confounds`` inverts ``clause_to_axis_map`` on it, and
  the A1 invariant check compares it to ``ConfoundEvent.axis``. A gate that
  accepted ``" verbosity "`` while those lookups missed it turned a safe
  UNMEASURED into a run-aborting ``RuntimeError``. Whitespace is stripped once
  at the extractor boundary (``ExtractedClause._normalise_axis``, #504) so a
  padded axis never reaches this classifier or those consumers; this function
  stays strict and fail-closed on anything that still arrives unstripped.

External-check axes (#555) sit beside Tier-1 axes in a second registry. They
are deterministic, program-checkable outcomes that need no LLM judge. The
protected-class comment-deletion rate is the first registered axis: its oracle
is a deterministic diff checker whose exit status is the score.
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
# External-check axes (#555)
# ---------------------------------------------------------------------------

EXTERNAL_CHECK_AXES: Final[tuple[Tier1Axis, ...]] = (
    Tier1Axis(
        "protected_comment_deletion",
        "did the edit delete a comment of a protected class (translation, "
        "rationale, authority, hazard, contract, history)",
    ),
)
"""Deterministic, program-checkable axes whose oracle is an external check.

Each axis maps to a deterministic checker that reads a diff and exits
non-zero when the diff deletes a comment of a protected class. The oracle
is not an LLM judge — it is a program that produces an exit status. The
runner records the score without routing through the judge.

``protected_comment_deletion`` is the first registered axis, carried from
MrBinnacle/skills#308. The checker reads a unified diff and refuses when
the diff deletes a comment of a protected class (rationale, authority,
hazard, contract, history). Translation is removable when the same change
adds code stating the fact.
"""

EXTERNAL_CHECK_AXIS_NAMES: Final[tuple[str, ...]] = tuple(axis.name for axis in EXTERNAL_CHECK_AXES)
"""Just the names of external-check axes, in registry order."""


# ---------------------------------------------------------------------------
# Disposal
# ---------------------------------------------------------------------------


class AxisScoreability(StrEnum):
    """What, if anything, can score a proposed axis."""

    TIER1_MECHANICAL = "tier1_mechanical"
    EXTERNAL_CHECK = "external_check"
    UNSCOREABLE = "unscoreable"


def classify_axis(axis: str) -> AxisScoreability:
    """Classify a proposed axis against the Tier-1 and external-check registries.

    Total over ``str`` — every input maps to a value, including the empty
    string. Never raises and never guesses a nearest match: ``UNSCOREABLE`` is a
    real answer ("nothing can score this"), not an error condition, because this
    sits downstream of model-generated text where a raise would turn an
    unrecognised axis into a crashed extraction.

    Returns ``EXTERNAL_CHECK`` when the axis is in the external-check registry
    (#555). The runner can score such axes via a deterministic checker without
    routing through the judge.
    """
    if axis in TIER1_AXIS_NAMES:
        return AxisScoreability.TIER1_MECHANICAL
    if axis in EXTERNAL_CHECK_AXIS_NAMES:
        return AxisScoreability.EXTERNAL_CHECK
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


# ---------------------------------------------------------------------------
# External-check scorer resolution (#555)
# ---------------------------------------------------------------------------


def get_external_check_scorers() -> dict[str, MetricFn]:
    """Return the registered external-check axis name -> scoring function mapping.

    Each external-check scorer is a deterministic program that reads input and
    produces a float. Unlike Tier-1 scorers, external-check scorers may require
    structured input (e.g., a diff rather than plain text), so the ``MetricFn``
    signature is a convenience — the runner passes the appropriate input.

    Zipped against ``EXTERNAL_CHECK_AXIS_NAMES`` rather than written as a
    name-keyed literal, so the names live in exactly one place and ``strict=True``
    turns a scorer added without its registry entry into an immediate error.

    Currently returns an empty dict because no external-check scorer is
    implemented in-tree. The checker from #308 is archived outside the
    repository and will be registered when it is brought in-tree.

    When scorers are added, they must be zipped against EXTERNAL_CHECK_AXIS_NAMES
    with strict=True, exactly like get_tier1_scorers, so a scorer added without
    its registry entry turns into an immediate error.
    """
    # No external-check scorers registered yet. Return empty dict.
    # When scorers are added, build the dict by zipping against EXTERNAL_CHECK_AXIS_NAMES.
    return {}
