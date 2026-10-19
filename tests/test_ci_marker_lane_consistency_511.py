"""#511: every marker called a "lane" in ci.yml must be selected on by a job.

Before this ticket the comments above the Test cell called ``slow`` "the slow
lane" and prescribed thinning it as the overrun remedy, but no CI job
selects or deselects on ``slow`` — the marker is advisory only
(pyproject.toml). A maintainer who follows the file's own instruction sees
no change.

S442 kept ``slow`` advisory and required a check: parse the marker registry
and ``ci.yml``, fail when any ``ci.yml`` comment calls a registered marker a
"lane" while no job's ``-m`` expression selects on it. Controls: a fixture
saying ``slow lane`` goes red; ``calibration lane`` and ``assurance lane``
stay green because jobs select on them.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ASSURANCE_YML = REPO_ROOT / ".github" / "workflows" / "assurance.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# pytest -m expressions on run lines (quoted or bare marker name).
# Require a leading "pytest" so "python -m pip" does not match.
_M_EXPR = re.compile(
    r"pytest\b[^\n]*?-m\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))",
    re.MULTILINE,
)

# ci.yml comment lines mentioning "<word> lane"
_LANE_COMMENT = re.compile(r"#.*\b(\w+)\s+lane\b", re.MULTILINE)

# "name: description" entries under [tool.pytest.ini_options].markers
_MARKER_ENTRY = re.compile(r'^["\']?(\w+)\s*:')


def _registered_markers() -> set[str]:
    """Marker names declared in pyproject.toml's pytest marker registry."""
    with PYPROJECT.open("rb") as fh:
        options = tomllib.load(fh)["tool"]["pytest"]["ini_options"]
    raw = options.get("markers", [])
    names: set[str] = set()
    for entry in raw:
        match = _MARKER_ENTRY.match(str(entry).strip())
        if match:
            names.add(match.group(1))
    return names


def _job_selected_markers(*workflow_texts: str) -> set[str]:
    """Markers a job's -m expression positively selects on (not deselected)."""
    selected: set[str] = set()
    for text in workflow_texts:
        for m in _M_EXPR.finditer(text):
            expr = next(g for g in m.groups() if g is not None)
            for raw in re.split(r"\s+and\s+|\s+or\s+", expr):
                name = raw.strip()
                if not name or name.startswith("not "):
                    continue
                selected.add(name)
    return selected


def _comment_lane_markers(ci_text: str, registered: set[str]) -> set[str]:
    """Registered markers called a "lane" in ci.yml comments."""
    found: set[str] = set()
    for m in _LANE_COMMENT.finditer(ci_text):
        name = m.group(1).lower()
        if name in registered:
            found.add(name)
    return found


def _workflow_bundle() -> tuple[str, str, set[str]]:
    ci_text = CI_YML.read_text(encoding="utf-8")
    assurance_text = ASSURANCE_YML.read_text(encoding="utf-8")
    return ci_text, assurance_text, _registered_markers()


def test_comment_lane_markers_have_a_selecting_job() -> None:
    """Every registered marker called a 'lane' in ci.yml must have a selecting job.

    Fails when a comment calls a marker a lane while no job's -m expression
    positively selects on it — the comment misleads a maintainer into thinking
    the marker controls CI routing.
    """
    ci_text, assurance_text, registered = _workflow_bundle()
    assert "slow" in registered, "slow must remain registered as an advisory marker"
    commented = _comment_lane_markers(ci_text, registered)
    selected = _job_selected_markers(ci_text, assurance_text)
    orphans = commented - selected
    assert not orphans, (
        f"ci.yml comments call these markers 'lane' but no job selects on them: "
        f"{sorted(orphans)}. Either add a job or remove the 'lane' phrasing."
    )


def test_registered_markers_called_lane_are_selected() -> None:
    """Controls: 'slow lane' goes red; calibration and assurance lanes stay green."""
    ci_text, assurance_text, registered = _workflow_bundle()
    selected = _job_selected_markers(ci_text, assurance_text)
    assert "calibration" in selected, "calibration job must select on -m calibration"
    assert "assurance" in selected, "assurance job must select on -m assurance"
    assert "slow" not in selected, "no job may select on slow (advisory only)"

    fixture_slow = ci_text + "\n    # thin the slow lane instead\n"
    orphans_slow = _comment_lane_markers(fixture_slow, registered) - selected
    assert "slow" in orphans_slow, (
        f"control A should catch 'slow' as orphaned lane, got orphans={sorted(orphans_slow)}"
    )

    fixture_cal = ci_text + "\n    # thin the calibration lane instead\n"
    orphans_cal = _comment_lane_markers(fixture_cal, registered) - selected
    assert "calibration" not in orphans_cal, (
        f"control B should pass for 'calibration', got orphans={sorted(orphans_cal)}"
    )

    fixture_as = ci_text + "\n    # the assurance lane runs on a schedule\n"
    orphans_as = _comment_lane_markers(fixture_as, registered) - selected
    assert "assurance" not in orphans_as, (
        f"control C should pass for 'assurance', got orphans={sorted(orphans_as)}"
    )
