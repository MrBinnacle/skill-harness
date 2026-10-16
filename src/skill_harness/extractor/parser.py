"""SKILL.md source file parser.

Responsibilities:
1. Detect and parse YAML-ish frontmatter (``---`` delimited, stdlib re only,
   no pyyaml dependency).
2. Return the raw body text after the frontmatter block.
3. Compute the SHA-256 of the raw file bytes.
4. Extract the ``name`` field from frontmatter (fallback: filename stem).

Frontmatter parsing is intentionally minimal — only ``key: value`` pairs on
a single line are extracted. Multi-line values, lists, and nested structures
are treated as unparseable and silently skipped. The body is passed verbatim
to the Claude extraction step; frontmatter is metadata only.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from skill_harness.extractor.errors import MalformedSkillError

# Matches the opening ``---`` delimiter at the very start of the file.
_FM_OPEN = re.compile(r"^---[ \t]*\r?\n", re.MULTILINE)
# Matches the closing ``---`` or ``...`` delimiter.
_FM_CLOSE = re.compile(r"^(?:---|\.\.\.)\s*$", re.MULTILINE)
# Matches a simple ``key: value`` line inside the frontmatter block.
_FM_KEY_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*?)[ \t]*$")


class ParsedSkill:
    """Result of parsing a SKILL.md source file."""

    __slots__ = ("body", "frontmatter", "name", "source_path", "source_sha256")

    def __init__(
        self,
        source_path: str,
        source_sha256: str,
        frontmatter: dict[str, str],
        body: str,
        name: str,
    ) -> None:
        self.source_path = source_path
        self.source_sha256 = source_sha256
        self.frontmatter = frontmatter
        self.body = body
        self.name = name


def parse_skill_file(path: Path) -> ParsedSkill:
    """Read ``path``, extract frontmatter and body, return a ``ParsedSkill``.

    :param path: Absolute or relative path to the skill markdown file.
    :raises MalformedSkillError: If the file is empty or contains only
        whitespace after stripping frontmatter.
    :raises OSError: If the file cannot be read (propagated as-is).
    """
    raw_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # Strict UTF-8: silent replacement would corrupt the body while audit
    # SHA-256 over raw bytes still says "clean" — violates write-time provenance.
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MalformedSkillError(f"Skill file '{path}' is not valid UTF-8: {exc}") from exc

    frontmatter: dict[str, str] = {}
    body = text

    # Check for frontmatter block.
    fm_open_match = _FM_OPEN.match(text)
    if fm_open_match:
        fm_start = fm_open_match.end()
        fm_close_match = _FM_CLOSE.search(text, fm_start)
        if fm_close_match:
            fm_block = text[fm_start : fm_close_match.start()]
            for line in fm_block.splitlines():
                kv = _FM_KEY_VALUE.match(line)
                if kv:
                    key, value = kv.group(1), kv.group(2)
                    frontmatter[key] = value
            body = text[fm_close_match.end() :]
        # If no closing delimiter found, treat whole file as body (no frontmatter).

    # Validate non-empty body.
    if not body.strip():
        raise MalformedSkillError(
            f"Skill file '{path}' has an empty body after stripping frontmatter."
        )

    # Derive name: frontmatter ``name`` field, else filename stem.
    name = frontmatter.get("name") or path.stem

    return ParsedSkill(
        source_path=str(path.resolve()),
        source_sha256=source_sha256,
        frontmatter=frontmatter,
        body=body,
        name=name,
    )
