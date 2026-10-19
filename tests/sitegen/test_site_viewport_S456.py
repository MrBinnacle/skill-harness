"""The narrow viewport, one test per S456 Check-report defect.

The S455 pass built the site and the S456 Check seat read it in a browser at
360px and 1440px. It found the site ready for a stranger at 1440 and not ready
at 360. Four of its six defects are geometry and they are pinned here.

What a test can hold and what it cannot is the line this file draws. A test can
hold that the stylesheet still carries the rule and that the markup still
carries the label the rule prints. It cannot hold that the page reads, and the
report's own numbers came from a browser rather than from a suite. Every
assertion below names the measurement it stands in for.

#589 built that browser reading. It lives in ``test_rendered_geometry.py``, and
the fourteen stylesheet greps this file used to spell inline now live in
``_s456_rules.py`` as named predicates. Nothing about what they hold changed.
They moved so the harness's negative control can run all fourteen against a
stylesheet a real browser has just measured as broken and show every one still
returning True, which is this file's own blindness stated as an assertion
rather than as the paragraph above.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from skill_harness.sitegen.render import FIGURE_COLUMN_LABELS, INDEX_COLUMN_LABELS
from tests.sitegen._s456_rules import (
    RULE_CELLS_BREAK_WORDS,
    RULE_DEFINITION_RULE_PINNED,
    RULE_DL_IS_ONE_COLUMN,
    RULE_HEADER_ROW_STAYS_IN_THE_TREE,
    RULE_LEAD_HAS_ROOM,
    RULE_NO_CELL_HIDDEN_FOR_BEING_EMPTY,
    RULE_REFUSAL_NOT_CRAMPED,
    RULE_ROW_LABEL_CAP_SCOPED,
    RULE_SINGLE_TRACK_ZERO_FLOOR,
    RULE_STACKED_LABEL_CARRIES_NO_COPY,
    RULE_STACKS_COST_TABLE,
    RULE_STACKS_MEASUREMENTS_TABLE,
    RULE_STACKS_RECEIPTS_TABLE,
    RULE_SYMPTOM_NOT_HIDDEN,
    StylesheetRule,
)
from tests.sitegen._sites import build_fixture_site

_REPO = Path(__file__).resolve().parents[2]
_STYLESHEET = _REPO / "src" / "skill_harness" / "sitegen" / "style.css"


def _build(output: Path) -> Path:
    """The repository's own site, through the shared builder.

    ``landing=False`` keeps this file measuring exactly the page set it always
    measured. The landing page is the geometry harness's business.
    """
    return build_fixture_site(output, landing=False)


def _css() -> str:
    """The stylesheet as it is on disk.

    Comment stripping used to happen here and now happens inside each predicate,
    because it is part of what a grep over this file means and both callers of a
    rule have to strip identically.
    """
    return _STYLESHEET.read_text(encoding="utf-8")


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
    assert RULE_DL_IS_ONE_COLUMN.holds(_css()), (
        "the narrow viewport no longer gives a definition list a single column"
    )


def test_the_single_column_track_has_a_zero_floor() -> None:
    """D1's second half, and it was measured after the first half shipped.

    A grid track's default floor is the item's min-content width. One receipt
    states a 40-character run id in its notes, so an auto floor made the track
    wider than the viewport and the page scrolled sideways by 212px.
    """
    assert RULE_SINGLE_TRACK_ZERO_FLOOR.holds(_css()), (
        "the definition list's single track no longer has a zero floor"
    )


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
    assert RULE_CELLS_BREAK_WORDS.holds(_css()), (
        "td, th, p and .figure must break on word boundaries and must not shred words; "
        "dd, td code and dd code must be able to break a machine token anywhere; "
        "th code must break on word boundaries"
    )


def test_the_definition_rule_is_pinned_on_its_own_ground() -> None:
    """``dd`` keeps ``anywhere``, and nothing else may be assumed to carry it.

    An independent reading at S456 measured the two narrow-viewport exceptions
    against each other. Either the ``dd`` rule or the definition list's zero
    track floor is sufficient alone to keep a receipt's prose fields inside a
    360px viewport; neither is necessary while the other stands. Both ship, and
    both are pinned here, because the failure mode is a later seat removing one
    on the belief that the other carries it by itself.
    """
    assert RULE_DEFINITION_RULE_PINNED.holds(_css()), (
        "the dd rule is gone; the dl track floor alone is not a reason to remove it"
    )


def test_the_stylesheet_still_refuses_to_hide_the_symptom() -> None:
    """Brief 4.2, carried forward. A hidden overflow is a concealed defect.

    S456 found the same concealment reached by another route: the word breaking
    was what kept the receipts index reporting no horizontal overflow while it
    needed 531px of a 328px main.
    """
    assert RULE_SYMPTOM_NOT_HIDDEN.holds(_css()), "the stylesheet hides a horizontal overflow"


# ---------------------------------------------------------------------------
# Defect 3: the five-column index needed 531px and had 328
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "labels"),
    [
        (RULE_STACKS_RECEIPTS_TABLE, INDEX_COLUMN_LABELS),
        (RULE_STACKS_MEASUREMENTS_TABLE, FIGURE_COLUMN_LABELS),
        (RULE_STACKS_COST_TABLE, FIGURE_COLUMN_LABELS),
    ],
    ids=["receipts", "measurements", "cost"],
)
def test_the_narrow_viewport_stops_drawing_these_tables(
    rule: StylesheetRule, labels: tuple[str, ...]
) -> None:
    """D3. Below 40rem each of the three becomes one labelled block per row."""
    assert rule.holds(_css()), f"{rule.name} no longer holds"
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
    assert RULE_STACKED_LABEL_CARRIES_NO_COPY.holds(_css()), (
        "either nothing prints the column label any more, or the stylesheet writes copy "
        "into generated content"
    )


def test_the_header_row_leaves_the_screen_and_stays_in_the_accessibility_tree() -> None:
    """``display: none`` on ``thead`` takes the column headers out of both.

    Measured on the first cut at 360px: zero ``columnheader`` nodes in the
    accessibility tree against five at 1440px, on the same page. The label a
    sighted reader gets comes from CSS generated content, which is not a header
    to assistive technology, so dropping the row dropped the association. The
    row goes off-canvas instead, the same technique the skip link uses.
    """
    assert RULE_HEADER_ROW_STAYS_IN_THE_TREE.holds(_css()), (
        "the narrow viewport either no longer rules the header row, or removes it from "
        "the accessibility tree instead of moving it off-canvas"
    )


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
    assert RULE_NO_CELL_HIDDEN_FOR_BEING_EMPTY.holds(_css()), (
        "a width-dependent cell is being concealed again"
    )


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
    assert RULE_ROW_LABEL_CAP_SCOPED.holds(_css()), (
        "the cap is missing from the wide viewport, or is declared outside it"
    )


# ---------------------------------------------------------------------------
# The two smaller defects (D4 and D6)
# ---------------------------------------------------------------------------


def test_the_lead_has_room_between_its_lines() -> None:
    """D4. 21px on 1.2 leading is a 25.2px line box; the detector needs 1.3."""
    assert RULE_LEAD_HAS_ROOM.holds(_css()), "the lead sets less than 1.3 leading"


def test_a_refusal_block_is_not_cramped_against_its_own_edge() -> None:
    """D6. 0.25rem is 4px against 14.72px text and the detector needs 4.4px.

    The 4px left edge stays. It is what tells a refusal from an absence, the
    detector calls it an AI tell, and the Check seat overruled the detector on
    the owner's own stylesheet comment. That argument is not reopened here.
    """
    assert RULE_REFUSAL_NOT_CRAMPED.holds(_css()), (
        "a refusal block's vertical padding is under 4.4px, or its left edge is gone"
    )
