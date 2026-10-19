"""Report stamps must carry the true harness version, even from an uninstalled
source tree.

Regression guard for the fallback that fires on ``PackageNotFoundError`` (running
from a source checkout with no installed dist). The fallback must resolve to the
package's own ``__version__`` — NOT a hardcoded string literal, which silently
goes stale one release after every bump (it was two minors behind at v0.2.0).
"""

from __future__ import annotations

import importlib.metadata
from unittest.mock import patch

import skill_harness
from skill_harness.cli.main import _resolve_harness_version


def test_resolve_uses_installed_metadata_when_available() -> None:
    with patch("importlib.metadata.version", return_value="9.9.9"):
        assert _resolve_harness_version() == "9.9.9"


def test_resolve_falls_back_to_package_version_not_a_stale_literal() -> None:
    # Uninstalled source tree: metadata lookup raises. The fallback must equal
    # the package's own __version__ so it can never drift from the real release.
    with patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        assert _resolve_harness_version() == skill_harness.__version__
