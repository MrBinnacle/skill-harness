"""Release gate — public-surface lockstep checks that block a stale release.

Why this exists: v0.2.1 (the first PyPI release, 2026-07-26) was tagged while
known-stale surfaces existed — the shipped wheel carried
``__version__ = "0.2.0"``, the README led with a v0.2.0 status banner and a
pip-from-git install path, and CHANGELOG ``[Unreleased]`` was never rolled.
The process failure was not any one literal: it was that NOTHING enforced
version/claims lockstep at tag time. This script is that enforcement.

Where it runs (blocked-by-default, not impossible — a maintainer can still
edit the workflows, and this script cannot see surfaces outside the repo,
e.g. an already-frozen PyPI description):

- ``ci.yml`` on every push/PR (early feedback; tag check self-skips).
- ``release-authorize.yml``, dispatched on the release tag after the
  assurance and CI runs at the candidate have completed and before the
  GitHub Release exists. This is the authorization run (#835).
- ``publish.yml`` as the first job of the release pipeline: the build and
  PyPI upload jobs depend on it, so a release of a stale tree fails before
  an artifact exists. It runs after the release is published, so it is a
  downstream defense, not the authorization.

Checks (all must pass; failures are listed, not first-fail):

  G1  pyproject.toml version == skill_harness.__init__.__version__, and
      every ``harness_version`` in tests/fixtures/sers/*.json names it too.
  G2  CHANGELOG.md has a rolled ``## [X.Y.Z] - `` section for the current
      version (an entry under [Unreleased] alone does not count) and a
      ``[X.Y.Z]:`` compare-link reference.
  G3  README.md status banner names the version this tree declares
      (Status: vX.Y.Z). Scope is repository-internal by design: both halves
      of the comparison live in this tree and move together, so G3 cannot
      observe the published package and is not evidence that PyPI serves
      this version. Reading the published index here would also measure the
      wrong thing: in publish.yml the gate runs before the build and upload
      jobs, so the index still serves the previous release at the moment G3
      runs. The published surface is guarded by G6 (the tag matches the
      tree) and by the publish pipeline's own ordering.
  G4  README.md is PyPI-render-safe: no relative Markdown link targets and
      no relative ``src=``/``srcset=`` attributes (PyPI renders the README
      verbatim as the project description; relative targets 404 there).
  G5  Every ``uses:`` in .github/workflows/ is pinned to a full 40-hex
      commit SHA (mutable tag/branch refs are not provenance).
  G6  When running on a tag ref (GITHUB_REF_NAME=vX.Y.Z), the tag matches
      the pyproject version exactly.
  G7  The version's minor line must have a declared row in
      ``ASSURANCE_REQUIREMENTS``. A declared row's issue list must all be
      closed on GitHub. An empty declared list passes by declaration. A
      missing row is NOT RUN and blocks (#735).
  G8  The version's minor line must have a declared row, and that row must
      either require a green assurance run or declare that it does not. When
      required, a tag ref must carry a successful ``assurance.yml`` run at
      ``GITHUB_SHA`` itself; off a tag ref G8 self-skips (no release
      candidate). A missing row is NOT RUN and blocks (#735). The newest
      assurance run at the SHA decides; an older success never masks a newer
      failure, cancellation or run in flight (#835).
  G9  From the 0.5 line on (#835): on a tag ref, the newest ``ci.yml`` run
      at ``GITHUB_SHA`` is completed and carries every job in
      ``REQUIRED_CI_JOBS`` exactly once, successful. Off a tag ref G9
      self-skips. Earlier lines pass it as not applicable.

From the 0.5 line on, G7 refuses an empty issue list and G8 refuses
``g8_required=False`` (#835). Lines 0.3 and 0.4 keep their released policy.

G7, G8 and G9 read the GitHub REST API and fail CLOSED: an unreadable API blocks
the release rather than passing it. ``RELEASE_GATE_GITHUB_API_URL`` names the
repository API base (default ``https://api.github.com/repos/MrBinnacle/skill-harness``)
so tests can seed both answers from a local server instead of the network.

The gated version always comes from the tree under ``--root``: there is no
version override, because a version the tree does not declare is the exact
drift this script exists to catch.

Run locally: ``python scripts/release_gate.py [--root <repo-root>]``.
Exit code 1 = at least one surface is stale (each listed). Exit code 0 prints
one of two verdicts. ``RELEASE GATE: AUTHORIZED`` appears only on a tag ref
with all nine gates run and passed. ``RELEASE GATE: PRELIMINARY`` is every
other clean run and is not release authorization (#835).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent
GITHUB_API_DEFAULT = "https://api.github.com/repos/MrBinnacle/skill-harness"


class AssuranceRequirement(NamedTuple):
    """One minor line's declared assurance requirement (#735).

    ``issues`` is the list G7 requires closed. It may be empty only when the
    row says so explicitly, in which case G7 passes by declaration.
    ``g8_required`` is whether G8 requires a green ``assurance.yml`` run at
    the release candidate's own commit. False passes G8 by declaration.
    """

    issues: tuple[int, ...]
    g8_required: bool


ASSURANCE_REQUIREMENTS: dict[str, AssuranceRequirement] = {
    "0.3": AssuranceRequirement(issues=tuple(range(167, 175)), g8_required=True),
    # Decided on #742 (2026-10-22). An issue is in this row when its open state
    # means a published claim surface carries a claim the tree cannot support,
    # or a control guarding one passes for the wrong reason. #691 and #764 are
    # closed and listed as the Stage 1A chain record. Membership and the
    # exclusions are argued on #742; change the row there first.
    "0.4": AssuranceRequirement(
        issues=(570, 732, 736, 691, 764, 797, 792, 793, 794, 795, 796),
        g8_required=True,
    ),
    # Later lines are declared here when their assurance phase is decided.
    # Absence of a row fails closed: G7 and G8 each report NOT RUN and the
    # gate blocks. Declaring a row is how a line becomes releasable. From
    # STRICT_ASSURANCE_FROM on, a row must name at least one issue and must
    # require the assurance run (#835).
}
"""Declared assurance requirements keyed by minor line (``"MAJOR.MINOR"``).

