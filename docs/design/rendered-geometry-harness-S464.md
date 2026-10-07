# Candidate: rendered-geometry harness (runner: Opus 5)

Target: `skill-harness#589`. Replaces the blind half of `tests/sitegen/test_site_viewport_S456.py`
with a real browser measurement, and re-types the greps it leaves behind as that measurement's
negative control.

The one-line shape: **a shipped measurement module in `src/` whose single public call returns one
typed table, and a test layer that owns only the assertions over it.** The browser, the server, the
font wait, the two detectors and the bisection all sit behind one function name.

---

## Usage (caller's view)

### The maintainer's quickstart

`docs/sitegen/rendered-geometry.md`, and the module docstring says the same:

> The stylesheet greps in `tests/sitegen/test_site_viewport_S456.py` cannot see a rendered page.
> They read `style.css` as text. A cascade override that leaves every rule's text intact — so every
> grep still matches — breaks five of seven pages, worst case a 867px scroll width inside a 360px
> viewport, and the suite stays green. That override is `SABOTAGE_CSS` in `tests/sitegen/_sites.py`
> and it is a standing test, not a story.
>
> The browser measurement runs in exactly one CI cell, because font fallback differs per platform
> and the reading is only reproducible where the font stack is identical. That cell is the one whose
> `env:` sets `SKILL_HARNESS_GEOMETRY_CELL: "1"`. Everywhere else these tests skip, and
> `tests/test_ci_geometry_cell_589.py` fails if the count of designated cells is ever anything but
> one — a skip nobody checks is how a control dies.
>
> To run them on your machine:
>
> ```
> pip install -e ".[dev,geometry]"
> python -m playwright install chromium
> SKILL_HARNESS_GEOMETRY_CELL=1 pytest tests/sitegen/test_rendered_geometry.py
> ```
>
> To reproduce one failure without pytest at all, the failure message prints the command.

### Call site 1 — the test layer (the whole of it)

```python
# tests/sitegen/test_rendered_geometry.py

from skill_harness.sitegen.geometry import GeometryReport, PageReading, width_ladder

def test_a_page_never_protrudes_past_its_viewport(
    geometry_report: GeometryReport, page_name: str
) -> None:
    """No page scrolls sideways, and no text run is painted past the edge.

    Parametrized per PAGE and not per (page, width). The ladder's widths live in
    the failure message as a band. See the rationale's "Shape": one defect must
    produce one red line.
    """
    reading = _measured(geometry_report, page_name)
    assert not reading.overflows, reading.explain()
```

`_measured` is four lines and lives in the same file. There is no other production call site in the
test layer; every other geometry test reads the same `geometry_report`.

### Call site 2 — the two controls, side by side

```python
def test_the_cascade_override_is_seen_by_the_browser(sabotaged_report: GeometryReport) -> None:
    """Positive control. The detector is not dead."""
    broken = [r for r in sabotaged_report.readings() if r.overflows]
    assert broken, sabotaged_report.explain()


def test_the_cascade_override_is_invisible_to_every_stylesheet_grep() -> None:
    """Negative control, and it is the reason the browser layer exists.

    All fourteen S456 predicates still return True against the sabotaged
    stylesheet that the test above just measured as broken. This is the blindness,
    executable.
    """
    sabotaged = _STYLESHEET.read_text(encoding="utf-8") + SABOTAGE_CSS
    still_true = [rule.name for rule in S456_RULES if rule.holds(sabotaged)]
    assert still_true == [rule.name for rule in S456_RULES], (
        "a stylesheet grep noticed the override; it is no longer a blind control"
    )
```

### Call site 3 — outside pytest, which is what the failure message tells you to run

```
$ python -m skill_harness.sitegen.geometry --site build/site \
      --page skill-git-pull-rebase-trap.html --widths 320,640,641

skill-git-pull-rebase-trap.html  320px  scroll 867 vs client 360  excess 507   INK 1, BOX 3
skill-git-pull-rebase-trap.html  640px  clean
skill-git-pull-rebase-trap.html  641px  clean
```

`--json -` writes the same `GeometryReport` to stdout.

### What a failure actually prints

This is the artifact the design is optimizing for. One page broke; the maintainer reads one block.

```
FAILED tests/sitegen/test_rendered_geometry.py::
       test_a_page_never_protrudes_past_its_viewport[skill-git-pull-rebase-trap.html]

skill-git-pull-rebase-trap.html protrudes past its viewport.

  overflowing        320px-1078px   (onset bisected: clean at 1079, broken at 1078)
  ladder             320 380 440 500 560 620 639 640 641 680 ... 1400   (24 rungs;
                     639/640/641 are the stylesheet's own 40rem breakpoint and its edges)
  worst              at 320px: scrollWidth 867 vs clientWidth 360, excess 507

  ink past the edge at 320px (a run of text painted outside the viewport):
    right  867.00   main > section:nth-of-type(2) > pre > code
                    "git pull --rebase origin main   # the whole line, unwrapped"

  boxes past the edge at 320px, worst first (attribution only, never the predicate):
    right  712.00   main > table:nth-of-type(1)
    right  690.00   main > table:nth-of-type(1) > tbody > tr:nth-child(3) > td:nth-child(2)

  instrument         Chromium 153.0.8010.12, device scale 1, viewport height 900,
                     fonts ready, 4 faces loaded, computed body font-family matched
  reproduce          python -m skill_harness.sitegen.geometry \
                       --site /tmp/pytest-of-x/geometry-site0/site \
                       --page skill-git-pull-rebase-trap.html --widths 320
  full table         /tmp/pytest-of-x/geometry-site0/geometry-report.json
```

