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
        raw = DESIGN_JSON.read_text(encoding="utf-8")
        # Search for the receipt- prefix in any JSON key or value.
        matches = re.findall(r'"receipt-[\w-]+"', raw)
        assert matches == [], f"receipt-* tokens found in snapshot: {matches}"


# -- Criterion 2: Site Header declares no serif family and no paper ground ----


class TestSiteHeader:
    """The site header declares no serif family and no paper ground."""

    def _css_rules(self, header: dict[str, Any]) -> str:
        result = header.get("css", "")
        assert isinstance(result, str)
        return result

    def test_no_serif_family(self, site_header: dict[str, Any]) -> None:
        css = self._css_rules(site_header)
        # Detect generic serif or known serif families.
        serif_patterns = [
            r"font-family\s*:\s*[^;]*serif",
            r"font-family\s*:\s*[^;]*Georgia",
            r"font-family\s*:\s*[^;]*Times",
        ]
        for pat in serif_patterns:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Site Header declares a serif family: matched {pat!r} in CSS"
            )

    def test_no_paper_ground(self, site_header: dict[str, Any]) -> None:
        css = self._css_rules(site_header)
        # The paper ground is the retired receipt-paper colour.
        paper_patterns = [
            r"background\s*:\s*#fbfbf9",
            r"background\s*:\s*var\(--receipt-paper\)",
            r"#fbfbf9",
        ]
        for pat in paper_patterns:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Site Header declares a paper ground: matched {pat!r} in CSS"
            )


# -- Criterion 3: Absent Marker declares no serif family, retains italic ------


class TestAbsentMarker:
    """The absent marker declares no serif family and retains italic."""

    def _css_rules(self, marker: dict[str, Any]) -> str:
        result = marker.get("css", "")
        assert isinstance(result, str)
        return result

    def test_no_serif_family(self, absent_marker: dict[str, Any]) -> None:
        css = self._css_rules(absent_marker)
        serif_patterns = [
            r"font-family\s*:\s*[^;]*serif",
            r"font-family\s*:\s*[^;]*Georgia",
            r"font-family\s*:\s*[^;]*Times",
        ]
        for pat in serif_patterns:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Absent Marker declares a serif family: matched {pat!r} in CSS"
            )

    def test_retains_italic(self, absent_marker: dict[str, Any]) -> None:
        css = self._css_rules(absent_marker)
        assert re.search(r"font-style\s*:\s*italic", css, re.IGNORECASE), (
            "Absent Marker lost its font-style: italic"
        )

    def test_not_coloured(self, absent_marker: dict[str, Any]) -> None:
        css = self._css_rules(absent_marker)
        # DESIGN.md says an absent marker is uncoloured: no explicit colour.
        colour_patterns = [
            r"color\s*:\s*#[0-9a-f]+",
            r"color\s*:\s*var\(--bench-\w+\)",
        ]
        for pat in colour_patterns:
            assert not re.search(pat, css, re.IGNORECASE), (
                f"Absent Marker has an explicit colour: matched {pat!r} in CSS"
            )


# -- Criterion 4: Snapshot declares only bench-* tokens -----------------------


class TestBenchTokensOnly:
    """Every colour and typography token in the snapshot is a bench-* token."""

    def test_all_colour_tokens_are_bench(self, color_meta: dict[str, Any]) -> None:
        for key in color_meta:
            assert key.startswith("bench-"), f"non-bench colour token: {key}"

    def test_all_typography_tokens_are_bench(self, typo_meta: dict[str, Any]) -> None:
        for key in typo_meta:
            assert key.startswith("bench-"), f"non-bench typography token: {key}"
