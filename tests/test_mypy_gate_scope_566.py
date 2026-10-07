"""mypy's scope is declared in three places; they must name the same paths (#566).

The CI command line is the contract: explicit paths on the command line override
``files`` in pyproject.toml, and pre-commit passes its own regex. The ruff scope
is pinned the same way in ``tests/test_ruff_gate_scope_483.py``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT_YML = REPO_ROOT / ".pre-commit-config.yaml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

GUARD_SCRIPTS = {"scripts/drift_check.py", "scripts/release_gate.py"}


def _ci_mypy_paths() -> set[str]:
    text = CI_YML.read_text(encoding="utf-8")
    matches = re.findall(r"^\s+run:\s+mypy --strict\s+(.+)$", text, re.MULTILINE)
    assert len(matches) == 1, f"expected one mypy --strict step in ci.yml, found {matches}"
    return {path.rstrip("/") for path in matches[0].split()}


def _pyproject_mypy_files() -> set[str]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return {path.rstrip("/") for path in config["tool"]["mypy"]["files"]}


def _pre_commit_mypy_files() -> re.Pattern[str]:
    text = PRE_COMMIT_YML.read_text(encoding="utf-8")
    hook = re.search(r"- id: mypy\n\s+files: (\S+)\n", text)
    assert hook is not None, "the pre-commit mypy hook declares no files pattern"
    return re.compile(hook.group(1))


def _probe_file(path: str) -> str:
    return path if path.endswith(".py") else f"{path}/probe.py"


def test_pyproject_files_match_the_ci_command_line() -> None:
    assert _pyproject_mypy_files() == _ci_mypy_paths()


def test_pre_commit_pattern_admits_exactly_the_ci_paths() -> None:
    pattern = _pre_commit_mypy_files()
    ci_paths = _ci_mypy_paths()
    missed = sorted(p for p in ci_paths if not pattern.search(_probe_file(p)))
    assert missed == [], f"pre-commit mypy skips CI paths: {missed}"
    outside = ["scripts/ebmom_probe.py", "scripts/other.py", "docs/probe.py"]
    admitted = [p for p in outside if pattern.search(p)]
    assert admitted == [], f"pre-commit mypy checks paths CI does not: {admitted}"


def test_the_guard_scripts_are_type_checked_in_ci() -> None:
    assert _ci_mypy_paths() >= GUARD_SCRIPTS
