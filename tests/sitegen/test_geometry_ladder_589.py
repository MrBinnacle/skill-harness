"""The width ladder, which is the only piece of real policy in the geometry module.

Pure unit tests. No browser, no server, no built site: ``width_ladder`` takes
stylesheet text and returns integers, so these run in any environment the rest of the
suite runs in, and they run first. Everything a later failure message prints about the
ladder is a measured thing rather than a literal because of what is asserted here.

Every assertion is about the ladder's SHAPE and MEMBERSHIP, never a pasted list of
every rung. A stylesheet that gains a breakpoint should add rungs to this ladder
without reddening a test that had no opinion about that breakpoint.
"""

from __future__ import annotations

import pytest

from skill_harness.sitegen.geometry import (
    DEFAULT_LADDER_HI,
    DEFAULT_LADDER_LO,
    DEFAULT_LADDER_STEP,
    width_ladder,
)
from skill_harness.sitegen.render import read_stylesheet

_NO_BREAKPOINTS = ""


def test_the_coarse_sweep_covers_the_range_at_the_requested_step() -> None:
    """A stylesheet with no media query yields exactly the ReDeCheck sweep."""
    ladder = width_ladder(_NO_BREAKPOINTS, lo=320, hi=1400, step=60)

    assert ladder == tuple(range(320, 1401, 60))
    assert ladder[0] == 320
    assert ladder[-1] == 1400


def test_the_top_of_the_range_is_measured_even_when_the_step_misses_it() -> None:
    """``hi`` is a rung whether or not the step lands on it.

    320 + 70n never equals 1000, so a sweep built from ``range`` alone would stop at
    950 and never measure the widest width the caller asked about.
    """
    ladder = width_ladder(_NO_BREAKPOINTS, lo=320, hi=1000, step=70)

    assert 1000 % 70 != 320 % 70, "the fixture stopped exercising the off-grid case"
    assert ladder[-1] == 1000
    assert 950 in ladder
    assert all(320 <= rung <= 1000 for rung in ladder)


def test_a_breakpoint_contributes_its_own_width_and_both_of_its_edges() -> None:
    """The +/-1 probes are the point: a 60px grid lands on neither side of an edge."""
    ladder = width_ladder("@media (min-width: 810px) { a { color: red } }")

    assert 810 not in range(DEFAULT_LADDER_LO, DEFAULT_LADDER_HI + 1, DEFAULT_LADDER_STEP)
    assert {809, 810, 811} <= set(ladder)
    assert not any(806 <= rung <= 808 for rung in ladder)


def test_px_and_rem_breakpoints_are_both_parsed() -> None:
    """``rem`` is resolved at the CSS root size, so ``40rem`` is the 640px edge."""
    ladder = width_ladder(
        "@media (max-width: 40rem) { a { color: red } }\n"
        "@media (min-width: 900px) { b { color: red } }"
    )

    assert {639, 640, 641} <= set(ladder)
    assert {899, 900, 901} <= set(ladder)


def test_a_prelude_with_no_width_feature_contributes_nothing() -> None:
    """``prefers-reduced-motion`` is a real ``@media`` prelude and not a breakpoint."""
    css = "@media (prefers-reduced-motion: no-preference) { a { transition: none } }"

    assert width_ladder(css) == width_ladder(_NO_BREAKPOINTS)


def test_a_breakpoint_outside_the_range_is_dropped_whole() -> None:
    """Neighbours included. A 2000px edge outside a 1400px ceiling adds no 1999 rung,
    and a 100px edge below a 320px floor adds no 101."""
    css = (
        "@media (min-width: 2000px) { a { color: red } }\n"
        "@media (max-width: 100px) { b { color: red } }"
    )
    ladder = width_ladder(css)

    assert ladder == width_ladder(_NO_BREAKPOINTS)
    assert all(DEFAULT_LADDER_LO <= rung <= DEFAULT_LADDER_HI for rung in ladder)


def test_an_edge_probe_is_the_one_rung_allowed_outside_the_range() -> None:
    """A breakpoint sitting on an endpoint still gets both sides of its edge measured.

    Clamping one neighbour away would measure half a transition and report it as a
    whole one. The ladder is still sorted and still carries no duplicate: 640 is both
    the coarse sweep's only rung here and the parsed breakpoint.
    """
    ladder = width_ladder("@media (max-width: 40rem) { a { color: red } }", lo=640, hi=640)

    assert ladder == (639, 640, 641)
    assert len(set(ladder)) == len(ladder)


def test_a_non_positive_step_is_refused() -> None:
    with pytest.raises(ValueError, match="step must be positive"):
        width_ladder(_NO_BREAKPOINTS, step=0)


def test_an_inverted_range_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be below"):
        width_ladder(_NO_BREAKPOINTS, lo=1400, hi=320)


def test_this_repositorys_own_stylesheet_puts_both_edges_of_40rem_on_the_ladder() -> None:
    """The one test that reads the real ``src/skill_harness/sitegen/style.css``.

    ``@media (max-width: 40rem)`` is the breakpoint five of this site's seven pages
    depend on, so 639, 640 and 641 are the three widths a coarse sweep would miss and
    the three a regression would hide behind. ``64rem`` is asserted the same way. The
    assertions are memberships, so a stylesheet that grows a breakpoint grows the
    ladder without reddening anything here.
    """
    ladder = width_ladder(read_stylesheet())
    rungs = set(ladder)

    assert {639, 640, 641} <= rungs
    assert {1023, 1024, 1025} <= rungs
    assert set(range(DEFAULT_LADDER_LO, DEFAULT_LADDER_HI + 1, DEFAULT_LADDER_STEP)) <= rungs
    assert ladder == tuple(sorted(rungs))
    assert len(ladder) > len(range(DEFAULT_LADDER_LO, DEFAULT_LADDER_HI + 1, DEFAULT_LADDER_STEP))
