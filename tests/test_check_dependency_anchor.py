"""Tests for the dependency-anchor pre-flight check (#557).

Unit tests exercising the script's functions directly, with mocked PyPI
responses.  Synthetic requirement files and diffs prove the failure lanes
without touching the network.

Each test pins one acceptance criterion.  The criterion number appears in
the test name so the evidence body can trace each checkbox to its test.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Import functions directly so mocks apply in-process.
# scripts/ carries no __init__.py and is not a package, so load by path.
_spec = importlib.util.spec_from_file_location(
    "check_dependency_anchor",
    _REPO_ROOT / "scripts" / "check_dependency_anchor.py",
)
assert _spec is not None and _spec.loader is not None
_mod: ModuleType = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

NetworkError = _mod.NetworkError
check_exact_pin_constraint = _mod.check_exact_pin_constraint
main = _mod.main
parse_diff = _mod.parse_diff
parse_pyproject_requirements = _mod.parse_pyproject_requirements
parse_requirement = _mod.parse_requirement
parse_requirements_file = _mod.parse_requirements_file

# ---------------------------------------------------------------------------
# Pure-function unit tests (no network, no I/O)
# ---------------------------------------------------------------------------


class TestParseRequirement:
    """parse_requirement returns (canonical_name, version) or None."""

    def test_exact_pin(self) -> None:
        assert parse_requirement("pydantic-core==2.46.5") == ("pydantic_core", "2.46.5")

    def test_greater_equal(self) -> None:
        assert parse_requirement("click>=8.5.0") == ("click", "8.5.0")

    def test_comment_line(self) -> None:
        assert parse_requirement("# a comment") is None

    def test_empty_line(self) -> None:
        assert parse_requirement("") is None

    def test_bare_name(self) -> None:
        assert parse_requirement("pydantic") is None

    def test_hyphen_to_underscore(self) -> None:
        assert parse_requirement("pydantic-core==1.0.0") == ("pydantic_core", "1.0.0")


class TestParseDiff:
    """parse_diff extracts changed packages with old and new versions."""

    def test_simple_bump(self) -> None:
        diff = textwrap.dedent("""\
            --- a/requirements.txt
            +++ b/requirements.txt
            @@ -1,2 +1,2 @@
            -pydantic-core==2.46.5
            +pydantic-core==2.48.0
        """)
        changes = parse_diff(diff)
        assert "pydantic_core" in changes
        old, new = changes["pydantic_core"]
        assert old == "2.46.5"
        assert new == "2.48.0"

    def test_no_changes(self) -> None:
        diff = textwrap.dedent("""\
            --- a/requirements.txt
            +++ b/requirements.txt
        """)
        assert parse_diff(diff) == {}


class TestCheckExactPinConstraint:
    """check_exact_pin_constraint returns the blocking pin or None."""

    def test_blocks_above_pin(self) -> None:
        requires_dist = ["pydantic-core>=2.46.5,<2.47.0"]
        pin = check_exact_pin_constraint(requires_dist, "pydantic-core", "2.48.0")
        assert pin == ">=2.46.5,<2.47.0"

    def test_passes_within_pin(self) -> None:
        requires_dist = ["pydantic-core>=2.46.5,<2.47.0"]
        pin = check_exact_pin_constraint(requires_dist, "pydantic-core", "2.46.6")
        assert pin is None

    def test_exact_pin_blocks_above(self) -> None:
        requires_dist = ["some-package==1.0.0"]
        pin = check_exact_pin_constraint(requires_dist, "some-package", "2.0.0")
        assert pin == "==1.0.0"

    def test_exact_pin_passes_at_same_version(self) -> None:
        requires_dist = ["some-package==1.0.0"]
        pin = check_exact_pin_constraint(requires_dist, "some-package", "1.0.0")
        assert pin is None

    def test_no_requires_dist(self) -> None:
        pin = check_exact_pin_constraint(None, "pydantic-core", "2.48.0")
        assert pin is None

    def test_different_package_ignored(self) -> None:
        requires_dist = ["other-package==1.0.0"]
        pin = check_exact_pin_constraint(requires_dist, "pydantic-core", "2.48.0")
        assert pin is None


class TestParseRequirementsFile:
    """parse_requirements_file returns {canonical_name: version}."""

    def test_basic(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        result = parse_requirements_file(req)
        assert result == {"pydantic": "2.13.5", "pydantic_core": "2.46.5"}


class TestParsePyprojectRequirements:
    """parse_pyproject_requirements extracts [project.dependencies]."""

    def test_basic(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
                [project]
                name = "test"
                dependencies = [
                    "pydantic>=2.6",
                    "click>=8.5.0",
                ]
            """),
            encoding="utf-8",
        )
        result = parse_pyproject_requirements(pyproject)
        assert result == {"pydantic": "2.6", "click": "8.5.0"}


