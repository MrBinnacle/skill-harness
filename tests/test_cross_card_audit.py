"""Cross-card audit screen tests (#652).

Tests that the cross-card audit script produces the expected finding document
and that the receipts-index.md is updated to include it.

The script runs the public ``skill audit`` command and uses its offline,
deterministic report to render the finding. The test verifies the output contract.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "cross_card_audit.py"
_FINDING = _REPO_ROOT / "docs" / "findings" / "cross-card-audit-screen.md"
_INDEX = _REPO_ROOT / "docs" / "receipts-index.md"


@pytest.fixture()
def audit_output() -> str:
    """Run the cross-card audit script and return its stdout."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env={"PYTHONPATH": str(_REPO_ROOT / "src"), **os.environ},
        check=False,
    )
    assert result.returncode == 0, f"script failed:\n{result.stderr}"
    return result.stdout


class TestCrossCardAuditScript:
    """Tests for the cross-card audit script contract."""

    def test_script_exits_cleanly(self, audit_output: str) -> None:
        """The script must run without error."""
        assert audit_output, "script produced no output"

    def test_output_has_ranked_table(self, audit_output: str) -> None:
        """The output reports each Stage-0 field the ticket names."""
        assert "## Ranked table" in audit_output
        assert "| Rank | Card |" in audit_output
        assert "| ---: | --- |" in audit_output
        assert "Standing (raw)" in audit_output
        assert "Measurable claims" in audit_output
        assert "Available Tier-1 axes" in audit_output
        assert "Claim class" in audit_output
        assert "Hazard family plausible?" in audit_output
        assert "Hazard family exists?" in audit_output
        assert "Out of reach, because" in audit_output

    def test_table_population_is_exactly_the_declared_published_population(
        self, audit_output: str
    ) -> None:
        """The table must not add fixtures or screen copies to #652's population."""
        result = subprocess.run(
            ["git", "ls-files", "skills/*/*/SKILL.md"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
            check=True,
        )
        expected_paths = sorted(result.stdout.splitlines())
        actual_paths = re.findall(r"\| `([^`]+/SKILL\.md)` \|", audit_output)
        assert actual_paths == expected_paths
        assert "tests/fixtures/" not in audit_output
        assert "scripts/screens/" not in audit_output

    def test_output_has_method_section(self, audit_output: str) -> None:
        """The output must document its method."""
        assert "## Method" in audit_output

    def test_empty_published_population_is_reported_without_a_substitute(
        self, audit_output: str
    ) -> None:
        """An empty declared population is a result, not permission to invent one."""
        assert 'No published cards matched `git ls-files "skills/*/*/SKILL.md"`.' in audit_output


class TestFindingDocument:
    """Tests for the committed finding document contract."""

    def test_finding_exists(self) -> None:
        """docs/findings/cross-card-audit-screen.md must exist."""
        assert _FINDING.is_file(), (
            "finding document not found at docs/findings/cross-card-audit-screen.md"
        )

    def test_finding_is_the_generated_audit_output(self, audit_output: str) -> None:
        """The committed finding is the generator's output over the sibling collection.

        The population lives in the ``skills`` clone (``--collection``), which CI does not
        hold, so the byte-for-byte check is against the generator's fixed text: every
        line the generator prints independently of the population must appear verbatim,
        the status block must pin the collection commit, and the table must be non-empty.
        """
        text = _FINDING.read_text(encoding="utf-8")
        fixed = [
            line
            for line in audit_output.splitlines()
            if line
            and "published card" not in line
            and "collection at `" not in line
            and "read at" not in line
            and not line.startswith("No ")
        ]
        for line in fixed:
            assert line in text, f"generator line missing from the finding: {line!r}"
        assert re.search(r"in the skills collection at `[0-9a-f]{7,}`", text)
        assert re.search(r"^> (\d+) published card\(s\)\.$", text, re.M)
        assert re.findall(r"\| `(skills/[^`]+/SKILL\.md)` \|", text)

    def test_finding_has_claims_and_refuses(self) -> None:
        """The finding must state claims and refuses-to-claim."""
        text = _FINDING.read_text(encoding="utf-8")
        assert "**Claims:**" in text
        assert "**Refuses to claim:**" in text


class TestReceiptsIndex:
    """Tests that receipts-index.md includes the new finding."""

    def test_index_includes_finding(self) -> None:
        """The receipts index must list the new finding document."""
        text = _INDEX.read_text(encoding="utf-8")
        assert "### [`docs/findings/cross-card-audit-screen.md`]" in text
