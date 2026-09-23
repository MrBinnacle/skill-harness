"""Tests for #651: the parse-csv placebo card and its surface-match check. No model."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from skill_harness.extractor.parser import parse_skill_file

_SCREEN_DIR = Path(__file__).resolve().parents[1] / "scripts" / "screens" / "419"

PLACEBO_SKILL = _SCREEN_DIR / "v5_arms" / "placebo" / "parse-csv" / "SKILL.md"
FULL_SKILL = _SCREEN_DIR / "v4_arms" / "full" / "pull-rebase" / "SKILL.md"

BANNED_RE = re.compile(r"\b(git|rebase|manifest|push|commit|sha|config)\b", re.IGNORECASE)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCREEN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def shape(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    return {
        "h2": len(re.findall(r"^## ", text, re.M)),
        "fences": text.count("```"),
        "steps": len(re.findall(r"^\d+\. ", text, re.M)),
        "bullets": len(re.findall(r"^- ", text, re.M)),
    }


def test_placebo_matches_the_card_section_for_section() -> None:
    assert shape(PLACEBO_SKILL) == shape(FULL_SKILL)


def test_placebo_length_and_description_are_within_the_match_band() -> None:
    placebo, full = parse_skill_file(PLACEBO_SKILL), parse_skill_file(FULL_SKILL)
    words_p, words_f = len(placebo.body.split()), len(full.body.split())
    assert abs(words_p - words_f) / words_f <= 0.10, (words_p, words_f)
    desc_p = len(str(placebo.frontmatter["description"]))
    desc_f = len(str(full.frontmatter["description"]))
    assert abs(desc_p - desc_f) / desc_f <= 0.10, (desc_p, desc_f)


def test_placebo_is_silent_on_domain_terms() -> None:
    text = PLACEBO_SKILL.read_text(encoding="utf-8")
    hits = BANNED_RE.findall(text)
    assert hits == []


def test_the_lint_catches_the_card_it_guards_against() -> None:
    hits = {h.lower() for h in BANNED_RE.findall(FULL_SKILL.read_text(encoding="utf-8"))}
    assert {"git", "rebase", "push", "config"} <= hits


def test_placebo_name_matches_its_directory() -> None:
    assert parse_skill_file(PLACEBO_SKILL).frontmatter["name"] == PLACEBO_SKILL.parent.name


def test_placebo_names_no_fixture_file_types() -> None:
    """The surface-match check refuses when the fixture tree contains file types the placebo names.
    The fixture tree has .md, .py, .sh, .yaml — not .csv, .tsv, .xlsx."""
    sm = _load("v5_surface_match")
    fixture_types = sm.fixture_file_types(sm.HERE)
    placebo_types = sm.PLACEBO_FILE_TYPES
    assert not (placebo_types & fixture_types), (
        f"fixture tree has types {placebo_types & fixture_types} that the placebo names"
    )


def test_surface_match_check_passes() -> None:
    sm = _load("v5_surface_match")
    assert sm.check() == 0


def test_surface_match_check_refuses_a_poison_placebo(tmp_path: Path) -> None:
    """A placebo containing 'git' must be refused by the surface-match check."""
    sm = _load("v5_surface_match")
    poison_desc = (
        "Use before git push where a repository holds config files. "
        "A .gitignore entry does NOT stop git add -f. Scan tracked files first."
    )
    poison_body = (
        "# poison\n\n## The trap\n\nRun git push to see the effect.\n\n"
        "## When this fires\n\n- git config is true\n"
    )
    poison_dir = tmp_path / "poison"
    poison_dir.mkdir()
    (poison_dir / "SKILL.md").write_text(
        f"---\nname: poison\ndescription: {poison_desc}\n---\n\n{poison_body}",
        encoding="utf-8",
    )
    original_placebo = sm.PLACEBO_SKILL
    try:
        sm.PLACEBO_SKILL = poison_dir / "SKILL.md"  # type: ignore[attr-defined]
        assert sm.check() == 1
    finally:
        sm.PLACEBO_SKILL = original_placebo  # type: ignore[attr-defined]


def test_surface_match_check_refuses_a_wrong_name_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sm = _load("v5_surface_match")
    malformed = tmp_path / "malformed-skill.md"
    malformed.write_text(
        PLACEBO_SKILL.read_text(encoding="utf-8").replace("name: parse-csv", "name: parsecsv"),
        encoding="utf-8",
    )
    original_placebo = sm.PLACEBO_SKILL
    try:
        sm.PLACEBO_SKILL = malformed  # type: ignore[attr-defined]
        assert sm.check() == 1
    finally:
        sm.PLACEBO_SKILL = original_placebo  # type: ignore[attr-defined]
    assert "names must use the two-token kebab shape" in capsys.readouterr().out


def test_listing_position_regex_matches_numbered_entries() -> None:
    s1a = _load("v5_cue_stage1a")
    assert s1a._LISTING_NUMBERED_RE.match("1. parse-csv: Use before")
    assert s1a._LISTING_NUMBERED_RE.match("2. pull-rebase: Use before")
    assert not s1a._LISTING_NUMBERED_RE.match("Skills:")
    assert not s1a._LISTING_NUMBERED_RE.match("- a bullet")


def test_placebo_desc_constant_matches_card() -> None:
    s1a = _load("v5_cue_stage1a")
    placebo = parse_skill_file(PLACEBO_SKILL)
    assert str(placebo.frontmatter["description"]) == s1a.PLACEBO_DESC
    full = parse_skill_file(FULL_SKILL)
    assert str(full.frontmatter["description"]) == s1a.FULL_DESC
