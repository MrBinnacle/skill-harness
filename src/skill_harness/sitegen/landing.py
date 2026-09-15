"""The landing page: a strict reader over ``docs/site/landing.md``, and its render.

The copy is the owner's and he edits it, so it lives in a Markdown file under
``docs/`` rather than in a template string inside a package. Three things follow
from that location and none of them cost an edit anywhere else: the required
``vale`` CI job already lints ``docs/`` at error level, the link checker already
reads ``docs/**/*.md``, and the file sits beside the rest of the prose a reader
can send a correction about.

**This is not a Markdown parser.** It reads a deliberately tiny fixed subset
keyed to the five sections the design brief fixes, and it raises
``SiteBuildError`` on any construct it does not recognise rather than silently
dropping copy. A Markdown library would break the cold-install contract, and a
general hand-rolled parser would be a new bug surface. The repository already
parses YAML frontmatter and workflow YAML by regex for the same reason.

The four section headings are pinned here verbatim. A sixth section, a renamed
section or a reordering fails the build, which is how the brief's fixed
structure is held by a machine instead of by memory.

Internal link targets are symbolic names, not paths. The receipts index lives at
``index.html`` or at ``receipts.html`` depending on whether the landing page is
built, so the href is the generator's to resolve and cannot be written in the
copy file. An ``https://`` target passes through unchanged and is link-checked
like any other prose link.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from skill_harness.sitegen.render import (
    INDEX_FILE_NAME,
    SCHEMA_PAGE_NAME,
    SiteBuildError,
    SiteShell,
    _indent,
    _template,
    safe,
)

#: The four ``##`` headings, in the one order the brief fixes.
SECTION_TITLES: Final[tuple[str, ...]] = (
    "What it refuses to claim",
    "What it measures, in the instrument's own terms",
    "Install",
    "Where the verdicts land",
)

#: Symbolic link targets the generator resolves. Anything else must be an
#: absolute ``https://`` URL, so a target can never be a path that is right in
#: one flag state and broken in the other.
_SYMBOLIC_TARGETS: Final[tuple[str, ...]] = ("receipts", "reporting-standard")

_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
_FIELD_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<key>[a-z]+):\s+(?P<value>.+?)\s*$")
_TERM_RE: Final[re.Pattern[str]] = re.compile(r"^-\s+\*\*(?P<term>[^*]+)\*\*:\s+(?P<body>.+?)\s*$")
_LINK_RE: Final[re.Pattern[str]] = re.compile(r"^-\s+(?P<label>.+?)\s+->\s+(?P<target>\S+)\s*$")


@dataclass(frozen=True)
class LandingCopy:
    """Every string the landing page draws, already validated."""

    heading: str
    lead: str
    claim: str
    action_label: str
    action_target: str
    refusals: tuple[tuple[str, str], ...]
    measures: tuple[str, ...]
    commands: tuple[str, ...]
    install_notes: tuple[str, ...]
    links: tuple[tuple[str, str], ...]


def _refuse(line_number: int, line: str, reason: str) -> SiteBuildError:
    return SiteBuildError(
        f"docs/site/landing.md line {line_number}: {reason}; refusing to publish a "
        f"landing page that drops copy. The line was: {line!r}"
    )


def _blocks(text: str) -> list[tuple[int, str]]:
    """Every non-blank line with its 1-based line number."""
    return [
        (number, line.rstrip())
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _split_sections(lines: Sequence[tuple[int, str]]) -> tuple[str, list[list[tuple[int, str]]]]:
    """The h1 text, then one list of lines per section: hero, then the four fixed ones."""
    if not lines:
        raise SiteBuildError("docs/site/landing.md is empty")
    first_number, first_line = lines[0]
    match = _HEADING_RE.match(first_line)
    if match is None or match.group("hashes") != "#":
        raise _refuse(first_number, first_line, "the file must open with a single '# ' heading")
    heading = match.group("text")

    sections: list[list[tuple[int, str]]] = [[]]
    seen_titles: list[str] = []
    for number, line in lines[1:]:
        found = _HEADING_RE.match(line)
        if found is None:
            sections[-1].append((number, line))
            continue
        if found.group("hashes") != "##":
            raise _refuse(number, line, "only '# ' and '## ' headings are read")
        seen_titles.append(found.group("text"))
        sections.append([])
    if tuple(seen_titles) != SECTION_TITLES:
        raise SiteBuildError(
            "docs/site/landing.md must carry exactly these '## ' headings, in this order: "
            f"{list(SECTION_TITLES)}. It carries: {seen_titles}. The section set and its "
            "order are fixed by the design brief; changing either is a Direction decision."
        )
    return heading, sections


def _read_hero(lines: Sequence[tuple[int, str]]) -> tuple[str, str, str, str]:
    """The hero's four fields: lead, claim, action label, action target."""
    fields: dict[str, str] = {}
    for number, line in lines:
        match = _FIELD_RE.match(line)
        if match is None:
            raise _refuse(number, line, "the hero reads only 'key: value' lines")
        key = match.group("key")
        if key not in {"lead", "claim", "action"}:
            raise _refuse(number, line, f"unknown hero field {key!r}")
        if key in fields:
            raise _refuse(number, line, f"hero field {key!r} is stated twice")
        fields[key] = match.group("value")
    missing = [key for key in ("lead", "claim", "action") if key not in fields]
    if missing:
        raise SiteBuildError(f"docs/site/landing.md hero is missing: {missing}")
    if len(fields["lead"].split()) > 20:
        raise SiteBuildError(
            "docs/site/landing.md hero lead is longer than 20 words. The hero holds one "
            "sentence, and a longer one means the statement is not settled."
        )
    label, _, target = fields["action"].partition(" -> ")
    if not target:
        raise SiteBuildError("docs/site/landing.md hero action must read 'label -> target'")
    return fields["lead"], fields["claim"], label.strip(), _checked_target(target.strip())


