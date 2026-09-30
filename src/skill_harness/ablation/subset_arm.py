"""Seeded random-subset arm (#667), a free part of the collection-effect screen (#663).

A declared-arm run's unit of comparison is a named arm: a whole prompt
assembly (#554). This module adds one arm factory and nothing else — no
second arm system. Given a subject package (card name -> description) and a
seed, ``draw_subset_arm`` resolves the package to a fixed subset of half its
descriptions (rounded down) and returns it as a plain ``ArmSpec`` the
existing machinery assembles and samples.

The same package and seed give the same subset on every call. A new run
draws a new seed unless one is passed: the seed is caller input when given
and fresh entropy when not, and either way it is reported on the draw for
the run record to freeze.

This module is data + pure functions only. It never calls a model and never
writes evidence; the runner owns the run row, and the record seam
(``subset_draws`` in ``runs.config_json``) is where the seed and the chosen
card names become durable.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from skill_harness.ablation.arms import ArmSpec, validate_arm_specs

# Default declared-arm name for a seeded random-subset arm. Must match
# ARM_NAME_PATTERN (storage/models.py), which is what validate_arm_specs
# enforces below.
SUBSET_ARM_NAME: str = "subset_half"


@dataclass(frozen=True)
class SubsetArmDraw:
    """The resolved product of one seeded random-subset draw (#667).

    Fields
    ------
    seed : int
        The draw's seed — caller-supplied when passed, drawn from fresh
        entropy otherwise. Recorded so the subset is reproducible from the
        run record alone.
    card_names : tuple[str, ...]
        The chosen card names, in package order (the caller's mapping
        order), so one seed always yields the same names in the same
        sequence.
    arm : ArmSpec
        The named arm this draw resolves to: the chosen cards' descriptions
        verbatim, in ``card_names`` order, ready for
        ``resolve_arm_assemblies`` and ``run_arms``.
    """

    seed: int
    card_names: tuple[str, ...]
    arm: ArmSpec


def draw_subset_arm(
    subject_cards: Mapping[str, str],
    *,
    seed: int | None = None,
    arm_name: str = SUBSET_ARM_NAME,
) -> SubsetArmDraw:
    """Draw a seeded random-subset arm from a subject package (#667).

    The subset holds half the package's descriptions, rounded down — at least
    one card for any package of two or more. The same package and seed always
    give the same subset; a package order fixes the sequence of names and
    bodies for that subset.

    :param subject_cards: The subject package — card name to its full
        description text, in a fixed order.
    :param seed: The draw's seed. ``None`` draws a fresh one from
        ``secrets`` (a new run's default).
    :param arm_name: Declared-arm name for the resulting ``ArmSpec``.
    :returns: The draw: seed, chosen card names, and the arm they resolve to.
    :raises ValueError: the package holds no cards or a blank card name.
    :raises ArmSpecError: ``arm_name`` is not a valid declared-arm name.
        Raised before anything is resolved, mirroring #554's refuse-first
        discipline.
    """
    names = tuple(subject_cards)
    if not names:
        raise ValueError(
            "subject package holds no cards; a random-subset draw needs a package to sample"
        )
    blank = [name for name in names if not name.strip()]
    if blank:
        raise ValueError(f"subject package holds a blank card name: {blank[0]!r}")
    if seed is None:
        seed = secrets.randbelow(2**63)

    # Half the package, rounded down: floor(n / 2), which is at least 1 for
    # every package of two or more (#667 AC2).
    subset_size = len(names) // 2
    # Mersenne Twister seeded from the caller's integer: a pure function of
    # (package, seed), the same convention as fit.py's bootstrap stream. The
    # seed comes from the caller or from secrets, never from module state.
    rng = random.Random(seed)  # noqa: S311
    chosen = set(rng.sample(list(names), subset_size))
    card_names = tuple(name for name in names if name in chosen)

    arm = ArmSpec(
        name=arm_name,
        body_texts=tuple(subject_cards[name] for name in card_names),
    )
    validate_arm_specs((arm,))
    return SubsetArmDraw(seed=seed, card_names=card_names, arm=arm)
