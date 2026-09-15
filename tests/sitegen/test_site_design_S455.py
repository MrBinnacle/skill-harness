"""The S455 direction brief's machine-held rules, one test per rule.

The brief splits its 39 rules into rules a test holds and rules only a reader
holds. This file is the first half. Each test names the rule it pins in its
docstring, so a later pass that wants to change one can find the argument it has
to beat rather than deleting an assertion it cannot place.

The rule this file exists for above all others is the landing page's default.
A landing page amplifies whatever is true, including the parts that are not, so
the project's definition of done orders it after claim integrity. That ordering
is held here by ``test_the_landing_page_is_off_by_default`` and
``test_the_flag_default_is_off_in_the_command_line_parser`` rather than by
anyone remembering it.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from skill_harness.sitegen import DEFAULT_BASE_URL, build_site
from skill_harness.sitegen.__main__ import _parser
from skill_harness.sitegen.landing import POINTER_COUNT, SECTION_TITLES, parse_landing
from skill_harness.sitegen.render import SiteBuildError

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO / "docs" / "sers" / "receipts"
_TEMPLATES = _REPO / "src" / "skill_harness" / "sitegen" / "templates"
_STYLESHEET = _REPO / "src" / "skill_harness" / "sitegen" / "style.css"
_LANDING_COPY = Path(__file__).parent / "fixtures" / "landing.md"
_SOCIAL_IMAGE = _REPO / "assets" / "social-preview.png"

_MARKER = "s455-pin-marker"


def _build(output: Path, *, landing: bool = False, base_url: str | None = None) -> Path:
    """Build the real site from the repository's own receipts and its own assets."""
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=_RECEIPTS,
        extraction_path=None,
        output_dir=output,
        marker=_MARKER,
        base_url=DEFAULT_BASE_URL if base_url is None else base_url,
        landing=landing,
        landing_copy_path=_LANDING_COPY if landing else None,
        social_image_path=_SOCIAL_IMAGE,
    )
    return output


def _prose_words(page: Path) -> set[str]:
    """Every word a reader meets in <main> that is NOT inside a <code> element.

    The exclusion is the point rather than a convenience. A <code> element is
    the machine layer the page deliberately shows: the reporting standard lists
    ``null`` as a member of a closed vocabulary, and that is the schema's own
    value being documented, not a value printed where a sentence belongs. The
    #583 defect was ``Cut sub-reason: null`` in a <dd>, which is prose.
    """
    main = ET.parse(page).getroot().find("body/main")
    assert main is not None, f"{page.name} has no <main>"

    words: set[str] = set()

    def walk(element: ET.Element) -> None:
        for child in element:
            if child.tag != "code":
                if child.text:
                    words.add(child.text.strip())
                walk(child)
            if child.tail:
                words.add(child.tail.strip())

    if main.text:
        words.add(main.text.strip())
    walk(main)
    return words


def _pages(output: Path) -> list[Path]:
    return sorted(output.glob("*.html"))


def _head_of(page: Path) -> ET.Element:
    head = ET.parse(page).getroot().find("head")
    assert head is not None, f"{page.name} has no <head>"
    return head


def _meta(head: ET.Element, *, name: str = "", prop: str = "") -> str | None:
    for element in head.iter("meta"):
        if name and element.get("name") == name:
            return element.get("content")
        if prop and element.get("property") == prop:
            return element.get("content")
    return None


# ---------------------------------------------------------------------------
# The ordering rule: the landing page is built, and it does not publish
# ---------------------------------------------------------------------------