The table is a tree property: it lives in this repo, so an undeclared line
fails on every ref, including ordinary CI. That is intended — a version bump
to a line with no declared requirement cannot merge.
"""

STRICT_ASSURANCE_FROM = (0, 5)
"""The first minor line on which the assurance policy is strict (#835).

From this line on, an empty G7 issue list and ``g8_required=False`` are
failures, not declarations, and G9 reads the candidate's CI evidence. Lines
0.3 and 0.4 keep the behavior they were released under.
"""

ASSURANCE_WORKFLOW = ".github/workflows/assurance.yml"
CI_WORKFLOW = ".github/workflows/ci.yml"

_DOT = chr(0xB7)  # ci.yml separates matrix values with a middle dot; source stays ASCII.
REQUIRED_CI_JOBS: tuple[str, ...] = (
    "Drift check (locked contracts)",
    "Structural bans (raw sqlite3.connect / oracle_verdicts / timestamp ORDER BY)",
    f"Calibration CS grid (ubuntu-latest {_DOT} py3.12)",
    f"Calibration CS grid (ubuntu-latest {_DOT} py3.13)",
    f"Calibration CS grid (windows-latest {_DOT} py3.12)",
    f"Calibration CS grid (windows-latest {_DOT} py3.13)",
    "Dependency audit (pip-audit)",
)
"""The ci.yml jobs G9 requires green at the candidate, by exact name (#835).

Branch protection does not require these, so G9 does. Every calibration
matrix cell is named. tests/test_release_gate_real_tree.py checks this tuple
against ci.yml, so a renamed job fails the suite instead of the release.
"""


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _api_base() -> str:
    return os.environ.get("RELEASE_GATE_GITHUB_API_URL", GITHUB_API_DEFAULT).rstrip("/")


def gate_versions_lockstep(root: Path, errors: list[str]) -> str:
    """G1: pyproject, package __version__ and SERS fixtures agree; returns the version."""
    pyproject = tomllib.loads(_read(root, "pyproject.toml"))
    version: str = pyproject["project"]["version"]

    init_text = _read(root, "src/skill_harness/__init__.py")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    if m is None:
        errors.append("G1: no __version__ in src/skill_harness/__init__.py")
    elif m.group(1) != version:
        errors.append(
            f"G1: version drift — pyproject.toml={version!r} but "
            f"src/skill_harness/__init__.py __version__={m.group(1)!r} "
            "(this exact drift shipped in the v0.2.1 wheel)"
        )
    _sers_fixture_lockstep(root, version, errors)
    return version


SERS_FIXTURES = "tests/fixtures/sers"
_HARNESS_VERSION_RE = re.compile(r'"harness_version"\s*:\s*"([^"]*)"')


def _sers_fixture_lockstep(root: Path, version: str, errors: list[str]) -> None:
    """G1, second half: every stored SERS fixture names the declared version.

    A receipt that must keep the version that minted it belongs in
    docs/sers/receipts/, which this check does not read.
    """
    for path in sorted((root / SERS_FIXTURES).glob("*.json")):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for found in _HARNESS_VERSION_RE.findall(line):
                if found != version:
                    errors.append(
                        f"G1: SERS fixture drift - pyproject.toml={version!r} but "
                        f"{rel}:{lineno} harness_version={found!r} "
                        "(tests/test_sers_conformance.py compares it with a live mint; "
                        "releases 0.3.0 and 0.4.0 both went red on it in CI)"
                    )


def gate_changelog_rolled(root: Path, version: str, errors: list[str]) -> None:
    """G2: CHANGELOG has a rolled section + compare link for this version."""
    changelog = _read(root, "CHANGELOG.md")
    section = re.compile(
        rf"^## \[{re.escape(version)}\] [-—] \d{{4}}-\d{{2}}-\d{{2}}", re.MULTILINE
    )
    if section.search(changelog) is None:
        errors.append(
            f"G2: CHANGELOG.md has no rolled '## [{version}] - YYYY-MM-DD' section — "
            "roll [Unreleased] before tagging"
        )
    if re.search(rf"^\[{re.escape(version)}\]:\s+http", changelog, re.MULTILINE) is None:
        errors.append(
            f"G2: CHANGELOG.md is missing the '[{version}]: <compare-url>' link reference"
        )


def gate_readme_status_banner(root: Path, version: str, errors: list[str]) -> None:
    """G3: the README status banner names the version this tree declares.

    Repository-internal check. It compares README.md against pyproject.toml
    and makes no network call, so it cannot observe the published package.
    """
    readme = _read(root, "README.md")
    if f"Status: v{version}" not in readme:
        banner = re.search(r"Status: v[\d.]+[0-9a-z]*", readme)
        found = f" (found {banner.group(0)!r})" if banner else ""
        errors.append(
            f"G3: README.md status banner does not say 'Status: v{version}'{found} - "
            "repository-internal check against pyproject.toml; "
            "it cannot observe the published package"
        )


def gate_readme_pypi_render_safe(root: Path, errors: list[str]) -> None:
    """G4: README carries no relative targets (they 404 on the PyPI page)."""
    readme = _read(root, "README.md")
    for lineno, line in enumerate(readme.splitlines(), start=1):
        for m in re.finditer(r"\]\(([^)]+)\)", line):
            target = m.group(1)
            if not target.startswith(("http://", "https://", "#")):
                errors.append(
                    f"G4: README.md:{lineno} relative link target {target!r} breaks on PyPI"
                )
        for m in re.finditer(r'(?:src|srcset)="([^"]+)"', line):
            if not m.group(1).startswith(("http://", "https://")):
                errors.append(
                    f"G4: README.md:{lineno} relative image ref {m.group(1)!r} breaks on PyPI"
                )


def gate_workflows_sha_pinned(root: Path, errors: list[str]) -> None:
    """G5: every workflow action is pinned to a full commit SHA.

    The glob reads ``.yaml`` as well as ``.yml``. GitHub runs both suffixes, so
    a ``*.yml`` glob left a workflow named ``release.yaml`` unread: its actions
    were never checked and the gate printed PASS. That hole was latent rather
    than live, because this repository tracks no ``.yaml`` workflow today, which
    is the shape of a hole that survives review. The sibling copy of this rule,
    ``_workflows`` in tests/test_assurance_supply_chain_172.py, already globbed
    both suffixes, so the two copies of one rule disagreed on scope; they now
    agree. AC-4 in scripts/drift_check.py calls THIS function, so the widened
    scope reaches the drift check too.
    """
    pinned = re.compile(r"^\s*-?\s*uses:\s*\S+@[0-9a-f]{40}(\s+#.*)?$")
    workflows = (root / ".github" / "workflows").glob("*.y*ml")
    for wf in sorted(wf for wf in workflows if wf.suffix in {".yml", ".yaml"}):
        for lineno, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(r"^\s*-?\s*uses:", line) and pinned.match(line) is None:
                errors.append(
                    f"G5: {wf.name}:{lineno} action not SHA-pinned: {line.strip()!r} "
                    "(mutable refs are not provenance)"
                )


def gate_tag_matches(version: str, errors: list[str], skipped: list[str]) -> None:
    """G6: on a tag ref, the tag must be exactly v<version>."""
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    ref_type = os.environ.get("GITHUB_REF", "")
    if ref_type.startswith("refs/tags/"):
        if ref_name != f"v{version}":
            errors.append(
                f"G6: tag {ref_name!r} does not match pyproject version {version!r} "
                f"(expected 'v{version}')"
            )
    else:
        skipped.append("G6")
        print(f"G6: not a tag ref ({ref_name or 'local run'}) — tag-match check self-skips.")


TOTAL_GATES = 9
"""Gates this script declares. G1 to G9, counted in the run summary.

A gate that does not run must say so. Before #576, G7 and G8 returned in
silence off the 0.3 minor line, so ``RELEASE GATE: PASS`` covered six of eight
checks and reported itself as though it covered all eight. #735 made an
undeclared minor line an error rather than a skip: ``NOT RUN`` gates are
listed as not run in the coverage claim and each adds an error.
"""


def _record_skip(skipped: list[str], gate: str, reason: str) -> None:
    """Print a gate's self-skip and record it for the run summary.

    G6 does not use this helper. It printed its own self-skip line before #576,
    and #576 asked only that G7 and G8 stop skipping in silence. Rewording a
    line nobody complained about would churn the transcript that
    docs/assurance/release-gate-red-206.md records, so G6 keeps its wording and
    appends to the ledger directly.
    """
    skipped.append(gate)
    print(f"{gate}: SKIPPED, {reason}.")


def _minor_line(version: str) -> str:
    """The ``MAJOR.MINOR`` key the requirements table is keyed by."""
    parts = version.split(".")
    return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else version


def _get_json(url: str) -> object:
    """GET a JSON document. Raises OSError/ValueError on any failure.

    Authenticates with ``GITHUB_TOKEN`` when it is set: unauthenticated reads
    share a 60-per-hour budget per IP, which shared CI runners exhaust.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # noqa: S310 - fixed API origin or test localhost
        url, headers=headers
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return json.load(response)


def _undeclared_line_error(gate: str, line: str) -> str:
    """The NOT RUN error an undeclared minor line produces (#735)."""
    return (
        f"{gate}: NOT RUN, no assurance requirement is declared for the {line} line; "
        f"add a row to ASSURANCE_REQUIREMENTS before releasing {line}.x."
    )


def gate_assurance_issues_closed(
    version: str, errors: list[str], skipped: list[str], not_run: list[str]
) -> None:
    """G7: the declared minor line's assurance issues must all be closed.

    An undeclared line is NOT RUN and adds an error; it never skips. A row
    whose issue list is explicitly empty passes by declaration, naming the
    row. A non-empty list is read from the API and every issue must be
    closed; an unreadable issue is an error.
    """
    line = _minor_line(version)
    row = ASSURANCE_REQUIREMENTS.get(line)
    if row is None:
        not_run.append("G7")
        errors.append(_undeclared_line_error("G7", line))
        return
    if not row.issues:
        if _is_strict_line(line):
            errors.append(
                f"G7: ASSURANCE_REQUIREMENTS row {line!r} declares no assurance issues; "
                f"from {_strict_label()} on a line must name at least one (#835)"
            )
            return
        print(
            f"G7: PASSED by declaration, ASSURANCE_REQUIREMENTS row {line!r} "
            f"declares no assurance issues for the {line} line."
        )
        return
    for issue in row.issues:
        try:
            document = _get_json(f"{_api_base()}/issues/{issue}")
        except (OSError, urllib.error.HTTPError, ValueError) as exc:
            errors.append(f"G7: could not read assurance issue #{issue}: {exc}")
            continue
        state = document.get("state") if isinstance(document, dict) else None
        if state != "closed":
            errors.append(f"G7: assurance issue #{issue} is {state or 'missing a state'}")


def gate_assurance_lane_green(
    version: str, errors: list[str], skipped: list[str], not_run: list[str]
) -> None:
    """G8: a required green assurance run at the release candidate's commit.

    Off a tag ref there is no release candidate, so G8 self-skips with that
    reason and never falls back to any historical green run. On a tag ref,
    G8 reads ``GITHUB_SHA`` and queries ``actions/runs?head_sha=<sha>``; only
    a completed successful run whose workflow path is
    ``.github/workflows/assurance.yml`` at exactly that SHA counts. A missing
    ``GITHUB_SHA`` on a tag ref is an error, not a skip. An undeclared line
    is NOT RUN and adds an error. A row whose ``g8_required`` flag is
    explicitly false passes by declaration, naming the row.
    """
    line = _minor_line(version)
    row = ASSURANCE_REQUIREMENTS.get(line)
    if row is None:
        not_run.append("G8")
        errors.append(_undeclared_line_error("G8", line))
        return
    if not row.g8_required:
        if _is_strict_line(line):
            errors.append(
                f"G8: ASSURANCE_REQUIREMENTS row {line!r} declares the assurance run "
                f"unnecessary; from {_strict_label()} on every line requires it (#835)"
            )
            return
        print(
            f"G8: PASSED by declaration, ASSURANCE_REQUIREMENTS row {line!r} "
            f"does not require a green assurance run for the {line} line."
        )
        return
    ref_type = os.environ.get("GITHUB_REF", "")
    if not ref_type.startswith("refs/tags/"):
        _record_skip(skipped, "G8", "not a tag ref, no release candidate commit")
        return
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        errors.append(
            "G8: GITHUB_SHA is unset on a tag ref; the release candidate commit "
            "cannot be identified"
        )
        return
    try:
        document = _get_json(f"{_api_base()}/actions/runs?head_sha={sha}")
    except (OSError, urllib.error.HTTPError, ValueError) as exc:
        errors.append(f"G8: could not read assurance workflow runs at {sha}: {exc}")
        return
    newest = _newest_run(document, ASSURANCE_WORKFLOW, sha, "G8", errors)
    if newest is None:
        if not any(e.startswith("G8:") for e in errors):
            errors.append(
                f"G8: no successful assurance.yml workflow run at the release candidate "
                f"commit {sha}; produce one with 'gh workflow run assurance.yml "
                f"--ref v{version}'"
            )
        return
    if newest.get("status") != "completed" or newest.get("conclusion") != "success":
        errors.append(
            f"G8: the newest assurance.yml run at the release candidate commit {sha} "
            f"is {newest.get('status')}/{newest.get('conclusion')}; an earlier success "
            f"does not count. Produce a green one with 'gh workflow run assurance.yml "
            f"--ref v{version}'"
        )


def _is_strict_line(line: str) -> bool:
    """Whether ``line`` is at or after STRICT_ASSURANCE_FROM, compared as integers.

    A string compare would put "0.10" before "0.5". A line that does not parse
    as integers is treated as strict, so an odd version never loosens policy.
    """
    try:
        key = tuple(int(part) for part in line.split("."))
    except ValueError:
        return True
    return key >= STRICT_ASSURANCE_FROM


def _strict_label() -> str:
    return ".".join(str(part) for part in STRICT_ASSURANCE_FROM)


def _newest_run(
    document: object, workflow: str, sha: str, gate: str, errors: list[str]
) -> dict[str, object] | None:
    """The most recently created run of ``workflow`` at exactly ``sha``.

    The newest run is the evidence, so an older success cannot mask a newer
    failure, cancellation or run still in flight (#835). Runs are ordered by
    ``created_at`` and then ``id``; a matching run without both is an error,
    because an unordered set cannot say which run is current.
    """
    runs = document.get("workflow_runs", []) if isinstance(document, dict) else []
    matching = [
        run
        for run in runs
        if isinstance(run, dict) and run.get("path") == workflow and run.get("head_sha") == sha
    ]
    keyed: list[tuple[str, int, dict[str, object]]] = []
    for run in matching:
        created, run_id = run.get("created_at"), run.get("id")
        if not isinstance(created, str) or not isinstance(run_id, int):
            errors.append(
                f"{gate}: a {workflow} run at {sha} has no created_at or id; "
                "the newest run cannot be identified"
            )
            return None
        keyed.append((created, run_id, run))
    if not keyed:
        return None
    return max(keyed, key=lambda item: (item[0], item[1]))[2]


def _ascii(text: str) -> str:
    """``text`` with non-ASCII escaped, for lines a cp1252 console may print."""
    return text.encode("ascii", "backslashreplace").decode("ascii")


def gate_ci_evidence(version: str, errors: list[str], skipped: list[str]) -> None:
    """G9: the candidate's own completed ci.yml run carries every required job, green.

    Historical lines (before STRICT_ASSURANCE_FROM) pass as not applicable.
    Off a tag ref there is no release candidate, so G9 self-skips. On a tag
    ref, G9 takes the newest ci.yml run at ``GITHUB_SHA``, requires it to be
    completed, reads that one run's latest-attempt jobs, and requires every
    name in REQUIRED_CI_JOBS present exactly once and successful. Results are
    never combined across runs or commits.
    """
    line = _minor_line(version)
    if not _is_strict_line(line):
        print(f"G9: PASSED, not applicable to the historical {line} line (#835).")
        return
    if not os.environ.get("GITHUB_REF", "").startswith("refs/tags/"):
        _record_skip(skipped, "G9", "not a tag ref, no release candidate commit")
        return
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        errors.append("G9: GITHUB_SHA is unset on a tag ref; the release candidate is unknown")
        return
    try:
        runs_document = _get_json(f"{_api_base()}/actions/runs?head_sha={sha}")
    except (OSError, urllib.error.HTTPError, ValueError) as exc:
        errors.append(f"G9: could not read ci.yml runs at {sha}: {exc}")
        return
    run = _newest_run(runs_document, CI_WORKFLOW, sha, "G9", errors)
    if run is None:
        if not any(e.startswith("G9:") for e in errors):
            errors.append(f"G9: no ci.yml run at the release candidate commit {sha}")
        return
    if run.get("status") != "completed":
        errors.append(
            f"G9: the newest ci.yml run at {sha} is {run.get('status')}; "
            "pending evidence does not authorize a release"
        )
        return
    _check_required_jobs(run, sha, errors)


def _check_required_jobs(run: dict[str, object], sha: str, errors: list[str]) -> None:
    """G9's per-job check against the one ci.yml run ``run``."""
    try:
        document = _get_json(
            f"{_api_base()}/actions/runs/{run.get('id')}/jobs?filter=latest&per_page=100"
        )
    except (OSError, urllib.error.HTTPError, ValueError) as exc:
        errors.append(f"G9: could not read the jobs of ci.yml run {run.get('id')}: {exc}")
        return
    jobs = document.get("jobs", []) if isinstance(document, dict) else []
    total = document.get("total_count") if isinstance(document, dict) else None
    if not isinstance(total, int) or total > len(jobs):
        errors.append(f"G9: the job list of ci.yml run {run.get('id')} is incomplete or unreadable")
        return
    for name in REQUIRED_CI_JOBS:
        found = [j for j in jobs if isinstance(j, dict) and j.get("name") == name]
        if len(found) != 1:
            errors.append(
                f"G9: required job {_ascii(name)!r} appears {len(found)} times in ci.yml "
                f"run {run.get('id')} at {sha}"
            )
            continue
        conclusion = found[0].get("conclusion")
        if found[0].get("status") != "completed" or conclusion != "success":
            errors.append(
                f"G9: required job {_ascii(name)!r} is {conclusion or found[0].get('status')} "
                f"in ci.yml run {run.get('id')} at {sha}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release gate — public-surface lockstep checks.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO,
        help="repo root to check (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    errors: list[str] = []
    skipped: list[str] = []
    not_run: list[str] = []
    version = gate_versions_lockstep(root, errors)
    gate_changelog_rolled(root, version, errors)
    gate_readme_status_banner(root, version, errors)
    gate_readme_pypi_render_safe(root, errors)
    gate_workflows_sha_pinned(root, errors)
    gate_tag_matches(version, errors, skipped)
    gate_assurance_issues_closed(version, errors, skipped, not_run)
    gate_assurance_lane_green(version, errors, skipped, not_run)
    gate_ci_evidence(version, errors, skipped)
    ran = TOTAL_GATES - len(skipped) - len(not_run)
    coverage = f"{ran} of {TOTAL_GATES} gates ran"
    if skipped:
        coverage += f"; skipped {', '.join(skipped)}"
    if not_run:
        coverage += f"; not run {', '.join(not_run)}"

    if errors:
        print(
            f"RELEASE GATE: BLOCKED ({coverage}), "
            f"{len(errors)} stale surface(s) at version {version}:"
        )
        for e in errors:
            print(f"  FAIL  {e}")
        return 1
    on_tag = os.environ.get("GITHUB_REF", "").startswith("refs/tags/")
    if on_tag and not skipped and not not_run:
        sha = os.environ.get("GITHUB_SHA", "")
        print(
            f"RELEASE GATE: AUTHORIZED ({coverage}), public surfaces in lockstep at "
            f"version {version}, release candidate {sha}."
        )
        return 0
    # Exit 0 so ordinary CI stays green; the word PASS is withheld on purpose (#835).
    print(
        f"RELEASE GATE: PRELIMINARY ({coverage}), public surfaces in lockstep at "
        f"version {version}. Not release authorization: G6, G8 and G9 run only on a "
        "tag ref."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