Four things in there that a naive shape does not give you, and each is a design decision below: the
**band with a bisected onset** instead of forty near-identical red lines; the **ink run** named with
its text, because the `design/port-field-manual` defect was an `h1` text run at right 363.22 with no
element box over the limit; the **instrument line**, so a maintainer can tell a broken page from a
broken harness without reading code; and the **reproduce command**, because the tmp site is gone by
the time anyone looks.

---

## Shape

### Module map

```
src/skill_harness/sitegen/geometry.py     NEW   the instrument. No pytest import, ever.
                                                public: measure_site, width_ladder, the types,
                                                BrowserNotInstalledError; plus __main__ CLI.

tests/sitegen/_sites.py                   NEW   which site. build_fixture_site(), SABOTAGE_CSS,
                                                expected_page_names().
tests/sitegen/_s456_rules.py              NEW   the fourteen greps as named pure predicates.
tests/sitegen/conftest.py                 NEW   three session fixtures, the designated-cell gate,
                                                the xdist_group marker, pytest_generate_tests.
tests/sitegen/test_rendered_geometry.py   NEW   the assertions and both controls.

tests/sitegen/test_site_viewport_S456.py  EDIT  each grep becomes `assert RULE_x.holds(_css())`.
                                                Behaviour unchanged; the predicates move.
tests/test_ci_geometry_cell_589.py        NEW   static: exactly one designated cell; addopts
                                                carries --dist loadgroup.
pyproject.toml                            EDIT  [geometry] extra; --dist loadgroup; geometry marker.
requirements-ci.txt                       EDIT  regenerate (61-pin frozen snapshot).
.github/workflows/ci.yml                  EDIT  designate one cell; playwright install chromium.
```

Tracing a failure takes two files: the test file and `geometry.py`. Nothing else is on the path.

### The types, and the invariants they carry

```python
# src/skill_harness/sitegen/geometry.py

@dataclass(frozen=True)
class Offender:
    """One thing painted past the viewport's right edge.

    `selector` is a CSS path built in the page, unique enough to paste into
    devtools. `text` is the first 80 characters of an ink run and empty for a box.
    """
    kind: Literal["ink", "box"]
    selector: str
    right: float
    text: str


@dataclass(frozen=True)
class Overflow:
    """One width at which a page failed at least one of the two predicates.

    INVARIANT, enforced in the constructor: an Overflow exists only when
    `scroll_width > client_width` or `ink_offenders` is non-empty. A clean width
    produces no Overflow at all, so an empty `overflows` tuple means clean and
    cannot mean "we did not look".

    `box_offenders` is attribution and never a predicate. A `position: fixed`
    decoration or a deliberately clipped element sits past the edge without being
    a defect, so a box walk cannot gate. It explains, it does not judge.
    """
    width: int
    scroll_width: int
    client_width: int
    ink_offenders: tuple[Offender, ...]
    box_offenders: tuple[Offender, ...]

    @property
    def scroll_excess(self) -> int:
        """Derived, never stored, per single-source-of-truth."""
        raise NotImplementedError


@dataclass(frozen=True)
class Instrument:
    """What the reading was taken with. Every field is observed, none is assumed."""
    browser_version: str
    device_scale_factor: float
    viewport_height: int
    fonts_loaded: int
    body_font_family: str


@dataclass(frozen=True)
class PageReading:
    """A page that was successfully read at every width in the ladder.

    INVARIANT by construction: this type exists only for a page whose stylesheet
    demonstrably applied and whose fonts finished loading. A page that failed
    either check is an UnreadablePage, not a PageReading with a flag set false.
    That is deliberate: a missing style.css makes `scrollWidth <= clientWidth`
    trivially true, so "the CSS did not load" must not be representable as a
    clean reading. Per encode-lessons-in-structure.
    """
    page: str
    widths: tuple[int, ...]
    overflows: tuple[Overflow, ...]
    onset: int | None
    instrument: Instrument

    @property
    def bands(self) -> tuple[tuple[int, int], ...]:
        """Contiguous runs of overflowing widths, derived from `overflows`.

        A tuple of runs, not one run. The session's sweep measured every failing
        range as contiguous from 320 upward, but that is a property of viewport
        protrusion on a narrow-first stylesheet and a band-scoped media query
        would break it. Nothing here assumes monotonicity; the report just gets
        longer when it does not hold.
        """
        raise NotImplementedError

    def explain(self) -> str:
        """The failure block reproduced in this design's Usage section."""
        raise NotImplementedError


@dataclass(frozen=True)
class UnreadablePage:
    """A typed refusal. The page could not be measured and no number is invented.

    `reason` is one of a closed set, spelled out rather than coded so the message
    is the message: the navigation failed, the stylesheet request did not return
    200, the computed body font-family does not match the stylesheet's, or
    document.fonts.ready did not settle inside the budget.
    """
    page: str
    reason: str

    def explain(self) -> str:
        raise NotImplementedError


PageResult = PageReading | UnreadablePage


@dataclass(frozen=True)
class GeometryReport:
    """Every page of one built site, measured across one width ladder, once."""
    site_dir: Path
    ladder: tuple[int, ...]
    results: tuple[PageResult, ...]

    def page_names(self) -> tuple[str, ...]: ...
    def result_for(self, page: str) -> PageResult: ...
    def readings(self) -> tuple[PageReading, ...]:
        """Only the pages that were measured. Callers that need the refusals ask
        for `results`; this exists so a control can say "something broke" without
        an Unreadable page counting as a break."""
        ...
    def to_json(self) -> str: ...
    def explain(self) -> str: ...
```

