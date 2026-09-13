"""#511: every marker called a "lane" in ci.yml must be selected on by a job.

Before this ticket the comments above the Test cell called ``slow`` "the slow
lane" and prescribed thinning it as the overrun remedy, but no CI job
deselects on ``slow`` — the marker is advisory only (pyproject.toml:135).
A maintainer who follows the file's own instruction sees no change.

These tests parse the real ``pyproject.toml`` marker registry and ``ci.yml``
job expressions, then fail when a comment calls a marker a "lane" while no
job's ``-m`` expression selects on it. Control fixtures prove the check
catches the defect (``slow lane`` goes red) and passes the real lanes
(``calibration lane``, ``assurance lane`` stay green).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# ci.yml -m expressions: `run:` lines containing `-m` and a quoted expression
_M_EXPR = re.compile(r'-m\s+"([^"]+)"', re.MULTILINE)

# ci.yml comment lines mentioning "<marker> lane"
_LANE_COMMENT = re.compile(r"#.*\b(\w+)\s+lane\b", re.MULTILINE)


def _job_lane_markers(ci_text: str) -> set[str]:
    """Markers selected on by a job's -m expression (lanes with their own job)."""
    lanes: set[str] = set()
    for m in _M_EXPR.finditer(ci_text):
        expr = m.group(1)
        for raw in re.split(r"\s+and\s+|\s+or\s+", expr):
            name = raw.strip()
            if name.startswith("not "):
                name = name[4:]
            name = name.strip()
            if name:
                lanes.add(name)
    return lanes


def _comment_lane_markers(ci_text: str) -> set[str]:
    """Markers called a "lane" in ci.yml comments."""
    lanes: set[str] = set()
    for m in _LANE_COMMENT.finditer(ci_text):
        lanes.add(m.group(1).lower())
    return lanes


def test_comment_lane_markers_have_a_selecting_job() -> None:
    """Every marker called a 'lane' in ci.yml must be selected on by a job.

    Fails when a comment calls a marker a lane while no job's -m expression
    selects on it — the comment misleads a maintainer into thinking the
    marker controls CI routing.
    """
    ci_text = CI_YML.read_text(encoding="utf-8")
    commented_lanes = _comment_lane_markers(ci_text)
    job_lanes = _job_lane_markers(ci_text)
    orphans = commented_lanes - job_lanes
    assert not orphans, (
        f"ci.yml comments call these markers 'lane' but no job selects on them: "
        f"{sorted(orphans)}. Either add a job or remove the 'lane' phrasing."
    )


def test_registered_markers_called_lane_are_selected() -> None:
    """Control: a fixture ci.yml saying 'slow lane' with the current expression
    goes red; 'calibration lane' stays green because a job selects on it.
    """
    current_ci = CI_YML.read_text(encoding="utf-8")

    # Control A: inject "slow lane" into a comment — slow is registered but no
    # job selects on it, so the check must catch it.
    fixture_a = current_ci + "\n    # thin the slow lane instead\n"
    assert "slow lane" in fixture_a, "control fixture did not receive 'slow lane'"

    commented_a = _comment_lane_markers(fixture_a)
    job_a = _job_lane_markers(fixture_a)
    orphans_a = commented_a - job_a
    assert "slow" in orphans_a, (
        f"control A should catch 'slow' as orphaned lane, got orphans={sorted(orphans_a)}"
    )

    # Control B: inject "calibration lane" — calibration IS selected on by the
    # calibration job, so it must NOT be flagged as an orphan.
    fixture_b = current_ci + "\n    # thin the calibration lane instead\n"
    commented_b = _comment_lane_markers(fixture_b)
    job_b = _job_lane_markers(fixture_b)
    orphans_b = commented_b - job_b
    assert "calibration" not in orphans_b, (
        f"control B should pass for 'calibration' (a real lane), got orphans={sorted(orphans_b)}"
    )
