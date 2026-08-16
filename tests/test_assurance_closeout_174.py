"""External contract checks for the issue #174 assurance close-out."""

from pathlib import Path

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
