"""One line per vulnerability in a `pip-audit --format json` report.

Used by .github/workflows/dependency-audit.yml to name each package, advisory
and fix version in the issue a red scheduled audit files (#702).

Usage: python scripts/summarize_pip_audit.py <report.json>
"""

import json
import sys
from pathlib import Path
from typing import Any


def _advisory(vuln: dict[str, Any]) -> str:
    cves = [alias for alias in vuln.get("aliases", []) if alias.startswith("CVE-")]
    if not cves or vuln["id"] in cves:
        return str(vuln["id"])
    return f"{', '.join(cves)} ({vuln['id']})"


def summarize(report: Path) -> list[str]:
    data = json.loads(report.read_text(encoding="utf-8"))
    lines: list[str] = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            fixes = vuln.get("fix_versions") or []
            fix = f"fixed in {', '.join(fixes)}" if fixes else "no fixed version published"
            lines.append(f"{dep['name']} {dep['version']}: {_advisory(vuln)}, {fix}")
    return lines


if __name__ == "__main__":
    print("\n".join(summarize(Path(sys.argv[1]))))
