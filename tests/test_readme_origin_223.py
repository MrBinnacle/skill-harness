"""README origin reconciliation lock (#223 / MrBinnacle/skills#66)."""

from __future__ import annotations

from pathlib import Path

_README = Path(__file__).resolve().parents[1] / "README.md"


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + len(heading) + 3)
    return text[start:] if end == -1 else text[start:end]


def test_why_this_exists_opens_on_whether_you_can_tell() -> None:
    section = _section(_readme(), "Why this exists")
    opening = section.split("\n\n", 1)[1].split("\n\n", 1)[0]

    assert opening == "I wanted to know if you could tell if a skill was any good."
    assert "I wanted to know whether a skill was any good." not in section
