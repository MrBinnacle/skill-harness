"""Tests for the delivered skill surface extractor (#664).

Per-ticket rule: write the test first, watch it fail for the right reason,
then make it pass. A test that passed before the change pins nothing.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from skill_harness.extractor.delivered_surface import (
    TRUNCATION_LIMIT,
    extract_delivered_listing,
)
from skill_harness.oracles.tier1.verbosity import count_tokens

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _user(content: str) -> SimpleNamespace:
    return SimpleNamespace(role="user", content=content)


def _system(content: str) -> SimpleNamespace:
    return SimpleNamespace(role="system", content=content)


def _assistant(content: str) -> SimpleNamespace:
    return SimpleNamespace(role="assistant", content=content)


def _listing_message(
    cards: dict[str, str],
    *,
    header: str = "The following skills are available for use with the Skill tool:\n",
    footer: str = "\nUse the Skill tool to invoke them.",
) -> SimpleNamespace:
    """Build a user message containing a skill listing from name->description."""
    lines = [header.rstrip()]
    for name, desc in cards.items():
        lines.append(f"- {name}: {desc}")
    lines.append(footer.lstrip())
    return _user("\n".join(lines))


# ---------------------------------------------------------------------------
# AC1: Full subject listing — every card reads visible with its position
# ---------------------------------------------------------------------------


def test_full_listing_all_cards_visible_with_position() -> None:
    """AC1: a transcript with the full subject listing records every card
    as visible, with its zero-based position in the listing."""
    subject = {
        "alpha-skill": "Does alpha things thoroughly.",
        "beta-skill": "Handles beta scenarios with care.",
    }
    messages = [
        _system("You are a helpful assistant."),
        _listing_message(subject),
        _assistant("I will use the skill."),
    ]
    result = extract_delivered_listing(messages, subject)

    assert len(result.subject_cards) == 2
    assert tuple(card.name for card in result.subject_cards) == ("alpha-skill", "beta-skill")

    alpha = next(c for c in result.subject_cards if c.name == "alpha-skill")
    assert alpha.status == "visible"
    assert alpha.position == 0
    assert alpha.delivered_description_length is None

    beta = next(c for c in result.subject_cards if c.name == "beta-skill")
    assert beta.status == "visible"
    assert beta.position == 1
    assert beta.delivered_description_length is None


def test_full_listing_records_listing_text() -> None:
    """AC1: the listing text is preserved on the result."""
    subject = {"my-skill": "A short description."}
    messages = [_listing_message(subject)]
    result = extract_delivered_listing(messages, subject)

    assert "- my-skill: A short description." in result.listing_text
    assert result.listing_description_tokens > 0
    assert result.empty_reason is None


def test_listing_excludes_task_bullets_before_and_after_the_delivered_block() -> None:
    """Only Claude Code's listing cards contribute positions and token counts."""
    description = "Antidisestablishmentarianism requires careful handling."
    subject = {"my-skill": description}
    messages = [
        _user(
            "Task checklist:\n"
            "- prepare-worktree: create an isolated worktree\n"
            "<system-reminder> The following skills are available for use with the Skill tool:\n"
            f"- my-skill: {description}\n"
            "</system-reminder>\n"
            "- report-result: state the outcome"
        )
    ]
    result = extract_delivered_listing(messages, subject)

    card = result.subject_cards[0]
    assert card.status == "visible"
    assert card.position == 0
    assert card.description_tokens == count_tokens(description)
    assert result.non_subject_cards == ()
    assert result.listing_description_tokens == count_tokens(description)


# ---------------------------------------------------------------------------
# AC2: Poison fixture — one description removed reads dropped
# ---------------------------------------------------------------------------


def test_poison_one_card_removed_reads_dropped() -> None:
    """AC2: a listing missing one subject card reads that card as dropped,
    never as visible."""
    full_listing = {
        "alpha-skill": "Does alpha things.",
        "beta-skill": "Handles beta scenarios.",
        "gamma-skill": "Manages gamma state.",
    }
    delivered = {
        "alpha-skill": "Does alpha things.",
        # beta-skill deliberately omitted
        "gamma-skill": "Manages gamma state.",
    }
    messages = [_listing_message(delivered)]
    result = extract_delivered_listing(messages, full_listing)

    alpha = next(c for c in result.subject_cards if c.name == "alpha-skill")
    assert alpha.status == "visible"

    beta = next(c for c in result.subject_cards if c.name == "beta-skill")
    assert beta.status == "dropped"
    assert beta.position is None
    assert beta.delivered_description_length is None

    gamma = next(c for c in result.subject_cards if c.name == "gamma-skill")
    assert gamma.status == "visible"


