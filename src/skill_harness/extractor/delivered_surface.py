"""Delivered skill surface extractor (#664).

Extracts the skill listing Claude Code delivered in a run's first user
message. For each subject card, records whether it was visible, truncated
(with delivered description length), or dropped. Also records each card's
position in the listing and the listing's total description tokens.

A listing that holds none of the subject's cards records as ``empty``,
never as ``missing``. Built-in and third-party skills in the listing are
recorded apart from the subject cards and are never counted as subject
cards.

Claude Code documents a 1,536-character truncation per description. Drops
at large listings are observed, not documented, so the extractor detects a
drop by absence from the delivered listing. It never predicts one from a
budget formula.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Claude Code's documented truncation limit per description.
TRUNCATION_LIMIT: int = 1536

# Type of a single card's delivery status.
CardStatus = Literal["visible", "truncated", "dropped"]

# Why a listing was classified as empty.
EmptyReason = Literal["no_listing", "listing_empty", "no_user_messages"]


class DeliveredCard(BaseModel):
    """One subject card's delivery status within the delivered listing."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    name: Annotated[str, Field(min_length=1)]
    """Skill name (from the subject card set)."""

    status: CardStatus
    """visible | truncated | dropped."""

    position: int | None
    """Zero-based index in the delivered listing. ``None`` when dropped."""

    delivered_description_length: int | None
    """Character length of the delivered description. ``None`` when dropped
    or when status is ``visible`` and the full description was delivered."""

    description_tokens: int | None
    """Estimated token count of the delivered description. ``None`` when
    dropped."""


class DeliveredListing(BaseModel):
    """The delivered skill surface for one run's transcript."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    subject_cards: tuple[DeliveredCard, ...]
    """Per-subject-card delivery status."""

    non_subject_cards: tuple[str, ...]
    """Names of built-in and third-party skills in the listing, in listing
    order. Never counted as subject cards."""

    listing_text: str
    """Raw text of the skill listing block extracted from the transcript.
    Empty string when no listing was found."""

    listing_description_tokens: int
    """Total estimated token count across all descriptions in the listing.
    Zero when no listing was found."""


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text. Roughly one token per 4 characters."""
    return max(1, len(text) // 4) if text else 0


def _parse_listing_cards(
    listing_text: str,
) -> list[tuple[str, str]]:
    """Parse a skill listing into (name, description) pairs.

    Each card starts with ``- name: description`` on a single line.
    Returns a list of (name, description) tuples in listing order.
    """
    cards: list[tuple[str, str]] = []
    for line in listing_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:]
        colon_pos = content.find(": ")
        if colon_pos < 0:
            continue
        name = content[:colon_pos]
        description = content[colon_pos + 2 :]
        if name:
            cards.append((name, description))
    return cards


def extract_delivered_listing(
    messages: Sequence[object],
    subject_cards: dict[str, str],
) -> DeliveredListing:
    """Extract the delivered skill surface from a run's transcript.

    Scans ``messages`` for the skill listing Claude Code delivered in the
    first user message. For each entry in ``subject_cards`` (a mapping of
    skill name to its full description text), determines whether the card
    was visible, truncated, or dropped.

    :param messages: The run's message list. Each message may have a
        ``content`` attribute that is a string or a list of text parts.
    :param subject_cards: Mapping of subject skill names to their full
        description text as declared in SKILL.md frontmatter.
    :returns: A ``DeliveredListing`` recording per-card delivery status.
    """
    listing_text = _find_listing_text(messages)

    if not listing_text:
        return _empty_listing(subject_cards, "no_listing")

    parsed_cards = _parse_listing_cards(listing_text)

    if not parsed_cards:
        return _empty_listing(subject_cards, "listing_empty")

    subject_names = set(subject_cards.keys())

    delivered_cards: list[DeliveredCard] = []
    for name in subject_names:
        description = subject_cards[name]
        card = _classify_card(name, description, parsed_cards)
        delivered_cards.append(card)

    non_subject = tuple(name for name, _ in parsed_cards if name not in subject_names)

    total_tokens = sum(_estimate_tokens(desc) for _, desc in parsed_cards)

    return DeliveredListing(
        subject_cards=tuple(delivered_cards),
        non_subject_cards=non_subject,
        listing_text=listing_text,
        listing_description_tokens=total_tokens,
    )


def _find_listing_text(messages: Sequence[object]) -> str:
    """Find the skill listing text from the first user message.

    Scans messages in order for the first user-role message whose content
    contains a skill listing (identified by the ``- skill-name:`` pattern).
    Returns the listing text if found, empty string otherwise.
    """
    for message in messages:
        content = getattr(message, "content", None)
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(part.get("text", ""))
                else:
                    t = getattr(part, "text", None)
                    if isinstance(t, str):
                        parts.append(t)
            text = "\n".join(parts)

        if not text:
            continue

        if _contains_listing(text):
            return text
    return ""


def _contains_listing(text: str) -> bool:
    """Check whether text contains a skill listing block.

    A listing is identified by at least one ``- name: description`` line.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ": " in stripped[2:]:
            return True
    return False


def _classify_card(
    name: str,
    full_description: str,
    parsed_cards: list[tuple[str, str]],
) -> DeliveredCard:
    """Classify one subject card's delivery status.

    Returns a ``DeliveredCard`` with the appropriate status, position, and
    delivered description length.
    """
    for i, (card_name, card_desc) in enumerate(parsed_cards):
        if card_name != name:
            continue

        if full_description in card_desc:
            return DeliveredCard(
                name=name,
                status="visible",
                position=i,
                delivered_description_length=None,
                description_tokens=_estimate_tokens(card_desc),
            )

        if (
            len(full_description) > TRUNCATION_LIMIT
            and card_desc == full_description[:TRUNCATION_LIMIT]
        ):
            return DeliveredCard(
                name=name,
                status="truncated",
                position=i,
                delivered_description_length=len(card_desc),
                description_tokens=_estimate_tokens(card_desc),
            )

        return DeliveredCard(
            name=name,
            status="truncated",
            position=i,
            delivered_description_length=len(card_desc),
            description_tokens=_estimate_tokens(card_desc),
        )

    return DeliveredCard(
        name=name,
        status="dropped",
        position=None,
        delivered_description_length=None,
        description_tokens=None,
    )


def _empty_listing(
    subject_cards: dict[str, str],
    reason: EmptyReason,
) -> DeliveredListing:
    """Build an empty listing result with every subject card dropped."""
    cards = tuple(
        DeliveredCard(
            name=name,
            status="dropped",
            position=None,
            delivered_description_length=None,
            description_tokens=None,
        )
        for name in subject_cards
    )
    return DeliveredListing(
        subject_cards=cards,
        non_subject_cards=(),
        listing_text="",
        listing_description_tokens=0,
    )
