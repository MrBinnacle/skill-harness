"""Pytest-visible structural bans mirrored in pre-commit and CI.

These do not read `.pre-commit-config.yaml` for the BAN patterns themselves —
pygrep's matching and Python's `re` differ slightly, and the point is an
independent second check, not a parser for the hook config. Keep the patterns
and exemption/allowlist sets here in sync with `.pre-commit-config.yaml`'s
`ban-raw-sqlite-connect`, `ban-raw-oracle-verdicts`, and
`ban-timestamp-final-order-by` hooks by hand; the CI
job that actually runs those hooks (`.github/workflows/ci.yml`
`structural-bans`) is the enforcement of record — this file exists so a
violation shows up in the ordinary `pytest -m "not live"` loop too, without
waiting on pre-commit/CI.

The public-copy guard is field-aware, so it cannot be expressed as a pygrep
pattern: only ``project.description`` is public PyPI copy, only SVG ``<text>``
content is in scope, and the kind-precision rule needs a multi-line context
window. Its pre-commit hook therefore invokes this module's zero-dependency
scanner directly instead of maintaining a second, weaker pattern/allowlist.

F-8 (S55 hostile review): the by-hand sync above was previously unchecked —
nothing caught the two allowlists drifting apart. `test_exclude_lists_match_pre_commit_config`
below is a diff-only cross-check: it extracts each hook's `exclude:` regex
straight out of `.pre-commit-config.yaml` by string search (no pyyaml — not a
declared project dependency; see F-8 finding notes) and asserts it matches
the SAME set of files as this module's Python-side exemption/allowlist, by
running both against every real .py file in scope. Neither side is made
authoritative by this test — it only fails loudly on divergence.
"""

from __future__ import annotations

import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SQLITE_CONNECT_RE = re.compile(r"sqlite3\.connect\(")
_SQLITE_CONNECT_EXEMPT = {
    REPO_ROOT / "src" / "skill_harness" / "storage" / "migrations.py",
}

_ORACLE_VERDICTS_RE = re.compile(r"(?i)from\s+oracle_verdicts")
# Mirrors PRD.md #17's documented allowlist: none of these read `observation`
# from the raw table to feed statistical aggregation (that is admissible_verdicts
# VIEW-only) — audit/ is cross-reference/inspection; the rest are single-row
# provenance copies, resume-state rebuilds, or single-verdict operator lookups.
_ORACLE_VERDICTS_ALLOWLIST = {
    REPO_ROOT / "src" / "skill_harness" / "audit" / "__init__.py",
    REPO_ROOT / "src" / "skill_harness" / "aggregation" / "engine.py",
    REPO_ROOT / "src" / "skill_harness" / "ablation" / "runner.py",
    REPO_ROOT / "src" / "skill_harness" / "cli" / "main.py",
    REPO_ROOT
    / "src"
    / "skill_harness"
    / "storage"
    / "repositories"
    / "evidence"
    / "frozen_cases.py",
}

# E3: an ORDER BY whose FINAL sort key is timestamp-shaped (*_at, ts,
# last_updated) leaves tie order to the implicit rowid, which is NOT stable
# across dump/restore/VACUUM on append-only tables. Every such clause must
# carry a trailing unique key (the table's PRIMARY KEY or a unique-in-scope
# column). Matched per line, mirroring pygrep's default line semantics.
_TS_FINAL_ORDER_BY_RE = re.compile(
    r"(?i)ORDER\s+BY\s+[\w.,\s]*\b(\w+_at|ts|last_updated)\b(\s+(ASC|DESC))?\s*[\"']?,?\s*$"
)
# No exemptions today; mirrors ban-timestamp-final-order-by's `exclude: '^$'`.
_TS_FINAL_ORDER_BY_EXEMPT: set[Path] = set()

_THIS_FILE = Path(__file__).resolve()

