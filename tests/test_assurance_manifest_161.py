"""#161 — ratified test-time dependency manifest (external install surface).

Pins the acceptance criteria for the assurance-pass dependency landing:
dev-extra installability, CI constraint mirror, container-only tools file,
unchanged runtime wheel metadata, and no src/ imports of the new *test-only*
packages this ticket introduces.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Packages this ticket newly lands as *test-time* surface. scipy/statsmodels are
# already runtime deps (pre-#161) and are imported under src/ — that pre-existing
# state is a ticket/code contradiction surfaced in the PR, not something this
# test rewrites. The AC "no src/ imports of the new packages" applies to the
# packages that are new as test-only: pytest-randomly (host/CI) plus the
# container-only pair.
_NEW_TEST_ONLY_IMPORT_ROOTS = ("pytest_randomly", "mutmut", "atheris")

_DEV_EXTRA_REQUIRED = ("scipy", "statsmodels", "numpy", "pytest-randomly")

# Runtime Requires-Dist names that must stay exactly as they were before this
# ticket (zero new runtime dependencies). Captured from main at ticket open.
_RUNTIME_REQUIRE_NAMES = frozenset(
    {
        "anthropic",
        "openai",
        "click",
        "pydantic",
        "rich",
        "scipy",
        "tiktoken",
        "statsmodels",
    }
)


def _load_pyproject() -> dict[str, Any]:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def _parse_requirement_name(req: str) -> str:
    """Strip markers/extras/version from a PEP 508 requirement string → name."""
    bare = req.split(";", 1)[0].strip()
    bare = bare.split("[", 1)[0].strip()
    return re.split(r"[<>=!~]", bare, maxsplit=1)[0].strip().lower()


def _ci_pinned_names() -> dict[str, str]:
    """name -> version for non-comment, non-editable pins in requirements-ci.txt."""
    out: dict[str, str] = {}
    for line in (_REPO_ROOT / "requirements-ci.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if "==" not in stripped:
            continue
        name, ver = stripped.split("==", 1)
        out[name.strip().lower()] = ver.strip()
    return out


def test_dev_extra_declares_numerical_and_hygiene_packages() -> None:
    """pip install -e '.[dev]' must pull scipy, statsmodels, numpy, pytest-randomly."""
    data = _load_pyproject()
    project = cast(dict[str, Any], data["project"])
    extras = cast(dict[str, list[str]], project["optional-dependencies"])
    dev = extras["dev"]
    names = {_parse_requirement_name(r) for r in dev}
    missing = [pkg for pkg in _DEV_EXTRA_REQUIRED if pkg.lower() not in names]
    assert missing == [], f"dev extra missing packages: {missing}"


def test_requirements_ci_mirrors_dev_manifest_pins() -> None:
    """requirements-ci.txt pins every newly-declared host/CI test-time package."""
    pins = _ci_pinned_names()
    for pkg in _DEV_EXTRA_REQUIRED:
        assert pkg.lower() in pins, f"requirements-ci.txt missing pin for {pkg}"
    # Hygiene pin from the supply-chain receipt on #161.
    assert pins["pytest-randomly"] == "4.1.0"


def test_requirements_assurance_container_exists_with_header_and_pins() -> None:
    """Container-only mutmut/atheris file with the Linux-container-only header."""
    path = _REPO_ROOT / "requirements-assurance-container.txt"
    assert path.is_file(), "requirements-assurance-container.txt must exist"
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    assert "linux" in lower and "container" in lower, "header must state Linux-container-only"
    assert "never" in lower and ("host" in lower or "host-side" in lower)
    assert "default ci" in lower or "ci matrix" in lower
    pins = {
        line.split("==", 1)[0].strip().lower(): line.split("==", 1)[1].strip()
        for line in text.splitlines()
        if "==" in line and not line.strip().startswith("#")
    }
    assert pins.get("mutmut") == "3.7.0"
    assert pins.get("atheris") == "3.1.0"
    # Only the two container tools — nothing from the host/CI manifest.
    assert set(pins) == {"mutmut", "atheris"}


def test_runtime_wheel_requires_dist_unchanged() -> None:
    """Built wheel runtime Requires-Dist names match the pre-#161 set (no adds)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(out), str(_REPO_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        wheels = list(out.glob("skill_harness-*.whl"))
        assert len(wheels) == 1, wheels
        with zipfile.ZipFile(wheels[0]) as zf:
            meta_name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
            meta = zf.read(meta_name).decode("utf-8")
    requires = [
        _parse_requirement_name(line.split(":", 1)[1])
        for line in meta.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line and "extra==" not in line
    ]
    # Drop optional-extra requires (Requires-Dist with environment marker extra ==)
    # — already filtered above. Compare name sets only.
    assert frozenset(requires) == _RUNTIME_REQUIRE_NAMES


def test_src_does_not_import_new_test_only_packages() -> None:
    """No module under src/ imports pytest_randomly / mutmut / atheris."""
    violations: list[str] = []
    src_root = _REPO_ROOT / "src"
    for path in src_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in _NEW_TEST_ONLY_IMPORT_ROOTS:
                        violations.append(f"{path.relative_to(_REPO_ROOT)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in _NEW_TEST_ONLY_IMPORT_ROOTS:
                    violations.append(
                        f"{path.relative_to(_REPO_ROOT)}: from {node.module} import ..."
                    )
    assert violations == [], f"src/ imports of new test-only packages: {violations}"


def test_project_dependencies_untouched_by_manifest() -> None:
    """[project.dependencies] must not gain the test-only additions from this ticket."""
    data = _load_pyproject()
    project = cast(dict[str, Any], data["project"])
    runtime = {_parse_requirement_name(r) for r in cast(list[str], project["dependencies"])}
    # pytest-randomly / mutmut / atheris must never appear as runtime deps.
    forbidden = {"pytest-randomly", "mutmut", "atheris", "pytest_randomly"}
    leaked = runtime & {n.lower() for n in forbidden}
    assert leaked == set(), f"test-only packages leaked into runtime deps: {leaked}"
    assert runtime == {n.lower() for n in _RUNTIME_REQUIRE_NAMES}


@pytest.mark.parametrize("pkg", ["scipy", "statsmodels", "numpy"])
def test_dev_extra_numerical_packages_importable(pkg: str) -> None:
    """Sanity: numerical reference packages resolve in the current env after dev install."""
    __import__(pkg)
