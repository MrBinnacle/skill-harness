"""External contract checks for the issue #172 supply-chain configuration."""

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
