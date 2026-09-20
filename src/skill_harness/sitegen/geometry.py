"""Rendered-geometry measurement for a built receipts site (#589).

The stylesheet greps in ``tests/sitegen/test_site_viewport_S456.py`` cannot see a
rendered page. They read ``style.css`` as text. A cascade override that leaves every
rule's text intact -- so every grep still matches -- breaks five of seven pages, worst
case a 867px scroll width inside a 360px viewport, and the suite stays green.

This module is the measurement those greps stand in for. One public call,
:func:`measure_site`, returns one typed table: every page of a built site, read in a
real browser at every width of a ladder derived from the page's own breakpoints. The
HTTP server, the Chromium lifecycle, the stylesheet-applied vacuity guard, the font
wait before every reading, the two overflow predicates, the attribution walk and the
onset bisection all sit behind that one name.

The browser measurement is only reproducible where the font stack is identical, so a
caller that runs it in CI runs it in exactly one cell and decides that skip above this
line, where the decision is visible. This module never skips: a missing browser is
:class:`BrowserNotInstalledError`.

To measure a site from the command line, which is what a failure message tells you to
run::

    pip install -e ".[dev,geometry]"
    python -m playwright install chromium
    python -m skill_harness.sitegen.geometry --site build/site --widths 320,640,641

``--json -`` writes the same :class:`GeometryReport` to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from skill_harness.sitegen.render import STYLESHEET_NAME, read_stylesheet

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from playwright.sync_api import Browser, Page

__all__ = [
    "BrowserNotInstalledError",
    "GeometryReport",
    "Instrument",
    "Offender",
    "Overflow",
    "PageReading",
    "PageResult",
    "UnreadablePage",
    "measure_site",
    "width_ladder",
]

#: The report's conventional filename beside the built site. ``explain()`` names it
#: only when the file is actually there, because a failure message that points at a
#: path nobody wrote is worse than no pointer.
REPORT_FILE_NAME = "geometry-report.json"

DEFAULT_LADDER_LO = 320
DEFAULT_LADDER_HI = 1400
DEFAULT_LADDER_STEP = 60  # ReDeCheck (Walsh et al., ISSTA 2017)

#: Not a parameter. Height is not inert -- a vertical scrollbar consumes layout width
#: on a build without overlay scrollbars, which is the 15 CSS px by which two Chrome
#: builds on this host disagree about a 360px viewport's ``clientWidth``. Pinning it is
#: reproducibility; hiding it keeps a knob off the public surface no caller would turn.
_VIEWPORT_HEIGHT = 900

#: Subpixel slack on both walks. A run painted 0.2px past the edge is a rounding
#: artifact; one painted 3px past it is a defect.
_INK_EPSILON_PX = 0.5

_FONT_BUDGET_MS = 5_000

#: How many box offenders the attribution walk carries back per width. The box walk
#: never gates, so an unbounded list buys nothing and can be thousands of entries on a
#: badly broken page.
_MAX_BOX_OFFENDERS = 25

#: CSS defines ``1rem`` as the root font size, and this stylesheet never changes it.
_REM_PX = 16

#: How many offenders the failure block PRINTS. The report carries the rest, and the
#: block exists so one defect produces one readable red line rather than a wall: a
#: measured sabotage puts twenty-two boxes past the edge on one page and the seventh
#: of them tells a maintainer nothing the first did not.
_PRINTED_OFFENDERS = 6

#: Failure-block geometry: the label column plus the width a wrapped body is folded to.
_BODY_INDENT = 21
_BODY_WIDTH = 76

_INSTALL_HINT = (
    "measuring rendered geometry requires the optional extra and its browser build: "
    'pip install "skill-harness[geometry]" && python -m playwright install chromium'
)


class BrowserNotInstalledError(RuntimeError):
    """Playwright or its Chromium build is missing (the optional ``[geometry]`` extra).

    Mirrors :class:`skill_harness.sitegen.SitegenNotInstalledError` exactly, including
    the lazy import behind a typed install hint, so a core install imports this module
    fine and fails at use time with an actionable message rather than at import time
    with a bare ImportError naming a package nobody asked for.
    """


# ---------------------------------------------------------------------------
# The types, and the invariants they carry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Offender:
    """One thing painted past the viewport's right edge.

    ``selector`` is a CSS path built in the page, unique enough to paste into devtools.
    ``text`` is the first 80 characters of an ink run and empty for a box.
    """

    kind: Literal["ink", "box"]
    selector: str
    right: float
    text: str

    def _as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "selector": self.selector,
            "right": self.right,
            "text": self.text,
        }


@dataclass(frozen=True)
class Overflow:
    """One width at which a page failed at least one of the two predicates.

    INVARIANT, enforced in ``__post_init__``: an Overflow exists only when
    ``scroll_width > client_width`` or ``ink_offenders`` is non-empty. A clean width
    produces no Overflow at all, so an empty ``overflows`` tuple means clean and cannot
    mean "we did not look".

    ``box_offenders`` is attribution and never a predicate. A ``position: fixed``
    decoration or a deliberately clipped element sits past the edge without being a
    defect, so a box walk cannot gate. It explains, it does not judge.
    """

    width: int
    scroll_width: int
    client_width: int
    ink_offenders: tuple[Offender, ...]
    box_offenders: tuple[Offender, ...]

    def __post_init__(self) -> None:
        if self.scroll_width <= self.client_width and not self.ink_offenders:
            raise ValueError(
                f"Overflow({self.width}px) carries neither predicate: scrollWidth "
                f"{self.scroll_width} <= clientWidth {self.client_width} and no ink "
                "offender. A clean width produces no Overflow at all."
            )

    @property
    def scroll_excess(self) -> int:
        """Derived, never stored, per single-source-of-truth.

        Zero for an ink-only overflow: text clipped by an ``overflow: hidden`` ancestor
        is unreadable without scrolling the page, so there is no excess to report.
        """
        return max(0, self.scroll_width - self.client_width)

    def _as_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "scroll_width": self.scroll_width,
            "client_width": self.client_width,
            "scroll_excess": self.scroll_excess,
            "ink_offenders": [o._as_dict() for o in self.ink_offenders],
            "box_offenders": [o._as_dict() for o in self.box_offenders],
        }


@dataclass(frozen=True)
class Instrument:
    """What the reading was taken with. Every field is observed, none is assumed.

    ``fonts_loaded`` is ``document.fonts.size`` and it is honestly 0 on a healthy page
    of this site: ``style.css`` declares no ``@font-face`` and the templates load no
    webfont, so the face count discriminates nothing here. ``stylesheet_rules`` is what
    does: a styled document reports 65 rules and an unstyled one reports 0. Both are
    recorded because both were read.
    """

    browser_version: str
    device_scale_factor: float
    viewport_height: int
    fonts_loaded: int
    stylesheet_rules: int
    body_font_family: str

    def _as_dict(self) -> dict[str, Any]:
        return {
            "browser_version": self.browser_version,
            "device_scale_factor": self.device_scale_factor,
            "viewport_height": self.viewport_height,
            "fonts_loaded": self.fonts_loaded,
            "stylesheet_rules": self.stylesheet_rules,
            "body_font_family": self.body_font_family,
        }

    def summary(self) -> str:
        """The failure message's instrument line, so a maintainer can tell a broken
        page from a broken harness without reading code."""
        return (
            f"Chromium {self.browser_version}, device scale "
            f"{self.device_scale_factor:g}, viewport height {self.viewport_height}, "
            f"fonts ready, {self.fonts_loaded} faces loaded, "
            f"{self.stylesheet_rules} stylesheet rules, computed body font-family "
            f"{self.body_font_family!r}"
        )


@dataclass(frozen=True)
class PageReading:
    """A page that was successfully read at every width in the ladder.

    INVARIANT by construction: this type exists only for a page whose stylesheet
    demonstrably applied. A page that failed that check is an :class:`UnreadablePage`,
    not a PageReading with a flag set false. That is deliberate: a missing
    ``style.css`` makes ``scrollWidth <= clientWidth`` trivially true, so "the CSS did
    not load" must not be representable as a clean reading.

    ``site_dir`` is carried so ``explain()`` can print the reproduce command. The
    temporary site is deleted by the time anyone reads a CI log, and that command is
    the most useful line in the message.
    """

    page: str
    site_dir: Path
    widths: tuple[int, ...]
    overflows: tuple[Overflow, ...]
    onset: int | None
    instrument: Instrument

    @property
    def bands(self) -> tuple[tuple[int, int], ...]:
        """Contiguous runs of overflowing widths, derived from ``overflows``.

        A tuple of runs, not one run. Contiguity is measured in ladder positions, not
        in pixels: two adjacent rungs 60px apart are one run. Nothing here assumes
        monotonicity; the report just gets longer when it does not hold.
        """
        position = {width: index for index, width in enumerate(self.widths)}
        broken = sorted((position[o.width], o.width) for o in self.overflows)
        runs: list[tuple[int, int]] = []
        for index, (slot, width) in enumerate(broken):
            if index and slot == broken[index - 1][0] + 1:
                runs[-1] = (runs[-1][0], width)
            else:
                runs.append((width, width))
        return tuple(runs)

    def explain(self) -> str:
        """The failure block this module exists to print."""
        if not self.overflows:
            return (
                f"{self.page} is clean at every one of {len(self.widths)} widths "
                f"({self.instrument.summary()})."
            )
        worst = min(self.overflows, key=lambda o: (-o.scroll_excess, o.width))
        lines = [f"{self.page} protrudes past its viewport.", ""]
        lines.append(_row("overflowing", f"{self._band_text()}   {self._onset_text()}", wrap=False))
        lines.append(_row("ladder", self._ladder_text()))
        lines.append(
            _row(
                "worst",
                f"at {worst.width}px: scrollWidth {worst.scroll_width} vs "
                f"clientWidth {worst.client_width}, excess {worst.scroll_excess}",
            )
        )
        if worst.ink_offenders:
            lines.append("")
            lines.append(
                f"  ink past the edge at {worst.width}px "
                "(a run of text painted outside the viewport):"
            )
            for offender in worst.ink_offenders[:_PRINTED_OFFENDERS]:
                lines.append(f"    right {offender.right:8.2f}   {offender.selector}")
                lines.append(f"{' ' * _BODY_INDENT}{offender.text!r}")
            lines.extend(_and_more(len(worst.ink_offenders), "ink run", "ink runs"))
        if worst.box_offenders:
            lines.append("")
            lines.append(
                f"  boxes past the edge at {worst.width}px, worst first "
                "(attribution only, never the predicate):"
            )
            for offender in worst.box_offenders[:_PRINTED_OFFENDERS]:
                lines.append(f"    right {offender.right:8.2f}   {offender.selector}")
            lines.extend(_and_more(len(worst.box_offenders), "box", "boxes"))
        lines.append("")
        lines.append(_row("instrument", self.instrument.summary()))
        lines.append(
            _row("reproduce", _reproduce(self.site_dir, self.page, worst.width), wrap=False)
        )
        table = self.site_dir / REPORT_FILE_NAME
        if table.is_file():
            lines.append(_row("full table", str(table), wrap=False))
        return "\n".join(lines)

    def _band_text(self) -> str:
        bands = self.bands
        spans: list[str] = []
        for index, (low, high) in enumerate(bands):
            last = index == len(bands) - 1
            edge = self.onset if last and self.onset is not None else high
            spans.append(f"{low}px" if low == edge else f"{low}px-{edge}px")
        return ", ".join(spans)

    def _onset_text(self) -> str:
        if self.onset is None:
            return "(the widest measured width already overflows; the onset is at or above it)"
        return f"(onset bisected: clean at {self.onset + 1}, broken at {self.onset})"

    def _ladder_text(self) -> str:
        rungs = " ".join(str(width) for width in self.widths)
        return (
            f"{rungs}   ({len(self.widths)} rungs; each parsed breakpoint is flanked "
            "by its own +/-1 probes)"
        )

    def _as_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "measured": True,
            "widths": list(self.widths),
            "onset": self.onset,
            "bands": [list(band) for band in self.bands],
            "instrument": self.instrument._as_dict(),
            "overflows": [o._as_dict() for o in self.overflows],
        }


@dataclass(frozen=True)
class UnreadablePage:
    """A typed refusal. The page could not be measured and no number is invented.

    ``reason`` is one of a closed set, spelled out rather than coded so the message is
    the message: the navigation failed, the loaded document reports no CSS rules, the
    computed body font-family does not match the stylesheet's, the rule count could not
    be read at all, or ``document.fonts.ready`` did not settle inside the budget.
    """

    page: str
    reason: str

    def explain(self) -> str:
        return f"{self.page} could not be measured: {self.reason}"

    def _as_dict(self) -> dict[str, Any]:
        return {"page": self.page, "measured": False, "reason": self.reason}


PageResult = PageReading | UnreadablePage


@dataclass(frozen=True)
class GeometryReport:
    """Every page of one built site, measured across one width ladder, once."""

    site_dir: Path
    ladder: tuple[int, ...]
    results: tuple[PageResult, ...]
    _index: dict[str, PageResult] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for result in self.results:
            if result.page in self._index:
                raise ValueError(f"two results name page {result.page!r}")
            self._index[result.page] = result

    def page_names(self) -> tuple[str, ...]:
        return tuple(result.page for result in self.results)

    def result_for(self, page: str) -> PageResult:
        try:
            return self._index[page]
        except KeyError:
            raise KeyError(
                f"{page!r} was not measured; this report covers "
                f"{', '.join(self.page_names()) or '(nothing)'}"
            ) from None

    def readings(self) -> tuple[PageReading, ...]:
        """Only the pages that were measured.

        Callers that need the refusals ask for ``results``; this exists so a control
        can say "something broke" without an unreadable page counting as a break.
        """
        return tuple(r for r in self.results if isinstance(r, PageReading))

    def refusals(self) -> tuple[UnreadablePage, ...]:
        """Only the pages that could not be read."""
        return tuple(r for r in self.results if isinstance(r, UnreadablePage))

    def to_json(self) -> str:
        """Serialize the whole table. Needs no browser, which is what lets the JSON
        artifact be read on a machine that has none."""
        payload = {
            "site_dir": str(self.site_dir),
            "ladder": list(self.ladder),
            "results": [result._as_dict() for result in self.results],
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def explain(self) -> str:
        broken = [r for r in self.readings() if r.overflows]
        blocks = [r.explain() for r in broken] + [r.explain() for r in self.refusals()]
        header = (
            f"{_count(len(self.results), 'page', 'pages')} measured across "
            f"{_count(len(self.ladder), 'width', 'widths')} under {self.site_dir}: "
            f"{len(broken)} overflowing, {len(self.refusals())} unreadable."
        )
        if not blocks:
            return header
        return header + "\n\n" + "\n\n".join(blocks)


def _row(label: str, body: str, *, wrap: bool = True) -> str:
    """One ``label   body`` line of a failure block, with continuations aligned.

    ``wrap=False`` for a body whose own line breaks carry meaning -- a shell command
    with a trailing backslash, a path that must stay one copyable token.
    """
    text = "\n".join(textwrap.wrap(body, width=_BODY_WIDTH)) if wrap else body
    return f"  {label:<18} " + text.replace("\n", "\n" + " " * _BODY_INDENT)


def _count(number: int, singular: str, plural: str) -> str:
    """``1 page`` / ``7 pages``. Used everywhere a count reaches a human."""
    return f"{number} {singular if number == 1 else plural}"


def _and_more(total: int, singular: str, plural: str) -> list[str]:
    """The line that admits the failure block is showing only the worst few."""
    hidden = total - _PRINTED_OFFENDERS
    if hidden <= 0:
        return []
    return [
        f"    ... and {_count(hidden, singular, plural)} more; the full list is in the JSON table"
    ]


def _reproduce(site_dir: Path, page: str, width: int) -> str:
    return (
        "python -m skill_harness.sitegen.geometry \\\n"
        f"  --site {site_dir} --page {page} --widths {width}"
    )


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


# ---------------------------------------------------------------------------
# The instrument
# ---------------------------------------------------------------------------


def measure_site(
    site_dir: Path,
    *,
    widths: Sequence[int],
    pages: Sequence[str] | None = None,
) -> GeometryReport:
    """Measure every page of a built site at every width. One call, one table.

    ``pages`` defaults to every ``*.html`` under ``site_dir``, ENUMERATED rather than
    counted: a default build emits seven pages and a ``landing=True`` build emits
    eight, so a pinned count is a latent false failure.

    Raises :class:`BrowserNotInstalledError` if Playwright or its Chromium build is
    absent. It does not skip and it does not return an empty report. A caller that
    wants a skip decides that itself, above this line, where the decision is visible.

    What this hides from the caller: an ephemeral-port static HTTP server over
    ``site_dir``; a Chromium launch and a single browser context pinned to device scale
    1, light colour scheme and reduced motion; per-page navigation and a
    stylesheet-applied probe; a font-readiness wait before every single reading; a
    resize-and-settle loop across the ladder; two independent overflow predicates; a
    bisection between adjacent rungs to find the exact onset; and the teardown of all
    of it on any exception. The caller sees a directory, a list of integers and a table.
    """
    if not site_dir.is_dir():
        raise FileNotFoundError(f"no built site at {site_dir}")
    ladder = tuple(int(width) for width in widths)
    if not ladder:
        raise ValueError("measure_site needs at least one width")
    if any(width <= 0 for width in ladder):
        raise ValueError(f"every width must be positive, got {ladder}")
    names = list(pages) if pages is not None else sorted(p.name for p in site_dir.glob("*.html"))
    expected_family = _declared_body_font_family(read_stylesheet())

    results: list[PageResult] = []
    with _serve(site_dir) as base_url, _chromium() as browser:
        context = browser.new_context(
            viewport={"width": ladder[0], "height": _VIEWPORT_HEIGHT},
            device_scale_factor=1,
            color_scheme="light",
            reduced_motion="reduce",
        )
        try:
            for name in names:
                page = context.new_page()
                try:
                    results.append(
                        _measure_page(
                            page,
                            base_url=base_url,
                            name=name,
                            site_dir=site_dir,
                            ladder=ladder,
                            browser_version=browser.version,
                            expected_family=expected_family,
                        )
                    )
                finally:
                    page.close()
        finally:
            context.close()
    return GeometryReport(site_dir=site_dir, ladder=ladder, results=tuple(results))


def _measure_page(
    page: Page,
    *,
    base_url: str,
    name: str,
    site_dir: Path,
    ladder: tuple[int, ...],
    browser_version: str,
    expected_family: str,
) -> PageResult:
    """One page: navigate once, resize across the ladder, bisect the onset if it broke.

    Navigation happens ONCE per page and the viewport is resized across the ladder:
    seven navigations rather than seven times twenty-four. Safe here because these
    pages are static with no script; a page with viewport-dependent JS would need the
    re-navigation, and this comment is where that is decided.
    """
    response = page.goto(f"{base_url}/{name}", wait_until="load")
    if response is None:
        return UnreadablePage(page=name, reason=f"navigation to {name} returned no response")
    if not response.ok:
        return UnreadablePage(
            page=name, reason=f"navigation to {name} returned HTTP {response.status}"
        )
    probe = _style_probe(page, expected_family, browser_version)
    if isinstance(probe, str):
        return UnreadablePage(page=name, reason=probe)

    overflows: list[Overflow] = []
    for width in ladder:
        overflow = _measure_at(page, width)
        if overflow is not None:
            overflows.append(overflow)
    onset = _bisect_onset(page, ladder, overflows) if overflows else None
    return PageReading(
        page=name,
        site_dir=site_dir,
        widths=ladder,
        overflows=tuple(overflows),
        onset=onset,
        instrument=probe,
    )


def _measure_at(page: Page, width: int) -> Overflow | None:
    """Resize, settle, read. The single place a reading is ever taken."""
    page.set_viewport_size({"width": width, "height": _VIEWPORT_HEIGHT})
    _settle(page)
    reading = _evaluate_mapping(
        page, _PROBE_JS, {"eps": _INK_EPSILON_PX, "maxBoxes": _MAX_BOX_OFFENDERS}
    )
    scroll_width = _as_int(reading.get("scrollWidth"))
    client_width = _as_int(reading.get("clientWidth"))
    ink = _offenders(reading.get("ink"), "ink")
    box = _offenders(reading.get("box"), "box")
    if scroll_width <= client_width and not ink:
        return None
    return Overflow(
        width=width,
        scroll_width=scroll_width,
        client_width=client_width,
        ink_offenders=ink,
        box_offenders=box,
    )


def _bisect_onset(page: Page, ladder: Sequence[int], overflows: Sequence[Overflow]) -> int | None:
    """The exact widest width at which the page still breaks.

    ReDeCheck binary-searches between adjacent sampled widths whenever the layout
    changes across them; this is that step, narrowed to the one transition a maintainer
    cares about. The transition is the edge of the broken range nearest the clean side:
    a page that protrudes at 320 and is fine at 1400 has its onset somewhere between
    the widest broken rung and the narrowest clean rung above it, and a band reported
    as "320px-1078px, clean at 1079" is the artifact this produces.

    Costs about six extra readings and only when something already failed, so a clean
    run pays nothing.

    Returns None when the widest measured width already overflows: the onset is then at
    or above the top of the measured range and the report says so rather than claiming
    a number the ladder never reached.
    """
    if not overflows:
        return None
    broken = {o.width for o in overflows}
    widest_broken = max(broken)
    clean_above = [width for width in ladder if width > widest_broken]
    if not clean_above:
        return None
    hi_clean = min(clean_above)
    lo_broken = widest_broken
    while hi_clean - lo_broken > 1:
        mid = (lo_broken + hi_clean) // 2
        if _measure_at(page, mid) is not None:
            lo_broken = mid
        else:
            hi_clean = mid
    return lo_broken


# ---------------------------------------------------------------------------
# The vacuity guard
# ---------------------------------------------------------------------------

_BODY_RULE = re.compile(r"(?:^|[{}])\s*body\s*\{([^}]*)\}", re.MULTILINE)
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)")


def _declared_body_font_family(stylesheet: str) -> str:
    """The first family named by the stylesheet's own top-level ``body`` rule.

    Parsed rather than hardcoded. The guard below asks whether the computed body
    font-family starts with this string, so writing ``-apple-system`` into the module
    would make the guard a claim about this stylesheet's present contents rather than
    about whether the stylesheet applied.
    """
    text = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    for body in _BODY_RULE.findall(text):
        declaration = _FONT_FAMILY.search(body)
        if declaration is not None:
            first = declaration.group(1).split(",")[0].strip()
            return first.strip("\"'")
    raise ValueError("the stylesheet's body rule declares no font-family to probe against")


_STYLE_PROBE_JS = """
(args) => {
  const settled = Promise.race([
    document.fonts.ready.then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), args.budget)),
  ]);
  return settled.then((fontsReady) => {
    let rules = null;
    let rulesError = null;
    try {
      const sheets = Array.prototype.slice.call(document.styleSheets);
      const own = sheets.filter((s) => (s.href || '').endsWith(args.stylesheet));
      const sheet = own.length ? own[0] : sheets[0];
      rules = sheet ? sheet.cssRules.length : 0;
    } catch (err) {
      rulesError = String((err && err.message) || err);
    }
    return {
      fontsReady: fontsReady,
      family: getComputedStyle(document.body).fontFamily,
      faces: document.fonts ? document.fonts.size : 0,
      rules: rules,
      rulesError: rulesError,
      scale: window.devicePixelRatio,
      height: window.innerHeight,
    };
  });
}
"""


def _style_probe(page: Page, expected_family: str, browser_version: str) -> Instrument | str:
    """Prove the stylesheet applied, or say why not.

    This is the vacuity guard and it is the most load-bearing private function here. If
    ``style.css`` 404s, the page renders unstyled, nothing is wider than the viewport,
    and ``scrollWidth <= clientWidth`` passes. A green suite would then mean "the CSS is
    missing", which is the exact failure the harness exists to catch.

    The two clauses below are the ones measured to discriminate on this site. Chromium
    153.0.8010.12 against a real build reported ``document.fonts.size`` as 0 both
    styled and unstyled -- ``style.css`` declares no ``@font-face`` and the templates
    load no webfont -- so a face-count guard would have refused every healthy page.
    What separated the two readings was the computed body font-family
    (``-apple-system, ...`` against ``"Times New Roman"``) and the loaded document's
    rule count (65 against 0). The face count is still recorded on
    :class:`Instrument`, because it was observed; it just does not gate.

    Reading ``cssRules`` throws on a cross-origin sheet. Everything here is
    same-origin, so the throw is caught in the page and reported as a refusal reason
    rather than escaping as an uncaught error.
    """
    probe = _evaluate_mapping(
        page, _STYLE_PROBE_JS, {"budget": _FONT_BUDGET_MS, "stylesheet": STYLESHEET_NAME}
    )
    if not _as_bool(probe.get("fontsReady")):
        return f"document.fonts.ready did not settle within {_FONT_BUDGET_MS}ms"
    rules_error = probe.get("rulesError")
    if rules_error is not None:
        return f"the loaded document's CSS rules could not be read: {_as_str(rules_error)}"
    rules = _as_int(probe.get("rules"))
    family = _as_str(probe.get("family"))
    if rules == 0:
        return (
            f"{STYLESHEET_NAME} did not apply: the loaded document reports 0 CSS rules "
            f"(computed body font-family is {family!r})"
        )
    if not family.strip().strip("\"'").startswith(expected_family):
        return (
            f"{STYLESHEET_NAME} did not apply: computed body font-family is {family!r}, "
            f"expected it to start with {expected_family!r}"
        )
    return Instrument(
        browser_version=browser_version,
        device_scale_factor=_as_float(probe.get("scale")),
        viewport_height=_as_int(probe.get("height")),
        fonts_loaded=_as_int(probe.get("faces")),
        stylesheet_rules=rules,
        body_font_family=family,
    )


_SETTLE_JS = """
(budget) => Promise.race([
  document.fonts.ready.then(() => true),
  new Promise((resolve) => setTimeout(() => resolve(false), budget)),
]).then(() => new Promise((resolve) => {
  requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
}))
"""


def _settle(page: Page) -> None:
    """Wait for fonts and let layout quiesce, before EVERY reading.

    Not once per page. The design/port-field-manual trail records a second defect that
    appeared "at 75px once the real faces loaded", so a reading taken before the real
    faces are in is a reading of a different page. The font wait is raced against
    ``_FONT_BUDGET_MS`` so a stalled ``fonts.ready`` cannot hang the run; the budget
    itself is already a refusal at probe time, so it is not re-reported here.
    """
    page.evaluate(_SETTLE_JS, _FONT_BUDGET_MS)


_PROBE_JS = """
(args) => {
  // Two independent predicates and one attribution walk.
  //
  // P1  document.documentElement.scrollWidth <= clientWidth
  //     Scrollbar-independent by construction, which is why it and not a nominal 360
  //     is the predicate: two Chrome builds on the author's own host disagree by 15
  //     CSS px about what a 360px viewport's clientWidth is.
  //
  // P2  no text run painted past clientWidth (+ eps)
  //     P1 alone misses ink clipped by an `overflow: hidden` ancestor, which is
  //     unreadable text that does not scroll the page. Range.getClientRects over
  //     every text node is what found the h1 run at right 363.22 in a 345px viewport
  //     where no element box was over the limit.
  //
  // BOX walk: getBoundingClientRect over body *, right > limit. Reported, never
  // asserted on -- see Overflow.box_offenders.
  const doc = document.documentElement;
  const clientWidth = doc.clientWidth;
  const limit = clientWidth + args.eps;

  // tag + :nth-of-type chain up to body, built in-page so the selector in the failure
  // message is one a maintainer can paste into devtools.
  const cssPath = (start) => {
    let el = start;
    if (el && el.nodeType !== 1) el = el.parentElement;
    const parts = [];
    while (el && el.nodeType === 1) {
      const tag = el.tagName.toLowerCase();
      const parent = el.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      const kin = Array.prototype.filter.call(
        parent.children, (c) => c.tagName === el.tagName);
      const nth = kin.indexOf(el) + 1;
      parts.unshift(kin.length > 1 ? tag + ':nth-of-type(' + nth + ')' : tag);
      if (el === document.body) break;
      el = parent;
    }
    return parts.join(' > ');
  };

  const ink = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const value = node.nodeValue || '';
    if (value.trim() === '') continue;
    range.selectNodeContents(node);
    const rects = range.getClientRects();
    let worst = null;
    for (let i = 0; i < rects.length; i++) {
      const right = rects[i].right;
      if (right > limit && (worst === null || right > worst)) worst = right;
    }
    if (worst !== null) {
      ink.push({
        kind: 'ink',
        selector: cssPath(node.parentElement),
        right: worst,
        text: value.trim().slice(0, 80),
      });
    }
  }
  ink.sort((a, b) => b.right - a.right);

  const box = [];
  const all = document.body.querySelectorAll('*');
  for (let i = 0; i < all.length; i++) {
    const rect = all[i].getBoundingClientRect();
    if (rect.width > 0 && rect.right > limit) {
      box.push({ kind: 'box', selector: cssPath(all[i]), right: rect.right, text: '' });
    }
  }
  box.sort((a, b) => b.right - a.right);

  return {
    scrollWidth: doc.scrollWidth,
    clientWidth: clientWidth,
    ink: ink,
    box: box.slice(0, args.maxBoxes),
  };
}
"""


# ---------------------------------------------------------------------------
# The browser and the server
# ---------------------------------------------------------------------------


@contextmanager
def _chromium() -> Iterator[Browser]:
    """A headless Chromium, or a typed refusal naming the extra to install."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - core install without the extra
        raise BrowserNotInstalledError(_INSTALL_HINT) from exc
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on the host's browser cache
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise BrowserNotInstalledError(f"{_INSTALL_HINT}\n{message}") from exc
            raise
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def _serve(root: Path) -> Iterator[str]:
    """A ThreadingHTTPServer on ``('127.0.0.1', 0)`` over ``root``, yielding its base URL.

    Port 0 on purpose: every xdist worker that reaches this binds a distinct ephemeral
    port with no coordination, so the harness is correct under any distribution mode.
    ``--dist loadgroup`` makes it fast, not correct.

    The lifecycle is the repository's existing idiom, lifted from
    ``tests/test_release_gate_206.py`` -- ``serve_forever`` on a thread, then
    ``shutdown`` / ``join`` / ``server_close`` in a finally. Those call sites serve a
    mocked JSON API; this is the first to serve a directory. ``ThreadingHTTPServer``
    tracks its handler threads and joins them in ``server_close``, and this context
    manager is entered outside the browser's, so every connection is already gone by
    the time the socket closes. That ordering is what keeps a ResourceWarning out of
    the run rather than a warning filter.

    HTTP and not ``file://``. The prior-art probe used ``file://``, which resolves the
    stylesheet by a different path rule than the published site and gives no way to
    observe that the request returned 200.
    """
    directory = str(root)

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            """Silence the stderr access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, name="sitegen-geometry-http")
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


# ---------------------------------------------------------------------------
# Narrowing what the page hands back
# ---------------------------------------------------------------------------


def _evaluate_mapping(page: Page, script: str, arg: object) -> Mapping[str, Any]:
    result: object = page.evaluate(script, arg)
    if not isinstance(result, dict):
        raise TypeError(f"the in-page probe returned {type(result).__name__}, not an object")
    narrowed: dict[str, Any] = result
    return narrowed


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected a number from the page, got {value!r}")
    return int(value)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected a number from the page, got {value!r}")
    return float(value)


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected a string from the page, got {value!r}")
    return value


def _as_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"expected a boolean from the page, got {value!r}")
    return value


def _offenders(value: object, kind: Literal["ink", "box"]) -> tuple[Offender, ...]:
    if not isinstance(value, list):
        raise TypeError(f"expected a list of {kind} offenders from the page, got {value!r}")
    found: list[Offender] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise TypeError(f"expected an {kind} offender object, got {entry!r}")
        row: dict[str, Any] = entry
        found.append(
            Offender(
                kind=kind,
                selector=_as_str(row.get("selector")),
                right=_as_float(row.get("right")),
                text=_as_str(row.get("text")),
            )
        )
    return tuple(found)


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def _parse_widths(raw: str) -> tuple[int, ...]:
    widths: list[int] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        if not text.isdigit() or int(text) <= 0:
            raise argparse.ArgumentTypeError(f"--widths takes positive integers, got {text!r}")
        widths.append(int(text))
    if not widths:
        raise argparse.ArgumentTypeError("--widths needs at least one width")
    return tuple(widths)


def _table(report: GeometryReport) -> str:
    """The row-per-(page, width) table the design's Usage section shows."""
    width = max((len(name) for name in report.page_names()), default=0)
    lines: list[str] = []
    readings = 0
    overflowing = 0
    for result in report.results:
        if isinstance(result, UnreadablePage):
            lines.append(f"{result.page:<{width}}  UNREADABLE  {result.reason}")
            continue
        broken = {o.width: o for o in result.overflows}
        for rung in result.widths:
            readings += 1
            overflow = broken.get(rung)
            if overflow is None:
                lines.append(f"{result.page:<{width}}  {rung}px  clean")
                continue
            overflowing += 1
            lines.append(
                f"{result.page:<{width}}  {rung}px  scroll {overflow.scroll_width} vs "
                f"client {overflow.client_width}  excess {overflow.scroll_excess}   "
                f"INK {len(overflow.ink_offenders)}, BOX {len(overflow.box_offenders)}"
            )
    lines.append("")
    lines.append(
        f"{_count(len(report.results), 'page', 'pages')}, "
        f"{_count(len(report.ladder), 'width', 'widths')}, "
        f"{_count(readings, 'reading', 'readings')}, "
        f"{overflowing} overflowing, {len(report.refusals())} unreadable"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Measure a built site from the command line. Exit 1 if anything broke."""
    parser = argparse.ArgumentParser(
        prog="python -m skill_harness.sitegen.geometry",
        description="Measure a built receipts site's rendered geometry in a real browser.",
    )
    parser.add_argument("--site", required=True, type=Path, help="the built site directory")
    parser.add_argument(
        "--page",
        action="append",
        default=None,
        metavar="NAME",
        help="measure only this page; repeatable (default: every *.html in --site)",
    )
    parser.add_argument(
        "--widths",
        default=None,
        metavar="N,N,N",
        help="comma-separated widths (default: the ladder derived from style.css)",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        default=None,
        metavar="PATH",
        help="write the full report as JSON; '-' writes it to stdout instead of the table",
    )
    args = parser.parse_args(argv)
    site: Path = args.site
    pages: list[str] | None = args.page
    widths = _parse_widths(args.widths) if args.widths else width_ladder(read_stylesheet())

    report = measure_site(site, widths=widths, pages=pages)
    if args.json_out == "-":
        sys.stdout.write(report.to_json())
    else:
        print(_table(report))
        if args.json_out is not None:
            Path(args.json_out).write_text(report.to_json(), encoding="utf-8", newline="\n")
    broke = any(r.overflows for r in report.readings()) or bool(report.refusals())
    return 1 if broke else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
