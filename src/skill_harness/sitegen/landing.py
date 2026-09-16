"""The landing page: a strict reader over ``docs/site/landing.md``, and its render.

The copy is the owner's and he edits it, so it lives in a Markdown file under
``docs/`` rather than in a template string inside a package. Three things follow
from that location and none of them cost an edit anywhere else: the required
``vale`` CI job already lints ``docs/`` at error level, the link checker already
reads ``docs/**/*.md``, and the file sits beside the rest of the prose a reader
can send a correction about.

**This is not a Markdown parser.** It reads a deliberately tiny fixed subset
keyed to the shape the design brief fixes, and it raises ``SiteBuildError`` on
any construct it does not recognise rather than silently dropping copy. A
Markdown library would break the cold-install contract, and a general
hand-rolled parser would be a new bug surface. The repository already parses
YAML frontmatter and workflow YAML by regex for the same reason.

The shape changed for issue #588. The page was a four-section document that
introduced the instrument by listing what it refuses to claim, what it measures,
how to install it, and where the verdicts land. It is now a heading, two hero
sentences and exactly three pointers.

THE PAGE PUBLISHES NO SCORE, and that is a ruling rather than an oversight.

An intermediate version of this change carried four hero sentences. Two of them
were ``detects``, which printed "8 of 8 with the skill, and 0 of 8 without", and
``control``, which said that control was synthetic so the run validated the
instrument and not any real skill. They were two fields rather than one so that
the build could not render the number without the caveat beside it.

The independent review seat argued that this does not work on a reader. The
figure was the only integer on the page. It answered the heading's question with
a yes. The repository's own next sentence says no production skill has ever
returned a KEEP. A caveat in the following paragraph is a subsequent sentence,
not a cancellation, and coupling the two at build time is not coupling them in
the reader. The owner accepted that argument on 2026-09-15 and cut the figure.

So the guarantee moved from editorial to structural. There is no hero field that
can carry a score, which is stronger than any rule about what must sit beside
one. ``tests/sitegen/test_site_design_S455.py`` holds it at the rendered page.

Cutting the figure is also what satisfies acceptance criterion 2. That criterion
asks for the heading, the two sentences and the pointers on the first 360px
screen. Four hero paragraphs and three pointers with supporting lines did not fit
in 640px, and removing two of them is what puts all three pointers above the
fold. The criterion is met rather than waived.

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

#: The one ``##`` heading the page carries. Issue #588 replaced a four-section
#: document with a heading, two hero sentences and three pointers.
SECTION_TITLES: Final[tuple[str, ...]] = ("Where to go next",)

#: The hero's fields, in the order the page prints them.
#:
#: THE CAPABILITY FIGURE IS GONE, and its absence is the rule (issue #588, owner's
#: ruling of 2026-09-15). The hero used to carry ``detects`` and ``control``: a sentence
#: printing "8 of 8 with the skill, and 0 of 8 without", and a sentence beneath it saying
#: the control was synthetic.
#:
#: The independent review seat argued that the caveat does not neutralise the number for
#: a skimmer. The figure was the only integer on the page, it answered the heading's
#: question with a yes, and the repository's own next sentence says no production skill
#: has ever returned a KEEP. Build-time coupling of figure and caveat is not reader-time
#: coupling. The owner accepted that and cut the figure rather than re-wording the caveat.
#:
#: What remains is what acceptance criterion 2 asked for in the first place: a heading,
#: two sentences and the pointers. Cutting the figure is also what lets the first 360px
#: screen carry all three pointers, so the criterion is met rather than waived.
HERO_FIELDS: Final[tuple[str, ...]] = ("lead", "evidence_is_thin")

#: The page carries exactly three pointers. "Three pointers and nothing else"
#: is the ticket's wording, so the count is held by the build rather than by a
#: reviewer counting bullets.
POINTER_COUNT: Final[int] = 3

#: Symbolic link targets the generator resolves. Anything else must be an
#: absolute ``https://`` URL, so a target can never be a path that is right in
#: one flag state and broken in the other.
_SYMBOLIC_TARGETS: Final[tuple[str, ...]] = ("receipts", "reporting-standard")

_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*$")
_FIELD_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<key>[a-z_]+):\s+(?P<value>.+?)\s*$")
_LINK_RE: Final[re.Pattern[str]] = re.compile(r"^-\s+(?P<label>.+?)\s+->\s+(?P<target>\S+)\s*$")


@dataclass(frozen=True)
class Pointer:
    """One of the three pointers: where it goes, and why a reader would follow.

    A frozen dataclass rather than a 3-tuple. The three strings travel together
    through the reader, the copy object and the template loop, which is the
    shape that wants a type, and ``pointer[2]`` says nothing about what it
    holds where ``pointer.support`` does.
    """

    label: str
    target: str
    support: str


@dataclass(frozen=True)
class LandingCopy:
    """Every string the landing page draws, already validated."""

    heading: str
    lead: str
    evidence_is_thin: str
    pointers: tuple[Pointer, ...]


def _refuse(line_number: int, line: str, reason: str) -> SiteBuildError:
    return SiteBuildError(
        f"docs/site/landing.md line {line_number}: {reason}; refusing to publish a "
        f"landing page that drops copy. The line was: {line!r}"
    )


def _blocks(text: str) -> list[tuple[int, str]]:
    """Every non-blank line with its 1-based line number, leading space kept."""
    return [
        (number, line.rstrip())
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _split_sections(lines: Sequence[tuple[int, str]]) -> tuple[str, list[list[tuple[int, str]]]]:
    """The h1 text, then one list of lines per section: hero, then the fixed ones."""
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
        found = _HEADING_RE.match(line.strip())
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


def _read_hero(lines: Sequence[tuple[int, str]]) -> dict[str, str]:
    """The hero sentences, keyed by field name."""
    fields: dict[str, str] = {}
    for number, line in lines:
        match = _FIELD_RE.match(line.strip())
        if match is None:
            raise _refuse(number, line, "the hero reads only 'key: value' lines")
        key = match.group("key")
        if key not in HERO_FIELDS:
            raise _refuse(number, line, f"unknown hero field {key!r}")
        if key in fields:
            raise _refuse(number, line, f"hero field {key!r} is stated twice")
        fields[key] = match.group("value")
    missing = [key for key in HERO_FIELDS if key not in fields]
    if missing:
        raise SiteBuildError(f"docs/site/landing.md hero is missing: {missing}")
    if len(fields["lead"].split()) > 20:
        raise SiteBuildError(
            "docs/site/landing.md hero lead is longer than 20 words. The hero holds one "
            "sentence, and a longer one means the statement is not settled."
        )
    return fields


def _checked_target(target: str) -> str:
    if target in _SYMBOLIC_TARGETS or target.startswith("https://"):
        return target
    raise SiteBuildError(
        f"docs/site/landing.md link target {target!r} is neither an https:// URL nor one of "
        f"{list(_SYMBOLIC_TARGETS)}. A relative path is right in one flag state and broken "
        "in the other, so the generator resolves internal targets by name."
    )


def _read_pointers(lines: Sequence[tuple[int, str]]) -> tuple[Pointer, ...]:
    """Each pointer is a link line followed by one supporting line.

    The supporting line is required. The ticket's wording is that each pointer
    says what is behind it and why a reader would want it, so a pointer without
    one fails the build rather than rendering a bare link.
    """
    rows: list[Pointer] = []
    index = 0
    while index < len(lines):
        number, line = lines[index]
        match = _LINK_RE.match(line.strip())
        if match is None:
            raise _refuse(number, line, "this section reads only '- label -> target' lines")
        if index + 1 >= len(lines):
            raise _refuse(number, line, "this pointer has no supporting line beneath it")
        support_number, support_line = lines[index + 1]
        if _LINK_RE.match(support_line.strip()) is not None:
            raise _refuse(
                support_number,
                support_line,
                "this pointer has no supporting line beneath it",
            )
        rows.append(
            Pointer(
                label=match.group("label"),
                target=_checked_target(match.group("target")),
                support=support_line.strip(),
            )
        )
        index += 2
    if len(rows) != POINTER_COUNT:
        raise SiteBuildError(
            f"docs/site/landing.md states {len(rows)} pointer(s) and the page carries exactly "
            f"{POINTER_COUNT}. Issue #588 fixes the count: three pointers and nothing else."
        )
    return tuple(rows)


def parse_landing(text: str) -> LandingCopy:
    """Read the landing copy, refusing anything the fixed shape does not allow."""
    heading, sections = _split_sections(_blocks(text))
    hero, pointers = sections
    fields = _read_hero(hero)
    return LandingCopy(
        heading=heading,
        lead=fields["lead"],
        evidence_is_thin=fields["evidence_is_thin"],
        pointers=_read_pointers(pointers),
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
        evidence_is_thin=safe(copy.evidence_is_thin),
        pointers=_indent(
            [
                f'<li><a class="pointer" href="{safe(_href(shell, pointer.target))}">'
                f"{safe(pointer.label)}</a><span>{safe(pointer.support)}</span></li>"
                for pointer in copy.pointers
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