# Public copy excludes only immutable historical records. These files preserve
# the wording used when their plans/observations were registered; changing that
# wording retroactively would falsify the record. Current docs, including the
# PRD and current case studies, are deliberately not exempt.
_PUBLIC_COPY_EXCLUDED = {
    Path("docs/PLAN.md"),
    Path("docs/findings/v0.2-preregistration.md"),
    Path("docs/findings/v0.2-reaim-gate.md"),
    Path("docs/observations/OBS-0001-fts5-notes-search-v1.md"),
    Path("docs/observations/OBS-0002-fts5-notes-search-v2.md"),
    Path("docs/observations/OBS-0003-sqlite-tie-break-red-test-trap.md"),
    Path("docs/observations/OBS-0004-bayesian-eval-discipline.md"),
    Path("docs/observations/OBS-0005-append-only-evidence-design.md"),
    Path("docs/observations/OBS-0006-llm-judge-calibration.md"),
}

_BARE_ADMISSIBILITY_RE = re.compile(r"(?<!evidence )(?<!evidence-)\badmissibility\b", re.IGNORECASE)
_EARN_FAMILY_RE = re.compile(r"\bearn(?:s|ed|ing)?\b", re.IGNORECASE)
_KIND_PRECISION_AGGREGATE_RE = re.compile(
    r"\b0\.835\b|\bkind[ -]precision\b[^\n.!?]{0,40}\b83\.5(?:%|\s+percent\b)",
    re.IGNORECASE,
)
_RECALL_RE = re.compile(r"\brecall\b", re.IGNORECASE)
_UNMEASURED_RE = re.compile(r"\bunmeasured\b", re.IGNORECASE)
_KIND_CONTEXT_LINES = 2
_SITE_TEMPLATE_SUFFIXES = {
    ".htm",
    ".html",
    ".j2",
    ".jinja",
    ".jinja2",
    ".liquid",
    ".mustache",
    ".njk",
    ".tmpl",
}


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _sentence_at(text: str, offset: int) -> str:
    start = max(text.rfind(mark, 0, offset) for mark in ".!?") + 1
    endings = [position for mark in ".!?" if (position := text.find(mark, offset)) >= 0]
    end = min(endings) if endings else len(text)
    return text[start:end]


def _public_copy_violations(text: str) -> list[str]:
    violations = [
        f"bare gate term at line {_line_number(text, match.start())}"
        for match in _BARE_ADMISSIBILITY_RE.finditer(text)
    ]
    violations.extend(
        f"earn/earned family at line {_line_number(text, match.start())}"
        for match in _EARN_FAMILY_RE.finditer(text)
    )

    lines = text.splitlines() or [text]
    for match in _KIND_PRECISION_AGGREGATE_RE.finditer(text):
        lineno = _line_number(text, match.start())
        start = max(0, lineno - 1 - _KIND_CONTEXT_LINES)
        end = min(len(lines), lineno + _KIND_CONTEXT_LINES)
        context = "\n".join(lines[start:end])
        if "77/78" not in context or "4/20" not in context:
            violations.append(f"bare kind-precision aggregate at line {lineno}")

    for match in _RECALL_RE.finditer(text):
        if not _UNMEASURED_RE.search(_sentence_at(text, match.start())):
            violations.append(
                f"recall not stated as UNMEASURED at line {_line_number(text, match.start())}"
            )
    return violations


def _svg_text(svg: str) -> str:
    root = ET.fromstring(svg)
    text_nodes: list[str] = []

    def collect(element: ET.Element) -> None:
        if element.tag.rsplit("}", 1)[-1] in {"script", "style"}:
            return
        if element.text:
            text_nodes.append(element.text)
        for child in element:
            collect(child)
            if child.tail:
                text_nodes.append(child.tail)

    collect(root)
    return "".join(text_nodes)


def _site_template_files(repo_root: Path) -> list[Path]:
    roots = (
        repo_root / "templates",
        repo_root / "site" / "templates",
        repo_root / "src" / "skill_harness" / "sitegen",
    )
    return sorted(
        {
            path
            for root in roots
            if root.is_dir()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in _SITE_TEMPLATE_SUFFIXES
        }
    )


