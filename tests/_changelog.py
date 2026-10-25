"""One reader for a released CHANGELOG section (#832).

Two test modules (``test_glossary_rename_722`` and
``test_changelog_unreleased_733``) pin what the 0.4.0 release recorded. Each
carried its own copy of a section regex with the version written into it, so
a fix to one copy could miss the other. This module holds the regex once, and
the caller names the release.

Anchor
------
The caller passes the release whose content its criteria describe, not the
version ``pyproject.toml`` declares and not "the newest dated section". #722
and #733 pin entries that shipped in 0.4.0. Under Keep a Changelog that
section stays in the file after later releases, so a reader keyed on 0.4.0
keeps reading the same entries at 0.5.0. A reader keyed on the declared
version or on the newest section would move to 0.5.0 at the next version PR,
and both tests would fail on entries that were never meant to be there.
"""

from __future__ import annotations

import re
from pathlib import Path

_CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def release_section(version: str) -> str:
    """Return the body of ``## [<version>]``, up to the next ``## [`` heading.

    :raises AssertionError: the CHANGELOG carries no section for ``version``.
    """
    text = _CHANGELOG.read_text(encoding="utf-8")
    pattern = r"## \[" + re.escape(version) + r"\][^\n]*(.*?)(?=\n## \[)"
    match = re.search(pattern, text, re.DOTALL)
    assert match is not None, f"CHANGELOG.md carries no ## [{version}] section"
    return match.group(1)
