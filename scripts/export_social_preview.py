"""Export assets/social-preview.png from assets/social-preview.svg.

Why this exists: the PNG is the raster copy GitHub's social-preview setting
takes, and ``assets/asset-pairs.json`` pins the SVG and the PNG as a sha256
pair (drift check DC-19). Before this script the export procedure lived
nowhere in the repository, so a recolour could not be reproduced. This is the
procedure.

How it renders: headless Chromium, through Playwright, opens the SVG file
directly. The viewport is the SVG's own viewBox size (1280x640 today) and the
device scale factor is 1, so one SVG unit is one PNG pixel. The script refuses
an SVG whose width and height attributes disagree with its viewBox, because
the screenshot would then crop or pad the composition.

Fonts: the SVG names a monospace stack (``ui-monospace, SFMono-Regular,
Menlo, Consolas, "Liberation Mono", monospace``) and its text nodes stay live.
The PNG therefore depends on which of those faces the exporting machine has.
Two machines with different fonts produce different PNG bytes from the same
SVG. Re-record the pair whenever the PNG is re-exported, and export the
uploaded PNG and the recorded PNG in the same run.

Dependency: Playwright is the optional ``[geometry]`` extra in
``pyproject.toml``; no other dependency is used. Install it with
``python -m pip install -e ".[geometry]"`` and then
``python -m playwright install chromium``.

Run: ``python scripts/export_social_preview.py [--svg PATH] [--png PATH]``.
Then record the new pair: put ``sha256sum assets/social-preview.svg`` and
``sha256sum assets/social-preview.png`` into ``assets/asset-pairs.json`` and
run ``python scripts/drift_check.py``.

Exit codes: 0 = PNG written; 2 = the SVG is unreadable or its size attributes
disagree with its viewBox, or Playwright or its browser is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SVG = REPO_ROOT / "assets" / "social-preview.svg"
DEFAULT_PNG = REPO_ROOT / "assets" / "social-preview.png"

_SVG_TAG = re.compile(r"<svg\b[^>]*>", re.DOTALL)
_ATTR = r'\b{name}="([^"]*)"'


def read_viewbox(svg_text: str) -> tuple[int, int]:
    """Return the (width, height) the SVG renders at, from its viewBox.

    Raises ValueError when the root element has no viewBox, when the viewBox
    does not start at 0 0, or when explicit width/height attributes disagree
    with it.
    """
    tag = _SVG_TAG.search(svg_text)
    if tag is None:
        raise ValueError("no <svg> root element")
    root = tag.group(0)
    viewbox = re.search(_ATTR.format(name="viewBox"), root)
    if viewbox is None:
        raise ValueError("the <svg> root has no viewBox")
    parts = viewbox.group(1).split()
    if len(parts) != 4 or parts[0] != "0" or parts[1] != "0":
        raise ValueError(f"viewBox must be '0 0 W H', got {viewbox.group(1)!r}")
    width, height = int(parts[2]), int(parts[3])
    for name, expected in (("width", width), ("height", height)):
        attr = re.search(_ATTR.format(name=name), root)
        if attr is not None and attr.group(1) != str(expected):
            raise ValueError(f"{name}={attr.group(1)!r} disagrees with the viewBox ({expected})")
    return width, height


def export(svg_path: Path, png_path: Path) -> tuple[int, int]:
    """Render svg_path to png_path at its viewBox size, device scale factor 1."""
    width, height = read_viewbox(svg_path.read_text(encoding="utf-8"))
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height}, device_scale_factor=1
            )
            page.goto(svg_path.resolve().as_uri())
            page.screenshot(
                path=str(png_path),
                clip={"x": 0, "y": 0, "width": width, "height": height},
            )
        finally:
            browser.close()
    return width, height


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the social-preview PNG from its SVG.")
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--png", type=Path, default=DEFAULT_PNG)
    args = parser.parse_args(argv)
    try:
        width, height = export(args.svg, args.png)
    except (OSError, ValueError) as exc:
        print(f"EXPORT: REFUSED - {exc}", file=sys.stderr)
        return 2
    except ImportError:
        print(
            "EXPORT: REFUSED - Playwright is missing; install the [geometry] extra",
            file=sys.stderr,
        )
        return 2
    print(f"EXPORT: wrote {args.png} at {width}x{height}, device scale factor 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
