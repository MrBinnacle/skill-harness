"""A bare pytest run never selects the live API tests (#740).

A local ``pytest -n auto`` with no ``-m`` once ran the live extractor test against
the Anthropic API. It got a 404 and spent nothing; with a valid key and model it
would have spent money. The default selection now excludes ``live`` through
``addopts``. pytest keeps the last ``-m`` it receives, and ``addopts`` comes before
the command line, so CI's explicit expression and a deliberate ``-m live`` both
still win.

Each test runs pytest in a subprocess on a throwaway module with one live test and
one plain test, under this repository's own ``[tool.pytest.ini_options]``.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

_MODULE = """
import pytest


@pytest.mark.live
def test_reaches_the_api() -> None:
    pass


def test_offline() -> None:
    pass
"""


def _write_repo_ini(tmp_path: Path) -> Path:
    """Write this repository's ``addopts`` and ``markers`` into an ini under ``tmp_path``.

    Pointing ``-c`` at the repository's ``pyproject.toml`` would put the config
    file outside ``tmp_path``. On Windows pytest then lists the shared temp root
    while it collects, and another process deleting a directory there turns the
    run into a collection error. An ini inside ``tmp_path`` keeps the walk there
    while the options under test still come from the real file.

    Only ``addopts`` and ``markers`` are copied: they alone decide ``-m`` selection.
    """
    with PYPROJECT.open("rb") as fh:
        options = tomllib.load(fh)["tool"]["pytest"]["ini_options"]
    addopts = " ".join(shlex.quote(str(opt)) for opt in options["addopts"])
    markers = "\n".join(f"    {marker}" for marker in options["markers"])
    ini = tmp_path / "pytest.ini"
    ini.write_text(f"[pytest]\naddopts = {addopts}\nmarkers =\n{markers}\n", encoding="utf-8")
    return ini


def _collect(tmp_path: Path, *extra: str) -> str:
    """Collect the throwaway module under the repository's pytest options."""
    module = tmp_path / "test_throwaway.py"
    module.write_text(_MODULE, encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(_write_repo_ini(tmp_path)),
        "--rootdir",
        str(tmp_path),
        "-p",
        "no:randomly",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:cov",
        "--collect-only",
        "-q",
        str(module),
        *extra,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=tmp_path, timeout=120, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_bare_run_deselects_live_tests(tmp_path: Path) -> None:
    """Fails when the ``-m "not live"`` entry leaves ``addopts``."""
    out = _collect(tmp_path)
    assert "test_reaches_the_api" not in out, "a bare run selected a live test:\n" + out
    assert "test_offline" in out, "the plain test was not collected:\n" + out
    assert "1 deselected" in out, out


def test_explicit_live_selects_live_tests(tmp_path: Path) -> None:
    """A deliberate ``-m live`` on the command line overrides the default."""
    out = _collect(tmp_path, "-m", "live")
    assert "test_reaches_the_api" in out, "-m live did not select the live test:\n" + out
    assert "test_offline" not in out, out


def test_ci_expression_still_wins(tmp_path: Path) -> None:
    """CI's own ``-m`` expression replaces the default rather than adding to it."""
    out = _collect(tmp_path, "-m", "not live and not calibration and not assurance")
    assert "test_offline" in out, out
    assert "test_reaches_the_api" not in out, out
