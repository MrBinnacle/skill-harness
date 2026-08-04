"""AST-walker test for evidence repository surface (A24).

Walks every .py file under src/skill_harness/storage/repositories/evidence/
and asserts that NO top-level function name matches the banned mutation prefixes:
  update_, delete_, set_, patch_, modify_, remove_

This is the falsifying-case enforcement for A24's defense-in-depth rule.
Uses stdlib ast (not regex on raw text) per the spec's requirement.

TDD note: this test will FAIL until the evidence repo modules exist (because
the directory itself must be present and importable). The test structure also
deliberately plants a banned name during its own self-test fixture to confirm
the detector fires.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Pre-compiled once at module level per spec.
_BANNED_PATTERN = re.compile(r"^(update|delete|set|patch|modify|remove)_")

EVIDENCE_REPO_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "skill_harness"
    / "storage"
    / "repositories"
    / "evidence"
)


def _collect_top_level_function_names(source: str) -> list[str]:
    """Return all top-level function names from a Python source string."""
    tree = ast.parse(source)
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and isinstance(node.col_offset, int)
        and node.col_offset == 0
    ]


class TestAstWalkerDetector:
    """Self-verification: the detector must fire on planted banned names."""

    def test_detector_finds_banned_name(self) -> None:
        planted = "def update_something():\n    pass\n"
        names = _collect_top_level_function_names(planted)
        matches = [n for n in names if _BANNED_PATTERN.match(n)]
        assert matches == ["update_something"], f"detector missed: {names}"

    def test_detector_finds_delete_name(self) -> None:
        planted = "def delete_row(conn):\n    pass\n"
        names = _collect_top_level_function_names(planted)
        assert any(_BANNED_PATTERN.match(n) for n in names)

    def test_detector_allows_insert(self) -> None:
        ok = "def insert_skill(conn, skill):\n    pass\n"
        names = _collect_top_level_function_names(ok)
        assert not any(_BANNED_PATTERN.match(n) for n in names)

    def test_detector_allows_get(self) -> None:
        ok = "def get_skill_by_id(conn, skill_id):\n    pass\n"
        names = _collect_top_level_function_names(ok)
        assert not any(_BANNED_PATTERN.match(n) for n in names)


class TestEvidenceRepoSurface:
    """The actual enforcement: NO banned names in evidence repo modules."""

    def test_evidence_repo_dir_exists(self) -> None:
        assert EVIDENCE_REPO_DIR.exists(), (
            f"evidence repo directory does not exist: {EVIDENCE_REPO_DIR}\n"
            "Run Track A.1 implementation before this test."
        )

    def test_no_banned_function_names(self) -> None:
        assert EVIDENCE_REPO_DIR.exists(), f"evidence repo directory missing: {EVIDENCE_REPO_DIR}"
        py_files = list(EVIDENCE_REPO_DIR.glob("*.py"))
        # Exclude __init__.py from banned-name check (re-exports are fine there)
        module_files = [f for f in py_files if f.name != "__init__.py"]
        assert module_files, (
            f"No .py module files found in {EVIDENCE_REPO_DIR} — "
            "at least 10 table modules are expected."
        )

        violations: list[str] = []
        for path in sorted(module_files):
            source = path.read_text(encoding="utf-8")
            names = _collect_top_level_function_names(source)
            for name in names:
                if _BANNED_PATTERN.match(name):
                    violations.append(f"{path.name}::{name}")

        assert not violations, (
            "Evidence repo modules must not export mutation functions.\n"
            "Banned names found:\n" + "\n".join(f"  {v}" for v in violations)
        )

    def test_expected_module_count(self) -> None:
        """Exactly 12 table modules (plus optionally __init__.py) must exist.

        10 original A24 table modules + screens.py (migration 0501: the Stage-0
        Null-only screen store, screen_runs/screen_trials) + task_frontier.py
        (migration 0700: the calibration/confirmation/matched phase partition).
        """
        assert EVIDENCE_REPO_DIR.exists(), f"directory missing: {EVIDENCE_REPO_DIR}"
        module_files = [f for f in EVIDENCE_REPO_DIR.glob("*.py") if f.name != "__init__.py"]
        assert len(module_files) == 12, (
            f"Expected 12 evidence table modules, found {len(module_files)}: "
            + str([f.name for f in module_files])
        )
