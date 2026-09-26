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

from skill_harness.oracles.tier1.verbosity import count_tokens

# Claude Code's documented truncation limit per description.
TRUNCATION_LIMIT: int = 1536

# Type of a single card's delivery status.
CardStatus = Literal["visible", "truncated", "dropped"]

# Why a listing was classified as empty.
EmptyReason = Literal["no_listing", "listing_empty", "no_user_messages"]

_LISTING_HEADER = "The following skills are available for use with the Skill tool:"


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

    empty_reason: EmptyReason | None
    """Structural reason no listing was extracted, or ``None`` for a listing."""


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
    listing_text, empty_reason = _find_listing_text(messages)

    if empty_reason is not None:
        return _empty_listing(subject_cards, empty_reason)

    parsed_cards = _parse_listing_cards(listing_text)

    if not parsed_cards:
        return _empty_listing(subject_cards, "listing_empty")

    subject_names = set(subject_cards.keys())

    delivered_cards: list[DeliveredCard] = []
    for name, description in subject_cards.items():
        card = _classify_card(name, description, parsed_cards)
        delivered_cards.append(card)

    non_subject = tuple(name for name, _ in parsed_cards if name not in subject_names)

    total_tokens = sum(count_tokens(desc) for _, desc in parsed_cards)

    return DeliveredListing(
        subject_cards=tuple(delivered_cards),
        non_subject_cards=non_subject,
        listing_text=listing_text,
        listing_description_tokens=total_tokens,
        empty_reason=None,
    )


def _find_listing_text(messages: Sequence[object]) -> tuple[str, EmptyReason | None]:
    """Find the skill listing text from the first user message.

    Returns a typed structural reason when no listing can be extracted. A
    listing on a non-user message or a later user message is not delivered
    context and must not be attributed to the run.
    """
    for message in messages:
        if getattr(message, "role", None) != "user":
            continue

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

        listing_start = text.find(_LISTING_HEADER)
        if listing_start >= 0:
            return _listing_block(text[listing_start:]), None
        return "", "no_listing"
    return "", "no_user_messages"


def _listing_block(text_after_header: str) -> str:
    """Extract the header and contiguous card lines from a user message.

    The first user message also carries task text, which can contain Markdown
    bullets. Only the contiguous card lines following Claude Code's header are
    part of the delivered listing.
    """
    lines = text_after_header.splitlines()
    if not lines:
        return ""

    listing_lines = [lines[0]]
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped.startswith("- ") or ": " not in stripped[2:]:
            break
        listing_lines.append(line)
    return "\n".join(listing_lines)


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
                description_tokens=count_tokens(card_desc),
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
                description_tokens=count_tokens(card_desc),
            )

        return DeliveredCard(
            name=name,
            status="truncated",
            position=i,
            delivered_description_length=len(card_desc),
            description_tokens=count_tokens(card_desc),
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
        empty_reason=reason,
    )
