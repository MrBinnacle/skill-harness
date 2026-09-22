"""#580: contributor setup must prescribe an isolated virtual environment."""

from __future__ import annotations

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