def _public_surface_texts(repo_root: Path) -> list[tuple[str, str]]:
    surfaces: list[tuple[str, str]] = []
    readme = repo_root / "README.md"
    if readme.is_file():
        surfaces.append(("README.md", readme.read_text(encoding="utf-8")))

    docs = repo_root / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md")):
            relative_doc = path.relative_to(repo_root)
            if relative_doc not in _PUBLIC_COPY_EXCLUDED:
                surfaces.append((relative_doc.as_posix(), path.read_text(encoding="utf-8")))

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        description = project.get("description")
        if isinstance(description, str):
            surfaces.append(("pyproject.toml:[project].description", description))

    assets = repo_root / "assets"
    if assets.is_dir():
        for path in sorted(assets.glob("*.svg")):
            relative_svg = path.relative_to(repo_root).as_posix()
            svg = _svg_text(path.read_text(encoding="utf-8"))
            surfaces.append((f"{relative_svg}:text", svg))

    for path in _site_template_files(repo_root):
        relative_template = path.relative_to(repo_root).as_posix()
        surfaces.append((relative_template, path.read_text(encoding="utf-8")))
    return surfaces


def _repo_public_copy_violations(repo_root: Path) -> list[str]:
    return [
        f"{surface}: {violation}"
        for surface, text in _public_surface_texts(repo_root)
        for violation in _public_copy_violations(text)
    ]


def _iter_py_files(*roots: str) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_no_raw_sqlite3_connect_outside_migrations() -> None:
    """A23 Sec.3: sqlite3.connect() bypasses connection-scoped pragmas
    (foreign_keys, synchronous, busy_timeout, WAL). Only migrations.py --
    the module that DEFINES open_db() -- may call it directly; everyone else
    (including tests) must go through open_db()/open_evidence()/open_runtime().
    """
    violations = []
    for path in _iter_py_files("src", "tests"):
        if path in _SQLITE_CONNECT_EXEMPT or path == _THIS_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        if _SQLITE_CONNECT_RE.search(text):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == [], f"raw sqlite3.connect() outside migrations.py: {violations}"


def test_oracle_verdicts_raw_access_matches_documented_allowlist() -> None:
    """A29/E2: raw reads of oracle_verdicts (bypassing the admissible_verdicts
    VIEW) are confined to the allowlist documented in PRD.md #17. A new
    production module hitting this pattern must be added here AND to
    .pre-commit-config.yaml's ban-raw-oracle-verdicts exclude list AND to the
    PRD wording -- or, preferably, routed through the VIEW or a repository
    function instead of being added to the list.
    """
    unexpected = []
    for path in _iter_py_files("src"):
        if path in _ORACLE_VERDICTS_ALLOWLIST or path == _THIS_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        if _ORACLE_VERDICTS_RE.search(text):
            unexpected.append(str(path.relative_to(REPO_ROOT)))
    assert unexpected == [], f"raw oracle_verdicts access outside allowlist: {unexpected}"


def test_no_timestamp_final_order_by_without_tiebreak() -> None:
    """E3: timestamp-only ORDER BY on append-only tables is non-deterministic
    among ties -- SQLite's implicit rowid tie-break does not survive
    dump/restore/VACUUM. A clause whose final sort key ends with `_at`, or is
    `ts`/`last_updated`, must append a unique tie-break key matching the
    timestamp key's direction (e.g. `ORDER BY started_at, run_id`).
    """
    violations = []
    for path in _iter_py_files("src"):
        if path in _TS_FINAL_ORDER_BY_EXEMPT:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if _TS_FINAL_ORDER_BY_RE.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert violations == [], (
        f"ORDER BY with timestamp-shaped final key and no unique tie-break: {violations}"
    )


def test_bare_gate_term_poison_and_qualified_phrase() -> None:
    poison = _public_copy_violations("Admissibility is checked before aggregation.")
    legitimate = _public_copy_violations("Evidence admissibility is checked before aggregation.")
    assert any("bare gate term" in violation for violation in poison)
    assert legitimate == []


def test_earn_family_poison_and_nearest_legitimate_phrase() -> None:
    poison = _public_copy_violations("Does this skill earn its place?")
    legitimate = _public_copy_violations(
        "What does this skill cost, and which parts are worth that cost?"
    )
    assert any("earn/earned family" in violation for violation in poison)
    assert legitimate == []


