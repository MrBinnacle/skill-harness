"""External contract checks for the issue #174 assurance close-out."""

import hashlib
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


RECEIPT = ROOT / "docs/assurance/issue-174-bottom-line-receipt.md"
_BOTTOM_LINE_HEADING = "## Bottom line" + chr(10) * 2


def _bottom_line_paragraph() -> str:
    text = CLOSEOUT.read_text(encoding="utf-8").rstrip()
    return text.rsplit(_BOTTOM_LINE_HEADING, 1)[1]


def test_bottom_line_receipt_matches_the_closeout() -> None:
    """The ENFORCED half of the publication contract: no credential required (#354).

    The remote check below asserts the same claim more strongly, and cannot run
    in CI: the test job provisions no `GH_TOKEN`, so it skips. That skip is why
    the claim went unchecked while issue #174 had zero comments and the suite
    reported green. A contract enforced only when an unrelated side effect
    authenticates the caller is not enforced.

    This assertion reads a tracked receipt instead. It fails when the close-out's
    bottom line is edited without the receipt being re-issued, which is the
    failure mode a reader of `docs/ASSURANCE.md` actually cares about: the
    document claiming a published finding that was never published in that form.

    It deliberately does NOT prove the remote comment is currently intact. Only
    the credentialed check sees that, and this file says so rather than implying
    coverage it does not have.
    """
    assert RECEIPT.is_file(), (
        "MISSING_PUBLICATION_RECEIPT: docs/assurance/issue-174-bottom-line-receipt.md is absent,"
        " so the close-out's claim to a published bottom line has no credential-free evidence."
    )
    receipt = RECEIPT.read_text(encoding="utf-8")
    digest = hashlib.sha256(_bottom_line_paragraph().encode("utf-8")).hexdigest()
    assert digest in receipt, (
        f"RECEIPT_IS_STALE: the close-out's bottom line hashes to {digest[:12]}, which the"
        f" receipt does not record. The paragraph was edited without re-publishing it and"
        f" re-issuing the receipt, so docs/ASSURANCE.md now claims a finding published in a"
        f" form that is not the form on issue #174."
    )


def test_publication_receipt_check_rejects_a_stale_digest() -> None:
    """Negative control: the digest comparison must fail on a paragraph that moved.

    Without this, a receipt that happened to contain any 64-hex string, or a
    comparison accidentally made against the wrong text, would leave the
    assertion above green and silent.
    """
    receipt = RECEIPT.read_text(encoding="utf-8")
    moved = hashlib.sha256((_bottom_line_paragraph() + " edited").encode("utf-8")).hexdigest()
    assert moved not in receipt


def test_issue_174_has_the_exact_bottom_line_comment() -> None:
    """CORROBORATION: the paragraph is verbatim on the issue, where `gh` can look.

    Strictly stronger than the receipt check above wherever it runs, because it
    reads the live remote and therefore catches an edit or a deletion. It cannot
    run in CI (no `GH_TOKEN`), so it is explicitly NOT the enforced contract —
    `test_bottom_line_receipt_matches_the_closeout` is. Treating this skip as
    coverage is what let issue #174 sit with zero comments while the suite
    stayed green (#354).
    """
    blocker = _gh_issue_read_blocker()
    if blocker is not None:
        pytest.skip(
            f"{blocker}. Remote corroboration not performed; the enforced contract is"
            f" test_bottom_line_receipt_matches_the_closeout, which ran."
        )

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
