"""README first-screen lock (#734).

The README is the PyPI long description. Its first screen must tell a stranger
who the tool is for and how to install it, and must not use a term before it
defines it (PRODUCT.md, Brand Commitments: "A term met before it is defined is
a defect").
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FIRST_SCREEN = 40


def _lines() -> list[str]:
    return (_ROOT / "README.md").read_text(encoding="utf-8").splitlines()


def _sentence_holding_first(term: str) -> str:
    flat = " ".join(" ".join(_lines()).split())
    first = re.search(rf"\b{term}\b", flat)
    assert first is not None, f"{term!r} never appears"
    start = flat.rfind(". ", 0, first.start()) + 2
    end = flat.find(". ", first.end())
    return flat[start:end]


def _audience() -> str:
    product = (_ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    users = product.split("## Users\n\n", 1)[1]
    return users.split("\n", 1)[0].removeprefix("A person ").rstrip(".")


def test_install_line_is_on_the_first_screen() -> None:
    first_screen = _lines()[:_FIRST_SCREEN]

    assert any(line.startswith("pip install skill-harness") for line in first_screen)


def test_audience_from_product_users_is_on_the_first_screen() -> None:
    first_screen = " ".join(_lines()[:_FIRST_SCREEN])

    assert _audience() in first_screen


def test_epoch_is_defined_in_the_sentence_that_first_uses_it() -> None:
    assert "an epoch is" in _sentence_holding_first("epoch")


def test_null_is_defined_in_the_sentence_that_first_uses_it() -> None:
    assert "Null condition (no skill)" in _sentence_holding_first("Null")
