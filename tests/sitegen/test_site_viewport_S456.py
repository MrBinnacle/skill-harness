"""The narrow viewport, one test per S456 Check-report defect.

The S455 pass built the site and the S456 Check seat read it in a browser at
360px and 1440px. It found the site ready for a stranger at 1440 and not ready
at 360. Four of its six defects are geometry and they are pinned here.

What a test can hold and what it cannot is the line this file draws. A test can
hold that the stylesheet still carries the rule and that the markup still
carries the label the rule prints. It cannot hold that the page reads, and the
report's own numbers came from a browser rather than from a suite. Every
assertion below names the measurement it stands in for, so the next pass can
find the browser reading rather than trusting the green.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from skill_harness.sitegen import DEFAULT_BASE_URL, build_site
from skill_harness.sitegen.render import FIGURE_COLUMN_LABELS, INDEX_COLUMN_LABELS

_REPO = Path(__file__).resolve().parents[2]
_STYLESHEET = _REPO / "src" / "skill_harness" / "sitegen" / "style.css"
_SCHEMA = _REPO / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO / "docs" / "sers" / "receipts"
_NARROW = "@media (max-width: 40rem)"
_WIDE = "@media (min-width: 40rem)"


def _build(output: Path) -> Path:
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=_RECEIPTS,
        extraction_path=None,
        output_dir=output,
        marker="s456-viewport-marker",
        base_url=DEFAULT_BASE_URL,
    )
    return output


def _css() -> str:
    """The stylesheet with its comments removed.

    The comments quote the defects by name, so a substring search over the whole
    file finds the shredded word inside the sentence explaining the shredding.
    """
    return re.sub(r"/\*.*?\*/", "", _STYLESHEET.read_text(encoding="utf-8"), flags=re.DOTALL)


def _media_blocks(css: str, opener: str) -> str:
    """Everything inside every ``@media`` block that opens with ``opener``."""
    blocks: list[str] = []
    for match in re.finditer(re.escape(opener), css):
        depth = 0
        for index in range(match.start(), len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(css[match.start() : index + 1])
                    break
        else:
            raise AssertionError(f"{opener} block never closes")
    assert blocks, f"the stylesheet carries no {opener} block"
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Defect 1: the definition list collapsed to one character a line at 360px
# ---------------------------------------------------------------------------


def test_a_definition_list_is_one_column_on_a_narrow_viewport() -> None:
    """D1. Two tracks need two columns' worth of room, and 328px is not that.

    The landing page's refusals list has a term 54 characters long. Its
    max-content width exceeded the whole main element, which left the second
    track a few pixels and ran the definition down the page one letter to a
    line for roughly two thousand pixels of scroll.
    """
    narrow = _media_blocks(_css(), _NARROW)
    assert re.search(r"\bdl\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)", narrow), (
        "the narrow viewport no longer gives a definition list a single column"
    )


def test_the_single_column_track_has_a_zero_floor() -> None:
    """D1's second half, and it was measured after the first half shipped.

    A grid track's default floor is the item's min-content width. One receipt
    states a 40-character run id in its notes, so an auto floor made the track
    wider than the viewport and the page scrolled sideways by 212px.
    """
    narrow = _media_blocks(_css(), _NARROW)
    assert "minmax(0, 1fr)" in narrow
    assert not re.search(r"\bdl\s*\{[^}]*grid-template-columns:\s*1fr\s*;", narrow)


# ---------------------------------------------------------------------------
# Defect 2: ordinary words broke between letters, at both widths
# ---------------------------------------------------------------------------


def test_a_cell_breaks_words_and_a_machine_token_breaks_anywhere() -> None:
    """D2. The two properties are not interchangeable.

    ``anywhere`` also shrinks min-content, so a table column carrying it
    collapses to one character and the cell shreds English to fit: "Ver / dic /
    t", "absen / t", "not_instrumen / ted". It belongs on the unbreakable
    machine string and nowhere else.
    """
    css = _css()
    breaking = re.findall(r"([^{}]+)\{[^}]*overflow-wrap:\s*break-word", css)
    anywhere = re.findall(r"([^{}]+)\{[^}]*overflow-wrap:\s*anywhere", css)

    selectors_breaking = {part.strip() for group in breaking for part in group.split(",")}
    selectors_anywhere = {part.strip() for group in anywhere for part in group.split(",")}

    for selector in ("td", "th", "p", ".figure"):
        assert selector in selectors_breaking, f"{selector} no longer breaks on word boundaries"
        assert selector not in selectors_anywhere, f"{selector} shreds words again"

    for selector in ("dd", "td code", "dd code"):
        assert selector in selectors_anywhere, f"{selector} can no longer break a machine token"

    assert "th code" in selectors_breaking, "the row header's schema key shreds again"


def test_the_definition_rule_is_pinned_on_its_own_ground() -> None:
    """``dd`` keeps ``anywhere``, and nothing else may be assumed to carry it.

    An independent reading at S456 measured the two narrow-viewport exceptions
    against each other. Either the ``dd`` rule or the definition list's zero
    track floor is sufficient alone to keep a receipt's prose fields inside a
    360px viewport; neither is necessary while the other stands. Both ship, and
    both are pinned here, because the failure mode is a later seat removing one
    on the belief that the other carries it by itself.
    """
    css = _css()
    assert re.search(r"(^|\n)dd,\n[^{]*\{[^}]*overflow-wrap:\s*anywhere", css), (
        "the dd rule is gone; the dl track floor alone is not a reason to remove it"
    )
    assert "minmax(0, 1fr)" in _media_blocks(css, _NARROW)


def test_the_stylesheet_still_refuses_to_hide_the_symptom() -> None:
    """Brief 4.2, carried forward. A hidden overflow is a concealed defect.

    S456 found the same concealment reached by another route: the word breaking
    was what kept the receipts index reporting no horizontal overflow while it
    needed 531px of a 328px main.
    """
    assert "overflow-x: hidden" not in _css()


# ---------------------------------------------------------------------------
# Defect 3: the five-column index needed 531px and had 328
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table_class", "labels"),
    [
        ("receipts", INDEX_COLUMN_LABELS),
        ("measurements", FIGURE_COLUMN_LABELS),
        ("cost", FIGURE_COLUMN_LABELS),
    ],
)
def test_the_narrow_viewport_stops_drawing_these_tables(
    table_class: str, labels: tuple[str, ...]
) -> None:
    """D3. Below 40rem each of the three becomes one labelled block per row."""
    narrow = _media_blocks(_css(), _NARROW)
    assert f".{table_class} tbody" in narrow
    assert f".{table_class} thead" in narrow
    assert f".{table_class} td::before" in narrow
    assert "content: attr(data-label)" in narrow
    assert labels, "a stacked table with no column labels would print bare values"


def test_the_stacked_label_carries_no_copy_in_the_stylesheet() -> None:
    """The generated content prints the attribute whole and adds nothing to it.

    Silent choice 1 of the first cut put the labels in ``data-label`` rather
    than in CSS, on the ground that copy in a stylesheet sits outside every gate
    that reads copy. That cut then wrote ``": "`` into the same declaration,
    which is copy in a stylesheet by its own test. The label is a block above
    its value instead, which is the shape the definition lists take at this
    width and needs no separator at all.
    """
    narrow = _media_blocks(_css(), _NARROW)
    generated = re.findall(r"content:\s*([^;]+);", narrow)
    assert generated, "nothing prints the column label any more"
    for declaration in generated:
        assert declaration.strip() == "attr(data-label)", (
            f"the stylesheet writes copy into generated content: {declaration!r}"
        )


def test_the_header_row_leaves_the_screen_and_stays_in_the_accessibility_tree() -> None:
    """``display: none`` on ``thead`` takes the column headers out of both.

    Measured on the first cut at 360px: zero ``columnheader`` nodes in the
    accessibility tree against five at 1440px, on the same page. The label a
    sighted reader gets comes from CSS generated content, which is not a header
    to assistive technology, so dropping the row dropped the association. The
    row goes off-canvas instead, the same technique the skip link uses.
    """
    narrow = _media_blocks(_css(), _NARROW)
    match = re.search(r"thead[^{]*\{([^}]*)\}", narrow)
    assert match is not None, "the narrow viewport no longer rules the header row"
    body = match.group(1)
    assert "display: none" not in body, "the header row is removed from the accessibility tree"
    assert "position: absolute" in body
    assert "left: -100vw" in body


def test_no_cell_ships_empty(tmp_path: Path) -> None:
    """A blank cell at 1440px was a dropped line at 360px, and nobody was told.

    Measured on the first cut through the rendered DOM: 43 ``<td>`` elements
    across the four receipt pages matched ``td:empty``, every one of them a
    figure's missing Detail. At 1440px each drew a box. At 360px they drew
    nothing and the phone reader was not told the field existed. An absent
    detail now states itself in the words the qualifier fields and a missing
    measurement key already use, at every width.
    """
    output = _build(tmp_path / "site")
    checked = 0
    for page in sorted(output.glob("*.html")):
        for cell in ET.parse(page).getroot().iter("td"):
            assert "".join(cell.itertext()).strip(), f"{page.name}: an empty cell ships"
            checked += 1
    assert checked, "the build rendered no cells to check"


def test_the_narrow_viewport_hides_no_cell_on_the_ground_that_it_is_empty() -> None:
    """The rule that dropped the cell is gone, and may not come back.

    Stating the absence removes the reason the rule existed. The rule is pinned
    out separately from the markup because a later pass could restore it while
    every cell still ships non-empty, and the next receipt with a blank field
    would reintroduce the width-dependent drop with no test going red.
    """
    assert "td:empty" not in _css(), "a width-dependent cell is being concealed again"


def test_every_body_cell_carries_the_column_label_its_header_states(tmp_path: Path) -> None:
    """The stacked blocks print ``data-label``, so the two must not drift.

    The header row is written in HTML and the body rows are written in Python.
    That duplication is deliberate and this is the test that makes it safe: the
    labels in the head equal the labels in the body, row by row, on the real
    build.
    """
    output = _build(tmp_path / "site")
    checked = 0
    for page in sorted(output.glob("*.html")):
        root = ET.parse(page).getroot()
        for table in root.iter("table"):
            head = table.find("thead")
            body = table.find("tbody")
            if head is None or body is None:
                continue
            columns = ["".join(cell.itertext()).strip() for cell in head.iter("th")]
            for row in body.iter("tr"):
                cells = list(row.iter("td"))
                labels = [cell.get("data-label") for cell in cells]
                assert None not in labels, f"{page.name}: a body cell carries no data-label"
                # The row header occupies the first column, so the data cells
                # line up with the tail of the header row.
                assert labels == columns[len(columns) - len(cells) :], (
                    f"{page.name}: {labels} does not match the header row {columns}"
                )
                checked += 1
    assert checked >= 4, "the build rendered no table rows to check"


# ---------------------------------------------------------------------------
# The row-label cap (Check report question 1, finding F7)
# ---------------------------------------------------------------------------


def test_the_row_label_cap_is_scoped_to_the_wide_viewport() -> None:
    """F7. 22rem is right at 1440px and no cap value is right at 360px.

    Measured: at 1440 the cap buys the figure column 27px over an uncapped
    header. At 360 it makes the header 98px of 328 and removing it makes the
    figure column 55px, which is worse. The narrow viewport stops drawing the
    table instead.
    """
    css = _css()
    wide = _media_blocks(css, _WIDE)
    assert "max-width: 22rem" in wide
    assert css.count("max-width: 22rem") == 1, "the cap is declared outside the wide viewport"


# ---------------------------------------------------------------------------
# The two smaller defects (D4 and D6)
# ---------------------------------------------------------------------------


def _declaration(css: str, selector: str, prop: str) -> str:
    """The value of ``prop`` in the rule whose selector list ends with ``selector``.

    Every rule is scanned rather than only the first match, because ``.lead``
    also appears in the shared mono font-family group above the rule that sets
    its own leading, and a first-match reader reports the wrong block.
    """
    wanted = {part.strip() for part in selector.split(",")}
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        selectors = {part.strip() for part in match.group(1).split(",")}
        if not wanted <= selectors:
            continue
        found = re.search(rf"{re.escape(prop)}:\s*([^;]+);", match.group(2))
        if found is not None:
            return found.group(1).strip()
    raise AssertionError(f"no rule for {selector} declares {prop}")


def test_the_lead_has_room_between_its_lines() -> None:
    """D4. 21px on 1.2 leading is a 25.2px line box; the detector needs 1.3."""
    leading = float(_declaration(_css(), ".lead", "line-height"))
    assert leading >= 1.3, f"the lead sets {leading} leading"


def test_a_refusal_block_is_not_cramped_against_its_own_edge() -> None:
    """D6. 0.25rem is 4px against 14.72px text and the detector needs 4.4px.

    The 4px left edge stays. It is what tells a refusal from an absence, the
    detector calls it an AI tell, and the Check seat overruled the detector on
    the owner's own stylesheet comment. That argument is not reopened here.
    """
    css = _css()
    padding = _declaration(css, ".refusal,\n.refused", "padding")
    top, _right, bottom, _left = padding.split()
    assert float(top.removesuffix("rem")) * 16 >= 4.4, padding
    assert float(bottom.removesuffix("rem")) * 16 >= 4.4, padding
    assert "border-left: 4px solid var(--bench-cant-tell)" in css