def test_kind_precision_poison_and_class_split() -> None:
    poison = _public_copy_violations("The detector's kind-precision is 0.835.")
    prose_poison = _public_copy_violations("The detector's kind precision was 83.5%.")
    legitimate = _public_copy_violations(
        "The detector's kind-precision is 0.835.\n"
        "not_a_directive matched 77/78; weak_directive matched 4/20."
    )
    assert any("bare kind-precision aggregate" in violation for violation in poison)
    assert any("bare kind-precision aggregate" in violation for violation in prose_poison)
    assert legitimate == []


def test_measured_recall_poison_and_unmeasured_statement() -> None:
    poison = _public_copy_violations("The detector's recall was measured.")
    legitimate = _public_copy_violations(
        "The detector's recall is UNMEASURED because 1,015 unflagged clauses were not adjudicated."
    )
    assert any("recall not stated as UNMEASURED" in violation for violation in poison)
    assert legitimate == []


def test_pyproject_description_is_scanned_in_both_directions(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndescription = "Does this skill earn its place?"\n'
        '[tool.example]\nnote = "Evidence admissibility is checked."\n',
        encoding="utf-8",
    )
    assert any(
        "pyproject.toml:[project].description" in item
        for item in _repo_public_copy_violations(tmp_path)
    )

    pyproject.write_text(
        '[project]\ndescription = "Reports what changed with and without the skill."\n'
        '[tool.example]\nnote = "Does this skill earn its place?"\n',
        encoding="utf-8",
    )
    assert _repo_public_copy_violations(tmp_path) == []


def test_svg_text_nodes_are_scanned_in_both_directions(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    svg = assets / "preview.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Does it earn its place?">'
        "<text>Does this skill earn its place?</text></svg>",
        encoding="utf-8",
    )
    assert any("assets/preview.svg:text" in item for item in _repo_public_copy_violations(tmp_path))

    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Does it earn its place?">'
        "<text>Reports the difference with and without the skill.</text></svg>",
        encoding="utf-8",
    )
    assert _repo_public_copy_violations(tmp_path) == []


def test_site_generator_templates_are_scanned_in_both_directions(tmp_path: Path) -> None:
    templates = tmp_path / "src" / "skill_harness" / "sitegen" / "templates"
    templates.mkdir(parents=True)
    page = templates / "receipt.html"
    page.write_text("<p>Admissibility is checked.</p>", encoding="utf-8")
    assert any("receipt.html" in item for item in _repo_public_copy_violations(tmp_path))

    page.write_text("<p>Evidence admissibility is checked.</p>", encoding="utf-8")
    assert _repo_public_copy_violations(tmp_path) == []


def test_no_banned_copy_on_public_surfaces() -> None:
    violations = _repo_public_copy_violations(REPO_ROOT)
    assert violations == [], f"banned public-surface copy: {violations}"


# ---------------------------------------------------------------------------
# F-8 (S55 hostile review): cross-check the by-hand-synced exemption/allowlist
# sets above against .pre-commit-config.yaml's actual exclude patterns.
# ---------------------------------------------------------------------------

_PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def _extract_hook_exclude_pattern(config_text: str, hook_id: str) -> str:
    """Return the raw (still-quoted-in-YAML) `exclude:` regex for one local
    pre-commit hook, found by string search -- not a YAML parser (pyyaml is
    not a declared project dependency; see module docstring).

    Looks for `- id: <hook_id>` then the next `exclude: '...'` line before the
    next `- id:` (or end of file), matching this config's actual hook shape.
    """
    id_match = re.search(rf"^\s*-\s*id:\s*{re.escape(hook_id)}\s*$", config_text, re.MULTILINE)
    assert id_match is not None, f"hook {hook_id!r} not found in {_PRE_COMMIT_CONFIG}"
    rest = config_text[id_match.end() :]
    next_hook = re.search(r"^\s*-\s*id:\s*\S+", rest, re.MULTILINE)
    window = rest[: next_hook.start()] if next_hook else rest
    exclude_match = re.search(r"^\s*exclude:\s*'(.*)'\s*$", window, re.MULTILINE)
    assert exclude_match is not None, (
        f"hook {hook_id!r} has no exclude: line in {_PRE_COMMIT_CONFIG}"
    )
    return exclude_match.group(1)