# ---------------------------------------------------------------------------
# AC3: Poison fixture — one description cut at 1,536 reads truncated
# ---------------------------------------------------------------------------


def test_poison_one_description_truncated_at_limit() -> None:
    """AC3: a listing with one description cut at 1,536 characters reads
    that card as truncated, with the delivered description length."""
    full_description = "x" * (TRUNCATION_LIMIT + 100)
    truncated_description = "x" * TRUNCATION_LIMIT

    subject = {
        "short-skill": "Short.",
        "long-skill": full_description,
    }
    delivered = {
        "short-skill": "Short.",
        "long-skill": truncated_description,
    }
    messages = [_listing_message(delivered)]
    result = extract_delivered_listing(messages, subject)

    short = next(c for c in result.subject_cards if c.name == "short-skill")
    assert short.status == "visible"

    long_card = next(c for c in result.subject_cards if c.name == "long-skill")
    assert long_card.status == "truncated"
    assert long_card.position is not None
    assert long_card.delivered_description_length == TRUNCATION_LIMIT


# ---------------------------------------------------------------------------
# AC4: Transcript with no listing records empty, never guessed
# ---------------------------------------------------------------------------


def test_no_user_messages_records_empty_with_typed_reason() -> None:
    """AC4: a transcript with no user messages records a typed, empty listing."""
    subject = {"my-skill": "Some description."}
    messages = [
        _system("You are helpful."),
        _assistant("I will help."),
    ]
    result = extract_delivered_listing(messages, subject)

    assert result.listing_text == ""
    assert result.listing_description_tokens == 0
    assert result.empty_reason == "no_user_messages"
    assert len(result.subject_cards) == 1
    card = result.subject_cards[0]
    assert card.name == "my-skill"
    assert card.status == "dropped"
    assert card.position is None


def test_empty_listing_block_records_empty() -> None:
    """AC4: a user message without the Claude Code listing records empty."""
    subject = {"my-skill": "Some description."}
    messages = [_user("Hello, no skills here.")]
    result = extract_delivered_listing(messages, subject)

    assert result.listing_text == ""
    assert all(c.status == "dropped" for c in result.subject_cards)
    assert result.empty_reason == "no_listing"


def test_messages_list_with_no_user_messages() -> None:
    """AC4: a transcript with no user messages records empty."""
    subject = {"my-skill": "Some description."}
    messages = [
        _system("System prompt."),
        _assistant("Response."),
    ]
    result = extract_delivered_listing(messages, subject)

    assert result.listing_text == ""
    assert all(c.status == "dropped" for c in result.subject_cards)
    assert result.empty_reason == "no_user_messages"


def test_listing_header_without_cards_records_typed_empty_listing() -> None:
    """AC4: a delivered listing header with no cards is structurally empty."""
    subject = {"my-skill": "Some description."}
    messages = [_user("The following skills are available for use with the Skill tool:")]
    result = extract_delivered_listing(messages, subject)

    assert result.listing_text == ""
    assert result.listing_description_tokens == 0
    assert result.empty_reason == "listing_empty"
    assert result.subject_cards[0].status == "dropped"


def test_uses_only_the_first_user_message_for_the_delivered_listing() -> None:
    """A later listing is not the surface delivered before the run started."""
    subject = {"my-skill": "My skill description."}
    messages = [
        _system(
            "The following skills are available for use with the Skill tool:\n"
            "- my-skill: My skill description."
        ),
        _user("Perform the task."),
        _listing_message(subject),
    ]
    result = extract_delivered_listing(messages, subject)

    assert result.empty_reason == "no_listing"
    assert result.subject_cards[0].status == "dropped"


