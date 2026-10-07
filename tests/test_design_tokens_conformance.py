"""Design-token conformance: the fence DESIGN.md sets around the public surfaces.

DESIGN.md's YAML frontmatter is the one declared token block for this
repository. This test reads it (no pyyaml -- not a declared dependency; the
block's shape is `key: "value"  # comment` at fixed indents, parsed by regex
the same way ``test_structural_bans`` reads ``.pre-commit-config.yaml``) and
asserts that every colour literal, every ``font-family`` value and every
``font-size`` value in the site stylesheet and the committed SVG assets is a
declared value.

A token DESIGN.md marks as retiring (a trailing comment naming the ticket that
removes it) is still declared here until that ticket removes it from the block.
The fence tightens by editing DESIGN.md, never this file.

Scope, stated exactly: colours (``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` and
``rgb()`` / ``rgba()``), ``font-family`` values and ``font-size`` values.
Spacing, radius and weight tokens are declared in the same block and are not
checked here (skill-harness#307 names the three classes above).

The scanner is one function over a path list, so the poison fixtures under
``tests/fixtures/design_tokens/`` and the live tree run through the same code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_MD = REPO_ROOT / "DESIGN.md"
STYLE_CSS = REPO_ROOT / "src" / "skill_harness" / "sitegen" / "style.css"
ASSETS_DIR = REPO_ROOT / "assets"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "design_tokens"

COLOR = "color"
FONT_FAMILY = "font-family"
FONT_SIZE = "font-size"

# One frontmatter line: indent, key, then either a double-quoted value (with
# backslash escapes, so `\"Liberation Mono\"` survives) or a bare scalar, then
# an optional `# comment`. The quoted alternative must come first: a hex colour
# inside quotes starts with `#` and would otherwise be eaten as a comment.
_FRONTMATTER_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[\w-]+):\s*"
    r'(?:"(?P<quoted>(?:[^"\\]|\\.)*)"|(?P<bare>[^#\s][^#]*?))?'
    r"\s*(?:#.*)?$"
)
_HEX_RE = re.compile(r"#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3})(?![0-9a-z_-])", re.IGNORECASE)
_RGB_RE = re.compile(r"\brgba?\([^)]*\)", re.IGNORECASE)
_CSS_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*(?P<value>[^;}]+)", re.IGNORECASE)
_CSS_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(?P<value>[^;}]+)", re.IGNORECASE)
_SVG_FONT_FAMILY_ATTR_RE = re.compile(r"""font-family\s*=\s*(?P<q>["'])(?P<value>.*?)(?P=q)""")
_SVG_FONT_SIZE_ATTR_RE = re.compile(r"""font-size\s*=\s*(?P<q>["'])(?P<value>.*?)(?P=q)""")
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_UNITLESS_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class DeclaredTokens:
    """The three token classes the conformance check reads from DESIGN.md."""

    colors: frozenset[str]
    font_families: frozenset[str]
    font_sizes: frozenset[str]


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    token_class: str
    literal: str

    def __str__(self) -> str:
        return f"{self.file.as_posix()}:{self.line}: undeclared {self.token_class} {self.literal!r}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blank_spans(text: str, pattern: re.Pattern[str]) -> str:
    """Blank matches in place (newlines kept) so offsets still map to real lines."""

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return pattern.sub(blank, text)


def normalize_color(literal: str) -> str:
    return re.sub(r"\s+", "", literal).lower()


def normalize_font_family(value: str) -> str:
    """Per-family: strip whitespace and quotes; join with a single comma.

    ``"SFMono-Regular"`` and ``SFMono-Regular`` name the same family in CSS,
    and the SVG stacks omit the space after each comma; neither difference is
    a design-token difference.
    """
    families = [family.strip().strip("\"'").strip() for family in value.split(",")]
    return ",".join(family.lower() for family in families if family)


def normalize_font_size(value: str) -> str:
    """Lower-case, whitespace stripped; a unitless SVG user-unit size is px."""
    size = re.sub(r"\s+", "", value).lower()
    if _UNITLESS_NUMBER_RE.match(size):
        size += "px"
    return size


def _unescape_yaml_double_quoted(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def _frontmatter_lines(design_md_text: str) -> list[str]:
    lines = design_md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        msg = f"{DESIGN_MD.name}: no YAML frontmatter opening '---' on line 1"
        raise ValueError(msg)
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    msg = f"{DESIGN_MD.name}: frontmatter opened on line 1 and never closed"
    raise ValueError(msg)


def parse_declared_tokens(design_md_text: str) -> DeclaredTokens:
    """Read the `colors:` and `typography:` blocks out of DESIGN.md's frontmatter.

    Raises ``ValueError`` when the block is missing, a line does not match the
    one shape the block uses, or a class ends up empty: an empty declared set
    would make every literal a violation and read as a broken tree rather than
    a broken parse.
    """
    colors: set[str] = set()
    families: set[str] = set()
    sizes: set[str] = set()
    section: str | None = None
    for raw_line in _frontmatter_lines(design_md_text):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = _FRONTMATTER_LINE_RE.match(raw_line)
        if match is None:
            msg = f"{DESIGN_MD.name}: frontmatter line does not parse: {raw_line!r}"
            raise ValueError(msg)
        indent = len(match.group("indent"))
        key = match.group("key")
        quoted = match.group("quoted")
        value = _unescape_yaml_double_quoted(quoted) if quoted is not None else match.group("bare")
        if indent == 0:
            section = key
            continue
        if section == "colors" and indent == 2 and value is not None:
            colors.add(normalize_color(value))
        elif section == "typography" and indent == 4 and value is not None:
            if key == "fontFamily":
                families.add(normalize_font_family(value))
            elif key == "fontSize":
                sizes.add(normalize_font_size(value))
    for name, declared in (("colors", colors), ("fontFamily", families), ("fontSize", sizes)):
        if not declared:
            msg = f"{DESIGN_MD.name}: frontmatter declares no {name} values"
            raise ValueError(msg)
    return DeclaredTokens(frozenset(colors), frozenset(families), frozenset(sizes))


def _strip_comments(path: Path, text: str) -> str:
    if path.suffix.lower() == ".svg":
        return _blank_spans(text, _XML_COMMENT_RE)
    return _blank_spans(text, _CSS_COMMENT_RE)


def _scan_text(path: Path, text: str, declared: DeclaredTokens) -> list[Violation]:
    text = _strip_comments(path, text)
    found: list[Violation] = []

    for pattern in (_HEX_RE, _RGB_RE):
        for match in pattern.finditer(text):
            literal = match.group(0)
            if normalize_color(literal) not in declared.colors:
                found.append(Violation(path, _line_number(text, match.start()), COLOR, literal))

    family_patterns: tuple[re.Pattern[str], ...] = (_CSS_FONT_FAMILY_RE,)
    size_patterns: tuple[re.Pattern[str], ...] = (_CSS_FONT_SIZE_RE,)
    if path.suffix.lower() == ".svg":
        family_patterns = (_CSS_FONT_FAMILY_RE, _SVG_FONT_FAMILY_ATTR_RE)
        size_patterns = (_CSS_FONT_SIZE_RE, _SVG_FONT_SIZE_ATTR_RE)

    for pattern in family_patterns:
        for match in pattern.finditer(text):
            literal = match.group("value").strip()
            if normalize_font_family(literal) not in declared.font_families:
                line = _line_number(text, match.start("value"))
                found.append(Violation(path, line, FONT_FAMILY, literal))

    for pattern in size_patterns:
        for match in pattern.finditer(text):
            literal = match.group("value").strip()
            if normalize_font_size(literal) not in declared.font_sizes:
                line = _line_number(text, match.start("value"))
                found.append(Violation(path, line, FONT_SIZE, literal))

    return sorted(found, key=lambda v: (v.line, v.token_class, v.literal))


def scan_for_undeclared_tokens(paths: list[Path], declared: DeclaredTokens) -> list[Violation]:
    """The one scanner. Poison fixtures and the live tree both come through here."""
    violations: list[Violation] = []
    for path in paths:
        violations.extend(_scan_text(path, path.read_text(encoding="utf-8"), declared))
    return violations


def _relative(violations: list[Violation]) -> list[str]:
    out: list[str] = []
    for violation in violations:
        try:
            file = violation.file.relative_to(REPO_ROOT)
        except ValueError:
            file = violation.file
        out.append(str(Violation(file, violation.line, violation.token_class, violation.literal)))
    return out


def live_surface_paths() -> list[Path]:
    """style.css plus every ``assets/*.svg`` (the same glob the public-copy scanner uses)."""
    return [STYLE_CSS, *sorted(ASSETS_DIR.glob("*.svg"))]


@pytest.fixture(scope="module")
def declared() -> DeclaredTokens:
    return parse_declared_tokens(DESIGN_MD.read_text(encoding="utf-8"))


def test_design_md_frontmatter_declares_all_three_classes(declared: DeclaredTokens) -> None:
    assert "#0d1117" in declared.colors
    assert (
        normalize_font_family(
            'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
        )
        in declared.font_families
    )
    assert "21px" in declared.font_sizes


def test_normalisation_treats_quoting_and_spacing_as_the_same_token() -> None:
    assert normalize_font_family('ui-monospace,SFMono-Regular,"Liberation Mono",monospace') == (
        normalize_font_family('ui-monospace, "SFMono-Regular", "Liberation Mono", monospace')
    )
    assert normalize_font_size("21") == "21px"
    assert normalize_font_size(" 1.25REM ") == "1.25rem"
    assert normalize_color("#E6EDF3") == "#e6edf3"


def test_live_surfaces_use_only_declared_tokens(declared: DeclaredTokens) -> None:
    paths = live_surface_paths()
    assert STYLE_CSS.is_file(), STYLE_CSS
    assert len(paths) > 1, "no assets/*.svg found"
    violations = _relative(scan_for_undeclared_tokens(paths, declared))
    assert violations == [], "undeclared design tokens on public surfaces:\n" + "\n".join(
        violations
    )


_POISON_CASES: list[tuple[str, str, str]] = [
    ("poison_color.css", COLOR, "#ff0000"),
    ("poison_color_rgb.css", COLOR, "rgba(255, 0, 0, 0.5)"),
    ("poison_color.svg", COLOR, "#ff0000"),
    ("poison_font_family.css", FONT_FAMILY, "Inter, sans-serif"),
    ("poison_font_family.svg", FONT_FAMILY, "Georgia, serif"),
    ("poison_font_size.css", FONT_SIZE, "1.3rem"),
    ("poison_font_size.svg", FONT_SIZE, "99"),
]


@pytest.mark.parametrize(("fixture", "token_class", "literal"), _POISON_CASES)
def test_poison_fixture_fails_naming_literal_file_and_class(
    declared: DeclaredTokens, fixture: str, token_class: str, literal: str
) -> None:
    path = FIXTURES_DIR / fixture
    violations = scan_for_undeclared_tokens([path], declared)
    assert violations, f"{fixture}: poison fixture produced no violation"
    messages = [str(v) for v in violations]
    assert any(
        v.token_class == token_class and v.literal == literal and v.file == path for v in violations
    ), messages
    assert [v.token_class for v in violations] == [token_class], (
        f"{fixture}: a poison fixture carries exactly one undeclared class: {messages}"
    )
    for message in messages:
        assert fixture in message
        assert token_class in message
    assert any(literal in message for message in messages)


@pytest.mark.parametrize("fixture", ["pass.css", "pass.svg"])
def test_must_pass_fixture_passes(declared: DeclaredTokens, fixture: str) -> None:
    path = FIXTURES_DIR / fixture
    assert scan_for_undeclared_tokens([path], declared) == []


def test_parser_refuses_a_file_without_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_declared_tokens("# Design System\n\nNo block here.\n")
    with pytest.raises(ValueError, match="declares no"):
        parse_declared_tokens('---\ncolors:\n  x: "#000"\n---\n')
