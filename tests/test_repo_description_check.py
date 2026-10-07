"""Repo description sync check tests.

No test in this file touches the network: ``main``'s ``fetch`` argument is
always a stub callable, never the real ``fetch_live_description``. That is
the point of the injectable-fetch seam in
``scripts/repo_description_check.py`` -- CI has no live network dependency in
the test suite, only in the scheduled workflow that runs the script for real.
"""

from __future__ import annotations

import importlib.util
import tomllib
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, rel_path: str) -> ModuleType:
    """Import a ``scripts/`` file by path.

    ``scripts/`` carries no ``__init__.py`` and is not a package (the same
    reason ``tests/test_drift_check.py`` drives ``scripts/drift_check.py``
    exclusively as a subprocess, never as an import). This test needs an
    in-process module handle instead, to inject a stub ``fetch`` and keep the
    network out of the test suite entirely -- so it loads the file directly
    from its path rather than adding an ``__init__.py`` scripts/ does not
    otherwise want.
    """
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / rel_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_repo_description_check = _load_script(
    "repo_description_check", "scripts/repo_description_check.py"
)
LiveDescriptionUnavailable = _repo_description_check.LiveDescriptionUnavailable
compare_descriptions = _repo_description_check.compare_descriptions
main = _repo_description_check.main


def _write_pyproject(root: Path, description: str) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "skill-harness"\ndescription = "{description}"\n',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# compare_descriptions -- the pure comparison function
# ---------------------------------------------------------------------------


def test_equal_strings_pass() -> None:
    assert compare_descriptions("same text", "same text") == 0


def test_differing_strings_are_drift() -> None:
    assert compare_descriptions("live text", "declared text") == 1


def test_live_none_is_refused() -> None:
    assert compare_descriptions(None, "declared text") == 2


def test_trailing_space_is_drift_not_normalized() -> None:
    """Proves byte-for-byte comparison: no whitespace stripping."""
    assert compare_descriptions("same text ", "same text") == 1


# ---------------------------------------------------------------------------
# main -- exit codes and printed output, fetch always stubbed
# ---------------------------------------------------------------------------


def test_main_exit_0_on_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_pyproject(tmp_path, "the same description")

    def fetch(repo: str, token: str | None) -> str:
        return "the same description"

    code = main(["--root", str(tmp_path)], fetch=fetch)
    out = capsys.readouterr().out
    assert code == 0
    assert "DESCRIPTION SYNC: PASS" in out


def test_main_exit_1_on_drift_prints_both_strings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path, "declared version")

    def fetch(repo: str, token: str | None) -> str:
        return "live version"

    code = main(["--root", str(tmp_path)], fetch=fetch)
    out = capsys.readouterr().out
    assert code == 1
    assert "DESCRIPTION SYNC: DRIFT" in out
    assert "declared version" in out
    assert "live version" in out


def test_main_exit_2_when_fetch_raises_states_refusal_not_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path, "declared version")

    def fetch(repo: str, token: str | None) -> str:
        raise LiveDescriptionUnavailable("network unreachable")

    code = main(["--root", str(tmp_path)], fetch=fetch)
    out = capsys.readouterr().out
    assert code == 2
    assert "DESCRIPTION SYNC: REFUSED" in out
    assert "refusal" in out
    assert "never a pass" in out


def test_main_exit_1_on_trailing_space_only_difference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Proves the CLI path carries the no-normalization contract too."""
    _write_pyproject(tmp_path, "declared version")

    def fetch(repo: str, token: str | None) -> str:
        return "declared version "

    code = main(["--root", str(tmp_path)], fetch=fetch)
    assert code == 1


def test_main_exit_2_on_url_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_pyproject(tmp_path, "declared version")

    def fetch(repo: str, token: str | None) -> str:
        raise LiveDescriptionUnavailable(
            "transport error contacting the API"
        ) from urllib.error.URLError("simulated unreachable host")

    code = main(["--root", str(tmp_path)], fetch=fetch)
    assert code == 2


def test_main_exit_2_on_non_200_response(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_pyproject(tmp_path, "declared version")

    def fetch(repo: str, token: str | None) -> str:
        raise LiveDescriptionUnavailable("GitHub API returned HTTP 404")

    code = main(["--root", str(tmp_path)], fetch=fetch)
    assert code == 2


def test_real_pyproject_parses_and_yields_nonempty_description() -> None:
    """No network: reads the real tree's pyproject.toml directly."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    description = data["project"]["description"]
    assert isinstance(description, str)
    assert description != ""


def test_poison_near_miss_missing_one_word_is_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poison control: the near-miss that motivated this ticket -- a live
    description equal to the declared one except one word removed must still
    be flagged as drift, not waved through as close enough."""
    declared = (
        "This runs the same task with and without the skill and reports what actually changed."
    )
    live_missing_word = declared.replace("actually ", "")
    _write_pyproject(tmp_path, declared)

    def fetch(repo: str, token: str | None) -> str:
        return live_missing_word

    code = main(["--root", str(tmp_path)], fetch=fetch)
    out = capsys.readouterr().out
    assert code == 1
    assert "DESCRIPTION SYNC: DRIFT" in out
