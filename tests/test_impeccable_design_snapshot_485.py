"""Tests that .impeccable/design.json agrees with DESIGN.md on the paper retirement.

Issue #485: the tracked snapshot still declares six receipt-* tokens and four
receipt-* faces that DESIGN.md filed under Retiring at #308. The snapshot also
describes a Site Header rendered on a paper ground in serif and an Absent Marker
in serif. DESIGN.md declares bench-* tokens only, bans serif on software surfaces,
and specifies the Site Header and Absent Marker without a paper ground or serif.

These tests pin each acceptance criterion in #485's brief.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_JSON = REPO_ROOT / ".impeccable" / "design.json"

# Site faces DESIGN.md declares in place of the retired receipt-* faces.
_SITE_BENCH_FACES = ("bench-prose", "bench-h1", "bench-h2", "bench-figure")

_SERIF_PATTERNS = (
    r"font-family\s*:\s*[^;]*serif",
    r"font-family\s*:\s*[^;]*Georgia",
    r"font-family\s*:\s*[^;]*Times",
)

_PAPER_PATTERNS = (
    r"background\s*:\s*#fbfbf9",
    r"background\s*:\s*var\(--receipt-paper\)",
    r"#fbfbf9",
)

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(DESIGN_JSON.read_text(encoding="utf-8"))
    return result


@pytest.fixture(scope="module")
def color_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = snapshot["extensions"]["colorMeta"]
    return result


@pytest.fixture(scope="module")
def typo_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = snapshot["extensions"]["typographyMeta"]
    return result


@pytest.fixture(scope="module")
def components(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = snapshot["components"]
    return result


@pytest.fixture(scope="module")
def site_header(components: list[dict[str, Any]]) -> dict[str, Any]:
    for c in components:
        if c["refersTo"] == "site-header":
            return c
    raise AssertionError("Site Header component not found in snapshot")


@pytest.fixture(scope="module")
def absent_marker(components: list[dict[str, Any]]) -> dict[str, Any]:
    for c in components:
        if c["refersTo"] == "absent-marker":
            return c
    raise AssertionError("Absent Marker component not found in snapshot")


def _css(component: dict[str, Any]) -> str:
    result = component.get("css", "")
    assert isinstance(result, str)
    return result


# -- Criterion 1: No retired receipt-* tokens survive in the snapshot ----------


class TestReceiptTokensRemoved:
    """A search of the snapshot for the retired token prefix returns nothing."""

    def test_no_receipt_color_tokens(self, color_meta: dict[str, Any]) -> None:
        receipt_keys = [k for k in color_meta if k.startswith("receipt-")]
        assert receipt_keys == [], f"retired receipt-* colour tokens remain: {receipt_keys}"

    def test_no_receipt_typography_tokens(self, typo_meta: dict[str, Any]) -> None:
        receipt_keys = [k for k in typo_meta if k.startswith("receipt-")]
        assert receipt_keys == [], f"retired receipt-* typography tokens remain: {receipt_keys}"

    def test_no_receipt_anywhere_in_snapshot_json(self, snapshot: dict[str, Any]) -> None:
        del snapshot  # fixture ensures file parses; search the raw bytes
        raw = DESIGN_JSON.read_text(encoding="utf-8")
        matches = re.findall(r'"receipt-[\w-]+"', raw)
        assert matches == [], f"receipt-* tokens found in snapshot: {matches}"


# -- Criterion 2: Site Header declares no serif family and no paper ground ----


class TestSiteHeader:
    """The site header declares no serif family and no paper ground."""

    def test_no_serif_family(self, site_header: dict[str, Any]) -> None:
        css = _css(site_header)
        for pat in _SERIF_PATTERNS:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Site Header declares a serif family: matched {pat!r} in CSS"
            )

    def test_no_paper_ground(self, site_header: dict[str, Any]) -> None:
        css = _css(site_header)
        for pat in _PAPER_PATTERNS:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Site Header declares a paper ground: matched {pat!r} in CSS"
            )

    def test_links_are_ink_not_navy(self, site_header: dict[str, Any]) -> None:
        """DESIGN.md: nav links in Ink; retired Certificate Navy must not return."""
        css = _css(site_header)
        assert "#1f4f82" not in css.lower(), "Site Header still uses retired Certificate Navy"
        assert re.search(r"color\s*:\s*inherit", css, re.IGNORECASE), (
            "Site Header links must inherit Ink, not carry a chromatic accent"
        )


# -- Criterion 3: Absent Marker declares no serif family, retains italic ------


class TestAbsentMarker:
    """The absent marker declares no serif family and retains italic."""

    def test_no_serif_family(self, absent_marker: dict[str, Any]) -> None:
        css = _css(absent_marker)
        for pat in _SERIF_PATTERNS:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Absent Marker declares a serif family: matched {pat!r} in CSS"
            )

    def test_retains_italic(self, absent_marker: dict[str, Any]) -> None:
        css = _css(absent_marker)
        assert re.search(r"font-style\s*:\s*italic", css, re.IGNORECASE), (
            "Absent Marker lost its font-style: italic"
        )

    def test_not_coloured(self, absent_marker: dict[str, Any]) -> None:
        css = _css(absent_marker)
        colour_patterns = [
            r"color\s*:\s*#[0-9a-f]+",
            r"color\s*:\s*var\(--bench-\w+\)",
        ]
        for pat in colour_patterns:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Absent Marker has an explicit colour: matched {pat!r} in CSS"
            )


# -- Criterion 4: Snapshot declares only bench-* tokens; matches what tree draws


class TestBenchTokensOnly:
    """Every colour and typography token in the snapshot is a bench-* token."""

    def test_all_colour_tokens_are_bench(self, color_meta: dict[str, Any]) -> None:
        for key in color_meta:
            assert key.startswith("bench-"), f"non-bench colour token: {key}"

    def test_all_typography_tokens_are_bench(self, typo_meta: dict[str, Any]) -> None:
        for key in typo_meta:
            assert key.startswith("bench-"), f"non-bench typography token: {key}"

    def test_cant_tell_declared_for_refusal_edge(self, color_meta: dict[str, Any]) -> None:
        """#308 moved the refusal edge onto bench-cant-tell; the snapshot must name it."""
        assert "bench-cant-tell" in color_meta, "bench-cant-tell missing from colorMeta"
        canonical = color_meta["bench-cant-tell"]["canonical"]
        assert canonical.lower() == "#58a6ff", f"bench-cant-tell canonical is {canonical!r}"

    def test_site_faces_replace_retired_receipt_faces(self, typo_meta: dict[str, Any]) -> None:
        """Removing receipt-* faces without the bench site faces leaves the type ramp empty."""
        missing = [name for name in _SITE_BENCH_FACES if name not in typo_meta]
        assert missing == [], f"site bench faces missing from typographyMeta: {missing}"

    def test_component_css_hex_literals_are_declared(
        self, components: list[dict[str, Any]], color_meta: dict[str, Any]
    ) -> None:
        """Component tiles must not draw a hex the snapshot's palette does not name."""
        declared = {str(meta["canonical"]).lower() for meta in color_meta.values()}
        undeclared: list[str] = []
        for component in components:
            css = _css(component)
            for match in _HEX_RE.finditer(css):
                literal = match.group(0).lower()
                if literal not in declared:
                    undeclared.append(f"{component['refersTo']}:{literal}")
        assert undeclared == [], f"component CSS hex not in colorMeta: {undeclared}"