**The dominant access pattern** is "give me page P's result so one test can assert on it", and
`result_for` answers it off a dict built once in `__post_init__`. The second pattern is "which pages
broke", answered by `readings()` plus a filter. No later index is needed; there is no third pattern.

### The public functions

```python
DEFAULT_LADDER_LO = 320
DEFAULT_LADDER_HI = 1400
DEFAULT_LADDER_STEP = 60          # ReDeCheck (Walsh et al., ISSTA 2017)


def width_ladder(
    stylesheet: str,
    *,
    lo: int = DEFAULT_LADDER_LO,
    hi: int = DEFAULT_LADDER_HI,
    step: int = DEFAULT_LADDER_STEP,
) -> tuple[int, ...]:
    """The widths to measure at: a coarse sweep augmented with the page's own breakpoints.

    Pure. No browser, no I/O. This is the only piece of real policy in the module
    and it has unit tests that need nothing installed.

    ReDeCheck samples 320-1400 at a 60px step AND augments with the breakpoint
    widths parsed out of the page's own CSS. The augmentation is what makes a 60px
    step defensible; a reimplementation that drops it is not the same technique, so
    dropping it here would be a silent methodology change.

    # TODO
    #   rungs = range(lo, hi + 1, step), plus hi itself if step does not land on it
    #   for each `(min-width|max-width): <n>(px|rem)` in every @media prelude:
    #       px = n if unit == px else round(n * 16)      # 40rem -> 640
    #       if lo <= px <= hi: add px, px - 1, px + 1    # both sides of the edge
    #   return tuple(sorted(set(...)))
    #
    # The +/-1 probes matter more than the rung: a max-width: 40rem block is
    # active at 640 and inactive at 641, and the 60px grid lands on neither.
    """
    raise NotImplementedError


def measure_site(
    site_dir: Path,
    *,
    widths: Sequence[int],
    pages: Sequence[str] | None = None,
) -> GeometryReport:
    """Measure every page of a built site at every width. One call, one table.

    `pages` defaults to every `*.html` under `site_dir`, ENUMERATED rather than
    counted: a default build emits seven pages and a `landing=True` build emits
    eight, so a pinned count is a latent false failure.

    Raises BrowserNotInstalledError if Playwright or its Chromium build is absent.
    It does not skip and it does not return an empty report. A caller that wants a
    skip decides that itself, above this line, where the decision is visible.

    What this hides from the caller: an ephemeral-port static HTTP server over
    `site_dir`; a Chromium launch and a single browser context pinned to device
    scale 1, light color scheme and reduced motion; per-page navigation and a
    stylesheet-applied probe; a font-readiness wait before every single reading;
    a resize-and-settle loop across the ladder; two independent overflow
    predicates; a bisection between adjacent rungs to find the exact onset; and
    the teardown of all of it on any exception. The caller sees a directory, a
    list of integers, and a table.

    # TODO  the flow, in order
    #   with _serve(site_dir) as base_url, _chromium() as browser:
    #       ctx = browser.new_context(viewport={w: widths[0], h: 900},
    #                                 device_scale_factor=1, color_scheme="light",
    #                                 reduced_motion="reduce")
    #       for name in (pages or sorted(p.name for p in site_dir.glob("*.html"))):
    #           page = ctx.new_page()
    #           resp = page.goto(f"{base_url}/{name}", wait_until="load")
    #           probe = _style_probe(page)          # -> Instrument | refusal reason
    #           if refusal: results.append(UnreadablePage(name, reason)); continue
    #           for w in widths:
    #               page.set_viewport_size({"width": w, "height": 900})
    #               _settle(page)                   # fonts.ready + two rAF ticks
    #               ov = _read(page, w)             # runs _PROBE_JS
    #               if ov: overflows.append(ov)
    #           onset = _bisect_onset(page, widths, overflows)  # only if any
    #           results.append(PageReading(...))
    #           page.close()
    #
    # Navigation happens ONCE per page and the viewport is resized across the
    # ladder. 7 navigations rather than 7 x 24. Safe here because these pages are
    # static with no script; a page with viewport-dependent JS would need the
    # re-navigation and this comment is where that is decided.
    """
    raise NotImplementedError


class BrowserNotInstalledError(RuntimeError):
    """Playwright or its Chromium build is missing (the optional [geometry] extra).

    Mirrors SitegenNotInstalledError exactly, including the lazy import behind a
    typed install hint, so a core install imports this module fine and fails at
    use time with an actionable message rather than at import time with a bare
    ImportError naming a package nobody asked for.
    """
```

### The private pieces, sketched

