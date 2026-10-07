"""Real-tree release-gate control (#563 question 2, #735).

Seam: run ``scripts/release_gate.py`` against the repository this file lives
in, with no ``--root``, so the gate's verdict on the real tree is asserted
inside the required ``Test`` job. This is the opposite seam from
``tests/test_release_gate_206.py``, where every subprocess call passes
``--root`` and points the gate at a seeded ``tmp_path``. Those tests prove the
gate's rules. This one proves the rules hold on the tree being merged.

Why it belongs in the required job. The ``Release gate (surface lockstep)``
job is not a required status context. The two sibling guards are enforced
anyway, because each has a real-tree test inside the required ``Test`` job:
``test_real_tree_is_green_and_exits_zero`` in ``tests/test_drift_check.py``
and ``test_no_banned_copy_on_public_surfaces`` in
``tests/test_structural_bans.py``. The release gate was the one of the three
with no such test, so a stale README banner, an unrolled CHANGELOG or an
unpinned action reference reddened only advisory jobs. This module is that
missing test, not a change to branch protection.

Scope, stated so a reader does not over-read the green. G1 to G5 are read off
the tree and are what this control asserts. G6 self-skips off a tag ref. G7
runs: the real tree declares ``0.3.0``, and the ``0.3`` row of
``ASSURANCE_REQUIREMENTS`` requires issues #167-#174 closed, which the local
stub answers. G8 self-skips off a tag ref with "not a tag ref, no release
candidate commit" (#735): there is no release candidate on an ordinary push,
so G8 does not read the API at all. The stub is still wired to answer the
``actions/runs?head_sha=`` endpoint, because that is the only endpoint the
gate is allowed to ask for a run list; the request-set assertion below proves
the gate asks for nothing on this ref.

What a green here does not prove, stated generally. This control reads the
gate's verdict from outside and drives a tree that is already clean, so it
cannot tell a gate that asked its questions and found nothing from a gate that
stopped asking. The limit is a property of the seam, not of any one check.
Three mutation shapes are measured to survive this module:

1. ``gate_workflows_sha_pinned`` returning before its loop, which neuters G5.
2. ``gate_readme_status_banner`` returning before its body, which neuters G3.
3. ``errors = []`` inserted immediately before ``if errors:`` in ``main``,
   which discards every finding the gate made. This one survives here even
   when a genuinely stale surface is seeded at the same time, because the gate
   still prints PASS and exits 0.

``tests/test_release_gate_206.py`` kills shapes 2 and 3 and not shape 1. It
seeds a tree it has made stale on purpose and asserts the named failure rather
than the verdict, so the seeded seam, not this one, is what catches a gate
whose findings are discarded; closing shape 1 would mean giving G5 a seeded
unpinned action there, which it does not have anywhere in the suite. Shape 1
is recorded in ``docs/assurance/release-gate-red-563.md``. Shapes 2 and 3 were
measured by the independent verification recorded on pull request #569.

The red demonstrations are recorded in
``docs/assurance/release-gate-red-563.md``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import tomllib
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "release_gate.py"
RED_RECEIPT = REPO_ROOT / "docs" / "assurance" / "release-gate-red-563.md"
RUNS_PATH = "/actions/workflows/assurance.yml/runs"
HEAD_SHA_RUNS_PATH = "/actions/runs"


def _script_assurance_issues() -> list[int]:
    """The issue numbers the ``0.3`` row of the requirements table names.

    A literal copy here would drift silently: widening the script's range
    would make the stub 404 an issue it never heard of, and G7 fails closed,
    so a required job would redden with ``could not read assurance issue``.
    That reads as a GitHub outage, which is the one failure this module is
    built never to produce. #735 folded ``ASSURANCE_ISSUES`` into the ``0.3``
    row of ``ASSURANCE_REQUIREMENTS``, so this parses that row.
    """
    text = GATE.read_text(encoding="utf-8")
    m = re.search(
        r'"0\.3":\s*AssuranceRequirement\(issues=tuple\(range\((\d+), (\d+)\)\)',
        text,
        re.MULTILINE,
    )
    assert m, (
        "scripts/release_gate.py no longer declares the 0.3 row of "
        "ASSURANCE_REQUIREMENTS as AssuranceRequirement(issues=tuple(range(...)))"
    )
    return list(range(int(m.group(1)), int(m.group(2))))


class _Handler(BaseHTTPRequestHandler):
    """Serves the green G7 answer and the head_sha runs answer, 404s anything else.

    Unknown paths are refused rather than answered, so a change to which
    endpoint the gate reads surfaces here instead of being absorbed. The
    workflow-filtered endpoint is answered with a 404 that names #735: the
    gate must not ask for it on any ref.
    """

    issues: ClassVar[list[int]] = []
    seen: ClassVar[list[str]] = []
    head_sha: ClassVar[str] = "0" * 40

    def do_GET(self) -> None:
        type(self).seen.append(self.path)
        body: bytes | None = None
        path_only = self.path.split("?", 1)[0]
        if path_only == HEAD_SHA_RUNS_PATH:
            run = {
                "status": "completed",
                "conclusion": "success",
                "path": ".github/workflows/assurance.yml",
                "head_sha": type(self).head_sha,
            }
            body = json.dumps({"workflow_runs": [run]}).encode()
        elif path_only == RUNS_PATH:
            self.send_error(404, "workflow-filtered endpoint removed by #735")
            return
        for issue in type(self).issues:
            if path_only == f"/issues/{issue}":
                body = json.dumps({"number": issue, "state": "closed"}).encode()
        if body is None:
            self.send_error(404, "unexpected path")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the stub silent so pytest output stays readable."""


