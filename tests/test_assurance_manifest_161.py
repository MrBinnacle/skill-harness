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


_EXACT_RELEASE = re.compile(r"\d+(?:\.\d+)*")


def _ci_requirement_line(package: str) -> str | None:
    """The raw requirements-ci.txt line for a package, whatever operator it uses.

    Deliberately NOT derived from `_ci_pinned_names`, which keeps only `==`
    lines. Asserting "this is an exact pin" against that dict is vacuous: a
    ranged requirement is filtered out before the assertion can see it, and the
    case then fails on the unrelated "missing pin" check with a message that
    says the requirement is absent when it is present and loose.
    """
    for line in (_REPO_ROOT / "requirements-ci.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if _parse_requirement_name(stripped) == package.lower():
            return stripped
    return None


def _version_tuple(version: str) -> tuple[int, ...]:
    """Numeric release segments, for an ordering comparison.

    Only release segments are read. A pre-release or local suffix would not be
    an exact release pin, and `_EXACT_RELEASE` rejects it before this is called.
    """
    return tuple(int(part) for part in version.split("."))


def _dev_extra_floor(package: str) -> str | None:
    """The `>=` floor the pyproject dev extra declares for a package, if any."""
    data = _load_pyproject()
    project = cast(dict[str, Any], data["project"])
    extras = cast(dict[str, list[str]], project["optional-dependencies"])
    for requirement in extras["dev"]:
        if _parse_requirement_name(requirement) != package.lower():
            continue
        match = re.search(r">=\s*(\d+(?:\.\d+)*)", requirement)
        if match:
            return match.group(1)
    return None


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
    # Absent and present-but-loose are different faults with different repairs,
    # and `pins` cannot tell them apart: it is built from `==` lines only, so a
    # ranged requirement is filtered out and reports as missing. Read the raw
    # line, then say which of the two it is.
    for pkg in _DEV_EXTRA_REQUIRED:
        line = _ci_requirement_line(pkg)
        assert line is not None, f"requirements-ci.txt states no requirement for {pkg}"
        assert "==" in line, (
            f"requirements-ci.txt states {pkg} as {line!r}, which is not a pin. "
            f"Every host/CI test-time package is pinned with '==' so two runs of "
            f"one commit resolve the same releases."
        )
        assert pkg.lower() in pins, f"requirements-ci.txt missing pin for {pkg}"

    # Hygiene from the supply-chain receipt on #161: the CI file pins an EXACT
    # version, so a CI run is reproducible and an upstream release cannot change
    # what a green tick means.
    #
    # The version itself is NOT frozen here. It read `== "4.1.0"` until
    # 2026-09-07, and what that asserted was one release rather than the pinning
    # property this test is named for: it went red on the routine bump to 5.0.0
    # with 2,660 other tests passing, so the only thing standing between the
    # repository and its own dependency update was the assertion meant to guard
    # it. A literal cannot tell a considered upgrade from an accident, and it
    # blocks the correction it should be waving through.
    #
    # What must hold instead, and does discriminate: the pin exists, it is an
    # exact release, and it satisfies the floor `pyproject.toml` declares.
    # The loop above already proved the requirement is present and uses `==`, so
    # those are not re-asserted here: a second copy could never fire, and an
    # assertion that cannot fail is one a later reader trusts for nothing. What
    # is left to check is the version itself.
    pinned = pins["pytest-randomly"]
    assert _EXACT_RELEASE.fullmatch(pinned), (
        f"requirements-ci.txt pins pytest-randomly=={pinned!r}, which is not a "
        f"plain release. A pre-release or local-version pin makes the CI matrix "
        f"depend on a build that can be yanked or replaced."
    )
    floor = _dev_extra_floor("pytest-randomly")
    assert floor is not None, "pyproject dev extra must declare a pytest-randomly floor"
    assert _version_tuple(pinned) >= _version_tuple(floor), (
        f"requirements-ci.txt pins pytest-randomly=={pinned}, below the "
        f">={floor} floor pyproject.toml declares. The two files disagree about "
        f"the minimum, and the CI file is the one that runs."
    )


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
