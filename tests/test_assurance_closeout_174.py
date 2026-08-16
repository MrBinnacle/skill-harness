"""External contract checks for the issue #174 assurance close-out."""

import subprocess
from pathlib import Path

import pytest

from tests.test_structural_bans import _public_copy_violations

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
    """Pin the close-out to the ratified public-copy rule, not a private copy of it.

    `tests/test_structural_bans.py` is the enforcement of record: the
    `ban-public-surface-copy` pre-commit hook invokes it and CI re-runs it as
    the `structural-bans` job. Delegating here is deliberate — a second,
    narrower banned-term list kept in hand-sync is the exact failure that
    module's docstring refuses, and a narrower one would pass this criterion
    while missing copy the ratified rule bans (`earn`, `earns`, `earning`,
    `earn its slot`) and flagging copy it allows (`learned`, `earnest`).
    """
    assert _public_copy_violations(CLOSEOUT.read_text(encoding="utf-8")) == []


def test_banned_vocabulary_check_rejects_poisoned_closeout() -> None:
    """Red-phase guard: banned copy planted in the close-out must be detected.

    Calls the same scanner the assertion above calls, so the criterion cannot
    go quietly vacuous if that scanner is ever weakened.
    """
    poisoned = CLOSEOUT.read_text(encoding="utf-8") + "\nThis skill earns its place.\n"

    assert any("earn/earned family" in violation for violation in _public_copy_violations(poisoned))


def test_closeout_ends_with_one_paragraph_bottom_line() -> None:
    text = CLOSEOUT.read_text(encoding="utf-8").rstrip()

    assert "## Bottom line" in text
    paragraph = text.rsplit("## Bottom line\n\n", 1)[1]
    assert "\n\n" not in paragraph


def _gh_issue_read_blocker() -> str | None:
    """Return why `gh issue view` cannot run here, or None when it can."""
    if not (ROOT / ".git").exists():
        return "requires the issue worktree (no .git)"
    try:
        probe = subprocess.run(
            ["gh", "auth", "status"], cwd=ROOT, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        return f"gh CLI not available: {exc}"
    if probe.returncode != 0:
        return "gh CLI is not authenticated (no GH_TOKEN and no `gh auth login`)"
    return None


def test_issue_174_has_the_exact_bottom_line_comment() -> None:
    """The bottom-line paragraph must be posted verbatim as an issue comment.

    Credential-gated, not weakened: the CI test job provisions no `GH_TOKEN`,
    so an unauthenticated `gh` is a missing credential rather than a failing
    contract, and the assertion still fails loudly wherever `gh` can read the
    issue. The read also depends on a mutable remote resource — editing the
    posted comment turns this red — which is why the skip reason names the
    blocker instead of hiding behind a bare worktree check.
    """
    blocker = _gh_issue_read_blocker()
    if blocker is not None:
        pytest.skip(blocker)

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
