"""Pytest-visible mirrors of the pre-commit/CI structural grep bans (E1/E2/E3).

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