```python
_VIEWPORT_HEIGHT = 900      # not a parameter. See "Tradeoffs accepted".
_INK_EPSILON_PX = 0.5
_FONT_BUDGET_MS = 5_000


@contextmanager
def _serve(root: Path) -> Iterator[str]:
    """A ThreadingHTTPServer on ('127.0.0.1', 0) over `root`, yielding its base URL.

    Port 0 on purpose: every xdist worker that reaches this binds a distinct
    ephemeral port with no coordination, so the harness is correct under any
    distribution mode. `--dist loadgroup` makes it fast, not correct.

    The lifecycle is the repository's existing idiom, lifted verbatim from
    tests/test_release_gate_206.py:147-155 -- serve_forever on a thread, then
    shutdown / join / server_close in a finally. Those two call sites serve a
    mocked JSON API; this is the first to serve a directory.

    HTTP and not file://. The prior-art probe at
    ~/.claude/skills/impeccable/scripts/detector/_s456b_measure.mjs used file://,
    which resolves the stylesheet by a different path rule than the published site
    and gives no way to observe that the request returned 200.
    """
    raise NotImplementedError


def _style_probe(page: Page) -> Instrument | str:
    """Prove the stylesheet applied and the fonts loaded, or say why not.

    This is the vacuity guard, and every reading in the report rests on it.
    If style.css 404s, the page renders unstyled, nothing is wider than the
    viewport, and `scrollWidth <= clientWidth` passes. A green suite would then
    mean "the CSS is missing", which is the exact failure the harness exists to
    catch. So a reading is only issued once the computed body font-family matches
    what the stylesheet declares and document.fonts.size is non-zero.

    # TODO
    #   await page.evaluate("document.fonts.ready") with _FONT_BUDGET_MS
    #   family = getComputedStyle(document.body).fontFamily
    #   if family does not contain the stylesheet's declared first family:
    #       return "style.css did not apply: computed body font-family is {family!r}"
    #   if document.fonts.size == 0: return "no font faces loaded"
    #   return Instrument(...)
    """
    raise NotImplementedError


def _settle(page: Page) -> None:
    """Wait for fonts and let layout quiesce, before EVERY reading.

    Not once per page. The design/port-field-manual trail records a second defect
    that appeared "at 75px once the real faces loaded", so a reading taken before
    the real faces are in is a reading of a different page.

    # TODO  await document.fonts.ready; then two requestAnimationFrame ticks.
    """
    raise NotImplementedError


_PROBE_JS = """
() => {
  // Two independent predicates and one attribution walk. Returns null when clean.
  //
  // P1  document.documentElement.scrollWidth <= clientWidth
  //     Scrollbar-independent by construction, which is why it and not a nominal
  //     360 is the predicate: two Chrome builds on the author's own host disagree
  //     by 15 CSS px about what a 360px viewport's clientWidth is.
  //
  // P2  no text run painted past clientWidth (+ _INK_EPSILON_PX)
  //     P1 alone misses ink clipped by an `overflow: hidden` ancestor, which is
  //     unreadable text that does not scroll the page. Range.getClientRects over
  //     every text node is what found the h1 run at right 363.22 in a 345px
  //     viewport where no element box was over the limit.
  //
  // BOX walk: getBoundingClientRect over body *, right > limit. Reported, never
  // asserted on -- see Overflow.box_offenders.
  //
  // cssPath(el): tag + :nth-of-type chain up to body. Built in-page so the
  // selector in the failure message is one a maintainer can paste into devtools.
}
"""


def _bisect_onset(page: Page, ladder: Sequence[int], overflows: Sequence[Overflow]) -> int | None:
    """The exact narrowest width at which the page first breaks.

    ReDeCheck binary-searches between adjacent sampled widths whenever the layout
    changes across them; this is that step, narrowed to the one transition a
    maintainer cares about. Costs about six extra readings and only when something
    already failed, so a clean run pays nothing.

    Returns None when the narrowest ladder rung already overflows, meaning the
    onset is at or below the bottom of the measured range and the report should
    say so rather than claim 320.
    """
    raise NotImplementedError
```

### The test layer

```python
# tests/sitegen/conftest.py

pytestmark = pytest.mark.xdist_group("sitegen_geometry")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize `page_name` at collection time, from the receipts, not the build.

    build_site refuses an existing output directory, so the site cannot exist at
    collection time and the page list cannot come from it. It is derived instead
    from the receipts directory plus the page-name constants and `skill_page_name`
    that sitegen.render already exports -- the NAMING POLICY stays in render.py and
    only the "which receipts" loop is repeated here.

    That repetition is checked rather than trusted:
    test_the_measured_page_set_is_the_built_page_set reddens the moment build_site
    emits a page this predicted set does not contain, or the reverse.
    """


@pytest.fixture(scope="session")
def designated_geometry_cell() -> None:
    """Skip unless this is the one cell designated to run the browser.

    Font fallback differs per platform and the measurement is only reproducible
    where the font stack is identical, so exactly one of the four CI cells runs
    this. The gate is one environment variable and nothing else, because a gate
    with two mechanisms is a gate somebody half-disables.

    A skip that nobody counts is a dead control, so the count is a test:
    tests/test_ci_geometry_cell_589.py reads ci.yml and fails unless exactly one
    matrix cell sets SKILL_HARNESS_GEOMETRY_CELL.
    """


@pytest.fixture(scope="session")
def geometry_report(
    tmp_path_factory: pytest.TempPathFactory, designated_geometry_cell: None
) -> GeometryReport:
    """Build the real site once, measure it once, hand the table to every test.

    On the designated cell a missing browser is a FAILURE and not a skip.
    BrowserNotInstalledError propagates. The only sanctioned skip is "this is not
    the designated cell".

    Writes geometry-report.json beside the site so CI can upload it and the
    failure message can point at it.
    """


@pytest.fixture(scope="session")
def sabotaged_report(tmp_path_factory, designated_geometry_cell) -> GeometryReport:
    """The control. A second build whose style.css has SABOTAGE_CSS appended.

    One page, three widths. It only has to prove the detector fires, so it does
    not pay for the full matrix.
    """
```