def _checked_target(target: str) -> str:
    if target in _SYMBOLIC_TARGETS or target.startswith("https://"):
        return target
    raise SiteBuildError(
        f"docs/site/landing.md link target {target!r} is neither an https:// URL nor one of "
        f"{list(_SYMBOLIC_TARGETS)}. A relative path is right in one flag state and broken "
        "in the other, so the generator resolves internal targets by name."
    )


def _read_refusals(lines: Sequence[tuple[int, str]]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for number, line in lines:
        match = _TERM_RE.match(line)
        if match is None:
            raise _refuse(number, line, "this section reads only '- **term**: sentence' lines")
        rows.append((match.group("term"), match.group("body")))
    if not rows:
        raise SiteBuildError("docs/site/landing.md states no refusals")
    return tuple(rows)


def _read_paragraphs(lines: Sequence[tuple[int, str]], section: str) -> tuple[str, ...]:
    for number, line in lines:
        if line.startswith(("-", "#", "|", ">", "    ", "\t")) or _FIELD_RE.match(line):
            raise _refuse(number, line, f"the {section!r} section reads only paragraph lines")
    paragraphs = tuple(line for _, line in lines)
    if not paragraphs:
        raise SiteBuildError(f"docs/site/landing.md section {section!r} is empty")
    return paragraphs


def _read_install(lines: Sequence[tuple[int, str]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    commands: list[str] = []
    notes: list[tuple[int, str]] = []
    for number, line in lines:
        match = _FIELD_RE.match(line)
        if match is not None:
            if match.group("key") != "command":
                raise _refuse(number, line, "the install section's only field is 'command'")
            commands.append(match.group("value"))
            continue
        notes.append((number, line))
    if not commands:
        raise SiteBuildError("docs/site/landing.md install section states no command")
    return tuple(commands), _read_paragraphs(notes, "Install")


def _read_links(lines: Sequence[tuple[int, str]]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for number, line in lines:
        match = _LINK_RE.match(line)
        if match is None:
            raise _refuse(number, line, "this section reads only '- label -> target' lines")
        rows.append((match.group("label"), _checked_target(match.group("target"))))
    if not rows:
        raise SiteBuildError("docs/site/landing.md states nowhere to go")
    return tuple(rows)


def parse_landing(text: str) -> LandingCopy:
    """Read the landing copy, refusing anything the five-section shape does not allow."""
    heading, sections = _split_sections(_blocks(text))
    hero, refusals, measures, install, links = sections
    lead, claim, action_label, action_target = _read_hero(hero)
    commands, install_notes = _read_install(install)
    return LandingCopy(
        heading=heading,
        lead=lead,
        claim=claim,
        action_label=action_label,
        action_target=action_target,
        refusals=_read_refusals(refusals),
        measures=_read_paragraphs(measures, SECTION_TITLES[1]),
        commands=commands,
        install_notes=install_notes,
        links=_read_links(links),
    )


def _href(shell: SiteShell, target: str) -> str:
    if target == "receipts":
        return shell.receipts_href
    if target == "reporting-standard":
        return SCHEMA_PAGE_NAME
    return target


def render_landing_page(*, shell: SiteShell, copy: LandingCopy) -> str:
    """The landing page, from copy the reader has already validated."""
    from skill_harness.sitegen.render import render_page

    body = _template("landing.html").substitute(
        lead=safe(copy.lead),
        claim=safe(copy.claim),
        action_href=safe(_href(shell, copy.action_target)),
        action_label=safe(copy.action_label),
        refusal_rows=_indent(
            [
                f"<dt>{safe(term)}</dt><dd>{safe(body_text)}</dd>"
                for term, body_text in copy.refusals
            ],
            10,
        ),
        measures_paragraphs=_indent(
            [f"<p>{safe(paragraph)}</p>" for paragraph in copy.measures], 8
        ),
        install_commands=_indent(
            [f"<code>{safe(command)}</code>" for command in copy.commands], 10
        ),
        install_paragraphs=_indent([f"<p>{safe(note)}</p>" for note in copy.install_notes], 8),
        verdict_links=_indent(
            [
                f'<li><a href="{safe(_href(shell, target))}">{safe(label)}</a></li>'
                for label, target in copy.links
            ],
            10,
        ),
    )
    return render_page(
        shell=shell,
        page_name=INDEX_FILE_NAME,
        title="Skill Harness",
        heading=copy.heading,
        description=copy.lead,
        body=body,
        body_class="landing",
        footer=False,
    )
