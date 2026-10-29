"""Root layout lock (#858, phase 1).

Phase 1 moved seven root entries to the places a reader of a Python project
expects them. A file that reappears at an old path splits its readers between
two copies, so each old path must stay empty and each new path must exist.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

_MOVES = {
    "prototypes": "examples/prototypes",
    "PRODUCT.md": "docs/PRODUCT.md",
    "DESIGN.md": "docs/design/DESIGN.md",
    ".impeccable/design.json": "docs/design/design.json",
    ".vale.ini": ".config/vale/.vale.ini",
    "styles": ".config/vale/styles",
    "fixtures/vale": "tests/fixtures/vale",
}


@pytest.mark.parametrize(("old", "new"), sorted(_MOVES.items()))
def test_moved_entry_lives_only_at_its_new_path(old: str, new: str) -> None:
    assert not (_ROOT / old).exists(), f"{old} is back at the root"
    assert (_ROOT / new).exists(), f"{new} is missing"


def test_pyright_config_lives_in_pyproject_at_the_runtime_floor() -> None:
    assert not (_ROOT / "pyrightconfig.json").exists()
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = pyproject["project"]["requires-python"].removeprefix(">=")
    assert pyproject["tool"]["pyright"]["pythonVersion"] == floor
