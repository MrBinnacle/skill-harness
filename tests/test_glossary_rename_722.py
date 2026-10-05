"""#722: the domain glossary is named GLOSSARY.md.

Criterion 1 pins the rename through depth-1-safe content assertions: the new
glossary exists, the old path is gone, the title line names the glossary, and
the body after the title matches the pre-rename base fixture. Criterion 2 pins
``docs/agents/domain.md`` to the v1.3.1 ``setup-matt-pocock-skills`` template.
Criteria 3-5 pin the live instruction surfaces and the CHANGELOG announcement.

The old filename is never written as a contiguous literal in this module: the
criterion-4 scan greps every tracked live file for that token, and a test that
names it to prove its absence would make its own assertion vacuous.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_OLD_NAME = "CONTEXT" + ".md"
_NEW_NAME = "GLOSSARY" + ".md"

# Pinned from the pre-rename glossary file: body after the title line.
# Only the title line may change; everything the glossary defines stays.
# Stored as a JSON fixture because every CI checkout uses fetch-depth: 1, so
# ``git log --follow`` cannot reconstruct the base file there. JSON keeps the
# body off the raw-line grid so cumulative-diff rename detection still pairs
# the old glossary path with the new one.
_EXPECTED_BODY_SHA256 = "d8179d5194856d82f9a7ebef77eebbc78730d0b52bc0a24f6ddd6a40ebdd532e"
_EXPECTED_BODY_LINE_COUNT = 67
_EXPECTED_TOTAL_LINE_COUNT = 68
_EXPECTED_TITLE = f"# {_NEW_NAME} — skill-harness\n"
_BASE_BODY_REL = "tests/fixtures/domain-docs/context-md-body-base.json"

# Criterion 2: docs/agents/domain.md is the v1.3.1 setup template, byte for
# byte. Source: github.com/mattpocock/skills at tag v1.3.1,
# skills/engineering/setup-matt-pocock-skills/domain.md, vendored under
# tests/fixtures/domain-docs/. This repo carries no local additions in that
# file (#677 aligned it verbatim to an earlier template; the v1.3.1 rename is
# the only delta that matters here).
_DOMAIN_TEMPLATE_V1_3_1_SHA256 = "593a7042218689f1d24df89df14eaf0a20e19e0d0a7d479a01947ac78f0784b9"
_DOMAIN_TEMPLATE_REL = "tests/fixtures/domain-docs/setup-matt-pocock-skills-domain-v1.3.1.md"

# Dated-record surfaces: historical wording stays as written.
_DATED_RECORD_FILES = frozenset(
    {
        "CHANGELOG.md",
    }
)


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def test_glossary_exists_and_context_is_gone() -> None:
    """Criterion 1: the root file is the new glossary; the old name is gone."""
    glossary = _REPO_ROOT / _NEW_NAME
    context = _REPO_ROOT / _OLD_NAME
    assert glossary.is_file(), f"{_NEW_NAME} must exist at the repo root"
    assert not context.exists(), f"{_OLD_NAME} must not remain at the repo root"


def test_glossary_title_names_the_glossary() -> None:
    """Criterion 1: the title line names the glossary, not the old path."""
    text = _read(_NEW_NAME)
    first_line = text.splitlines(keepends=True)[0]
    assert first_line == _EXPECTED_TITLE, (
        f"{_NEW_NAME} title line is {first_line!r}, expected {_EXPECTED_TITLE!r}"
    )
    assert "GLOSSARY" in first_line
    assert _OLD_NAME not in first_line


def test_glossary_body_is_unchanged() -> None:
    """Criterion 1: content other than the title line is byte-identical."""
    text = _read(_NEW_NAME)
    lines = text.splitlines(keepends=True)
    assert lines[0] == _EXPECTED_TITLE
    assert len(lines) == _EXPECTED_TOTAL_LINE_COUNT, (
        f"{_NEW_NAME} has {len(lines)} lines; expected {_EXPECTED_TOTAL_LINE_COUNT}"
    )
    body = "".join(lines[1:])
    body_lines = body.splitlines()
    assert len(body_lines) == _EXPECTED_BODY_LINE_COUNT, (
        f"{_NEW_NAME} body has {len(body_lines)} lines; expected {_EXPECTED_BODY_LINE_COUNT}"
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _EXPECTED_BODY_SHA256, (
        f"{_NEW_NAME} body digest moved; only the title line may change in #722"
    )


def test_glossary_body_keeps_the_glossary_entries() -> None:
    """Criterion 1: the vocabulary of record still defines its terms."""
    text = _read(_NEW_NAME)
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
        assert term in text, f"{_NEW_NAME} is missing the entry {term!r}"
    assert _OLD_NAME not in text, f"{_NEW_NAME} must not still name the old {_OLD_NAME} path"


def test_rename_body_matches_base_fixture() -> None:
    """Criterion 1: the move is pinable without git history.

    Every CI checkout uses ``fetch-depth: 1``, so ``git log --follow`` sees no
    rename there. Assert only what a depth-1 checkout can make: the new
    glossary exists, the old path does not, and the body after the title line
    equals the pre-rename base body stored under ``tests/fixtures/domain-docs/``.
    """
    glossary = _REPO_ROOT / _NEW_NAME
    context = _REPO_ROOT / _OLD_NAME
    assert glossary.is_file(), f"{_NEW_NAME} must exist at the repo root"
    assert not context.exists(), f"{_OLD_NAME} must not remain at the repo root"
    body = "".join(glossary.read_text(encoding="utf-8").splitlines(keepends=True)[1:])
    payload = json.loads(_read(_BASE_BODY_REL))
    base = payload["body"]
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    assert digest == payload["sha256"] == _EXPECTED_BODY_SHA256, (
        f"{_BASE_BODY_REL} body digest moved; only the title line may change in #722"
    )
    assert body == base, (
        f"{_NEW_NAME} body after its title line differs from the base {_OLD_NAME} body "
        f"in {_BASE_BODY_REL}; only the title line may change in #722"
    )


def test_domain_doc_is_the_v1_3_1_setup_template() -> None:
    """Criterion 2: docs/agents/domain.md is the v1.3.1 setup template.

    Byte-identical to the vendored copy of
    ``skills/engineering/setup-matt-pocock-skills/domain.md`` at
    ``github.com/mattpocock/skills`` tag ``v1.3.1``. This repo carries no
    local additions in that file, so the template is the whole content.
    """
    text = _read("docs/agents/domain.md")
    expected = _read(_DOMAIN_TEMPLATE_REL)
    assert text == expected, (
        "docs/agents/domain.md is not the v1.3.1 setup-matt-pocock-skills template"
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == _DOMAIN_TEMPLATE_V1_3_1_SHA256, (
        f"docs/agents/domain.md digest {digest} != pinned v1.3.1 template digest"
    )


def test_agents_md_names_the_glossary_not_context() -> None:
    """Criterion 3: live pointers in AGENTS.md name the new glossary."""
    text = _read("AGENTS.md")
    assert _NEW_NAME in text, "AGENTS.md must name the new glossary file"
    assert _OLD_NAME not in text, f"AGENTS.md still names {_OLD_NAME} on a live instruction surface"


def test_no_live_file_still_names_context_md() -> None:
    """Criterion 4: live tracked files carry no hit on the old glossary name."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    offenders: list[str] = []
    for rel in listed:
        if rel in _DATED_RECORD_FILES:
            continue
        path = _REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _OLD_NAME in text:
            offenders.append(rel)
    assert not offenders, "live files still name the old glossary file:\n" + "\n".join(
        f"  - {o}" for o in offenders
    )


def test_changelog_announces_the_rename() -> None:
    """Criterion 5: the release convention records the rename under Unreleased."""
    text = _read("CHANGELOG.md")
    match = re.search(r"## \[Unreleased\](.*?)(?=\n## \[)", text, re.DOTALL)
    assert match is not None, "CHANGELOG.md must carry an [Unreleased] section"
    unreleased = match.group(1)
    assert _NEW_NAME in unreleased, "[Unreleased] must announce the new glossary name"
    assert _OLD_NAME in unreleased, "[Unreleased] must state what it was called before"
    assert re.search(r"(?i)renam", unreleased), (
        "[Unreleased] must use rename language, not a silent path swap"
    )
