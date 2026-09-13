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

_RUFF_HOOK_IDS = ("ruff", "ruff-format")


def _ci_ruff_paths() -> set[str]:
    """Directories passed to ``ruff check`` and ``ruff format --check`` in CI."""
    text = CI_YML.read_text(encoding="utf-8")
    paths: set[str] = set()
    for m in re.finditer(r"^\s+run:\s+ruff (?:check|format --check)\s+(.+)$", text, re.MULTILINE):
        for token in m.group(1).split():
            if not token.startswith("-"):
                paths.add(token)
    return paths


def _pre_commit_ruff_files_by_hook() -> dict[str, str | None]:
    """``files:`` regex per ruff hook id in .pre-commit-config.yaml.

    A missing ``files:`` key means the hook receives every path pre-commit
    stages (effectively unrestricted relative to CI's explicit path list).
    """
    text = PRE_COMMIT_YML.read_text(encoding="utf-8")
    ruff_repo = re.search(
        r"repo: https://github.com/astral-sh/ruff-pre-commit\n(.*?)(?=^\s*- repo:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if ruff_repo is None:
        return dict.fromkeys(_RUFF_HOOK_IDS)

    block = ruff_repo.group(1)
    out: dict[str, str | None] = {}
    for hook_id in _RUFF_HOOK_IDS:
        hook_match = re.search(rf"^\s*- id: {re.escape(hook_id)}\s*$", block, re.MULTILINE)
        if hook_match is None:
            out[hook_id] = None
            continue
        rest = block[hook_match.end() :]
        next_hook = re.search(r"^\s*- id:", rest, re.MULTILINE)
        window = rest[: next_hook.start()] if next_hook else rest
        files_match = re.search(r"^\s*files:\s*(\S+)", window, re.MULTILINE)
        out[hook_id] = files_match.group(1) if files_match else None
    return out


def _paths_from_files_regex(files_regex: str | None) -> set[str]:
    """Directory names implied by a pre-commit ``files:`` regex, or a sentinel."""
    if files_regex is None:
        return {"<no files: restriction on pre-commit ruff hook>"}
    dir_match = re.search(r"\(([^)]+)\)", files_regex)
    return set(dir_match.group(1).split("|")) if dir_match else {files_regex}


def _extend_exclude() -> set[str]:
    """Directories in ``extend-exclude`` under ``[tool.ruff]``."""
    with PYPROJECT.open("rb") as fh:
        config = tomllib.load(fh)
    return set(config.get("tool", {}).get("ruff", {}).get("extend-exclude", []))


def test_ruff_path_set_matches_between_gates() -> None:
    """CI and both pre-commit ruff hooks must lint the same directories.

    Fails when one gate adds a directory the other does not cover, or when
    ``ruff`` and ``ruff-format`` disagree with each other. Equality of the
    extracted path sets, not a literal value, so a deliberate change to what
    is linted survives as long as both configs change together.
    """
    ci_paths = _ci_ruff_paths()
    by_hook = _pre_commit_ruff_files_by_hook()

    assert ci_paths, (
        "no ruff path arguments found in CI -- "
        "expected 'ruff check <paths>' in .github/workflows/ci.yml"
    )

    hook_path_sets = {hook_id: _paths_from_files_regex(regex) for hook_id, regex in by_hook.items()}

    for hook_id, paths in hook_path_sets.items():
        assert paths == ci_paths, (
            f"ruff path sets disagree: CI={sorted(ci_paths)}, "
            f"pre-commit {hook_id}={sorted(paths)}. "
            f"Both gates must lint the same directories."
        )

    distinct = {frozenset(paths) for paths in hook_path_sets.values()}
    assert len(distinct) == 1, (
        f"pre-commit ruff hooks disagree with each other: "
        f"{ {k: sorted(v) for k, v in hook_path_sets.items()} }. "
        f"ruff and ruff-format must share the same files: scope."
    )


def test_extend_exclude_includes_prototypes() -> None:
    """prototypes/ must be in ruff's extend-exclude (issue #483)."""
    excludes = _extend_exclude()
    assert "prototypes" in excludes, (
        f"prototypes/ not in extend-exclude; found {sorted(excludes)}. "
        "Throwaway walkthrough scripts are not held to production lint."
    )
