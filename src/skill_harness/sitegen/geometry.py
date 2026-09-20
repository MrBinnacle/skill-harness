"""The width ladder for the rendered-geometry harness (#589).

The stylesheet greps in ``tests/sitegen/test_site_viewport_S456.py`` cannot see a
rendered page. They read ``style.css`` as text. Replacing them with a real browser
measurement starts here, with the one piece of that measurement which is published
methodology rather than plumbing: which widths to measure at.

``width_ladder`` is pure. It takes stylesheet text and returns integers, so it is
unit-testable with no browser installed and no site built. The browser half lands on
top of it.
"""

from __future__ import annotations

import re

__all__ = ["width_ladder"]

DEFAULT_LADDER_LO = 320
DEFAULT_LADDER_HI = 1400
DEFAULT_LADDER_STEP = 60  # ReDeCheck (Walsh et al., ISSTA 2017)

#: CSS defines ``1rem`` as the root font size, and this stylesheet never changes it.
_REM_PX = 16


# ---------------------------------------------------------------------------
# The ladder: the one piece of real policy, and it is pure
# ---------------------------------------------------------------------------

_MEDIA_PRELUDE = re.compile(r"@media([^{]*)\{")
_MEDIA_WIDTH = re.compile(r"\b(?:min|max)-width\s*:\s*(\d+(?:\.\d+)?)\s*(px|rem)\b")


def width_ladder(
    stylesheet: str,
    *,
    lo: int = DEFAULT_LADDER_LO,
    hi: int = DEFAULT_LADDER_HI,
    step: int = DEFAULT_LADDER_STEP,
) -> tuple[int, ...]:
    """The widths to measure at: a coarse sweep augmented with the page's own breakpoints.

    Pure. No browser, no I/O.

    ReDeCheck samples 320-1400 at a 60px step AND augments with the breakpoint widths
    parsed out of the page's own CSS. The augmentation is what makes a 60px step
    defensible; a reimplementation that drops it is not the same technique, so dropping
    it here would be a silent methodology change.

    Each parsed breakpoint contributes three rungs: the breakpoint and both its
    neighbours. The ``+/-1`` probes matter more than the rung itself, because a
    ``max-width: 40rem`` block is active at 640 and inactive at 641 and the 60px grid
    lands on neither. Those two neighbours are the only rungs allowed outside
    ``[lo, hi]``: a breakpoint sitting exactly on an endpoint still gets both sides of
    its edge probed, because clamping one away would measure only half the transition.

    A prelude carrying no width feature -- ``prefers-reduced-motion``,
    ``prefers-color-scheme`` -- contributes nothing. A breakpoint outside ``[lo, hi]``
    is dropped whole, neighbours included.
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    if hi < lo:
        raise ValueError(f"hi ({hi}) must not be below lo ({lo})")
    rungs = set(range(lo, hi + 1, step))
    rungs.add(hi)
    for prelude in _MEDIA_PRELUDE.findall(stylesheet):
        for raw, unit in _MEDIA_WIDTH.findall(prelude):
            value = float(raw)
            edge = int(value) if unit == "px" else round(value * _REM_PX)
            if lo <= edge <= hi:
                rungs.update((edge - 1, edge, edge + 1))
    return tuple(sorted(rungs))