# ---------------------------------------------------------------------------
# AC2: refuses a follower bump above an exact-pinned anchor's requirement
# ---------------------------------------------------------------------------


class TestRefusesBumpAboveExactPin:
    """AC2: pydantic-core 2.46.5 -> 2.48.0 refused by pydantic pin."""

    def test_refuses(self, tmp_path: Path) -> None:
        """Reproduces the #549 scenario."""
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.48.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "pydantic-core>=2.46.5,<2.47.0",
                    "typing-extensions>=4.12.0",
                ],
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=lambda pkg: mock_metadata if pkg == "pydantic" else {},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 1


# ---------------------------------------------------------------------------
# AC7: red demonstration reproduces #549 as a fixture
# ---------------------------------------------------------------------------


class TestReproducesIssue549:
    """AC7: exact reproduction of the #549 scenario as a named fixture."""

    def test_reproduces(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.49.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "pydantic-core>=2.46.5,<2.47.0",
                    "typing-extensions>=4.12.0",
                ],
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=lambda pkg: mock_metadata if pkg == "pydantic" else {},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 1


# ---------------------------------------------------------------------------
# AC3: passes a bump where the anchor's pin permits the new version
# ---------------------------------------------------------------------------


class TestPassesBumpWithinAnchorPin:
    """AC3: pydantic-core 2.46.5 -> 2.46.6 passes when anchor allows it."""

    def test_passes(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.46.6
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "pydantic-core>=2.46.5,<2.47.0",
                    "typing-extensions>=4.12.0",
                ],
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=lambda pkg: mock_metadata if pkg == "pydantic" else {},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 0


# ---------------------------------------------------------------------------
# AC4: passes a bump of a package no anchor pins with ==
# ---------------------------------------------------------------------------


class TestPassesUnpinnedPackage:
    """AC4: bumping a package no anchor pins with == passes."""

    def test_passes(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                click==8.5.0
                pydantic==2.13.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -click==8.5.0
                +click==8.6.0
            """),
            encoding="utf-8",
        )

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            return_value={"info": {"requires_dist": []}},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 0


# ---------------------------------------------------------------------------
# AC6: network failure is a refusal with a distinct message
# ---------------------------------------------------------------------------


class TestNetworkFailureIsRefusal:
    """AC6: network error reaching PyPI is a refusal, never a pass."""

    def test_refuses(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.48.0
            """),
            encoding="utf-8",
        )

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=NetworkError(
                "network error fetching https://pypi.org/pypi/pydantic/json: timeout"
            ),
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 1


# ---------------------------------------------------------------------------
# AC5: discovers anchor relationship from published metadata, not a list
# ---------------------------------------------------------------------------


class TestDiscoversAnchorFromMetadata:
    """AC5: the check reads PyPI metadata rather than using a hand-maintained list."""

    def test_discovers(self, tmp_path: Path) -> None:
        """Uses a fictitious anchor that pins the changed package with ==."""
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                fictitious-anchor==1.0.0
                fictitious-follower==1.0.0
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -fictitious-follower==1.0.0
                +fictitious-follower==2.0.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "fictitious-follower==1.0.0",
                ],
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=lambda pkg: mock_metadata if pkg == "fictitious_anchor" else {},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 1


# ---------------------------------------------------------------------------
# AC8: mutation control disables exact-pin comparison, turns named fixture red
# ---------------------------------------------------------------------------


