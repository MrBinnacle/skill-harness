"""The fourteen S456 stylesheet greps, as named pure predicates (#589).

``tests/sitegen/test_site_viewport_S456.py`` asserted these inline. Extracting them
changes no behaviour: each rule below is the same expression the assertion held, and the
test file now calls it. The rules moved so that the negative control in
``test_rendered_geometry.py`` can run ALL FOURTEEN against a stylesheet a real browser
has just measured as broken, and show every one still returning ``True``.

That is what this whole ticket claims, stated as an executable assertion instead of a
paragraph in a docstring: a grep over ``style.css`` cannot see a rendered page, so a
cascade override that leaves every rule's text intact keeps all fourteen green while the
site breaks.

Every predicate is TOTAL. It takes stylesheet source text and returns a bool for any
input, never raising, because the negative control feeds it a deliberately broken
stylesheet and a control that errors is not a control that measured something.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_NARROW = "@media (max-width: 40rem)"
_WIDE = "@media (min-width: 40rem)"


@dataclass(frozen=True)
class StylesheetRule:
    """One of the fourteen S456 greps, as a pure predicate over stylesheet text.

    ``defect`` is the S456 Check-report defect the grep stands in for, so a reader of the
    blind set can tell which rendered failure each rule was supposed to be guarding.
    """

    name: str
    defect: str
    holds: Callable[[str], bool]


def _strip_comments(css: str) -> str:
    """The stylesheet with its comments removed.

    The comments quote the defects by name, so a substring search over the whole file
    finds the shredded word inside the sentence explaining the shredding. This lived in
    the test file's ``_css()`` helper; it belongs in the predicate, because stripping is
    part of what the grep means and both callers must strip identically.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _rule(name: str, defect: str, predicate: Callable[[str], bool]) -> StylesheetRule:
    """Bind one predicate to its name, with comment stripping applied to its input."""
    return StylesheetRule(
        name=name, defect=defect, holds=lambda css: predicate(_strip_comments(css))
    )


def _media_blocks(css: str, opener: str) -> str:
    """Everything inside every ``@media`` block that opens with ``opener``.

    An empty string when there is no such block, so a rule over a stylesheet that lost
    its narrow viewport entirely returns False rather than raising.
    """
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
    return "\n".join(blocks)


def _selectors_declaring(css: str, prop: str, value: str) -> set[str]:
    """Every selector in every rule whose block declares ``prop: value``."""
    groups = re.findall(rf"([^{{}}]+)\{{[^}}]*{re.escape(prop)}:\s*{re.escape(value)}", css)
    return {part.strip() for group in groups for part in group.split(",")}


def _declaration(css: str, selector: str, prop: str) -> str | None:
    """The value of ``prop`` in the rule whose selector list contains ``selector``.

    Every rule is scanned rather than only the first match, because ``.lead`` also
    appears in the shared mono font-family group above the rule that sets its own
    leading, and a first-match reader reports the wrong block.
    """
    wanted = {part.strip() for part in selector.split(",")}
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        selectors = {part.strip() for part in match.group(1).split(",")}
        if not wanted <= selectors:
            continue
        found = re.search(rf"{re.escape(prop)}:\s*([^;]+);", match.group(2))
        if found is not None:
            return found.group(1).strip()
    return None


def _rem_px(value: str) -> float | None:
    """``0.3rem`` as 4.8 CSS pixels, or None when the value is not a rem length."""
    if not value.endswith("rem"):
        return None
    try:
        return float(value.removesuffix("rem")) * 16
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# D1: the definition list collapsed to one character a line at 360px
# ---------------------------------------------------------------------------


def _dl_is_one_column(css: str) -> bool:
    """Two tracks need two columns' worth of room, and 328px is not that."""
    narrow = _media_blocks(css, _NARROW)
    return bool(re.search(r"\bdl\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)", narrow))


def _the_single_track_has_a_zero_floor(css: str) -> bool:
    """A grid track's default floor is its item's min-content width, and one receipt
    states a 40-character run id, which made the track wider than the viewport."""
    narrow = _media_blocks(css, _NARROW)
    if "minmax(0, 1fr)" not in narrow:
        return False
    return not re.search(r"\bdl\s*\{[^}]*grid-template-columns:\s*1fr\s*;", narrow)


# ---------------------------------------------------------------------------
# D2: ordinary words broke between letters, at both widths
# ---------------------------------------------------------------------------


