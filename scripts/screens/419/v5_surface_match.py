"""Surface-match check for the parse-csv placebo card (S477).

Prints both descriptions' character, word and token counts and both bodies' line counts and
section headings. Refuses a placebo description or body that contains a banned term (git, rebase,
manifest, push, commit, SHA, config), and refuses when the fixture tree contains any file type
the placebo names (.csv, .tsv, .xlsx). The description length tolerance is 10%.

Run: PYTHONPATH=src python scripts/screens/419/v5_surface_match.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_harness.extractor.parser import parse_skill_file

HERE = Path(__file__).resolve().parent
PLACEBO_DIR = HERE / "v5_arms" / "placebo" / "parse-csv"
PLACEBO_SKILL = PLACEBO_DIR / "SKILL.md"
FULL_SKILL = HERE / "v4_arms" / "full" / "pull-rebase" / "SKILL.md"

BANNED_RE = re.compile(r"\b(git|rebase|manifest|push|commit|sha|config)\b", re.IGNORECASE)

PLACEBO_FILE_TYPES = {".csv", ".tsv", ".xlsx"}

SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
NAME_RE = re.compile(r"^[a-z]+-[a-z]+$")


def tokenize(text: str) -> list[str]:
    """Whitespace tokenizer for surface-match counts."""
    return text.split()


def heading_counts(body: str) -> list[str]:
    return SECTION_RE.findall(body)


def fixture_file_types(root: Path) -> set[str]:
    """All file extensions in the fixture tree (the screen directory itself)."""
    return {p.suffix.lower() for p in root.rglob("*") if p.is_file()}


def check() -> int:
    placebo = parse_skill_file(PLACEBO_SKILL)
    full = parse_skill_file(FULL_SKILL)

    placebo_desc = str(placebo.frontmatter["description"])
    full_desc = str(full.frontmatter["description"])

    print("=== Name-shape match ===")
    print(f"  Placebo: {placebo.name}")
    print(f"  Full:    {full.name}")
    if not (NAME_RE.fullmatch(placebo.name) and NAME_RE.fullmatch(full.name)):
        print("  REFUSED: names must use the two-token kebab shape")
        return 1
    print("  PASS: both names use the two-token kebab shape")
    print()

    print("=== Description surface match ===")
    print(
        f"  Placebo: {len(placebo_desc):4d} chars  {len(placebo_desc.split()):3d} words  "
        f"{len(tokenize(placebo_desc)):3d} tokens"
    )
    print(
        f"  Full:    {len(full_desc):4d} chars  {len(full_desc.split()):3d} words  "
        f"{len(tokenize(full_desc)):3d} tokens"
    )
    desc_char_ratio = abs(len(placebo_desc) - len(full_desc)) / len(full_desc)
    print(f"  Char diff: {desc_char_ratio:.1%}  (tolerance 10%)")

    print()
    print("=== Body surface match ===")
    placebo_lines = placebo.body.splitlines()
    full_lines = full.body.splitlines()
    print(f"  Placebo: {len(placebo_lines):3d} lines  {len(placebo.body.split()):3d} words")
    print(f"  Full:    {len(full_lines):3d} lines  {len(full.body.split()):3d} words")

    placebo_headings = heading_counts(placebo.body)
    full_headings = heading_counts(full.body)
    print(f"  Placebo headings ({len(placebo_headings)}): {placebo_headings}")
    print(f"  Full headings ({len(full_headings)}):    {full_headings}")
    print(f"  Heading count match: {len(placebo_headings) == len(full_headings)}")

    word_ratio = abs(len(placebo.body.split()) - len(full.body.split())) / len(full.body.split())
    print(f"  Word diff: {word_ratio:.1%}  (tolerance 10%)")

    print()
    print("=== Banned-term check ===")
    placebo_all = placebo_desc + " " + placebo.body
    hits = BANNED_RE.findall(placebo_all)
    if hits:
        print(f"  REFUSED: placebo contains banned terms: {hits}")
        return 1
    print("  PASS: no banned terms in placebo description or body")

    print()
    print("=== Fixture file-type check ===")
    existing = fixture_file_types(HERE)
    collision = PLACEBO_FILE_TYPES & existing
    if collision:
        print(f"  REFUSED: placebo names file types present in fixture: {collision}")
        return 1
    print(f"  PASS: placebo file types {PLACEBO_FILE_TYPES} not in fixture tree ({existing})")

    print()
    print("=== Tolerance check ===")
    errors: list[str] = []
    if desc_char_ratio > 0.10:
        errors.append(f"description char diff {desc_char_ratio:.1%} exceeds 10%")
    if word_ratio > 0.10:
        errors.append(f"body word diff {word_ratio:.1%} exceeds 10%")
    if errors:
        for e in errors:
            print(f"  REFUSED: {e}")
        return 1
    print("  PASS: all within tolerance")

    return 0


if __name__ == "__main__":
    sys.exit(check())
