"""The published site, measured in a real browser, and the two controls (#589).

``tests/sitegen/test_site_viewport_S456.py`` reads ``style.css`` as text. It cannot see a
rendered page, and this file is the measurement it stands in for: every page of a real
build, read in Chromium at every width of a ladder derived from the stylesheet's own
breakpoints.

The two controls below are why the file exists rather than what it does incidentally.
The positive control sabotages a second build's stylesheet and asserts the browser sees
the break. The negative control runs all fourteen S456 greps over that same sabotaged
text and asserts the override changes not one of their verdicts. Together they are the
ticket's whole argument, executable: the greps are blind to a break the browser sees.

Neither control is an ``xfail``. A control that passes whether or not it reddens is the
exact defect class this ticket is about.

These tests run on one CI cell. Everywhere else they skip, and the skip says so.
"""

from __future__ import annotations

import pytest

from skill_harness.sitegen.geometry import GeometryReport, PageReading, UnreadablePage
from skill_harness.sitegen.render import read_stylesheet
from tests.sitegen import _s456_rules
from tests.sitegen._s456_rules import S456_RULES, StylesheetRule
from tests.sitegen._sites import expected_page_names, sabotaged_stylesheet


def _measured(report: GeometryReport, page_name: str) -> PageReading:
    """The page's reading, or a failure carrying the typed refusal's own reason."""
    result = report.result_for(page_name)
    if isinstance(result, UnreadablePage):
        pytest.fail(result.explain())
    return result


def test_a_page_never_protrudes_past_its_viewport(
    geometry_report: GeometryReport, page_name: str
) -> None:
    """No page scrolls sideways, and no text run is painted past the edge.

    Parametrized per PAGE and not per (page, width), so one defect produces one red line.
    The ladder's widths live in the failure message as a band with a bisected onset.
    """
    reading = _measured(geometry_report, page_name)

    # The bool is taken first on purpose. Asserting on the tuple itself makes pytest's
    # assertion rewriting print every Overflow's repr underneath the message, which is
    # several thousand characters of dataclass and buries the block explain() built.
    protrudes = bool(reading.overflows)

    assert not protrudes, reading.explain()


def test_the_measured_page_set_is_the_built_page_set(geometry_report: GeometryReport) -> None:
    """The parametrized page list is DERIVED, so the derivation is checked.

    ``expected_page_names`` predicts the build from the receipts directory and
    ``render.py``'s naming policy, because the site cannot exist at collection time. This
    reddens the moment a build emits a page that prediction does not contain, or the
    reverse. It is enumeration and never a count: seven pages today without a landing
    page and eight with one, and neither number is written anywhere.
    """
    assert geometry_report.page_names() == expected_page_names()


def test_the_cascade_override_is_seen_by_the_browser(sabotaged_report: GeometryReport) -> None:
    """Positive control. The detector is not dead.

    A plain assertion and deliberately not ``xfail(strict=False)``, which passes whether
    the control reddens or not and would reproduce #589's defect class inside its fix.

    ``readings()`` excludes the typed refusals, so a sabotaged build whose stylesheet
    failed to load cannot be mistaken for a detected break: it would leave this list
    empty and redden here.
    """
    broken = [reading for reading in sabotaged_report.readings() if reading.overflows]

    assert broken, sabotaged_report.explain()


def test_the_cascade_override_is_invisible_to_every_stylesheet_grep() -> None:
    """Negative control, and it is the reason the browser layer exists.

    Every one of the fourteen S456 predicates returns the SAME verdict on the sabotaged
    stylesheet as on the clean one. Both texts come from one function, so this is a claim
    about one stylesheet rather than about two assumed to agree.

    Needs no browser and no fixture, so the blindness is asserted on every cell rather
    than only the designated one. Its sibling, the positive control, skips everywhere but
    the designated cell, so the two do not always run together.

    If somebody later strengthens a grep enough to catch the override, this reddens and a
    maintainer decides whether the sabotage string is still the right control. That is
    the correct outcome. A control that silently stops being a control is the failure
    mode this whole ticket is about.
    """
    extracted = {
        value.name for value in vars(_s456_rules).values() if isinstance(value, StylesheetRule)
    }
    assert extracted == {rule.name for rule in S456_RULES}, (
        "a rule was extracted but left out of S456_RULES; the blind set is no longer the "
        "grep set, so this control covers less than the suite it speaks for"
    )

    clean = read_stylesheet()
    sabotaged = sabotaged_stylesheet()

    # Blindness is a DELTA, not a level. Asserting only that every rule holds on the
    # sabotaged text reddens when a rule is DELETED from style.css, and reports that a
    # grep noticed the override, which is false. Measured: removing one real rule failed
    # this test with exactly that message. So the clean verdicts are established first
    # and the claim is that the override changes none of them.
    before = {rule.name: rule.holds(clean) for rule in S456_RULES}
    after = {rule.name: rule.holds(sabotaged) for rule in S456_RULES}

    assert all(before.values()), (
        "a grep is already failing on the UNSABOTAGED stylesheet, so this control cannot "
        "speak about blindness until the suite it speaks for is green: "
        f"{sorted(name for name, held in before.items() if not held)}"
    )
    assert after == before, (
        "a stylesheet grep changed its verdict under the override, so it is no longer "
        "blind to it: "
        f"{sorted(name for name in before if before[name] != after[name])}"
    )
