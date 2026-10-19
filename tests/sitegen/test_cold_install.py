"""Cold-install behaviour for the receipts site generator (#415).

``jsonschema`` is an optional dependency: it reaches this environment through
the ``[sitegen]`` extra (and through ``[dev]``, re-declared there for the test
stack; and transitively through ``inspect-ai``), never through
``[project.dependencies]``. A core install — ``pip install skill-harness``
with no extras — must still import ``skill_harness.sitegen`` and answer
``python -m skill_harness.sitegen --help``, and a build must refuse at use
time with a typed error naming the extra to install rather than failing at
import time with a bare ``ImportError``.

CI installs ``[dev]`` everywhere, so ``jsonschema`` is always present on the
matrix. These tests cannot therefore rely on the package being absent: they
install a ``find_spec``-based meta-path finder that makes ``jsonschema`` (and
every submodule) unimportable, and they assert that blocker is effective
*before* asserting the cold-install outcome — otherwise the outcome assertion
would pass vacuously in CI. The legacy ``find_module`` API is not consulted on
Python 3.12+, so a finder that only overrides ``find_module`` would let the
import succeed and the test pass vacuously; ``find_spec`` is the seam.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.abc
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO_ROOT / "docs" / "sers" / "sers.schema.json"

# Keys whose presence in ``sys.modules`` we both clear (so a re-import
# re-executes module top-level code, exercising the lazy import) and restore
# (so the rest of the session keeps the original module objects).
_JSONSCHEMA_PREFIXES = ("jsonschema", "jsonschema.")
_SITEGEN_PREFIXES = ("skill_harness.sitegen", "skill_harness.sitegen.")


def _matches(prefixes: tuple[str, ...], name: str) -> bool:
    return any(name == p.rstrip(".") or name.startswith(p) for p in prefixes)


class _JsonschemaBlocker(importlib.abc.MetaPathFinder):
    """A meta-path finder whose ``find_spec`` raises for ``jsonschema``.

    Raising (rather than returning ``None``) makes the import fail here and
    now, which is what lets the effectiveness assertion distinguish "blocked"
    from "not installed at all". ``find_spec`` is the API Python 3.12+
    consults; a ``find_module``-only finder would be skipped and the import
    would succeed, leaving the outcome assertion vacuous.
    """

    def find_spec(
        self,
        fullname: str,
        path: object,
        target: object | None = None,
    ) -> (
        importlib.machinery.ModuleSpec | None
    ):  # pragma: no cover - never returns for the blocked name
        if fullname == "jsonschema" or fullname.startswith("jsonschema."):
            raise ImportError(f"blocked by cold-install probe: {fullname}")
        return None


@contextlib.contextmanager
def _without_jsonschema() -> Iterator[None]:
    """Make ``jsonschema`` unimportable and force ``skill_harness.sitegen`` to
    re-import against that, restoring both on exit."""
    saved: dict[str, object] = {
        name: module
        for name, module in list(sys.modules.items())
        if _matches(_JSONSCHEMA_PREFIXES, name) or _matches(_SITEGEN_PREFIXES, name)
    }
    for name in list(saved):
        del sys.modules[name]
    blocker = _JsonschemaBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        for name in [
            n
            for n in sys.modules
            if _matches(_JSONSCHEMA_PREFIXES, n) or _matches(_SITEGEN_PREFIXES, n)
        ]:
            del sys.modules[name]
        sys.modules.update(saved)  # type: ignore[arg-type]


def _assert_blocker_effective() -> None:
    """The probe must actually make ``jsonschema`` unimportable.

    Asserted inside the blocked context, after the precondition, before every
    cold-install outcome so the outcome cannot pass vacuously in CI, where
    ``jsonschema`` is always installed: a probe that failed to block would let
    ``import jsonschema`` succeed, and a lazy-import regression would then
    surface as a green test rather than a red one.
    """
    with pytest.raises(ImportError, match="jsonschema"):
        import jsonschema  # noqa: F401


def _assert_jsonschema_installed() -> None:
    """Precondition: ``jsonschema`` is genuinely importable in this environment.

    Checked BEFORE the blocker is installed (``find_spec`` consults the same
    meta-path the blocker installs onto). CI always installs ``[dev]``, so
    ``jsonschema`` is always present there; this precondition holds the
    blocker to the standard that it must defeat a real, present package, not
    merely observe one that was never installed.
    """
    assert importlib.util.find_spec("jsonschema") is not None, (
        "precondition: jsonschema must be installed in CI for the blocker to be "
        "distinguishable from genuine absence"
    )


# ---------------------------------------------------------------------------
# Importing the affected modules succeeds without jsonschema (lazy import)
# ---------------------------------------------------------------------------


def test_sitegen_imports_without_jsonschema() -> None:
    """A core install imports the package without the [sitegen] extra.

    Before #415 the top-level ``from jsonschema import Draft202012Validator``
    made this raise ``ModuleNotFoundError`` at import time. The import now sits
    behind a typed seam, so importing the module succeeds; the build fails
    later, at use time, with the extra's name.
    """
    _assert_jsonschema_installed()
    with _without_jsonschema():
        _assert_blocker_effective()
        sitegen = importlib.import_module("skill_harness.sitegen")
        importlib.import_module("skill_harness.sitegen.__main__")
        # The typed error is exported on the freshly imported module.
        assert hasattr(sitegen, "SitegenNotInstalledError")


# ---------------------------------------------------------------------------
# A build refuses at use time with a typed error naming the extra
# ---------------------------------------------------------------------------


def test_build_site_refuses_with_typed_error_naming_the_extra(tmp_path: Path) -> None:
    """Without jsonschema, ``build_site`` fails at use time, not import time.

    The failure is ``SitegenNotInstalledError`` and its message names the extra
    to install (``skill-harness[sitegen]``), so the operator can act on it
    rather than reading a bare ``ModuleNotFoundError``.
    """
    _assert_jsonschema_installed()
    with _without_jsonschema():
        _assert_blocker_effective()
        from skill_harness.sitegen import SitegenNotInstalledError, build_site

        receipts = tmp_path / "receipts"
        receipts.mkdir()
        output = tmp_path / "site"

        with pytest.raises(SitegenNotInstalledError, match=r"skill-harness\[sitegen\]"):
            build_site(
                schema_path=_SCHEMA,
                receipts_dir=receipts,
                extraction_path=None,
                output_dir=output,
                marker="cold-install-marker",
            )
        assert not output.exists()


def test_module_entry_point_refuses_with_install_hint_without_extra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``python -m skill_harness.sitegen <build>`` refuses with the extra's name.

    The entry point catches the typed error and prints an actionable refusal
    to stderr, returning a non-zero exit, rather than crashing on an uncaught
    ``ImportError`` from a top-level import.
    """
    _assert_jsonschema_installed()
    with _without_jsonschema():
        _assert_blocker_effective()
        from skill_harness.sitegen.__main__ import main

        receipts = tmp_path / "receipts"
        receipts.mkdir()
        output = tmp_path / "site"

        exit_code = main(
            [
                "--schema",
                str(_SCHEMA),
                "--receipts",
                str(receipts),
                "--output",
                str(output),
                "--marker",
                "cold-install-marker",
            ]
        )

        assert exit_code == 1
        assert not output.exists()
        stderr = capsys.readouterr().err
        assert "REFUSED" in stderr
        assert "skill-harness[sitegen]" in stderr


# ---------------------------------------------------------------------------
# --help runs without jsonschema (argparse answers before any build)
# ---------------------------------------------------------------------------


def test_module_help_runs_without_jsonschema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--help`` answers without the [sitegen] extra.

    ``--help`` is resolved by argparse during ``parse_args``, before any build
    and therefore before any lazy ``jsonschema`` import. A top-level import of
    ``jsonschema.exceptions`` (the pre-#415 state) made even ``--help`` crash
    at import time; the lazy import lets the entry point's help surface stay
    reachable on a core install.
    """
    _assert_jsonschema_installed()
    with _without_jsonschema():
        _assert_blocker_effective()
        from skill_harness.sitegen.__main__ import main

        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "python -m skill_harness.sitegen" in out
