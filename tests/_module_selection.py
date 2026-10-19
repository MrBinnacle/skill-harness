"""Shared module-selection helpers for static scan tests.

Two test modules (``test_value_class_call_sites_static`` and
``test_mint_path_allowlist``) walk production sources with the same directory
exclusion logic.  Duplicating the filter is how defect #447 survived being
fixed once — the second copy was never touched.  This module is the single
source of truth.

Anchoring
---------
The exclusion is anchored at the *scanned root*, not tested against the
absolute path.  Builds run in worktrees at
``<repo>/.sandcastle/worktrees/agent-issue-<n>/``.  A filter that tested the
absolute path's components excluded every file in such a tree, so the scan
returned nothing and every assertion in the calling module passed while
guarding nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

EXCLUDED_DIRECTORY_NAMES: Final[frozenset[str]] = frozenset({"__pycache__", ".sandcastle"})


def python_modules_under(root: Path) -> list[Path]:
    """Return every Python module under *root*, skipping caches and nested build trees.

    The exclusion is anchored at *root* rather than tested against the absolute
    path.  What the exclusion is for is caches and nested build trees *inside*
    the tree being scanned, and that is a property of the path relative to the
    root.
    """
    return sorted(
        path
        for path in root.rglob("*.py")
        if not (EXCLUDED_DIRECTORY_NAMES & set(path.relative_to(root).parts))
    )
