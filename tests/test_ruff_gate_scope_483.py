"""#483: pre-commit and CI must scope ruff over the same path set.

The two gates disagreed: CI ran ``ruff check src tests`` while the pre-commit
ruff hook had no ``files:`` restriction and therefore linted ``prototypes/``
too. The three findings in ``prototypes/PROTOTYPE_firewall_walkthrough.py``
were latent in CI and fatal in ``pre-commit run --all-files``.

This test parses both configs and asserts the ruff path sets are identical.
It does not assert a literal value -- a legitimate change to what is linted
survives as long as both configs change together.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT_YML = REPO_ROOT / ".pre-commit-config.yaml"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _ci_ruff_paths() -> set[str]:
    """Directories passed to ``ruff check`` and ``ruff format --check`` in CI."""
    text = CI_YML.read_text(encoding="utf-8")
    paths: set[str] = set()
    for m in re.finditer(r"^\s+run:\s+ruff (?:check|format --check)\s+(.+)$", text, re.MULTILINE):
        for token in m.group(1).split():
            if not token.startswith("-"):
                paths.add(token)
    return paths


def _pre_commit_ruff_files() -> str | None:
    """The ``files:`` regex on the ruff hook in .pre-commit-config.yaml.

    Returns None when no ``files:`` key is present (meaning all files).
    """
    text = PRE_COMMIT_YML.read_text(encoding="utf-8")
    # Locate the ruff repo block, then the ruff hook id, then its files: line.
    ruff_repo = re.search(
        r"repo: https://github.com/astral-sh/ruff-pre-commit\n(.*?)(?=^\s*- repo:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if ruff_repo is None:
        return None
    block = ruff_repo.group(1)
    hook_match = re.search(r"^\s*- id: ruff\s*$", block, re.MULTILINE)
    if hook_match is None:
        return None
    rest = block[hook_match.end() :]
    next_hook = re.search(r"^\s*- id:", rest, re.MULTILINE)
    window = rest[: next_hook.start()] if next_hook else rest
    files_match = re.search(r"^\s*files:\s*(\S+)", window, re.MULTILINE)
    return files_match.group(1) if files_match else None


def _extend_exclude() -> set[str]:
    """Directories in ``extend-exclude`` under ``[tool.ruff]``."""
    with PYPROJECT.open("rb") as fh:
        config = tomllib.load(fh)
    return set(config.get("tool", {}).get("ruff", {}).get("extend-exclude", []))


def test_ruff_path_set_matches_between_gates() -> None:
    """CI and pre-commit must lint the same directories.

    Fails when one gate adds a directory the other does not cover. The
    assertion is equality of the extracted path sets, not a literal value,
    so a deliberate change to what is linted survives as long as both
    configs change together.
    """
    ci_paths = _ci_ruff_paths()
    pre_commit_files = _pre_commit_ruff_files()

    assert ci_paths, (
        "no ruff path arguments found in CI -- "
        "expected 'ruff check <paths>' in .github/workflows/ci.yml"
    )

    if pre_commit_files is None:
        # No files: restriction means pre-commit lints everything ruff discovers.
        # That can only match CI if extend-exclude restricts ruff to the same set.
        # For this assertion, treat "all files minus extend-exclude" as the
        # pre-commit path set and require it to equal CI's explicit set.
        # In practice, adding files: ^(src|tests)/ is the cleaner fix.
        # Use a sentinel that cannot equal ci_paths to force the assertion to fail.
        pre_commit_paths = {"<no files: restriction on pre-commit ruff hook>"}
    else:
        # Extract directory names from the regex pattern (e.g. ^(src|tests)/).
        dir_match = re.search(r"\(([^)]+)\)", pre_commit_files)
        pre_commit_paths = set(dir_match.group(1).split("|")) if dir_match else {pre_commit_files}

    assert ci_paths == pre_commit_paths, (
        f"ruff path sets disagree: CI={sorted(ci_paths)}, "
        f"pre-commit={sorted(pre_commit_paths)}. "
        f"Both gates must lint the same directories."
    )


def test_extend_exclude_includes_prototypes() -> None:
    """prototypes/ must be in ruff's extend-exclude (issue #483)."""
    excludes = _extend_exclude()
    assert "prototypes" in excludes, (
        f"prototypes/ not in extend-exclude; found {sorted(excludes)}. "
        "Throwaway walkthrough scripts are not held to production lint."
    )
