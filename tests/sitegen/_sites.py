"""Which site the geometry tests measure, and the stylesheet that breaks it (#589).

``src/skill_harness/sitegen/geometry.py`` knows how to measure any built site. This
module knows which one: this repository's own schema, its own receipts, its own landing
copy and its own assets, built into a fresh directory. It carries that policy rather
than forwarding arguments, so a caller asks for a site and not for six paths.

It also carries ``SABOTAGE_CSS``, which is the measured non-vacuity control rather than
a story about one.
"""

from __future__ import annotations

import json
from pathlib import Path

from skill_harness.sitegen import DEFAULT_BASE_URL, build_site
from skill_harness.sitegen.render import (
    INDEX_FILE_NAME,
    NOT_FOUND_PAGE_NAME,
    RECEIPTS_PAGE_NAME,
    SCHEMA_PAGE_NAME,
    STYLESHEET_NAME,
    read_stylesheet,
    skill_page_name,
)

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO / "docs" / "sers" / "receipts"
_SOCIAL_IMAGE = _REPO / "assets" / "social-preview.png"
_FAVICON = _REPO / "assets" / "favicon.svg"

#: The published landing copy, not ``tests/sitegen/fixtures/landing.md``. The two are
#: byte-identical today and the fixture is the right input for a structure test, but the
#: geometry harness exists to say that the page a stranger loads does not protrude, and
#: that page is rendered from this file. A 54-character term added here has to be
#: measured, and it would not be if the harness read a copy.
_LANDING_COPY = _REPO / "docs" / "site" / "landing.md"

_MARKER = "s589-geometry-marker"

#: The widths the sabotaged control is measured at. Three, not the full ladder: the
#: control only has to prove the detector fires. 320 is the bottom of the ladder, and
#: 640/641 are the two sides of the stylesheet's own ``40rem`` breakpoint, which is where
#: the override's table rule changes behaviour. Measured on this build: the override puts
#: five of the eight pages past their viewport at 320, and two of them at 640 and 641 as
#: well.
SABOTAGE_WIDTHS: tuple[int, ...] = (320, 640, 641)

SABOTAGE_CSS = """
* { overflow-wrap: normal !important; word-break: normal !important; }
table { table-layout: auto !important; }
@media (max-width: 40rem) {
  table, thead, tbody, tr, th, td { display: revert !important; }
}
"""
"""The measured non-vacuity control.

Every existing rule's TEXT survives it, so all fourteen S456 stylesheet greps still
match, and it still breaks the site: five of eight pages protrude, worst case a scroll
width of 867 inside a 320px viewport on ``skill-git-pull-rebase-trap.html``. Do not
"tidy" this string. Its value is that it was measured, and both controls in
``test_rendered_geometry.py`` rest on that measurement.
"""


def sabotaged_stylesheet() -> str:
    """Exactly the stylesheet text a sabotaged build serves.

    One definition, used by both controls. The positive control measures a site whose
    ``style.css`` is these bytes and the negative control runs the fourteen greps over
    the same string, so "the browser saw a break the greps did not" is a claim about one
    stylesheet rather than about two that are assumed to agree.
    """
    return read_stylesheet() + SABOTAGE_CSS


def build_fixture_site(output: Path, *, landing: bool = True, sabotage: bool = False) -> Path:
    """The repository's own site, built into a fresh directory.

    ``build_site`` refuses an existing output directory, so ``output`` must not exist.

    ``sabotage`` overwrites the built stylesheet with :func:`sabotaged_stylesheet` after
    the build. It is applied to the OUTPUT and never to the source tree, so a control
    run cannot leave a broken stylesheet behind in the repository.
    """
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=_RECEIPTS,
        extraction_path=None,
        output_dir=output,
        marker=_MARKER,
        base_url=DEFAULT_BASE_URL,
        landing=landing,
        landing_copy_path=_LANDING_COPY if landing else None,
        social_image_path=_SOCIAL_IMAGE,
        favicon_path=_FAVICON,
    )
    if sabotage:
        (output / STYLESHEET_NAME).write_text(
            sabotaged_stylesheet(), encoding="utf-8", newline="\n"
        )
    return output


def expected_page_names(*, landing: bool = True) -> tuple[str, ...]:
    """The pages a ``build_fixture_site`` build emits, ENUMERATED and never counted.

    Derived rather than built, because ``build_site`` refuses an existing output
    directory and the site therefore cannot exist at collection time, which is when the
    geometry tests need the list in order to parametrize one test per page.

    The NAMING POLICY stays in ``render.py``: the page-name constants and
    :func:`skill_page_name` are imported, not spelled. Only the "which receipts" loop is
    repeated here, and that repetition is checked rather than trusted by
    ``test_the_measured_page_set_is_the_built_page_set``, which reddens the moment a
    build emits a page this set does not contain or the reverse.
    """
    names = {SCHEMA_PAGE_NAME, NOT_FOUND_PAGE_NAME}
    names.add(RECEIPTS_PAGE_NAME if landing else INDEX_FILE_NAME)
    if landing:
        names.add(INDEX_FILE_NAME)
    names.update(skill_page_name(skill) for skill in _receipted_skill_names())
    return tuple(sorted(names))


def _receipted_skill_names() -> tuple[str, ...]:
    """Every skill named by a receipt, read the way ``build_site`` reads them.

    No extraction join is passed to ``build_fixture_site``, so the receipts are the whole
    source of skill pages.
    """
    found: set[str] = set()
    for path in sorted(_RECEIPTS.glob("*.json")):
        receipt: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise TypeError(f"{path} is not a JSON object")
        name = receipt.get("skill_name")
        if not isinstance(name, str) or not name:
            raise TypeError(f"{path} names no skill")
        found.add(name)
    return tuple(sorted(found))


__all__ = [
    "SABOTAGE_CSS",
    "SABOTAGE_WIDTHS",
    "build_fixture_site",
    "expected_page_names",
    "sabotaged_stylesheet",
]
