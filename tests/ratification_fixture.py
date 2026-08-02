"""Shared test fixture: a RATIFIED row-pick record + matching --execute args.

The #57 mechanical preflight gate refuses every ``run ablation --execute``
invocation that does not reference a RATIFIED record whose cap and scope
match the run. Tests whose concern is downstream of the gate (exit codes,
rendering, resume, budget errors) use this helper to pass it honestly —
through the real parser and gate, never by patching the gate away.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

TEST_TASK_FAMILY = "test-task-family"
TEST_ESTIMAND = "treatment-policy"

_RECORD_TEMPLATE = """---
rat: RAT-0001
status: RATIFIED
skill_id: {skill_id}
task_family: {task_family}
estimand: {estimand}
gate: gate2
n: 20
worst_case_cost_usd: {cap}
hard_cap_usd: {cap}
cost_provenance: project_pair_usd
sme_status: deliberated
ratified_date: "2026-08-02"
---

# RAT-0001 - {skill_id} row-pick (shared test fixture)
"""

# TemporaryDirectory objects are held here so the records live for the whole
# test session; the OS reclaims them afterwards.
_DIRS: dict[tuple[str, int], tempfile.TemporaryDirectory[str]] = {}


def ratified_exec_args(skill_id: str = "skill-abc", max_usd: float = 5.0) -> list[str]:
    """Return ``--execute`` plus gate-satisfying ratification/scope/cap args."""
    key = (skill_id, round(max_usd * 100))
    if key not in _DIRS:
        tmp = tempfile.TemporaryDirectory(prefix="rat-fixture-")
        record = Path(tmp.name) / f"RAT-0001-{skill_id}.md"
        record.write_text(
            _RECORD_TEMPLATE.format(
                skill_id=skill_id,
                task_family=TEST_TASK_FAMILY,
                estimand=TEST_ESTIMAND,
                cap=f"{max_usd:.2f}",
            ),
            encoding="utf-8",
        )
        _DIRS[key] = tmp
    record_path = Path(_DIRS[key].name) / f"RAT-0001-{skill_id}.md"
    return [
        "--execute",
        "--ratification",
        str(record_path),
        "--task-family",
        TEST_TASK_FAMILY,
        "--estimand",
        TEST_ESTIMAND,
        "--max-usd",
        f"{max_usd:.2f}",
    ]