```python
# tests/sitegen/_s456_rules.py

@dataclass(frozen=True)
class StylesheetRule:
    """One of the fourteen S456 greps, as a pure predicate over stylesheet text.

    Extracting these changes no behaviour. It exists so the negative control can
    run all fourteen against the SABOTAGED stylesheet and show every one still
    returns True -- which is the blindness this whole ticket is about, stated as
    an executable claim instead of a paragraph in a docstring.
    """
    name: str
    defect: str                       # "D1", "D2", ...
    holds: Callable[[str], bool]


S456_RULES: tuple[StylesheetRule, ...] = (...)   # fourteen entries
```

```python
# tests/sitegen/_sites.py

SABOTAGE_CSS = """
* { overflow-wrap: normal !important; word-break: normal !important; }
table { table-layout: auto !important; }
@media (max-width: 40rem) {
  table, thead, tbody, tr, th, td { display: revert !important; }
}
"""
"""The measured non-vacuity control.

Every existing rule's TEXT survives it, so all fourteen greps still match, and it
breaks five of seven pages with a worst case of scrollWidth 867 against
clientWidth 360. Do not "tidy" this string; its value is that it was measured.
"""


def build_fixture_site(output: Path, *, landing: bool = True, sabotage: bool = False) -> Path:
    """The repository's own site, built into a fresh directory.

    The fourth `_build` closure would have been the third divergence. This is the
    first shared one and the S456 and S455 files move onto it in the same change.
    It carries policy rather than forwarding arguments: it knows this repository's
    schema path, receipts directory, landing copy fixture and social image, and it
    is the single place that decides whether the site under test has a landing page.
    """
```

### Interface depth, judged

The public surface of the instrument is **two functions and five frozen dataclasses**. Behind it:
HTTP serving, Chromium lifecycle, context determinism pinning, navigation, a stylesheet-applied
vacuity guard, font readiness before every reading, a resize-and-settle loop, two predicates, a box
attribution walk, an in-page CSS-path builder, bisection, JSON serialization, and a CLI. Learning
`measure_site(site_dir, widths=...)` genuinely saves the caller from learning any of it.

What stays exposed, and why it has to be: `widths`, because the ladder is policy the caller may
legitimately narrow (the control does); `pages`, because "which pages" is a domain question. What
was deliberately pulled inside: the base URL, the browser, the context options, the viewport height,
whether to bisect. An earlier draft had `refine: bool` and it was cut — a public option naming an
internal stage is the red-flag definition of a shallow module.

No transport type crosses the boundary, per boundary-discipline. Playwright's `Page`, `Browser` and
`Response` appear only in private signatures. `GeometryReport` is domain data and serializes without
Playwright installed, which is what lets the JSON artifact be read on a machine that has no browser.

### Under `pytest-xdist`

The repository runs `pytest -q -n 4` on four matrix cells, with `pytest-randomly` shuffling
collection order. Three separate things follow.

**Correctness first, and it needs nothing.** Each worker that reaches the fixture builds its own site
under its own `tmp_path_factory` root, binds its own port-0 ephemeral port, and launches its own
browser. Two workers cannot both write anything: there is no shared file, no shared port, no shared
lock. Asking the runner prompt's question — if two actors both write, what happens? — the answer
here is literally nothing, because the design is per-actor state by construction rather than by
arrangement. **This is the property worth protecting.** A design that reaches for a fixed port, a
`FileLock`, or an `is_master` / `workerinput` broadcast has made parallelism a correctness problem
to make it a cost problem.

**Cost second, and that is what the grouping buys.** `pytest.mark.xdist_group("sitegen_geometry")`
on the whole `tests/sitegen/` package, plus `--dist loadgroup` in `addopts`. `loadgroup` sends every
test carrying the same group name to one worker as a unit and distributes everything else exactly as
`load` does, so the change to the other 3000 tests is nil. One worker, one build, one Chromium, one
measurement pass, one port. The other three keep working on the rest of the suite.

**The grouping is asserted, not hoped for.** `tests/test_ci_geometry_cell_589.py` reads
`pyproject.toml` and `.github/workflows/ci.yml` and fails if `--dist loadgroup` leaves `addopts` or
if the designated-cell count is not exactly one. The repository already does exactly this in
`tests/test_ci_test_cell_attribution_509.py`, which reads the workflow's `--durations` line, so this
is the house pattern rather than a new one. If somebody reverts the addopt anyway, the suite gets
slower and stays correct — the enforcement protects the cost, and nothing protects correctness
because nothing has to.

