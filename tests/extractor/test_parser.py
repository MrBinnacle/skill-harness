"""Tests for skill_harness.extractor.parser."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from skill_harness.extractor.errors import MalformedSkillError
from skill_harness.extractor.parser import parse_skill_file

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def simple_skill(tmp_path: Path) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text(
        "---\nname: my-skill\nversion: 1.0\n---\n\n# Instructions\nDo the thing.\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def no_frontmatter_skill(tmp_path: Path) -> Path:
    p = tmp_path / "plain.md"
    p.write_text("# Instructions\nBe concise.\n", encoding="utf-8")
    return p


@pytest.fixture()
def unclosed_frontmatter_skill(tmp_path: Path) -> Path:
    p = tmp_path / "unclosed.md"
    p.write_text("---\nname: unclosed\n# Body starts here without closing ---\nDo things.\n")
    return p


# ---------------------------------------------------------------------------
# parse_skill_file — frontmatter extraction
# ---------------------------------------------------------------------------


def test_parses_name_from_frontmatter(simple_skill: Path) -> None:
    result = parse_skill_file(simple_skill)
    assert result.name == "my-skill"


def test_parses_frontmatter_key_value(simple_skill: Path) -> None:
    result = parse_skill_file(simple_skill)
    assert result.frontmatter["name"] == "my-skill"
    assert result.frontmatter["version"] == "1.0"


def test_body_excludes_frontmatter(simple_skill: Path) -> None:
    result = parse_skill_file(simple_skill)
    assert "---" not in result.body
    assert "Instructions" in result.body


def test_no_frontmatter_body_is_full_content(no_frontmatter_skill: Path) -> None:
    result = parse_skill_file(no_frontmatter_skill)
    assert "Be concise" in result.body
    assert result.frontmatter == {}


def test_no_frontmatter_name_falls_back_to_stem(no_frontmatter_skill: Path) -> None:
    result = parse_skill_file(no_frontmatter_skill)
    assert result.name == "plain"


def test_unclosed_frontmatter_treats_whole_file_as_body(unclosed_frontmatter_skill: Path) -> None:
    """When there is no closing ---, frontmatter block is ignored (whole file is body)."""
    result = parse_skill_file(unclosed_frontmatter_skill)
    assert result.frontmatter == {}
    assert "Do things" in result.body


# ---------------------------------------------------------------------------
# parse_skill_file — SHA-256 computation
# ---------------------------------------------------------------------------


def test_source_sha256_matches_file_bytes(simple_skill: Path) -> None:
    raw = simple_skill.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    result = parse_skill_file(simple_skill)
    assert result.source_sha256 == expected


def test_source_path_is_absolute(simple_skill: Path) -> None:
    result = parse_skill_file(simple_skill)
    assert Path(result.source_path).is_absolute()


# ---------------------------------------------------------------------------
# parse_skill_file — error cases
# ---------------------------------------------------------------------------


def test_empty_body_raises_malformed(tmp_path: Path) -> None:
    p = tmp_path / "empty.md"
    p.write_text("---\nname: empty\n---\n   \n\t\n", encoding="utf-8")
    with pytest.raises(MalformedSkillError, match="empty body"):
        parse_skill_file(p)


def test_completely_empty_file_raises_malformed(tmp_path: Path) -> None:
    p = tmp_path / "blank.md"
    p.write_text("", encoding="utf-8")
    with pytest.raises(MalformedSkillError, match="empty body"):
        parse_skill_file(p)


def test_non_utf8_bytes_raise_malformed(tmp_path: Path) -> None:
    """Non-UTF-8 input must raise, not silently produce U+FFFD-mangled text.

    Silent replacement would produce a body that does not match the
    source_sha256 audit trail (computed over raw bytes) — Coverage and
    Contribution metrics would derive from a corrupted body while
    provenance says "clean."
    """
    p = tmp_path / "latin1.md"
    p.write_bytes(b"# Skill\n\nca\xe9 latte\n")  # 0xE9 = é in Latin-1, invalid UTF-8
    with pytest.raises(MalformedSkillError, match="not valid UTF-8"):
        parse_skill_file(p)


def test_frontmatter_only_fixture_raises_malformed() -> None:
    """The frontmatter_only.md fixture should raise because body is empty."""
    with pytest.raises(MalformedSkillError):
        parse_skill_file(_FIXTURES / "frontmatter_only.md")


# ---------------------------------------------------------------------------
# parse_skill_file — mostly-prose fixture
# ---------------------------------------------------------------------------


def test_mostly_prose_fixture_parses(mostly_prose_path: Path) -> None:
    result = parse_skill_file(mostly_prose_path)
    assert result.name == "mostly-prose-skill"
    assert "Background" in result.body


@pytest.fixture()
def mostly_prose_path() -> Path:
    return _FIXTURES / "mostly_prose.md"
