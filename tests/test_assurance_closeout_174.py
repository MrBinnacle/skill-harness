"""External contract checks for the issue #174 assurance close-out."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = ROOT / "docs/ASSURANCE.md"


def test_closeout_records_every_named_figure_with_source_receipts() -> None:
    assert CLOSEOUT.is_file()
    text = CLOSEOUT.read_text(encoding="utf-8")

    expected = {
        "mutation": ("81.7%", "76.2%", "70.1%", "80.6%", "mutation-report.md"),
        "A/A": ("5.2%", "26 / 500", "aa-report.md"),
        "calibration": ("495 / 500", "calibration-report.md"),
        "differential": ("4,000 / 4,000", "differential-report.md"),
        "fuzz": ("60.1 minutes", "0 crashes", "fuzz-report.md"),
        "static": ("7 of 20", "coverage-floors.md"),
        "supply": ("No known vulnerabilities found", "dependency-audit.md"),
        "re-derivation": ("missing", "#173"),
    }
    for label, values in expected.items():
        assert all(value in text for value in values), f"{label} figure or receipt missing"


def test_closeout_states_named_residual_risks_and_open_findings() -> None:
    text = CLOSEOUT.read_text(encoding="utf-8")

    required = (
        "no recall claim",
        "29/33/34 clauses",
        "documented instrument property, not a bug",
        "single-maintainer review limits",
        "open findings: none",
    )
    assert all(item in text for item in required)


def test_closeout_proposes_drift_rows_without_changing_configuration() -> None:
    text = CLOSEOUT.read_text(encoding="utf-8")
    drift_config = (ROOT / "scripts/drift_check.py").read_text(encoding="utf-8")

    assert "## Proposed drift-check candidates" in text
    assert "PROPOSED, NOT CONFIGURED" in text
    assert "AC-1" in text and "AC-4" in text
    assert "AC-1" not in drift_config and "AC-4" not in drift_config


def test_closeout_omits_operator_banned_vocabulary() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_assurance_copy.py"), str(CLOSEOUT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout


def test_banned_vocabulary_check_rejects_poisoned_document(tmp_path: Path) -> None:
    poisoned = tmp_path / "ASSURANCE.md"
    poisoned.write_text("This result earned confidence.\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_assurance_copy.py"), str(poisoned)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "banned assurance vocabulary" in result.stdout


def test_closeout_ends_with_one_paragraph_bottom_line() -> None:
    text = CLOSEOUT.read_text(encoding="utf-8").rstrip()

    assert "## Bottom line" in text
    paragraph = text.rsplit("## Bottom line\n\n", 1)[1]
    assert "\n\n" not in paragraph


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="requires the issue worktree")
def test_issue_174_has_the_exact_bottom_line_comment() -> None:
    text = CLOSEOUT.read_text(encoding="utf-8").rstrip()
    paragraph = text.rsplit("## Bottom line\n\n", 1)[1]
    result = subprocess.run(
        ["gh", "issue", "view", "174", "--json", "comments", "--jq", ".comments[].body"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert paragraph in result.stdout
