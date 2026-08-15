"""External contract checks for the issue #172 supply-chain configuration."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_COMMAND = "python -m pip_audit --local"
WORKFLOW_DIR = ROOT / ".github/workflows"

_USES_RE = re.compile(r"(?m)^\s*-?\s*uses:\s*(\S+)")
_SHA_PINNED_RE = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")
_WRITE_SCOPE_RE = re.compile(r"(?m)^\s+([a-z-]+):\s*write\s*(?:#.*)?$")


def _workflows() -> list[Path]:
    """Every workflow file GitHub would run, `.yaml` included.

    Globbing `*.yml` alone would let a `.yaml` workflow escape both the audit's
    coverage claim and the pinning and permission checks below.
    """
    return sorted(path for path in WORKFLOW_DIR.glob("*.y*ml") if path.suffix in {".yml", ".yaml"})


def _unpinned_uses(text: str) -> list[str]:
    """`uses:` references that are not `owner/repo[/path]@<40-hex commit sha>`.

    Every `uses:` value is inspected, not only those that already contain an
    `@`: `uses: docker://image:tag` and an in-repo composite action carry no
    `@ref` at all, so a pattern that requires one reports the references it
    cannot see as pinned. A reference that is legitimately unpinnable is a
    finding for the audit document to record, not one for this test to skip.
    """
    return [ref for ref in _USES_RE.findall(text) if not _SHA_PINNED_RE.fullmatch(ref)]


def _workflow_level_permissions(text: str) -> str:
    """The workflow-level `permissions:` value: inline scalar or indented block.

    Column-0 only. `"permissions:" in text` is satisfied by a job-level block,
    by a comment, and by `permissions: write-all`, none of which is the
    least-privilege baseline the audit document claims for every workflow.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("permissions:"):
            continue
        inline = line.split(":", 1)[1].strip()
        if inline:
            return inline
        block: list[str] = []
        for following in lines[index + 1 :]:
            if following.strip() and not following.startswith((" ", "\t")):
                break
            block.append(following)
        return "\n".join(block).strip()
    return ""


def _dependency_audit_job() -> str:
    """The `dependency-audit` job body from ci.yml, by string (no pyyaml dep).

    Bounded by the next line indented exactly two spaces - the following job key
    or the comment introducing it - rather than by one particular neighbouring
    comment, so rewording an unrelated comment cannot silently widen this slice
    to the rest of the file and make the checks below vacuous.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    parts = ci.split("\n  dependency-audit:\n", 1)
    assert len(parts) == 2, "ci.yml declares no dependency-audit job"
    return re.split(r"(?m)^  \S", parts[1], maxsplit=1)[0]


def _exit_cell(row: str) -> str:
    """Last cell of a Markdown table row, stripped of emphasis markers."""
    return [cell.strip().strip("*").strip() for cell in row.strip().strip("|").split("|")][-1]


def test_ci_runs_pip_audit_as_a_job_that_can_fail() -> None:
    requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
    audit_job = _dependency_audit_job()

    assert re.search(r"(?mi)^pip-audit==", requirements)
    assert AUDIT_COMMAND in audit_job
    assert "continue-on-error" not in audit_job


def test_pip_audit_fail_ability_is_demonstrated_not_asserted() -> None:
    """#172 makes the demonstration a deliverable: a scanner that cannot fail is
    indistinguishable from one that found nothing.

    So the receipt must record a run of the SAME command CI runs that exited
    non-zero *because of a finding* - a non-zero exit alone can come from the
    scanner crashing on its way to the advisory lookup - plus a zero-exit run on
    the current dependency set, and it must name the pip-audit version CI pins,
    so bumping that pin without re-running the demonstration fails here.
    """
    receipt = (ROOT / "docs/assurance/dependency-audit.md").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")

    pin = re.search(r"(?mi)^pip-audit==([^\s;#]+)", requirements)
    assert pin is not None, "requirements-ci.txt does not pin pip-audit"
    version = pin.group(1)
    assert f"pip-audit {version}" in receipt, f"receipt does not state pip-audit {version}"

    assert AUDIT_COMMAND in receipt, "the demonstration is not of the command CI runs"

    exit_rows = [
        row
        for row in receipt.splitlines()
        if row.startswith("|") and re.fullmatch(r"[0-9]+", _exit_cell(row))
    ]
    exits = {int(_exit_cell(row)): row for row in exit_rows}
    assert 0 in exits, "no zero-exit run recorded for the current dependency set"

    from_finding = [
        row
        for code, row in exits.items()
        if code != 0 and "vulnerabilit" in row.lower() and re.search(r"[\w.-]+==[0-9]", row)
    ]
    assert from_finding, (
        "no non-zero-exit run recorded whose result was a vulnerability finding "
        "against a named installed pin - 'exit 1' on its own is not the deliverable"
    )
    assert re.search(r"\b(?:PYSEC|GHSA|CVE)-[0-9A-Za-z-]+\b", receipt), (
        "the demonstrated finding carries no advisory identifier"
    )


def test_scorecard_workflow_publishes_sarif_with_minimal_permissions() -> None:
    workflow = WORKFLOW_DIR / "scorecard.yml"

    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "ossf/scorecard-action@" in text
    assert "github/codeql-action/upload-sarif@" in text
    assert "publish_results: true" in text
    assert not _unpinned_uses(text), _unpinned_uses(text)

    # Minimal, not merely sufficient: exactly the two grants SARIF upload and
    # result publication consume, and nothing else anywhere in the file.
    assert set(_WRITE_SCOPE_RE.findall(text)) == {"security-events", "id-token"}


def test_workflow_audit_covers_every_workflow_and_records_required_checks() -> None:
    audit_path = ROOT / "docs/assurance/workflows-audit.md"

    assert audit_path.is_file()
    audit = audit_path.read_text(encoding="utf-8")
    workflows = _workflows()
    assert len(workflows) >= 6, workflows
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        assert f"`.github/workflows/{workflow.name}`" in audit, workflow.name
        assert "pull_request_target" not in text, workflow.name
        assert not _unpinned_uses(text), f"{workflow.name}: {_unpinned_uses(text)}"

        permissions = _workflow_level_permissions(text)
        assert permissions, f"{workflow.name}: no workflow-level permissions block"
        assert "write" not in permissions, (
            f"{workflow.name}: workflow-level write grant {permissions!r} - the audit "
            "claims write access exists only on the job that consumes it"
        )

    assert "No existing job was renamed" in audit
    assert "No branch-protection setting was changed" in audit
