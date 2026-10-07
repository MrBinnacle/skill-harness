"""External release-gate contracts for the assurance gates (#206, #735).

Every test here drives ``scripts/release_gate.py`` as a subprocess against a
seeded repo tree (``--root``) and a local stand-in for the GitHub REST API. The
seeded tree passes G1-G6 by construction, so any ``FAIL`` line a run prints is
attributable to the assurance checks G7/G8 and nothing else — the assertions
compare the whole failure list, not a substring of it.

The tree is seeded rather than the version overridden: pointing the gate at a
version the tree does not declare would decouple the version checked from the
version shipped, which is the drift the gate exists to catch.

#735 changed the assurance contract. G7 and G8 are no longer scoped by a
hard-coded ``_is_zero_three`` predicate. They read a declared requirements
table keyed by minor line. An undeclared line fails closed: both gates print
``NOT RUN`` and the gate blocks. A declared replacement (empty G7 list, or G8
not required) passes by declaration and never prints ``SKIPPED``. G8 on a tag
ref counts only a green ``assurance.yml`` run at ``GITHUB_SHA``; off a tag ref
G8 self-skips as "no release candidate commit" and never falls back to any
historical green run.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "release_gate.py"
RED_RECEIPT = ROOT / "docs" / "assurance" / "release-gate-red-206.md"
ZERO_THREE_ISSUES = tuple(range(167, 175))
GREEN_RUN = {
    "status": "completed",
    "conclusion": "success",
    "path": ".github/workflows/assurance.yml",
    "head_sha": "",
}
# The workflow-filtered endpoint #735 removes from the gate. Kept as a named
# constant so the "never queried" assertion below is not a magic string.
FORBIDDEN_RUNS_PATH = "/actions/workflows/assurance.yml/runs"

# One SHA-pinned action so G5 passes on a populated workflows directory rather
# than on an empty one.
_PINNED_WORKFLOW = """\
jobs:
  build:
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
"""


def _seed_tree(root: Path, version: str, banner_version: str | None = None) -> Path:
    """Write the minimal tree that satisfies G1-G5 at ``version``.

    ``banner_version`` names the version the README status banner claims. It
    defaults to ``version``, which is the lockstep G3 requires. Passing a
    different value is the G3 mutant: one surface of the tree names a version
    the tree does not declare.
    """
    banner = banner_version if banner_version is not None else version
    files = {
        "pyproject.toml": f'[project]\nname = "skill-harness-seed"\nversion = "{version}"\n',
        "src/skill_harness/__init__.py": f'__version__ = "{version}"\n',
        "CHANGELOG.md": (
            f"# Changelog\n\n## [Unreleased]\n\n## [{version}] — 2026-08-16\n\n"
            "### Added\n- Seeded entry.\n\n"
            f"[{version}]: https://github.com/MrBinnacle/skill-harness/releases\n"
        ),
        "README.md": (
            f"# Seed\n\nStatus: v{banner} on PyPI. "
            "[PyPI](https://pypi.org/project/skill-harness/)\n"
        ),
        ".github/workflows/ci.yml": _PINNED_WORKFLOW,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _gate_env(
    api_url: str,
    token: str | None = None,
    ref: str | None = None,
    sha: str | None = None,
) -> dict[str, str]:
    """Gate environment: seeded API base, no inherited tag ref (G6) unless set.

    ``PYTHONIOENCODING`` pins the child's pipe encoding. Without it, a
    Windows child encodes stdout as cp1252, so the gate's em-dashes
    (0x97) crash ``_invoke``'s utf-8 decode inside the reader thread.
    ``GITHUB_TOKEN`` is set only when ``token`` is given, never inherited.
    ``GITHUB_REF``/``GITHUB_REF_NAME``/``GITHUB_SHA`` are set only when the
    caller asks for a tag-ref or non-tag environment.
    """
    env = os.environ | {
        "RELEASE_GATE_GITHUB_API_URL": api_url,
        "PYTHONIOENCODING": "utf-8",
    }
    for inherited in ("GITHUB_REF", "GITHUB_REF_NAME", "GITHUB_TOKEN", "GITHUB_SHA"):
        env.pop(inherited, None)
    if token is not None:
        env["GITHUB_TOKEN"] = token
    if ref is not None:
        env["GITHUB_REF"] = ref
        if ref.startswith("refs/tags/"):
            env["GITHUB_REF_NAME"] = ref.removeprefix("refs/tags/")
    if sha is not None:
        env["GITHUB_SHA"] = sha
    return env


def _invoke(
    root: Path,
    api_url: str,
    token: str | None = None,
    ref: str | None = None,
    sha: str | None = None,
    script: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the gate (the real script, or ``script`` when a test copies it)."""
    target = script if script is not None else GATE
    return subprocess.run(
        [sys.executable, str(target), "--root", str(root)],
        cwd=str(ROOT),
        env=_gate_env(api_url, token=token, ref=ref, sha=sha),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _run_gate(
    root: Path,
    issue_states: dict[int, str],
    workflow_runs: list[dict[str, str]],
    token: str | None = None,
    seen_auth: list[str | None] | None = None,
    seen_paths: list[str] | None = None,
    ref: str | None = None,
    sha: str | None = None,
    script: Path | None = None,
    filter_runs_by_head_sha: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run the gate against ``root`` with the GitHub answers seeded locally.

    ``seen_auth``, when given, receives the Authorization header of every
    request the gate makes (``None`` for a request without one).
    ``seen_paths`` receives the request path of every request.
    The stub answers ``/issues/<n>`` and ``/actions/runs?head_sha=<sha>``.
    It 404s the workflow-filtered endpoint; the gate must never ask for it.

    ``filter_runs_by_head_sha`` controls whether the ``/actions/runs``
    answer is filtered to the queried ``head_sha``. The default matches
    GitHub's real endpoint. Passing ``False`` returns every seeded run
    regardless of the query, which is the shape that pins G8's own
    ``run.get("head_sha") == sha`` clause: a stub that filters first can
    never show the gate a run at another commit, so deleting the clause
    would leave the suite green.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if seen_auth is not None:
                seen_auth.append(self.headers.get("Authorization"))
            if seen_paths is not None:
                seen_paths.append(self.path)
            path_only = self.path.split("?", 1)[0]
            if path_only == "/actions/runs":
                sha_query = ""
                if "?" in self.path:
                    for pair in self.path.split("?", 1)[1].split("&"):
                        if pair.startswith("head_sha="):
                            sha_query = pair.removeprefix("head_sha=")
                if filter_runs_by_head_sha:
                    matching = [run for run in workflow_runs if run.get("head_sha") == sha_query]
                else:
                    matching = list(workflow_runs)
                self._respond(200, {"workflow_runs": matching})
                return
            if path_only == FORBIDDEN_RUNS_PATH:
                self._respond(
                    404,
                    {"message": "workflow-filtered endpoint removed by #735"},
                )
                return
            if path_only.startswith("/issues/"):
                issue = int(path_only.removeprefix("/issues/"))
                state = issue_states.get(issue)
                if state is None:
                    self._respond(404, {"message": f"issue #{issue} not seeded"})
                    return
                self._respond(200, {"state": state})
                return
            self._respond(404, {"message": f"unseeded path {self.path}"})

        def _respond(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Silence the stderr access log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        return _invoke(
            root,
            f"http://127.0.0.1:{server.server_port}",
            token=token,
            ref=ref,
            sha=sha,
            script=script,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _failures(result: subprocess.CompletedProcess[str]) -> list[str]:
    """The gate's listed failures, in order, without the ``FAIL`` prefix."""
    return [
        line.strip().removeprefix("FAIL").strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("FAIL")
    ]


def _closed() -> dict[int, str]:
    return dict.fromkeys(ZERO_THREE_ISSUES, "closed")


def _run_record(
    sha: str,
    *,
    path: str = ".github/workflows/assurance.yml",
    status: str = "completed",
    conclusion: str = "success",
) -> dict[str, str]:
    """One seeded workflow run at ``sha``."""
    return {
        "status": status,
        "conclusion": conclusion,
        "path": path,
        "head_sha": sha,
    }


def _dead_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        _host, port = probe.getsockname()
        assert isinstance(port, int)
        return port


def _script_with_declared_row(
    tmp_path: Path,
    line: str,
    issues: tuple[int, ...],
    g8_required: bool,
) -> Path:
    """A copy of the gate script with one extra declared requirement row.

    The requirements table lives in the script, which is the repo. A test
    cannot add a production row (#735 forbids that for this ticket), so the
    declared-replacement lane copies the script and inserts a row. The copy
    is still the shipped lookup logic; only the declaration differs.
    """
    text = GATE.read_text(encoding="utf-8")
    if issues == ():
        issues_repr = "()"
    elif issues == tuple(range(issues[0], issues[-1] + 1)):
        issues_repr = f"tuple(range({issues[0]}, {issues[-1] + 1}))"
    else:
        issues_repr = "(" + ", ".join(str(i) for i in issues) + ")"
    row = f'    "{line}": AssuranceRequirement(issues={issues_repr}, g8_required={g8_required}),\n'
    needle = "ASSURANCE_REQUIREMENTS: dict[str, AssuranceRequirement] = {\n"
    assert needle in text, (
        "scripts/release_gate.py no longer declares ASSURANCE_REQUIREMENTS "
        "in the form this module's copy helper inserts into"
    )
    copy = tmp_path / f"release_gate_{line.replace('.', '_')}.py"
    copy.write_text(text.replace(needle, needle + row, 1), encoding="utf-8")
    return copy


def _coverage(stdout: str) -> tuple[int, int, set[str], set[str]]:
    """The summary's coverage claim, as numbers rather than as a string.

    Returns (ran, total, skipped, not_run). The assertions below lock the
    SHAPE and the arithmetic, never the literals. A test that pinned "7 of 8
    gates ran" would couple every gate assertion to TOTAL_GATES, so adding a
    ninth gate would redden tests that have nothing to say about it.
    """
    match = re.search(
        r"(\d+) of (\d+) gates ran"
        r"(?:; skipped ([A-Z0-9, ]+))?"
        r"(?:; not run ([A-Z0-9, ]+))?",
        stdout,
    )
    assert match is not None, f"no coverage line in gate output: {stdout!r}"
    skipped_named = match.group(3)
    not_run_named = match.group(4)
    skipped = {token.strip() for token in skipped_named.split(",")} if skipped_named else set()
    not_run = {token.strip() for token in not_run_named.split(",")} if not_run_named else set()
    return int(match.group(1)), int(match.group(2)), skipped, not_run


def test_zero_three_release_passes_when_assurance_is_closed(tmp_path: Path) -> None:
    """The positive case: G7 is satisfiable, not a permanent block.

    Off a tag ref G8 self-skips (no release candidate), so a closed 0.3 tree
    is still releasable. Without this, the blocked cases below would stay
    green if G7 appended its failures unconditionally.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _run_gate(root, _closed(), [])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout
    assert _failures(result) == []


def test_the_assurance_reads_authenticate_when_a_token_is_present(tmp_path: Path) -> None:
    """Unauthenticated reads share a 60-per-hour budget per runner IP, and a
    shared CI runner exhausts it: main went red on 2026-09-10 with G7 failing
    "HTTP Error 403: rate limit exceeded" on every read.

    Off a tag ref only G7 reads the API; G8 has no release candidate and
    self-skips, so the request set is exactly the declared 0.3 issues.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    seen: list[str | None] = []
    result = _run_gate(root, _closed(), [], token="seed-token", seen_auth=seen)

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(seen) == len(ZERO_THREE_ISSUES)
    assert set(seen) == {"Bearer seed-token"}


def test_the_assurance_reads_send_no_credential_without_a_token(tmp_path: Path) -> None:
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    seen: list[str | None] = []
    result = _run_gate(root, _closed(), [], seen_auth=seen)

    assert result.returncode == 0, result.stdout + result.stderr
    assert seen and set(seen) == {None}


def test_zero_three_release_is_blocked_while_an_assurance_issue_is_open(tmp_path: Path) -> None:
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    states = _closed() | {169: "open"}
    result = _run_gate(root, states, [])

    assert result.returncode == 1
    assert _failures(result) == ["G7: assurance issue #169 is open"]


def test_zero_three_row_reads_the_same_assurance_issues_as_before(tmp_path: Path) -> None:
    """Criterion 7: the 0.3 row reproduces the pre-#735 issue range exactly.

    ``ASSURANCE_ISSUES = range(167, 175)`` was folded into the ``0.3`` row.
    The stub 404s any issue outside the seeded set and G7 fails closed, so a
    widened or narrowed range reddens here with a named mismatch rather than
    as a GitHub outage. The request-set assertion is the external evidence:
    the gate asked for exactly 167 to 174.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    seen_paths: list[str] = []
    result = _run_gate(root, _closed(), [], seen_paths=seen_paths)

    assert result.returncode == 0, result.stdout + result.stderr
    expected = {f"/issues/{n}" for n in ZERO_THREE_ISSUES}
    assert set(seen_paths) == expected, (
        "the 0.3 row's issue reads drifted from 167-174; "
        f"requested {sorted(set(seen_paths))}, expected {sorted(expected)}"
    )


def test_unknown_minor_line_fails_closed_with_not_run_for_g7_and_g8(tmp_path: Path) -> None:
    """Criterion 1: a version whose minor line has no row blocks the gate.

    #735 replaces ``_is_zero_three`` with a declared requirements table. An
    undeclared line is a tree property — the table lives in the repo — so it
    fails on every ref, including ordinary CI. G7 and G8 each print ``NOT
    RUN``, each adds an error, and the gate exits 1. They do not print
    ``SKIPPED``: a gate with no declared requirement has not been waived, it
    has been refused.
    """
    root = _seed_tree(tmp_path, "0.4.0")
    result = _run_gate(root, issue_states={}, workflow_runs=[])

    assert result.returncode == 1, result.stdout + result.stderr
    assert "RELEASE GATE: BLOCKED" in result.stdout, result.stdout + result.stderr
    assert "G7: NOT RUN, no assurance requirement is declared for the 0.4 line" in (
        result.stdout
    ), result.stdout + result.stderr
    assert "G8: NOT RUN, no assurance requirement is declared for the 0.4 line" in (
        result.stdout
    ), result.stdout + result.stderr
    assert "add a row to ASSURANCE_REQUIREMENTS before releasing 0.4.x" in (result.stdout), (
        result.stdout + result.stderr
    )
    assert "G7: SKIPPED" not in result.stdout
    assert "G8: SKIPPED" not in result.stdout

    ran, total, skipped, not_run = _coverage(result.stdout)
    assert {"G7", "G8"} <= not_run, f"summary does not name G7 and G8 as not run: {not_run}"
    assert "G7" not in skipped and "G8" not in skipped, (
        f"a NOT RUN gate was counted as skipped: {skipped}"
    )
    assert ran + len(skipped) + len(not_run) == total, (
        f"{ran} ran plus {skipped} skipped plus {not_run} not run is not {total}"
    )


def test_unknown_minor_line_blocks_even_a_patch_release(tmp_path: Path) -> None:
    """The same fail-closed rule on another undeclared line.

    Differential pair with the 0.4 case above: identical GitHub state, the
    only difference is the declared version. Before #735 a 0.2.x patch was
    exempt because ``_is_zero_three`` was false; after #735 an undeclared
    line blocks, whatever its patch number. That is the intended outcome.
    """
    root = _seed_tree(tmp_path, "0.2.4")
    result = _run_gate(root, issue_states={}, workflow_runs=[])

    assert result.returncode == 1, result.stdout + result.stderr
    assert "G7: NOT RUN, no assurance requirement is declared for the 0.2 line" in (
        result.stdout
    ), result.stdout + result.stderr
    assert "G8: NOT RUN, no assurance requirement is declared for the 0.2 line" in (
        result.stdout
    ), result.stdout + result.stderr
    assert "RELEASE GATE: BLOCKED" in result.stdout


def test_declared_empty_requirement_passes_by_declaration(tmp_path: Path) -> None:
    """Criterion 2: a declared replacement passes by declaration, never SKIPPED.

    A row whose G7 list is explicitly empty and whose G8 flag is explicitly
    false makes both gates pass and print that they passed by declaration,
    naming the row. The API base points at a dead port: the gate must not
    read the network at all, which is the external proof that the
    declaration, not an empty result set, is what passed the gate.
    """
    script = _script_with_declared_row(tmp_path, "0.9", (), g8_required=False)
    root = _seed_tree(tmp_path / "tree", "0.9.0")
    dead = _dead_port()
    result = _invoke(root, f"http://127.0.0.1:{dead}", script=script)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout, result.stdout + result.stderr
    assert "G7: PASSED by declaration" in result.stdout, result.stdout + result.stderr
    assert "G8: PASSED by declaration" in result.stdout, result.stdout + result.stderr
    assert "row '0.9'" in result.stdout, result.stdout + result.stderr
    assert "G7: SKIPPED" not in result.stdout
    assert "G8: SKIPPED" not in result.stdout

    ran, total, skipped, not_run = _coverage(result.stdout)
    assert "G7" not in skipped and "G8" not in skipped
    assert "G7" not in not_run and "G8" not in not_run
    assert ran + len(skipped) + len(not_run) == total


def test_g8_fails_when_the_green_run_is_at_another_sha(tmp_path: Path) -> None:
    """Criterion 3: a green run at any other SHA does not count.

    Tag ref at ``sha_a``; the stub's only successful assurance run is at
    ``sha_b``. G8 fails and the message names ``sha_a`` and how to produce
    the run. Before #735 G8 accepted any historical success, so this exact
    pair of SHAs was the hole the ticket closes.

    This arm filters the stub answer by the queried ``head_sha``, so the
    gate never sees the ``sha_b`` run. The companion test below returns the
    ``sha_b`` run unfiltered and pins G8's own head-equality clause.
    """
    sha_a = "a" * 40
    sha_b = "b" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record(sha_b)],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    g8 = [f for f in _failures(result) if f.startswith("G8:")]
    assert len(g8) == 1, _failures(result)
    assert sha_a in g8[0], g8[0]
    assert "gh workflow run assurance.yml --ref v0.3.0" in g8[0], g8[0]
    assert sha_b not in g8[0] or sha_a in g8[0]


def test_g8_fails_when_a_green_run_at_another_sha_is_returned_unfiltered(
    tmp_path: Path,
) -> None:
    """R1-F1: G8's ``head_sha == sha`` clause, pinned against an unfiltered stub.

    The stub returns every seeded run regardless of the ``head_sha`` query,
    which is the only shape that can show G8 a green ``assurance.yml`` run at
    ``sha_b`` while the release candidate is ``sha_a``. Deleting
    ``run.get("head_sha") == sha`` from the gate makes this test red: the
    mutant sees the green run, prints ``RELEASE GATE: PASS (8 of 8 gates
    ran)``, and exits 0. With the clause present G8 fails and the message
    names ``sha_a``.
    """
    sha_a = "a" * 40
    sha_b = "b" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record(sha_b)],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
        filter_runs_by_head_sha=False,
    )

    assert result.returncode == 1, (
        "G8 accepted a green assurance run at another SHA when the stub "
        f"returned it unfiltered.\n{result.stdout}{result.stderr}"
    )
    g8 = [f for f in _failures(result) if f.startswith("G8:")]
    assert len(g8) == 1, _failures(result)
    assert sha_a in g8[0], g8[0]
    assert "gh workflow run assurance.yml --ref v0.3.0" in g8[0], g8[0]


def test_one_part_version_fails_closed_with_not_run(tmp_path: Path) -> None:
    """R1-F2: ``_minor_line``'s one-part fallback, pinned by a one-part version.

    A version with no minor component (``"0"``) has no declared row, so G7
    and G8 each print NOT RUN and the gate blocks. Deleting the fallback
    branch of ``_minor_line`` makes this test red with an IndexError instead
    of the NOT RUN lines.
    """
    root = _seed_tree(tmp_path, "0")
    result = _run_gate(root, issue_states={}, workflow_runs=[])

    assert result.returncode == 1, result.stdout + result.stderr
    assert "RELEASE GATE: BLOCKED" in result.stdout, result.stdout + result.stderr
    assert "G7: NOT RUN, no assurance requirement is declared for the 0 line" in (result.stdout), (
        result.stdout + result.stderr
    )
    assert "G8: NOT RUN, no assurance requirement is declared for the 0 line" in (result.stdout), (
        result.stdout + result.stderr
    )
    assert "G7: SKIPPED" not in result.stdout
    assert "G8: SKIPPED" not in result.stdout
    assert "IndexError" not in result.stderr, result.stderr


def test_g8_passes_when_the_green_run_is_at_the_release_candidate_sha(tmp_path: Path) -> None:
    """Criterion 4, green arm: a green assurance run at GITHUB_SHA counts."""
    sha_a = "a" * 40
    sha_b = "b" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record(sha_b), _run_record(sha_a)],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout
    assert _failures(result) == []


def test_g8_fails_when_the_run_at_the_sha_is_another_workflow(tmp_path: Path) -> None:
    """Criterion 4: a green run at the right SHA but the wrong workflow path fails."""
    sha_a = "a" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record(sha_a, path=".github/workflows/ci.yml")],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    g8 = [f for f in _failures(result) if f.startswith("G8:")]
    assert len(g8) == 1, _failures(result)
    assert sha_a in g8[0], g8[0]


@pytest.mark.parametrize(
    ("status", "conclusion", "case"),
    [
        ("completed", "failure", "a completed red run"),
        ("completed", "", "a run with no conclusion"),
        ("in_progress", "", "a run still in flight"),
    ],
    ids=["red-run", "no-conclusion", "in-flight-run"],
)
def test_g8_fails_when_the_run_at_the_sha_is_not_success(
    tmp_path: Path, status: str, conclusion: str, case: str
) -> None:
    """Criterion 4: only a completed successful run at the right SHA passes."""
    sha_a = "a" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record(sha_a, status=status, conclusion=conclusion)],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
    )

    assert result.returncode == 1, f"{case} must not satisfy G8"
    g8 = [f for f in _failures(result) if f.startswith("G8:")]
    assert len(g8) == 1, _failures(result)
    assert sha_a in g8[0], g8[0]


def test_g8_fails_when_github_sha_is_unset_on_a_tag_ref(tmp_path: Path) -> None:
    """Criterion 5: a tag ref without GITHUB_SHA is an error, not a skip.

    The release candidate commit cannot be identified, so G8 cannot check it.
    Before #735 this shape was either a silent skip or an any-success pass;
    #735 makes it a named failure.
    """
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        _closed(),
        [_run_record("a" * 40)],
        ref="refs/tags/v0.3.0",
        sha=None,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    failures = _failures(result)
    assert any(f.startswith("G8:") and "GITHUB_SHA is unset" in f for f in failures), failures
    assert "G8: SKIPPED" not in result.stdout


def test_g8_skips_off_a_tag_ref_with_no_release_candidate(tmp_path: Path) -> None:
    """Criterion 6, behaviour half: off a tag ref G8 self-skips, like G6.

    The skip reason is "not a tag ref, no release candidate commit". The
    summary counts it. G8 does not fall back to any historical green run: a
    stub that would answer a head_sha query is never consulted.
    """
    root = _seed_tree(tmp_path, "0.3.0")
    seen_paths: list[str] = []
    result = _run_gate(
        root,
        _closed(),
        [_run_record("a" * 40)],
        seen_paths=seen_paths,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "G8: SKIPPED, not a tag ref, no release candidate commit" in (result.stdout), (
        result.stdout + result.stderr
    )
    assert "G8: SKIPPED" in result.stdout

    ran, total, skipped, not_run = _coverage(result.stdout)
    assert "G8" in skipped, f"summary does not name G8 as skipped: {skipped}"
    assert "G8" not in not_run
    assert ran + len(skipped) + len(not_run) == total
    assert not any("/actions/runs" in path for path in seen_paths), (
        f"G8 queried the runs endpoint off a tag ref: {seen_paths}"
    )


def test_the_script_never_queries_the_workflow_filtered_endpoint() -> None:
    """Criterion 6, source half: the gate no longer names the removed endpoint.

    ``actions/workflows/assurance.yml/runs`` answered "any run ever green",
    which is the stale-evidence hole #735 closes. The replacement is
    ``actions/runs?head_sha=<sha>``. This assertion greps the shipped script,
    so a reintroduction of the old endpoint reddens the suite even if no
    behavioural test happens to hit it.
    """
    text = GATE.read_text(encoding="utf-8")
    assert FORBIDDEN_RUNS_PATH not in text, (
        "scripts/release_gate.py queries the workflow-filtered endpoint again; "
        "#735 binds G8 to actions/runs?head_sha="
    )
    assert "/actions/runs?head_sha=" in text


def test_zero_three_release_is_blocked_when_the_assurance_state_is_unreadable(
    tmp_path: Path,
) -> None:
    """Fail closed: an API the gate cannot read is not evidence of a green lane.

    Run on a tag ref so both G7 and G8 attempt their reads. Off a tag ref G8
    has no release candidate and skips without reading.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _invoke(
        root,
        f"http://127.0.0.1:{_dead_port()}",
        ref="refs/tags/v0.3.0",
        sha="a" * 40,
    )

    assert result.returncode == 1
    assert "RELEASE GATE: PASS" not in result.stdout
    failures = _failures(result)
    assert any(f.startswith("G7: could not read assurance issue #167") for f in failures), failures
    assert any(f.startswith("G8: could not read assurance workflow runs") for f in failures), (
        failures
    )


def test_gate_reports_g7_running_and_g8_skipping_on_the_zero_three_line(tmp_path: Path) -> None:
    """On 0.3 off a tag ref: G7 runs, G8 skips, G6 skips. The summary is honest.

    Negative control for an implementation that printed a skip line for G7
    unconditionally, or that counted a NOT RUN gate as skipped. Before #735
    this shape was "all eight ran"; after #735 the release candidate is the
    thing G8 needs, and there is none off a tag ref.
    """
    root = _seed_tree(tmp_path, "0.3.9")
    result = _run_gate(
        root,
        issue_states=dict.fromkeys(ZERO_THREE_ISSUES, "closed"),
        workflow_runs=[],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "G7: SKIPPED" not in result.stdout, "G7 reported as skipped on the 0.3 line"
    assert "G7: NOT RUN" not in result.stdout
    assert "G8: SKIPPED, not a tag ref, no release candidate commit" in result.stdout

    ran, total, skipped, not_run = _coverage(result.stdout)
    assert "G7" not in skipped, f"G7 self-skipped on the 0.3 line: {skipped}"
    assert "G7" not in not_run, f"G7 was NOT RUN on the 0.3 line: {not_run}"
    assert skipped == {"G6", "G8"}, f"expected G6 and G8 to self-skip, got {skipped}"
    assert ran + len(skipped) + len(not_run) == total


def test_gate_reports_all_eight_running_on_a_tag_ref(tmp_path: Path) -> None:
    """On a tag ref the release candidate exists, so G8 runs rather than skips."""
    sha_a = "a" * 40
    root = _seed_tree(tmp_path, "0.3.0")
    result = _run_gate(
        root,
        issue_states=dict.fromkeys(ZERO_THREE_ISSUES, "closed"),
        workflow_runs=[_run_record(sha_a)],
        ref="refs/tags/v0.3.0",
        sha=sha_a,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "G6: not a tag ref" not in result.stdout
    assert "G7: SKIPPED" not in result.stdout
    assert "G8: SKIPPED" not in result.stdout

    ran, total, skipped, not_run = _coverage(result.stdout)
    assert not skipped, f"a gate self-skipped on a tag ref: {skipped}"
    assert not not_run, f"a gate was NOT RUN on a tag ref: {not_run}"
    assert ran == total, f"{ran} of {total} gates ran on a tag ref"


G3_STALE_BANNER = (
    "G3: README.md status banner does not say 'Status: v0.2.4' "
    "(found 'Status: v0.2.3') - repository-internal check against "
    "pyproject.toml; it cannot observe the published package"
)


def test_release_is_blocked_when_the_readme_banner_names_another_version(
    tmp_path: Path,
) -> None:
    """The G3 red control: a stale README banner blocks the release.

    Differential pair. Both arms seed the identical tree at 0.2.4; the arms
    differ only in the version the README status banner names. Before #735
    the green arm relied on 0.2.x being outside the assurance scope; after
    #735 both arms need a declared row, so the green arm runs a script copy
    that declares 0.2. The red arm's single failure is attributable to G3.
    """
    script = _script_with_declared_row(tmp_path, "0.2", ZERO_THREE_ISSUES, True)
    matched = _seed_tree(tmp_path / "matched", "0.2.4")
    green = _run_gate(matched, _closed(), [], script=script)
    assert green.returncode == 0, green.stdout + green.stderr
    assert _failures(green) == []

    stale = _seed_tree(tmp_path / "stale", "0.2.4", banner_version="0.2.3")
    red = _run_gate(stale, _closed(), [], script=script)

    assert _failures(red) == [G3_STALE_BANNER], (
        "G3 did not report the stale banner. The gate printed:\n" + red.stdout + red.stderr
    )
    assert red.returncode == 1, red.stdout + red.stderr
    assert "RELEASE GATE: PASS" not in red.stdout


def test_the_g3_failure_states_the_scope_it_actually_checks(tmp_path: Path) -> None:
    """G3 names its limit in the message a maintainer reads.

    G3 compares two surfaces of one tree and makes no network call, so it
    cannot show that the published package carries this version. The message
    has to say that; a gate whose name implies more than it checks is the
    defect this control exists to prevent.
    """
    script = _script_with_declared_row(tmp_path, "0.2", ZERO_THREE_ISSUES, True)
    stale = _seed_tree(tmp_path / "stale", "0.2.4", banner_version="0.2.3")
    result = _run_gate(stale, _closed(), [], script=script)

    (failure,) = [f for f in _failures(result) if f.startswith("G3:")]
    assert "repository-internal check against pyproject.toml" in failure
    assert "it cannot observe the published package" in failure


_TAG_PINNED_WORKFLOW = """jobs:
  build:
    steps:
      - uses: actions/checkout@v5
"""


def test_g5_reads_yaml_workflows_as_well_as_yml(tmp_path: Path) -> None:
    """The G5 scope control: `.yaml` is a workflow suffix GitHub runs.

    Differential pair. Both arms seed the identical tree at 0.2.4 with a
    script copy that declares the 0.2 line; the arms differ only in whether
    a second workflow file named with the `.yaml` suffix is present. The red
    arm's single failure is attributable to G5 reading that file.
    """
    script = _script_with_declared_row(tmp_path, "0.2", ZERO_THREE_ISSUES, True)
    matched = _seed_tree(tmp_path / "yml-only", "0.2.4")
    green = _run_gate(matched, _closed(), [], script=script)
    assert green.returncode == 0, green.stdout + green.stderr
    assert _failures(green) == []

    widened = _seed_tree(tmp_path / "with-yaml", "0.2.4")
    (widened / ".github/workflows/release.yaml").write_text(_TAG_PINNED_WORKFLOW, encoding="utf-8")
    red = _run_gate(widened, _closed(), [], script=script)

    assert _failures(red) == [
        "G5: release.yaml:4 action not SHA-pinned: '- uses: actions/checkout@v5' "
        "(mutable refs are not provenance)"
    ], (
        "G5 did not report the tag pin in the .yaml workflow. The gate printed:\n"
        + red.stdout
        + red.stderr
    )
    assert red.returncode == 1, red.stdout + red.stderr


def _recorded_transcript() -> list[str]:
    """The lines of the receipt's fenced output block."""
    text = RED_RECEIPT.read_text(encoding="utf-8")
    _, _, after = text.partition("```text\n")
    block, fence, _ = after.partition("```")
    assert fence, "the RED receipt has no ```text output block"
    return [line for line in block.splitlines() if line.strip()]


def test_red_receipt_records_the_output_the_gate_actually_prints(tmp_path: Path) -> None:
    """The receipt is checked against the run, not just read for keywords.

    The recorded transcript is the demonstration's evidence. Comparing it to
    prose only would let the gate's copy change under it — the receipt would
    keep asserting a line the program no longer prints.

    #735 re-recorded this transcript: G8 now self-skips off a tag ref, so
    the same seeded scenario yields one failure (the open issue) rather than
    two.
    """
    root = _seed_tree(tmp_path / "tree", "0.3.0")
    result = _run_gate(root, _closed() | {169: "open"}, [])

    assert result.returncode == 1
    recorded = _recorded_transcript()
    assert recorded, "the RED receipt records no output"
    printed = [line for line in result.stdout.splitlines() if line.strip()]
    assert recorded == printed, (
        "receipt transcript has drifted from the gate's output:\n"
        f"recorded:\n{chr(10).join(recorded)}\n\nactual:\n{result.stdout}"
    )


def test_red_receipt_names_the_command_and_exit_code() -> None:
    text = RED_RECEIPT.read_text(encoding="utf-8")

    assert "RELEASE_GATE_GITHUB_API_URL" in text
    assert "python scripts/release_gate.py --root" in text
    assert "Exit code: `1`" in text
