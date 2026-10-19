"""The favicon: the file, the fence that scans it, and the link every page emits.

Audit finding A4 (brief 4.1) asked for a favicon. The S455 Make seat built the
plumbing and halted on the mark itself, because a favicon is an identity claim
and the tree held no glyph to reduce. ``docs/design/direction-favicon-S456.md``
put three candidates to the owner and he chose C, the wordmark's initial inside
the declared Readout Frame.

These tests pin the file rather than the drawing. What they hold is that the
mark cannot drift outside the declared token set without a red suite, that the
fence's ``assets/*.svg`` glob actually reaches the path, and that every page of
every build carries exactly one ``rel="icon"``.

The fence test carries its own negative control. A scan that passes everything
proves nothing, so the same scanner runs over a poisoned copy of the real file
in the same test and must report the poison.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from skill_harness.sitegen import DEFAULT_BASE_URL, build_site
from skill_harness.sitegen.render import FAVICON_NAME
from tests.test_design_tokens_conformance import (
    DESIGN_MD,
    live_surface_paths,
    parse_declared_tokens,
    scan_for_undeclared_tokens,
)

_REPO = Path(__file__).resolve().parents[2]
_FAVICON = _REPO / "assets" / "favicon.svg"
_SCHEMA = _REPO / "docs" / "sers" / "sers.schema.json"
_RECEIPTS = _REPO / "docs" / "sers" / "receipts"
_LANDING_COPY = Path(__file__).parent / "fixtures" / "landing.md"


def _build(output: Path, *, favicon: Path | None, landing: bool = False) -> Path:
    build_site(
        schema_path=_SCHEMA,
        receipts_dir=_RECEIPTS,
        extraction_path=None,
        output_dir=output,
        marker="s456-favicon-marker",
        base_url=DEFAULT_BASE_URL,
        landing=landing,
        landing_copy_path=_LANDING_COPY if landing else None,
        favicon_path=favicon,
    )
    return output


def test_the_favicon_file_is_on_the_tree() -> None:
    """A4 closes with a file, not with a code change. The plumbing already existed."""
    assert _FAVICON.is_file(), "assets/favicon.svg is missing; no page will emit a rel=icon"


def test_the_token_fence_globs_the_favicon_path() -> None:
    """The fence's path list is style.css plus assets/*.svg, by glob.

    This is the reason the mark had to land at exactly this path. A favicon
    anywhere else on the tree, or inlined as a data URI in a template, escapes
    the scanner entirely.
    """
    assert _FAVICON in live_surface_paths()


def test_the_favicon_draws_only_declared_tokens_and_the_scanner_can_still_fail(
    tmp_path: Path,
) -> None:
    """The mark scans clean, and the same scanner reddens on a poisoned copy of it.

    The poison is the control. Without it this test would pass just as happily
    against a scanner that reported nothing at all.
    """
    declared = parse_declared_tokens(DESIGN_MD.read_text(encoding="utf-8"))

    assert scan_for_undeclared_tokens([_FAVICON], declared) == []

    source = _FAVICON.read_text(encoding="utf-8")
    poisoned = tmp_path / "favicon.svg"
    poisoned.write_text(
        source.replace('fill="#0d1117"', 'fill="#1b2030"').replace(
            'font-size="21"', 'font-size="14"'
        ),
        encoding="utf-8",
    )
    violations = scan_for_undeclared_tokens([poisoned], declared)
    literals = {violation.literal for violation in violations}
    assert "#1b2030" in literals, "the scanner did not catch an undeclared colour"
    assert "14" in literals, "the scanner did not catch an undeclared font-size"


def test_the_favicon_carries_no_chroma() -> None:
    """Direction constraint 3: the semantic three are never a brand colour.

    A favicon sits on the tab whatever the page says, so a coloured icon would
    spend the instrument's one state signal on identity.
    """
    semantic = ("#3fb950", "#d29922", "#58a6ff")
    text = _FAVICON.read_text(encoding="utf-8").lower()
    for colour in semantic:
        assert colour not in text, f"the favicon draws the claim-state colour {colour}"


def test_the_favicon_declares_its_font_stack_in_a_style_block() -> None:
    """Direction constraint 5, measured rather than preferred.

    The scanner strips ``"`` and ``'`` but not ``&quot;``, so a font-family
    written as an SVG attribute reads as an undeclared family and fails. The
    three existing assets use a ``.mono`` class for the same reason.
    """
    text = _FAVICON.read_text(encoding="utf-8")
    assert "<style>" in text
    assert "font-family=" not in text


@pytest.mark.parametrize("landing", [False, True])
def test_every_page_carries_exactly_one_favicon_link(tmp_path: Path, landing: bool) -> None:
    output = _build(tmp_path / "site", favicon=_FAVICON, landing=landing)
    pages = sorted(output.glob("*.html"))
    assert pages, "the build wrote no pages"
    for page in pages:
        links = [
            element
            for element in ET.parse(page).getroot().iter("link")
            if element.get("rel") == "icon"
        ]
        assert len(links) == 1, f"{page.name} carries {len(links)} rel=icon links"
        assert links[0].get("href") == FAVICON_NAME


def test_the_build_output_carries_the_favicon_bytes_unchanged(tmp_path: Path) -> None:
    output = _build(tmp_path / "site", favicon=_FAVICON)
    written = output / FAVICON_NAME
    assert written.is_file()
    assert written.read_bytes() == _FAVICON.read_bytes()


def test_a_build_without_the_file_emits_no_link_rather_than_a_broken_one(tmp_path: Path) -> None:
    """The absent case stays silent. A page pointing at a 404 icon is worse than none."""
    output = _build(tmp_path / "site", favicon=tmp_path / "nothing-here.svg")
    assert not (output / FAVICON_NAME).exists()
    for page in sorted(output.glob("*.html")):
        assert not re.search(r'rel="icon"', page.read_text(encoding="utf-8"))
