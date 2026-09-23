"""Cross-card audit screen tests (#652).

Tests that the cross-card audit script produces the expected finding document
and that the receipts-index.md is updated to include it.

Seam: the script calls audit_skill_artifact() from skill_harness.preflight,
which is offline and deterministic. The test verifies the output contract.
"""

from __future__ import annotations

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
        env={"PYTHONPATH": str(_REPO_ROOT / "src"), **__import__("os").environ},
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
        """The output must contain a ranked table with a header row."""
        assert "## Ranked table" in audit_output
        assert "| Rank | Card |" in audit_output
        assert "| ---: | --- |" in audit_output

    def test_every_published_card_has_a_row(self, audit_output: str) -> None:
        """Every known published SKILL.md must appear in the ranked table."""
        known_cards = [
            "pull-rebase",
            "push-secret-scan",
            "declared-synthetic-positive-control",
        ]
        for card in known_cards:
            assert card in audit_output, f"card {card!r} missing from ranked table"

    def test_output_has_method_section(self, audit_output: str) -> None:
        """The output must document its method."""
        assert "## Method" in audit_output

    def test_output_has_per_card_detail(self, audit_output: str) -> None:
        """The output must have per-card detail sections."""
        assert "## Per-card detail" in audit_output
        assert "### pull-rebase" in audit_output
        assert "### push-secret-scan" in audit_output


class TestFindingDocument:
    """Tests for the committed finding document contract."""

    def test_finding_exists(self) -> None:
        """docs/findings/cross-card-audit-screen.md must exist."""
        assert _FINDING.is_file(), (
            "finding document not found at docs/findings/cross-card-audit-screen.md"
        )

    def test_finding_has_ranked_table(self) -> None:
        """The finding must contain the ranked table."""
        text = _FINDING.read_text(encoding="utf-8")
        assert "## Ranked table" in text
        assert "| Rank | Card |" in text

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
        assert "cross-card-audit-screen" in text
