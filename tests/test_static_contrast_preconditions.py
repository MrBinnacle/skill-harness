"""The precondition that makes static WCAG contrast reasoning sound on these surfaces.

Reading a contrast ratio out of stylesheet literals is only valid while every
colour a glyph is painted against is itself stated as a literal. Alpha
compositing, gradients, background images, blend modes, filters and
``currentColor`` each break that, which is why axe-core returns ``incomplete``
rather than a ratio when it meets one. W3C's Understanding text for SC 1.4.3
admits colours taken from "the underlying markup and stylesheets" as evidence,
so the admissibility is a property of the file, not of the method. This gate
holds that property.

When one of these constructs is genuinely needed, the intended escape is to
render the page and measure the composited pixels, never to loosen this file.

Each hazard is a row carrying its name, its detector and the sentence saying
why its presence invalidates the inference. The scanner is one function over a
path list, so the fixtures under ``tests/fixtures/static_contrast/`` and the
live tree run through the same code, and the comment blanking, line numbering
and surface list come from ``test_design_tokens_conformance``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.test_design_tokens_conformance import (
    REPO_ROOT,
    _line_number,
    _strip_comments,
    live_surface_paths,
)

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "static_contrast"

_ALPHA_CAPABLE_FUNCTIONS = "rgb|hsl|hwb|lab|lch|oklab|oklch|color"


@dataclass(frozen=True)
class Hazard:
    name: str
    pattern: re.Pattern[str]
    reason: str


@dataclass(frozen=True)
class Hit:
    file: Path
    line: int
    hazard: Hazard

    def __str__(self) -> str:
        return (
            f"{self.file.as_posix()}:{self.line}: "
            f"static-contrast hazard {self.hazard.name}: {self.hazard.reason}"
        )


HAZARDS: tuple[Hazard, ...] = (
    Hazard(
        "gradient",
        re.compile(r"\b(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(", re.IGNORECASE),
        "A gradient paints a range of colours behind one run of text, so no single background "
        "literal names the colour a given glyph is composited against.",
    ),
    Hazard(
        "alpha-color-function",
        re.compile(r"\b(?:rgba|hsla)\s*\(", re.IGNORECASE),
        "An alpha channel makes the painted colour a function of whatever lies beneath it, "
        "which the stylesheet does not record.",
    ),
    Hazard(
        "slash-alpha-color",
        re.compile(rf"\b(?:{_ALPHA_CAPABLE_FUNCTIONS})\s*\([^)]*/", re.IGNORECASE),
        "The slash form of a colour function carries the same alpha channel, so the literal "
        "names a colour that is never painted on its own.",
    ),
    Hazard(
        "alpha-hex",
        # The lookbehind keeps XML numeric character references out: `&#8594;` is four
        # hex digits behind a `#`, and assets/social-preview.svg has one.
        re.compile(r"(?<!&)#(?:[0-9a-f]{8}|[0-9a-f]{4})(?![0-9a-z_-])", re.IGNORECASE),
        "A four- or eight-digit hex literal carries an alpha channel, so the rendered colour "
        "is a composite the literal does not describe.",
    ),
    Hazard(
        "opacity",
        re.compile(r"\bopacity\s*[:=]", re.IGNORECASE),
        "An opacity declaration composites the element and its descendants against their "
        "backdrop, so a descendant's own colour literal stops describing what is rendered.",
    ),
    Hazard(
        "background-image",
        re.compile(r"\bbackground-image\s*:|\burl\s*\(|<image\b", re.IGNORECASE),
        "An image behind text puts arbitrary pixels under the glyphs, and no literal in the "
        "file bounds their luminance.",
    ),
    Hazard(
        "current-color",
        re.compile(r"\bcurrentcolor\b", re.IGNORECASE),
        "currentColor resolves to whatever colour was inherited at the point of use, so the "
        "declaration site does not determine the painted value.",
    ),
    Hazard(
        "blend-mode",
        re.compile(r"\b(?:mix|background)-blend-mode\s*[:=]", re.IGNORECASE),
        "A blend mode derives the rendered colour from the element and its backdrop together, "
        "so neither literal alone is the result.",
    ),
    Hazard(
        "filter",
        re.compile(r"\b(?:backdrop-)?filter\s*[:=]|<filter\b", re.IGNORECASE),
        "A filter transforms pixels after the cascade has resolved, so the resolved colour is "
        "not the displayed colour.",
    ),
    Hazard(
        "computed-color",
        re.compile(r"\bcolor-mix\s*\(", re.IGNORECASE),
        "color-mix() produces a colour that no literal in the file states, so the value "
        "reaching the screen is not present to be read.",
    ),
)


def scan_for_hazards(paths: list[Path]) -> list[Hit]:
    """The one scanner. Fixtures and the live tree both come through here."""
    hits: list[Hit] = []
    for path in paths:
        text = _strip_comments(path, path.read_text(encoding="utf-8"))
        for hazard in HAZARDS:
            hits.extend(
                Hit(path, _line_number(text, match.start()), hazard)
                for match in hazard.pattern.finditer(text)
            )
    return sorted(hits, key=lambda hit: (hit.file.as_posix(), hit.line, hit.hazard.name))


def _relative(hits: list[Hit]) -> list[str]:
    out: list[str] = []
    for hit in hits:
        try:
            file = hit.file.relative_to(REPO_ROOT)
        except ValueError:
            file = hit.file
        out.append(str(Hit(file, hit.line, hit.hazard)))
    return out


def test_live_surfaces_admit_static_contrast_reasoning() -> None:
    paths = live_surface_paths()
    assert HAZARDS, "an empty hazard table would make this gate vacuous"
    assert len(paths) > 1, "no assets/*.svg found"
    for path in paths:
        assert path.is_file(), path
    hits = _relative(scan_for_hazards(paths))
    assert hits == [], (
        "static contrast reasoning is no longer sound on these surfaces; render and measure "
        "instead of loosening this gate:\n" + "\n".join(hits)
    )


_POISON_CASES: list[tuple[str, str]] = [
    ("hazard_gradient.css", "gradient"),
    ("hazard_alpha_color_function.css", "alpha-color-function"),
    ("hazard_slash_alpha_color.css", "slash-alpha-color"),
    ("hazard_alpha_hex.svg", "alpha-hex"),
    ("hazard_opacity.svg", "opacity"),
    ("hazard_background_image.css", "background-image"),
    ("hazard_current_color.css", "current-color"),
    ("hazard_blend_mode.css", "blend-mode"),
    ("hazard_filter.svg", "filter"),
    ("hazard_computed_color.css", "computed-color"),
]


@pytest.mark.parametrize(("fixture", "hazard_name"), _POISON_CASES)
def test_poison_fixture_is_flagged_naming_hazard_file_line_and_reason(
    fixture: str, hazard_name: str
) -> None:
    path = FIXTURES_DIR / fixture
    hits = scan_for_hazards([path])
    assert hits, f"{fixture}: poison fixture produced no hit"
    messages = [str(hit) for hit in hits]
    assert {hit.hazard.name for hit in hits} == {hazard_name}, (
        f"{fixture}: a poison fixture carries exactly one hazard: {messages}"
    )
    hazard = next(h for h in HAZARDS if h.name == hazard_name)
    for hit, message in zip(hits, messages, strict=True):
        assert hit.file == path
        assert hit.line > 0
        assert fixture in message
        assert hazard_name in message
        assert hazard.reason in message


def test_every_hazard_has_a_poison_fixture() -> None:
    assert {hazard.name for hazard in HAZARDS} == {name for _, name in _POISON_CASES}


@pytest.mark.parametrize("fixture", ["clean.css", "clean.svg"])
def test_clean_fixture_passes(fixture: str) -> None:
    assert scan_for_hazards([FIXTURES_DIR / fixture]) == []