**The one real cost risk**, stated plainly: the grouped worker becomes the cell's tail. Seven pages
at roughly 24 rungs is 168 readings plus 7 navigations; the session's own 7,567-measurement sweep ran
in about a minute, which puts this near 3 seconds of measurement plus a one-off Chromium launch. It
is not close to the 486s cell. The 1px fine sweep, which *is* a minute, is marked `slow` and does not
run in the PR cell at all.

### The two controls, and why both are standing tests

The positive control — sabotage the built stylesheet, assert the browser sees it — proves the
detector is alive. On its own it is half an argument. The negative control — the same sabotaged text,
all fourteen greps still `True` — proves the layer being replaced is blind. Together they are the
ticket's entire claim, executable, running on every PR, costing one extra three-width measurement.
Neither is a comment and neither is a thing somebody ran once in a session.

The negative control is also a live alarm on a real future event: if someone strengthens a grep so
that it *does* catch the override, `test_the_cascade_override_is_invisible_to_every_stylesheet_grep`
reddens and the maintainer has to decide whether the sabotage string is still the right control. That
is the correct outcome; a control that silently stops being a control is this project's named failure
mode.

### The measurement record

`GeometryReport.to_json()` is written beside the built site and named in every failure message.
`UnreadablePage` is the typed refusal: a page that could not be read produces a reason string and no
geometry at all. There is no sentinel width, no zero excess, no `-1`. A reading that exists is a
reading that was taken with the stylesheet demonstrably applied and the fonts demonstrably loaded,
because those two facts are preconditions of the type rather than fields on it.

---

## Synthesis decision

Three candidates were designed in parallel on three models against one measured grounding
packet. This one became the base. The grafts and the rejections are below, with the reason
for each, so a later reader can tell a decision from an accident.

**Why this candidate is the base.** It was the only one that found the vacuity trap. If
`style.css` fails to load, the page renders unstyled, nothing is wider than the viewport, and
`scrollWidth <= clientWidth` passes. A green suite would then mean the stylesheet is missing,
which is the exact class of failure the harness exists to catch. `_style_probe` refuses to
issue a reading until the computed body font-family matches what the stylesheet declares and
at least one font face has loaded. Neither other candidate has any guard here, and both would
have shipped a control that passes hardest when the site is most broken.

It was also the only one to build the negative control. Haiku raised it as an open question
and then dismissed it. Sonnet did not raise it. Running all fourteen greps against the
sabotaged stylesheet and asserting every one still returns `True` turns this ticket's entire
argument into a standing test rather than a paragraph, and it puts a live alarm on the day
somebody strengthens a grep enough to catch the override.

**Grafted from sonnet.** Its restraint about the three `_build` closures is adopted over this
candidate's own proposal. This candidate moves both `test_site_viewport_S456.py` and
`test_site_design_S455.py` onto one `build_fixture_site` in the same change. Sonnet argued
that forcing S455 and S456 through one helper is itself the shallow-module red flag, because
they want genuinely different parameters, and it factored only the duplicated repository-path
constants. That argument holds, and there is a second reason it wins here: S455 is not this
ticket's subject, so moving it is scope this ticket did not ask for. **`build_fixture_site`
is created and `test_site_viewport_S456.py` moves onto it. `test_site_design_S455.py` is left
exactly as it is, and its unification is a separate ticket.**

**Rejected from sonnet, with the reason.** Its full one-pixel ladder across 320-1400. Its
argument was that the session measured a full sweep at about a minute for seven pages, so the
coarse-step-plus-breakpoint machinery buys nothing. That is true about affordability and
wrong about the tiering. A minute in the PR cell, every PR, to re-measure widths that differ
by one pixel is a cost with no corresponding information, and this candidate's `+/-1` probes
around each parsed breakpoint catch the thing a coarse grid actually misses: a
`max-width: 40rem` block is active at 640 and inactive at 641, and a sixty-pixel grid lands on
neither. **The tiered answer is adopted: the derived ladder runs on every PR, and the full
one-pixel sweep survives as a `slow`-marked test that does not run in the PR cell.** Sonnet's
measurement stands as the reason the slow sweep is affordable at all.

**Rejected from haiku, with the reason.** Its non-vacuity control was
`@pytest.mark.xfail(..., strict=False)`, which passes whether the control reddens or not. That
is a vacuous control, and it reproduces the exact defect class of `#589` inside the fix for
`#589`. Its control body was also internally inconsistent, carrying an `xfail` decorator while
calling `pytest.fail` in its own `else` branch, and referencing two helpers it never defined.

**Kept from haiku.** Its reasoning that the harness belongs outside the installed package was
costed and correct in isolation, and it loses here only to this candidate's `python -m`
reproduce path, which is the most useful line in the failure message once the temporary site
has been deleted. Its per-page-rather-than-per-width parametrization instinct agrees with the
base and is recorded as convergent rather than grafted.