def test_the_landing_page_is_off_by_default(tmp_path: Path) -> None:
    """Brief 1.3: with no flag, index.html is the receipts index, as it is today.

    This is the ordering rule made mechanical. If the default ever flips, this
    test fails before the site publishes a page that claims more than the
    receipts behind it support.

    Issue #588's fourth acceptance criterion asks for this default to be
    reconciled with the new front page, or for the reason it survives to be
    stated. It survives, and this is the reason.

    The ordering rule is that a landing page amplifies whatever is true,
    including the parts that are not, so it comes after claim integrity. Claim
    integrity is not done: issue #587 is open and names four published sentences
    this repository contradicts. Flipping the default now would publish the new
    page over an unfixed claim set, which is the exact sequence the rule exists
    to prevent, and polish would raise the confidence a reader places in claims
    that have not been checked.

    So #588 builds the page and #587 is what unblocks the flip. The page is
    reachable today with --landing, and every test in this file that covers it
    runs with the flag on.
    """
    output = _build(tmp_path / "site")

    assert (output / "index.html").is_file()
    assert not (output / "receipts.html").exists(), (
        "receipts.html exists, which means the landing page took index.html with the flag off"
    )
    root = ET.parse(output / "index.html").getroot()
    heading = root.find("body/main/h1")
    assert heading is not None
    assert (heading.text or "").strip() == "Published receipts"


def test_the_flag_default_is_off_in_the_command_line_parser() -> None:
    """The same rule at the other layer: argparse's own default for --landing.

    Held separately from the build test on purpose. A refactor could keep
    build_site's default and flip the CLI's, and the CLI is what the Pages
    workflow runs, so the CLI's default is the one a stranger actually meets.
    """
    parsed = _parser().parse_args(["--marker", "x"])
    assert parsed.landing is False


def test_the_landing_flag_moves_the_receipts_index_without_losing_it(
    tmp_path: Path,
) -> None:
    """Brief 4.6: flag on, index.html is the landing page and receipts move."""
    output = _build(tmp_path / "site", landing=True)

    assert (output / "receipts.html").is_file()
    receipts_heading = ET.parse(output / "receipts.html").getroot().find("body/main/h1")
    assert receipts_heading is not None
    assert (receipts_heading.text or "").strip() == "Published receipts"

    landing_heading = ET.parse(output / "index.html").getroot().find("body/main/h1")
    assert landing_heading is not None
    assert (landing_heading.text or "").strip() != "Published receipts"

    nav_labels = [
        "".join(item.itertext()).strip()
        for item in ET.parse(output / "index.html").getroot().iter("a")
    ]
    assert "Home" in nav_labels


def test_both_flag_states_write_the_same_receipt_pages(tmp_path: Path) -> None:
    """Brief 5.14: the surfaces may be reorganised; no page leaves the site."""
    off = {path.name for path in _pages(_build(tmp_path / "off"))}
    on = {path.name for path in _pages(_build(tmp_path / "on", landing=True))}

    assert off - on == set(), f"the flag-on build dropped {off - on}"
    assert on - off == {"receipts.html"}


# ---------------------------------------------------------------------------
# The page shell (brief 4.2), on every page of both builds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("landing", [False, True])
def test_every_page_carries_the_head_the_brief_specifies(tmp_path: Path, landing: bool) -> None:
    """Brief 4.2, closing audit findings A3: description, og and twitter tags."""
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        head = _head_of(page)
        description = _meta(head, name="description")
        assert description, f"{page.name} carries no meta description"
        assert _meta(head, prop="og:title"), f"{page.name} carries no og:title"
        assert _meta(head, prop="og:description"), f"{page.name} has no og:description"
        assert _meta(head, prop="og:url"), f"{page.name} carries no og:url"
        assert _meta(head, prop="og:type"), f"{page.name} carries no og:type"
        assert _meta(head, prop="og:image"), f"{page.name} carries no og:image"
        assert _meta(head, name="twitter:card") == "summary_large_image"


