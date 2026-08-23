"""README origin reconciliation lock (#223 / MrBinnacle/skills#66)."""

from __future__ import annotations

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

    What is still asserted here is unchanged - the figures, the two commands,
    and the fresh-clone basis. What changed is only which file states them.
    """
    section = _section(_why(), "The size of the detour")

    assert "Measured on 2026-08-15" in section
    assert "**71 commits of collection against 323 commits of machinery" in section
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

    assert "71 commits of collection" not in text
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
