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
pattern: only ``project.description`` is public PyPI copy, SVG copy includes
rendered text and accessible labels, and the calibration rules need multi-line
context windows. Its pre-commit hook therefore invokes this module's
zero-dependency scanner directly instead of maintaining a second, weaker
pattern/allowlist.

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
    Path("docs/observations/OBS-0003-sqlite-tie-break-red-test-trap.md"),
    Path("docs/observations/OBS-0004-bayesian-eval-discipline.md"),
    Path("docs/observations/OBS-0005-append-only-evidence-design.md"),
    Path("docs/observations/OBS-0006-llm-judge-calibration.md"),
}

_ADMISSIBILITY_RE = re.compile(r"\badmissibility\b", re.IGNORECASE)
# The qualifier must sit immediately before the bare word: same line, or one
# line-wrap. A bare ``\s+`` here spanned blank lines, so a paragraph ending in
# the word "evidence" silently qualified an unrelated "Admissibility ..." that
# opened the next paragraph -- the substring trap this rule exists to catch.
# ``\Z``, not ``$``: ``$`` also matches before a trailing newline, which lets
# exactly one blank line back through.
_QUALIFIED_ADMISSIBILITY_PREFIX_RE = re.compile(
    r"(?<![\w-])evidence(?:-|[^\S\n]+|[^\S\n]*\n[^\S\n]*)\Z", re.IGNORECASE
)
_EARN_FAMILY_RE = re.compile(r"\bearn(?:s|ed|ing)?\b", re.IGNORECASE)
_KIND_PRECISION_AGGREGATE_RE = re.compile(
    r"\b0\.835\b"
    r"|\bkind[ -]precision\b[^\n.!?]{0,40}\b83\.5\s*(?:%|percent\b)"
    r"|\b83\.5\s*(?:%|percent\b)[^\n.!?]{0,40}\bkind[ -]precision\b",
    re.IGNORECASE,
)
_NOT_A_DIRECTIVE_SPLIT_RE = re.compile(
    r"(?:\bnot_a_directive\b(?:(?!\bweak_directive\b)[^\n.!?]){0,60}\b77/77\b"
    r"|\b77/77\b(?:(?!\bweak_directive\b)[^\n.!?]){0,60}\bnot_a_directive\b)",
    re.IGNORECASE,
)
_WEAK_DIRECTIVE_SPLIT_RE = re.compile(
    r"(?:\bweak_directive\b(?:(?!\bnot_a_directive\b)[^\n.!?]){0,60}\b4/20\b"
    r"|\b4/20\b(?:(?!\bnot_a_directive\b)[^\n.!?]){0,60}\bweak_directive\b)",
    re.IGNORECASE,
)
# The second-generation figures are receipt vacuity-flag-adjudication-2026-08-09
# arm_C: overall_kind_match 0.9667, not_a_directive 255/255, weak_directive 6/15.
# Same rule as the 2026-08-08 aggregate above, and deliberately the same surface
# variants -- the decimal anywhere, plus the percentage rendering on either side
# of the claim. A rule that only knows the decimal is not a guard: "96.67 % kind
# precision" is the same bare aggregate spelled the way prose spells it. 96.67
# and 96.7 are both renderings of 0.9667; the `kind[ -]precision` proximity gate
# is what keeps those bare numbers from matching unrelated prose.
_GEN2_KIND_PRECISION_AGGREGATE_RE = re.compile(
    r"\b0\.9667\b"
    r"|\bkind[ -]precision\b[^\n.!?]{0,40}\b(?:96\.67|96\.7)\s*(?:%|percent\b)"
    r"|\b(?:96\.67|96\.7)\s*(?:%|percent\b)[^\n.!?]{0,40}\bkind[ -]precision\b",
    re.IGNORECASE,
)
_GEN2_NOT_A_DIRECTIVE_SPLIT_RE = re.compile(
    r"(?:\bnot_a_directive\b(?:(?!\bweak_directive\b)[^\n.!?]){0,60}\b255/255\b"
    r"|\b255/255\b(?:(?!\bweak_directive\b)[^\n.!?]){0,60}\bnot_a_directive\b)",
    re.IGNORECASE,
)
_GEN2_WEAK_DIRECTIVE_SPLIT_RE = re.compile(
    r"(?:\bweak_directive\b(?:(?!\bnot_a_directive\b)[^\n.!?]){0,60}\b6/15\b"
    r"|\b6/15\b(?:(?!\bnot_a_directive\b)[^\n.!?]){0,60}\bweak_directive\b)",
    re.IGNORECASE,
)
_VACUITY_RECALL_RE = re.compile(
    r"(?:\b(?:vacuity[- ](?:flag|detector)|detector)(?:'s)?\b"
    r"[^\n.!?]{0,80}\brecall\b"
    r"|\brecall\b[^\n.!?]{0,80}"
    r"\b(?:vacuity[- ](?:flag|detector)|detector)\b)",
    re.IGNORECASE,
)
_MEASURED_RE = re.compile(r"\bmeasur(?:e|ed|ing)\b", re.IGNORECASE)
_UNMEASURED_RE = re.compile(r"\bunmeasured\b", re.IGNORECASE)
_KIND_CONTEXT_LINES = 2
_RECALL_CONTEXT_LINES = 2
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


