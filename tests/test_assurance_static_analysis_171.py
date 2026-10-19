"""External contract checks for the issue #171 assurance configuration."""

import re
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


def test_coverage_floor_report_has_branch_results_and_honesty_warning() -> None:
    report_path = ROOT / "docs/assurance/coverage-floors.md"
    assert report_path.is_file()
    report = report_path.read_text(encoding="utf-8")
    lower = report.lower()

    assert "--cov-branch" in report
    assert "coverage proves nothing about correctness" in lower

    module_paths = sorted(
        path.relative_to(ROOT).as_posix()
        for package in ("aggregation", "ablation")
        for path in (ROOT / "src/skill_harness" / package).glob("*.py")
    )
    for module_path in module_paths:
        row = next(line for line in report.splitlines() if f"`{module_path}`" in line)
        fields = [field.strip() for field in row.strip("|").split("|")]

        # A module with no branches gets no percentage. Coverage.py calls that
        # 100%, which is arithmetically true and carries no information, and an
        # empty 100% is precisely the figure a later reader quotes.
        if fields[-1] == "no branches":
            assert fields[-2] == "n/a", f"{module_path}: 0-branch row must print n/a"
            assert fields[1] == "0", f"{module_path}: 'no branches' row must have 0 branches"
            continue

        percentage = re.fullmatch(r"([0-9.]+)%", fields[-2])
        assert percentage is not None, f"no branch percentage in the row for {module_path}"
        branch_coverage = float(percentage.group(1))

        # The flag encodes the report's stated attention rule, which reads BOTH
        # instruments: a module is flagged when either figure is under the floor,
        # or when mutation never measured it. A row can therefore read BELOW on a
        # healthy branch percentage, and that is the point of pairing the columns.
        mutation_field = fields[-3]
        mutation = re.fullmatch(r"([0-9.]+)%", mutation_field)
        needs_attention = (
            branch_coverage < 80.0
            or mutation_field == "absent"
            or (mutation is not None and float(mutation.group(1)) < 80.0)
        )
        expected = "BELOW 80%" if needs_attention else "OK"
        assert fields[-1] == expected, (
            f"{module_path}: floor says {fields[-1]!r}, attention rule says {expected!r} "
            f"(branch {branch_coverage}%, mutation {mutation_field})"
        )