def _run_gate_on_real_tree(api_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke the gate with no ``--root``, so it resolves its own repository.

    ``PYTHONIOENCODING`` pins the child's pipe encoding: without it a Windows
    child encodes stdout as cp1252 and the gate's em dashes crash the utf-8
    decode. The ``GITHUB_REF`` pair and ``GITHUB_SHA`` are dropped so G6 and
    G8 self-skip on an ordinary push, and ``GITHUB_TOKEN`` so no credential
    reaches the local stub.
    """
    env = os.environ | {
        "RELEASE_GATE_GITHUB_API_URL": api_url,
        "PYTHONIOENCODING": "utf-8",
    }
    for inherited in ("GITHUB_REF", "GITHUB_REF_NAME", "GITHUB_TOKEN", "GITHUB_SHA"):
        env.pop(inherited, None)
    return subprocess.run(
        [sys.executable, str(GATE)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.fixture(scope="module")
def gate_run() -> Iterator[tuple[subprocess.CompletedProcess[str], list[str]]]:
    """One real-tree gate run, plus every path it asked the assurance stub for.

    Module-scoped because the gate is deterministic on a fixed tree, so a
    second subprocess would buy nothing and cost a second full run.
    """
    _Handler.issues = _script_assurance_issues()
    _Handler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = _run_gate_on_real_tree(f"http://127.0.0.1:{server.server_address[1]}")
        yield result, list(_Handler.seen)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_tree_passes_the_release_gate(
    gate_run: tuple[subprocess.CompletedProcess[str], list[str]],
) -> None:
    """The tree this commit produces is releasable on G1 to G5, with G7 green."""
    result, _ = gate_run

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RELEASE GATE: PASS" in result.stdout, result.stdout + result.stderr


def test_the_pass_line_names_the_version_this_tree_declares(
    gate_run: tuple[subprocess.CompletedProcess[str], list[str]],
) -> None:
    """The verdict is about this tree, not a constant the gate carries.

    Exit 0 and the PASS line alone cannot separate a working gate from one
    short-circuited to an empty failure list. The version in the PASS line
    can: the gate reads it from pyproject.toml at run time, so a gate that
    stopped reading the tree would have to invent it. This is the assertion
    that goes red under the second red demonstration in the receipt.
    """
    result, _ = gate_run
    declared = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = declared["project"]["version"]

    assert f"lockstep at version {version}." in result.stdout, result.stdout + result.stderr


def test_no_tag_ref_leaks_into_the_gate_environment(
    gate_run: tuple[subprocess.CompletedProcess[str], list[str]],
) -> None:
    """G6 self-skipped, so the environment scrub held.

    On a tag build of this repository the runner sets GITHUB_REF, and an
    unscrubbed environment would have G6 compare that tag to the tree. This
    control is about tree surfaces, so the scrub is what keeps a tag build
    from changing its verdict.
    """
    result, _ = gate_run

    assert "G6: not a tag ref" in result.stdout, result.stdout + result.stderr


def test_g8_self_skips_off_a_tag_ref_on_the_real_tree(
    gate_run: tuple[subprocess.CompletedProcess[str], list[str]],
) -> None:
    """#735: off a tag ref there is no release candidate, so G8 skips.

    The reason is named in the output, the summary counts the skip, and the
    stub is never asked for a run list. A green here does not prove G8 would
    accept a run at the release candidate; the seeded module owns that lane.
    """
    result, requested = gate_run

    assert "G8: SKIPPED, not a tag ref, no release candidate commit" in (result.stdout), (
        result.stdout + result.stderr
    )
    assert not any(HEAD_SHA_RUNS_PATH in path for path in requested), (
        f"G8 queried the runs endpoint off a tag ref on the real tree: {requested}"
    )
    assert RUNS_PATH not in requested, (
        f"the gate asked for the workflow-filtered endpoint: {requested}"
    )


def test_the_assurance_gates_asked_for_exactly_the_issues_the_script_names(
    gate_run: tuple[subprocess.CompletedProcess[str], list[str]],
) -> None:
    """G7 ran, and the stub answers the paths it actually requests.

    The stub 404s anything else and G7 fails closed, so a drift between the
    script's 0.3 row and what the stub serves would redden a required job
    with a message that reads like a GitHub outage. Asserting the request set
    turns that into a named mismatch instead. After #735 the only API reads
    on this ref are the G7 issue reads; G8 has no release candidate.
    """
    _, requested = gate_run
    expected = {f"/issues/{issue}" for issue in _script_assurance_issues()}

    assert set(requested) == expected, (
        "the gate's assurance reads have drifted from what this module's stub serves; "
        f"requested {sorted(set(requested))}, stub answers {sorted(expected)}"
    )


def test_red_receipt_names_the_command_the_mutation_and_the_exit_code() -> None:
    """The recorded demonstrations stay legible as evidence.

    The receipt is the durable half of #563's last acceptance criterion. A
    red demonstration that lives only in a session transcript is not evidence
    anyone can re-read.
    """
    text = RED_RECEIPT.read_text(encoding="utf-8")

    assert "python scripts/release_gate.py" in text
    assert "Status: v0.2.9" in text
    assert "Exit code: `1`" in text
    assert "test_the_pass_line_names_the_version_this_tree_declares" in text