# -- Desired behaviour: no software surface draws serif or paper ground --------


class TestNoComponentDrawsPaperSurface:
    """Desired behavior: no component renders a serif face or a paper ground."""

    def test_no_component_css_declares_serif(self, components: list[dict[str, Any]]) -> None:
        offenders: list[str] = []
        for component in components:
            css = _css(component)
            for pat in _SERIF_PATTERNS:
                if re.search(pat, css, re.IGNORECASE):
                    offenders.append(f"{component['refersTo']}:{pat}")
        assert offenders == [], f"component CSS still declares serif: {offenders}"

    def test_no_component_css_draws_paper_ground(self, components: list[dict[str, Any]]) -> None:
        offenders: list[str] = []
        for component in components:
            css = _css(component)
            for pat in _PAPER_PATTERNS:
                if re.search(pat, css, re.IGNORECASE):
                    offenders.append(f"{component['refersTo']}:{pat}")
        assert offenders == [], f"component CSS still draws paper ground: {offenders}"


class TestNarrativeDropsPaperDualSystem:
    """narrative.overview and rules must not keep the retired two-system claim."""

    def test_overview_does_not_claim_two_systems(self, snapshot: dict[str, Any]) -> None:
        overview = snapshot["narrative"]["overview"]
        assert "two distinct visual systems" not in overview.lower()
        assert "open owner decision" not in overview.lower()
        assert "issue #216" not in overview

    def test_mono_rule_does_not_endorse_serif(self, snapshot: dict[str, Any]) -> None:
        rules = snapshot["narrative"]["rules"]
        mono = next(r for r in rules if r["name"] == "The Mono-Carries-The-Claim Rule")
        body = mono["body"]
        assert "serif" not in body.lower(), (
            "Mono-Carries rule still endorses serif after paper retirement"
        )
        assert "both surfaces" not in body.lower(), (
            "Mono-Carries rule still refers to two surfaces after paper retirement"
        )