def _line_context(text: str, offset: int, radius: int) -> str:
    lines = text.splitlines() or [text]
    lineno = _line_number(text, offset)
    start = max(0, lineno - 1 - radius)
    end = min(len(lines), lineno + radius)
    return "\n".join(lines[start:end])


def _measured_recall_has_current_receipt_context(context: str) -> bool:
    required = (
        r"\b0\.73(?:31)?\b",
        r"\b0\.75(?:24)?\b",
        r"\b0\.66\b",
        r"\b0\.87(?:4)?\b",
        r"\b0\.62(?:2)?\b",
        r"\b0\.91(?:3)?\b",
        r"\b47\b",
        r"\bstratified\b",
        r"\bbootstrap\b",
        r"\bgeneration\b",
    )
    return all(re.search(pattern, context, re.IGNORECASE) for pattern in required)


def _public_copy_violations(text: str) -> list[str]:
    violations = [
        f"bare gate term at line {_line_number(text, match.start())}"
        for match in _ADMISSIBILITY_RE.finditer(text)
        if not _QUALIFIED_ADMISSIBILITY_PREFIX_RE.search(text[: match.start()])
    ]
    violations.extend(
        f"earn/earned family at line {_line_number(text, match.start())}"
        for match in _EARN_FAMILY_RE.finditer(text)
    )

    # Backstop only: each registered aggregate requires its own split pair to
    # occur somewhere in the document. This deliberately does not parse prose
    # claims or bind a nearby aggregate to a nearby pair.
    kind_precision_receipts = (
        (
            _KIND_PRECISION_AGGREGATE_RE,
            _NOT_A_DIRECTIVE_SPLIT_RE,
            _WEAK_DIRECTIVE_SPLIT_RE,
        ),
        (
            _GEN2_KIND_PRECISION_AGGREGATE_RE,
            _GEN2_NOT_A_DIRECTIVE_SPLIT_RE,
            _GEN2_WEAK_DIRECTIVE_SPLIT_RE,
        ),
    )
    for aggregate_re, not_a_directive_re, weak_directive_re in kind_precision_receipts:
        has_complete_pair = not_a_directive_re.search(text) and weak_directive_re.search(text)
        if has_complete_pair:
            continue
        violations.extend(
            f"bare kind-precision aggregate at line {_line_number(text, match.start())}"
            for match in aggregate_re.finditer(text)
        )

    for match in _VACUITY_RECALL_RE.finditer(text):
        context = _line_context(text, match.start(), _RECALL_CONTEXT_LINES)
        measured = _MEASURED_RE.search(context)
        if (measured and not _measured_recall_has_current_receipt_context(context)) or (
            not measured and not _UNMEASURED_RE.search(context)
        ):
            violations.append(
                f"recall not stated as UNMEASURED at line {_line_number(text, match.start())}"
            )
    return violations


def _svg_text(svg: str) -> str:
    root = ET.fromstring(svg)
    public_copy: list[str] = []
    for element in root.iter():
        aria_label = element.get("aria-label")
        if aria_label:
            public_copy.append(aria_label)
        if element.tag.rsplit("}", 1)[-1] in {"text", "title", "desc"}:
            public_copy.append("".join(element.itertext()))
    return "\n".join(public_copy)


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
    assert any("bare gate term" in violation for violation in poison)
    assert _public_copy_violations("Evidence admissibility is checked before aggregation.") == []
    assert _public_copy_violations("Evidence\nadmissibility is checked before aggregation.") == []
    near_miss = _public_copy_violations("Counterevidence admissibility is not the gate term.")
    assert any("bare gate term" in violation for violation in near_miss)


def test_qualifier_must_be_adjacent_not_merely_upstream() -> None:
    """A paragraph break severs the qualifier from the bare word.

    The lookbehind is the whole rule here: the qualified term contains the
    bare word, so anything that lets "evidence" qualify from an arbitrary
    distance turns the rule off wherever the two happen to be neighbours.
    """
    for poison in (
        "The store keeps evidence.\n\nAdmissibility is checked at write time.",
        "The store keeps evidence\n\nAdmissibility is checked at write time.",
        "The store keeps evidence\n\n\n\nAdmissibility is resolved at write.",
    ):
        assert any(
            "bare gate term" in violation for violation in _public_copy_violations(poison)
        ), poison
    # One line-wrap is still the qualified term.
    assert _public_copy_violations("... write-time evidence\nadmissibility snapshots.") == []


