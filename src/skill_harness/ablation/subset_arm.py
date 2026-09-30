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

Delivery integrity (#667, against #664): after a run, the delivered listing
is compared with the subset the arm intended. A card the arm included that
was dropped or truncated is flagged on the run record. The run is kept —
the check reports, never silently corrects.

This module is data + pure functions only. It never calls a model and never
writes evidence; the runner owns the run row, and the record seam
(``subset_draws`` in ``runs.config_json``) is where the seed and the chosen
card names become durable.
"""

from __future__ import annotations

import json
import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from skill_harness.ablation.arms import ArmSpec, validate_arm_specs
from skill_harness.extractor.delivered_surface import DeliveredListing

# Default declared-arm name for a seeded random-subset arm. Must match
# ARM_NAME_PATTERN (storage/models.py), which is what validate_arm_specs
# enforces below.
SUBSET_ARM_NAME: str = "subset_half"


@dataclass(frozen=True)
class SubsetArmDrawRecord:
    """One seeded random-subset draw, frozen into the run record (#667).

    The durable form of a draw: what ``runs.config_json.subset_draws`` holds
    once the run starts. Keyed by ``arm_name`` so a receipt's
    ``subject_identity.arms`` vocabulary (#554) points back at exactly this
    record — the trace from a published receipt to the seed and the subset.
    """

    arm_name: str
    seed: int
    card_names: tuple[str, ...]

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize for ``runs.config_json.subset_draws``."""
        return {
            "arm_name": self.arm_name,
            "seed": self.seed,
            "card_names": list(self.card_names),
        }

    @staticmethod
    def from_json_dict(d: Mapping[str, Any]) -> SubsetArmDrawRecord:
        """Deserialize from ``runs.config_json.subset_draws``."""
        return SubsetArmDrawRecord(
            arm_name=str(d["arm_name"]),
            seed=int(d["seed"]),
            card_names=tuple(str(name) for name in d["card_names"]),
        )


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

    @property
    def record(self) -> SubsetArmDrawRecord:
        """The durable form of this draw, for the run record to freeze."""
        return SubsetArmDrawRecord(
            arm_name=self.arm.name,
            seed=self.seed,
            card_names=self.card_names,
        )


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


def trace_subset_draw(config_json: str, arm_name: str) -> SubsetArmDrawRecord:
    """Trace a receipt's arm name back to the seed and the subset names (#667).

    A SERS receipt carries ``subject_identity.arms`` — the run's declared arm
    vocabulary (#554). Given that name and the run's ``runs.config_json``,
    return the subset draw frozen for the arm: its seed and its chosen card
    names. This is the join that makes a published receipt re-checkable
    against the record of what was actually assembled.

    :param config_json: The stored ``runs.config_json`` text of one run.
    :param arm_name: The arm name to look up, as the receipt declares it.
    :returns: The draw recorded for that arm.
    :raises ValueError: the run record carries no subset draw for that arm.
    """
    config = json.loads(config_json)
    for raw in config.get("subset_draws", []):
        record = SubsetArmDrawRecord.from_json_dict(raw)
        if record.arm_name == arm_name:
            return record
    raise ValueError(f"run record carries no subset draw for arm {arm_name!r}")


@dataclass(frozen=True)
class DeliveryIntegrity:
    """Post-run comparison of the intended subset against the delivered listing (#667).

    Every intended card the arm included is checked against #664's delivered
    listing. A card that was dropped or truncated is flagged by name.
    ``integrity_ok`` is the flag: ``False`` when any intended card was
    delivered damaged or not at all. The check never rewrites the listing,
    the run, or the evidence — the run is kept, and the flag rides on the
    record.
    """

    intended_names: tuple[str, ...]
    """The arm's intended card names, in subset order."""

    flagged_names: tuple[str, ...]
    """Intended cards that were dropped or truncated in the delivered listing."""

    integrity_ok: bool
    """``True`` when every intended card was delivered whole; ``False``
    otherwise. This is the integrity flag."""


def check_delivery_integrity(
    listing: DeliveredListing,
    intended_names: Sequence[str],
) -> DeliveryIntegrity:
    """Compare the delivered listing with the subset the arm intended (#667).

    A card the arm included that is missing from the delivered listing (the
    extractor records that as ``dropped``) or present only in truncated form
    is flagged. Cards delivered whole leave the flag down. Pure function: no
    writes, no corrections, no exceptions for a damaged delivery — the damage
    is reported, the run is kept.

    :param listing: The delivered skill surface extracted from the run's
        transcript (#664).
    :param intended_names: The card names the arm's subset included.
    :returns: The integrity verdict naming every flagged card.
    """
    delivered = {card.name: card for card in listing.subject_cards}
    flagged: list[str] = []
    for name in intended_names:
        card = delivered.get(name)
        if card is None or card.status in ("dropped", "truncated"):
            flagged.append(name)
    return DeliveryIntegrity(
        intended_names=tuple(intended_names),
        flagged_names=tuple(flagged),
        integrity_ok=not flagged,
    )


@dataclass(frozen=True)
class SubsetRunRecord:
    """The screen-facing record of one seeded-subset run (#667).

    The run record for a subset arm: the draw frozen into ``runs.config_json``
    at run start, plus — once the delivered listing is known — the delivery
    integrity verdict. Assembled from the stored config; it never rewrites it.
    """

    run_id: str
    subset_draws: tuple[SubsetArmDrawRecord, ...]
    delivery_integrity: DeliveryIntegrity | None
    """The post-run delivery check, or ``None`` when no listing was supplied."""


def build_subset_run_record(
    run_id: str,
    config_json: str,
    listing: DeliveredListing | None = None,
) -> SubsetRunRecord:
    """Assemble the subset run record from the frozen config and listing (#667).

    Reads the draws the run froze into ``runs.config_json`` and, when a
    delivered listing is supplied, flags every intended card the listing
    dropped or truncated. The run is kept: a failed integrity check flags the
    record and never corrects, rewrites, or discards the run or its evidence.

    :param run_id: The run's identifier.
    :param config_json: The stored ``runs.config_json`` text of that run.
    :param listing: The delivered listing extracted from the transcript, or
        ``None`` to record the draw without a delivery verdict.
    :returns: The run record carrying the draw and, if supplied, the flag.
    """
    config = json.loads(config_json)
    draws = tuple(SubsetArmDrawRecord.from_json_dict(raw) for raw in config.get("subset_draws", []))
    integrity: DeliveryIntegrity | None = None
    if listing is not None:
        intended: list[str] = []
        for draw in draws:
            for name in draw.card_names:
                if name not in intended:
                    intended.append(name)
        integrity = check_delivery_integrity(listing, intended)
    return SubsetRunRecord(
        run_id=run_id,
        subset_draws=draws,
        delivery_integrity=integrity,
    )
