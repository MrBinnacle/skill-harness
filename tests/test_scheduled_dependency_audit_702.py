"""Contract checks for the scheduled dependency audit (issue #702).

The `dependency-audit` job in ci.yml runs only when a commit or a pull request
arrives, so an advisory published against an unchanged dependency stays unseen
until someone happens to open a pull request. The weekly workflow closes that gap.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/dependency-audit.yml"
CI = ROOT / ".github/workflows/ci.yml"
INSTALL = 'python -m pip install -c requirements-ci.txt -e ".[dev]" pip-audit'
AUDIT = "python -m pip_audit --local"


def _summary_module() -> ModuleType:
    path = ROOT / "scripts/summarize_pip_audit.py"
    spec = importlib.util.spec_from_file_location("summarize_pip_audit", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _triggers(text: str) -> str:
    return text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]


def test_runs_weekly_and_on_dispatch_only() -> None:
    triggers = _triggers(WORKFLOW.read_text(encoding="utf-8"))

    assert "schedule:" in triggers
    assert "- cron: " in triggers
    assert "workflow_dispatch:" in triggers
    # Advisory: no push or pull_request trigger, so it can never sit on the merge path.
    assert "push:" not in triggers
    assert "pull_request" not in triggers


def test_audits_the_environment_ci_audits() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    ci = CI.read_text(encoding="utf-8")

    for command in (INSTALL, AUDIT):
        assert command in ci, f"ci.yml no longer runs {command!r}; update #702's copy too"
        assert command in workflow, command


def test_a_red_audit_opens_or_updates_one_issue() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    report = workflow.split("\n  report-failure:\n", 1)

    assert len(report) == 2, "no report-failure job"
    job = report[1]
    assert "if: failure()" in job
    assert "issues: write" in job
    assert "gh issue comment" in job
    assert "gh issue create" in job
    assert "scripts/summarize_pip_audit.py" in workflow


def test_summary_names_package_cve_and_fix_version(tmp_path: Path) -> None:
    report = tmp_path / "audit.json"
    report.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "pytest", "version": "8.3.0", "vulns": []},
                    {
                        "name": "urllib3",
                        "version": "2.2.1",
                        "vulns": [
                            {
                                "id": "GHSA-34jh-p97f-mpxf",
                                "fix_versions": ["2.2.2"],
                                "aliases": ["CVE-2024-37891"],
                            },
                            {"id": "PYSEC-2099-1", "fix_versions": [], "aliases": []},
                        ],
                    },
                    {"name": "local-pkg", "skip_reason": "not on PyPI"},
                ],
                "fixes": [],
            }
        ),
        encoding="utf-8",
    )

    lines = _summary_module().summarize(report)

    assert lines == [
        "urllib3 2.2.1: CVE-2024-37891 (GHSA-34jh-p97f-mpxf), fixed in 2.2.2",
        "urllib3 2.2.1: PYSEC-2099-1, no fixed version published",
    ]


def test_summary_of_a_clean_report_is_empty(tmp_path: Path) -> None:
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({"dependencies": [], "fixes": []}), encoding="utf-8")

    assert _summary_module().summarize(report) == []
