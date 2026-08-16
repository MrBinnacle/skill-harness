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


_DRIFT_CANDIDATES = ("AC-1", "AC-2", "AC-3", "AC-4")


def _row_status_violations(closeout: str, drift_config: str) -> list[str]:
    """Disagreements between the close-out's per-candidate status word and the
    rows actually configured in ``scripts/drift_check.py``.

    The close-out text is whitespace-normalized first, so a status word split
    across a line wrap still reads as the claim it makes (the drift check's
    registered-text rule, same reason).
    """
    flat = " ".join(closeout.split())
    violations: list[str] = []
    for candidate in _DRIFT_CANDIDATES:
        claims_configured = f"{candidate} CONFIGURED" in flat
        claims_unconfigured = f"{candidate} NOT CONFIGURED" in flat
        if claims_configured == claims_unconfigured:
            violations.append(f"{candidate}: close-out states no single status word")
            continue
        is_row = f'dc_id="{candidate}"' in drift_config
        if is_row != claims_configured:
            stated = "CONFIGURED" if claims_configured else "NOT CONFIGURED"
            held = "has" if is_row else "has no"
            violations.append(
                f"{candidate}: close-out says {stated} but scripts/drift_check.py {held} such row"
            )
    return violations


def test_closeout_row_status_matches_the_configured_drift_rows() -> None:
    """The close-out's per-candidate status must equal what the script enforces.

    #174 landed AC-1..AC-4 as candidates only, and this check pinned that
    nothing had been configured. #248 configures them one at a time, so the
    fixed "nothing configured" reading expired; keeping it would have gone
    green only by refusing to look. The contract now compares the two surfaces
    directly: a candidate the doc calls CONFIGURED must exist as a row in
    ``scripts/drift_check.py``, and a candidate it calls NOT CONFIGURED must
    not. Configuring a row while leaving the doc's status word behind — or
    claiming a status the table never gained — turns this red.
    """
    text = CLOSEOUT.read_text(encoding="utf-8")
    drift_config = (ROOT / "scripts/drift_check.py").read_text(encoding="utf-8")

    assert "## Proposed drift-check candidates" in text
    assert all(candidate in text for candidate in _DRIFT_CANDIDATES)
    assert _row_status_violations(text, drift_config) == []


def test_row_status_check_rejects_both_directions_of_disagreement() -> None:
    """Red-phase guard: the comparison above must fail when either surface lies.

    Calls the same helper the contract calls, on synthetic surfaces, so the
    criterion cannot go quietly vacuous — an always-empty violation list would
    fail here.
    """
    table_with_ac1_only = 'dc_id="AC-1"'

    overclaimed = "AC-1 CONFIGURED. AC-2 CONFIGURED. AC-3 NOT CONFIGURED. AC-4 NOT CONFIGURED."
    assert any(
        "AC-2" in violation and "has no such row" in violation
        for violation in _row_status_violations(overclaimed, table_with_ac1_only)
    )

    underclaimed = (
        "AC-1 NOT CONFIGURED. AC-2 NOT CONFIGURED. AC-3 NOT CONFIGURED. AC-4 NOT CONFIGURED."
    )
    assert any(
        "AC-1" in violation and "has such row" in violation
        for violation in _row_status_violations(underclaimed, table_with_ac1_only)
    )

    both_words = "AC-1 CONFIGURED. AC-1 NOT CONFIGURED. AC-2 NOT CONFIGURED."
    assert any(
        "AC-1: close-out states no single status word" in violation
        for violation in _row_status_violations(both_words, table_with_ac1_only)
    )


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