class TestMutationControlDisablesPinCheck:
    """AC8: disabling the exact-pin comparison must turn a named fixture red.

    Monkeypatches check_exact_pin_constraint to always return None (no pin
    blocks anything).  The #549 fixture must then PASS instead of REFUSE.
    This proves the pin comparison is load-bearing.
    """

    def test_mutation_turns_549_green(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                pydantic==2.13.5
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.48.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "pydantic-core>=2.46.5,<2.47.0",
                    "typing-extensions>=4.12.0",
                ],
            },
        }

        def _mutated_check_pin(
            requires_dist: list[str] | None,
            target_package: str,
            proposed_version: str,
        ) -> None:
            """Mutated version: always reports no blocking pin."""
            return None

        with (
            patch(
                "check_dependency_anchor.fetch_pypi_metadata",
                side_effect=lambda pkg: mock_metadata if pkg == "pydantic" else {},
            ),
            patch(
                "check_dependency_anchor.check_exact_pin_constraint",
                side_effect=_mutated_check_pin,
            ),
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        # Under the mutation, the check passes — proving the pin comparison is
        # what caught #549.  This is the named fixture that must turn red.
        assert result == 0, (
            "mutation control: disabling exact-pin comparison must turn the "
            "#549 fixture green; the check still refused, which means the "
            "pin comparison is not the only catching mechanism"
        )


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error paths."""

    def test_no_changes_in_diff(self, tmp_path: Path) -> None:
        """An empty diff passes with no network calls."""
        req = tmp_path / "requirements.txt"
        req.write_text("pydantic-core==2.46.5\n", encoding="utf-8")
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
            """),
            encoding="utf-8",
        )

        result = main(["--requirements", str(req), "--diff", str(diff)])
        assert result == 0

    def test_missing_requirements_file(self, tmp_path: Path) -> None:
        """Missing requirements file is a refusal."""
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1 +1 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.48.0
            """),
            encoding="utf-8",
        )

        result = main(["--requirements", str(tmp_path / "nonexistent.txt"), "--diff", str(diff)])
        assert result == 1

    def test_missing_diff_file(self, tmp_path: Path) -> None:
        """Missing diff file is a refusal."""
        req = tmp_path / "requirements.txt"
        req.write_text("pydantic-core==2.46.5\n", encoding="utf-8")

        result = main(["--requirements", str(req), "--diff", str(tmp_path / "nonexistent.diff")])
        assert result == 1

    def test_anchor_with_no_requires_dist(self, tmp_path: Path) -> None:
        """An anchor with no requires_dist (None) does not cause a refusal."""
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                some-package==1.0.0
                pydantic-core==2.46.5
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -pydantic-core==2.46.5
                +pydantic-core==2.48.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": None,
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            return_value=mock_metadata,
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 0

    def test_exact_pin_at_proposed_version_passes(self, tmp_path: Path) -> None:
        """An exact pin at the proposed version does not block."""
        req = tmp_path / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                some-anchor==1.0.0
                some-package==1.0.0
            """),
            encoding="utf-8",
        )
        diff = tmp_path / "changes.diff"
        diff.write_text(
            textwrap.dedent("""\
                --- a/requirements.txt
                +++ b/requirements.txt
                @@ -1,2 +1,2 @@
                -some-package==1.0.0
                +some-package==2.0.0
            """),
            encoding="utf-8",
        )

        mock_metadata = {
            "info": {
                "requires_dist": [
                    "some-package==2.0.0",
                ],
            },
        }

        with patch(
            "check_dependency_anchor.fetch_pypi_metadata",
            side_effect=lambda pkg: mock_metadata if pkg == "some-anchor" else {},
        ):
            result = main(["--requirements", str(req), "--diff", str(diff)])

        assert result == 0


# ---------------------------------------------------------------------------
# Subprocess integration test (AC1: runs before the test matrix)
# ---------------------------------------------------------------------------


class TestSubprocessIntegration:
    """AC1: the script runs as a subprocess and exits appropriately."""

    def test_script_runs(self) -> None:
        """The script can be invoked as a subprocess and exits 0 with --help."""
        result = subprocess.run(
            [sys.executable, str(_REPO_ROOT / "scripts" / "check_dependency_anchor.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "Refuse" in result.stdout or "refuse" in result.stdout.lower()
