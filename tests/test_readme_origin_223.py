"""README origin reconciliation lock (#223 / MrBinnacle/skills#66)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

_README = Path(__file__).resolve().parents[1] / "README.md"
_WHY = Path(__file__).resolve().parents[1] / "docs" / "why-this-exists.md"


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def _why() -> str:
    return _WHY.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + len(heading) + 3)
    return text[start:] if end == -1 else text[start:end]


def test_why_this_exists_opens_on_whether_you_can_tell() -> None:
    section = _section(_readme(), "Why this exists")
    opening = section.split("\n\n", 1)[1].split("\n\n", 1)[0]

    assert opening == "I wanted to know if you could tell if a skill was any good."
    assert "I wanted to know whether a skill was any good." not in section


def test_commit_claim_matches_the_public_collection_measurement() -> None:
    """The #223 claim, re-registered to the file the 2026-08-23 ruling moved it to.

    The ruling took the commit-count comparison off the front page and named
    `docs/why-this-exists.md` as its destination, with the derivation commands
    intact. The lock follows the content rather than being retired with it:
    retiring it would have loosened a guard to make a removal pass, which is
    the opposite of what a move is.

    What is asserted is the SHAPE of the claim - a dated measurement, two
    integer counts, the two derivation commands, the fresh-clone basis - and
    not the values. Locking the values made the guard backwards: it could not
    tell a stale figure from a fresh one, and the only thing it could stop was
    someone correcting the figure. It ran for eighteen days over a count that
    had drifted from 71/323 to 152/511, then failed the commit that fixed it.

    A shape lock still cannot detect staleness. That is the steering repo's issue 61,
    and it needs a freshly measured comparison, not a stricter string.
    """
    section = _section(_why(), "The size of the detour")

    measured = re.search(r"Measured on (\d{4})-(\d{2})-(\d{2}):", section)
    assert measured, "the detour section must carry a dated measurement"
    date(int(measured[1]), int(measured[2]), int(measured[3]))

    counts = re.search(
        r"\*\*(\d+) commits of collection against (\d+) commits of machinery",
        section,
    )
    assert counts, "the claim must state both counts as integers"
    collection, machinery = int(counts[1]), int(counts[2])
    assert collection > 0 and machinery > 0
    assert machinery > collection, (
        "the claim is that the machinery outweighs the collection; if that "
        "reverses, the sentence needs rewriting rather than re-measuring"
    )

    assert (
        "git clone https://github.com/MrBinnacle/skills.git        "
        "&& git -C skills        rev-list --count HEAD"
    ) in section
    assert (
        "git clone https://github.com/MrBinnacle/skill-harness.git "
        "&& git -C skill-harness rev-list --count HEAD"
    ) in section
    assert "The basis is a fresh clone at `HEAD`" in section


def test_commit_claim_is_gone_from_the_front_page() -> None:
    """A move is a removal AND an arrival. This is the removal half.

    Without it the lock above is satisfied by the claim existing at the
    destination while a copy stays on the front page, which is the state the
    ruling refused - and two copies of a dated figure drift the moment either
    is updated.
    """
    text = _readme()

    assert not re.search(r"\d+ commits of collection", text), (
        "the commit comparison must not reappear on the front page in any revision of its figures"
    )
    assert "rev-list --count HEAD" not in text
    assert "docs/why-this-exists.md" in text, (
        "the front page must point at where the comparison went"
    )


def test_other_half_describes_the_rewritten_collection() -> None:
    section = _section(_readme(), "The other half")
    rendered = " ".join(section.split())

    assert "each skill carries its own dated evidence record" in rendered
    assert "controlled results are read from that skill's record" in rendered
    assert "publicly retired" in rendered
    assert "against its stated criterion" in rendered
    assert "each skill carries a dated evidence record" not in rendered