**The open questions, decided rather than escalated.** None is a values fork, so none goes to
the owner. The designated cell is `ubuntu-latest` on `3.13`, because it already uploads the
coverage artifact and is therefore the natural host for the JSON report.
**WITHDRAWN at implementation. The cell is `windows-latest` on `3.13`**, because artifact
convenience is not a measurement argument and the font stack resolves differently on Linux.
See "Implementation reconciliation". A `ResourceWarning`
out of the server thread or the Playwright transport is treated as a real defect and fixed at
source, not filtered. `pip install -e ".[dev]"` stays browser-free and the browser is reachable
only through the explicit extra, which mirrors the `[sitegen]` precedent exactly. Running the
geometry check in `pages.yml` before publishing, and adding a `prefers-color-scheme: dark`
axis, are both real and both out of scope here; each gets its own ticket.

**Delivery, as a stack of verifiable units rather than one change.** The unit boundaries are
where a check lands, per sequence-verifiable-units.

1. `width_ladder` and its unit tests. Pure, no browser, no install. This is the only piece of
   published methodology in the design, and having it green first makes the ladder in every
   later failure message a measured thing rather than a literal.
2. `geometry.py`, its types and the `python -m` CLI. Verified by hand against the real built
   site before any test depends on it.
3. The test layer: `conftest.py`, `_sites.py`, `_s456_rules.py`, `test_rendered_geometry.py`,
   and both controls. Verified by watching the positive control redden and the negative
   control stay green on the same sabotaged stylesheet.
4. The plumbing: the `[geometry]` extra, the `requirements-ci.txt` regeneration, the cell
   designation in `ci.yml`, and the static test that asserts exactly one designated cell.

---

## Tradeoffs accepted

- **We accept a new module in `src/` in exchange for a measurement instrument that is not
  pytest-shaped.** The obvious objection is that this is test infrastructure shipped in the product.
  The answer is the boundary: `src` owns *how to measure any built site*, `tests` owns *which site
  and what must be true of it*, and `geometry.py` imports no pytest. It buys the `python -m` reproduce
  path, mypy `--strict` coverage, and the option of a release-gate caller later, none of which a
  `tests/` helper can give.
- **We accept parametrizing per page and not per (page, width) in exchange for one red line per
  defect.** A 7x24 grid gives finer node ids and, on the measured sabotage, 60-odd near-identical
  failures for five real defects. The width information is not lost; it moves into the band and the
  bisected onset, where it is more precise than a node id would have been.
- **We accept a fixed 900px viewport height, hidden from the caller.** Height is not inert: a vertical
  scrollbar consumes layout width on a build without overlay scrollbars, and that is exactly the 15px
  disagreement measured between two Chrome builds on this host. Pinning it is reproducibility. Hiding
  it keeps a knob off the public surface that no caller has a reason to turn.
- **We accept touching `test_site_viewport_S456.py` to extract fourteen predicates.** It looks like
  unrelated churn. It is the only way the negative control can be an assertion instead of a paragraph.
  Behaviour is unchanged; the `assert` lines become `assert RULE.holds(_css())`.
- **We accept adding `--dist loadgroup` to global `addopts` for one package's benefit.** It is a
  no-op for ungrouped tests and a no-op without `-n`, so the blast radius is a line of config and a
  static test that guards it.
- **We accept that the box walk can report an offender that is not a defect.** It is attribution, it
  never gates, and a `position: fixed` decoration showing up in the offender list is a smaller cost
  than a maintainer with a 507px excess and no idea which element produced it.
- **We accept navigating once per page and resizing across the ladder.** Re-navigating at every width
  would need less justification and run about 20x slower. It is safe because these pages carry no
  script; the comment in `measure_site` is where that assumption is recorded so the next person can
  find it when it stops holding.

## Alternatives considered

- **A `conftest.py` fixture and nothing else, all logic in `tests/sitegen/`.** The smallest possible
  change and the one most people would write. It loses the `python -m` reproduce path — which is the
  single most useful line in the failure message, because the tmp site is deleted by the time anyone
  reads the log — and it makes the measurement uncallable from anything that is not a pytest session.
  Interface depth: identical capability, but the public surface becomes "a fixture", which cannot be
  invoked, typed against, or serialized by a caller. It hides the same complexity from one caller
  instead of from any caller.
- **`pytest-playwright`'s fixtures instead of `playwright.sync_api` directly.** It hands you `page`
  and `browser` and artifact capture for free. It also makes `page` function-scoped with a fresh
  context per test, which fights the one-pass session measurement this design is built on, and it
  puts a pytest plugin on the dependency path of a module that is deliberately pytest-free. Rejected
  on both counts; the artifact capture it would have given us is replaced by `to_json()`, which is
  readable without a browser installed.
- **A `(page, width)` parametrization grid, 7x24 = 168 node ids.** The finest granularity and the
  best `-k` story. Rejected on what it prints: the measured sabotage produces contiguous failing
  bands, so this shape reports one defect 40 times and buries five real defects in sixty red lines.
  It also multiplies fixture plumbing without multiplying information.
- **One test that sweeps everything and asserts once.** The cheapest to write and the exact opposite
  failure: five defects collapse into one red line and a maintainer has to read a wall of text to
  find out how many pages are actually broken. The chosen shape sits between the two deliberately.
- **A fixed port plus a `FileLock` so all xdist workers share one server and one browser.** Maximum
  efficiency. It converts a cost problem into a correctness problem — a stale lock, a port already
  bound on a developer's machine, a worker crash holding the lock — and buys nothing that
  `--dist loadgroup` does not already buy without shared state. Rejected per
  separate-before-serializing-shared-state.