def _cells_break_words_and_tokens_break_anywhere(css: str) -> bool:
    """``anywhere`` also shrinks min-content, so a table column carrying it collapses to
    one character and the cell shreds English to fit. It belongs on the unbreakable
    machine string and nowhere else."""
    breaking = _selectors_declaring(css, "overflow-wrap", "break-word")
    anywhere = _selectors_declaring(css, "overflow-wrap", "anywhere")
    for selector in ("td", "th", "p", ".figure"):
        if selector not in breaking or selector in anywhere:
            return False
    if any(selector not in anywhere for selector in ("dd", "td code", "dd code")):
        return False
    return "th code" in breaking


def _the_definition_rule_is_pinned_on_its_own_ground(css: str) -> bool:
    """Either the ``dd`` rule or the definition list's zero track floor is sufficient
    alone; neither is necessary while the other stands. Both ship, and both are pinned,
    because the failure mode is a later seat removing one believing the other carries
    it."""
    if not re.search(r"(^|\n)dd,\n[^{]*\{[^}]*overflow-wrap:\s*anywhere", css):
        return False
    return "minmax(0, 1fr)" in _media_blocks(css, _NARROW)


def _the_symptom_is_not_hidden(css: str) -> bool:
    """A hidden overflow is a concealed defect. The word breaking was what kept the
    receipts index reporting no horizontal overflow while it needed 531px of a 328px
    main."""
    return "overflow-x: hidden" not in css


# ---------------------------------------------------------------------------
# D3: the five-column index needed 531px and had 328
# ---------------------------------------------------------------------------


def _stacks_the_table(table_class: str) -> Callable[[str], bool]:
    """Below 40rem this table becomes one labelled block per row."""

    def predicate(css: str) -> bool:
        narrow = _media_blocks(css, _NARROW)
        return (
            f".{table_class} tbody" in narrow
            and f".{table_class} thead" in narrow
            and f".{table_class} td::before" in narrow
            and "content: attr(data-label)" in narrow
        )

    return predicate


def _the_stacked_label_carries_no_copy(css: str) -> bool:
    """The generated content prints the attribute whole and adds nothing to it. Copy in
    a stylesheet sits outside every gate that reads copy."""
    generated = re.findall(r"content:\s*([^;]+);", _media_blocks(css, _NARROW))
    if not generated:
        return False
    return all(declaration.strip() == "attr(data-label)" for declaration in generated)


def _the_header_row_leaves_the_screen_and_stays_in_the_tree(css: str) -> bool:
    """``display: none`` on ``thead`` takes the column headers out of the accessibility
    tree as well as off the screen: zero ``columnheader`` nodes at 360px against five at
    1440px. The row goes off-canvas instead."""
    match = re.search(r"thead[^{]*\{([^}]*)\}", _media_blocks(css, _NARROW))
    if match is None:
        return False
    body = match.group(1)
    return "display: none" not in body and "position: absolute" in body and "left: -100vw" in body


def _no_cell_is_hidden_for_being_empty(css: str) -> bool:
    """A later pass could restore the rule while every cell still ships non-empty, and
    the next receipt with a blank field would reintroduce the width-dependent drop with
    no test going red."""
    return "td:empty" not in css


# ---------------------------------------------------------------------------
# F7: the row-label cap
# ---------------------------------------------------------------------------


def _the_row_label_cap_is_scoped_to_the_wide_viewport(css: str) -> bool:
    """22rem is right at 1440px and no cap value is right at 360px. At 360 the cap makes
    the header 98px of 328 and removing it makes the figure column 55px, which is
    worse."""
    if "max-width: 22rem" not in _media_blocks(css, _WIDE):
        return False
    return css.count("max-width: 22rem") == 1


# ---------------------------------------------------------------------------
# D4 and D6: the two smaller defects
# ---------------------------------------------------------------------------


def _the_lead_has_room_between_its_lines(css: str) -> bool:
    """21px on 1.2 leading is a 25.2px line box; the detector needs 1.3."""
    value = _declaration(css, ".lead", "line-height")
    if value is None:
        return False
    try:
        leading = float(value)
    except ValueError:
        return False
    return leading >= 1.3