def _assert_exclusion_sets_match(
    *,
    hook_id: str,
    scan_roots: tuple[str, ...],
    python_side_excluded: set[Path],
) -> None:
    """Assert the YAML hook's exclude regex and the Python-side exemption set
    agree on EVERY real .py file in scope, by running both as predicates
    rather than trying to algebraically decompose the regex's alternation
    syntax. This exercises the exact matching semantics pygrep uses
    (`re.search` against the repo-relative POSIX path), so it catches drift
    whether the divergence is an added/removed file OR a rewritten regex.
    """
    config_text = _PRE_COMMIT_CONFIG.read_text(encoding="utf-8")
    yaml_pattern = re.compile(_extract_hook_exclude_pattern(config_text, hook_id))

    mismatches = []
    for path in _iter_py_files(*scan_roots):
        rel_posix = path.relative_to(REPO_ROOT).as_posix()
        yaml_excludes = bool(yaml_pattern.search(rel_posix))
        python_excludes = path in python_side_excluded
        if yaml_excludes != python_excludes:
            mismatches.append(
                f"{rel_posix}: pre-commit exclude={yaml_excludes} vs Python-side={python_excludes}"
            )
    assert mismatches == [], (
        f"{hook_id}: .pre-commit-config.yaml exclude and the Python-side exemption/"
        f"allowlist in {_THIS_FILE.name} disagree on: {mismatches}"
    )


def test_sqlite_connect_exclude_matches_pre_commit_config() -> None:
    """F-8: ban-raw-sqlite-connect's YAML exclude must cover exactly
    _SQLITE_CONNECT_EXEMPT plus this mirror test's own self-exclusion (the
    YAML hook additionally excludes tests/test_structural_bans.py itself,
    per E1b; the Python side expresses that as the separate `path == _THIS_FILE`
    check in test_no_raw_sqlite3_connect_outside_migrations above)."""
    _assert_exclusion_sets_match(
        hook_id="ban-raw-sqlite-connect",
        scan_roots=("src", "tests"),
        python_side_excluded=_SQLITE_CONNECT_EXEMPT | {_THIS_FILE},
    )


def test_oracle_verdicts_exclude_matches_pre_commit_config() -> None:
    """F-8: ban-raw-oracle-verdicts's YAML exclude (src/ only) must cover
    exactly _ORACLE_VERDICTS_ALLOWLIST."""
    _assert_exclusion_sets_match(
        hook_id="ban-raw-oracle-verdicts",
        scan_roots=("src",),
        python_side_excluded=_ORACLE_VERDICTS_ALLOWLIST,
    )


def test_timestamp_order_by_exclude_matches_pre_commit_config() -> None:
    """F-8: ban-timestamp-final-order-by's YAML exclude (src/ only, '^$' =
    match-nothing placeholder) must cover exactly _TS_FINAL_ORDER_BY_EXEMPT
    (currently empty -- no file is exempt from E3)."""
    _assert_exclusion_sets_match(
        hook_id="ban-timestamp-final-order-by",
        scan_roots=("src",),
        python_side_excluded=_TS_FINAL_ORDER_BY_EXEMPT,
    )


def test_public_copy_hook_invokes_field_aware_scanner() -> None:
    config_text = _PRE_COMMIT_CONFIG.read_text(encoding="utf-8")
    hook = re.search(
        r"(?ms)^\s*- id: ban-public-surface-copy\s*$"
        r"(.*?)(?=^\s*- id:|\Z)",
        config_text,
    )
    assert hook is not None, "ban-public-surface-copy hook is missing"
    assert re.search(
        r"^\s*entry: python tests/test_structural_bans\.py\s*$",
        hook.group(1),
        re.MULTILINE,
    )
    assert re.search(r"^\s*pass_filenames: false\s*$", hook.group(1), re.MULTILINE)


def _main() -> int:
    violations = _repo_public_copy_violations(REPO_ROOT)
    if violations:
        print("banned public-surface copy:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