- **Re-deriving the static cascade resolver.** Not considered. 755 lines, already built in this
  project, already withdrawn.

## Implementation reconciliation

Where the built thing differs from the design above. Each entry names what the design said,
what shipped, and why. The per-decision record is
`docs/design/rendered-geometry-trail-S464.tsv`.

**The designated cell is `windows-latest` / `3.13`, not `ubuntu-latest` / `3.13`.** The design
chose ubuntu because that cell already uploads the coverage artifact and is therefore a
convenient host for the JSON report. Convenience is not a measurement argument and it lost to
one. Every reading behind this harness was taken on Windows Chromium 153, and the stylesheet's
font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`) resolves to
a different face on Linux, where no reading has ever been taken. The ink walk could
legitimately report overflow on Ubuntu that nobody has measured, and that red would be a
platform difference wearing a defect's clothes. The designation is one GitHub Actions
expression in the Test job's `env:`, and the two install steps gate on its value rather than
repeating the condition, so there is exactly one site to read and one site to revert.

**The xdist group is narrowed to the fixture closure.** The design put
`pytest.mark.xdist_group` on the whole `tests/sitegen` package. Unit 3 shipped that and recorded
it as open, because it serialises every test in the package onto one worker to protect two
fixtures most of them never request. The marker is now applied to the items whose
`fixturenames` contain `geometry_report` or `sabotaged_report`. Measured over the whole suite,
`-m xdist_group` selects 10 of 3225 where it selected 133 of 3225.

**`requirements-ci.txt` was extended, not re-frozen.** The design said regenerate. The header's
regeneration command re-resolves the whole environment, and doing that today is a much larger
change than this ticket: it drops `pip-audit` and `tqdm`, replaces `httpcore`/`httpx` with
`httpcore2`/`httpx2`, and adds eleven `pre-commit` transitives the snapshot has never carried.
The seven browser pins were captured by resolving `.[dev,geometry]` against the existing file,
which is how `jsonschema` was added on 2026-08-10. Every pre-existing pin is byte-identical and
the diff is the browser surface alone.

**`[geometry]` carries `pytest-playwright`, which nothing imports.** The Alternatives section
above rejected its function-scoped `page` fixture, and `geometry.py` is pytest-free by
construction. It is declared so the extra names the whole browser-test surface in one place,
and it costs four of the seven new CI pins (itself, `pytest-base-url`, `python-slugify`,
`text-unidecode`). It is carried openly rather than quietly; if no caller appears it should be
deleted rather than found a use.

**No geometry marker was registered.** The module map above says `pyproject.toml` gains one.
`xdist_group` is registered by pytest-xdist itself, so `--strict-markers` accepts it with no
entry in the `markers` table, and adding one would have been a second declaration of somebody
else's marker.

**`docs/sitegen/rendered-geometry.md` does not exist.** The Usage section above cites it as the
maintainer's quickstart. Units 1 to 3 put that text in the module docstring and never wrote the
file, so the citation at the top of this document is a pointer to nothing. It is named here
rather than left for a reader to discover.

**Open question resolved by measurement, not by argument.** `filterwarnings = ["error"]` needed
no geometry override. The full suite runs green with and without the designated-cell variable
set, so neither the server thread nor the Playwright transport raised a `ResourceWarning` that
had to be filtered.

## Open questions and risks

- ANSWERED, no override was needed. `pyproject.toml` sets `filterwarnings = ["error"]`. Should
  the geometry tests carry a narrow `filterwarnings` override, or should any `ResourceWarning`
  from the HTTP server thread or the Playwright transport be treated as a real defect and fixed
  at the source? I lean toward the second, but it is a first-run discovery and the first run has
  not happened. It has now, and neither source raised one.
- ANSWERED, `windows-latest` / `3.13`. Which cell should be the designated one? Font fallback is
  the reason for picking one, and `ubuntu-latest` / `3.13` is the cell that already uploads the
  coverage artifact, so it is the natural host for the JSON report. Does the owner want the
  browser on the Windows cell instead, given the published site's readers are not on CI runners
  at all? The question reached the right answer for a reason it did not name: every reading
  behind this harness was taken on Windows, so Ubuntu is the platform with no baseline. See
  "Implementation reconciliation".
- Should `.github/workflows/pages.yml`, which builds the real published site, run the geometry check
  before publishing? That would make "the published page does not protrude" a release condition
  rather than a PR condition. Out of scope as written; worth a ticket either way.
- The context is pinned to `color_scheme="light"`. If the stylesheet grows a
  `prefers-color-scheme: dark` block that changes any box, the harness will not be looking at it.
  Does the ladder need a second axis, or does a separate dark-mode reading belong in its own ticket?
- The `[geometry]` extra adds Playwright plus its Chromium download to the designated cell only, and
  `requirements-ci.txt` is a frozen 61-pin snapshot that must be regenerated. Is the owner content
  for `pip install -e ".[dev]"` to stay browser-free, with the browser reachable only through the
  explicit extra?

## Next implementation step

Write `width_ladder` and its unit tests first — it is pure, it needs no browser, it encodes the one
piece of published methodology in the design, and having it green makes the ladder in every later
failure message a measured thing rather than a literal.