def _a_refusal_block_is_not_cramped(css: str) -> bool:
    """0.25rem is 4px against 14.72px text and the detector needs 4.4px. The 4px left
    edge stays: it is what tells a refusal from an absence."""
    padding = _declaration(css, ".refusal,\n.refused", "padding")
    if padding is None:
        return False
    parts = padding.split()
    if len(parts) != 4:
        return False
    for raw in (parts[0], parts[2]):
        pixels = _rem_px(raw)
        if pixels is None or pixels < 4.4:
            return False
    return "border-left: 4px solid var(--bench-cant-tell)" in css


RULE_DL_IS_ONE_COLUMN = _rule("dl_is_one_column_on_a_narrow_viewport", "D1", _dl_is_one_column)
RULE_SINGLE_TRACK_ZERO_FLOOR = _rule(
    "the_single_column_track_has_a_zero_floor", "D1", _the_single_track_has_a_zero_floor
)
RULE_CELLS_BREAK_WORDS = _rule(
    "a_cell_breaks_words_and_a_machine_token_breaks_anywhere",
    "D2",
    _cells_break_words_and_tokens_break_anywhere,
)
RULE_DEFINITION_RULE_PINNED = _rule(
    "the_definition_rule_is_pinned_on_its_own_ground",
    "D2",
    _the_definition_rule_is_pinned_on_its_own_ground,
)
RULE_SYMPTOM_NOT_HIDDEN = _rule(
    "the_stylesheet_still_refuses_to_hide_the_symptom", "D2", _the_symptom_is_not_hidden
)
RULE_STACKS_RECEIPTS_TABLE = _rule(
    "the_narrow_viewport_stops_drawing_the_receipts_table", "D3", _stacks_the_table("receipts")
)
RULE_STACKS_MEASUREMENTS_TABLE = _rule(
    "the_narrow_viewport_stops_drawing_the_measurements_table",
    "D3",
    _stacks_the_table("measurements"),
)
RULE_STACKS_COST_TABLE = _rule(
    "the_narrow_viewport_stops_drawing_the_cost_table", "D3", _stacks_the_table("cost")
)
RULE_STACKED_LABEL_CARRIES_NO_COPY = _rule(
    "the_stacked_label_carries_no_copy_in_the_stylesheet", "D3", _the_stacked_label_carries_no_copy
)
RULE_HEADER_ROW_STAYS_IN_THE_TREE = _rule(
    "the_header_row_leaves_the_screen_and_stays_in_the_accessibility_tree",
    "D3",
    _the_header_row_leaves_the_screen_and_stays_in_the_tree,
)
RULE_NO_CELL_HIDDEN_FOR_BEING_EMPTY = _rule(
    "the_narrow_viewport_hides_no_cell_on_the_ground_that_it_is_empty",
    "D3",
    _no_cell_is_hidden_for_being_empty,
)
RULE_ROW_LABEL_CAP_SCOPED = _rule(
    "the_row_label_cap_is_scoped_to_the_wide_viewport",
    "F7",
    _the_row_label_cap_is_scoped_to_the_wide_viewport,
)
RULE_LEAD_HAS_ROOM = _rule(
    "the_lead_has_room_between_its_lines", "D4", _the_lead_has_room_between_its_lines
)
RULE_REFUSAL_NOT_CRAMPED = _rule(
    "a_refusal_block_is_not_cramped_against_its_own_edge", "D6", _a_refusal_block_is_not_cramped
)

#: Every extracted grep, in the order its test appears in ``test_site_viewport_S456.py``.
#: The negative control asserts this tuple names every ``StylesheetRule`` this module
#: defines, so a rule cannot be extracted and then quietly left out of the blind set.
S456_RULES: tuple[StylesheetRule, ...] = (
    RULE_DL_IS_ONE_COLUMN,
    RULE_SINGLE_TRACK_ZERO_FLOOR,
    RULE_CELLS_BREAK_WORDS,
    RULE_DEFINITION_RULE_PINNED,
    RULE_SYMPTOM_NOT_HIDDEN,
    RULE_STACKS_RECEIPTS_TABLE,
    RULE_STACKS_MEASUREMENTS_TABLE,
    RULE_STACKS_COST_TABLE,
    RULE_STACKED_LABEL_CARRIES_NO_COPY,
    RULE_HEADER_ROW_STAYS_IN_THE_TREE,
    RULE_NO_CELL_HIDDEN_FOR_BEING_EMPTY,
    RULE_ROW_LABEL_CAP_SCOPED,
    RULE_LEAD_HAS_ROOM,
    RULE_REFUSAL_NOT_CRAMPED,
)
