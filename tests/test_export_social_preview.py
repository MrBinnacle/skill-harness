"""The social-preview export reads its render size from the SVG's viewBox.

The browser render itself needs Chromium and is exercised by running the
script; these tests pin the size contract, which decides whether the PNG is
cropped, padded or exact.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "export_social_preview.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_social_preview", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_live_social_preview_renders_at_1280x640() -> None:
    module = _load()
    svg = (REPO_ROOT / "assets" / "social-preview.svg").read_text(encoding="utf-8")
    assert module.read_viewbox(svg) == (1280, 640)


@pytest.mark.parametrize(
    "root",
    [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640">',
        '<svg viewBox="10 0 1280 640">',
        '<svg width="1200" height="640" viewBox="0 0 1280 640">',
    ],
)
def test_a_size_the_screenshot_would_crop_or_pad_is_refused(root: str) -> None:
    module = _load()
    with pytest.raises(ValueError):
        module.read_viewbox(root + "</svg>")