def test_unrelated_bullets_in_the_first_user_message_are_not_a_listing() -> None:
    """Task Markdown must not be attributed to Claude Code's delivered surface."""
    subject = {"my-skill": "My skill description."}
    messages = [_user("Follow these steps:\n- my-skill: My skill description.")]
    result = extract_delivered_listing(messages, subject)

    assert result.empty_reason == "no_listing"
    assert result.subject_cards[0].status == "dropped"


# ---------------------------------------------------------------------------
# AC5: Built-in and third-party skills recorded apart, never counted as
#       subject cards
# ---------------------------------------------------------------------------


def test_builtin_skills_recorded_apart_not_counted_as_subject() -> None:
    """AC5: built-in and third-party skills in the listing are recorded in
    non_subject_cards and are never counted as subject cards."""
    subject = {"my-skill": "My skill description."}
    delivered = {
        "my-skill": "My skill description.",
        "built-in-read": "Read files from disk.",
        "third-party-search": "Search the web.",
    }
    messages = [_listing_message(delivered)]
    result = extract_delivered_listing(messages, subject)

    subject_names = {c.name for c in result.subject_cards}
    assert subject_names == {"my-skill"}

    assert "built-in-read" in result.non_subject_cards
    assert "third-party-search" in result.non_subject_cards
    assert "my-skill" not in result.non_subject_cards


def test_only_non_subject_skills_yields_empty_subject_cards() -> None:
    """AC5: a listing with only non-subject skills yields no subject cards
    as visible."""
    subject = {"my-skill": "My skill description."}
    delivered = {
        "built-in-read": "Read files.",
        "built-in-write": "Write files.",
    }
    messages = [_listing_message(delivered)]
    result = extract_delivered_listing(messages, subject)

    assert len(result.subject_cards) == 1
    assert result.subject_cards[0].status == "dropped"
    assert len(result.non_subject_cards) == 2


# ---------------------------------------------------------------------------
# AC6: Gate — tested by running ruff and mypy (see CI)
# The gate is run after each criterion in the build process. This test
# file itself passes the gate; the CI job runs it over all of src/ tests/.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------


def test_result_model_is_frozen() -> None:
    """DeliveredListing is immutable (frozen=True)."""
    subject = {"s": "d."}
    result = extract_delivered_listing([], subject)
    with pytest.raises(Exception):
        result.listing_text = "changed"


def test_delivered_card_model_is_frozen() -> None:
    """DeliveredCard is immutable (frozen=True)."""
    subject = {"s": "d."}
    result = extract_delivered_listing([], subject)
    card = result.subject_cards[0]
    with pytest.raises(Exception):
        card.status = "visible"


def test_empty_subject_cards_yields_no_subject_cards() -> None:
    """An empty subject_cards dict yields an empty subject_cards tuple."""
    result = extract_delivered_listing([], {})
    assert result.subject_cards == ()
    assert result.non_subject_cards == ()


def test_listing_description_tokens_sum_of_all_cards() -> None:
    """listing_description_tokens is the sum across all listing cards."""
    subject = {"a": "AAAA", "b": "BBBB"}
    delivered = {"a": "AAAA", "b": "BBBB", "c": "CCCCCCCC"}
    messages = [_listing_message(delivered)]
    result = extract_delivered_listing(messages, subject)

    assert result.listing_description_tokens == (
        count_tokens("AAAA") + count_tokens("BBBB") + count_tokens("CCCCCCCC")
    )


def test_content_as_list_of_dicts() -> None:
    """Messages with content as a list of dicts are handled."""
    subject = {"s": "desc."}
    messages = [
        SimpleNamespace(
            role="user",
            content=[
                {
                    "text": (
                        "The following skills are available for use with the Skill tool:\n"
                        "- s: desc.\n"
                    )
                }
            ],
        ),
    ]
    result = extract_delivered_listing(messages, subject)
    assert result.subject_cards[0].status == "visible"


def test_content_as_list_of_namespace_parts() -> None:
    """Messages with content as a list of SimpleNamespace parts are handled."""
    subject = {"s": "desc."}
    messages = [
        SimpleNamespace(
            role="user",
            content=[
                SimpleNamespace(
                    text=(
                        "The following skills are available for use with the Skill tool:\n"
                        "- s: desc.\n"
                    )
                )
            ],
        ),
    ]
    result = extract_delivered_listing(messages, subject)
    assert result.subject_cards[0].status == "visible"
