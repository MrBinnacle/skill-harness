"""Pytest-visible mirrors of the pre-commit/CI structural grep bans (E1/E2).

These do not read `.pre-commit-config.yaml` — pygrep's matching and Python's
`re` differ slightly, and the point is an independent second check, not a
parser for the hook config. Keep the patterns and exemption/allowlist sets
here in sync with `.pre-commit-config.yaml`'s `ban-raw-sqlite-connect` and
`ban-raw-oracle-verdicts` hooks by hand; the CI job that actually runs those
hooks (`.github/workflows/ci.yml` `structural-bans`) is the enforcement of
record — this file exists so a violation shows up in the ordinary
`pytest -m "not live"` loop too, without waiting on pre-commit/CI.
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
