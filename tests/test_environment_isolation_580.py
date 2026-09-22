"""#580: contributor setup must prescribe an isolated virtual environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_contributing_documents_an_isolated_venv_for_pytest() -> None:
    """The documented setup must keep user-site seeders out of local pytest runs.

    pytest-randomly invokes registered seeders during collection, before a test
    body can inspect the active environment. The contributor instructions are
    therefore the repository-controlled interface that prevents this failure.
    """
    contributing = (_REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    setup = contributing.split("## Development setup", maxsplit=1)[1].split("## ", maxsplit=1)[0]

    assert "python -m venv .venv" in setup
    assert "do **not** use `--system-site-packages`" in setup
    assert "ValueError: Seed must be between 0 and 2**32 - 1" in setup


def test_sers_conformance_passes_without_user_site_three_times() -> None:
    """The acceptance suite must pass when Python excludes user-site packages."""
    environment = os.environ | {"PYTHONNOUSERSITE": "1"}
    command = [sys.executable, "-m", "pytest", "tests/test_sers_conformance.py", "-q"]

    for attempt in range(1, 4):
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            cwd=_REPO_ROOT,
            env=environment,
            text=True,
        )
        assert result.returncode == 0, (
            f"SERS conformance failed on isolated attempt {attempt}/3.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
