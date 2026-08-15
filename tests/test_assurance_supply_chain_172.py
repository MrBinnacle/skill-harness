"""External contract checks for the issue #172 supply-chain configuration."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_pip_audit_as_a_failing_gate_on_current_dependencies() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")

    assert "pip-audit==" in requirements
    assert "dependency-audit:" in ci
    audit_job = ci.split("  dependency-audit:\n", 1)[1].split("\n  # NON-required", 1)[0]
    assert "python -m pip_audit" in audit_job
    assert "continue-on-error" not in audit_job


def test_scorecard_workflow_publishes_sarif_with_minimal_permissions() -> None:
    workflow = ROOT / ".github/workflows/scorecard.yml"

    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "ossf/scorecard-action@" in text
    assert "github/codeql-action/upload-sarif@" in text
    assert "security-events: write" in text
    assert "id-token: write" in text
    assert "publish_results: true" in text
    for ref in re.findall(r"uses:\s*[^\s@]+@([^\s#]+)", text):
        assert re.fullmatch(r"[0-9a-f]{40}", ref), ref