@pytest.mark.parametrize("landing", [False, True])
def test_every_page_carries_the_build_marker_meta(tmp_path: Path, landing: bool) -> None:
    """Brief M12: whatever document sits at / carries the marker the deploy greps.

    The visible footer string comes off the landing page. The meta tag does not
    come off anything, and the meta tag is what pages.yml fetches and greps, so
    this is the assertion that keeps the deploy verification honest across the
    flag.
    """
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        assert _meta(_head_of(page), name="skill-harness-build") == _MARKER, page.name


@pytest.mark.parametrize("landing", [False, True])
def test_the_skip_link_is_the_first_focusable_element(tmp_path: Path, landing: bool) -> None:
    """Brief 4.2, closing A6."""
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        body = ET.parse(page).getroot().find("body")
        assert body is not None
        first = body.find("a")
        assert first is not None, f"{page.name} has no link in <body>"
        assert first.get("class") == "skip-link", page.name
        assert first.get("href") == "#main", page.name
        main = ET.parse(page).getroot().find("body/main")
        assert main is not None, f"{page.name} has no <main>"
        assert main.get("id") == "main", page.name


@pytest.mark.parametrize("landing", [False, True])
def test_the_current_page_is_marked_once_and_only_on_a_nav_page(
    tmp_path: Path, landing: bool
) -> None:
    """Brief 4.2, closing A2 and DESIGN.md Known Divergence 7.

    404.html is not a nav destination, so it carries no current-page marker.
    Every page that IS in the nav carries exactly one.
    """
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        marked = [
            element
            for element in ET.parse(page).getroot().iter("a")
            if element.get("aria-current") == "page"
        ]
        assert len(marked) <= 1, f"{page.name} marks {len(marked)} nav items current"
        nav_targets = {
            element.get("href")
            for element in ET.parse(page).getroot().iter("nav")
            for element in element.iter("a")
        }
        if page.name in nav_targets:
            assert len(marked) == 1, f"{page.name} is in the nav but marks nothing"


def test_the_404_page_is_written(tmp_path: Path) -> None:
    """Brief 4.5, closing A7."""
    output = _build(tmp_path / "site")
    assert (output / "404.html").is_file()


# ---------------------------------------------------------------------------
# The absence vocabulary, and the figures (brief 1.1, 3.2 T1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("landing", [False, True])
def test_no_page_prints_a_machine_token_to_a_reader(tmp_path: Path, landing: bool) -> None:
    """Brief 1.1 and 6.3: the literal strings null and false are not readable text.

    #583 fixed this in the renderer. This holds it at the built-page level, which
    is where the defect was found in the first place: on the live site, not in a
    unit test.
    """
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        words = _prose_words(page)
        assert "null" not in words, f"{page.name} prints the literal string null"
        assert "false" not in words, f"{page.name} prints the literal string false"
        assert "true" not in words, f"{page.name} prints the literal string true"
        assert "None" not in words, f"{page.name} prints a Python None"


@pytest.mark.parametrize("landing", [False, True])
def test_the_display_step_is_spent_at_most_once_per_page(tmp_path: Path, landing: bool) -> None:
    """Brief 3.2 T22 and 4.3: the 52px step states the one datum a page exists for.

    A second display-step element on one page is halt item 7, so it is a test
    failure here rather than a judgement call at review time.
    """
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        found = [
            element
            for element in ET.parse(page).getroot().iter()
            if "verdict-display" in (element.get("class") or "").split()
        ]
        assert len(found) <= 1, f"{page.name} spends the display step {len(found)} times"


# ---------------------------------------------------------------------------
# The token fence's boundary (brief 4.2, halt item 4)
# ---------------------------------------------------------------------------


