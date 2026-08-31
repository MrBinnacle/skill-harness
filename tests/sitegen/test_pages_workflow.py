"""The Pages workflow, and the CI job names it must not disturb (#186).

Two acceptance criteria live in workflow files rather than in code, so they are
pinned here:

- a deploy is not evidence of a publish: the workflow must fetch the published
  URL and check it for this build's own marker;
- no existing CI job may be renamed, and a job joins the required-check set only
  through a deliberate, coordinated edit here, because branch protection matches
  on those names.

Parsed by string, deliberately: pyyaml is not a declared dependency of this
project (see ``tests/test_structural_bans.py`` for the same reasoning), and the
question here is what the file says.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_PAGES = _REPO_ROOT / ".github" / "workflows" / "pages.yml"

# Frozen: these are the names branch protection selects on. A rename here is a
# silently-unprotected branch, so it must break a test rather than a merge.
#
# The list is the full ci.yml inventory in file order, not just the required
# names, so ADDING a job is also a deliberate edit here. `dependency-audit`
# (#172) is additive: it is listed here and deliberately absent from
# _REQUIRED_JOB_IDS below, which is what keeps it out of `all-green`.
_CI_JOB_IDS = (
    "lint",
    "typecheck",
    "test",
    "calibration",
    "structural-bans",
    "drift-check",
    "release-gate",
    "dependency-audit",
    "linkcheck",
    "vale",
    "all-green",
)
_REQUIRED_JOB_IDS = (
    "lint",
    "typecheck",
    "test",
    "calibration",
    "structural-bans",
    "drift-check",
    "release-gate",
    "vale",
)


def _job_ids(workflow: Path) -> list[str]:
    lines = workflow.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.rstrip() == "jobs:")
    ids: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        match = re.match(r"^ {2}([a-z][a-z0-9-]*):\s*$", line)
        if match is not None:
            ids.append(match.group(1))
    return ids


def _linkcheck_job() -> str:
    """The ``linkcheck`` job's text, from its id to the next job at the same indent."""
    lines = _CI.read_text(encoding="utf-8").splitlines()
    first = next(index for index, line in enumerate(lines) if line == "  linkcheck:")
    body: list[str] = []
    for line in lines[first + 1 :]:
        if re.match(r"^ {2}([a-z][a-z0-9-]*):\s*$", line) is not None:
            break
        body.append(line)
    assert body, "ci.yml declares an empty linkcheck job"
    return "\n".join(body)


def _all_green_needs() -> list[str]:
    text = _CI.read_text(encoding="utf-8")
    match = re.search(r"^  all-green:\n(?:.*\n)*?    needs: \[([^\]]+)\]", text, re.MULTILINE)
    assert match is not None, "ci.yml all-green job has no needs list"
    return [name.strip() for name in match.group(1).split(",")]


def test_pages_workflow_exists_and_builds_via_the_generator() -> None:
    text = _PAGES.read_text(encoding="utf-8")
    assert "python -m skill_harness.sitegen" in text
    assert "--marker" in text
    # No toolchain beyond the generator: no node, no bundler, no site framework.
    for foreign in ("npm ", "yarn ", "npx ", "jekyll", "hugo", "mkdocs"):
        assert foreign not in text, foreign


def test_deploy_is_verified_against_the_published_url() -> None:
    """A green deploy step is not proof the site updated; the URL is fetched."""
    text = _PAGES.read_text(encoding="utf-8")
    assert "steps.deployment.outputs.page_url" in text
    assert "needs.build.outputs.marker" in text
    verify = text.split("Verify the published URL serves this build", 1)
    assert len(verify) == 2, "pages.yml has no published-URL verification step"
    script = verify[1]
    assert "curl" in script
    assert 'grep -qF "${MARKER}"' in script
    assert "exit 1" in script


def test_pages_workflow_renames_no_existing_ci_job() -> None:
    assert _job_ids(_CI) == list(_CI_JOB_IDS)


def _all_green_checked_results() -> list[str]:
    """The job results the all-green STEP actually tests, read from its script.

    ``_all_green_needs`` reads the dependency list; this reads the condition that
    consumes it. They are two hand-maintained lists of the same thing.
    """
    text = _CI.read_text(encoding="utf-8")
    match = re.search(
        r"^  all-green:\n(?:.*\n)*?          echo \"All checks passed", text, re.MULTILINE
    )
    assert match is not None, "ci.yml all-green job has no verification step"
    return sorted(set(re.findall(r"needs\.([a-z-]+)\.result", match.group(0))))


def test_all_green_checks_exactly_the_jobs_it_depends_on() -> None:
    """The needs list and the condition that reads it cannot drift apart.

    They did. `vale` was removed from `needs:` and left in the condition. A result
    for a job that is not a dependency is the EMPTY STRING, so
    ``[[ "" != "success" ]]`` is always true and all-green failed on every run,
    including runs where all twenty real checks passed. The failure names no job,
    so it reads as an infrastructure flake rather than as a one-line edit.

    The inverse is worse and this test catches it too: a job added to ``needs``
    but never tested in the condition is a required check that can fail while
    all-green stays green.
    """
    assert _all_green_checked_results() == sorted(_all_green_needs())


def test_pages_jobs_are_not_required_checks() -> None:
    assert _all_green_needs() == list(_REQUIRED_JOB_IDS)
    pages_jobs = set(_job_ids(_PAGES))
    assert pages_jobs, "pages.yml declares no jobs"
    assert pages_jobs.isdisjoint(_all_green_needs())
    assert pages_jobs.isdisjoint(_CI_JOB_IDS)


def test_linkcheck_covers_the_generated_site() -> None:
    """#288: the link checker reads the built site, not only the hand-written prose.

    #184 shipped the checker over ``README.md`` and ``docs/**/*.md``. Spec #181
    had named three surfaces. The third went missing without breaking anything,
    which is why it is pinned here: dropping it again fails a test rather than
    quietly narrowing coverage.
    """
    job = _linkcheck_job()
    assert "python -m skill_harness.sitegen" in job, "linkcheck does not build the site"
    assert "--output site" in job
    assert '"site/**/*.html"' in job, "the built site is not passed to the link checker"
    # The two original surfaces are additions to, not replacements of, each other.
    assert "README.md" in job
    assert '"docs/**/*.md"' in job
    assert "fail: true" in job


def test_linkcheck_stays_outside_the_required_check_set() -> None:
    """#288 widened the job's coverage; it must not widen what blocks a merge."""
    assert "linkcheck" not in _all_green_needs()