def test_earn_family_poison_and_nearest_legitimate_phrase() -> None:
    for poison in (
        "Does this skill earn its slot?",
        "This skill earned its place.",
        "This skill earns its place.",
        "This skill is earning its place.",
    ):
        violations = _public_copy_violations(poison)
        assert any("earn/earned family" in violation for violation in violations)
    assert (
        _public_copy_violations("What does this skill cost, and which parts are worth that cost?")
        == []
    )
    assert _public_copy_violations("Learn from earnest comparisons year-round.") == []


def test_kind_precision_poison_and_class_split() -> None:
    poison = _public_copy_violations("The detector's kind-precision is 0.835.")
    prose_poison = _public_copy_violations("The detector reported 83.5 % kind precision.")
    legitimate = _public_copy_violations(
        "The detector's kind-precision is 0.835.\n"
        "not_a_directive matched 77/77; weak_directive matched 4/20."
    )
    stale_split = _public_copy_violations(
        "The detector's kind-precision is 0.835.\n"
        "not_a_directive matched 77/78; weak_directive matched 4/20."
    )
    swapped_split = _public_copy_violations(
        "The detector's kind-precision is 0.835.\n"
        "not_a_directive matched 4/20; weak_directive matched 77/77."
    )
    assert any("bare kind-precision aggregate" in violation for violation in poison)
    assert any("bare kind-precision aggregate" in violation for violation in prose_poison)
    assert any("bare kind-precision aggregate" in violation for violation in stale_split)
    assert any("bare kind-precision aggregate" in violation for violation in swapped_split)
    assert legitimate == []


def test_gen2_kind_precision_poison_and_class_split() -> None:
    """Mirrors the 2026-08-08 case above, direction for direction.

    `prose_poison` is the percentage rendering, as it is in the Gen-1 test: a
    decimal spelled with a space instead of a hyphen is already caught by the
    bare-decimal alternative, so asserting it here would have been a passing
    assertion that pinned nothing and hid the missing percentage direction.
    """
    poison = _public_copy_violations("The detector's kind-precision is 0.9667.")
    prose_poison = _public_copy_violations("The detector reported 96.67 % kind precision.")
    term_first_prose_poison = _public_copy_violations(
        "The detector's kind-precision reached 96.7 percent."
    )
    legitimate = _public_copy_violations(
        "The detector's kind-precision is 0.9667.\n"
        "not_a_directive matched 255/255; weak_directive matched 6/15."
    )
    stale_split = _public_copy_violations(
        "The detector's kind-precision is 0.9667.\n"
        "not_a_directive matched 255/256; weak_directive matched 6/15."
    )
    swapped_split = _public_copy_violations(
        "The detector's kind-precision is 0.9667.\n"
        "not_a_directive matched 6/15; weak_directive matched 255/255."
    )
    assert any("bare kind-precision aggregate" in violation for violation in poison)
    assert any("bare kind-precision aggregate" in violation for violation in prose_poison)
    assert any(
        "bare kind-precision aggregate" in violation for violation in term_first_prose_poison
    )
    assert any("bare kind-precision aggregate" in violation for violation in stale_split)
    assert any("bare kind-precision aggregate" in violation for violation in swapped_split)
    assert legitimate == []


def test_gen2_kind_precision_aggregate_accepts_document_level_class_split() -> None:
    document = (
        "The detector's kind-precision is 0.9667.\n\n\n"
        "The receipt reports not_a_directive matched 255/255 and "
        "weak_directive matched 6/15."
    )

    assert _public_copy_violations(document) == []


def test_measured_recall_poison_and_unmeasured_statement() -> None:
    poison = _public_copy_violations("The detector's recall was measured.")
    contradictory = _public_copy_violations(
        "The vacuity detector's recall was measured, not UNMEASURED."
    )
    historical = _public_copy_violations(
        "The detector's recall is UNMEASURED because 1,015 unflagged clauses were not adjudicated."
    )
    current = _public_copy_violations(
        "The vacuity detector's recall was MEASURED at 0.73-0.75 for this generation, with "
        "stratified-FPC 95% [0.66, 0.87], skill-cluster bootstrap 95% [0.62, 0.91], "
        "and skill-level n=47."
    )
    assert any("recall not stated as UNMEASURED" in violation for violation in poison)
    assert any("recall not stated as UNMEASURED" in violation for violation in contradictory)
    assert historical == []
    assert current == []
    assert _public_copy_violations("Recall that evidence is append-only.") == []


