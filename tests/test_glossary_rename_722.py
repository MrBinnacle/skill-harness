"""#722 criterion 1: the domain glossary is named GLOSSARY.md.

A reader following any live pointer to the glossary lands on ``GLOSSARY.md``.
This module pins the rename, the title line, and the requirement that content
otherwise stays unchanged.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Pinned from the pre-rename CONTEXT.md: body after the title line.
# Only the title line may change; everything the glossary defines stays.
_EXPECTED_BODY_SHA256 = "d8179d5194856d82f9a7ebef77eebbc78730d0b52bc0a24f6ddd6a40ebdd532e"
_EXPECTED_BODY_LINE_COUNT = 67
_EXPECTED_TOTAL_LINE_COUNT = 68
_EXPECTED_TITLE = "# GLOSSARY.md — skill-harness\n"


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def test_glossary_exists_and_context_is_gone() -> None:
    """Criterion 1: the root file is GLOSSARY.md; CONTEXT.md is not there."""
    glossary = _REPO_ROOT / "GLOSSARY.md"
    context = _REPO_ROOT / "CONTEXT.md"
    assert glossary.is_file(), "GLOSSARY.md must exist at the repo root"
    assert not context.exists(), "CONTEXT.md must not remain at the repo root"


def test_glossary_title_names_the_glossary() -> None:
    """Criterion 1: the title line names the glossary, not the old path."""
    text = _read("GLOSSARY.md")
    first_line = text.splitlines(keepends=True)[0]
    assert first_line == _EXPECTED_TITLE, (
        f"GLOSSARY.md title line is {first_line!r}, expected {_EXPECTED_TITLE!r}"
    )
    assert "GLOSSARY" in first_line
    assert "CONTEXT.md" not in first_line


def test_glossary_body_is_unchanged() -> None:
    """Criterion 1: content other than the title line is byte-identical."""
    text = _read("GLOSSARY.md")
    lines = text.splitlines(keepends=True)
    assert lines[0] == _EXPECTED_TITLE
    assert len(lines) == _EXPECTED_TOTAL_LINE_COUNT, (
        f"GLOSSARY.md has {len(lines)} lines; expected {_EXPECTED_TOTAL_LINE_COUNT}"
    )
    body = "".join(lines[1:])
    body_lines = body.splitlines()
    assert len(body_lines) == _EXPECTED_BODY_LINE_COUNT, (
        f"GLOSSARY.md body has {len(body_lines)} lines; expected {_EXPECTED_BODY_LINE_COUNT}"
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _EXPECTED_BODY_SHA256, (
        "GLOSSARY.md body digest moved; only the title line may change in #722"
    )


def test_glossary_body_keeps_the_glossary_entries() -> None:
    """Criterion 1: the vocabulary of record still defines its terms."""
    text = _read("GLOSSARY.md")
    for term in (
        "**Skill**:",
        "**Clause**:",
        "**Condition**:",
        "**Measurement**:",
        "**Price / benefit**:",
        "**Oracle**:",
        "**Evidence admissibility**:",
        "**Population integrity**:",
        "**Verdict**:",
        "**Typed refusal**:",
        "**Receipt**:",
        "**SERS**:",
        "**Unmeasured**:",
        "**Vacuity flag**:",
        "**Declared synthetic control**:",
        "**Matched-evidence bridge**:",
        "**Evidence grade**:",
        "**Admission state vs measurement state**:",
        "## Relationships",
    ):
        assert term in text, f"GLOSSARY.md is missing the entry {term!r}"
    assert "CONTEXT.md" not in text, "GLOSSARY.md must not still name the old CONTEXT.md path"


def test_git_history_records_a_rename() -> None:
    """Criterion 1: the move is a rename in git, not a delete-plus-add.

    Checks the staged summary first (``git mv`` records a rename as soon as it
    runs) and then the committed history, so the pin holds both before and
    after the commit that lands the rename.
    """
    staged = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "diff", "--cached", "--summary"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert staged.returncode == 0, staged.stderr
    staged_is_rename = bool(
        re.search(
            r"rename (CONTEXT|GLOSSARY)\.md\s*(?:=>|->|to)\s*(CONTEXT|GLOSSARY)\.md",
            staged.stdout,
        )
    )
    committed = subprocess.run(
        [
            "git",
            "-C",
            str(_REPO_ROOT),
            "log",
            "--follow",
            "--diff-filter=R",
            "--summary",
            "--",
            "GLOSSARY.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert committed.returncode == 0, committed.stderr
    committed_is_rename = bool(
        re.search(
            r"rename (CONTEXT|GLOSSARY)\.md\s*(?:=>|->|to)\s*(CONTEXT|GLOSSARY)\.md",
            committed.stdout,
        )
    )
    assert staged_is_rename or committed_is_rename, (
        "git neither staged nor committed a CONTEXT.md <-> GLOSSARY.md rename.\n"
        f"staged summary:\n{staged.stdout}\n"
        f"committed summary:\n{committed.stdout}"
    )