def test_no_template_carries_css() -> None:
    """Brief halt item 4: CSS in a template escapes the conformance scanner.

    The scanner's path list is style.css plus assets/*.svg. Templates are not
    scanned, so a colour in a template reaches the published site with CI green.
    This test is the fence around that hole.
    """
    for template in sorted(_TEMPLATES.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        assert "<style" not in text.lower(), f"{template.name} carries a style block"
        assert "style=" not in text.lower(), f"{template.name} carries a style attribute"


def test_no_template_carries_an_em_dash_or_an_en_dash() -> None:
    """Brief 3.2 T15: the regular hyphen, in visible copy and in attributes alike."""
    for template in sorted(_TEMPLATES.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{template.name} carries an em-dash"
        assert chr(0x2013) not in text, f"{template.name} carries an en-dash"


def _declarations_only(css: str) -> str:
    """The stylesheet with its comments removed.

    The comments explain which properties were rejected and why, so a naive
    substring search over the whole file finds the rejected property in the
    sentence rejecting it.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def test_the_stylesheet_breaks_long_values_rather_than_overflowing() -> None:
    """Brief 4.2, closing A9. overflow-x: hidden would hide the symptom instead."""
    css = _declarations_only(_STYLESHEET.read_text(encoding="utf-8"))
    assert "overflow-wrap: anywhere" in css
    assert "overflow-x: hidden" not in css


def test_the_display_step_steps_down_by_media_query_not_by_clamp() -> None:
    """Brief M3 and 4.3: clamp() and var() both fail the fence in a font-size."""
    css = _declarations_only(_STYLESHEET.read_text(encoding="utf-8"))
    for declaration in re.findall(r"font-size:\s*([^;]+);", css):
        assert "clamp(" not in declaration, declaration
        assert "var(" not in declaration, declaration
    assert "font-size: 52px" in css
    assert "font-size: 21px" in css


# ---------------------------------------------------------------------------
# The audience lock (brief 3.4, halt item 9)
# ---------------------------------------------------------------------------


_AUDIENCE_WORDS = ("engineers", "developers", "operators", "practitioners", "teams")


@pytest.mark.parametrize("landing", [False, True])
def test_no_surface_names_an_audience(tmp_path: Path, landing: bool) -> None:
    """Brief 3.4, the owner's ruling: no page says who it is for.

    Reaches the meta description, the title and every aria-label, because the
    lock names all three. The word list is the brief's own.
    """
    output = _build(tmp_path / "site", landing=landing)

    for page in _pages(output):
        root = ET.parse(page).getroot()
        surfaces = ["".join(root.itertext())]
        for element in root.iter():
            for attribute in ("content", "aria-label", "alt", "title"):
                value = element.get(attribute)
                if value:
                    surfaces.append(value)
        haystack = " ".join(surfaces).lower()
        for word in _AUDIENCE_WORDS:
            assert word not in haystack, f"{page.name} names an audience: {word}"


# ---------------------------------------------------------------------------
# Host independence (brief 8.3)
# ---------------------------------------------------------------------------


def test_every_absolute_url_is_composed_from_the_base_url(tmp_path: Path) -> None:
    """Brief 8.3: a domain move is one build argument, not a code change.

    The test builds against an address that is not the published one and asserts
    that no page still names the published one. A literal github.io anywhere in
    the generator would survive the substitution and fail here.
    """
    other = "https://example.invalid/harness/"
    output = _build(tmp_path / "site", base_url=other)

    for page in _pages(output):
        text = page.read_text(encoding="utf-8")
        assert "mrbinnacle.github.io" not in text, f"{page.name} hardcodes the host"
        head = _head_of(page)
        for attribute in ("og:url", "og:image"):
            value = _meta(head, prop=attribute)
            assert value is not None and value.startswith(other), (page.name, attribute)


def test_no_template_hardcodes_the_published_host() -> None:
    """The same rule at its source, so the finding names the file to edit."""
    for template in sorted(_TEMPLATES.glob("*.html")):
        assert "github.io" not in template.read_text(encoding="utf-8"), template.name


# ---------------------------------------------------------------------------
# The landing copy reader refuses rather than drops (brief 8.2)
# ---------------------------------------------------------------------------


def test_the_landing_copy_fixture_parses() -> None:
    """The reader accepts the shape the brief fixes."""
    copy = parse_landing(_LANDING_COPY.read_text(encoding="utf-8"))
    assert copy.heading
    assert copy.detects
    assert copy.control
    assert copy.evidence_is_thin
    assert len(copy.pointers) == POINTER_COUNT
    assert len(copy.lead.split()) <= 20


def test_the_capability_sentence_never_renders_without_its_caveat(tmp_path: Path) -> None:
    """Issue #588: the 8-of-8 figure belongs to a declared synthetic control.

    The owner's ordering comment requires the page to say so plainly rather
    than let the number read as a win.

    An earlier version of this test called ``parse_landing`` and asserted the
    parser raised. An independent reviewer pointed out that it therefore never
    rendered anything, so it proved the parser was fussy and left the template
    free to emit the number without the caveat. The name claimed a render the
    body never performed. This version builds the site and reads the page, so
    the assertion is about the HTML a stranger receives.
    """
    output = _build(tmp_path / "site", landing=True)
    page = (output / "index.html").read_text(encoding="utf-8")

    copy = parse_landing(_LANDING_COPY.read_text(encoding="utf-8"))
    assert copy.detects in page
    assert copy.control in page, (
        "the rendered page carries the capability sentence without its caveat"
    )
    assert page.index(copy.detects) < page.index(copy.control), (
        "the caveat must follow the figure it qualifies, not precede it"
    )


def test_the_published_figure_matches_the_receipt_it_came_from() -> None:
    """Issue #588: no line may claim anything this repository cannot show.

    The capability sentence prints two integers. Copy is not data, so nothing
    else in this change stops those integers drifting from the run that
    produced them. This binds them to the receipt on disk. If the receipt
    changes or the sentence is edited to a different score, this fails.
    """
    receipt = json.loads(
        (_REPO / "docs" / "sers" / "receipts" / "synthetic-control-keep-2026-07-27.json").read_text(
            encoding="utf-8"
        )
    )
    measurements = receipt["measurements"]
    full = measurements["full_pass_rate"]
    null = measurements["null_pass_rate"]
    assert receipt["declared_synthetic_control"] is True, (
        "the page calls this control synthetic; the receipt must agree"
    )

    sentence = parse_landing(_LANDING_COPY.read_text(encoding="utf-8")).detects
    assert f"{full['passes']} of {full['epochs']}" in sentence, (
        f"the page states a Full score the receipt does not: {sentence!r}"
    )
    assert f"{null['passes']} of {null['epochs']}" in sentence, (
        f"the page states a Null score the receipt does not: {sentence!r}"
    )


def test_a_fourth_pointer_is_refused() -> None:
    """Issue #588: three pointers and nothing else, held by the build.

    A reviewer counting bullets is the control this replaces.
    """
    text = _LANDING_COPY.read_text(encoding="utf-8")
    text += "- One more -> https://example.invalid/\n  A fourth pointer.\n"
    with pytest.raises(SiteBuildError) as caught:
        parse_landing(text)
    assert str(POINTER_COUNT) in str(caught.value)


def test_a_pointer_without_a_supporting_line_is_refused() -> None:
    """Issue #588: each pointer says what is behind it and why to want it.

    The line to strip is read out of the parsed copy rather than written here.
    A hardcoded sentence makes this test pass vacuously the moment the copy is
    edited: it would remove nothing, the parse would succeed, and the control
    would be gone with nothing going red. That happened once while this change
    was being written.
    """
    text = _LANDING_COPY.read_text(encoding="utf-8")
    support = parse_landing(text).pointers[0].support
    assert support in text, "the support line could not be located in the copy"
    stripped = text.replace(support + "\n", "", 1)
    assert stripped != text, "nothing was removed, so this test would pass vacuously"

    with pytest.raises(SiteBuildError) as caught:
        parse_landing(stripped)
    assert "supporting line" in str(caught.value)


def test_a_sixth_section_is_refused() -> None:
    """Brief halt item 8: the section count is fixed, and a machine holds it."""
    text = _LANDING_COPY.read_text(encoding="utf-8") + "\n\n## Testimonials\n\nSomething.\n"
    with pytest.raises(SiteBuildError) as caught:
        parse_landing(text)
    assert "Testimonials" in str(caught.value)


def test_renaming_the_section_is_refused() -> None:
    """Brief halt item 8: the section set is fixed, not only its size.

    This test pinned section ORDER until issue #588 cut the page to one
    section, where order is not a thing a document can get wrong. The rule that
    survives is the one order was a special case of: the heading set is the
    build's to hold, and a rename is a Direction decision. Pinning the rename
    keeps a live control here rather than deleting an assertion because its
    original phrasing stopped applying.
    """
    text = _LANDING_COPY.read_text(encoding="utf-8").replace(
        "## " + SECTION_TITLES[0], "## Further reading", 1
    )
    with pytest.raises(SiteBuildError) as caught:
        parse_landing(text)
    assert "Further reading" in str(caught.value)


def test_an_unrecognised_construct_is_refused_rather_than_dropped() -> None:
    """Brief 8.2: the reader raises on a construct it does not know.

    Silently dropping copy is the failure mode a hand-rolled Markdown subset
    invites, and it is the one this reader exists to refuse.
    """
    text = _LANDING_COPY.read_text(encoding="utf-8").replace(
        "## " + SECTION_TITLES[0],
        "## " + SECTION_TITLES[0] + "\n\n> A block quote the reader does not know.",
        1,
    )
    with pytest.raises(SiteBuildError):
        parse_landing(text)


def test_a_relative_link_target_is_refused() -> None:
    """Brief 8.2: an internal target is symbolic, because the href moves.

    receipts lives at index.html with the flag off and at receipts.html with it
    on. A path written into the copy is correct in one state and broken in the
    other, so the copy names the destination and the generator resolves it.
    """
    text = _LANDING_COPY.read_text(encoding="utf-8").replace(" -> receipts", " -> receipts.html")
    with pytest.raises(SiteBuildError) as caught:
        parse_landing(text)
    assert "receipts.html" in str(caught.value)


def test_a_lead_longer_than_the_brief_allows_is_refused() -> None:
    """Brief 4.6: the hero lead is at most 20 words."""
    text = _LANDING_COPY.read_text(encoding="utf-8").replace("lead: ", "lead: " + ("word " * 25), 1)
    with pytest.raises(SiteBuildError) as caught:
        parse_landing(text)
    assert "20 words" in str(caught.value)


def test_the_landing_build_refuses_a_missing_copy_file(tmp_path: Path) -> None:
    """The flag without the copy is a refusal, not an empty page."""
    with pytest.raises(SiteBuildError) as caught:
        build_site(
            schema_path=_SCHEMA,
            receipts_dir=_RECEIPTS,
            extraction_path=None,
            output_dir=tmp_path / "site",
            marker=_MARKER,
            landing=True,
            landing_copy_path=tmp_path / "nowhere.md",
        )
    assert "nowhere.md" in str(caught.value)


# ---------------------------------------------------------------------------
# The footer (brief 4.2)
# ---------------------------------------------------------------------------


def test_the_visible_marker_is_on_the_data_pages_and_off_the_landing_page(
    tmp_path: Path,
) -> None:
    """Brief 4.2: a build marker is a real identifier on a devtool page.

    On the landing page it is a version footer, which the governing skill bans,
    and it is not needed there because the meta tag carries the marker.
    """
    output = _build(tmp_path / "site", landing=True)

    landing_text = (output / "index.html").read_text(encoding="utf-8")
    assert "<footer" not in landing_text

    for page in _pages(output):
        if page.name == "index.html":
            continue
        assert "<footer" in page.read_text(encoding="utf-8"), page.name