def test_pyproject_description_is_scanned_in_both_directions(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "skill-harness"\n'
        'description = "Evaluation harness for reusable AI agent skills - does a skill earn '
        "its slot? Returns KEEP / CUT / CAN'T-TELL-YET.\"\n",
        encoding="utf-8",
    )
    assert any(
        "pyproject.toml:[project].description" in item
        for item in _repo_public_copy_violations(tmp_path)
    )

    pyproject.write_text(
        "[project]\n"
        'name = "skill-harness"\n'
        'description = "Reports what changed with and without the skill."\n'
        'keywords = ["earn", "admissibility"]\n'
        '[tool.example]\nnote = "Does this skill earn its place?"\n',
        encoding="utf-8",
    )
    assert _repo_public_copy_violations(tmp_path) == []


def test_historical_pyproject_description_reconstruction_is_rejected(tmp_path: Path) -> None:
    """Reconstruct the pre-fix PyPI summary that prompted issue #185.

    A reconstruction, not a live catch: the line was already rewritten on this
    branch before the guard existed, so this is the value from git history
    (``git show 8da8e20:pyproject.toml``, line 8) replayed verbatim -- em dash
    included. A "reconstruction" that silently normalises a character is a
    paraphrase, and the poison direction is worth no more than its fidelity.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "skill-harness"\n'
        'description = "Evaluation harness for reusable AI agent skills \u2014 does a skill earn '
        "its slot? Returns KEEP / CUT / CAN'T-TELL-YET, never a manufactured score. "
        'First-class Claude Code support."\n',
        encoding="utf-8",
    )

    violations = _repo_public_copy_violations(tmp_path)

    assert any(
        item.startswith("pyproject.toml:[project].description: earn/earned family")
        for item in violations
    )


def test_pyproject_description_matches_approved_repo_description() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["description"] == (
        "I wanted to know whether a skill was actually any good. This runs the same task with "
        "the skill and without it, and reports what can honestly be said about the difference "
        '- often "not enough to call it". A missing figure is a typed refusal, never an '
        "invented score. First-class Claude Code support."
    )


def test_svg_text_nodes_are_scanned_in_both_directions(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    svg = assets / "preview.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Does this skill earn its place?">'
        "<text>Reports the difference with and without the skill.</text></svg>",
        encoding="utf-8",
    )
    assert any("assets/preview.svg:text" in item for item in _repo_public_copy_violations(tmp_path))

    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Reports the comparison.">'
        "<text>Does this skill </text><text>earn its place?</text></svg>",
        encoding="utf-8",
    )
    assert any("assets/preview.svg:text" in item for item in _repo_public_copy_violations(tmp_path))

    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Reports the comparison.">'
        "<text>Reports the <tspan>difference</tspan> with and without the skill.</text></svg>",
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


def test_readme_and_nested_docs_are_scanned_in_both_directions(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Does this skill earn its slot?", encoding="utf-8")
    assert any("README.md" in item for item in _repo_public_copy_violations(tmp_path))
    readme.write_text("Reports the comparison.", encoding="utf-8")

    nested = tmp_path / "docs" / "nested" / "page.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("Admissibility is checked.", encoding="utf-8")
    assert any("docs/nested/page.md" in item for item in _repo_public_copy_violations(tmp_path))
    nested.write_text("Evidence admissibility is checked.", encoding="utf-8")
    assert _repo_public_copy_violations(tmp_path) == []


def test_gen2_receipt_json_is_not_a_public_surface(tmp_path: Path) -> None:
    """Pins the scanned surface set: docs/*.md is copy, docs/*.json is data.

    Scope, stated exactly, because the name is broader than the fixture: the
    receipt's `kind_precision` JSON *key* is not a claim (the same distinction
    `vacuity_policy.assert_kind_precision_render_safe` draws). Its `note` field
    IS prose, and the real receipt's note carries the bare aggregate beside a
    split this rule's proximity window cannot see -- so if the surface set ever
    grows to JSON, that note is flagged and the decision has to be taken
    deliberately rather than inherited from this test.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    public_doc = docs / "summary.md"
    public_doc.write_text("Kind-precision is 0.9667.", encoding="utf-8")
    receipt = docs / "calibration" / "vacuity-adjudication-receipt-2026-08-09.json"
    receipt.parent.mkdir()
    receipt.write_text('{"kind_precision": 0.9667}\n', encoding="utf-8")

    violations = _repo_public_copy_violations(tmp_path)

    assert violations == ["docs/summary.md: bare kind-precision aggregate at line 1"]


def test_public_copy_exclusion_list_is_minimal() -> None:
    unnecessary = [
        relative.as_posix()
        for relative in sorted(_PUBLIC_COPY_EXCLUDED)
        if not _public_copy_violations((REPO_ROOT / relative).read_text(encoding="utf-8"))
    ]
    assert unnecessary == [], f"public-copy exclusions hiding no current violation: {unnecessary}"


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
