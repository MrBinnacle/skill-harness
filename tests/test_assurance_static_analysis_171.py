"""External contract checks for the issue #171 assurance configuration."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_enables_required_rule_groups_without_blanket_ignores() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lint = config["tool"]["ruff"]["lint"]

    assert {"B", "PL", "RUF"} <= set(lint["select"])
    ignored = set(lint.get("ignore", ()))
    per_file_ignored = {
        rule for rules in lint.get("per-file-ignores", {}).values() for rule in rules
    }
    assert not ({"B", "PL", "RUF"} & ignored)
    assert not ({"B", "PL", "RUF"} & per_file_ignored)


def test_ci_randomizes_test_order_and_documents_seed_reproduction() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    pytest_step = ci.split("- name: pytest\n", 1)[1].split("- name: Upload coverage", 1)[0]
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "--randomly-seed=" in pytest_step
    assert "pytest-randomly" in contributing
    assert "--randomly-seed=" in contributing
    assert "prints" in contributing.lower() and "seed" in contributing.lower()
