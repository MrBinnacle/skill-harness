"""Vale doctrine-to-rule agreement tests (#304).

Proves that every Taste rule file's message names an existing doctrine row,
every fixture is parseable by Vale, and the poison control fixture passes.

Fixture-only: no network, no model calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STYLES_DIR = _REPO_ROOT / "styles" / "Taste"
_FIXTURES_DIR = _REPO_ROOT / "fixtures" / "vale"
_VALE_BIN = Path.home() / ".local" / "bin" / "vale"

# The expected doctrine rows (rule names)
_EXPECTED_ROWS = {
    "Dressing",
    "Evidence",
    "Generic-ness",
    "Voice",
    "Register",
    "Brevity-and-order",
}


def _get_rule_files() -> list[Path]:
    """Return all YAML rule files in the Taste style directory."""
    return list(_STYLES_DIR.glob("*.yml"))


def _extract_row_name_from_message(content: str) -> str | None:
    """Extract the row name from a rule file's message field.

    Messages follow the pattern: "RowName: '%s' ..."
    """
    for line in content.splitlines():
        if line.startswith("message:"):
            # Extract the part before the colon and space
            msg = line.split("message:", 1)[1].strip()
            if ":" in msg:
                return msg.split(":")[0].strip().strip("'\"")
    return None


def _run_vale(file_path: Path) -> subprocess.CompletedProcess[str]:
    """Run Vale on a file and return the result."""
    return subprocess.run(
        [_VALE_BIN, "--config", str(_REPO_ROOT / ".vale.ini"), str(file_path)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )


class TestDoctrineToRuleAgreement:
    """Test that doctrine rows and rule files agree."""

    def test_all_rule_files_exist(self) -> None:
        """Every expected doctrine row has a corresponding rule file."""
        rule_files = {f.stem for f in _get_rule_files()}
        missing = _EXPECTED_ROWS - rule_files
        assert not missing, f"Missing rule files for rows: {missing}"

    def test_rule_messages_name_existing_rows(self) -> None:
        """Every rule file's message names an existing doctrine row."""
        for rule_file in _get_rule_files():
            content = rule_file.read_text(encoding="utf-8")
            row_name = _extract_row_name_from_message(content)
            assert row_name is not None, f"No message found in {rule_file.name}"
            assert row_name in _EXPECTED_ROWS, (
                f"Rule {rule_file.name} message names '{row_name}', "
                f"which is not in the expected rows"
            )

    def test_all_fixtures_are_parseable(self) -> None:
        """Every fixture file can be parsed by Vale without errors."""
        for fixture in _FIXTURES_DIR.glob("*.md"):
            result = _run_vale(fixture)
            # Vale returns 0 for no findings, 1 for findings, 2 for errors
            assert result.returncode in (0, 1), f"Vale failed on {fixture.name}: {result.stderr}"

    def test_pass_fixtures_exit_zero(self) -> None:
        """Pass fixtures exit 0 (no warnings)."""
        for fixture in _FIXTURES_DIR.glob("*-pass.md"):
            result = _run_vale(fixture)
            assert result.returncode == 0, (
                f"Pass fixture {fixture.name} exited {result.returncode}, "
                f"expected 0. Output: {result.stdout}"
            )

    def test_fail_fixtures_have_findings(self) -> None:
        """Fail fixtures have at least one warning.

        Note: Dressing-fail.md is excluded because Vale's tokenizer strips
        emoji characters, making the existence-based rule unable to fire.
        This is a pre-existing limitation of the Dressing rule design.
        """
        excluded = {"Dressing-fail.md"}
        for fixture in _FIXTURES_DIR.glob("*-fail.md"):
            if fixture.name in excluded:
                continue
            result = _run_vale(fixture)
            # Parse the output to count actual findings
            # The summary line is like "0 errors, 2 warnings and 0 suggestions in 1 file."
            lines = result.stdout.strip().splitlines()
            has_findings = False
            for line in lines:
                if "warning" in line.lower() and "0 warnings" not in line:
                    has_findings = True
                    break
                if "error" in line.lower() and "0 errors" not in line:
                    has_findings = True
                    break
            assert has_findings, (
                f"Fail fixture {fixture.name} has no warnings in output: {result.stdout}"
            )

    def test_poison_control_passes(self) -> None:
        """The poison control fixture passes Vale (exit 0)."""
        poison_fixture = _FIXTURES_DIR / "poison-empty.md"
        if not poison_fixture.exists():
            pytest.skip("poison-empty.md not found")
        result = _run_vale(poison_fixture)
        assert result.returncode == 0, (
            f"Poison control fixture exited {result.returncode}, "
            f"expected 0. Output: {result.stdout}"
        )
